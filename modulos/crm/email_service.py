"""
Servicio de email — envío SMTP con tracking de apertura y clicks.

Configuración via .env:
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=tu@gmail.com
  SMTP_PASSWORD=app-password-aqui
  SMTP_FROM_NAME=Cercha ERP
  SMTP_USE_TLS=true
  APP_BASE_URL=http://localhost:8000

Tracking:
  - Pixel de apertura: imagen 1x1 transparente servida por el endpoint
  - Click tracking: links reescritos para pasar por redirect endpoint
"""

import logging
import re
import secrets
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from core.config import settings
from .models import EmailMessage, EstadoEmail, CarpetaEmail, ActividadTimeline, TipoActividad

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuración SMTP (desde settings)
# ---------------------------------------------------------------------------

def _get_smtp_config() -> dict:
    """Lee la config SMTP desde las variables de entorno."""
    return {
        "host": getattr(settings, "smtp_host", ""),
        "port": int(getattr(settings, "smtp_port", 587)),
        "user": getattr(settings, "smtp_user", ""),
        "password": getattr(settings, "smtp_password", ""),
        "from_name": getattr(settings, "smtp_from_name", "Cercha ERP"),
        "use_tls": getattr(settings, "smtp_use_tls", True),
    }


def _get_base_url() -> str:
    return getattr(settings, "app_base_url", "http://localhost:8000")


def smtp_configurado() -> bool:
    """Retorna True si las credenciales SMTP están configuradas."""
    cfg = _get_smtp_config()
    return bool(cfg["host"] and cfg["user"] and cfg["password"])


# ---------------------------------------------------------------------------
# Tracking: pixel + link rewrite
# ---------------------------------------------------------------------------

def _generar_tracking_id() -> str:
    """Genera un ID único para tracking."""
    return secrets.token_urlsafe(32)


def _insertar_pixel_tracking(html: str, tracking_id: str) -> str:
    """
    Inserta un pixel de tracking (imagen 1x1 transparente) antes del </body>.
    Si no hay </body>, lo agrega al final.
    """
    base = _get_base_url()
    pixel = f'<img src="{base}/api/crm/email/track/{tracking_id}/open" width="1" height="1" style="display:none" alt="" />'

    if "</body>" in html.lower():
        # Insertar antes de </body>
        return re.sub(
            r"(</body>)",
            f"{pixel}\\1",
            html,
            flags=re.IGNORECASE,
        )
    return html + pixel


_SAFE_HREF_RE = re.compile(r"^https?://", re.IGNORECASE)


def _reescribir_links(html: str, tracking_id: str) -> str:
    """
    Reemplaza todos los href="..." por redirect a través del tracking endpoint.
    - Excluye mailto:, tel:, #, y links internos de tracking.
    - **Sólo reescribe URLs con protocolo http(s)**. Los demás protocolos
      (javascript:, data:, vbscript:, file:, etc.) se neutralizan
      reemplazándolos por href="#" para prevenir XSS.
    """
    base = _get_base_url()

    def _reemplazar(match):
        url_original = match.group(1).strip()
        lower = url_original.lower()

        # Links seguros que dejamos pasar intactos
        if lower.startswith(("mailto:", "tel:", "#")) or "/track/" in lower:
            return match.group(0)

        # SÓLO http(s) son candidatos a reescritura. Cualquier otro
        # esquema (javascript:, data:, vbscript:, …) se neutraliza.
        if not _SAFE_HREF_RE.match(url_original):
            logger.warning(
                "Link con protocolo no permitido bloqueado en email tracking: %r",
                url_original[:80],
            )
            return 'href="#"'

        encoded = quote(url_original, safe="")
        return f'href="{base}/api/crm/email/track/{tracking_id}/click?url={encoded}"'

    return re.sub(r'href="([^"]+)"', _reemplazar, html, flags=re.IGNORECASE)


# ---------------------------------------------------------------------------
# Envío SMTP
# ---------------------------------------------------------------------------

def _enviar_smtp(
    de_email: str,
    de_nombre: str,
    para_email: str,
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: str,
    cc: Optional[str] = None,
    cco: Optional[str] = None,
) -> None:
    """
    Envía un email via SMTP.
    Lanza Exception si falla.
    """
    cfg = _get_smtp_config()

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{de_nombre} <{de_email}>"
    msg["To"] = para_email
    msg["Subject"] = asunto

    if cc:
        msg["Cc"] = cc

    # Agregar partes
    if cuerpo_texto:
        msg.attach(MIMEText(cuerpo_texto, "plain", "utf-8"))
    if cuerpo_html:
        msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    # Destinatarios reales (To + Cc + Bcc)
    destinatarios = [para_email]
    if cc:
        destinatarios.extend([e.strip() for e in cc.split(",") if e.strip()])
    if cco:
        destinatarios.extend([e.strip() for e in cco.split(",") if e.strip()])

    # Conectar y enviar
    if cfg["use_tls"]:
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(de_email, destinatarios, msg.as_string())
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as server:
            server.ehlo()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(de_email, destinatarios, msg.as_string())


# ---------------------------------------------------------------------------
# API pública del servicio
# ---------------------------------------------------------------------------

def crear_borrador(
    db: Session,
    de_email: str,
    para_email: str,
    asunto: str,
    cuerpo_html: str = "",
    cuerpo_texto: str = "",
    de_nombre: str = "",
    para_nombre: str = "",
    cc: str = "",
    cco: str = "",
    deal_id: Optional[int] = None,
    contacto_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
) -> EmailMessage:
    """Crea un borrador de email sin enviarlo."""
    tracking_id = _generar_tracking_id()

    email = EmailMessage(
        tracking_id=tracking_id,
        de_email=de_email,
        de_nombre=de_nombre or de_email,
        para_email=para_email,
        para_nombre=para_nombre,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
        cc=cc or None,
        cco=cco or None,
        estado=EstadoEmail.BORRADOR,
        carpeta=CarpetaEmail.BORRADORES,
        deal_id=deal_id,
        contacto_id=contacto_id,
        empresa_id=empresa_id,
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    return email


def enviar_email(
    db: Session,
    email_id: Optional[int] = None,
    email_obj: Optional[EmailMessage] = None,
    # Parámetros directos (para enviar sin crear borrador primero)
    de_email: str = "",
    para_email: str = "",
    asunto: str = "",
    cuerpo_html: str = "",
    cuerpo_texto: str = "",
    de_nombre: str = "",
    para_nombre: str = "",
    cc: str = "",
    cco: str = "",
    deal_id: Optional[int] = None,
    contacto_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
) -> EmailMessage:
    """
    Envía un email. Puede recibir un borrador existente o crear uno nuevo.
    Inyecta tracking pixel y reescribe links antes de enviar.
    """
    # Obtener o crear el email
    if email_obj:
        email = email_obj
    elif email_id:
        email = db.query(EmailMessage).filter(EmailMessage.id == email_id).first()
        if not email:
            raise ValueError(f"Email {email_id} no encontrado")
    else:
        # Crear nuevo
        email = crear_borrador(
            db=db,
            de_email=de_email, para_email=para_email,
            asunto=asunto, cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_texto, de_nombre=de_nombre,
            para_nombre=para_nombre, cc=cc, cco=cco,
            deal_id=deal_id, contacto_id=contacto_id,
            empresa_id=empresa_id,
        )

    # Inyectar tracking en el HTML
    html_con_tracking = email.cuerpo_html or ""
    if html_con_tracking:
        html_con_tracking = _insertar_pixel_tracking(html_con_tracking, email.tracking_id)
        html_con_tracking = _reescribir_links(html_con_tracking, email.tracking_id)

    # Intentar enviar
    try:
        cfg = _get_smtp_config()
        _enviar_smtp(
            de_email=cfg["user"] or email.de_email,
            de_nombre=email.de_nombre or cfg["from_name"],
            para_email=email.para_email,
            asunto=email.asunto,
            cuerpo_html=html_con_tracking,
            cuerpo_texto=email.cuerpo_texto or "",
            cc=email.cc,
            cco=email.cco,
        )

        email.estado = EstadoEmail.ENVIADO
        email.carpeta = CarpetaEmail.ENVIADOS
        email.enviado_at = datetime.utcnow()
        email.error_mensaje = None

        logger.info("Email enviado: id=%s para=%s asunto='%s'", email.id, email.para_email, email.asunto)

    except Exception as exc:
        email.estado = EstadoEmail.ERROR
        email.error_mensaje = str(exc)
        logger.error("Error enviando email id=%s: %s", email.id, exc)

    db.commit()
    db.refresh(email)

    # Registrar en timeline del deal si está vinculado
    if email.deal_id and email.estado == EstadoEmail.ENVIADO:
        actividad = ActividadTimeline(
            deal_id=email.deal_id,
            tipo=TipoActividad.EMAIL,
            titulo=f"Email enviado: {email.asunto}",
            contenido=f"Para: {email.para_email}",
            email_asunto=email.asunto,
            email_destinatario=email.para_email,
            usuario="sistema",
        )
        db.add(actividad)
        db.commit()

    return email


def registrar_apertura(db: Session, tracking_id: str) -> bool:
    """Registra que el email fue abierto (pixel tracking)."""
    email = db.query(EmailMessage).filter(EmailMessage.tracking_id == tracking_id).first()
    if not email:
        return False

    email.veces_abierto = (email.veces_abierto or 0) + 1

    if not email.email_abierto:
        email.email_abierto = True
        email.abierto_at = datetime.utcnow()
        email.estado = EstadoEmail.ABIERTO

        # Actualizar timeline del deal
        if email.deal_id:
            actividad = ActividadTimeline(
                deal_id=email.deal_id,
                tipo=TipoActividad.EMAIL,
                titulo=f"Email abierto: {email.asunto}",
                contenido=f"{email.para_email} abrió el email",
                email_asunto=email.asunto,
                email_destinatario=email.para_email,
                email_abierto=True,
                usuario="sistema",
            )
            db.add(actividad)

    db.commit()
    return True


def registrar_click(db: Session, tracking_id: str, url: str) -> bool:
    """Registra que un link del email fue clickeado."""
    email = db.query(EmailMessage).filter(EmailMessage.tracking_id == tracking_id).first()
    if not email:
        return False

    email.veces_clicked = (email.veces_clicked or 0) + 1

    if not email.email_clicked:
        email.email_clicked = True
        email.clicked_at = datetime.utcnow()
        email.estado = EstadoEmail.CLICKED

        if email.deal_id:
            actividad = ActividadTimeline(
                deal_id=email.deal_id,
                tipo=TipoActividad.EMAIL,
                titulo=f"Click en email: {email.asunto}",
                contenido=f"{email.para_email} clickeó un link: {url[:100]}",
                email_asunto=email.asunto,
                email_destinatario=email.para_email,
                email_clicked=True,
                usuario="sistema",
            )
            db.add(actividad)

    db.commit()
    return True


def listar_emails(
    db: Session,
    carpeta: Optional[CarpetaEmail] = None,
    deal_id: Optional[int] = None,
    contacto_id: Optional[int] = None,
    empresa_id: Optional[int] = None,
    limite: int = 50,
) -> list[EmailMessage]:
    """Lista emails filtrados por carpeta o entidad CRM."""
    query = db.query(EmailMessage)

    if carpeta:
        query = query.filter(EmailMessage.carpeta == carpeta)
    if deal_id:
        query = query.filter(EmailMessage.deal_id == deal_id)
    if contacto_id:
        query = query.filter(EmailMessage.contacto_id == contacto_id)
    if empresa_id:
        query = query.filter(EmailMessage.empresa_id == empresa_id)

    return query.order_by(EmailMessage.created_at.desc()).limit(limite).all()


def obtener_email(db: Session, email_id: int) -> Optional[EmailMessage]:
    return db.query(EmailMessage).filter(EmailMessage.id == email_id).first()


def obtener_estadisticas_email(db: Session) -> dict:
    """Métricas de email para el dashboard."""
    from sqlalchemy import func

    total = db.query(func.count(EmailMessage.id)).scalar() or 0
    enviados = db.query(func.count(EmailMessage.id)).filter(
        EmailMessage.estado.in_([EstadoEmail.ENVIADO, EstadoEmail.ABIERTO, EstadoEmail.CLICKED])
    ).scalar() or 0
    abiertos = db.query(func.count(EmailMessage.id)).filter(
        EmailMessage.email_abierto == True
    ).scalar() or 0
    clicked = db.query(func.count(EmailMessage.id)).filter(
        EmailMessage.email_clicked == True
    ).scalar() or 0
    errores = db.query(func.count(EmailMessage.id)).filter(
        EmailMessage.estado == EstadoEmail.ERROR
    ).scalar() or 0
    borradores = db.query(func.count(EmailMessage.id)).filter(
        EmailMessage.estado == EstadoEmail.BORRADOR
    ).scalar() or 0

    tasa_apertura = (abiertos / enviados * 100) if enviados > 0 else 0
    tasa_click = (clicked / enviados * 100) if enviados > 0 else 0

    return {
        "total": total,
        "enviados": enviados,
        "abiertos": abiertos,
        "clicked": clicked,
        "errores": errores,
        "borradores": borradores,
        "tasa_apertura": round(tasa_apertura, 1),
        "tasa_click": round(tasa_click, 1),
    }
