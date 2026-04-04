"""
Catalogo de materiales — construido desde la BD.

El sync scrapea productos, los persiste, crea canonicals con IA,
y genera embeddings. Despues el catalogo se sirve directamente
desde la BD agrupando por canonical (= mismo producto en distintas tiendas).

Flujo:
  1. sync_catalogo() → scrapea queries predefinidos → persiste → crea canonicals
  2. obtener_catalogo() → lee canonicals + variantes de BD → retorna al frontend
  3. buscar_en_catalogo() → filtra productos de BD por texto
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from .models import (
    ProductoProveedor,
    ProductoCanonical,
    NombreProveedor,
    EstadoScraping,
)
from .scraper import ejecutar_busqueda, ResultadoScraper
from .service import persistir_resultados_scraper

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Categorías con color — el frontend las usa para chips y tarjetas
# ---------------------------------------------------------------------------

FAMILIAS_CONFIG = {
    "Tornillos":              {"color": "#6366f1", "icon": "🔩"},
    "Clavos":                 {"color": "#ef4444", "icon": "📌"},
    "Pernos":                 {"color": "#3b82f6", "icon": "⚙️"},
    "Tuercas y Golillas":     {"color": "#f59e0b", "icon": "🔧"},
    "Tirafondos":             {"color": "#8b5cf6", "icon": "🪛"},
    "Placas y Conectores":    {"color": "#10b981", "icon": "🛠️"},
    "Adhesivos y Sellantes":  {"color": "#ec4899", "icon": "🧴"},
}

# ---------------------------------------------------------------------------
# Queries predefinidos para el sync diario — con familia asignada
# ---------------------------------------------------------------------------

QUERIES_SYNC = [
    # Tornillos
    {"query": "Tornillo autoperforante 1 pulgada",       "familia": "Tornillos"},
    {"query": "Tornillo autoperforante 1 1/2 pulgada",   "familia": "Tornillos"},
    {"query": "Tornillo volcanita 6x1",                  "familia": "Tornillos"},
    {"query": "Tornillo volcanita 6x1 5/8",              "familia": "Tornillos"},
    {"query": "Tornillo madera 8x2 pulgadas",            "familia": "Tornillos"},
    {"query": "Tornillo hexagonal 1/4 pulgada",          "familia": "Tornillos"},
    {"query": "Tornillo hexagonal 5/16 pulgada",         "familia": "Tornillos"},
    {"query": "Tornillo hexagonal 3/8 pulgada",          "familia": "Tornillos"},
    # Clavos
    {"query": "Clavo 1 pulgada",                         "familia": "Clavos"},
    {"query": "Clavo 1 1/2 pulgada",                     "familia": "Clavos"},
    {"query": "Clavo 2 pulgadas",                        "familia": "Clavos"},
    {"query": "Clavo 2 1/2 pulgadas",                    "familia": "Clavos"},
    {"query": "Clavo 3 pulgadas",                        "familia": "Clavos"},
    {"query": "Clavo 4 pulgadas",                        "familia": "Clavos"},
    {"query": "Clavo acero 1 pulgada",                   "familia": "Clavos"},
    # Pernos
    {"query": "Perno 1/4 x 1 pulgada",                  "familia": "Pernos"},
    {"query": "Perno 1/4 x 2 pulgadas",                 "familia": "Pernos"},
    {"query": "Perno 5/16 x 2 pulgadas",                "familia": "Pernos"},
    {"query": "Perno 3/8 x 2 pulgadas",                 "familia": "Pernos"},
    {"query": "Perno 3/8 x 3 pulgadas",                 "familia": "Pernos"},
    # Tuercas / Golillas
    {"query": "Tuerca hexagonal 1/4",                    "familia": "Tuercas y Golillas"},
    {"query": "Tuerca hexagonal 3/8",                    "familia": "Tuercas y Golillas"},
    {"query": "Golilla plana 1/4",                       "familia": "Tuercas y Golillas"},
    {"query": "Golilla presion 1/4",                     "familia": "Tuercas y Golillas"},
    # Tirafondos
    {"query": "Tirafondo 1/4 x 2 pulgadas",             "familia": "Tirafondos"},
    {"query": "Tirafondo 1/4 x 3 pulgadas",             "familia": "Tirafondos"},
    {"query": "Tirafondo 3/8 x 3 pulgadas",             "familia": "Tirafondos"},
    # Placas / Conectores
    {"query": "Placa perforada 80x200",                  "familia": "Placas y Conectores"},
    {"query": "Placa perforada 100x300",                 "familia": "Placas y Conectores"},
    {"query": "Escuadra metalica reforzada",             "familia": "Placas y Conectores"},
    {"query": "Conector angular metalico",               "familia": "Placas y Conectores"},
    {"query": "Pie derecho regulable",                   "familia": "Placas y Conectores"},
    # Adhesivos
    {"query": "Silicona transparente",                   "familia": "Adhesivos y Sellantes"},
    {"query": "Silicona estructural",                    "familia": "Adhesivos y Sellantes"},
    {"query": "Adhesivo montaje",                        "familia": "Adhesivos y Sellantes"},
    {"query": "Espuma poliuretano expandido",            "familia": "Adhesivos y Sellantes"},
]


# ---------------------------------------------------------------------------
# Lectura del catalogo desde BD (agrupado por canonical)
# ---------------------------------------------------------------------------

def _inferir_familia(nombre: str) -> str:
    """Infiere la familia de un producto a partir de su nombre."""
    nombre_lower = nombre.lower()
    if any(w in nombre_lower for w in ["tornillo", "autoperforante", "volcanita"]):
        return "Tornillos"
    if any(w in nombre_lower for w in ["clavo"]):
        return "Clavos"
    if any(w in nombre_lower for w in ["perno"]):
        return "Pernos"
    if any(w in nombre_lower for w in ["tuerca", "golilla"]):
        return "Tuercas y Golillas"
    if any(w in nombre_lower for w in ["tirafondo"]):
        return "Tirafondos"
    if any(w in nombre_lower for w in ["placa", "escuadra", "conector", "angular", "pie derecho"]):
        return "Placas y Conectores"
    if any(w in nombre_lower for w in ["silicona", "adhesivo", "sellante", "espuma", "montaje"]):
        return "Adhesivos y Sellantes"
    return "Otros"


def _extraer_tienda(p: Optional[ProductoProveedor]) -> dict:
    """Extrae datos de un producto de proveedor para la respuesta."""
    if not p:
        return {"precio": None, "nombre": None, "imagen": None, "sku": None, "url": None}
    return {
        "precio": p.precio_oferta or p.precio_clp,
        "nombre": p.nombre_raw,
        "imagen": str(p.imagen_url) if p.imagen_url else None,
        "sku": p.sku_proveedor,
        "url": str(p.url_producto) if p.url_producto else None,
    }


def obtener_catalogo(db: Session) -> list[dict]:
    """
    Retorna el catálogo agrupado por FAMILIA para el frontend.

    Formato de salida:
    [
      {
        "familia": "Tornillos",
        "color": "#6366f1",
        "variantes": [
          {
            "query": "tornillo autoperforante 1 pulgada",
            "nombre": "Tornillo autoperforante 1 pulgada",
            "precio_sodimac": 2490, "precio_easy": 2190,
            "imagen_sodimac": "...", "imagen_easy": "...",
            ...
          },
          ...
        ]
      },
      ...
    ]
    """
    # Cargar todos los canonicals con sus variantes
    canonicals = (
        db.query(ProductoCanonical)
        .options(joinedload(ProductoCanonical.variantes))
        .all()
    )

    # Paso 1: construir lista plana de productos canónicos
    productos_planos = []

    for canon in canonicals:
        variantes_activas = [
            v for v in canon.variantes
            if v.disponible and v.estado_scraping == EstadoScraping.EXITO
        ]
        if not variantes_activas:
            continue

        # Más reciente por proveedor
        por_prov: dict[str, ProductoProveedor] = {}
        for v in variantes_activas:
            existente = por_prov.get(v.proveedor)
            if existente is None or (v.scraped_at and (not existente.scraped_at or v.scraped_at > existente.scraped_at)):
                por_prov[v.proveedor] = v

        sodimac = por_prov.get(NombreProveedor.SODIMAC)
        easy = por_prov.get(NombreProveedor.EASY)

        sod = _extraer_tienda(sodimac)
        eas = _extraer_tienda(easy)

        # Determinar mejor precio
        mejor_precio = None
        mejor_tienda = None
        ahorro = None
        if sod["precio"] is not None and eas["precio"] is not None:
            if sod["precio"] <= eas["precio"]:
                mejor_precio, mejor_tienda = sod["precio"], "Sodimac"
            else:
                mejor_precio, mejor_tienda = eas["precio"], "Easy"
            ahorro = abs(sod["precio"] - eas["precio"])
        elif sod["precio"] is not None:
            mejor_precio, mejor_tienda = sod["precio"], "Sodimac"
        elif eas["precio"] is not None:
            mejor_precio, mejor_tienda = eas["precio"], "Easy"

        # Timestamp más reciente
        timestamps = [v.scraped_at for v in variantes_activas if v.scraped_at]
        ultimo = max(timestamps).isoformat() if timestamps else None

        # Familia: usar categoria del canonical, o inferir del nombre
        familia = canon.categoria or _inferir_familia(canon.nombre_normalizado)

        # Actualizar la categoria en BD si estaba vacía
        if not canon.categoria and familia != "Otros":
            canon.categoria = familia
            db.add(canon)

        productos_planos.append({
            "id": canon.id,
            "query": canon.nombre_normalizado,
            "nombre": canon.nombre_normalizado,
            "familia": familia,
            # Sodimac
            "precio_sodimac": sod["precio"],
            "nombre_sodimac": sod["nombre"],
            "imagen_sodimac": sod["imagen"],
            "sku_sodimac": sod["sku"],
            "url_sodimac": sod["url"],
            # Easy
            "precio_easy": eas["precio"],
            "nombre_easy": eas["nombre"],
            "imagen_easy": eas["imagen"],
            "sku_easy": eas["sku"],
            "url_easy": eas["url"],
            # Resumen
            "mejor_precio": mejor_precio,
            "mejor_tienda": mejor_tienda,
            "ahorro": ahorro,
            "scraped_at": ultimo,
            "n_tiendas": sum(1 for x in [sod["precio"], eas["precio"]] if x is not None),
        })

    # Commit categorias actualizadas
    try:
        db.commit()
    except Exception:
        db.rollback()

    # Paso 2: agrupar por familia
    por_familia: dict[str, list[dict]] = {}
    for p in productos_planos:
        por_familia.setdefault(p["familia"], []).append(p)

    # Paso 3: construir respuesta agrupada
    resultado = []
    for familia_nombre, variantes in por_familia.items():
        cfg = FAMILIAS_CONFIG.get(familia_nombre, {"color": "#94a3b8", "icon": "📦"})
        # Ordenar variantes: primero los que tienen ambas tiendas
        variantes.sort(key=lambda x: (-x["n_tiendas"], x["nombre"].lower()))
        resultado.append({
            "familia": familia_nombre,
            "color": cfg["color"],
            "icon": cfg["icon"],
            "variantes": variantes,
        })

    # Ordenar familias: por cantidad de variantes (más primero)
    resultado.sort(key=lambda x: -len(x["variantes"]))

    return resultado


def buscar_en_catalogo(db: Session, texto: str, limite: int = 50) -> list[dict]:
    """
    Busca productos en la BD por texto.
    Retorna en el mismo formato agrupado que obtener_catalogo pero filtrado.
    """
    texto_limpio = texto.strip().lower()
    if not texto_limpio:
        return obtener_catalogo(db)

    catalogo = obtener_catalogo(db)

    # Filtrar variantes dentro de cada familia
    resultado = []
    for familia_grupo in catalogo:
        variantes_filtradas = []
        for v in familia_grupo["variantes"]:
            nombres = " ".join(filter(None, [
                v.get("nombre", ""), v.get("nombre_sodimac", ""), v.get("nombre_easy", ""),
            ])).lower()
            if texto_limpio in nombres:
                variantes_filtradas.append(v)

        if variantes_filtradas:
            resultado.append({
                **familia_grupo,
                "variantes": variantes_filtradas[:limite],
            })

    return resultado


# ---------------------------------------------------------------------------
# Sincronizacion (scraping + AI matching)
# ---------------------------------------------------------------------------

async def sync_catalogo(db: Session, max_resultados: int = 5) -> dict:
    """
    Scrapea todos los queries predefinidos, persiste los productos,
    y ejecuta el pipeline de AI matching (canonical + embeddings).
    """
    from .ai_matcher import obtener_o_crear_canonical, generar_y_guardar_embedding

    inicio = datetime.utcnow()
    proveedores = [NombreProveedor.SODIMAC, NombreProveedor.EASY]

    total_queries = len(QUERIES_SYNC)
    queries_ok = 0
    queries_error = 0
    productos_total = 0
    canonicals_creados = 0

    logger.info("=== SYNC CATALOGO INICIADO: %d queries ===", total_queries)
    print(f"\n{'='*60}")
    print(f"  SYNC CATALOGO - {total_queries} queries")
    print(f"{'='*60}\n")

    for i, query_info in enumerate(QUERIES_SYNC, 1):
        query = query_info["query"]
        familia = query_info["familia"]
        print(f"\n  [{i}/{total_queries}] '{query}' ({familia})")

        try:
            # 1) Scrapear
            resultados: list[ResultadoScraper] = await ejecutar_busqueda(
                query=query,
                proveedores=proveedores,
                max_resultados=max_resultados,
            )

            n_productos = sum(len(r.productos) for r in resultados)
            if n_productos == 0:
                queries_error += 1
                print(f"     SIN RESULTADOS")
                await asyncio.sleep(2)
                continue

            # 2) Persistir en BD
            persistidos = persistir_resultados_scraper(resultados, db)
            productos_total += len(persistidos)
            print(f"     {len(persistidos)} productos guardados")

            # 3) Crear canonical + asociar productos (AI matching)
            try:
                canonical = await obtener_o_crear_canonical(
                    nombre_query=query,
                    productos_encontrados=persistidos,
                    db=db,
                )
                if canonical:
                    canonicals_creados += 1
                    # Asignar categoría/familia al canonical
                    if not canonical.categoria:
                        canonical.categoria = familia
                        db.add(canonical)
                        db.commit()
                    print(f"     Canonical: '{canonical.nombre_normalizado}' (id={canonical.id})")
            except Exception as exc:
                logger.warning("Error en canonical para '%s': %s", query, exc)
                print(f"     Canonical ERROR: {exc}")

            # 4) Generar embeddings (best effort)
            for p in persistidos[:3]:  # Solo los 3 mejores por query
                try:
                    await generar_y_guardar_embedding(p, db)
                except Exception:
                    pass

            queries_ok += 1

        except Exception as exc:
            queries_error += 1
            logger.error("Error scrapeando '%s': %s", query, exc)
            print(f"     ERROR: {exc}")

        # Pausa entre queries
        await asyncio.sleep(2)

    duracion = (datetime.utcnow() - inicio).total_seconds()

    resumen = {
        "status": "completado",
        "inicio": inicio.isoformat(),
        "duracion_seg": round(duracion, 1),
        "total_queries": total_queries,
        "queries_ok": queries_ok,
        "queries_error": queries_error,
        "productos_guardados": productos_total,
        "canonicals_creados": canonicals_creados,
    }

    print(f"\n{'='*60}")
    print(f"  SYNC COMPLETADO: {queries_ok}/{total_queries} OK")
    print(f"  Productos: {productos_total} | Canonicals: {canonicals_creados}")
    print(f"  Duracion: {duracion:.0f}s")
    print(f"{'='*60}\n")

    return resumen


def obtener_estado_sync(db: Session) -> dict:
    ultimo = (
        db.query(ProductoProveedor)
        .filter(ProductoProveedor.estado_scraping == EstadoScraping.EXITO)
        .order_by(ProductoProveedor.scraped_at.desc())
        .first()
    )

    total = db.query(ProductoProveedor).filter(
        ProductoProveedor.estado_scraping == EstadoScraping.EXITO
    ).count()

    total_sod = db.query(ProductoProveedor).filter(
        ProductoProveedor.proveedor == NombreProveedor.SODIMAC,
        ProductoProveedor.estado_scraping == EstadoScraping.EXITO,
    ).count()

    total_easy = db.query(ProductoProveedor).filter(
        ProductoProveedor.proveedor == NombreProveedor.EASY,
        ProductoProveedor.estado_scraping == EstadoScraping.EXITO,
    ).count()

    total_canonicals = db.query(ProductoCanonical).count()

    return {
        "ultimo_scraping": ultimo.scraped_at.isoformat() if ultimo else None,
        "total_productos": total,
        "productos_sodimac": total_sod,
        "productos_easy": total_easy,
        "total_canonicals": total_canonicals,
    }
