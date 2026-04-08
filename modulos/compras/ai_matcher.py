"""
Motor de IA para emparejamiento de productos — Compound Entity Matching (ComEM).

ARQUITECTURA v2:
  Pipeline de 5 capas con observabilidad completa:
    Capa 0 → ETIM Taxonomy (clasificación por clase de producto)
    Capa 1 → Unit Normalizer (quantulum3 + pint)
    Capa 2 → Embeddings (Gemini gemini-embedding-001)
    Capa 3 → LLM Chain-of-Thought (Gemini 2.5-flash, 3-step CoT)
    Capa 4 → Jaccard Fallback (sin API key)

MODOS DE OPERACIÓN:
  - Con LLM_API_KEY → Capas 0+1+2+3 (máxima precisión)
  - Sin LLM_API_KEY → Capas 0+1+4 (sin costo)

REFERENCIA:
  - ComEM: Compound Entity Matching framework
  - CoT: Chain-of-Thought prompting (Wei et al., 2022)
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import re
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from core.config import settings
from .models import (
    ProductoProveedor,
    ProductoCanonical,
    ComparacionPrecios,
    AICallLog,
    PromptVersion,
    NombreProveedor,
)
from .unit_normalizer import (
    compare_units,
    normalized_unit_text,
    to_millimeters,
    mm_equivalent,
    MM_EQUIVALENCE_TOLERANCE,
    UnitComparisonResult,
)
from .etim_taxonomy import (
    classify_product,
    are_same_etim_class,
    get_critical_attributes_diff,
    extract_product_attributes,
    ClassificationResult,
)
from .diccionarios import canonicalize, are_synonyms, contains_any_alias
from .event_bus import publish_event, MatchEvent, ProductoRef, Layer, Decision


# ---------------------------------------------------------------------------
# Emisor de eventos para el Centro de Comando (WebSocket)
# ---------------------------------------------------------------------------

def _producto_ref(p: "ProductoProveedor") -> ProductoRef:
    """Convierte un ProductoProveedor a un DTO ligero para el evento."""
    return ProductoRef(
        id=int(getattr(p, "id", 0) or 0),
        sku=str(getattr(p, "sku_proveedor", "") or ""),
        nombre=str(getattr(p, "nombre_raw", "") or "")[:160],
        marca=str(getattr(p, "marca", "") or ""),
        proveedor=str(getattr(p, "proveedor", "") or ""),
    )


def _emit_decision(
    layer: "Layer",
    decision: "Decision",
    producto_a: "ProductoProveedor",
    producto_b: "ProductoProveedor",
    resultado: "MatchResult",
    latencia_parcial_ms: float = 0.0,
    event_type: str = "layer_decision",
) -> None:
    """
    Publica un evento de decisión en el event bus.
    Non-blocking, seguro frente a fallos (try/except interno).
    """
    try:
        publish_event(MatchEvent(
            event_type=event_type,  # type: ignore[arg-type]
            layer=layer,
            decision=decision,
            producto_a=_producto_ref(producto_a),
            producto_b=_producto_ref(producto_b),
            confidence=float(resultado.confidence_score or 0.0),
            similitud_coseno=float(resultado.similitud_coseno or 0.0),
            razon=str(resultado.razon or "")[:240],
            latencia_ms=float(latencia_parcial_ms or resultado.latencia_ms or 0.0),
            tokens=int(resultado.tokens_usados or 0),
            costo_usd=float(resultado.costo_usd or 0.0),
            metodo=str(resultado.metodo or ""),
        ))
    except Exception as exc:
        logger.debug("Evento WS no emitido (no bloqueante): %s", exc)


# ---------------------------------------------------------------------------
# Capa 1.5 — Cruce de Grafos Determinista (con Capa 1.25 integrada)
# ---------------------------------------------------------------------------
# Nodos estrictos (críticos para identidad física del producto).
# Si ambos productos DEFINEN el mismo nodo y sus valores no coinciden
# (tras normalización a mm + sinónimos), NO pueden ser el mismo SKU.
_STRICT_NODES: tuple[str, ...] = (
    "diametro_raw",
    "largo_raw",
    "medida_mm",
    "material",
    "cabeza",
)

# Nodos que representan dimensiones físicas lineales → se normalizan a mm.
_DIMENSION_NODES: frozenset[str] = frozenset({"diametro_raw", "largo_raw", "medida_mm"})

# Nodos que aceptan sinónimos de un diccionario externo.
_SYNONYM_SECTIONS: dict[str, str] = {
    "material": "materiales",
    "cabeza": "cabezas",
}


def _normalize_node_value(key: str, value) -> tuple[str, Optional[float]]:
    """
    Normaliza un valor de nodo a una representación comparable.

    Returns:
        (forma_canonica_str, valor_mm_o_None)
        - valor_mm_o_None es el valor numérico en mm si el nodo es dimensional.
        - forma_canonica_str es el canónico de sinónimos (o el texto limpio).
    """
    if value is None or value == "":
        return "", None

    if key in _DIMENSION_NODES:
        mm = to_millimeters(value)
        if mm is not None:
            return f"{mm:.2f}mm", mm
        # Sin mm parseable: fallback a string limpio
        return str(value).strip().lower(), None

    section = _SYNONYM_SECTIONS.get(key)
    if section:
        canon = canonicalize(section, str(value))
        if canon:
            return canon, None
        return str(value).strip().lower(), None

    # Otros nodos: limpiar texto
    return str(value).strip().lower(), None


def cruzar_grafos_deterministas(
    nombre_a: str, marca_a: str,
    nombre_b: str, marca_b: str,
) -> tuple[bool, str, dict]:
    """
    Capa 1.5 — Cruce determinista de nodos físicos (grafo de atributos).

    Pipeline:
      1. Extrae atributos crudos con classify_product + extract_product_attributes.
      2. Aplica CAPA 1.25: normaliza cada dimensión a milímetros (1/2" ≡ 12.7mm).
      3. Aplica diccionario de sinónimos para material/cabeza (inox ≡ stainless).
      4. Compara nodo por nodo con tolerancia MM_EQUIVALENCE_TOLERANCE para
         dimensiones y equivalencia canónica para categóricos.

    Returns:
        (compatible, razon, debug_info)
    """
    cls_a = classify_product(nombre_a, marca_a)
    cls_b = classify_product(nombre_b, marca_b)

    attrs_a = extract_product_attributes(nombre_a, marca_a,
                                         cls_a.etim_class if cls_a else None)
    attrs_b = extract_product_attributes(nombre_b, marca_b,
                                         cls_b.etim_class if cls_b else None)

    debug = {
        "nodos_a": {k: attrs_a.get(k) for k in _STRICT_NODES if k in attrs_a},
        "nodos_b": {k: attrs_b.get(k) for k in _STRICT_NODES if k in attrs_b},
        "nodos_normalizados": {},
        "conflictos": [],
    }

    for node in _STRICT_NODES:
        if node in attrs_a and node in attrs_b:
            canon_a, mm_a = _normalize_node_value(node, attrs_a[node])
            canon_b, mm_b = _normalize_node_value(node, attrs_b[node])
            debug["nodos_normalizados"][node] = {"a": canon_a, "b": canon_b}

            if mm_a is not None and mm_b is not None:
                # Comparación numérica con tolerancia (Capa 1.25)
                if abs(mm_a - mm_b) > MM_EQUIVALENCE_TOLERANCE:
                    debug["conflictos"].append(
                        f"{node}: {attrs_a[node]!r} ({mm_a:.2f}mm) ≠ "
                        f"{attrs_b[node]!r} ({mm_b:.2f}mm)"
                    )
            elif canon_a and canon_b and canon_a != canon_b:
                debug["conflictos"].append(
                    f"{node}: '{attrs_a[node]}' ≠ '{attrs_b[node]}' "
                    f"(canónico: '{canon_a}' vs '{canon_b}')"
                )

    if debug["conflictos"]:
        return False, "; ".join(debug["conflictos"]), debug

    return True, "nodos compatibles", debug


# ---------------------------------------------------------------------------
# Capa 0.5 — Rechazo estricto por marca
# ---------------------------------------------------------------------------

def verificar_marcas_compatibles(
    marca_a: Optional[str],
    marca_b: Optional[str],
) -> tuple[bool, str]:
    """
    Capa 0.5 — Si ambos productos declaran marca y NO son sinónimos/iguales,
    rechaza el match inmediatamente.

    Política:
      • Si una (o ambas) marcas están vacías → no se puede decidir → pasa.
      • Si las marcas son equivalentes por sinónimos → pasa.
      • Si las marcas difieren → rechazo.

    Returns:
        (compatible, razon)
    """
    ma = (marca_a or "").strip()
    mb = (marca_b or "").strip()

    if not ma or not mb:
        return True, "al menos una marca vacía — no se puede decidir por marca"

    # Canonicalizar vía diccionario de sinónimos
    if are_synonyms("marcas", ma, mb):
        return True, f"marcas equivalentes: '{ma}' ≡ '{mb}'"

    return False, f"marcas distintas: '{ma}' vs '{mb}'"

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuración y umbrales
# ---------------------------------------------------------------------------
UMBRAL_MATCH_DIRECTO: float = 0.92
UMBRAL_RECHAZO_DIRECTO: float = 0.60
UMBRAL_LLM_MATCH: float = 0.75

# TTL del cache de comparaciones en ComparacionPrecios.
# Evita re-llamar al LLM para el mismo par A/B durante 24h.
COMPARACION_CACHE_TTL_HORAS: int = 24
EMBEDDING_MODEL = "gemini-embedding-001"
LLM_MODEL = "gemini-2.5-flash"
LLM_MAX_TOKENS_RESPUESTA = 2048
EMBEDDING_DIM = 3072
PROMPT_VERSION_TAG = "aawr_v1"

# Penalización post-LLM por divergencia de precios.
# Si el ratio entre precios es > este umbral, se asume diferencia de
# formato/empaque y el confidence_score se reduce a la mitad.
PRICE_RATIO_PENALTY_THRESHOLD: float = 3.5

# Costos estimados por token (Gemini pricing — ajustar según plan)
_COST_PER_INPUT_TOKEN = 0.0000001    # $0.10 / 1M tokens
_COST_PER_OUTPUT_TOKEN = 0.0000004   # $0.40 / 1M tokens
_COST_PER_EMBEDDING_TOKEN = 0.00000001  # ~$0.01 / 1M tokens


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    es_mismo_producto: bool
    confidence_score: float
    similitud_coseno: float
    razon: str
    metodo: str
    tokens_usados: int = 0
    latencia_ms: float = 0.0
    costo_usd: float = 0.0
    lineage: dict = field(default_factory=dict)


@dataclass
class EmbeddingResult:
    vector: list[float]
    tokens_input: int
    modelo: str
    latencia_ms: float = 0.0


# ---------------------------------------------------------------------------
# Detector de API key
# ---------------------------------------------------------------------------

def _tiene_api_key_valida() -> bool:
    key = settings.llm_api_key or ""
    return bool(key) and "aqui" not in key.lower() and len(key) > 20


def _get_openai_headers() -> dict[str, str]:
    api_key = settings.llm_api_key
    if not api_key or not _tiene_api_key_valida():
        raise RuntimeError("LLM_API_KEY no configurada.")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Observabilidad — logging de llamadas IA
# ---------------------------------------------------------------------------

def _log_ai_call(
    db: Session,
    call_type: str,
    latencia_ms: float,
    modelo: str = "",
    tokens_input: int = 0,
    tokens_output: int = 0,
    producto_a_id: Optional[int] = None,
    producto_b_id: Optional[int] = None,
    input_preview: str = "",
    resultado_json: str = "",
    exitoso: bool = True,
    error_msg: str = "",
) -> None:
    """Persiste un registro de observabilidad en AICallLog."""
    try:
        costo = (tokens_input * _COST_PER_INPUT_TOKEN +
                 tokens_output * _COST_PER_OUTPUT_TOKEN)
        if call_type == "embedding":
            costo = tokens_input * _COST_PER_EMBEDDING_TOKEN

        db.add(AICallLog(
            call_type=call_type,
            modelo=modelo,
            prompt_version=PROMPT_VERSION_TAG if call_type == "llm" else None,
            producto_a_id=producto_a_id,
            producto_b_id=producto_b_id,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            latencia_ms=round(latencia_ms, 2),
            costo_usd=round(costo, 8),
            input_preview=input_preview[:500] if input_preview else "",
            resultado_json=resultado_json[:2000] if resultado_json else "",
            exitoso=exitoso,
            error_msg=error_msg[:300] if error_msg else "",
        ))
        db.commit()
    except Exception as exc:
        logger.debug("Error logging AI call: %s", exc)


# ---------------------------------------------------------------------------
# Similitud textual (Jaccard — fallback sin API)
# ---------------------------------------------------------------------------

def _normalizar_texto(texto: str) -> str:
    t = texto.lower().strip()
    for a, b in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u"),("ñ","n")]:
        t = t.replace(a, b)
    t = re.sub(r"[^\w\s\d/\"'.-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _bigramas(texto: str) -> set[str]:
    palabras = _normalizar_texto(texto).split()
    if len(palabras) < 2:
        return set(palabras)
    return {f"{palabras[i]} {palabras[i+1]}" for i in range(len(palabras) - 1)} | set(palabras)


def similitud_textual(nombre_a: str, nombre_b: str) -> float:
    set_a = _bigramas(nombre_a)
    set_b = _bigramas(nombre_b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _construir_texto_matching(producto: ProductoProveedor) -> str:
    partes = [
        producto.nombre_raw,
        f"marca {producto.marca}" if producto.marca else "",
        f"unidad {producto.unidad_normalizada or producto.unidad}" if (producto.unidad_normalizada or producto.unidad) else "",
    ]
    return " ".join(p for p in partes if p).strip()


def comparar_textualmente(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
) -> MatchResult:
    t0 = time.perf_counter()
    texto_a = _construir_texto_matching(producto_a)
    texto_b = _construir_texto_matching(producto_b)
    sim = similitud_textual(texto_a, texto_b)
    lat = (time.perf_counter() - t0) * 1000

    if sim >= 0.40:
        return MatchResult(
            es_mismo_producto=True,
            confidence_score=round(min(sim * 0.85, 0.85), 4),
            similitud_coseno=round(sim, 4),
            razon=f"Similitud textual (Jaccard bigramas): {sim:.2%}",
            metodo="texto_jaccard",
            latencia_ms=lat,
        )
    return MatchResult(
        es_mismo_producto=False,
        confidence_score=0.0,
        similitud_coseno=round(sim, 4),
        razon=f"Baja similitud textual: {sim:.2%}",
        metodo="texto_jaccard_rechazo",
        latencia_ms=lat,
    )


# ---------------------------------------------------------------------------
# Embeddings (Gemini)
# ---------------------------------------------------------------------------

def _construir_texto_embedding(producto: ProductoProveedor) -> str:
    unit_text = normalized_unit_text(producto.nombre_raw, producto.unidad or "")
    partes = [
        producto.nombre_raw,
        f"Marca: {producto.marca}" if producto.marca else "",
        f"Unidad de venta: {unit_text}",
        f"Proveedor: {producto.proveedor}",
    ]
    return " | ".join(p for p in partes if p).strip()


async def generar_embedding(texto: str) -> EmbeddingResult:
    if not texto or not texto.strip():
        raise ValueError("No se puede generar embedding de texto vacío")

    t0 = time.perf_counter()
    payload = {
        "model": EMBEDDING_MODEL,
        "input": texto[:8000],
        "encoding_format": "float",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        respuesta = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/openai/v1/embeddings",
            headers=_get_openai_headers(),
            json=payload,
        )

    lat = (time.perf_counter() - t0) * 1000

    if respuesta.status_code != 200:
        raise RuntimeError(f"Error Embeddings [{respuesta.status_code}]: {respuesta.text[:300]}")

    data = respuesta.json()
    tokens = data.get("usage", {}).get("prompt_tokens", 0)

    return EmbeddingResult(
        vector=data["data"][0]["embedding"],
        tokens_input=tokens,
        modelo=EMBEDDING_MODEL,
        latencia_ms=lat,
    )


async def generar_y_guardar_embedding(
    producto: ProductoProveedor,
    db: Session,
) -> list[float]:
    if producto.embedding_json:
        return json.loads(producto.embedding_json)

    # Skip productos sin precio: suelen ser listados "fantasma" (sin stock
    # o con error de scraping). Generar embedding para ellos es desperdicio
    # de cuota LLM y contamina búsquedas.
    _precio = (producto.precio_oferta or producto.precio_clp or 0) or 0
    if _precio <= 0:
        raise ValueError(f"Producto {producto.id} sin precio — embedding omitido")

    texto = _construir_texto_embedding(producto)
    resultado = await generar_embedding(texto)
    producto.embedding_json = json.dumps(resultado.vector)
    db.add(producto)
    db.commit()

    _log_ai_call(
        db, call_type="embedding", latencia_ms=resultado.latencia_ms,
        modelo=EMBEDDING_MODEL, tokens_input=resultado.tokens_input,
        producto_a_id=producto.id, input_preview=texto, exitoso=True,
    )

    return resultado.vector


# ---------------------------------------------------------------------------
# Similitud coseno
# ---------------------------------------------------------------------------

def similitud_coseno(vec_a: list[float], vec_b: list[float]) -> float:
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Dimensiones incompatibles: {len(vec_a)} vs {len(vec_b)}")
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    na = math.sqrt(sum(a * a for a in vec_a))
    nb = math.sqrt(sum(b * b for b in vec_b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def buscar_por_similitud(
    vector_query: list[float],
    candidatos: list[tuple[int, list[float]]],
    top_k: int = 5,
    umbral_minimo: float = UMBRAL_RECHAZO_DIRECTO,
) -> list[tuple[int, float]]:
    scores = [
        (pid, similitud_coseno(vector_query, vec))
        for pid, vec in candidatos
        if similitud_coseno(vector_query, vec) >= umbral_minimo
    ]
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


# ---------------------------------------------------------------------------
# LLM — Chain-of-Thought ComEM (3 pasos)
# ---------------------------------------------------------------------------

PROMPT_SISTEMA_COEM = """
Eres un Principal Entity Resolution Engineer especializado en ferretería y
materiales de construcción chilenos. Aplicas la metodología AAWR
(Attribute-Aware Weighted Reasoning) sobre razonamiento Chain-of-Thought
de 3 pasos.

═══════════════════════════════════════════════════════════════
  METODOLOGÍA AAWR — PESOS DE ATRIBUTOS
═══════════════════════════════════════════════════════════════
Cada atributo del producto tiene un PESO de impacto en la decisión final:

  • Dimensiones numéricas (diámetro, largo, espesor) ............ peso 1.0
  • Unidad de venta (pack, kg, unidad, ciento, saco) ............ peso 1.0
  • Material / acabado (zincado, inox, pavonado, acero) ......... peso 0.8
  • Marca .......................................................... peso 0.7
  • Color, código interno, formato de nombre .................... peso 0.0 (informativo)

El confidence_score se calcula como suma ponderada de coincidencias /
suma de pesos de atributos verificados, normalizado a [0.0, 1.0].

═══════════════════════════════════════════════════════════════
  REGLA DE ORO — DIMENSIONES (INFRANQUEABLE)
═══════════════════════════════════════════════════════════════
Si los VALORES NUMÉRICOS de las medidas difieren entre A y B
(ejemplos: 1/4" vs 3/8", 50mm vs 60mm, 8x1 vs 8x2, M6 vs M8,
3 metros vs 5 metros), el veredicto es **OBLIGATORIAMENTE**:

      es_mismo_producto = false
      confidence_score   = 0.0

…IGNORANDO cualquier otra coincidencia textual, de marca, material o
similitud vectorial. Esta regla no admite excepciones. Una diferencia
de dimensión convierte al producto en una SKU diferente, sin importar
qué tan parecidos sean en el resto.

REGLAS DURAS ADICIONALES (también infranqueables):
  • Pack/Caja/Tira/Plancha/Saco de N unidades ≠ Unidad individual
  • Ciento (100 u) ≠ Millar (1000 u) ≠ Unidad
  • 1 kg ≠ 1 unidad ≠ 1 metro (dimensiones físicas distintas)
  • Zincado ≠ Pavonado ≠ Inoxidable ≠ Galvanizado en caliente
  • Si el ratio de precios es >5x con dimensiones iguales → revisar
    unidad de venta antes de declarar match.

═══════════════════════════════════════════════════════════════
  EJEMPLOS FEW-SHOT
═══════════════════════════════════════════════════════════════

Ejemplo 1 — FALSO POSITIVO POR DIMENSIÓN (regla de oro)
  A: "Tornillo autoperforante cabeza plana 8x1 zincado"
  B: "Tornillo autoperforante cabeza plana 8x2 zincado"
  Análisis: mismo tipo, mismo material (zincado +0.8), misma marca,
            pero las dimensiones difieren (8x1 vs 8x2, peso 1.0).
  Veredicto: { "es_mismo_producto": false, "confidence_score": 0.0,
               "razon": "Regla de oro: dimensión 8x1 ≠ 8x2" }

Ejemplo 2 — MATCH POR SINÓNIMOS
  A: "Perno hexagonal 1/2 x 3 zincado Stanley"
  B: "Perno Hex 1/2x3 Zn Stanley"
  Análisis: mismas dimensiones (1.0 ✓), mismo material zincado/Zn (0.8 ✓),
            misma marca Stanley (0.7 ✓). El "Hex" y "hexagonal" son
            sinónimos del mismo tipo.
  Veredicto: { "es_mismo_producto": true, "confidence_score": 0.96,
               "razon": "Coincidencia total: dim+material+marca; Zn = Zincado" }

Ejemplo 3 — FALSO POSITIVO POR CANTIDAD/EMPAQUE
  A: "Clavo galvanizado 2 pulgadas Pack x100"
  B: "Clavo galvanizado 2 pulgadas (1 unidad)"
  Análisis: mismo tipo, mismas dimensiones, mismo material —
            PERO la unidad de venta difiere (100 u vs 1 u, peso 1.0).
            La diferencia de empaque convierte el SKU en diferente.
  Veredicto: { "es_mismo_producto": false, "confidence_score": 0.0,
               "razon": "Unidad de venta incompatible: pack 100 u vs unidad" }

═══════════════════════════════════════════════════════════════
  PIPELINE DE RAZONAMIENTO (3 PASOS)
═══════════════════════════════════════════════════════════════

PASO 1 — IDENTIFICACIÓN DE TOKENS
  Lista TODOS los tokens significativos de cada producto y márcalos
  como COINCIDENTE (✓) o DISCREPANTE (✗) entre A y B:
    - Tipo de producto base (tornillo, clavo, perno, plancha…)
    - Dimensiones numéricas (diámetro, largo, espesor, calibre)
    - Material / acabado
    - Marca
    - Unidad de venta + cantidad en el envase

PASO 2 — APLICACIÓN AAWR + REGLA DE ORO
  a) Aplica la REGLA DE ORO de dimensiones PRIMERO. Si dispara → corta
     aquí: false / 0.0.
  b) Aplica las reglas duras de unidad de venta. Si disparan → false / 0.0.
  c) Si pasaste (a) y (b), calcula el score AAWR:
     score = Σ (peso_atributo × coincide) / Σ (peso_atributo evaluado)

PASO 3 — VEREDICTO FINAL
  - es_mismo_producto = true SI score >= 0.75 y ningún corte duro disparó.
  - es_mismo_producto = false en cualquier otro caso.
  - confidence_score = score AAWR (después de aplicar la regla de oro).

═══════════════════════════════════════════════════════════════
  FORMATO DE SALIDA — JSON ESTRICTO
═══════════════════════════════════════════════════════════════
Responde ÚNICAMENTE con este JSON, sin texto adicional ni markdown:
{
  "paso_1_tokens": {
    "producto_a": ["token1", "token2", ...],
    "producto_b": ["token1", "token2", ...],
    "coincidentes": ["token1", ...],
    "discrepantes": ["token1: A=valor vs B=valor", ...]
  },
  "paso_2_aawr": {
    "regla_oro_disparo": true | false,
    "regla_oro_razon": "valor_a vs valor_b si disparó, sino vacío",
    "pesos_evaluados": {
      "dimensiones":   {"peso": 1.0, "coincide": true|false, "valor_a": "...", "valor_b": "..."},
      "unidad_venta":  {"peso": 1.0, "coincide": true|false, "valor_a": "...", "valor_b": "..."},
      "material":      {"peso": 0.8, "coincide": true|false, "valor_a": "...", "valor_b": "..."},
      "marca":         {"peso": 0.7, "coincide": true|false, "valor_a": "...", "valor_b": "..."}
    },
    "score_aawr": 0.0
  },
  "paso_3_veredicto": {
    "es_mismo_producto": true | false,
    "confidence_score": 0.0,
    "razon": "Explicación breve basada en AAWR + regla de oro",
    "unidad_a": "unidad de venta detectada",
    "unidad_b": "unidad de venta detectada",
    "unidades_compatibles": true | false
  }
}
""".strip()

# Hash para versionamiento
_PROMPT_HASH = hashlib.sha256(PROMPT_SISTEMA_COEM.encode()).hexdigest()[:16]


async def evaluar_con_llm(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
    query_original: str = "",
    etim_context: str = "",
    unit_context: str = "",
    db: Optional[Session] = None,
) -> dict:
    """Evaluación LLM con Chain-of-Thought de 3 pasos (ComEM framework)."""

    bloque_query = f"\nBÚSQUEDA DEL USUARIO: \"{query_original}\"\n" if query_original else ""

    # Contexto ETIM y unidades pre-calculado
    contexto_extra = ""
    if etim_context:
        contexto_extra += f"\n{etim_context}\n"
    if unit_context:
        contexto_extra += f"\n{unit_context}\n"

    # Detectar ratio de precios
    precio_a = producto_a.precio_oferta or producto_a.precio_clp or 0
    precio_b = producto_b.precio_oferta or producto_b.precio_clp or 0
    alerta_precio = ""
    if precio_a > 0 and precio_b > 0:
        ratio = max(precio_a, precio_b) / min(precio_a, precio_b)
        if ratio > 5:
            alerta_precio = f"\n⚠️ ALERTA PRECIO: Ratio {ratio:.1f}x — verificar unidades de venta.\n"

    contenido: list[dict] = [{
        "type": "text",
        "text": f"""{bloque_query}
PRODUCTO A ({producto_a.proveedor}):
  Nombre:    {producto_a.nombre_raw}
  Marca:     {producto_a.marca or 'No especificada'}
  Precio:    ${producto_a.precio_clp:,.0f} CLP{f' (oferta: ${producto_a.precio_oferta:,.0f})' if producto_a.precio_oferta else ''}
  Unidad:    {producto_a.unidad or 'No especificada'}
  Und.Norm.: {producto_a.unidad_normalizada or 'No parseada'}
  SKU:       {producto_a.sku_proveedor}
  URL:       {producto_a.url_producto or 'N/A'}

PRODUCTO B ({producto_b.proveedor}):
  Nombre:    {producto_b.nombre_raw}
  Marca:     {producto_b.marca or 'No especificada'}
  Precio:    ${producto_b.precio_clp:,.0f} CLP{f' (oferta: ${producto_b.precio_oferta:,.0f})' if producto_b.precio_oferta else ''}
  Unidad:    {producto_b.unidad or 'No especificada'}
  Und.Norm.: {producto_b.unidad_normalizada or 'No parseada'}
  SKU:       {producto_b.sku_proveedor}
  URL:       {producto_b.url_producto or 'N/A'}
{contexto_extra}{alerta_precio}
Ejecuta los 3 pasos del framework ComEM y entrega tu veredicto.
""".strip(),
    }]

    payload = {
        "model": LLM_MODEL,
        "max_tokens": LLM_MAX_TOKENS_RESPUESTA,
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA_COEM},
            {"role": "user", "content": contenido},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    t0 = time.perf_counter()
    _LLM_URL = "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions"
    resp = None
    for _intento in range(3):
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(_LLM_URL, headers=_get_openai_headers(), json=payload)
        if resp.status_code != 429:
            break
        wait = (2 ** _intento) + random.uniform(0, 1)
        logger.warning("Rate limit (429) — reintentando en %.1fs (intento %d/3)...", wait, _intento + 1)
        await asyncio.sleep(wait)

    latencia = (time.perf_counter() - t0) * 1000

    if resp.status_code != 200:
        raise RuntimeError(f"Error LLM [{resp.status_code}]: {resp.text[:300]}")

    data = resp.json()
    usage = data.get("usage", {})
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)
    tokens_total = usage.get("total_tokens", 0)
    contenido_llm = data["choices"][0]["message"]["content"]

    resultado = _parsear_respuesta_coem(contenido_llm)
    resultado["tokens_usados"] = tokens_total
    resultado["tokens_input"] = tokens_in
    resultado["tokens_output"] = tokens_out
    resultado["latencia_ms"] = latencia
    resultado["costo_usd"] = (tokens_in * _COST_PER_INPUT_TOKEN +
                               tokens_out * _COST_PER_OUTPUT_TOKEN)

    # Log de observabilidad
    if db:
        _log_ai_call(
            db, call_type="llm", latencia_ms=latencia, modelo=LLM_MODEL,
            tokens_input=tokens_in, tokens_output=tokens_out,
            producto_a_id=producto_a.id, producto_b_id=producto_b.id,
            input_preview=contenido[0]["text"][:500],
            resultado_json=contenido_llm[:2000],
        )

    return resultado


def _parsear_respuesta_coem(contenido: str) -> dict:
    """
    Parsea respuesta JSON del LLM con formato ComEM de 3 pasos.
    Extrae el veredicto del paso_3_veredicto si existe.
    """
    defaults = {
        "es_mismo_producto": False,
        "confidence_score": 0.0,
        "razon": "Respuesta no procesada",
        "diferencias_criticas": [],
    }

    if not contenido or not contenido.strip():
        return defaults

    # Capa 1: parse directo
    try:
        full = json.loads(contenido)
        # Si tiene formato ComEM con paso_3_veredicto
        veredicto = full.get("paso_3_veredicto", {})
        if veredicto:
            result = {
                "es_mismo_producto": bool(veredicto.get("es_mismo_producto", False)),
                "confidence_score": max(0.0, min(1.0, float(veredicto.get("confidence_score", 0.0)))),
                "razon": str(veredicto.get("razon", ""))[:300],
                "unidad_a": veredicto.get("unidad_a", ""),
                "unidad_b": veredicto.get("unidad_b", ""),
                "unidades_compatibles": veredicto.get("unidades_compatibles", True),
            }
            # Extraer info del paso 2 — soportar tanto el esquema legacy
            # (paso_2_influencia) como el nuevo AAWR (paso_2_aawr).
            paso2 = full.get("paso_2_aawr") or full.get("paso_2_influencia") or {}
            result["diferencias_criticas"] = (
                paso2.get("criticos_discrepantes")
                or ([paso2.get("regla_oro_razon")] if paso2.get("regla_oro_disparo") else [])
                or []
            )
            result["regla_oro_disparo"] = bool(paso2.get("regla_oro_disparo", False))
            result["score_aawr"] = float(paso2.get("score_aawr", result["confidence_score"]) or 0.0)

            # Si la regla de oro disparó pero el LLM no normalizó el veredicto,
            # forzamos el corte aquí: la regla de oro es infranqueable.
            if result["regla_oro_disparo"]:
                result["es_mismo_producto"] = False
                result["confidence_score"] = 0.0

            # Guardar pasos completos para lineage
            result["coem_steps"] = {
                "paso_1": full.get("paso_1_tokens", {}),
                "paso_2": paso2,
            }
            return result
        # Fallback: formato plano
        return _sanitizar_resultado_llm(full, defaults)
    except json.JSONDecodeError:
        pass

    # Capa 2: regex
    match = re.search(r"\{[\s\S]*\}", contenido)
    if match:
        try:
            resultado = json.loads(match.group())
            return _sanitizar_resultado_llm(resultado, defaults)
        except json.JSONDecodeError:
            pass

    logger.error("No se pudo parsear respuesta LLM: %r", contenido[:200])
    return defaults


def _sanitizar_resultado_llm(resultado: dict, defaults: dict) -> dict:
    out = dict(defaults)
    out.update(resultado)
    out["es_mismo_producto"] = bool(out.get("es_mismo_producto", False))
    try:
        score = float(out.get("confidence_score", 0.0))
        out["confidence_score"] = max(0.0, min(1.0, score))
    except (TypeError, ValueError):
        out["confidence_score"] = 0.0
    out["razon"] = str(out.get("razon", ""))[:300]
    return out


# ---------------------------------------------------------------------------
# Pipeline principal — ComEM con 5 capas
# ---------------------------------------------------------------------------

async def comparar_productos(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
    db: Session,
    query_original: str = "",
    bypass_cache: bool = False,
) -> MatchResult:
    """
    Pipeline ComEM de 5 capas con observabilidad completa:
      Capa 0: ETIM Taxonomy
      Capa 1: Unit Normalizer (quantulum3 + pint)
      Capa 2: Embeddings (cosine similarity)
      Capa 3: LLM Chain-of-Thought (zona gris)
      Capa 4: Jaccard Fallback

    Args:
        bypass_cache: Si True, ignora el caché de ComparacionPrecios y
            vuelve a correr todas las capas. Útil para diagnóstico desde
            el Centro IA (ver la decisión real capa por capa).
    """
    t_pipeline_start = time.perf_counter()
    lineage: dict = {"prompt_version": PROMPT_VERSION_TAG, "modelo": LLM_MODEL}

    # ══════════════════════════════════════════════════════════════════
    # CACHE: si existe ComparacionPrecios reciente para este par → reusar
    # Evita re-llamar al LLM y re-embeddings para el mismo par durante
    # COMPARACION_CACHE_TTL_HORAS. Ahorra $$$ y latencia.
    # Si bypass_cache=True, se saltea esta sección completa y el par
    # vuelve a recorrer TODAS las capas del pipeline.
    # ══════════════════════════════════════════════════════════════════
    try:
        if bypass_cache:
            logger.debug(
                "Cache BYPASS forzado para par (%s vs %s)",
                producto_a.sku_proveedor, producto_b.sku_proveedor,
            )
            _cache_hit = None
        else:
            from datetime import datetime, timedelta
            _cache_limite = datetime.utcnow() - timedelta(hours=COMPARACION_CACHE_TTL_HORAS)
            _cache_hit = (
                db.query(ComparacionPrecios)
                .filter(
                    ComparacionPrecios.producto_a_id == producto_a.id,
                    ComparacionPrecios.producto_b_id == producto_b.id,
                    ComparacionPrecios.calculado_at >= _cache_limite,
                )
                .first()
            )
        if _cache_hit is not None:
            try:
                razon_obj = json.loads(_cache_hit.razon_ia or "{}")
            except Exception:
                razon_obj = {}
            try:
                cached_lineage = json.loads(_cache_hit.lineage_json or "{}")
            except Exception:
                cached_lineage = {}
            cached_lineage["cache_hit"] = True
            logger.info(
                "Cache HIT comparacion (%s vs %s), edad=%s",
                producto_a.sku_proveedor,
                producto_b.sku_proveedor,
                (datetime.utcnow() - _cache_hit.calculado_at),
            )
            cached_result = MatchResult(
                es_mismo_producto=(_cache_hit.confidence_score or 0.0) >= UMBRAL_LLM_MATCH,
                confidence_score=float(_cache_hit.confidence_score or 0.0),
                similitud_coseno=float(cached_lineage.get("embedding", {}).get("similitud_coseno") or 0.0),
                razon=razon_obj.get("razon", "cache"),
                metodo=f"cache:{razon_obj.get('metodo', 'desconocido')}",
                tokens_usados=0,
                latencia_ms=(time.perf_counter() - t_pipeline_start) * 1000,
                costo_usd=0.0,
                lineage=cached_lineage,
            )
            _emit_decision(
                "cache", "cache_hit", producto_a, producto_b, cached_result,
                latencia_parcial_ms=cached_result.latencia_ms,
                event_type="pipeline_end",
            )
            return cached_result
    except Exception as _cache_exc:
        logger.debug("Cache lookup falló (no bloqueante): %s", _cache_exc)

    # ══════════════════════════════════════════════════════════════════
    # PRE-CAPA: Rechazo DURO por ratio de precios extremo (> 6x)
    # Indica casi con certeza unidades de venta incompatibles
    # (ej: 1 unidad vs ciento, kg vs unidad). El umbral suave de 3.5x
    # se aplica como PENALIZACIÓN post-LLM más abajo.
    # ══════════════════════════════════════════════════════════════════
    _precio_a = producto_a.precio_oferta or producto_a.precio_clp or 0
    _precio_b = producto_b.precio_oferta or producto_b.precio_clp or 0
    _ratio_precios: Optional[float] = None
    if _precio_a > 0 and _precio_b > 0:
        _ratio_precios = max(_precio_a, _precio_b) / min(_precio_a, _precio_b)
        lineage["price_ratio"] = round(_ratio_precios, 2)
        if _ratio_precios > 6.0:
            _razon_ratio = (
                f"Ratio de precios {_ratio_precios:.1f}x (>6x) — "
                f"unidades de venta incompatibles, rechazo duro"
            )
            logger.info("Ratio rechazo duro (%s vs %s): %s",
                        producto_a.sku_proveedor, producto_b.sku_proveedor, _razon_ratio)
            resultado = MatchResult(
                es_mismo_producto=False, confidence_score=0.0, similitud_coseno=0.0,
                razon=_razon_ratio, metodo="ratio_precio_rechazo",
                latencia_ms=(time.perf_counter() - t_pipeline_start) * 1000, lineage=lineage,
            )
            _guardar_comparacion(producto_a, producto_b, resultado, db)
            _emit_decision("pre_ratio", "reject", producto_a, producto_b, resultado,
                           latencia_parcial_ms=resultado.latencia_ms)
            return resultado

    # ══════════════════════════════════════════════════════════════════
    # CAPA 0: ETIM TAXONOMY — Rechazo rápido por clase de producto
    # ══════════════════════════════════════════════════════════════════
    t0 = time.perf_counter()
    same_class, etim_reason = are_same_etim_class(producto_a.nombre_raw, producto_b.nombre_raw)
    etim_lat = (time.perf_counter() - t0) * 1000
    lineage["etim"] = {"same_class": same_class, "razon": etim_reason, "latencia_ms": round(etim_lat, 2)}

    if not same_class:
        logger.info("ETIM rechazo (%s vs %s): %s", producto_a.sku_proveedor, producto_b.sku_proveedor, etim_reason)
        resultado = MatchResult(
            es_mismo_producto=False, confidence_score=0.0, similitud_coseno=0.0,
            razon=f"Taxonomía ETIM: {etim_reason}", metodo="etim_rechazo",
            latencia_ms=etim_lat, lineage=lineage,
        )
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        _log_ai_call(db, "etim_classify", etim_lat, producto_a_id=producto_a.id,
                     producto_b_id=producto_b.id, resultado_json=etim_reason)
        _emit_decision("capa_0_etim", "reject", producto_a, producto_b, resultado,
                       latencia_parcial_ms=etim_lat)
        return resultado

    # ══════════════════════════════════════════════════════════════════
    # CAPA 0.5: RECHAZO ESTRICTO POR MARCA
    # Si ambos productos declaran marca y NO son sinónimos (según el
    # diccionario externo), rechazamos inmediatamente. Evita falsos
    # positivos cuando el texto es muy parecido pero el fabricante difiere
    # (ej. Stanley vs Bosch).
    # ══════════════════════════════════════════════════════════════════
    t0 = time.perf_counter()
    marca_ok, marca_reason = verificar_marcas_compatibles(
        producto_a.marca, producto_b.marca,
    )
    marca_lat = (time.perf_counter() - t0) * 1000
    lineage["marca_check"] = {
        "compatible": marca_ok,
        "razon": marca_reason,
        "marca_a": producto_a.marca or "",
        "marca_b": producto_b.marca or "",
        "latencia_ms": round(marca_lat, 2),
    }

    if not marca_ok:
        logger.info(
            "Capa 0.5 rechazo por marca (%s vs %s): %s",
            producto_a.sku_proveedor, producto_b.sku_proveedor, marca_reason,
        )
        resultado = MatchResult(
            es_mismo_producto=False,
            confidence_score=0.0,
            similitud_coseno=0.0,
            razon=f"Marcas incompatibles: {marca_reason}",
            metodo="marca_rechazo",
            latencia_ms=etim_lat + marca_lat,
            lineage=lineage,
        )
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        _log_ai_call(
            db, "marca_check", marca_lat,
            producto_a_id=producto_a.id, producto_b_id=producto_b.id,
            resultado_json=marca_reason,
        )
        _emit_decision("capa_0_5_marca", "reject", producto_a, producto_b, resultado,
                       latencia_parcial_ms=marca_lat)
        return resultado

    # Extraer diferencias de atributos ETIM para contexto LLM
    etim_diffs = get_critical_attributes_diff(
        producto_a.nombre_raw, producto_a.marca or "",
        producto_b.nombre_raw, producto_b.marca or "",
    )
    etim_context = ""
    if etim_diffs:
        etim_context = f"DIFERENCIAS TÉCNICAS DETECTADAS: {', '.join(etim_diffs)}"

    # ══════════════════════════════════════════════════════════════════
    # CAPA 1: UNIT NORMALIZER — quantulum3 + pint
    # ══════════════════════════════════════════════════════════════════
    t0 = time.perf_counter()
    unit_result: UnitComparisonResult = compare_units(
        producto_a.nombre_raw, producto_a.unidad or "",
        producto_b.nombre_raw, producto_b.unidad or "",
        precio_a=producto_a.precio_oferta or producto_a.precio_clp or 0,
        precio_b=producto_b.precio_oferta or producto_b.precio_clp or 0,
    )
    unit_lat = (time.perf_counter() - t0) * 1000
    lineage["unit_check"] = {
        "compatible": unit_result.compatible,
        "razon": unit_result.razon,
        "qty_a": unit_result.qty_a.surface_form if unit_result.qty_a else None,
        "qty_b": unit_result.qty_b.surface_form if unit_result.qty_b else None,
        "ratio": unit_result.ratio,
        "latencia_ms": round(unit_lat, 2),
    }

    if not unit_result.compatible:
        logger.info("Unit rechazo (%s vs %s): %s", producto_a.sku_proveedor, producto_b.sku_proveedor, unit_result.razon)
        resultado = MatchResult(
            es_mismo_producto=False, confidence_score=0.0, similitud_coseno=0.0,
            razon=f"Unidades incompatibles: {unit_result.razon}", metodo="unidad_rechazo",
            latencia_ms=etim_lat + unit_lat, lineage=lineage,
        )
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        _log_ai_call(db, "unit_parse", unit_lat, producto_a_id=producto_a.id,
                     producto_b_id=producto_b.id, resultado_json=unit_result.razon)
        _emit_decision("capa_1_unit", "reject", producto_a, producto_b, resultado,
                       latencia_parcial_ms=unit_lat)
        return resultado

    unit_context = f"ANÁLISIS DE UNIDADES: {unit_result.razon}"

    # ══════════════════════════════════════════════════════════════════
    # CAPA 1.5: CRUCE DE GRAFOS DETERMINISTA
    # Extrae nodos físicos (diametro_raw, largo_raw, medida_mm, material,
    # cabeza) con classify_product + extract_product_attributes. Si ambos
    # productos definen el mismo nodo con valores divergentes → rechazo
    # inmediato con confidence=0.0 (imposible que sean el mismo SKU).
    # ══════════════════════════════════════════════════════════════════
    t0 = time.perf_counter()
    graph_ok, graph_reason, graph_debug = cruzar_grafos_deterministas(
        producto_a.nombre_raw, producto_a.marca or "",
        producto_b.nombre_raw, producto_b.marca or "",
    )
    graph_lat = (time.perf_counter() - t0) * 1000
    lineage["graph_cross"] = {
        "compatible": graph_ok,
        "razon": graph_reason,
        "nodos_a": graph_debug.get("nodos_a", {}),
        "nodos_b": graph_debug.get("nodos_b", {}),
        "conflictos": graph_debug.get("conflictos", []),
        "latencia_ms": round(graph_lat, 2),
    }

    if not graph_ok:
        logger.info(
            "Capa 1.5 rechazo determinista (%s vs %s): %s",
            producto_a.sku_proveedor, producto_b.sku_proveedor, graph_reason,
        )
        resultado = MatchResult(
            es_mismo_producto=False,
            confidence_score=0.0,
            similitud_coseno=0.0,
            razon=f"Nodos físicos incompatibles: {graph_reason}",
            metodo="graph_cross_rechazo",
            latencia_ms=etim_lat + unit_lat + graph_lat,
            lineage=lineage,
        )
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        _log_ai_call(
            db, "graph_cross", graph_lat,
            producto_a_id=producto_a.id, producto_b_id=producto_b.id,
            resultado_json=json.dumps(graph_debug, ensure_ascii=False),
        )
        _emit_decision("capa_1_5_graph", "reject", producto_a, producto_b, resultado,
                       latencia_parcial_ms=graph_lat)
        return resultado

    # ══════════════════════════════════════════════════════════════════
    # MODO SIN API KEY → Capa 4 (Jaccard Fallback)
    # ══════════════════════════════════════════════════════════════════
    if not _tiene_api_key_valida():
        resultado = comparar_textualmente(producto_a, producto_b)
        resultado.lineage = lineage
        resultado.latencia_ms += etim_lat + unit_lat
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        _emit_decision(
            "capa_4_jaccard",
            "match" if resultado.es_mismo_producto else "reject",
            producto_a, producto_b, resultado,
            latencia_parcial_ms=resultado.latencia_ms,
            event_type="pipeline_end",
        )
        return resultado

    # ══════════════════════════════════════════════════════════════════
    # CAPA 2: EMBEDDINGS — similitud coseno
    # ══════════════════════════════════════════════════════════════════
    t0 = time.perf_counter()
    try:
        vec_a = await generar_y_guardar_embedding(producto_a, db)
        vec_b = await generar_y_guardar_embedding(producto_b, db)
    except Exception as exc:
        logger.warning("Embeddings fallaron, fallback textual: %s", exc)
        resultado = comparar_textualmente(producto_a, producto_b)
        resultado.lineage = lineage
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        _emit_decision(
            "capa_4_jaccard",
            "match" if resultado.es_mismo_producto else "reject",
            producto_a, producto_b, resultado,
            latencia_parcial_ms=resultado.latencia_ms,
            event_type="pipeline_end",
        )
        return resultado

    sim = similitud_coseno(vec_a, vec_b)
    emb_lat = (time.perf_counter() - t0) * 1000
    lineage["embedding"] = {"similitud_coseno": round(sim, 4), "latencia_ms": round(emb_lat, 2)}

    if sim >= UMBRAL_MATCH_DIRECTO:
        total_lat = etim_lat + unit_lat + emb_lat
        resultado = MatchResult(
            es_mismo_producto=True, confidence_score=round(sim, 4),
            similitud_coseno=round(sim, 4),
            razon=f"Alta similitud vectorial ({sim:.2%})", metodo="vectorial",
            latencia_ms=total_lat, lineage=lineage,
        )
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        _emit_decision("capa_2_embedding", "match", producto_a, producto_b, resultado,
                       latencia_parcial_ms=emb_lat, event_type="pipeline_end")
        return resultado

    if sim < UMBRAL_RECHAZO_DIRECTO:
        total_lat = etim_lat + unit_lat + emb_lat
        resultado = MatchResult(
            es_mismo_producto=False, confidence_score=0.0,
            similitud_coseno=round(sim, 4),
            razon=f"Baja similitud vectorial ({sim:.2%})", metodo="rechazo_directo",
            latencia_ms=total_lat, lineage=lineage,
        )
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        _emit_decision("capa_2_embedding", "reject", producto_a, producto_b, resultado,
                       latencia_parcial_ms=emb_lat, event_type="pipeline_end")
        return resultado

    # ══════════════════════════════════════════════════════════════════
    # CAPA 3: LLM Chain-of-Thought (zona gris 0.60 - 0.92)
    # ══════════════════════════════════════════════════════════════════
    logger.info("Zona gris (sim=%.4f) → LLM CoT para (%s vs %s)",
                sim, producto_a.sku_proveedor, producto_b.sku_proveedor)
    try:
        llm_r = await evaluar_con_llm(
            producto_a, producto_b,
            query_original=query_original,
            etim_context=etim_context,
            unit_context=unit_context,
            db=db,
        )
        confidence = float(llm_r.get("confidence_score", 0.0))
        es_match = llm_r.get("es_mismo_producto", False) and confidence >= UMBRAL_LLM_MATCH

        llm_lat = llm_r.get("latencia_ms", 0)
        total_lat = etim_lat + unit_lat + emb_lat + llm_lat
        total_cost = llm_r.get("costo_usd", 0)

        lineage["llm"] = {
            "confidence": confidence,
            "es_match": es_match,
            "metodo": "coem_cot_3step",
            "tokens": llm_r.get("tokens_usados", 0),
            "latencia_ms": round(llm_lat, 2),
            "costo_usd": round(total_cost, 8),
            "coem_steps": llm_r.get("coem_steps", {}),
        }

        resultado = MatchResult(
            es_mismo_producto=es_match,
            confidence_score=round(confidence, 4),
            similitud_coseno=round(sim, 4),
            razon=llm_r.get("razon", ""),
            metodo="llm_coem",
            tokens_usados=llm_r.get("tokens_usados", 0),
            latencia_ms=total_lat,
            costo_usd=total_cost,
            lineage=lineage,
        )
    except Exception as exc:
        logger.error("LLM falló en zona gris: %s — fallback textual", exc)
        resultado = comparar_textualmente(producto_a, producto_b)
        resultado.similitud_coseno = round(sim, 4)
        resultado.metodo = "vectorial_fallback_textual"
        resultado.lineage = lineage

    # ══════════════════════════════════════════════════════════════════
    # POST-PIPELINE: penalización suave AAWR por ratio de precios alto
    # Si el ratio de precios > PRICE_RATIO_PENALTY_THRESHOLD (3.5x) y
    # el LLM aún declaró match, reducimos confidence_score a la mitad y
    # añadimos una nota. Por encima del umbral de match (0.75) seguimos
    # devolviendo es_mismo_producto=true, pero la confianza queda
    # marcada como dudosa por probable diferencia de formato/empaque.
    # ══════════════════════════════════════════════════════════════════
    if _ratio_precios is not None and _ratio_precios > PRICE_RATIO_PENALTY_THRESHOLD:
        original_score = resultado.confidence_score
        penalizado = round(original_score * 0.5, 4)
        nota = (
            f" | ⚠ Penalización AAWR price_ratio={_ratio_precios:.1f}x>"
            f"{PRICE_RATIO_PENALTY_THRESHOLD}x: probable diferencia de "
            f"formato/empaque (confidence {original_score:.2f}→{penalizado:.2f})"
        )
        resultado.confidence_score = penalizado
        resultado.razon = (resultado.razon or "") + nota
        resultado.es_mismo_producto = penalizado >= UMBRAL_LLM_MATCH
        lineage["aawr_price_penalty"] = {
            "ratio": round(_ratio_precios, 2),
            "threshold": PRICE_RATIO_PENALTY_THRESHOLD,
            "score_original": original_score,
            "score_penalizado": penalizado,
        }
        resultado.lineage = lineage
        logger.info(
            "AAWR price penalty (%s vs %s): ratio=%.1fx score %.2f→%.2f",
            producto_a.sku_proveedor, producto_b.sku_proveedor,
            _ratio_precios, original_score, penalizado,
        )

    _guardar_comparacion(producto_a, producto_b, resultado, db)
    _emit_decision(
        "capa_3_llm",
        "match" if resultado.es_mismo_producto else "reject",
        producto_a, producto_b, resultado,
        latencia_parcial_ms=resultado.latencia_ms,
        event_type="pipeline_end",
    )
    return resultado


# ---------------------------------------------------------------------------
# Global Consistency — Select Strategy (para N candidatos)
# ---------------------------------------------------------------------------

async def seleccionar_mejor_par(
    candidatos_a: list[ProductoProveedor],
    candidatos_b: list[ProductoProveedor],
    query: str,
    db: Session,
    top_k: int = 3,
) -> tuple[Optional[ProductoProveedor], Optional[ProductoProveedor], Optional[MatchResult]]:
    """
    Estrategia Select de ComEM: en lugar de comparar solo el top-1 de cada proveedor,
    evalúa una matriz de top_k × top_k candidatos y selecciona el mejor par global.

    Esto evita inconsistencias donde el top-1 por Jaccard no es el mejor match real.
    """
    if not candidatos_a or not candidatos_b:
        return None, None, None

    # Pre-filtrar por relevancia al query
    def _relevancia(p: ProductoProveedor) -> float:
        return similitud_textual(query, p.nombre_raw)

    top_a = sorted(candidatos_a, key=_relevancia, reverse=True)[:top_k]
    top_b = sorted(candidatos_b, key=_relevancia, reverse=True)[:top_k]

    # Evaluar todos los pares (máx top_k² = 9 comparaciones)
    mejor_par: tuple = (None, None, None)
    mejor_score: float = -1

    for a in top_a:
        for b in top_b:
            try:
                result = await comparar_productos(a, b, db, query_original=query)
                if result.es_mismo_producto and result.confidence_score > mejor_score:
                    mejor_score = result.confidence_score
                    mejor_par = (a, b, result)
            except Exception as exc:
                logger.warning("Error comparando par (%s, %s): %s", a.sku_proveedor, b.sku_proveedor, exc)

    # Si no hubo match, retornar el par con mayor similitud para al menos mostrar algo
    if mejor_par[2] is None and top_a and top_b:
        return top_a[0], top_b[0], None

    return mejor_par


# ---------------------------------------------------------------------------
# Persistencia de comparación (con lineage)
# ---------------------------------------------------------------------------

def _guardar_comparacion(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
    resultado: MatchResult,
    db: Session,
) -> None:
    precio_min, proveedor_min = _calcular_minimo(producto_a, producto_b)

    diff_pct = None
    if producto_a.precio_clp and producto_b.precio_clp and producto_b.precio_clp > 0:
        diff_pct = abs(producto_a.precio_clp - producto_b.precio_clp) / producto_b.precio_clp * 100

    razon_json = json.dumps({
        "razon": resultado.razon,
        "metodo": resultado.metodo,
    }, ensure_ascii=False)

    lineage_str = json.dumps(resultado.lineage, ensure_ascii=False, default=str) if resultado.lineage else None

    existente = db.query(ComparacionPrecios).filter_by(
        producto_a_id=producto_a.id,
        producto_b_id=producto_b.id,
    ).first()

    if existente:
        existente.confidence_score = resultado.confidence_score
        existente.razon_ia = razon_json
        existente.precio_diff_pct = diff_pct
        existente.precio_minimo = precio_min
        existente.proveedor_minimo = proveedor_min
        existente.prompt_version = PROMPT_VERSION_TAG
        existente.modelo_usado = LLM_MODEL
        existente.latencia_total_ms = resultado.latencia_ms
        existente.tokens_totales = resultado.tokens_usados
        existente.costo_usd = resultado.costo_usd
        existente.lineage_json = lineage_str
    else:
        db.add(ComparacionPrecios(
            canonical_id=producto_a.canonical_id or producto_b.canonical_id,
            proveedor_a=producto_a.proveedor,
            proveedor_b=producto_b.proveedor,
            producto_a_id=producto_a.id,
            producto_b_id=producto_b.id,
            confidence_score=resultado.confidence_score,
            razon_ia=razon_json,
            precio_diff_pct=diff_pct,
            precio_minimo=precio_min,
            proveedor_minimo=proveedor_min,
            prompt_version=PROMPT_VERSION_TAG,
            modelo_usado=LLM_MODEL,
            latencia_total_ms=resultado.latencia_ms,
            tokens_totales=resultado.tokens_usados,
            costo_usd=resultado.costo_usd,
            lineage_json=lineage_str,
        ))
    db.commit()


def _calcular_minimo(
    a: ProductoProveedor, b: ProductoProveedor,
) -> tuple[Optional[float], Optional[NombreProveedor]]:
    pa = a.precio_oferta or a.precio_clp
    pb = b.precio_oferta or b.precio_clp
    if pa is None and pb is None:
        return None, None
    if pa is None:
        return pb, b.proveedor
    if pb is None:
        return pa, a.proveedor
    return (pa, a.proveedor) if pa <= pb else (pb, b.proveedor)


# ---------------------------------------------------------------------------
# Canonical — crear / buscar
# ---------------------------------------------------------------------------

async def obtener_o_crear_canonical(
    nombre_query: str,
    productos_encontrados: list[ProductoProveedor],
    db: Session,
) -> ProductoCanonical:
    nombre_normalizado = nombre_query.strip().lower()

    if not _tiene_api_key_valida():
        canonicals = db.query(ProductoCanonical).all()
        for c in canonicals:
            sim = similitud_textual(nombre_normalizado, c.nombre_normalizado)
            if sim >= 0.75:
                _asociar_productos_a_canonical(productos_encontrados, c, db)
                return c

        canonical = ProductoCanonical(nombre_normalizado=nombre_normalizado[:300])
        db.add(canonical)
        db.flush()
        _asociar_productos_a_canonical(productos_encontrados, canonical, db)
        db.commit()
        return canonical

    vec_query = None
    try:
        emb = await generar_embedding(nombre_normalizado)
        vec_query = emb.vector
    except Exception as exc:
        logger.error("No se pudo generar embedding del query: %s", exc)

    if vec_query:
        canonicals = db.query(ProductoCanonical).filter(
            ProductoCanonical.embedding_json.isnot(None)
        ).all()
        candidatos = [(c.id, json.loads(c.embedding_json)) for c in canonicals]
        if candidatos:
            similares = buscar_por_similitud(vec_query, candidatos, top_k=1, umbral_minimo=0.88)
            if similares:
                cid, score = similares[0]
                canonical = db.query(ProductoCanonical).get(cid)
                _asociar_productos_a_canonical(productos_encontrados, canonical, db)
                return canonical

    canonical = ProductoCanonical(
        nombre_normalizado=nombre_normalizado[:300],
        embedding_json=json.dumps(vec_query) if vec_query else None,
    )
    db.add(canonical)
    db.flush()
    _asociar_productos_a_canonical(productos_encontrados, canonical, db)
    db.commit()
    return canonical


def _asociar_productos_a_canonical(
    productos: list[ProductoProveedor],
    canonical: ProductoCanonical,
    db: Session,
) -> None:
    for p in productos:
        if p.canonical_id is None:
            p.canonical_id = canonical.id
            db.add(p)
