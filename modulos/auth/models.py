"""
Modelos de autenticación y seguridad.

- User: identidad del humano (viene de Google o Microsoft).
- OAuthToken: tokens encriptados (Fernet) 1:1 con User.
- SecurityAuditLog: registro inmutable de eventos de seguridad.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from core.database import Base


class OAuthProvider(str, enum.Enum):
    google = "google"
    microsoft = "microsoft"


class AuditEvento(str, enum.Enum):
    login_success = "login_success"
    login_failed = "login_failed"
    logout = "logout"
    token_refresh = "token_refresh"
    oauth_callback_invalid_state = "oauth_callback_invalid_state"
    oauth_callback_error = "oauth_callback_error"
    inbox_sync_started = "inbox_sync_started"
    inbox_sync_failed = "inbox_sync_failed"
    inbox_sync_success = "inbox_sync_success"
    user_disabled = "user_disabled"
    admin_action = "admin_action"
    permission_denied = "permission_denied"


class User(Base):
    __tablename__ = "auth_users"

    id = Column(Integer, primary_key=True, index=True)

    # Identidad estable: (provider, oauth_subject) es la clave verdadera.
    # El email puede cambiar; oauth_subject ("sub" del ID token) NO.
    oauth_provider = Column(Enum(OAuthProvider), nullable=False, index=True)
    oauth_subject  = Column(String(255), nullable=False, index=True)

    # Email es único como conveniencia (login + visualización).
    email   = Column(String(254), nullable=False, unique=True, index=True)
    nombre  = Column(String(200), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    locale  = Column(String(10), nullable=True)

    activo  = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)

    # Sync inbox
    inbox_sync_enabled = Column(Boolean, default=True, nullable=False)
    inbox_last_sync_at = Column(DateTime, nullable=True)
    inbox_last_history_id = Column(String(60), nullable=True)  # Gmail historyId / Graph deltaToken

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)

    token = relationship(
        "OAuthToken",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("oauth_provider", "oauth_subject", name="uq_provider_subject"),
        Index("ix_auth_users_email_lower", "email"),
    )


class OAuthToken(Base):
    """
    Tokens OAuth encriptados con Fernet.
    Nunca exponer access_token_enc/refresh_token_enc por API.
    """
    __tablename__ = "auth_oauth_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("auth_users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    access_token_enc  = Column(Text, nullable=False)
    refresh_token_enc = Column(Text, nullable=True)
    token_type        = Column(String(20), default="Bearer", nullable=False)
    scopes            = Column(Text, nullable=True)  # JSON list serializado
    token_expires_at  = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="token")


class SecurityAuditLog(Base):
    """
    Bitácora inmutable de eventos sensibles. Sólo INSERT, jamás UPDATE/DELETE
    desde la app (las queries del módulo nunca modifican filas existentes).
    """
    __tablename__ = "auth_security_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evento     = Column(Enum(AuditEvento), nullable=False, index=True)
    exitoso    = Column(Boolean, default=True, nullable=False)
    ip         = Column(String(45), nullable=True)   # IPv6 cabe en 45
    user_agent = Column(String(500), nullable=True)
    detalle    = Column(Text, nullable=True)         # JSON breve, ya redactado
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
