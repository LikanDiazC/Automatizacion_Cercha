"""
Router FastAPI — Módulo de Compras Inteligentes.
"""

import json as _json
import logging
import secrets
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status, BackgroundTasks
from sqlalchemy.orm import Session
from core.rate_limit import limiter

from core.database import get_db, SessionLocal
from .models import (
    ProductoProveedor,
    ProductoCanonical,
    ComparacionPrecios,
    AICallLog,
    PromptVersion,
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
    similitud_textual,
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
@limiter.limit("5/minute")  # Máx 5 búsquedas/minuto por IP — el scraping es costoso
async def buscar_productos(
    request:    Request,                            # FastAPI Request — requerido por slowapi
    body:       BusquedaProductoRequest,            # Cuerpo JSON de la petición
    background: BackgroundTasks,
    db:         Session = Depends(get_db),
) -> list[ResultadoBusqueda]:

    logger.info("Búsqueda iniciada: query='%s' proveedores=%s", body.query, body.proveedores)

    # --- Paso 1: Scraping en vivo ---
    try:
        resultados_scraper: list[ResultadoScraper] = await ejecutar_busqueda(
            query=body.query,
            proveedores=body.proveedores,
            max_resultados=body.max_resultados,
        )
    except Exception as exc:
        logger.error("Error crítico en scraping: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error al conectar con los proveedores. Intenta de nuevo.",
        )

    total_productos = sum(len(r.productos) for r in resultados_scraper)
    if total_productos == 0:
        logger.warning("Ningún scraper devolvió productos para query='%s'", body.query)
        return []

    # --- Paso 2: Persistir en BD ---
    productos_db: list[ProductoProveedor] = persistir_resultados_scraper(resultados_scraper, db)

    if not productos_db:
        return []

    # --- Paso 3: Canonical y embeddings ---
    try:
        canonical = await obtener_o_crear_canonical(
            nombre_query=body.query,
            productos_encontrados=productos_db,
            db=db,
        )
    except Exception as exc:
        logger.error("Error creando canonical: %s", exc)
        canonical = None

    # Sesión independiente para embeddings en background — evita Database Lock con SQLite
    async def _generar_embeddings_background(productos_ids: list[int]) -> None:
        db_bg = SessionLocal()
        try:
            productos_bg = (
                db_bg.query(ProductoProveedor)
                .filter(ProductoProveedor.id.in_(productos_ids))
                .all()
            )
            for p in productos_bg:
                try:
                    await generar_y_guardar_embedding(p, db_bg)
                except Exception as e:
                    logger.warning("Embedding fallido para producto id=%s: %s", p.id, e)
        finally:
            db_bg.close()

    ids_productos = [p.id for p in productos_db]
    background.add_task(_generar_embeddings_background, ids_productos)

    # --- Paso 4: Agrupar por canonical y hacer matching ---
    resultados: list[ResultadoBusqueda] = await _construir_resultados_busqueda(
        query=body.query,
        productos=productos_db,
        canonical=canonical,
        db=db,
    )

    logger.info("Búsqueda completada: query='%s' → %d resultados", body.query, len(resultados))
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

    # 1. Seleccionar el candidato más relevante al query por cada proveedor.
    #    Si el mejor candidato no comparte ninguna palabra con el query, se descarta
    #    ese proveedor (evita comparar p.ej. "Silla PC Asti negro" para búsqueda "tornillo").
    variantes_finales = []
    for prov in proveedores_con_datos:
        candidatos = por_proveedor.get(prov, [])
        if not candidatos:
            continue
        # Ordenar por similitud Jaccard al query (mayor relevancia primero)
        candidatos_ordenados = sorted(
            candidatos,
            key=lambda p: similitud_textual(query, p.nombre_raw),
            reverse=True,
        )
        mejor = candidatos_ordenados[0]
        relevancia = similitud_textual(query, mejor.nombre_raw)
        if relevancia > 0.0:
            variantes_finales.append(mejor)
        else:
            logger.warning(
                "Proveedor %s descartado: ningún producto es relevante para '%s' "
                "(mejor candidato: '%s', relevancia=0.0)",
                prov, query, mejor.nombre_raw,
            )

    # Si ningún proveedor tiene productos relevantes, no retornar tarjeta vacía
    if not variantes_finales:
        logger.warning("Ningún proveedor tiene productos relevantes para '%s'", query)
        return []

    # 2. IA compara los dos finalistas
    match_result: Optional[MatchResult] = None
    if len(variantes_finales) >= 2:
        try:
            match_result = await comparar_productos(variantes_finales[0], variantes_finales[1], db, query_original=query)
        except Exception as exc:
            logger.error("Error en matching IA: %s", exc)

    # 3. Calculamos la diferencia de precio
    mejor_precio = None
    proveedor_optimo = None
    diferencia = None

    if variantes_finales:
        mejor_variante = min(variantes_finales, key=lambda p: p.precio_oferta or p.precio_clp)
        mejor_precio = mejor_variante.precio_oferta or mejor_variante.precio_clp
        proveedor_optimo = mejor_variante.proveedor
        
        if len(variantes_finales) == 2:
            p1 = variantes_finales[0].precio_oferta or variantes_finales[0].precio_clp
            p2 = variantes_finales[1].precio_oferta or variantes_finales[1].precio_clp
            diferencia = abs(p1 - p2)

    canonical_resp = _canonical_a_response(canonical) if canonical else ProductoCanonicalResponse(
        id=0,
        nombre_normalizado=query,
        descripcion=None,
        unidad_base=None,
        categoria=None,
        created_at=datetime.utcnow(),
    )

    # 4. Retornamos UN SOLO resultado consolidado
    return [ResultadoBusqueda(
        canonical=canonical_resp,
        variantes=[_producto_a_response(p) for p in variantes_finales],
        mejor_precio=mejor_precio,
        proveedor_optimo=proveedor_optimo,
        diferencia_precio=diferencia,
        confidence_score=match_result.confidence_score if match_result else None,
    )]


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

# ---------------------------------------------------------------------------
# Endpoints: Catalogo con precios pre-scrapeados
# ---------------------------------------------------------------------------

@router.get(
    "/catalogo",
    summary="Catalogo completo — productos agrupados por canonical con precios",
)
def obtener_catalogo_endpoint(db: Session = Depends(get_db)):
    from .catalogo import obtener_catalogo
    return obtener_catalogo(db)


@router.get(
    "/catalogo/buscar",
    summary="Buscar dentro del catalogo de la BD (sin scraping)",
)
def buscar_catalogo_endpoint(q: str = "", limite: int = 50, db: Session = Depends(get_db)):
    from .catalogo import buscar_en_catalogo
    return buscar_en_catalogo(db, q, limite)


@router.get(
    "/catalogo/estado",
    summary="Estado de la ultima sincronizacion del catalogo",
)
def estado_catalogo(db: Session = Depends(get_db)):
    from .catalogo import obtener_estado_sync
    return obtener_estado_sync(db)


@router.post(
    "/catalogo/sync",
    summary="Lanzar sincronizacion manual del catalogo (scrapea todo)",
)
async def sincronizar_catalogo(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Lanza el scraping de TODAS las variantes del catalogo.
    Esto toma varios minutos — se ejecuta en background via asyncio.create_task.
    """
    from .catalogo import sync_catalogo

    async def _sync_en_background():
        db_bg = SessionLocal()
        try:
            resultado = await sync_catalogo(db_bg)
            logger.info("Sync catalogo completado: %s", resultado)
        except Exception as exc:
            logger.error("Error en sync catalogo: %s", exc, exc_info=True)
        finally:
            db_bg.close()

    # create_task corre en el event loop principal de asyncio — no en un thread
    asyncio.create_task(_sync_en_background())
    return {"status": "sync_iniciado", "mensaje": "Sincronizacion del catalogo iniciada en background"}


@router.post(
    "/catalogo/sync-item",
    summary="Sincronizar un solo item del catalogo",
)
@limiter.limit("5/minute")
async def sincronizar_item(
    request: Request,
    body: BusquedaProductoRequest,
    db: Session = Depends(get_db),
):
    """
    Scrapea un solo producto y guarda en BD.
    Util para actualizar un item especifico sin esperar el sync completo.
    """
    try:
        resultados_scraper = await ejecutar_busqueda(
            query=body.query,
            proveedores=body.proveedores,
            max_resultados=body.max_resultados,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    total = sum(len(r.productos) for r in resultados_scraper)
    if total == 0:
        return {"status": "sin_resultados", "query": body.query, "productos": 0}

    persistidos = persistir_resultados_scraper(resultados_scraper, db)
    return {
        "status": "ok",
        "query": body.query,
        "productos": len(persistidos),
    }


# ---------------------------------------------------------------------------
# Endpoint: Diagnóstico de scraper
# ---------------------------------------------------------------------------

@router.get(
    "/debug/dumps",
    summary="Listar dumps de diagnóstico del scraper",
)
def listar_dumps_scraper(limite: int = 20):
    from .scraper_debug import listar_dumps
    return listar_dumps(limite)


@router.get(
    "/debug/dumps/{filename}",
    summary="Leer un dump de diagnóstico específico",
)
def leer_dump_scraper(filename: str):
    import json as _json
    from pathlib import Path
    dumps_dir = Path(__file__).parent.parent.parent / "debug" / "scraper_dumps"
    filepath = dumps_dir / filename
    if not filepath.exists() or not filepath.suffix == ".json":
        raise HTTPException(status_code=404, detail="Dump no encontrado.")
    with open(filepath, "r", encoding="utf-8") as f:
        return _json.load(f)


# ---------------------------------------------------------------------------
# Endpoints: Historial de precios (estilo SoloTodo)
# ---------------------------------------------------------------------------

@router.get(
    "/precios/historial/{canonical_id}",
    summary="Historial de precios de un producto canónico",
)
def historial_precios(canonical_id: int, dias: int = 30, db: Session = Depends(get_db)):
    """
    Retorna el historial de precios de todas las variantes de un canonical.
    Útil para gráficos de evolución de precios estilo SoloTodo.
    """
    from datetime import timedelta
    from .models import HistorialPrecios

    limite = datetime.utcnow() - timedelta(days=dias)

    registros = (
        db.query(HistorialPrecios)
        .join(ProductoProveedor)
        .filter(
            HistorialPrecios.canonical_id == canonical_id,
            HistorialPrecios.registrado_at >= limite,
        )
        .order_by(HistorialPrecios.registrado_at.asc())
        .all()
    )

    # Agrupar por proveedor
    por_proveedor: dict[str, list] = {}
    for r in registros:
        prov = r.producto.proveedor.value if r.producto else "desconocido"
        por_proveedor.setdefault(prov, []).append({
            "fecha": r.registrado_at.isoformat(),
            "precio_normal": r.precio_normal,
            "precio_oferta": r.precio_oferta,
            "disponible": r.disponible,
        })

    return {
        "canonical_id": canonical_id,
        "dias": dias,
        "series": por_proveedor,
    }


@router.get(
    "/precios/alertas",
    summary="Productos con mayor caída de precio reciente",
)
def alertas_precios(limite: int = 10, db: Session = Depends(get_db)):
    """
    Retorna los productos cuyo precio bajó más respecto al registro anterior.
    Útil para un dashboard de oportunidades.
    """
    from .models import HistorialPrecios
    from sqlalchemy import desc

    # Obtener los últimos 2 registros por producto
    subquery = (
        db.query(
            HistorialPrecios.producto_id,
            HistorialPrecios.precio_normal,
            HistorialPrecios.registrado_at,
        )
        .order_by(HistorialPrecios.producto_id, desc(HistorialPrecios.registrado_at))
        .all()
    )

    # Agrupar por producto y calcular cambio
    por_producto: dict[int, list] = {}
    for prod_id, precio, fecha in subquery:
        por_producto.setdefault(prod_id, []).append({"precio": precio, "fecha": fecha})

    alertas = []
    for prod_id, registros_list in por_producto.items():
        if len(registros_list) < 2:
            continue
        actual = registros_list[0]["precio"]
        anterior = registros_list[1]["precio"]
        if anterior > 0 and actual < anterior:
            cambio_pct = ((actual - anterior) / anterior) * 100
            producto = db.query(ProductoProveedor).get(prod_id)
            if producto:
                alertas.append({
                    "producto_id": prod_id,
                    "nombre": producto.nombre_raw,
                    "proveedor": producto.proveedor.value,
                    "precio_anterior": anterior,
                    "precio_actual": actual,
                    "cambio_pct": round(cambio_pct, 1),
                    "canonical_id": producto.canonical_id,
                })

    alertas.sort(key=lambda x: x["cambio_pct"])
    return alertas[:limite]


@router.get(
    "/scheduler/estado",
    summary="Estado del scheduler de sync automático",
)
def estado_scheduler():
    """Retorna el estado del scheduler y el último sync."""
    try:
        from core.scheduler import get_scheduler, get_ultimo_sync
        scheduler = get_scheduler()
        return {
            "scheduler_activo": scheduler is not None and scheduler.running if scheduler else False,
            "ultimo_sync": get_ultimo_sync(),
            "jobs": [
                {"id": job.id, "name": job.name, "next_run": str(job.next_run_time)}
                for job in (scheduler.get_jobs() if scheduler else [])
            ],
        }
    except ImportError:
        return {"scheduler_activo": False, "error": "APScheduler no instalado"}


# ---------------------------------------------------------------------------
# Endpoints: Admin — Diagnóstico de Comparaciones IA
# ---------------------------------------------------------------------------

@router.get(
    "/admin/comparaciones",
    summary="Listar todas las comparaciones IA con detalle completo",
)
def listar_comparaciones(
    limite: int = 100,
    offset: int = 0,
    solo_matches: Optional[bool] = None,
    metodo: Optional[str] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    db: Session = Depends(get_db),
):
    """
    Dashboard administrativo de comparaciones.
    Permite filtrar por método, confidence, y si fue match o no.
    """
    import json as _json

    query = db.query(ComparacionPrecios).order_by(ComparacionPrecios.calculado_at.desc())

    if min_confidence is not None:
        query = query.filter(ComparacionPrecios.confidence_score >= min_confidence)
    if max_confidence is not None:
        query = query.filter(ComparacionPrecios.confidence_score <= max_confidence)

    total = query.count()
    comparaciones = query.offset(offset).limit(limite).all()

    resultados = []
    for c in comparaciones:
        prod_a = db.query(ProductoProveedor).get(c.producto_a_id)
        prod_b = db.query(ProductoProveedor).get(c.producto_b_id)

        # Parsear razon_ia JSON
        razon_data = {}
        if c.razon_ia:
            try:
                razon_data = _json.loads(c.razon_ia)
            except _json.JSONDecodeError:
                razon_data = {"razon": c.razon_ia}

        metodo_usado = razon_data.get("metodo", "desconocido")

        # Filtrar por método si se pide
        if metodo and metodo_usado != metodo:
            continue

        # Filtrar por matches
        es_match = c.confidence_score >= 0.40
        if solo_matches is True and not es_match:
            continue
        if solo_matches is False and es_match:
            continue

        item = {
            "id": c.id,
            "calculado_at": c.calculado_at.isoformat() if c.calculado_at else None,
            "confidence_score": c.confidence_score,
            "precio_diff_pct": c.precio_diff_pct,
            "precio_minimo": c.precio_minimo,
            "proveedor_minimo": c.proveedor_minimo.value if c.proveedor_minimo else None,
            "es_match": es_match,
            "metodo": metodo_usado,
            "razon": razon_data.get("razon", ""),
            "canonical_id": c.canonical_id,
            # Observabilidad v2
            "prompt_version": c.prompt_version,
            "modelo_usado": c.modelo_usado,
            "latencia_total_ms": c.latencia_total_ms,
            "tokens_totales": c.tokens_totales,
            "costo_usd": c.costo_usd,
            "tiene_lineage": bool(c.lineage_json),
            "producto_a": {
                "id": prod_a.id,
                "nombre": prod_a.nombre_raw,
                "proveedor": prod_a.proveedor.value,
                "precio": prod_a.precio_clp,
                "precio_oferta": prod_a.precio_oferta,
                "unidad": prod_a.unidad,
                "sku": prod_a.sku_proveedor,
                "imagen_url": prod_a.imagen_url,
                "url": prod_a.url_producto,
                "tiene_embedding": bool(prod_a.embedding_json),
            } if prod_a else None,
            "producto_b": {
                "id": prod_b.id,
                "nombre": prod_b.nombre_raw,
                "proveedor": prod_b.proveedor.value,
                "precio": prod_b.precio_clp,
                "precio_oferta": prod_b.precio_oferta,
                "unidad": prod_b.unidad,
                "sku": prod_b.sku_proveedor,
                "imagen_url": prod_b.imagen_url,
                "url": prod_b.url_producto,
                "tiene_embedding": bool(prod_b.embedding_json),
            } if prod_b else None,
        }
        resultados.append(item)

    return {
        "total": total,
        "offset": offset,
        "limite": limite,
        "comparaciones": resultados,
    }


@router.get(
    "/admin/comparaciones/stats",
    summary="Estadísticas globales de las comparaciones IA",
)
def stats_comparaciones(db: Session = Depends(get_db)):
    """Resumen general para el dashboard admin."""
    import json as _json
    from sqlalchemy import func

    total = db.query(ComparacionPrecios).count()
    total_productos = db.query(ProductoProveedor).count()
    total_canonicals = db.query(ProductoCanonical).count()
    productos_con_embedding = db.query(ProductoProveedor).filter(
        ProductoProveedor.embedding_json.isnot(None)
    ).count()

    # Distribución de confidence
    rangos = {
        "alta_0.9_1.0": db.query(ComparacionPrecios).filter(
            ComparacionPrecios.confidence_score >= 0.9
        ).count(),
        "media_0.6_0.9": db.query(ComparacionPrecios).filter(
            ComparacionPrecios.confidence_score >= 0.6,
            ComparacionPrecios.confidence_score < 0.9,
        ).count(),
        "baja_0.3_0.6": db.query(ComparacionPrecios).filter(
            ComparacionPrecios.confidence_score >= 0.3,
            ComparacionPrecios.confidence_score < 0.6,
        ).count(),
        "rechazo_0_0.3": db.query(ComparacionPrecios).filter(
            ComparacionPrecios.confidence_score < 0.3,
        ).count(),
    }

    # Distribución por método
    all_comparaciones = db.query(ComparacionPrecios).all()
    metodos: dict[str, int] = {}
    for c in all_comparaciones:
        if c.razon_ia:
            try:
                data = _json.loads(c.razon_ia)
                m = data.get("metodo", "desconocido")
            except _json.JSONDecodeError:
                m = "desconocido"
        else:
            m = "desconocido"
        metodos[m] = metodos.get(m, 0) + 1

    # Productos sin canonical
    sin_canonical = db.query(ProductoProveedor).filter(
        ProductoProveedor.canonical_id.is_(None)
    ).count()

    # Productos con ETIM y unidad normalizada
    con_etim = db.query(ProductoProveedor).filter(
        ProductoProveedor.etim_class_code.isnot(None)
    ).count()
    con_unidad_norm = db.query(ProductoProveedor).filter(
        ProductoProveedor.unidad_normalizada.isnot(None)
    ).count()

    # Total AI calls y costo
    total_ai_calls = db.query(AICallLog).count()
    from sqlalchemy import func as sa_func
    total_ai_cost = db.query(sa_func.sum(AICallLog.costo_usd)).scalar() or 0
    avg_latencia_llm = db.query(sa_func.avg(AICallLog.latencia_ms)).filter(
        AICallLog.call_type == "llm"
    ).scalar() or 0

    return {
        "total_comparaciones": total,
        "total_productos": total_productos,
        "total_canonicals": total_canonicals,
        "productos_con_embedding": productos_con_embedding,
        "productos_sin_embedding": total_productos - productos_con_embedding,
        "productos_sin_canonical": sin_canonical,
        "productos_con_etim": con_etim,
        "productos_con_unidad_normalizada": con_unidad_norm,
        "total_ai_calls": total_ai_calls,
        "total_ai_cost_usd": round(total_ai_cost, 6),
        "avg_latencia_llm_ms": round(avg_latencia_llm, 2),
        "distribucion_confidence": rangos,
        "distribucion_metodos": metodos,
    }


@router.get(
    "/admin/productos",
    summary="Listar productos con info de embeddings y canonicals",
)
def listar_productos_admin(
    limite: int = 100,
    offset: int = 0,
    proveedor: Optional[str] = None,
    sin_canonical: bool = False,
    sin_embedding: bool = False,
    db: Session = Depends(get_db),
):
    """Lista de productos con metadata técnica para el admin."""
    query = db.query(ProductoProveedor).order_by(ProductoProveedor.scraped_at.desc())

    if proveedor:
        query = query.filter(ProductoProveedor.proveedor == proveedor)
    if sin_canonical:
        query = query.filter(ProductoProveedor.canonical_id.is_(None))
    if sin_embedding:
        query = query.filter(ProductoProveedor.embedding_json.is_(None))

    total = query.count()
    productos = query.offset(offset).limit(limite).all()

    return {
        "total": total,
        "productos": [{
            "id": p.id,
            "nombre": p.nombre_raw,
            "proveedor": p.proveedor.value,
            "sku": p.sku_proveedor,
            "precio": p.precio_clp,
            "precio_oferta": p.precio_oferta,
            "unidad": p.unidad,
            "imagen_url": p.imagen_url,
            "url": p.url_producto,
            "canonical_id": p.canonical_id,
            "canonical_nombre": p.canonical.nombre_normalizado if p.canonical else None,
            "tiene_embedding": bool(p.embedding_json),
            "embedding_dim": len(_json_loads_safe(p.embedding_json)) if p.embedding_json else 0,
            "unidad_normalizada": p.unidad_normalizada,
            "etim_class_code": p.etim_class_code,
            "scraped_at": p.scraped_at.isoformat() if p.scraped_at else None,
            "estado_scraping": p.estado_scraping.value if p.estado_scraping else None,
        } for p in productos],
    }


@router.get(
    "/admin/embedding/{producto_id}",
    summary="Ver el embedding completo de un producto (para visualización)",
)
def ver_embedding(producto_id: int, db: Session = Depends(get_db)):
    """Retorna el vector de embedding para diagnóstico/visualización."""
    import json as _json

    producto = db.query(ProductoProveedor).get(producto_id)
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    vector = None
    dim = 0
    stats = {}
    if producto.embedding_json:
        vector = _json.loads(producto.embedding_json)
        dim = len(vector)
        import math
        vals = [abs(v) for v in vector]
        stats = {
            "dimension": dim,
            "min": round(min(vector), 6),
            "max": round(max(vector), 6),
            "mean": round(sum(vector) / dim, 6),
            "magnitude": round(math.sqrt(sum(v*v for v in vector)), 4),
            "nonzero": sum(1 for v in vector if abs(v) > 1e-8),
        }

    return {
        "producto_id": producto_id,
        "nombre": producto.nombre_raw,
        "proveedor": producto.proveedor.value,
        "texto_embedding": f"{producto.nombre_raw} | Marca: {producto.marca or ''} | Unidad: {producto.unidad or ''} | Proveedor: {producto.proveedor}",
        "tiene_embedding": bool(vector),
        "stats": stats,
        # Solo enviar los primeros 50 valores para no sobrecargar el frontend
        "vector_preview": vector[:50] if vector else [],
        "vector_full_length": dim,
    }


@router.post(
    "/admin/re-comparar/{comparacion_id}",
    summary="Re-ejecutar una comparación específica con el matcher mejorado",
)
async def re_comparar(comparacion_id: int, db: Session = Depends(get_db)):
    """Re-ejecuta el matching IA para una comparación existente."""
    comp = db.query(ComparacionPrecios).get(comparacion_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Comparación no encontrada.")

    prod_a = db.query(ProductoProveedor).get(comp.producto_a_id)
    prod_b = db.query(ProductoProveedor).get(comp.producto_b_id)
    if not prod_a or not prod_b:
        raise HTTPException(status_code=404, detail="Productos de la comparación no encontrados.")

    try:
        resultado = await comparar_productos(prod_a, prod_b, db, query_original="")
        return {
            "comparacion_id": comparacion_id,
            "resultado_anterior": {
                "confidence": comp.confidence_score,
                "razon": comp.razon_ia,
            },
            "resultado_nuevo": {
                "es_match": resultado.es_mismo_producto,
                "confidence": resultado.confidence_score,
                "similitud_coseno": resultado.similitud_coseno,
                "metodo": resultado.metodo,
                "razon": resultado.razon,
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al re-comparar: {exc}")


# ---------------------------------------------------------------------------
# Endpoints: Observabilidad IA — AI Call Logs, Prompts, Lineage
# ---------------------------------------------------------------------------

@router.get(
    "/admin/ai-logs",
    summary="Logs de llamadas IA con filtros",
)
def listar_ai_logs(
    limite: int = 50,
    offset: int = 0,
    call_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Logs de todas las llamadas a servicios de IA (embeddings, LLM, unit_parse)."""
    query = db.query(AICallLog).order_by(AICallLog.created_at.desc())
    if call_type:
        query = query.filter(AICallLog.call_type == call_type)
    total = query.count()
    logs = query.offset(offset).limit(limite).all()
    return {
        "total": total,
        "logs": [{
            "id": l.id,
            "call_type": l.call_type,
            "modelo": l.modelo,
            "prompt_version": l.prompt_version,
            "tokens_input": l.tokens_input,
            "tokens_output": l.tokens_output,
            "latencia_ms": l.latencia_ms,
            "costo_usd": l.costo_usd,
            "exitoso": l.exitoso,
            "error_msg": l.error_msg,
            "input_preview": l.input_preview,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs],
    }


@router.get(
    "/admin/ai-stats",
    summary="Estadísticas agregadas de llamadas IA",
)
def stats_ai_calls(db: Session = Depends(get_db)):
    """Métricas de observabilidad: latencia promedio, costos, tokens."""
    from sqlalchemy import func

    stats_by_type = (
        db.query(
            AICallLog.call_type,
            func.count(AICallLog.id).label("total"),
            func.avg(AICallLog.latencia_ms).label("avg_latencia"),
            func.sum(AICallLog.costo_usd).label("total_costo"),
            func.sum(AICallLog.tokens_input).label("total_tokens_in"),
            func.sum(AICallLog.tokens_output).label("total_tokens_out"),
            func.avg(AICallLog.tokens_input).label("avg_tokens_in"),
        )
        .group_by(AICallLog.call_type)
        .all()
    )

    total_costo = sum(r.total_costo or 0 for r in stats_by_type)
    total_llamadas = sum(r.total or 0 for r in stats_by_type)

    return {
        "total_llamadas": total_llamadas,
        "total_costo_usd": round(total_costo, 6),
        "por_tipo": [{
            "tipo": r.call_type,
            "total": r.total,
            "avg_latencia_ms": round(r.avg_latencia or 0, 2),
            "total_costo_usd": round(r.total_costo or 0, 6),
            "total_tokens_input": r.total_tokens_in or 0,
            "total_tokens_output": r.total_tokens_out or 0,
            "avg_tokens_input": round(r.avg_tokens_in or 0, 0),
        } for r in stats_by_type],
    }


@router.get(
    "/admin/prompts",
    summary="Listar versiones de prompts",
)
def listar_prompts(db: Session = Depends(get_db)):
    """Lista todas las versiones de prompts registradas."""
    prompts = db.query(PromptVersion).order_by(PromptVersion.created_at.desc()).all()
    return [{
        "id": p.id,
        "version_tag": p.version_tag,
        "activo": p.activo,
        "descripcion": p.descripcion,
        "prompt_hash": p.prompt_hash,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    } for p in prompts]


@router.get(
    "/admin/lineage/{comparacion_id}",
    summary="Ver lineage completo de una comparación",
)
def ver_lineage(comparacion_id: int, db: Session = Depends(get_db)):
    """Traza completa del pipeline para una comparación específica."""
    comp = db.query(ComparacionPrecios).get(comparacion_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Comparación no encontrada.")

    lineage = {}
    if comp.lineage_json:
        try:
            lineage = _json.loads(comp.lineage_json)
        except _json.JSONDecodeError:
            lineage = {"raw": comp.lineage_json}

    return {
        "comparacion_id": comparacion_id,
        "prompt_version": comp.prompt_version,
        "modelo_usado": comp.modelo_usado,
        "latencia_total_ms": comp.latencia_total_ms,
        "tokens_totales": comp.tokens_totales,
        "costo_usd": comp.costo_usd,
        "etim_class_code": comp.etim_class_code,
        "confidence_score": comp.confidence_score,
        "lineage": lineage,
    }


def _json_loads_safe(s: Optional[str]) -> list:
    """JSON parse seguro que retorna lista vacía si falla."""
    if not s:
        return []
    try:
        import json as _json
        return _json.loads(s)
    except Exception:
        return []


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