"""
Servicio de sincronización de bandeja de entrada OAuth2.

Soporta Gmail API (Google) y Microsoft Graph API (Microsoft 365 / Outlook).

Seguridad crítica:
  - Multi-tenant estricto: TODAS las queries filtran por user_id.
  - HTML sanitizado con bleach (whitelist) antes de guardar.
  - Acceso al provider vía httpx con timeouts y límites explícitos.
  - Tokens OAuth obtenidos vía `get_valid_access_token` (cifrados en DB).
  - Paginación con límite máximo por ciclo (anti-DoS).
  - Clasificación automática de remitentes:
      * dominio personal (gmail/outlook/…) → Contacto "personal"
      * dominio corporativo → Empresa + Contacto vinculado

No usamos google-api-python-client ni msgraph-sdk a propósito: menos
superficie de ataque, dependencias menores y auditoría directa del tráfico.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

import httpx
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.security import sanitize_email_html, extract_domain, is_valid_email
from modulos.auth.models import User, OAuthProvider
from modulos.auth.service import get_valid_access_token

from .models import Empresa, Contacto, EmailInbox

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

# Dominios considerados "personales" (no corporativos). El contacto creado
# NO se asocia a una empresa. Se compara en minúsculas.
DOMINIOS_PERSONALES: frozenset[str] = frozenset({
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.es", "yahoo.com.ar", "yahoo.com.mx",
    "icloud.com", "me.com", "mac.com",
    "proton.me", "protonmail.com",
    "aol.com", "gmx.com", "zoho.com",
    "duck.com", "yandex.com",
})

# Límite por ciclo de sync — evita procesar buzones enormes en una pasada.
MAX_MENSAJES_POR_SYNC = 50

# Timeout duro para llamadas HTTP al provider
HTTP_TIMEOUT = httpx.Timeout(20.0, connect=5.0)

# User-Agent para auditoría en logs del provider
USER_AGENT = "CERCHA-ERP/2.0 (+inbox-sync)"


# ---------------------------------------------------------------------------
# Helpers genéricos
# ---------------------------------------------------------------------------

def _parse_remitente(header_from: str) -> tuple[str, str | None]:
    """
    Parsea un header "Name <email@x.com>" a (email_lower, nombre).
    Devuelve (\"\", None) si no es válido.
    """
    if not header_from:
        return "", None
    nombre, email = parseaddr(header_from)
    email = (email or "").strip().lower()
    nombre = (nombre or "").strip() or None
    if not is_valid_email(email):
        return "", None
    return email, nombre


def _safe_datetime(raw: Any) -> datetime:
    """Parser seguro — cae a utcnow() si falla."""
    if isinstance(raw, datetime):
        return raw.replace(tzinfo=None)
    if isinstance(raw, str):
        try:
            dt = parsedate_to_datetime(raw)
            if dt is not None:
                return dt.replace(tzinfo=None)
        except Exception:
            pass
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            pass
    return datetime.utcnow()


def _truncar(texto: str | None, limite: int) -> str | None:
    if texto is None:
        return None
    texto = str(texto)
    return texto[:limite]


# ---------------------------------------------------------------------------
# Clasificación y upsert de contactos / empresas
# ---------------------------------------------------------------------------

def procesar_remitente_como_contacto(
    db: Session,
    *,
    user_id: int,
    email: str,
    nombre: str | None,
    recibido_at: datetime,
) -> Contacto | None:
    """
    Crea o actualiza un Contacto a partir de un remitente de email.

    Reglas:
      - Si el dominio es personal → Contacto sin empresa (es_personal=True).
      - Si el dominio es corporativo → upsert Empresa por (user_id, dominio)
        y vincula el Contacto a ella.
      - Incrementa frecuencia_emails y actualiza ultimo_email_at.

    Multi-tenant: TODO filtrado por user_id.
    """
    if not is_valid_email(email):
        return None

    email = email.lower()
    dominio = extract_domain(email)
    if not dominio:
        return None

    es_personal = dominio in DOMINIOS_PERSONALES

    # 1) Upsert contacto por (user_id, email)
    contacto = (
        db.query(Contacto)
        .filter(Contacto.user_id == user_id, Contacto.email == email)
        .first()
    )

    empresa: Empresa | None = None
    if not es_personal:
        # 2) Upsert empresa por (user_id, dominio_email)
        empresa = (
            db.query(Empresa)
            .filter(
                Empresa.user_id == user_id,
                Empresa.dominio_email == dominio,
            )
            .first()
        )
        if empresa is None:
            empresa = Empresa(
                user_id=user_id,
                nombre=dominio.split(".")[0].capitalize(),
                dominio_email=dominio,
                origen_inbox=True,
            )
            db.add(empresa)
            db.flush()

    if contacto is None:
        # Parsear nombre/apellido del header
        nombre_clean = (nombre or "").strip()
        if nombre_clean:
            partes = nombre_clean.split(maxsplit=1)
            first = partes[0]
            last = partes[1] if len(partes) > 1 else None
        else:
            first = email.split("@")[0]
            last = None

        contacto = Contacto(
            user_id=user_id,
            empresa_id=empresa.id if empresa else None,
            nombre=_truncar(first, 100) or email,
            apellido=_truncar(last, 100),
            email=email,
            es_personal=es_personal,
            origen_inbox=True,
            frecuencia_emails=1,
            ultimo_email_at=recibido_at,
        )
        db.add(contacto)
        db.flush()
    else:
        contacto.frecuencia_emails = (contacto.frecuencia_emails or 0) + 1
        if contacto.ultimo_email_at is None or recibido_at > contacto.ultimo_email_at:
            contacto.ultimo_email_at = recibido_at
        if empresa and contacto.empresa_id is None:
            contacto.empresa_id = empresa.id
        if nombre and not contacto.apellido and " " in nombre:
            partes = nombre.split(maxsplit=1)
            contacto.nombre = _truncar(partes[0], 100) or contacto.nombre
            contacto.apellido = _truncar(partes[1], 100)

    return contacto


# ---------------------------------------------------------------------------
# Gmail API
# ---------------------------------------------------------------------------

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


async def _gmail_list_message_ids(client: httpx.AsyncClient, token: str) -> list[str]:
    """Lista los IDs de los últimos mensajes en INBOX (sin detalles)."""
    resp = await client.get(
        f"{GMAIL_BASE}/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={"maxResults": MAX_MENSAJES_POR_SYNC, "labelIds": "INBOX"},
    )
    resp.raise_for_status()
    data = resp.json()
    return [m["id"] for m in data.get("messages", []) if m.get("id")]


async def _gmail_fetch_message(client: httpx.AsyncClient, token: str, msg_id: str) -> dict:
    resp = await client.get(
        f"{GMAIL_BASE}/messages/{msg_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"format": "full"},
    )
    resp.raise_for_status()
    return resp.json()


def _gmail_extract_body(payload: dict) -> tuple[str | None, str | None]:
    """
    Recorre las partes MIME del payload Gmail y devuelve (html_raw, text_raw).
    """
    html_raw: str | None = None
    text_raw: str | None = None

    def _walk(part: dict) -> None:
        nonlocal html_raw, text_raw
        mime = part.get("mimeType", "")
        body = part.get("body", {}) or {}
        data = body.get("data")
        if data:
            try:
                decoded = base64.urlsafe_b64decode(data.encode("ascii") + b"==").decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                decoded = None
            if decoded:
                if mime == "text/html" and html_raw is None:
                    html_raw = decoded
                elif mime == "text/plain" and text_raw is None:
                    text_raw = decoded
        for sub in part.get("parts", []) or []:
            _walk(sub)

    _walk(payload or {})
    return html_raw, text_raw


def _gmail_header(headers: list[dict], name: str) -> str:
    name_low = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == name_low:
            return h.get("value") or ""
    return ""


async def _sync_gmail(db: Session, user: User, access_token: str) -> int:
    """Descarga y persiste los últimos mensajes del usuario Gmail."""
    nuevos = 0
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        ids = await _gmail_list_message_ids(client, access_token)
        for msg_id in ids:
            # Idempotencia: skip si ya lo tenemos
            ya = (
                db.query(EmailInbox.id)
                .filter(
                    EmailInbox.user_id == user.id,
                    EmailInbox.message_id_remoto == msg_id,
                )
                .first()
            )
            if ya:
                continue

            try:
                msg = await _gmail_fetch_message(client, access_token, msg_id)
            except httpx.HTTPError as exc:
                logger.warning("gmail fetch falló id=%s: %s", msg_id, exc)
                continue

            payload = msg.get("payload") or {}
            headers = payload.get("headers") or []
            from_hdr = _gmail_header(headers, "From")
            subject = _gmail_header(headers, "Subject")
            to_hdr = _gmail_header(headers, "To")
            cc_hdr = _gmail_header(headers, "Cc")
            date_hdr = _gmail_header(headers, "Date")

            email_from, nombre_from = _parse_remitente(from_hdr)
            if not email_from:
                continue

            html_raw, text_raw = _gmail_extract_body(payload)
            html_safe = sanitize_email_html(html_raw) if html_raw else None

            labels = msg.get("labelIds") or []
            leido = "UNREAD" not in labels
            importante = "IMPORTANT" in labels
            recibido_at = _safe_datetime(date_hdr) or datetime.utcnow()

            contacto = procesar_remitente_como_contacto(
                db,
                user_id=user.id,
                email=email_from,
                nombre=nombre_from,
                recibido_at=recibido_at,
            )

            row = EmailInbox(
                user_id=user.id,
                proveedor="google",
                message_id_remoto=msg_id,
                thread_id_remoto=msg.get("threadId"),
                remitente_email=email_from,
                remitente_nombre=_truncar(nombre_from, 200),
                destinatarios=json.dumps([to_hdr]) if to_hdr else None,
                cc=json.dumps([cc_hdr]) if cc_hdr else None,
                asunto=_truncar(subject, 500),
                snippet=_truncar(msg.get("snippet"), 1000),
                body_html_safe=html_safe,
                body_text=_truncar(text_raw, 200_000),
                leido=leido,
                importante=importante,
                carpeta="inbox",
                labels_json=json.dumps(labels),
                contacto_id=contacto.id if contacto else None,
                recibido_at=recibido_at,
            )
            db.add(row)
            try:
                db.commit()
                nuevos += 1
            except IntegrityError:
                db.rollback()  # race condition idempotente
    return nuevos


# ---------------------------------------------------------------------------
# Microsoft Graph API
# ---------------------------------------------------------------------------

GRAPH_BASE = "https://graph.microsoft.com/v1.0/me"


async def _graph_list_messages(client: httpx.AsyncClient, token: str) -> list[dict]:
    resp = await client.get(
        f"{GRAPH_BASE}/mailFolders/Inbox/messages",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "$top": MAX_MENSAJES_POR_SYNC,
            "$orderby": "receivedDateTime desc",
            "$select": (
                "id,internetMessageId,conversationId,subject,bodyPreview,body,"
                "from,toRecipients,ccRecipients,receivedDateTime,isRead,importance,"
                "categories"
            ),
        },
    )
    resp.raise_for_status()
    return resp.json().get("value", [])


async def _sync_microsoft(db: Session, user: User, access_token: str) -> int:
    nuevos = 0
    async with httpx.AsyncClient(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        try:
            messages = await _graph_list_messages(client, access_token)
        except httpx.HTTPError as exc:
            logger.warning("graph list falló user=%s: %s", user.id, exc)
            return 0

    for m in messages:
        msg_id = m.get("id")
        if not msg_id:
            continue

        ya = (
            db.query(EmailInbox.id)
            .filter(
                EmailInbox.user_id == user.id,
                EmailInbox.message_id_remoto == msg_id,
            )
            .first()
        )
        if ya:
            continue

        from_obj = (m.get("from") or {}).get("emailAddress") or {}
        email_from = (from_obj.get("address") or "").strip().lower()
        nombre_from = from_obj.get("name")
        if not is_valid_email(email_from):
            continue

        body_obj = m.get("body") or {}
        content_type = (body_obj.get("contentType") or "").lower()
        content = body_obj.get("content") or ""
        if content_type == "html":
            html_safe = sanitize_email_html(content) if content else None
            text_raw = None
        else:
            html_safe = None
            text_raw = content

        to_list = [
            (r.get("emailAddress") or {}).get("address", "")
            for r in (m.get("toRecipients") or [])
        ]
        cc_list = [
            (r.get("emailAddress") or {}).get("address", "")
            for r in (m.get("ccRecipients") or [])
        ]

        recibido_at = _safe_datetime(m.get("receivedDateTime")) or datetime.utcnow()

        contacto = procesar_remitente_como_contacto(
            db,
            user_id=user.id,
            email=email_from,
            nombre=nombre_from,
            recibido_at=recibido_at,
        )

        row = EmailInbox(
            user_id=user.id,
            proveedor="microsoft",
            message_id_remoto=msg_id,
            thread_id_remoto=m.get("conversationId"),
            remitente_email=email_from,
            remitente_nombre=_truncar(nombre_from, 200),
            destinatarios=json.dumps([x for x in to_list if x]),
            cc=json.dumps([x for x in cc_list if x]),
            asunto=_truncar(m.get("subject"), 500),
            snippet=_truncar(m.get("bodyPreview"), 1000),
            body_html_safe=html_safe,
            body_text=_truncar(text_raw, 200_000),
            leido=bool(m.get("isRead")),
            importante=(m.get("importance") == "high"),
            carpeta="inbox",
            labels_json=json.dumps(m.get("categories") or []),
            contacto_id=contacto.id if contacto else None,
            recibido_at=recibido_at,
        )
        db.add(row)
        try:
            db.commit()
            nuevos += 1
        except IntegrityError:
            db.rollback()
    return nuevos


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def sincronizar_inbox(db: Session, user: User) -> dict:
    """
    Sincroniza la bandeja de entrada del `user` especificado.

    Devuelve un dict con metadata: {nuevos, total, proveedor, error}.
    NO lanza — siempre devuelve el dict para que el scheduler pueda seguir.
    """
    result = {
        "nuevos": 0,
        "proveedor": user.oauth_provider.value if user.oauth_provider else None,
        "error": None,
    }
    if not user.inbox_sync_enabled:
        result["error"] = "sync_disabled"
        return result
    if not user.activo:
        result["error"] = "user_inactive"
        return result

    try:
        token = await get_valid_access_token(db, user)
    except Exception as exc:
        logger.warning("sincronizar_inbox: no token user=%s err=%s", user.id, exc)
        result["error"] = "no_token"
        return result

    try:
        if user.oauth_provider == OAuthProvider.google:
            result["nuevos"] = await _sync_gmail(db, user, token)
        elif user.oauth_provider == OAuthProvider.microsoft:
            result["nuevos"] = await _sync_microsoft(db, user, token)
        else:
            result["error"] = "provider_unknown"
            return result
    except Exception as exc:
        logger.exception("sincronizar_inbox falló user=%s", user.id)
        result["error"] = str(exc)[:200]
        try:
            db.rollback()
        except Exception:
            pass
        return result

    user.inbox_last_sync_at = datetime.utcnow()
    try:
        db.commit()
    except Exception:
        db.rollback()

    result["total"] = (
        db.query(func.count(EmailInbox.id))
        .filter(EmailInbox.user_id == user.id)
        .scalar()
        or 0
    )
    return result


async def sincronizar_todos_los_usuarios(db: Session) -> dict:
    """
    Llamado por el scheduler. Sincroniza todos los usuarios con sync habilitado.
    """
    resumen = {"ok": 0, "errores": 0, "nuevos_total": 0}
    usuarios = (
        db.query(User)
        .filter(User.activo == True, User.inbox_sync_enabled == True)  # noqa: E712
        .all()
    )
    for u in usuarios:
        r = await sincronizar_inbox(db, u)
        if r.get("error"):
            resumen["errores"] += 1
        else:
            resumen["ok"] += 1
            resumen["nuevos_total"] += r.get("nuevos", 0)
    return resumen
