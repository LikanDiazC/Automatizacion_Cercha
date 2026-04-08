"""
Event bus asíncrono in-memory para el Centro de Comando de IA.

Patrón pub/sub con las siguientes garantías:
  • Non-blocking: `publish()` nunca espera; usa `put_nowait` sobre colas
    bounded y descarta mensajes si un suscriptor está saturado (back-
    pressure local — protege al pipeline de matching).
  • Thread-safe vía asyncio.Lock para el registro/baja de suscriptores.
  • Zero deps externas (solo asyncio + dataclasses + json).

Uso desde el pipeline:
    from .event_bus import publish_event, MatchEvent
    publish_event(MatchEvent(
        event_type="layer_decision",
        layer="capa_1_5",
        decision="reject",
        ...
    ))

Uso desde el endpoint WebSocket:
    async with subscribe() as queue:
        while True:
            event = await queue.get()
            await ws.send_json(event)
"""
from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import AsyncIterator, Literal, Optional

logger = logging.getLogger(__name__)

# Tamaño por cola de suscriptor. Si un cliente WebSocket se queda atrás
# (red lenta / DevTools pausado), perderá mensajes a partir de N pendientes
# en lugar de bloquear el pipeline.
_SUBSCRIBER_QUEUE_MAXSIZE: int = 256

# Ring buffer de histórico — permite que un cliente que se conecte DESPUÉS
# de que haya corrido el pipeline siga pudiendo diagnosticar las decisiones
# recientes. Es in-memory y se pierde al reiniciar el proceso.
_HISTORY_MAXLEN: int = 1000


# ---------------------------------------------------------------------------
# Payload estructurado
# ---------------------------------------------------------------------------

Decision = Literal["match", "reject", "pass_through", "cache_hit"]
Layer = Literal[
    "pre_ratio",
    "capa_0_etim",
    "capa_0_5_marca",
    "capa_1_unit",
    "capa_1_5_graph",
    "capa_2_embedding",
    "capa_3_llm",
    "capa_4_jaccard",
    "cache",
]


@dataclass
class ProductoRef:
    """Vista ligera de un producto para serializar al frontend."""
    id: int
    sku: str
    nombre: str
    marca: str = ""
    proveedor: str = ""


@dataclass
class MatchEvent:
    """
    Evento estructurado emitido por el pipeline al tomar una decisión.

    Se serializa a JSON y viaja por WebSocket al frontend. Mantenerlo
    pequeño y plano facilita el parsing y la visualización en tiempo real.
    """
    event_type: Literal["layer_decision", "pipeline_end", "heartbeat"] = "layer_decision"
    layer: Layer = "capa_0_etim"
    decision: Decision = "pass_through"
    producto_a: Optional[ProductoRef] = None
    producto_b: Optional[ProductoRef] = None
    confidence: float = 0.0
    similitud_coseno: float = 0.0
    razon: str = ""
    latencia_ms: float = 0.0
    tokens: int = 0
    costo_usd: float = 0.0
    metodo: str = ""
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Redondeos defensivos para payloads ligeros
        d["confidence"] = round(float(d.get("confidence") or 0.0), 4)
        d["similitud_coseno"] = round(float(d.get("similitud_coseno") or 0.0), 4)
        d["latencia_ms"] = round(float(d.get("latencia_ms") or 0.0), 2)
        d["costo_usd"] = round(float(d.get("costo_usd") or 0.0), 8)
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------

class _EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._lock = asyncio.Lock()
        self._dropped_total: int = 0
        # Histórico in-memory de los últimos N eventos publicados.
        # Es un deque acotado → descarta automáticamente los más antiguos.
        self._history: collections.deque[dict] = collections.deque(maxlen=_HISTORY_MAXLEN)

    async def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAXSIZE)
        async with self._lock:
            self._subscribers.add(q)
        logger.info("WS subscriber añadido (total=%d)", len(self._subscribers))
        return q

    async def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        async with self._lock:
            self._subscribers.discard(q)
        logger.info("WS subscriber removido (total=%d)", len(self._subscribers))

    def publish(self, event: MatchEvent) -> None:
        """
        Non-blocking. Envía a TODOS los suscriptores activos y guarda en el
        histórico in-memory para consultas async posteriores.
        Si una cola está llena → descarta el mensaje para ese cliente (no bloquea).
        """
        payload = event.to_dict()
        # Heartbeats no entran al histórico (son ruido puro de conexión).
        if payload.get("event_type") != "heartbeat":
            self._history.append(payload)
        if not self._subscribers:
            return
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                self._dropped_total += 1
                if self._dropped_total % 50 == 1:
                    logger.warning(
                        "Event bus: cola llena — mensajes descartados=%d",
                        self._dropped_total,
                    )

    def get_history(self, limit: Optional[int] = None) -> list[dict]:
        """
        Devuelve los últimos eventos publicados, ordenados cronológicamente
        (el más viejo primero). `limit` acota cuántos devolver desde el final.
        """
        if limit is None or limit >= len(self._history):
            return list(self._history)
        if limit <= 0:
            return []
        # deque no soporta slicing: copiamos y tajamos.
        return list(self._history)[-limit:]

    def clear_history(self) -> int:
        n = len(self._history)
        self._history.clear()
        return n

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    @property
    def history_size(self) -> int:
        return len(self._history)


_bus = _EventBus()


def publish_event(event: MatchEvent) -> None:
    """
    Publica un evento en el bus. Safe para llamar desde código async.
    NO bloquea el pipeline de matching.
    """
    try:
        _bus.publish(event)
    except Exception as exc:
        # Nunca dejar que un fallo del bus afecte al pipeline
        logger.debug("publish_event error (ignorado): %s", exc)


@contextlib.asynccontextmanager
async def subscribe() -> AsyncIterator[asyncio.Queue[dict]]:
    """
    Context manager para suscribirse desde un endpoint WebSocket.
    Garantiza limpieza de la cola al desconectarse el cliente.
    """
    q = await _bus.subscribe()
    try:
        yield q
    finally:
        await _bus.unsubscribe(q)


def subscriber_count() -> int:
    return _bus.subscriber_count


def get_history(limit: Optional[int] = None) -> list[dict]:
    """Devuelve los últimos eventos publicados (más antiguos primero)."""
    return _bus.get_history(limit)


def history_size() -> int:
    return _bus.history_size


def clear_history() -> int:
    return _bus.clear_history()
