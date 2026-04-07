"""
Router de la bandeja de entrada (inbox) CRM.

Todos los endpoints son multi-tenant: filtran por `current_user.id`.
Requieren autenticación JWT (ver `get_current_user`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from core.database import get_db
from modulos.auth.dependencies import get_current_user
from modulos.auth.models import User

from .models import EmailInbox, Contacto, Empresa
from .inbox_sync_service import sincronizar_inbox

router = APIRouter(prefix="/api/crm/inbox", tags=["CRM Inbox"])


# ---------------------------------------------------------------------------
# Listar mensajes
# ---------------------------------------------------------------------------
@router.get("")
def listar_inbox(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(None, max_length=200, description="Búsqueda por asunto/remitente"),
    solo_no_leidos: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Lista los correos recibidos del usuario actual, ordenados desc."""
    query = db.query(EmailInbox).filter(EmailInbox.user_id == current_user.id)

    if solo_no_leidos:
        query = query.filter(EmailInbox.leido == False)  # noqa: E712

    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            (EmailInbox.asunto.ilike(like))
            | (EmailInbox.remitente_email.ilike(like))
            | (EmailInbox.remitente_nombre.ilike(like))
        )

    total = query.with_entities(func.count(EmailInbox.id)).scalar() or 0

    rows = (
        query.order_by(desc(EmailInbox.recibido_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": r.id,
                "proveedor": r.proveedor,
                "remitente_email": r.remitente_email,
                "remitente_nombre": r.remitente_nombre,
                "asunto": r.asunto,
                "snippet": r.snippet,
                "leido": r.leido,
                "importante": r.importante,
                "recibido_at": r.recibido_at.isoformat() if r.recibido_at else None,
                "contacto_id": r.contacto_id,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# Detalle de un mensaje (incluye body sanitizado)
# ---------------------------------------------------------------------------
@router.get("/{mensaje_id}")
def obtener_mensaje(
    mensaje_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = (
        db.query(EmailInbox)
        .filter(
            EmailInbox.id == mensaje_id,
            EmailInbox.user_id == current_user.id,  # row-level isolation
        )
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")

    # Marcar como leído automáticamente al abrir
    if not r.leido:
        r.leido = True
        db.commit()

    return {
        "id": r.id,
        "proveedor": r.proveedor,
        "thread_id_remoto": r.thread_id_remoto,
        "remitente_email": r.remitente_email,
        "remitente_nombre": r.remitente_nombre,
        "destinatarios": r.destinatarios,
        "cc": r.cc,
        "asunto": r.asunto,
        "snippet": r.snippet,
        "body_html_safe": r.body_html_safe,
        "body_text": r.body_text,
        "leido": r.leido,
        "importante": r.importante,
        "labels_json": r.labels_json,
        "contacto_id": r.contacto_id,
        "recibido_at": r.recibido_at.isoformat() if r.recibido_at else None,
    }


# ---------------------------------------------------------------------------
# Marcar leído / no leído
# ---------------------------------------------------------------------------
@router.patch("/{mensaje_id}/leido")
def marcar_leido(
    mensaje_id: int,
    leido: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    r = (
        db.query(EmailInbox)
        .filter(
            EmailInbox.id == mensaje_id,
            EmailInbox.user_id == current_user.id,
        )
        .first()
    )
    if r is None:
        raise HTTPException(status_code=404, detail="Mensaje no encontrado")
    r.leido = bool(leido)
    db.commit()
    return {"ok": True, "leido": r.leido}


# ---------------------------------------------------------------------------
# Sincronización manual (fuerza un sync ahora)
# ---------------------------------------------------------------------------
@router.post("/sync")
async def sync_inbox_ahora(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fuerza una sincronización inmediata del buzón del usuario actual."""
    resultado = await sincronizar_inbox(db, current_user)
    return resultado


# ---------------------------------------------------------------------------
# Estado del sync (último timestamp, provider, contadores)
# ---------------------------------------------------------------------------
@router.get("/_meta/estado")
def estado_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = (
        db.query(func.count(EmailInbox.id))
        .filter(EmailInbox.user_id == current_user.id)
        .scalar()
        or 0
    )
    no_leidos = (
        db.query(func.count(EmailInbox.id))
        .filter(
            EmailInbox.user_id == current_user.id,
            EmailInbox.leido == False,  # noqa: E712
        )
        .scalar()
        or 0
    )
    return {
        "proveedor": current_user.oauth_provider.value if current_user.oauth_provider else None,
        "email": current_user.email,
        "sync_habilitado": current_user.inbox_sync_enabled,
        "ultimo_sync_at": (
            current_user.inbox_last_sync_at.isoformat()
            if current_user.inbox_last_sync_at
            else None
        ),
        "total": total,
        "no_leidos": no_leidos,
    }


# ---------------------------------------------------------------------------
# Contactos detectados vía inbox
# ---------------------------------------------------------------------------
@router.get("/_meta/contactos-detectados")
def contactos_detectados(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
):
    rows = (
        db.query(Contacto)
        .filter(
            Contacto.user_id == current_user.id,
            Contacto.origen_inbox == True,  # noqa: E712
        )
        .order_by(desc(Contacto.frecuencia_emails))
        .limit(limit)
        .all()
    )
    return [
        {
            "id": c.id,
            "nombre": c.nombre,
            "apellido": c.apellido,
            "email": c.email,
            "es_personal": c.es_personal,
            "frecuencia_emails": c.frecuencia_emails,
            "ultimo_email_at": c.ultimo_email_at.isoformat() if c.ultimo_email_at else None,
            "empresa_id": c.empresa_id,
        }
        for c in rows
    ]


# ---------------------------------------------------------------------------
# Empresas detectadas vía inbox (por dominio corporativo)
# ---------------------------------------------------------------------------
@router.get("/_meta/empresas-detectadas")
def empresas_detectadas(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Empresa)
        .filter(
            Empresa.user_id == current_user.id,
            Empresa.origen_inbox == True,  # noqa: E712
        )
        .order_by(Empresa.nombre)
        .all()
    )
    return [
        {
            "id": e.id,
            "nombre": e.nombre,
            "dominio_email": e.dominio_email,
            "contactos_count": len(e.contactos or []),
        }
        for e in rows
    ]
