"""
Servicio de auth: upsert de usuarios, almacenamiento seguro de tokens, audit log.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from core.security import encrypt_token, decrypt_token, redact, is_valid_email
from .models import User, OAuthToken, SecurityAuditLog, OAuthProvider, AuditEvento
from .oauth_clients import (
    OAuthUserInfo,
    TokenSet,
    refresh_google_token,
    refresh_microsoft_token,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def log_audit(
    db: Session,
    *,
    evento: AuditEvento,
    user_id: Optional[int] = None,
    exitoso: bool = True,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    detalle: Optional[dict] = None,
) -> None:
    """
    Inserta una entrada de auditoría. Nunca lanza — auditar nunca debe romper
    el flujo principal. Logueamos en consola si falla.
    """
    try:
        safe_detalle = json.dumps(redact(detalle), default=str)[:2000] if detalle else None
        entry = SecurityAuditLog(
            user_id=user_id,
            evento=evento,
            exitoso=exitoso,
            ip=(ip or "")[:45] or None,
            user_agent=(user_agent or "")[:500] or None,
            detalle=safe_detalle,
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        logger.warning("log_audit falló: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Upsert de usuario tras OAuth callback
# ---------------------------------------------------------------------------
def upsert_user_from_oauth(
    db: Session,
    *,
    provider: OAuthProvider,
    info: OAuthUserInfo,
    tokens: TokenSet,
) -> User:
    """
    Crea o actualiza el User identificado por (provider, subject).
    Encripta y persiste los tokens OAuth.
    El primer usuario que entra al sistema se marca automáticamente como is_admin.
    """
    if not is_valid_email(info.email):
        raise ValueError("OAuth devolvió un email inválido")

    user: Optional[User] = (
        db.query(User)
        .filter(User.oauth_provider == provider, User.oauth_subject == info.subject)
        .first()
    )

    es_primer_usuario = db.query(User).count() == 0

    if user is None:
        user = User(
            oauth_provider=provider,
            oauth_subject=info.subject,
            email=info.email.lower(),
            nombre=info.nombre,
            avatar_url=info.avatar_url,
            locale=info.locale,
            activo=True,
            is_admin=es_primer_usuario,  # primer login → admin
            inbox_sync_enabled=True,
            created_at=datetime.utcnow(),
            last_login_at=datetime.utcnow(),
        )
        db.add(user)
        db.flush()
        logger.info(
            "Nuevo usuario OAuth: id=%s provider=%s admin=%s",
            user.id, provider.value, es_primer_usuario,
        )
    else:
        # Actualizamos campos mutables; NUNCA tocamos id/oauth_subject/provider.
        user.email = info.email.lower()
        if info.nombre:
            user.nombre = info.nombre
        if info.avatar_url:
            user.avatar_url = info.avatar_url
        if info.locale:
            user.locale = info.locale
        user.last_login_at = datetime.utcnow()
        if not user.activo:
            raise PermissionError("Usuario deshabilitado")

    _persist_tokens(db, user, tokens)
    db.commit()
    db.refresh(user)
    return user


def _persist_tokens(db: Session, user: User, tokens: TokenSet) -> None:
    """Encripta y guarda tokens OAuth (1:1 con user)."""
    expires_at = datetime.utcnow() + timedelta(seconds=max(60, tokens.expires_in - 60))

    if user.token is None:
        token_row = OAuthToken(
            user_id=user.id,
            access_token_enc=encrypt_token(tokens.access_token),
            refresh_token_enc=encrypt_token(tokens.refresh_token) if tokens.refresh_token else None,
            token_type=tokens.token_type or "Bearer",
            scopes=json.dumps(tokens.scope.split() if tokens.scope else []),
            token_expires_at=expires_at,
        )
        db.add(token_row)
    else:
        user.token.access_token_enc = encrypt_token(tokens.access_token)
        if tokens.refresh_token:
            user.token.refresh_token_enc = encrypt_token(tokens.refresh_token)
        user.token.token_type = tokens.token_type or "Bearer"
        user.token.scopes = json.dumps(tokens.scope.split() if tokens.scope else [])
        user.token.token_expires_at = expires_at
        user.token.updated_at = datetime.utcnow()


# ---------------------------------------------------------------------------
# Obtener access token válido (refresh automático si expira)
# ---------------------------------------------------------------------------
async def get_valid_access_token(db: Session, user: User) -> str:
    """
    Devuelve un access_token vigente. Si está por expirar (<2 min), lo refresca
    contra el proveedor OAuth correspondiente. Lanza ValueError si no hay
    refresh_token o si el refresh falla (el caller debe pedir reauth).
    """
    if user.token is None:
        raise ValueError("Usuario sin tokens — re-autenticación requerida")

    expires = user.token.token_expires_at
    needs_refresh = (
        expires is None or expires <= datetime.utcnow() + timedelta(minutes=2)
    )

    if not needs_refresh:
        try:
            return decrypt_token(user.token.access_token_enc)
        except ValueError:
            # Token cifrado corrupto → forzar refresh
            needs_refresh = True

    if user.token.refresh_token_enc is None:
        raise ValueError("Sin refresh_token — re-autenticación requerida")

    try:
        refresh_plain = decrypt_token(user.token.refresh_token_enc)
    except ValueError as exc:
        raise ValueError("Refresh token cifrado corrupto") from exc

    if user.oauth_provider == OAuthProvider.google:
        new_tokens = await refresh_google_token(refresh_plain)
    elif user.oauth_provider == OAuthProvider.microsoft:
        new_tokens = await refresh_microsoft_token(refresh_plain)
    else:
        raise ValueError(f"Provider desconocido: {user.oauth_provider}")

    _persist_tokens(db, user, new_tokens)
    db.commit()
    log_audit(db, evento=AuditEvento.token_refresh, user_id=user.id, exitoso=True)
    return new_tokens.access_token
