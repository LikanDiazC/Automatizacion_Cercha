"""Schemas Pydantic del módulo de auth (sólo datos no sensibles)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import OAuthProvider


class UserPublic(BaseModel):
    """Datos del usuario que se devuelven al frontend. NUNCA tokens."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    nombre: Optional[str] = None
    avatar_url: Optional[str] = None
    locale: Optional[str] = None
    oauth_provider: OAuthProvider
    is_admin: bool
    activo: bool
    inbox_sync_enabled: bool
    inbox_last_sync_at: Optional[datetime] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    """Respuesta del endpoint /auth/me y /auth/refresh."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int  # segundos
    user: UserPublic


class LoginUrlResponse(BaseModel):
    """Respuesta de /auth/login/{provider}: URL a la que el frontend debe redirigir."""
    authorize_url: str
