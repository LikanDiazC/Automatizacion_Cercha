"""
Capa de servicio: persiste los resultados del scraper en la BD.
Separa la lógica de negocio del router y del scraper.
Incluye normalización de unidades (quantulum3+pint) y clasificación ETIM.
"""

import logging
from sqlalchemy.orm import Session

from .models import ProductoProveedor, EstadoScraping
from .scraper import ResultadoScraper
from .schemas import ProductoProveedorCreate
from .unit_normalizer import normalized_unit_text
from .etim_taxonomy import classify_product

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

            # Normalizar unidad con quantulum3+pint
            unidad_norm = None
            try:
                unidad_norm = normalized_unit_text(
                    schema.nombre_raw, schema.unidad or ""
                )
            except Exception as exc:
                logger.debug("Error normalizando unidad: %s", exc)

            # Clasificar con ETIM
            etim_code = None
            try:
                etim_result = classify_product(schema.nombre_raw, schema.marca or "")
                if etim_result.etim_class:
                    etim_code = etim_result.etim_class.code
            except Exception as exc:
                logger.debug("Error clasificando ETIM: %s", exc)

            if existente:
                # Actualizar precio, disponibilidad y metadata
                existente.precio_clp   = schema.precio_clp
                existente.precio_oferta= schema.precio_oferta
                existente.disponible   = schema.disponible
                existente.estado_scraping = EstadoScraping.EXITO
                existente.unidad = schema.unidad or existente.unidad
                existente.unidad_normalizada = unidad_norm or existente.unidad_normalizada
                existente.etim_class_code = etim_code or existente.etim_class_code
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
                    unidad_normalizada=unidad_norm,
                    imagen_url     =str(schema.imagen_url) if schema.imagen_url else None,
                    disponible     =schema.disponible,
                    estado_scraping=EstadoScraping.EXITO,
                    etim_class_code=etim_code,
                )
                db.add(nuevo)
                persistidos.append(nuevo)

    db.commit()

    for p in persistidos:
        if p.id is None:
            db.refresh(p)

    logger.info("Persistidos %d productos de scraping", len(persistidos))
    return persistidos