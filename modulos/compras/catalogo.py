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
# Queries predefinidos para el sync diario
# ---------------------------------------------------------------------------

QUERIES_SYNC = [
    # Tornillos
    "Tornillo autoperforante 1 pulgada",
    "Tornillo autoperforante 1 1/2 pulgada",
    "Tornillo volcanita 6x1",
    "Tornillo volcanita 6x1 5/8",
    "Tornillo madera 8x2 pulgadas",
    "Tornillo hexagonal 1/4 pulgada",
    "Tornillo hexagonal 5/16 pulgada",
    "Tornillo hexagonal 3/8 pulgada",
    # Clavos
    "Clavo 1 pulgada",
    "Clavo 1 1/2 pulgada",
    "Clavo 2 pulgadas",
    "Clavo 2 1/2 pulgadas",
    "Clavo 3 pulgadas",
    "Clavo 4 pulgadas",
    "Clavo acero 1 pulgada",
    # Pernos
    "Perno 1/4 x 1 pulgada",
    "Perno 1/4 x 2 pulgadas",
    "Perno 5/16 x 2 pulgadas",
    "Perno 3/8 x 2 pulgadas",
    "Perno 3/8 x 3 pulgadas",
    # Tuercas / Golillas
    "Tuerca hexagonal 1/4",
    "Tuerca hexagonal 3/8",
    "Golilla plana 1/4",
    "Golilla presion 1/4",
    # Tirafondos
    "Tirafondo 1/4 x 2 pulgadas",
    "Tirafondo 1/4 x 3 pulgadas",
    "Tirafondo 3/8 x 3 pulgadas",
    # Placas / Conectores
    "Placa perforada 80x200",
    "Placa perforada 100x300",
    "Escuadra metalica reforzada",
    "Conector angular metalico",
    "Pie derecho regulable",
    # Adhesivos
    "Silicona transparente",
    "Silicona estructural",
    "Adhesivo montaje",
    "Espuma poliuretano expandido",
]


# ---------------------------------------------------------------------------
# Lectura del catalogo desde BD (agrupado por canonical)
# ---------------------------------------------------------------------------

def obtener_catalogo(db: Session) -> list[dict]:
    """
    Retorna TODOS los productos de la BD agrupados por canonical.
    Cada grupo = 1 producto con sus variantes en distintas tiendas.
    """
    # Cargar todos los canonicals que tienen al menos 1 variante disponible
    canonicals = (
        db.query(ProductoCanonical)
        .options(joinedload(ProductoCanonical.variantes))
        .all()
    )

    resultado = []

    for canon in canonicals:
        variantes_activas = [
            v for v in canon.variantes
            if v.disponible and v.estado_scraping == EstadoScraping.EXITO
        ]
        if not variantes_activas:
            continue

        # Agrupar por proveedor — quedarse con el mas reciente de cada uno
        por_prov: dict[str, ProductoProveedor] = {}
        for v in variantes_activas:
            existente = por_prov.get(v.proveedor)
            if existente is None or (v.scraped_at and (not existente.scraped_at or v.scraped_at > existente.scraped_at)):
                por_prov[v.proveedor] = v

        sodimac = por_prov.get(NombreProveedor.SODIMAC)
        easy = por_prov.get(NombreProveedor.EASY)

        # Precio y datos de cada tienda
        def _extraer(p):
            if not p:
                return {"precio": None, "nombre": None, "imagen": None, "sku": None, "url": None}
            return {
                "precio": p.precio_oferta or p.precio_clp,
                "nombre": p.nombre_raw,
                "imagen": str(p.imagen_url) if p.imagen_url else None,
                "sku": p.sku_proveedor,
                "url": str(p.url_producto) if p.url_producto else None,
            }

        sod = _extraer(sodimac)
        eas = _extraer(easy)

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

        # Timestamp mas reciente
        timestamps = [v.scraped_at for v in variantes_activas if v.scraped_at]
        ultimo = max(timestamps).isoformat() if timestamps else None

        # Imagen principal (preferir la de la tienda con mejor precio)
        imagen_principal = None
        if mejor_tienda == "Sodimac":
            imagen_principal = sod["imagen"] or eas["imagen"]
        else:
            imagen_principal = eas["imagen"] or sod["imagen"]

        resultado.append({
            "id": canon.id,
            "nombre": canon.nombre_normalizado,
            "categoria": canon.categoria,
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
            "imagen": imagen_principal,
            "scraped_at": ultimo,
            "n_tiendas": sum(1 for x in [sod["precio"], eas["precio"]] if x is not None),
        })

    # Ordenar: primero los que tienen precio en ambas tiendas, luego por nombre
    resultado.sort(key=lambda x: (-x["n_tiendas"], x["nombre"].lower()))

    return resultado


def buscar_en_catalogo(db: Session, texto: str, limite: int = 50) -> list[dict]:
    """
    Busca productos en la BD por texto (LIKE en nombre).
    Retorna en el mismo formato que obtener_catalogo pero filtrado.
    """
    texto_limpio = texto.strip().lower()
    if not texto_limpio:
        return obtener_catalogo(db)

    # Buscar canonicals cuyo nombre contenga el texto
    todos = obtener_catalogo(db)

    # Filtrar por coincidencia en cualquiera de los nombres
    filtrados = []
    for p in todos:
        nombres = " ".join(filter(None, [
            p["nombre"], p["nombre_sodimac"], p["nombre_easy"],
        ])).lower()
        if texto_limpio in nombres:
            filtrados.append(p)

    return filtrados[:limite]


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

    for i, query in enumerate(QUERIES_SYNC, 1):
        print(f"\n  [{i}/{total_queries}] '{query}'")

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
