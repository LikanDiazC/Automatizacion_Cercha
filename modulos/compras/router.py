"""
Router FastAPI — Módulo de Compras Inteligentes.
"""

import logging
import secrets
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from core.database import get_db, SessionLocal
from .models import (
    ProductoProveedor,
    ProductoCanonical,
    CarritoCompras,
    ItemCarrito,
    EstadoCarrito,
    EstadoScraping,
    NombreProveedor,
)
from .schemas import (
    BusquedaProductoRequest,
    ResultadoBusqueda,
    ProductoProveedorResponse,
    ProductoCanonicalResponse,
    CarritoResponse,
    ItemCarritoResponse,
    AgregarItemRequest,
    ResumenCotizacion,
)
from .scraper import ejecutar_busqueda, ResultadoScraper
from .service import persistir_resultados_scraper
from .ai_matcher import (
    comparar_productos,
    obtener_o_crear_canonical,
    generar_y_guardar_embedding,
    MatchResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/compras",
    tags=["Cotizador Inteligente"],
)

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _producto_a_response(p: ProductoProveedor) -> ProductoProveedorResponse:
    return ProductoProveedorResponse(
        id             =p.id,
        proveedor      =p.proveedor,
        sku_proveedor  =p.sku_proveedor,
        url_producto   =str(p.url_producto),
        nombre_raw     =p.nombre_raw,
        marca          =p.marca,
        precio_clp     =p.precio_clp,
        precio_oferta  =p.precio_oferta,
        unidad         =p.unidad,
        imagen_url     =str(p.imagen_url) if p.imagen_url else None,
        disponible     =p.disponible,
        estado_scraping=p.estado_scraping,
        scraped_at     =p.scraped_at,
        canonical_id   =p.canonical_id,
    )


def _canonical_a_response(c: ProductoCanonical) -> ProductoCanonicalResponse:
    return ProductoCanonicalResponse(
        id                 =c.id,
        nombre_normalizado =c.nombre_normalizado,
        descripcion        =c.descripcion,
        unidad_base        =c.unidad_base,
        categoria          =c.categoria,
        created_at         =c.created_at,
    )


def _item_a_response(item: ItemCarrito) -> ItemCarritoResponse:
    canonical = None
    if item.canonical:
        canonical = _canonical_a_response(item.canonical)
    return ItemCarritoResponse(
        id             =item.id,
        canonical_id   =item.canonical_id,
        cantidad       =item.cantidad,
        query_original =item.query_original,
        precio_sodimac =item.precio_sodimac,
        precio_easy    =item.precio_easy,
        canonical      =canonical,
    )


def _obtener_carrito_o_404(session_key: str, db: Session) -> CarritoCompras:
    carrito = db.query(CarritoCompras).filter_by(
        session_key=session_key,
        estado=EstadoCarrito.ACTIVO,
    ).first()
    if not carrito:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Carrito '{session_key}' no encontrado o ya procesado.",
        )
    return carrito


# ---------------------------------------------------------------------------
# Endpoint 1: Búsqueda inteligente
# ---------------------------------------------------------------------------

@router.post(
    "/buscar",
    response_model=list[ResultadoBusqueda],
    summary="Buscar y comparar productos entre proveedores",
)
async def buscar_productos(
    request:    BusquedaProductoRequest,
    background: BackgroundTasks,
    db:         Session = Depends(get_db),
) -> list[ResultadoBusqueda]:
    
    logger.info("Búsqueda iniciada: query='%s' proveedores=%s", request.query, request.proveedores)

    # --- Paso 1: Scraping con curl_cffi ---
    try:
        resultados_scraper: list[ResultadoScraper] = await ejecutar_busqueda(
            query=request.query,
            proveedores=request.proveedores,
            max_resultados=request.max_resultados,
        )
    except Exception as exc:
        logger.error("Error crítico en scraping: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al conectar con los proveedores. Intenta de nuevo.",
        )

    total_productos = sum(len(r.productos) for r in resultados_scraper)
    if total_productos == 0:
        logger.warning("Ningún scraper devolvió productos para query='%s'", request.query)
        return []

    # --- Paso 2: Persistir en BD ---
    productos_db: list[ProductoProveedor] = persistir_resultados_scraper(resultados_scraper, db)

    if not productos_db:
        return []

    # --- Paso 3: Canonical y embeddings ---
    try:
        canonical = await obtener_o_crear_canonical(
            nombre_query=request.query,
            productos_encontrados=productos_db,
            db=db,
        )
    except Exception as exc:
        logger.error("Error creando canonical: %s", exc)
        canonical = None

    # Fix: Sesión independiente para evitar Database Lock
    async def _generar_embeddings_background(productos_ids: list[int]) -> None:
        db_bg = SessionLocal() 
        try:
            productos_bg = db_bg.query(ProductoProveedor).filter(ProductoProveedor.id.in_(productos_ids)).all()
            for p in productos_bg:
                try:
                    await generar_y_guardar_embedding(p, db_bg)
                except Exception as e:
                    logger.warning("Embedding fallido: %s", e)
        finally:
            db_bg.close()

    ids_productos = [p.id for p in productos_db]
    background.add_task(_generar_embeddings_background, ids_productos)

    # --- Paso 4: Agrupar por canonical y hacer matching ---
    resultados: list[ResultadoBusqueda] = await _construir_resultados_busqueda(
        query=request.query,
        productos=productos_db,
        canonical=canonical,
        db=db,
    )

    logger.info("Búsqueda completada: query='%s' → %d resultados", request.query, len(resultados))
    return resultados


async def _construir_resultados_busqueda(
    query:     str,
    productos: list[ProductoProveedor],
    canonical: Optional[ProductoCanonical],
    db:        Session,
) -> list[ResultadoBusqueda]:
    
    por_proveedor: dict[NombreProveedor, list[ProductoProveedor]] = {}
    for p in productos:
        por_proveedor.setdefault(p.proveedor, []).append(p)

    proveedores_con_datos = list(por_proveedor.keys())
    resultados = []

    representantes: list[ProductoProveedor] = [
        por_proveedor[prov][0]
        for prov in proveedores_con_datos
        if por_proveedor[prov]
    ]

    match_result: Optional[MatchResult] = None
    if len(representantes) >= 2:
        try:
            match_result = await comparar_productos(representantes[0], representantes[1], db)
        except Exception as exc:
            logger.error("Error en matching IA: %s", exc)

    for proveedor in proveedores_con_datos:
        variantes_proveedor = por_proveedor[proveedor]

        mejor_precio_prov = min(
            (p.precio_oferta or p.precio_clp)
            for p in variantes_proveedor
            if p.precio_clp is not None
        )

        otro_proveedor = [pv for pv in proveedores_con_datos if pv != proveedor]
        precio_otro = None
        if otro_proveedor:
            otros = por_proveedor[otro_proveedor[0]]
            if otros:
                precio_otro = min(
                    (p.precio_oferta or p.precio_clp)
                    for p in otros
                    if p.precio_clp is not None
                )

        diferencia = None
        if precio_otro is not None and mejor_precio_prov is not None:
            diferencia = abs(mejor_precio_prov - precio_otro)

        canonical_resp = _canonical_a_response(canonical) if canonical else None

        resultados.append(ResultadoBusqueda(
            canonical        =canonical_resp or ProductoCanonicalResponse(
                id=0,
                nombre_normalizado=query,
                descripcion=None,
                unidad_base=None,
                categoria=None,
                created_at=datetime.utcnow(),
            ),
            variantes        =[_producto_a_response(p) for p in variantes_proveedor],
            mejor_precio     =mejor_precio_prov,
            proveedor_optimo =proveedor,
            diferencia_precio=diferencia,
            confidence_score =match_result.confidence_score if match_result else None,
        ))

    return resultados


# ---------------------------------------------------------------------------
# Endpoint 2: Resultados cacheados (sin scraping)
# ---------------------------------------------------------------------------

@router.get(
    "/buscar/cache",
    response_model=list[ResultadoBusqueda],
    summary="Buscar en productos ya scrapeados (sin scraping en vivo)",
)
def buscar_en_cache(
    query:          str,
    max_resultados: int = 10,
    db:             Session = Depends(get_db),
) -> list[ResultadoBusqueda]:
    
    query_limpio = query.strip()[:200]

    productos = (
        db.query(ProductoProveedor)
        .filter(
            ProductoProveedor.nombre_raw.ilike(f"%{query_limpio}%"),
            ProductoProveedor.disponible == True,
        )
        .limit(max_resultados)
        .all()
    )

    if not productos:
        return []

    por_canonical: dict[Optional[int], list[ProductoProveedor]] = {}
    for p in productos:
        por_canonical.setdefault(p.canonical_id, []).append(p)

    resultados = []
    for canonical_id, grupo in por_canonical.items():
        canonical = None
        if canonical_id:
            canonical = db.query(ProductoCanonical).get(canonical_id)

        mejor = min(
            (p.precio_oferta or p.precio_clp for p in grupo if p.precio_clp),
            default=None,
        )

        resultados.append(ResultadoBusqueda(
            canonical=_canonical_a_response(canonical) if canonical else ProductoCanonicalResponse(
                id=0,
                nombre_normalizado=query_limpio,
                descripcion=None,
                unidad_base=None,
                categoria=None,
                created_at=datetime.utcnow(),
            ),
            variantes        =[_producto_a_response(p) for p in grupo],
            mejor_precio     =mejor,
            proveedor_optimo =grupo[0].proveedor if grupo else None,
            diferencia_precio=None,
            confidence_score =None,
        ))

    return resultados


# ---------------------------------------------------------------------------
# Endpoint 3: Detalle de un producto canónico
# ---------------------------------------------------------------------------

@router.get(
    "/productos/{canonical_id}",
    response_model=ResultadoBusqueda,
    summary="Detalle de un producto canónico con todas sus variantes",
)
def obtener_producto(
    canonical_id: int,
    db:           Session = Depends(get_db),
) -> ResultadoBusqueda:

    canonical = db.query(ProductoCanonical).get(canonical_id)
    if not canonical:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Producto canónico {canonical_id} no encontrado.",
        )

    variantes = (
        db.query(ProductoProveedor)
        .filter_by(canonical_id=canonical_id, disponible=True)
        .all()
    )

    mejor_precio = None
    proveedor_optimo = None
    if variantes:
        mejor = min(
            variantes,
            key=lambda p: p.precio_oferta or p.precio_clp or float("inf"),
        )
        mejor_precio    = mejor.precio_oferta or mejor.precio_clp
        proveedor_optimo = mejor.proveedor

    return ResultadoBusqueda(
        canonical        =_canonical_a_response(canonical),
        variantes        =[_producto_a_response(v) for v in variantes],
        mejor_precio     =mejor_precio,
        proveedor_optimo =proveedor_optimo,
        diferencia_precio=None,
        confidence_score =None,
    )

# ---------------------------------------------------------------------------
# Endpoints de Carrito
# ---------------------------------------------------------------------------

@router.post("/carrito", response_model=CarritoResponse, status_code=status.HTTP_201_CREATED)
def crear_carrito(db: Session = Depends(get_db)) -> CarritoResponse:
    session_key = secrets.token_urlsafe(32)
    carrito = CarritoCompras(session_key=session_key)
    db.add(carrito)
    db.commit()
    db.refresh(carrito)
    return _carrito_a_response(carrito)

@router.post("/carrito/{session_key}/items", response_model=CarritoResponse)
def agregar_item(session_key: str, request: AgregarItemRequest, db: Session = Depends(get_db)) -> CarritoResponse:
    carrito = _obtener_carrito_o_404(session_key, db)
    canonical = db.query(ProductoCanonical).get(request.canonical_id)
    if not canonical:
        raise HTTPException(status_code=404, detail="Producto canónico no encontrado.")

    item_existente = next((i for i in carrito.items if i.canonical_id == request.canonical_id), None)
    if item_existente:
        item_existente.cantidad += request.cantidad
        db.add(item_existente)
    else:
        precio_sodimac = _precio_de_proveedor(request.canonical_id, NombreProveedor.SODIMAC, db)
        precio_easy = _precio_de_proveedor(request.canonical_id, NombreProveedor.EASY, db)
        nuevo_item = ItemCarrito(
            carrito_id=carrito.id,
            canonical_id=request.canonical_id,
            cantidad=request.cantidad,
            query_original=request.query_original,
            precio_sodimac=precio_sodimac,
            precio_easy=precio_easy,
        )
        db.add(nuevo_item)

    db.commit()
    db.refresh(carrito)
    return _carrito_a_response(carrito)

@router.get("/carrito/{session_key}", response_model=CarritoResponse)
def ver_carrito(session_key: str, db: Session = Depends(get_db)) -> CarritoResponse:
    carrito = _obtener_carrito_o_404(session_key, db)
    return _carrito_a_response(carrito)

@router.delete("/carrito/{session_key}/items/{item_id}", response_model=CarritoResponse)
def eliminar_item(session_key: str, item_id: int, db: Session = Depends(get_db)) -> CarritoResponse:
    carrito = _obtener_carrito_o_404(session_key, db)
    item = next((i for i in carrito.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado en el carrito.")
    db.delete(item)
    db.commit()
    db.refresh(carrito)
    return _carrito_a_response(carrito)

@router.post("/carrito/{session_key}/procesar", response_model=ResumenCotizacion)
def procesar_carrito(session_key: str, db: Session = Depends(get_db)) -> ResumenCotizacion:
    carrito = _obtener_carrito_o_404(session_key, db)
    if not carrito.items:
        raise HTTPException(status_code=400, detail="Carrito vacío.")

    total_sodimac, total_easy = 0.0, 0.0
    advertencias, items_resp = [], []

    for item in carrito.items:
        qty = item.cantidad
        if item.precio_sodimac is not None: total_sodimac += item.precio_sodimac * qty
        else: advertencias.append(f"'{item.query_original}' no disponible en Sodimac.")
        
        if item.precio_easy is not None: total_easy += item.precio_easy * qty
        else: advertencias.append(f"'{item.query_original}' no disponible en Easy.")
        
        items_resp.append(_item_a_response(item))

    if total_sodimac > 0 and total_easy > 0:
        proveedor_optimo = NombreProveedor.SODIMAC if total_sodimac <= total_easy else NombreProveedor.EASY
        ahorro = abs(total_easy - total_sodimac)
    elif total_sodimac > 0:
        proveedor_optimo, ahorro = NombreProveedor.SODIMAC, 0.0
        advertencias.append("Comparación parcial (falta Easy).")
    elif total_easy > 0:
        proveedor_optimo, ahorro = NombreProveedor.EASY, 0.0
        advertencias.append("Comparación parcial (falta Sodimac).")
    else:
        raise HTTPException(status_code=422, detail="Sin precios para comparar.")

    referencia = max(total_sodimac, total_easy)
    ahorro_porcentaje = (ahorro / referencia * 100) if referencia > 0 else 0.0

    carrito.total_sodimac = total_sodimac
    carrito.total_easy = total_easy
    carrito.ahorro_potencial = ahorro
    carrito.proveedor_optimo = proveedor_optimo
    carrito.estado = EstadoCarrito.PROCESADO
    carrito.procesado_at = datetime.utcnow()
    db.commit()

    return ResumenCotizacion(
        carrito_id=carrito.id,
        items_count=len(carrito.items),
        total_sodimac=total_sodimac,
        total_easy=total_easy,
        ahorro_potencial=ahorro,
        proveedor_optimo=proveedor_optimo,
        ahorro_porcentaje=round(ahorro_porcentaje, 2),
        detalle=items_resp,
        advertencias=advertencias,
    )

def _precio_de_proveedor(canonical_id: int, proveedor: NombreProveedor, db: Session) -> Optional[float]:
    p = db.query(ProductoProveedor).filter_by(canonical_id=canonical_id, proveedor=proveedor, disponible=True).order_by(ProductoProveedor.precio_clp.asc()).first()
    return (p.precio_oferta or p.precio_clp) if p else None

def _carrito_a_response(carrito: CarritoCompras) -> CarritoResponse:
    return CarritoResponse(
        id=carrito.id, session_key=carrito.session_key, estado=carrito.estado,
        items=[_item_a_response(i) for i in carrito.items],
        total_sodimac=carrito.total_sodimac, total_easy=carrito.total_easy,
        ahorro_potencial=carrito.ahorro_potencial, proveedor_optimo=carrito.proveedor_optimo,
        created_at=carrito.created_at, procesado_at=carrito.procesado_at,
    )