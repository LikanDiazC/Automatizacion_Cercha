"""
Router CRM — Empresas, Contactos, Deals (Kanban), Timeline, Email.

Endpoints:
  /api/crm/empresas       — CRUD empresas
  /api/crm/contactos      — CRUD contactos
  /api/crm/deals          — CRUD deals + pipeline Kanban
  /api/crm/deals/{id}/timeline — Timeline de un deal
  /api/crm/email           — Envío, listado, tracking de correos
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from core.database import get_db

from .models import (
    Empresa, Contacto, Deal, ActividadTimeline,
    EstadoDeal, TipoActividad, CarpetaEmail,
    Tarea, EstadoTarea, PrioridadTarea,
    Llamada, TipoLlamada, ResultadoLlamada,
    PlantillaEmail, Cotizacion, EstadoCotizacion,
)
from .schemas import (
    EmpresaCreate, EmpresaUpdate, EmpresaRead,
    ContactoCreate, ContactoUpdate, ContactoRead,
    DealCreate, DealUpdate, DealRead,
    ActividadCreate, ActividadRead,
    PipelineResumen, DealKanbanColumn,
    EmailCreate, EmailRead, EmailEstadisticas,
    TareaCreate, TareaUpdate, TareaRead,
    LlamadaCreate, LlamadaRead,
    PlantillaCreate, PlantillaUpdate, PlantillaRead,
    CotizacionCreate, CotizacionUpdate, CotizacionRead,
)

router = APIRouter(prefix="/api/crm", tags=["CRM"])


# ===========================================================================
# EMPRESAS
# ===========================================================================

@router.get("/empresas", response_model=list[EmpresaRead])
def listar_empresas(
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Empresa)
    if q:
        query = query.filter(Empresa.nombre.ilike(f"%{q}%"))
    empresas = query.order_by(Empresa.nombre).offset(skip).limit(limit).all()

    resultado = []
    for e in empresas:
        data = EmpresaRead.model_validate(e)
        data.n_contactos = len(e.contactos)
        data.n_deals = len(e.deals)
        resultado.append(data)
    return resultado


@router.post("/empresas", response_model=EmpresaRead, status_code=201)
def crear_empresa(payload: EmpresaCreate, db: Session = Depends(get_db)):
    empresa = Empresa(**payload.model_dump())
    db.add(empresa)
    db.commit()
    db.refresh(empresa)
    return EmpresaRead.model_validate(empresa)


@router.get("/empresas/{empresa_id}", response_model=EmpresaRead)
def obtener_empresa(empresa_id: int, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(404, "Empresa no encontrada")
    data = EmpresaRead.model_validate(empresa)
    data.n_contactos = len(empresa.contactos)
    data.n_deals = len(empresa.deals)
    return data


@router.patch("/empresas/{empresa_id}", response_model=EmpresaRead)
def actualizar_empresa(empresa_id: int, payload: EmpresaUpdate, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(404, "Empresa no encontrada")
    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(empresa, campo, valor)
    db.commit()
    db.refresh(empresa)
    return EmpresaRead.model_validate(empresa)


@router.delete("/empresas/{empresa_id}", status_code=204)
def eliminar_empresa(empresa_id: int, db: Session = Depends(get_db)):
    empresa = db.query(Empresa).filter(Empresa.id == empresa_id).first()
    if not empresa:
        raise HTTPException(404, "Empresa no encontrada")
    db.delete(empresa)
    db.commit()


# ===========================================================================
# CONTACTOS
# ===========================================================================

@router.get("/contactos", response_model=list[ContactoRead])
def listar_contactos(
    q: Optional[str] = None,
    empresa_id: Optional[int] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Contacto).options(joinedload(Contacto.empresa))
    if q:
        query = query.filter(
            (Contacto.nombre.ilike(f"%{q}%")) |
            (Contacto.apellido.ilike(f"%{q}%")) |
            (Contacto.email.ilike(f"%{q}%"))
        )
    if empresa_id:
        query = query.filter(Contacto.empresa_id == empresa_id)
    contactos = query.order_by(Contacto.nombre).offset(skip).limit(limit).all()

    resultado = []
    for c in contactos:
        data = ContactoRead.model_validate(c)
        data.empresa_nombre = c.empresa.nombre if c.empresa else None
        resultado.append(data)
    return resultado


@router.post("/contactos", response_model=ContactoRead, status_code=201)
def crear_contacto(payload: ContactoCreate, db: Session = Depends(get_db)):
    contacto = Contacto(**payload.model_dump())
    db.add(contacto)
    db.commit()
    db.refresh(contacto)
    return ContactoRead.model_validate(contacto)


@router.get("/contactos/{contacto_id}", response_model=ContactoRead)
def obtener_contacto(contacto_id: int, db: Session = Depends(get_db)):
    contacto = db.query(Contacto).options(joinedload(Contacto.empresa)).filter(Contacto.id == contacto_id).first()
    if not contacto:
        raise HTTPException(404, "Contacto no encontrado")
    data = ContactoRead.model_validate(contacto)
    data.empresa_nombre = contacto.empresa.nombre if contacto.empresa else None
    return data


@router.patch("/contactos/{contacto_id}", response_model=ContactoRead)
def actualizar_contacto(contacto_id: int, payload: ContactoUpdate, db: Session = Depends(get_db)):
    contacto = db.query(Contacto).filter(Contacto.id == contacto_id).first()
    if not contacto:
        raise HTTPException(404, "Contacto no encontrado")
    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(contacto, campo, valor)
    db.commit()
    db.refresh(contacto)
    return ContactoRead.model_validate(contacto)


@router.delete("/contactos/{contacto_id}", status_code=204)
def eliminar_contacto(contacto_id: int, db: Session = Depends(get_db)):
    contacto = db.query(Contacto).filter(Contacto.id == contacto_id).first()
    if not contacto:
        raise HTTPException(404, "Contacto no encontrado")
    db.delete(contacto)
    db.commit()


# ===========================================================================
# DEALS (Kanban Pipeline)
# ===========================================================================

@router.get("/deals", response_model=list[DealRead])
def listar_deals(
    estado: Optional[EstadoDeal] = None,
    empresa_id: Optional[int] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Deal).options(
        joinedload(Deal.empresa),
        joinedload(Deal.contacto),
    )
    if estado:
        query = query.filter(Deal.estado == estado)
    if empresa_id:
        query = query.filter(Deal.empresa_id == empresa_id)
    deals = query.order_by(Deal.updated_at.desc()).offset(skip).limit(limit).all()

    resultado = []
    for d in deals:
        data = DealRead.model_validate(d)
        data.empresa_nombre = d.empresa.nombre if d.empresa else None
        data.contacto_nombre = f"{d.contacto.nombre} {d.contacto.apellido or ''}".strip() if d.contacto else None
        resultado.append(data)
    return resultado


@router.get("/deals/pipeline", response_model=list[DealKanbanColumn])
def obtener_pipeline(db: Session = Depends(get_db)):
    """Retorna el pipeline completo para el Kanban board."""
    columnas = []
    for estado in EstadoDeal:
        deals = (
            db.query(Deal)
            .options(joinedload(Deal.empresa), joinedload(Deal.contacto))
            .filter(Deal.estado == estado)
            .order_by(Deal.updated_at.desc())
            .all()
        )
        deals_read = []
        for d in deals:
            data = DealRead.model_validate(d)
            data.empresa_nombre = d.empresa.nombre if d.empresa else None
            data.contacto_nombre = f"{d.contacto.nombre} {d.contacto.apellido or ''}".strip() if d.contacto else None
            deals_read.append(data)

        valor_total = sum(d.valor or 0 for d in deals)
        columnas.append(DealKanbanColumn(
            estado=estado,
            deals=deals_read,
            valor_total=valor_total,
        ))
    return columnas


@router.get("/deals/resumen", response_model=list[PipelineResumen])
def resumen_pipeline(db: Session = Depends(get_db)):
    """Resumen del pipeline para métricas/dashboard."""
    resultados = (
        db.query(
            Deal.estado,
            func.count(Deal.id),
            func.coalesce(func.sum(Deal.valor), 0),
        )
        .group_by(Deal.estado)
        .all()
    )
    return [
        PipelineResumen(estado=estado, cantidad=cantidad, valor_total=valor)
        for estado, cantidad, valor in resultados
    ]


@router.post("/deals", response_model=DealRead, status_code=201)
def crear_deal(payload: DealCreate, db: Session = Depends(get_db)):
    deal = Deal(**payload.model_dump())
    db.add(deal)
    db.commit()
    db.refresh(deal)

    # Crear actividad de timeline automática
    actividad = ActividadTimeline(
        deal_id=deal.id,
        tipo=TipoActividad.SISTEMA,
        titulo="Deal creado",
        contenido=f"Deal '{deal.titulo}' creado en etapa {deal.estado.value}",
        usuario="sistema",
    )
    db.add(actividad)
    db.commit()

    return DealRead.model_validate(deal)


@router.get("/deals/{deal_id}", response_model=DealRead)
def obtener_deal(deal_id: int, db: Session = Depends(get_db)):
    deal = (
        db.query(Deal)
        .options(joinedload(Deal.empresa), joinedload(Deal.contacto))
        .filter(Deal.id == deal_id)
        .first()
    )
    if not deal:
        raise HTTPException(404, "Deal no encontrado")
    data = DealRead.model_validate(deal)
    data.empresa_nombre = deal.empresa.nombre if deal.empresa else None
    data.contacto_nombre = f"{deal.contacto.nombre} {deal.contacto.apellido or ''}".strip() if deal.contacto else None
    return data


@router.patch("/deals/{deal_id}", response_model=DealRead)
def actualizar_deal(deal_id: int, payload: DealUpdate, db: Session = Depends(get_db)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(404, "Deal no encontrado")

    estado_anterior = deal.estado
    datos = payload.model_dump(exclude_unset=True)

    for campo, valor in datos.items():
        setattr(deal, campo, valor)

    # Si cambió de estado → registrar en timeline
    if "estado" in datos and datos["estado"] != estado_anterior:
        nuevo_estado = datos["estado"]
        actividad = ActividadTimeline(
            deal_id=deal.id,
            tipo=TipoActividad.CAMBIO_ESTADO,
            titulo=f"Estado: {estado_anterior.value} → {nuevo_estado.value}",
            estado_anterior=estado_anterior.value,
            estado_nuevo=nuevo_estado.value if isinstance(nuevo_estado, EstadoDeal) else nuevo_estado,
            usuario="sistema",
        )
        db.add(actividad)

        # Si se cerró como ganado/perdido → registrar fecha
        if nuevo_estado in (EstadoDeal.GANADO, EstadoDeal.PERDIDO):
            deal.fecha_cierre_real = datetime.utcnow()

    db.commit()
    db.refresh(deal)
    return DealRead.model_validate(deal)


@router.delete("/deals/{deal_id}", status_code=204)
def eliminar_deal(deal_id: int, db: Session = Depends(get_db)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(404, "Deal no encontrado")
    db.delete(deal)
    db.commit()


# ===========================================================================
# TIMELINE
# ===========================================================================

@router.get("/deals/{deal_id}/timeline", response_model=list[ActividadRead])
def obtener_timeline(deal_id: int, db: Session = Depends(get_db)):
    """Retorna todas las actividades del deal, más recientes primero."""
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(404, "Deal no encontrado")

    actividades = (
        db.query(ActividadTimeline)
        .filter(ActividadTimeline.deal_id == deal_id)
        .order_by(ActividadTimeline.created_at.desc())
        .all()
    )
    return [ActividadRead.model_validate(a) for a in actividades]


@router.post("/deals/{deal_id}/timeline", response_model=ActividadRead, status_code=201)
def agregar_actividad(deal_id: int, payload: ActividadCreate, db: Session = Depends(get_db)):
    deal = db.query(Deal).filter(Deal.id == deal_id).first()
    if not deal:
        raise HTTPException(404, "Deal no encontrado")

    actividad = ActividadTimeline(
        deal_id=deal_id,
        tipo=payload.tipo,
        titulo=payload.titulo,
        contenido=payload.contenido,
        email_asunto=payload.email_asunto,
        email_destinatario=payload.email_destinatario,
        duracion_min=payload.duracion_min,
        estado_anterior=payload.estado_anterior,
        estado_nuevo=payload.estado_nuevo,
        usuario=payload.usuario,
    )
    db.add(actividad)
    db.commit()
    db.refresh(actividad)
    return ActividadRead.model_validate(actividad)


# ===========================================================================
# EMAIL — Envío, listado, tracking
# ===========================================================================

@router.get("/email/config", summary="Verificar configuración SMTP")
def verificar_config_email():
    from .email_service import smtp_configurado, _get_smtp_config
    cfg = _get_smtp_config()
    return {
        "configurado": smtp_configurado(),
        "host": cfg["host"] or "(no configurado)",
        "port": cfg["port"],
        "user": cfg["user"][:3] + "***" if cfg["user"] else "(no configurado)",
        "from_name": cfg["from_name"],
    }


@router.get("/email/estadisticas", response_model=EmailEstadisticas)
def estadisticas_email(db: Session = Depends(get_db)):
    from .email_service import obtener_estadisticas_email
    return obtener_estadisticas_email(db)


@router.get("/email", response_model=list[EmailRead])
def listar_emails_endpoint(
    carpeta: Optional[CarpetaEmail] = None,
    deal_id: Optional[int] = None,
    contacto_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
    limite: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    from .email_service import listar_emails
    emails = listar_emails(
        db, carpeta=carpeta, deal_id=deal_id,
        contacto_id=contacto_id, empresa_id=empresa_id,
        limite=limite,
    )
    return [EmailRead.model_validate(e) for e in emails]


@router.get("/email/{email_id}", response_model=EmailRead)
def obtener_email_endpoint(email_id: int, db: Session = Depends(get_db)):
    from .email_service import obtener_email
    email = obtener_email(db, email_id)
    if not email:
        raise HTTPException(404, "Email no encontrado")
    return EmailRead.model_validate(email)


@router.post("/email/borrador", response_model=EmailRead, status_code=201)
def crear_borrador_endpoint(payload: EmailCreate, db: Session = Depends(get_db)):
    """Crea un borrador de email sin enviarlo."""
    from .email_service import crear_borrador
    from core.config import settings

    email = crear_borrador(
        db=db,
        de_email=getattr(settings, "smtp_user", "noreply@cercha.cl"),
        de_nombre=getattr(settings, "smtp_from_name", "Cercha ERP"),
        para_email=payload.para_email,
        para_nombre=payload.para_nombre or "",
        asunto=payload.asunto,
        cuerpo_html=payload.cuerpo_html,
        cuerpo_texto=payload.cuerpo_texto,
        cc=payload.cc or "",
        cco=payload.cco or "",
        deal_id=payload.deal_id,
        contacto_id=payload.contacto_id,
        empresa_id=payload.empresa_id,
    )
    return EmailRead.model_validate(email)


@router.post("/email/enviar", response_model=EmailRead, status_code=201)
def enviar_email_endpoint(payload: EmailCreate, db: Session = Depends(get_db)):
    """Crea y envía un email directamente."""
    from .email_service import enviar_email, smtp_configurado
    from core.config import settings

    email = enviar_email(
        db=db,
        de_email=getattr(settings, "smtp_user", "noreply@cercha.cl"),
        de_nombre=getattr(settings, "smtp_from_name", "Cercha ERP"),
        para_email=payload.para_email,
        para_nombre=payload.para_nombre or "",
        asunto=payload.asunto,
        cuerpo_html=payload.cuerpo_html,
        cuerpo_texto=payload.cuerpo_texto,
        cc=payload.cc or "",
        cco=payload.cco or "",
        deal_id=payload.deal_id,
        contacto_id=payload.contacto_id,
        empresa_id=payload.empresa_id,
    )
    return EmailRead.model_validate(email)


@router.post("/email/{email_id}/enviar", response_model=EmailRead)
def enviar_borrador_endpoint(email_id: int, db: Session = Depends(get_db)):
    """Envía un borrador existente."""
    from .email_service import enviar_email
    email = enviar_email(db=db, email_id=email_id)
    return EmailRead.model_validate(email)


@router.delete("/email/{email_id}", status_code=204)
def eliminar_email_endpoint(email_id: int, db: Session = Depends(get_db)):
    from .models import EmailMessage
    email = db.query(EmailMessage).filter(EmailMessage.id == email_id).first()
    if not email:
        raise HTTPException(404, "Email no encontrado")
    db.delete(email)
    db.commit()


# ---------------------------------------------------------------------------
# Tracking endpoints (pixel de apertura + redirect de clicks)
# ---------------------------------------------------------------------------

# Pixel transparente 1x1 GIF
_PIXEL_GIF = bytes([
    0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00,
    0x80, 0x00, 0x00, 0xff, 0xff, 0xff, 0x00, 0x00, 0x00, 0x21,
    0xf9, 0x04, 0x01, 0x00, 0x00, 0x00, 0x00, 0x2c, 0x00, 0x00,
    0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x02, 0x02, 0x44,
    0x01, 0x00, 0x3b,
])


@router.get("/email/track/{tracking_id}/open", include_in_schema=False)
def track_apertura(tracking_id: str, db: Session = Depends(get_db)):
    """Pixel de tracking — registra apertura y retorna imagen 1x1 transparente."""
    from .email_service import registrar_apertura
    registrar_apertura(db, tracking_id)
    return Response(
        content=_PIXEL_GIF,
        media_type="image/gif",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/email/track/{tracking_id}/click", include_in_schema=False)
def track_click(tracking_id: str, url: str, db: Session = Depends(get_db)):
    """Click tracking — registra click y redirige al URL original."""
    from .email_service import registrar_click
    registrar_click(db, tracking_id, url)
    # Validar que el URL es seguro (no javascript:, data:, etc.)
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL inválida")
    return RedirectResponse(url=url, status_code=302)


# ===========================================================================
# TAREAS
# ===========================================================================

@router.get("/tareas", response_model=list[TareaRead])
def listar_tareas(
    estado: Optional[EstadoTarea] = None,
    prioridad: Optional[PrioridadTarea] = None,
    asignado_a: Optional[str] = None,
    deal_id: Optional[int] = None,
    contacto_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Tarea)
    if estado:
        query = query.filter(Tarea.estado == estado)
    if prioridad:
        query = query.filter(Tarea.prioridad == prioridad)
    if asignado_a:
        query = query.filter(Tarea.asignado_a.ilike(f"%{asignado_a}%"))
    if deal_id:
        query = query.filter(Tarea.deal_id == deal_id)
    if contacto_id:
        query = query.filter(Tarea.contacto_id == contacto_id)
    if empresa_id:
        query = query.filter(Tarea.empresa_id == empresa_id)

    tareas = query.order_by(Tarea.fecha_vencimiento.asc().nullslast(), Tarea.created_at.desc()).offset(skip).limit(limit).all()

    resultado = []
    for t in tareas:
        data = TareaRead.model_validate(t)
        # Campos computados
        if t.deal:
            data.deal_titulo = t.deal.titulo
        if t.contacto:
            data.contacto_nombre = f"{t.contacto.nombre} {t.contacto.apellido or ''}".strip()
        if t.empresa:
            data.empresa_nombre = t.empresa.nombre
        if t.fecha_vencimiento and not t.completada_at:
            data.vencida = t.fecha_vencimiento < datetime.utcnow()
        resultado.append(data)
    return resultado


@router.post("/tareas", response_model=TareaRead, status_code=201)
def crear_tarea(payload: TareaCreate, db: Session = Depends(get_db)):
    tarea = Tarea(**payload.model_dump())
    db.add(tarea)
    db.commit()
    db.refresh(tarea)
    return TareaRead.model_validate(tarea)


@router.get("/tareas/{tarea_id}", response_model=TareaRead)
def obtener_tarea(tarea_id: int, db: Session = Depends(get_db)):
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id).first()
    if not tarea:
        raise HTTPException(404, "Tarea no encontrada")
    data = TareaRead.model_validate(tarea)
    if tarea.deal:
        data.deal_titulo = tarea.deal.titulo
    if tarea.contacto:
        data.contacto_nombre = f"{tarea.contacto.nombre} {tarea.contacto.apellido or ''}".strip()
    if tarea.empresa:
        data.empresa_nombre = tarea.empresa.nombre
    if tarea.fecha_vencimiento and not tarea.completada_at:
        data.vencida = tarea.fecha_vencimiento < datetime.utcnow()
    return data


@router.patch("/tareas/{tarea_id}", response_model=TareaRead)
def actualizar_tarea(tarea_id: int, payload: TareaUpdate, db: Session = Depends(get_db)):
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id).first()
    if not tarea:
        raise HTTPException(404, "Tarea no encontrada")

    datos = payload.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        setattr(tarea, campo, valor)

    # Si se marca como completada, registrar fecha
    if "estado" in datos and datos["estado"] == EstadoTarea.COMPLETADA and not tarea.completada_at:
        tarea.completada_at = datetime.utcnow()
    # Si se reabre, limpiar fecha completada
    elif "estado" in datos and datos["estado"] != EstadoTarea.COMPLETADA:
        tarea.completada_at = None

    db.commit()
    db.refresh(tarea)
    return TareaRead.model_validate(tarea)


@router.delete("/tareas/{tarea_id}", status_code=204)
def eliminar_tarea(tarea_id: int, db: Session = Depends(get_db)):
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id).first()
    if not tarea:
        raise HTTPException(404, "Tarea no encontrada")
    db.delete(tarea)
    db.commit()


# ===========================================================================
# LLAMADAS
# ===========================================================================

@router.get("/llamadas", response_model=list[LlamadaRead])
def listar_llamadas(
    tipo: Optional[TipoLlamada] = None,
    resultado: Optional[ResultadoLlamada] = None,
    deal_id: Optional[int] = None,
    contacto_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Llamada)
    if tipo:
        query = query.filter(Llamada.tipo == tipo)
    if resultado:
        query = query.filter(Llamada.resultado == resultado)
    if deal_id:
        query = query.filter(Llamada.deal_id == deal_id)
    if contacto_id:
        query = query.filter(Llamada.contacto_id == contacto_id)
    if empresa_id:
        query = query.filter(Llamada.empresa_id == empresa_id)

    llamadas = query.order_by(Llamada.created_at.desc()).offset(skip).limit(limit).all()

    resultado_list = []
    for ll in llamadas:
        data = LlamadaRead.model_validate(ll)
        if ll.contacto:
            data.contacto_nombre = f"{ll.contacto.nombre} {ll.contacto.apellido or ''}".strip()
        if ll.empresa:
            data.empresa_nombre = ll.empresa.nombre
        resultado_list.append(data)
    return resultado_list


@router.post("/llamadas", response_model=LlamadaRead, status_code=201)
def crear_llamada(payload: LlamadaCreate, db: Session = Depends(get_db)):
    llamada = Llamada(**payload.model_dump())
    db.add(llamada)
    db.commit()
    db.refresh(llamada)

    # Si tiene deal_id, registrar en timeline
    if llamada.deal_id:
        tipo_texto = "entrante" if llamada.tipo == TipoLlamada.ENTRANTE else "saliente"
        actividad = ActividadTimeline(
            deal_id=llamada.deal_id,
            tipo=TipoActividad.LLAMADA,
            titulo=f"Llamada {tipo_texto}",
            contenido=llamada.notas or "",
            duracion_min=(llamada.duracion_seg or 0) // 60,
            usuario="sistema",
        )
        db.add(actividad)
        db.commit()

    return LlamadaRead.model_validate(llamada)


@router.get("/llamadas/{llamada_id}", response_model=LlamadaRead)
def obtener_llamada(llamada_id: int, db: Session = Depends(get_db)):
    llamada = db.query(Llamada).filter(Llamada.id == llamada_id).first()
    if not llamada:
        raise HTTPException(404, "Llamada no encontrada")
    data = LlamadaRead.model_validate(llamada)
    if llamada.contacto:
        data.contacto_nombre = f"{llamada.contacto.nombre} {llamada.contacto.apellido or ''}".strip()
    if llamada.empresa:
        data.empresa_nombre = llamada.empresa.nombre
    return data


@router.delete("/llamadas/{llamada_id}", status_code=204)
def eliminar_llamada(llamada_id: int, db: Session = Depends(get_db)):
    llamada = db.query(Llamada).filter(Llamada.id == llamada_id).first()
    if not llamada:
        raise HTTPException(404, "Llamada no encontrada")
    db.delete(llamada)
    db.commit()


# ===========================================================================
# PLANTILLAS DE EMAIL
# ===========================================================================

@router.get("/plantillas", response_model=list[PlantillaRead])
def listar_plantillas(
    q: Optional[str] = None,
    categoria: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(PlantillaEmail)
    if q:
        query = query.filter(PlantillaEmail.nombre.ilike(f"%{q}%"))
    if categoria:
        query = query.filter(PlantillaEmail.categoria == categoria)
    return query.order_by(PlantillaEmail.nombre).offset(skip).limit(limit).all()


@router.post("/plantillas", response_model=PlantillaRead, status_code=201)
def crear_plantilla(payload: PlantillaCreate, db: Session = Depends(get_db)):
    plantilla = PlantillaEmail(**payload.model_dump())
    db.add(plantilla)
    db.commit()
    db.refresh(plantilla)
    return PlantillaRead.model_validate(plantilla)


@router.get("/plantillas/{plantilla_id}", response_model=PlantillaRead)
def obtener_plantilla(plantilla_id: int, db: Session = Depends(get_db)):
    plantilla = db.query(PlantillaEmail).filter(PlantillaEmail.id == plantilla_id).first()
    if not plantilla:
        raise HTTPException(404, "Plantilla no encontrada")
    return PlantillaRead.model_validate(plantilla)


@router.patch("/plantillas/{plantilla_id}", response_model=PlantillaRead)
def actualizar_plantilla(plantilla_id: int, payload: PlantillaUpdate, db: Session = Depends(get_db)):
    plantilla = db.query(PlantillaEmail).filter(PlantillaEmail.id == plantilla_id).first()
    if not plantilla:
        raise HTTPException(404, "Plantilla no encontrada")
    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(plantilla, campo, valor)
    db.commit()
    db.refresh(plantilla)
    return PlantillaRead.model_validate(plantilla)


@router.delete("/plantillas/{plantilla_id}", status_code=204)
def eliminar_plantilla(plantilla_id: int, db: Session = Depends(get_db)):
    plantilla = db.query(PlantillaEmail).filter(PlantillaEmail.id == plantilla_id).first()
    if not plantilla:
        raise HTTPException(404, "Plantilla no encontrada")
    db.delete(plantilla)
    db.commit()


# ===========================================================================
# COTIZACIONES
# ===========================================================================

@router.get("/cotizaciones", response_model=list[CotizacionRead])
def listar_cotizaciones(
    estado: Optional[EstadoCotizacion] = None,
    deal_id: Optional[int] = None,
    contacto_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
    skip: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Cotizacion)
    if estado:
        query = query.filter(Cotizacion.estado == estado)
    if deal_id:
        query = query.filter(Cotizacion.deal_id == deal_id)
    if contacto_id:
        query = query.filter(Cotizacion.contacto_id == contacto_id)
    if empresa_id:
        query = query.filter(Cotizacion.empresa_id == empresa_id)

    cotizaciones = query.order_by(Cotizacion.created_at.desc()).offset(skip).limit(limit).all()

    resultado = []
    for c in cotizaciones:
        data = CotizacionRead.model_validate(c)
        if c.deal:
            data.deal_titulo = c.deal.titulo
        if c.contacto:
            data.contacto_nombre = f"{c.contacto.nombre} {c.contacto.apellido or ''}".strip()
        if c.empresa:
            data.empresa_nombre = c.empresa.nombre
        resultado.append(data)
    return resultado


@router.post("/cotizaciones", response_model=CotizacionRead, status_code=201)
def crear_cotizacion(payload: CotizacionCreate, db: Session = Depends(get_db)):
    import json

    # Calcular totales
    items_data = [item.model_dump() for item in payload.items]
    for item in items_data:
        item["total"] = item["cantidad"] * item["precio_unitario"]

    subtotal = sum(item["total"] for item in items_data)
    descuento = subtotal * (payload.descuento_pct / 100)
    base_iva = subtotal - descuento
    iva = base_iva * (payload.iva_pct / 100)
    total = base_iva + iva

    # Generar número único
    count = db.query(func.count(Cotizacion.id)).scalar() or 0
    numero = f"COT-{count + 1:05d}"

    cotizacion = Cotizacion(
        numero=numero,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        items_json=json.dumps(items_data, ensure_ascii=False),
        subtotal=round(subtotal, 2),
        descuento_pct=payload.descuento_pct,
        iva_pct=payload.iva_pct,
        total=round(total, 2),
        moneda=payload.moneda,
        notas=payload.notas,
        fecha_emision=datetime.utcnow(),
        fecha_expiracion=payload.fecha_expiracion,
        deal_id=payload.deal_id,
        contacto_id=payload.contacto_id,
        empresa_id=payload.empresa_id,
    )
    db.add(cotizacion)
    db.commit()
    db.refresh(cotizacion)
    return CotizacionRead.model_validate(cotizacion)


@router.get("/cotizaciones/{cotizacion_id}", response_model=CotizacionRead)
def obtener_cotizacion(cotizacion_id: int, db: Session = Depends(get_db)):
    cotizacion = db.query(Cotizacion).filter(Cotizacion.id == cotizacion_id).first()
    if not cotizacion:
        raise HTTPException(404, "Cotización no encontrada")
    data = CotizacionRead.model_validate(cotizacion)
    if cotizacion.deal:
        data.deal_titulo = cotizacion.deal.titulo
    if cotizacion.contacto:
        data.contacto_nombre = f"{cotizacion.contacto.nombre} {cotizacion.contacto.apellido or ''}".strip()
    if cotizacion.empresa:
        data.empresa_nombre = cotizacion.empresa.nombre
    return data


@router.patch("/cotizaciones/{cotizacion_id}", response_model=CotizacionRead)
def actualizar_cotizacion(cotizacion_id: int, payload: CotizacionUpdate, db: Session = Depends(get_db)):
    import json

    cotizacion = db.query(Cotizacion).filter(Cotizacion.id == cotizacion_id).first()
    if not cotizacion:
        raise HTTPException(404, "Cotización no encontrada")

    datos = payload.model_dump(exclude_unset=True)

    # Si se actualizan items, recalcular totales
    if "items" in datos and datos["items"] is not None:
        items_data = [item.model_dump() if hasattr(item, "model_dump") else item for item in datos["items"]]
        for item in items_data:
            item["total"] = item["cantidad"] * item["precio_unitario"]
        cotizacion.items_json = json.dumps(items_data, ensure_ascii=False)
        subtotal = sum(item["total"] for item in items_data)
        cotizacion.subtotal = round(subtotal, 2)
        del datos["items"]

        # Recalcular total con descuento e IVA
        desc_pct = datos.get("descuento_pct", cotizacion.descuento_pct)
        iva_pct = datos.get("iva_pct", cotizacion.iva_pct)
        descuento = cotizacion.subtotal * (desc_pct / 100)
        base_iva = cotizacion.subtotal - descuento
        iva = base_iva * (iva_pct / 100)
        cotizacion.total = round(base_iva + iva, 2)

    for campo, valor in datos.items():
        setattr(cotizacion, campo, valor)

    db.commit()
    db.refresh(cotizacion)
    return CotizacionRead.model_validate(cotizacion)


@router.delete("/cotizaciones/{cotizacion_id}", status_code=204)
def eliminar_cotizacion(cotizacion_id: int, db: Session = Depends(get_db)):
    cotizacion = db.query(Cotizacion).filter(Cotizacion.id == cotizacion_id).first()
    if not cotizacion:
        raise HTTPException(404, "Cotización no encontrada")
    db.delete(cotizacion)
    db.commit()
