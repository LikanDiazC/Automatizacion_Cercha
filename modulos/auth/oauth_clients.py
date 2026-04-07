"""
Clientes OAuth2 manuales para Google y Microsoft.

Implementamos el flujo Authorization Code + PKCE (S256) usando httpx directo,
sin depender de SDKs pesados (google-api-python-client, msgraph-sdk). Esto:
  - Reduce superficie de ataque y dependencias.
  - Permite auditar exactamente qué se envía y recibe.
  - Facilita testeo (httpx es trivial de mockear).

Endpoints fijos (NUNCA dinámicos desde input del usuario):

GOOGLE
  authorize: https://accounts.google.com/o/oauth2/v2/auth
  token:     https://oauth2.googleapis.com/token
  userinfo:  https://openidconnect.googleapis.com/v1/userinfo
  revoke:    https://oauth2.googleapis.com/revoke

MICROSOFT
  authorize: https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize
  token:     https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token
  userinfo:  https://graph.microsoft.com/v1.0/me

Scopes mínimos necesarios:
  Google:    openid email profile https://www.googleapis.com/auth/gmail.readonly
  Microsoft: openid email profile offline_access User.Read Mail.Read
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx

from core.config import settings
from core.security import redact

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes — endpoints fijos
# ---------------------------------------------------------------------------
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL     = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL  = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_REVOKE_URL    = "https://oauth2.googleapis.com/revoke"

GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]

MICROSOFT_SCOPES = [
    "openid",
    "email",
    "profile",
    "offline_access",
    "User.Read",
    "Mail.Read",
]

_HTTP_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


# ---------------------------------------------------------------------------
# Resultados tipados
# ---------------------------------------------------------------------------
@dataclass
class TokenSet:
    access_token: str
    refresh_token: Optional[str]
    expires_in: int
    token_type: str
    scope: str
    id_token: Optional[str] = None


@dataclass
class OAuthUserInfo:
    subject: str          # ID estable del proveedor (NO el email)
    email: str
    nombre: Optional[str]
    avatar_url: Optional[str]
    locale: Optional[str]


# ---------------------------------------------------------------------------
# Helpers de configuración
# ---------------------------------------------------------------------------
def google_configured() -> bool:
    return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)


def microsoft_configured() -> bool:
    return bool(settings.microsoft_oauth_client_id and settings.microsoft_oauth_client_secret)


def _microsoft_authorize_url() -> str:
    return f"https://login.microsoftonline.com/{settings.microsoft_oauth_tenant}/oauth2/v2.0/authorize"


def _microsoft_token_url() -> str:
    return f"https://login.microsoftonline.com/{settings.microsoft_oauth_tenant}/oauth2/v2.0/token"


# ---------------------------------------------------------------------------
# Construcción del authorize URL
# ---------------------------------------------------------------------------
def build_google_authorize_url(state: str, code_challenge: str) -> str:
    if not google_configured():
        raise RuntimeError("Google OAuth no configurado: faltan client_id/secret en .env")
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",   # para obtener refresh_token
        "prompt": "consent",        # forzar consentimiento (asegura refresh_token)
        "include_granted_scopes": "true",
    }
    return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"


def build_microsoft_authorize_url(state: str, code_challenge: str) -> str:
    if not microsoft_configured():
        raise RuntimeError("Microsoft OAuth no configurado: faltan client_id/secret en .env")
    params = {
        "client_id": settings.microsoft_oauth_client_id,
        "redirect_uri": settings.microsoft_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(MICROSOFT_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "response_mode": "query",
        "prompt": "select_account",
    }
    return f"{_microsoft_authorize_url()}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Intercambio code → tokens
# ---------------------------------------------------------------------------
def _parse_token_response(data: dict) -> TokenSet:
    """Mapea respuesta JSON estándar OAuth2 a TokenSet."""
    return TokenSet(
        access_token  = data["access_token"],
        refresh_token = data.get("refresh_token"),
        expires_in    = int(data.get("expires_in", 3600)),
        token_type    = data.get("token_type", "Bearer"),
        scope         = data.get("scope", ""),
        id_token      = data.get("id_token"),
    )


async def exchange_code_google(code: str, code_verifier: str) -> TokenSet:
    if not google_configured():
        raise RuntimeError("Google OAuth no configurado")
    payload = {
        "client_id":     settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "code":          code,
        "code_verifier": code_verifier,
        "grant_type":    "authorization_code",
        "redirect_uri":  settings.google_oauth_redirect_uri,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
    if resp.status_code != 200:
        logger.warning(
            "Google token exchange falló: status=%s body=%s",
            resp.status_code, redact(resp.text[:300]),
        )
        raise ValueError("Intercambio de código con Google falló")
    return _parse_token_response(resp.json())


async def exchange_code_microsoft(code: str, code_verifier: str) -> TokenSet:
    if not microsoft_configured():
        raise RuntimeError("Microsoft OAuth no configurado")
    payload = {
        "client_id":     settings.microsoft_oauth_client_id,
        "client_secret": settings.microsoft_oauth_client_secret,
        "code":          code,
        "code_verifier": code_verifier,
        "grant_type":    "authorization_code",
        "redirect_uri":  settings.microsoft_oauth_redirect_uri,
        "scope":         " ".join(MICROSOFT_SCOPES),
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(_microsoft_token_url(), data=payload)
    if resp.status_code != 200:
        logger.warning(
            "Microsoft token exchange falló: status=%s body=%s",
            resp.status_code, redact(resp.text[:300]),
        )
        raise ValueError("Intercambio de código con Microsoft falló")
    return _parse_token_response(resp.json())


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------
async def refresh_google_token(refresh_token: str) -> TokenSet:
    payload = {
        "client_id":     settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
    if resp.status_code != 200:
        logger.warning("Refresh Google falló: %s", resp.status_code)
        raise ValueError("No se pudo refrescar token Google")
    data = resp.json()
    # Google a veces no devuelve refresh_token nuevo en refresh; se mantiene el viejo.
    if "refresh_token" not in data:
        data["refresh_token"] = refresh_token
    return _parse_token_response(data)


async def refresh_microsoft_token(refresh_token: str) -> TokenSet:
    payload = {
        "client_id":     settings.microsoft_oauth_client_id,
        "client_secret": settings.microsoft_oauth_client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
        "scope":         " ".join(MICROSOFT_SCOPES),
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(_microsoft_token_url(), data=payload)
    if resp.status_code != 200:
        logger.warning("Refresh Microsoft falló: %s", resp.status_code)
        raise ValueError("No se pudo refrescar token Microsoft")
    return _parse_token_response(resp.json())


# ---------------------------------------------------------------------------
# Userinfo
# ---------------------------------------------------------------------------
async def fetch_google_userinfo(access_token: str) -> OAuthUserInfo:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(GOOGLE_USERINFO_URL, headers=headers)
    if resp.status_code != 200:
        raise ValueError(f"Google userinfo falló: {resp.status_code}")
    data = resp.json()
    return OAuthUserInfo(
        subject    = str(data["sub"]),
        email      = data["email"],
        nombre     = data.get("name"),
        avatar_url = data.get("picture"),
        locale     = data.get("locale"),
    )


async def fetch_microsoft_userinfo(access_token: str) -> OAuthUserInfo:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get("https://graph.microsoft.com/v1.0/me", headers=headers)
    if resp.status_code != 200:
        raise ValueError(f"Microsoft Graph /me falló: {resp.status_code}")
    data = resp.json()
    email = data.get("mail") or data.get("userPrincipalName") or ""
    return OAuthUserInfo(
        subject    = str(data["id"]),
        email      = email,
        nombre     = data.get("displayName"),
        avatar_url = None,  # Graph requiere call separada para foto
        locale     = data.get("preferredLanguage"),
    )
