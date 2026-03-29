"""
Motor de IA para emparejamiento de productos entre proveedores.

Responsabilidades:
    1. Generar embeddings de texto con OpenAI (text-embedding-3-small)
    2. Calcular cosine similarity entre vectores
    3. Usar GPT-4o como árbitro multimodal cuando la similitud es ambigua
    4. Crear/actualizar ProductoCanonical en la BD

Costos estimados (OpenAI, mayo 2025):
    - Embedding: $0.00002 / 1K tokens ≈ despreciable
    - GPT-4o input: $0.005 / 1K tokens — usar solo cuando sea necesario

Limitaciones conocidas:
    - Los embeddings capturan semántica, no especificidad técnica.
      "tornillo 1/4" y "tornillo 3/8" pueden tener alta similitud.
      El LLM es el que detecta diferencias de medidas.
    - Sin imagen disponible, el LLM opera solo con texto — bajar el
      umbral de confianza a 0.75 en ese caso.
"""

import json
import logging
import math
from dataclasses import dataclass, field
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
# Umbrales de decisión
# ---------------------------------------------------------------------------

# Por encima de este valor → match sin consultar LLM
UMBRAL_MATCH_DIRECTO: float = 0.92

# Por debajo de este valor → rechazo sin consultar LLM
UMBRAL_RECHAZO_DIRECTO: float = 0.60

# Confianza mínima del LLM para declarar match
UMBRAL_LLM_MATCH: float = 0.75

# Modelo de embedding — text-embedding-3-small: rápido y barato
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM   = 1536

# Modelo LLM para evaluación multimodal
LLM_MODEL = "gpt-4o"

# Máx. tokens en el prompt de sistema (para controlar costos)
LLM_MAX_TOKENS_RESPUESTA = 400


# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------

@dataclass
class MatchResult:
    """Resultado de comparar dos productos."""
    es_mismo_producto: bool
    confidence_score:  float          # 0.0 – 1.0
    similitud_coseno:  float          # Score vectorial puro
    razon:             str            # Justificación del LLM o matemática
    metodo:            str            # "vectorial" | "llm" | "rechazo_directo"
    tokens_usados:     int = 0        # Para monitorear costos


@dataclass
class EmbeddingResult:
    vector:       list[float]
    tokens_input: int
    modelo:       str


# ---------------------------------------------------------------------------
# Cliente HTTP reutilizable (httpx async)
# ---------------------------------------------------------------------------

def _get_openai_headers() -> dict[str, str]:
    """
    Construye headers para OpenAI. La key viene de variables de entorno,
    nunca hardcodeada.
    """
    api_key = settings.llm_api_key
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY no configurada. Agregar al archivo .env: LLM_API_KEY=sk-..."
        )
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }


# ---------------------------------------------------------------------------
# 1. Generación de embeddings
# ---------------------------------------------------------------------------

def _construir_texto_embedding(producto: ProductoProveedor) -> str:
    """
    Construye el texto que se convertirá en embedding.
    Incluir marca y unidad mejora mucho la precisión semántica.

    El orden importa: los LLMs de embedding dan más peso al inicio.
    """
    partes = [
        producto.nombre_raw,
        f"Marca: {producto.marca}" if producto.marca else "",
        f"Unidad: {producto.unidad}" if producto.unidad else "",
        f"Proveedor: {producto.proveedor}",
    ]
    return " | ".join(p for p in partes if p).strip()


async def generar_embedding(texto: str) -> EmbeddingResult:
    """
    Llama a la API de OpenAI para obtener el embedding de un texto.
    Lanza excepción si falla — el caller decide qué hacer.
    """
    if not texto or not texto.strip():
        raise ValueError("No se puede generar embedding de texto vacío")

    payload = {
        "model": EMBEDDING_MODEL,
        "input": texto[:8000],  # Límite del modelo
        "encoding_format": "float",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        respuesta = await client.post(
            "https://api.openai.com/v1/embeddings",
            headers=_get_openai_headers(),
            json=payload,
        )

    if respuesta.status_code != 200:
        raise RuntimeError(
            f"Error de OpenAI Embeddings [{respuesta.status_code}]: {respuesta.text[:300]}"
        )

    data = respuesta.json()
    return EmbeddingResult(
        vector=data["data"][0]["embedding"],
        tokens_input=data["usage"]["prompt_tokens"],
        modelo=EMBEDDING_MODEL,
    )


async def generar_y_guardar_embedding(
    producto: ProductoProveedor,
    db: Session,
) -> list[float]:
    """
    Genera embedding para un producto y lo persiste en la BD (como JSON).
    Si ya tiene embedding, lo devuelve sin llamar a la API.
    """
    if producto.embedding_json:
        return json.loads(producto.embedding_json)

    texto = _construir_texto_embedding(producto)

    try:
        resultado = await generar_embedding(texto)
        producto.embedding_json = json.dumps(resultado.vector)
        db.add(producto)
        db.commit()
        logger.debug(
            "Embedding generado para producto id=%s (%d tokens)",
            producto.id, resultado.tokens_input,
        )
        return resultado.vector

    except Exception as exc:
        logger.error("No se pudo generar embedding para producto id=%s: %s", producto.id, exc)
        raise


# ---------------------------------------------------------------------------
# 2. Similitud coseno
# ---------------------------------------------------------------------------

def similitud_coseno(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Calcula la similitud coseno entre dos vectores.

    Rango: -1.0 (opuestos) a 1.0 (idénticos). Para embeddings de texto
    el rango práctico suele ser 0.0 – 1.0.

    Nota de migración:
        En PostgreSQL + pgvector esto se reemplaza por la consulta:
            SELECT 1 - (embedding <=> $1) AS similitud
            FROM productos_proveedor
            ORDER BY embedding <=> $1
            LIMIT 10;
        Con un índice HNSW es órdenes de magnitud más rápido que este loop.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Dimensiones incompatibles: {len(vec_a)} vs {len(vec_b)}")

    dot_product  = sum(a * b for a, b in zip(vec_a, vec_b))
    norma_a      = math.sqrt(sum(a * a for a in vec_a))
    norma_b      = math.sqrt(sum(b * b for b in vec_b))

    if norma_a == 0.0 or norma_b == 0.0:
        return 0.0

    return dot_product / (norma_a * norma_b)


def buscar_por_similitud(
    vector_query: list[float],
    candidatos: list[tuple[int, list[float]]],  # [(id, vector), ...]
    top_k: int = 5,
    umbral_minimo: float = UMBRAL_RECHAZO_DIRECTO,
) -> list[tuple[int, float]]:
    """
    Busca los `top_k` candidatos más similares al vector de query.
    Implementación Python pura — reemplazar por pgvector en producción.

    Returns:
        Lista de (id_producto, score) ordenada por score desc.
    """
    scores = []
    for producto_id, vector in candidatos:
        score = similitud_coseno(vector_query, vector)
        if score >= umbral_minimo:
            scores.append((producto_id, score))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


# ---------------------------------------------------------------------------
# 3. Evaluación multimodal con LLM
# ---------------------------------------------------------------------------

PROMPT_SISTEMA = """
Eres un experto en materiales de construcción y ferretería chilena.
Tu única tarea es determinar si dos productos de distintas tiendas
son EXACTAMENTE el mismo artículo (equivalentes para compra).

Analiza CON DETALLE:
  - Nombre y descripción
  - Marca y modelo
  - Medidas, dimensiones y unidades (¡MUY IMPORTANTE! Un tornillo 1/4" NO es igual a uno 3/8")
  - Material y acabado
  - Cantidad en el envase o presentación
  - Imágenes si están disponibles

Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional:
{
  "es_mismo_producto": true | false,
  "confidence_score": 0.0 a 1.0,
  "razon": "Explicación breve en español (máx 150 palabras)",
  "diferencias_criticas": ["lista de diferencias que impiden el match, o []"]
}

IMPORTANTE:
  - confidence_score = 1.0 solo si estás 100% seguro
  - Si hay duda sobre medidas o material, bajar confidence_score a máximo 0.7
  - Ser conservador: un falso positivo (decir que son iguales cuando no lo son)
    es más dañino que un falso negativo
""".strip()


async def evaluar_con_llm(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
) -> dict:
    """
    Usa GPT-4o para evaluar si dos productos son equivalentes.
    Incluye imágenes si están disponibles (visión multimodal).

    Returns:
        Dict con es_mismo_producto, confidence_score, razon, diferencias_criticas
    """
    # Construir el contenido del mensaje de usuario
    contenido_usuario: list[dict] = []

    # Texto descriptivo de cada producto
    texto_comparacion = f"""
PRODUCTO A ({producto_a.proveedor}):
  Nombre: {producto_a.nombre_raw}
  Marca: {producto_a.marca or 'No especificada'}
  Precio: ${producto_a.precio_clp:,.0f} CLP
  Unidad: {producto_a.unidad or 'No especificada'}
  SKU: {producto_a.sku_proveedor}

PRODUCTO B ({producto_b.proveedor}):
  Nombre: {producto_b.nombre_raw}
  Marca: {producto_b.marca or 'No especificada'}
  Precio: ${producto_b.precio_clp:,.0f} CLP
  Unidad: {producto_b.unidad or 'No especificada'}
  SKU: {producto_b.sku_proveedor}

¿Son exactamente el mismo producto o equivalentes para reemplazarse entre sí?
""".strip()

    contenido_usuario.append({"type": "text", "text": texto_comparacion})

    # Agregar imágenes si están disponibles (visión multimodal)
    for label, producto in [("Producto A", producto_a), ("Producto B", producto_b)]:
        if producto.imagen_url:
            contenido_usuario.append({
                "type": "text",
                "text": f"Imagen del {label}:",
            })
            contenido_usuario.append({
                "type":      "image_url",
                "image_url": {
                    "url":    producto.imagen_url,
                    "detail": "low",  # "low" = menor costo, suficiente para comparar
                },
            })

    payload = {
        "model":      LLM_MODEL,
        "max_tokens": LLM_MAX_TOKENS_RESPUESTA,
        "messages": [
            {"role": "system",  "content": PROMPT_SISTEMA},
            {"role": "user",    "content": contenido_usuario},
        ],
        "response_format": {"type": "json_object"},  # Forzar JSON válido
        "temperature": 0.1,  # Bajo para respuestas consistentes y deterministas
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        respuesta = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=_get_openai_headers(),
            json=payload,
        )

    if respuesta.status_code != 200:
        raise RuntimeError(
            f"Error de GPT-4o [{respuesta.status_code}]: {respuesta.text[:300]}"
        )

    data          = respuesta.json()
    tokens_usados = data["usage"]["total_tokens"]
    contenido_llm = data["choices"][0]["message"]["content"]

    logger.info(
        "LLM evaluó par (%s, %s) → %d tokens",
        producto_a.sku_proveedor, producto_b.sku_proveedor, tokens_usados,
    )

    try:
        resultado = json.loads(contenido_llm)
        resultado["tokens_usados"] = tokens_usados
        # Validar campos mínimos
        resultado.setdefault("es_mismo_producto", False)
        resultado.setdefault("confidence_score", 0.0)
        resultado.setdefault("razon", "Sin razón proporcionada por el LLM")
        resultado.setdefault("diferencias_criticas", [])
        return resultado

    except json.JSONDecodeError as exc:
        logger.error("LLM devolvió JSON inválido: %s | contenido: %s", exc, contenido_llm[:200])
        return {
            "es_mismo_producto":   False,
            "confidence_score":    0.0,
            "razon":               "Error al parsear respuesta del LLM",
            "diferencias_criticas": ["Respuesta inválida del modelo"],
            "tokens_usados":       tokens_usados,
        }


# ---------------------------------------------------------------------------
# 4. Pipeline completo de matching
# ---------------------------------------------------------------------------

async def comparar_productos(
    producto_a: ProductoProveedor,
    producto_b: ProductoProveedor,
    db: Session,
) -> MatchResult:
    """
    Pipeline completo: embedding → similitud → (opcionalmente) LLM.
    Persiste el resultado en ComparacionPrecios.

    Primero intenta resolver con matemática pura (barato y rápido).
    Solo llama al LLM cuando la zona gris lo requiere.
    """

    # --- Paso 1: Obtener/generar embeddings ---
    try:
        vec_a = await generar_y_guardar_embedding(producto_a, db)
        vec_b = await generar_y_guardar_embedding(producto_b, db)
    except Exception as exc:
        logger.error("No se pudo obtener embeddings para comparación: %s", exc)
        return MatchResult(
            es_mismo_producto=False,
            confidence_score=0.0,
            similitud_coseno=0.0,
            razon=f"Error generando embeddings: {exc}",
            metodo="error",
        )

    # --- Paso 2: Similitud coseno ---
    sim = similitud_coseno(vec_a, vec_b)
    logger.debug(
        "Similitud coseno (%s vs %s) = %.4f",
        producto_a.sku_proveedor, producto_b.sku_proveedor, sim,
    )

    # --- Paso 3: Decisión según umbrales ---

    if sim >= UMBRAL_MATCH_DIRECTO:
        # Match claro — no necesita LLM
        resultado = MatchResult(
            es_mismo_producto=True,
            confidence_score=round(sim, 4),
            similitud_coseno=round(sim, 4),
            razon=f"Alta similitud vectorial ({sim:.2%}) — match automático",
            metodo="vectorial",
        )

    elif sim < UMBRAL_RECHAZO_DIRECTO:
        # Rechazo claro — no necesita LLM
        resultado = MatchResult(
            es_mismo_producto=False,
            confidence_score=0.0,
            similitud_coseno=round(sim, 4),
            razon=f"Baja similitud vectorial ({sim:.2%}) — productos distintos",
            metodo="rechazo_directo",
        )

    else:
        # Zona gris — consultar LLM
        logger.info(
            "Zona gris (sim=%.4f) — consultando LLM para (%s vs %s)",
            sim, producto_a.sku_proveedor, producto_b.sku_proveedor,
        )
        try:
            llm_resultado = await evaluar_con_llm(producto_a, producto_b)
            confidence    = float(llm_resultado.get("confidence_score", 0.0))
            es_match      = (
                llm_resultado.get("es_mismo_producto", False)
                and confidence >= UMBRAL_LLM_MATCH
            )
            resultado = MatchResult(
                es_mismo_producto=es_match,
                confidence_score=round(confidence, 4),
                similitud_coseno=round(sim, 4),
                razon=llm_resultado.get("razon", ""),
                metodo="llm",
                tokens_usados=llm_resultado.get("tokens_usados", 0),
            )

        except Exception as exc:
            logger.error("LLM falló en zona gris: %s — usando solo similitud", exc)
            # Fallback conservador: zona gris sin LLM = no match
            resultado = MatchResult(
                es_mismo_producto=False,
                confidence_score=round(sim * 0.7, 4),  # Penalizar por incertidumbre
                similitud_coseno=round(sim, 4),
                razon=f"LLM no disponible. Similitud vectorial: {sim:.2%}",
                metodo="vectorial_fallback",
            )

    # --- Paso 4: Persistir comparación ---
    _guardar_comparacion(producto_a, producto_b, resultado, db)

    return resultado


def _guardar_comparacion(
    producto_a:  ProductoProveedor,
    producto_b:  ProductoProveedor,
    resultado:   MatchResult,
    db:          Session,
) -> None:
    """
    Persiste el resultado en ComparacionPrecios.
    Si ya existe el par, actualiza en lugar de duplicar.
    """
    precio_min, proveedor_min = _calcular_minimo(producto_a, producto_b)

    existente = db.query(ComparacionPrecios).filter_by(
        producto_a_id=producto_a.id,
        producto_b_id=producto_b.id,
    ).first()

    diff_pct = None
    if producto_a.precio_clp and producto_b.precio_clp and producto_b.precio_clp > 0:
        diff_pct = abs(producto_a.precio_clp - producto_b.precio_clp) / producto_b.precio_clp * 100

    if existente:
        existente.confidence_score = resultado.confidence_score
        existente.razon_ia         = json.dumps({
            "razon":  resultado.razon,
            "metodo": resultado.metodo,
        }, ensure_ascii=False)
        existente.precio_diff_pct  = diff_pct
        existente.precio_minimo    = precio_min
        existente.proveedor_minimo = proveedor_min
    else:
        nueva = ComparacionPrecios(
            canonical_id    =producto_a.canonical_id or producto_b.canonical_id,
            proveedor_a     =producto_a.proveedor,
            proveedor_b     =producto_b.proveedor,
            producto_a_id   =producto_a.id,
            producto_b_id   =producto_b.id,
            confidence_score=resultado.confidence_score,
            razon_ia        =json.dumps({
                "razon":  resultado.razon,
                "metodo": resultado.metodo,
            }, ensure_ascii=False),
            precio_diff_pct =diff_pct,
            precio_minimo   =precio_min,
            proveedor_minimo=proveedor_min,
        )
        db.add(nueva)

    db.commit()


def _calcular_minimo(
    a: ProductoProveedor,
    b: ProductoProveedor,
) -> tuple[Optional[float], Optional[NombreProveedor]]:
    """Devuelve (precio_más_bajo, proveedor_más_barato)."""
    precio_a = a.precio_oferta or a.precio_clp
    precio_b = b.precio_oferta or b.precio_clp

    if precio_a is None and precio_b is None:
        return None, None
    if precio_a is None:
        return precio_b, b.proveedor
    if precio_b is None:
        return precio_a, a.proveedor

    if precio_a <= precio_b:
        return precio_a, a.proveedor
    return precio_b, b.proveedor


# ---------------------------------------------------------------------------
# 5. Crear / buscar ProductoCanonical
# ---------------------------------------------------------------------------

async def obtener_o_crear_canonical(
    nombre_query: str,
    productos_encontrados: list[ProductoProveedor],
    db: Session,
) -> ProductoCanonical:
    """
    Dado un query de búsqueda y los productos encontrados,
    crea o recupera el ProductoCanonical que los agrupa.

    Estrategia:
        1. Generar embedding del query normalizado
        2. Buscar en canonicals existentes por similitud
        3. Si hay match → asociar productos a ese canonical
        4. Si no → crear uno nuevo
    """
    # Normalizar el query como nombre canónico provisional
    nombre_normalizado = nombre_query.strip().lower()

    try:
        embedding_query = await generar_embedding(nombre_normalizado)
        vec_query       = embedding_query.vector
    except Exception as exc:
        logger.error("No se pudo generar embedding del query: %s", exc)
        vec_query = None

    # Buscar canonical existente por similitud si tenemos embedding
    if vec_query:
        canonicals = db.query(ProductoCanonical).filter(
            ProductoCanonical.embedding_json.isnot(None)
        ).all()

        candidatos = [
            (c.id, json.loads(c.embedding_json))
            for c in canonicals
        ]

        if candidatos:
            similares = buscar_por_similitud(
                vec_query,
                candidatos,
                top_k=1,
                umbral_minimo=0.88,  # Umbral alto para canonicals — ser conservador
            )
            if similares:
                canonical_id, score = similares[0]
                canonical = db.query(ProductoCanonical).get(canonical_id)
                logger.info(
                    "Canonical existente reutilizado: id=%d score=%.4f", canonical_id, score
                )
                _asociar_productos_a_canonical(productos_encontrados, canonical, db)
                return canonical

    # Crear nuevo canonical
    canonical = ProductoCanonical(
        nombre_normalizado=nombre_normalizado[:300],
        embedding_json=json.dumps(vec_query) if vec_query else None,
    )
    db.add(canonical)
    db.flush()  # Para obtener el ID antes del commit

    _asociar_productos_a_canonical(productos_encontrados, canonical, db)
    db.commit()

    logger.info("Nuevo ProductoCanonical creado: id=%d nombre='%s'", canonical.id, nombre_normalizado)
    return canonical


def _asociar_productos_a_canonical(
    productos: list[ProductoProveedor],
    canonical: ProductoCanonical,
    db: Session,
) -> None:
    """Asigna el canonical_id a los productos que aún no lo tienen."""
    for p in productos:
        if p.canonical_id is None:
            p.canonical_id = canonical.id
            db.add(p)