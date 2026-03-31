"""
Motor de IA para emparejamiento de productos entre proveedores.

MODOS DE OPERACIÓN:
  - Con LLM_API_KEY válida → embeddings OpenAI + GPT-4o (máxima precisión)
  - Sin LLM_API_KEY        → similitud textual (Jaccard + bigramas) — sin costo

El sistema detecta automáticamente qué modo usar.
"""

from __future__ import annotations

import json
import logging
import math
import re
import asyncio
from dataclasses import dataclass
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from core.config import settings
from .models import (
    ProductoProveedor,
    ProductoCanonical,
    ComparacionPrecios,
    NombreProveedor,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Umbrales
# ---------------------------------------------------------------------------
UMBRAL_MATCH_DIRECTO: float = 0.92
UMBRAL_RECHAZO_DIRECTO: float = 0.60
UMBRAL_LLM_MATCH: float = 0.75
EMBEDDING_MODEL = "gemini-embedding-001"
LLM_MODEL = "gemini-2.5-flash"
# gemini-2.5-flash es un modelo con "thinking" interno.
# Los thinking tokens consumen el presupuesto de max_tokens ANTES del output visible.
# Con 400 tokens el modelo se queda sin espacio para escribir el JSON → respuesta truncada.
# 2048 es suficiente para el JSON de respuesta + overhead de thinking.
LLM_MAX_TOKENS_RESPUESTA = 2048
EMBEDDING_DIM = 3072


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


@dataclass
class EmbeddingResult:
    vector: list[float]
    tokens_input: int
    modelo: str


# ---------------------------------------------------------------------------
# Detector de API key
# ---------------------------------------------------------------------------

def _tiene_api_key_valida() -> bool:
    """Retorna True solo si hay una key que no sea el placeholder del .env."""
    key = settings.llm_api_key or ""
    return bool(key) and "aqui" not in key.lower() and len(key) > 20


def _get_openai_headers() -> dict[str, str]:
    api_key = settings.llm_api_key
    if not api_key or not _tiene_api_key_valida():
        raise RuntimeError(
            "LLM_API_KEY no configurada. Agregar al .env: LLM_API_KEY=sk-..."
        )
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Similitud textual (fallback sin OpenAI)
# ---------------------------------------------------------------------------

def _normalizar_texto(texto: str) -> str:
    """Minúsculas, sin tildes básicas, sin caracteres especiales."""
    t = texto.lower().strip()
    t = t.replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    t = t.replace("ñ","n")
    t = re.sub(r"[^\w\s\d/\"'.-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _bigramas(texto: str) -> set[str]:
    """Genera bigramas de palabras: {'tornillo hexagonal', 'hexagonal 1/4', ...}"""
    palabras = _normalizar_texto(texto).split()
    if len(palabras) < 2:
        return set(palabras)
    return {f"{palabras[i]} {palabras[i+1]}" for i in range(len(palabras) - 1)} | set(palabras)


def similitud_textual(nombre_a: str, nombre_b: str) -> float:
    """
    Similitud Jaccard sobre bigramas de palabras.
    Rango: 0.0 (sin coincidencia) a 1.0 (idénticos).

    Ventajas sobre Levenshtein:
    - Insensible al orden de palabras
    - Funciona bien con nombres de productos que comparten subfrases
    - O(n) en lugar de O(n²)
    """
    set_a = _bigramas(nombre_a)
    set_b = _bigramas(nombre_b)
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    interseccion = set_a & set_b
    union = set_a | set_b
    return len(interseccion) / len(union)


def _construir_texto_matching(producto: ProductoProveedor) -> str:
    """Texto representativo del producto para similitud."""
    partes = [
        producto.nombre_raw,
        f"marca {producto.marca}" if producto.marca else "",
    ]
    return " ".join(p for p in partes if p).strip()


def comparar_textualmente(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
) -> MatchResult:
    """
    Matching sin API: usa similitud Jaccard + bigramas.
    Adecuado para desarrollo y demos sin API key de OpenAI.
    """
    texto_a = _construir_texto_matching(producto_a)
    texto_b = _construir_texto_matching(producto_b)
    sim = similitud_textual(texto_a, texto_b)

    logger.debug(
        "Similitud textual (%s vs %s) = %.4f",
        producto_a.sku_proveedor, producto_b.sku_proveedor, sim,
    )

    if sim >= 0.40:  # Umbral más permisivo que vectorial (bigramas son menos precisos)
        return MatchResult(
            es_mismo_producto=True,
            confidence_score=round(min(sim * 0.85, 0.85), 4),  # Cap en 0.85 (sin LLM)
            similitud_coseno=round(sim, 4),
            razon=f"Similitud textual (Jaccard bigramas): {sim:.2%}",
            metodo="texto_jaccard",
        )
    else:
        return MatchResult(
            es_mismo_producto=False,
            confidence_score=0.0,
            similitud_coseno=round(sim, 4),
            razon=f"Baja similitud textual: {sim:.2%}",
            metodo="texto_jaccard_rechazo",
        )


# ---------------------------------------------------------------------------
# Embeddings (solo si hay API key)
# ---------------------------------------------------------------------------

def _construir_texto_embedding(producto: ProductoProveedor) -> str:
    partes = [
        producto.nombre_raw,
        f"Marca: {producto.marca}" if producto.marca else "",
        f"Unidad: {producto.unidad}" if producto.unidad else "",
        f"Proveedor: {producto.proveedor}",
    ]
    return " | ".join(p for p in partes if p).strip()


async def generar_embedding(texto: str) -> EmbeddingResult:
    if not texto or not texto.strip():
        raise ValueError("No se puede generar embedding de texto vacío")

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

    if respuesta.status_code != 200:
        raise RuntimeError(
            f"Error de Embeddings [{respuesta.status_code}]: {respuesta.text[:300]}"
        )

 # PONER ESTO:
    data = respuesta.json()
    
    # Extraer tokens de forma segura (si no existe 'usage', asume 0)
    tokens = 0
    if "usage" in data and "prompt_tokens" in data["usage"]:
        tokens = data["usage"]["prompt_tokens"]

    return EmbeddingResult(
        vector=data["data"][0]["embedding"],
        tokens_input=tokens,
        modelo=EMBEDDING_MODEL,
    )


async def generar_y_guardar_embedding(
    producto: ProductoProveedor,
    db: Session,
) -> list[float]:
    if producto.embedding_json:
        return json.loads(producto.embedding_json)

    texto = _construir_texto_embedding(producto)
    try:
        resultado = await generar_embedding(texto)
        producto.embedding_json = json.dumps(resultado.vector)
        db.add(producto)
        db.commit()
        logger.debug("Embedding generado para producto id=%s", producto.id)
        return resultado.vector
    except Exception as exc:
        logger.error("No se pudo generar embedding para producto id=%s: %s", producto.id, exc)
        raise


# ---------------------------------------------------------------------------
# Similitud coseno (para vectores de embeddings)
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
# LLM — evaluación multimodal (solo si hay API key)
# ---------------------------------------------------------------------------

PROMPT_SISTEMA = """
Eres un experto en materiales de construcción y ferretería chilena.
Tu única tarea es determinar si dos productos de distintas tiendas
son EXACTAMENTE el mismo artículo (equivalentes para compra).

Analiza CON DETALLE:
  - Nombre y descripción
  - Marca y modelo
  - Medidas, dimensiones y unidades (un tornillo 1/4\" NO es igual a uno 3/8\")
  - Material y acabado
  - Cantidad en el envase

Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional:
{
  "es_mismo_producto": true | false,
  "confidence_score": 0.0 a 1.0,
  "razon": "Explicación breve (máx 100 palabras)",
  "diferencias_criticas": []
}
""".strip()


async def evaluar_con_llm(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
) -> dict:
    contenido: list[dict] = [{
        "type": "text",
        "text": f"""
PRODUCTO A ({producto_a.proveedor}):
  Nombre: {producto_a.nombre_raw}
  Marca:  {producto_a.marca or 'No especificada'}
  Precio: ${producto_a.precio_clp:,.0f} CLP
  SKU:    {producto_a.sku_proveedor}

PRODUCTO B ({producto_b.proveedor}):
  Nombre: {producto_b.nombre_raw}
  Marca:  {producto_b.marca or 'No especificada'}
  Precio: ${producto_b.precio_clp:,.0f} CLP
  SKU:    {producto_b.sku_proveedor}

¿Son exactamente el mismo producto?
""".strip(),
    }]

    # Agregar imágenes si están disponibles
    #for label, prod in [("Producto A", producto_a), ("Producto B", producto_b)]:
     #   if prod.imagen_url:
      #      contenido.append({"type": "text", "text": f"Imagen {label}:"})
       #     contenido.append({
        #        "type": "image_url",
         #       "image_url": {"url": prod.imagen_url, "detail": "low"},
          #  })

    payload = {
        "model": LLM_MODEL,
        "max_tokens": LLM_MAX_TOKENS_RESPUESTA,
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA},
            {"role": "user", "content": contenido},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        # Nota: el parámetro "thinking" NO es compatible con el endpoint
        # OpenAI-compatible de Gemini (/v1beta/openai/v1/...).
        # El truncamiento estaba causado por max_tokens bajo (400), ya corregido arriba.
    }

    # Delay adaptativo: respetar el rate limit de la API (Free Tier: ~15 rpm)
    # En producción con API de pago se puede reducir este valor.
    _LLM_RATE_LIMIT_DELAY = 2.0
    logger.info("Esperando %.1fs para respetar límite de API...", _LLM_RATE_LIMIT_DELAY)
    await asyncio.sleep(_LLM_RATE_LIMIT_DELAY)

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions",
            headers=_get_openai_headers(),
            json=payload,
        )

    if resp.status_code == 429:
        # Rate limit: esperar más y reintentar una vez
        logger.warning("Rate limit de LLM alcanzado (429) — reintentando en 10s...")
        await asyncio.sleep(10)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/openai/v1/chat/completions",
                headers=_get_openai_headers(),
                json=payload,
            )

    if resp.status_code != 200:
        raise RuntimeError(f"Error de LLM [{resp.status_code}]: {resp.text[:300]}")

    data = resp.json()
    tokens = data.get("usage", {}).get("total_tokens", 0)
    contenido_llm = data["choices"][0]["message"]["content"]

    resultado = _parsear_respuesta_llm(contenido_llm)
    resultado["tokens_usados"] = tokens
    return resultado


def _parsear_respuesta_llm(contenido: str) -> dict:
    """
    Parsea la respuesta JSON del LLM con tres capas de fallback:
    1. json.loads directo (caso ideal)
    2. Extracción de JSON con regex si el modelo añadió texto extra
    3. Valores seguros por defecto si todo falla

    Esto evita que una respuesta malformada produzca un crash silencioso
    donde confidence_score queda en 0.0 sin que nadie lo note.
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
        resultado = json.loads(contenido)
        return _sanitizar_resultado_llm(resultado, defaults)
    except json.JSONDecodeError:
        pass

    # Capa 2: extraer el primer objeto JSON del texto (el modelo a veces añade prosa)
    match = re.search(r"\{[^{}]*\}", contenido, re.DOTALL)
    if match:
        try:
            resultado = json.loads(match.group())
            logger.debug("JSON extraído con regex del contenido LLM")
            return _sanitizar_resultado_llm(resultado, defaults)
        except json.JSONDecodeError:
            pass

    logger.error("No se pudo parsear la respuesta del LLM: %r", contenido[:200])
    return defaults


def _sanitizar_resultado_llm(resultado: dict, defaults: dict) -> dict:
    """Garantiza tipos y rangos correctos en la respuesta parseada del LLM."""
    out = dict(defaults)
    out.update(resultado)
    # Forzar tipo bool
    out["es_mismo_producto"] = bool(out.get("es_mismo_producto", False))
    # Clampear confidence_score al rango [0, 1]
    try:
        score = float(out.get("confidence_score", 0.0))
        out["confidence_score"] = max(0.0, min(1.0, score))
    except (TypeError, ValueError):
        out["confidence_score"] = 0.0
    # Garantizar string en razon
    out["razon"] = str(out.get("razon", ""))[:300]
    return out


# ---------------------------------------------------------------------------
# Pipeline principal de matching
# ---------------------------------------------------------------------------

async def comparar_productos(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
    db: Session,
) -> MatchResult:
    """
    Pipeline completo con detección automática de modo:
    - Con API key válida → embeddings + LLM en zona gris
    - Sin API key        → similitud textual Jaccard (instantáneo, sin costo)
    """

    # ── MODO SIN API KEY (fallback textual) ───────────────────────────
    if not _tiene_api_key_valida():
        logger.info(
            "Sin API key válida → usando similitud textual para (%s vs %s)",
            producto_a.sku_proveedor, producto_b.sku_proveedor,
        )
        resultado = comparar_textualmente(producto_a, producto_b)
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        return resultado

    # ── MODO CON API KEY (embeddings + LLM) ───────────────────────────
    try:
        vec_a = await generar_y_guardar_embedding(producto_a, db)
        vec_b = await generar_y_guardar_embedding(producto_b, db)
    except Exception as exc:
        logger.warning("Embeddings fallaron, usando fallback textual: %s", exc)
        resultado = comparar_textualmente(producto_a, producto_b)
        _guardar_comparacion(producto_a, producto_b, resultado, db)
        return resultado

    sim = similitud_coseno(vec_a, vec_b)
    logger.debug(
        "Similitud coseno (%s vs %s) = %.4f",
        producto_a.sku_proveedor, producto_b.sku_proveedor, sim,
    )

    if sim >= UMBRAL_MATCH_DIRECTO:
        resultado = MatchResult(
            es_mismo_producto=True,
            confidence_score=round(sim, 4),
            similitud_coseno=round(sim, 4),
            razon=f"Alta similitud vectorial ({sim:.2%})",
            metodo="vectorial",
        )
    elif sim < UMBRAL_RECHAZO_DIRECTO:
        resultado = MatchResult(
            es_mismo_producto=False,
            confidence_score=0.0,
            similitud_coseno=round(sim, 4),
            razon=f"Baja similitud vectorial ({sim:.2%})",
            metodo="rechazo_directo",
        )
    else:
        logger.info(
            "Zona gris (sim=%.4f) → consultando LLM para (%s vs %s)",
            sim, producto_a.sku_proveedor, producto_b.sku_proveedor,
        )
        try:
            llm_r = await evaluar_con_llm(producto_a, producto_b)
            confidence = float(llm_r.get("confidence_score", 0.0))
            es_match = llm_r.get("es_mismo_producto", False) and confidence >= UMBRAL_LLM_MATCH
            resultado = MatchResult(
                es_mismo_producto=es_match,
                confidence_score=round(confidence, 4),
                similitud_coseno=round(sim, 4),
                razon=llm_r.get("razon", ""),
                metodo="llm",
                tokens_usados=llm_r.get("tokens_usados", 0),
            )
        except Exception as exc:
            logger.error("LLM falló en zona gris: %s — fallback textual", exc)
            resultado = comparar_textualmente(producto_a, producto_b)
            resultado.similitud_coseno = round(sim, 4)
            resultado.metodo = "vectorial_fallback_textual"

    _guardar_comparacion(producto_a, producto_b, resultado, db)
    return resultado


# ---------------------------------------------------------------------------
# Persistencia de comparación
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

    existente = db.query(ComparacionPrecios).filter_by(
        producto_a_id=producto_a.id,
        producto_b_id=producto_b.id,
    ).first()

    razon_json = json.dumps({"razon": resultado.razon, "metodo": resultado.metodo}, ensure_ascii=False)

    if existente:
        existente.confidence_score = resultado.confidence_score
        existente.razon_ia = razon_json
        existente.precio_diff_pct = diff_pct
        existente.precio_minimo = precio_min
        existente.proveedor_minimo = proveedor_min
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
        ))
    db.commit()


def _calcular_minimo(
    a: ProductoProveedor,
    b: ProductoProveedor,
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
    """
    Crea o recupera el ProductoCanonical que agrupa los productos.
    Con API key → usa embeddings para deduplicar canonicals.
    Sin API key → usa similitud textual como fallback.
    """
    nombre_normalizado = nombre_query.strip().lower()

    # ── Sin API key: buscar canonical existente por texto ─────────────
    if not _tiene_api_key_valida():
        canonicals = db.query(ProductoCanonical).all()
        for c in canonicals:
            sim = similitud_textual(nombre_normalizado, c.nombre_normalizado)
            if sim >= 0.75:
                logger.info("Canonical textual reutilizado: id=%d sim=%.4f", c.id, sim)
                _asociar_productos_a_canonical(productos_encontrados, c, db)
                return c

        # Crear nuevo
        canonical = ProductoCanonical(nombre_normalizado=nombre_normalizado[:300])
        db.add(canonical)
        db.flush()
        _asociar_productos_a_canonical(productos_encontrados, canonical, db)
        db.commit()
        logger.info("Nuevo canonical (sin IA): id=%d nombre='%s'", canonical.id, nombre_normalizado)
        return canonical

    # ── Con API key: usar embeddings ──────────────────────────────────
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
                logger.info("Canonical existente reutilizado: id=%d score=%.4f", cid, score)
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
    logger.info("Nuevo canonical: id=%d nombre='%s'", canonical.id, nombre_normalizado)
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