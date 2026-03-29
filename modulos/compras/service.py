"""
Capa de servicio: persiste los resultados del scraper en la BD.
Separa la lógica de negocio del router y del scraper.
"""

import logging
from sqlalchemy.orm import Session

from .models import ProductoProveedor, EstadoScraping
from .scraper import ResultadoScraper
from .schemas import ProductoProveedorCreate

logger = logging.getLogger(__name__)


def persistir_resultados_scraper(
    resultados: list[ResultadoScraper],
    db: Session,
) -> list[ProductoProveedor]:
    """
    Persiste los productos de todos los scrapers en la BD.
    Evita duplicados por SKU + proveedor (upsert manual).
    Devuelve la lista de instancias persistidas.
    """
    persistidos: list[ProductoProveedor] = []

    for resultado in resultados:
        if resultado.estado != EstadoScraping.EXITO:
            # Registrar el intento fallido pero no guardar productos vacíos
            logger.warning(
                "Scraper %s falló con estado %s: %s",
                resultado.proveedor,
                resultado.estado,
                resultado.error_msg,
            )
            continue

        for schema in resultado.productos:
            # Verificar si ya existe este SKU en este proveedor
            existente = db.query(ProductoProveedor).filter_by(
                proveedor=schema.proveedor,
                sku_proveedor=schema.sku_proveedor,
            ).first()

            if existente:
                # Actualizar precio y disponibilidad si cambió
                existente.precio_clp   = schema.precio_clp
                existente.precio_oferta= schema.precio_oferta
                existente.disponible   = schema.disponible
                existente.estado_scraping = EstadoScraping.EXITO
                persistidos.append(existente)
            else:
                nuevo = ProductoProveedor(
                    proveedor      =schema.proveedor,
                    sku_proveedor  =schema.sku_proveedor,
                    url_producto   =str(schema.url_producto),
                    nombre_raw     =schema.nombre_raw,
                    marca          =schema.marca,
                    precio_clp     =schema.precio_clp,
                    precio_oferta  =schema.precio_oferta,
                    unidad         =schema.unidad,
                    imagen_url     =str(schema.imagen_url) if schema.imagen_url else None,
                    disponible     =schema.disponible,
                    estado_scraping=EstadoScraping.EXITO,
                )
                db.add(nuevo)
                persistidos.append(nuevo)

    db.commit()

    for p in persistidos:
        if p.id is None:
            db.refresh(p)

    logger.info("Persistidos %d productos de scraping", len(persistidos))
    return persistidos