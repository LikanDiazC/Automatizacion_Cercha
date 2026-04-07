"""
Router de autenticación OAuth2 (Google + Microsoft) + sesión JWT.

Endpoints:
  GET  /api/auth/login/google         → 302 a Google (con state + PKCE)
  GET  /api/auth/login/microsoft      → 302 a Microsoft (con state + PKCE)
  GET  /api/auth/callback/google      → recibe code, valida, emite JWT
  GET  /api/auth/callback/microsoft   → recibe code, valida, emite JWT
  GET  /api/auth/me                   → datos del usuario logueado
  POST /api/auth/refresh              → nuevo access token desde refresh cookie
  POST /api/auth/logout               → limpia cookies de sesión
  GET  /api/auth/providers            → qué providers están configurados

Cookies emitidas (todas HttpOnly + SameSite):
  cercha_oauth_state     (10 min) — durante el flow OAuth
  cercha_pkce_verifier   (10 min) — durante el flow OAuth
  cercha_oauth_provider  (10 min) — para saber a qué callback volver
  cercha_refresh         (jwt_refresh_ttl_days) — sesión persistente
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.rate_limit import limiter
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_oauth_state,
    generate_pkce_pair,
)

from .dependencies import get_current_user
from .models import AuditEvento, OAuthProvider, User
from .oauth_clients import (
    build_google_authorize_url,
    build_microsoft_authorize_url,
    exchange_code_google,
    exchange_code_microsoft,
    fetch_google_userinfo,
    fetch_microsoft_userinfo,
    google_configured,
    microsoft_configured,
)
from .schemas import TokenResponse, UserPublic
from .service import log_audit, upsert_user_from_oauth

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# ---------------------------------------------------------------------------
# Constantes de cookies
# ---------------------------------------------------------------------------
COOKIE_STATE    = "cercha_oauth_state"
COOKIE_PKCE     = "cercha_pkce_verifier"
COOKIE_PROVIDER = "cercha_oauth_provider"
COOKIE_REFRESH  = "cercha_refresh"
COOKIE_FLOW_TTL = 600  # 10 minutos para completar OAuth flow


def _set_flow_cookie(response: Response, name: str, value: str) -> None:
    response.set_cookie(
        key=name,
        value=value,
        max_age=COOKIE_FLOW_TTL,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/auth",
    )


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=COOKIE_REFRESH,
        value=refresh_token,
        max_age=settings.jwt_refresh_ttl_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/api/auth",
    )


def _clear_cookie(response: Response, name: str, path: str = "/api/auth") -> None:
    response.delete_cookie(key=name, path=path)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "")[:45]


# ---------------------------------------------------------------------------
# /providers — qué métodos de login están disponibles
# ---------------------------------------------------------------------------
@router.get("/providers")
def list_providers():
    return {
        "google":    google_configured(),
        "microsoft": microsoft_configured(),
    }


# ---------------------------------------------------------------------------
# /login/google → 302 a Google
# ---------------------------------------------------------------------------
@router.get("/login/google")
@limiter.limit("10/minute")
def login_google(request: Request):
    if not google_configured():
        raise HTTPException(status_code=503, detail="Google OAuth no configurado")
    state = generate_oauth_state()
    verifier, challenge = generate_pkce_pair()
    auth_url = build_google_authorize_url(state, challenge)

    response = RedirectResponse(url=auth_url, status_code=302)
    _set_flow_cookie(response, COOKIE_STATE, state)
    _set_flow_cookie(response, COOKIE_PKCE, verifier)
    _set_flow_cookie(response, COOKIE_PROVIDER, "google")
    return response


@router.get("/login/microsoft")
@limiter.limit("10/minute")
def login_microsoft(request: Request):
    if not microsoft_configured():
        raise HTTPException(status_code=503, detail="Microsoft OAuth no configurado")
    state = generate_oauth_state()
    verifier, challenge = generate_pkce_pair()
    auth_url = build_microsoft_authorize_url(state, challenge)

    response = RedirectResponse(url=auth_url, status_code=302)
    _set_flow_cookie(response, COOKIE_STATE, state)
    _set_flow_cookie(response, COOKIE_PKCE, verifier)
    _set_flow_cookie(response, COOKIE_PROVIDER, "microsoft")
    return response


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------
async def _handle_callback(
    *,
    request: Request,
    provider: OAuthProvider,
    code: Optional[str],
    state: Optional[str],
    error: Optional[str],
    cookie_state: Optional[str],
    cookie_pkce: Optional[str],
    cookie_provider: Optional[str],
    db: Session,
) -> Response:
    """Lógica común de validación + intercambio + emisión de sesión."""
    failure_redirect = f"{settings.frontend_base_url.rstrip('/')}/login?error="

    # 1) Provider devolvió error explícito
    if error:
        log_audit(db, evento=AuditEvento.oauth_callback_error, exitoso=False,
                  ip=_client_ip(request),
                  user_agent=request.headers.get("user-agent"),
                  detalle={"error": error[:100]})
        return RedirectResponse(url=failure_redirect + "oauth_error", status_code=302)

    # 2) Validar presencia de code y state
    if not code or not state:
        return RedirectResponse(url=failure_redirect + "missing_params", status_code=302)

    # 3) Validar state contra cookie (anti-CSRF)
    if not cookie_state or cookie_state != state:
        log_audit(db, evento=AuditEvento.oauth_callback_invalid_state, exitoso=False,
                  ip=_client_ip(request),
                  user_agent=request.headers.get("user-agent"))
        return RedirectResponse(url=failure_redirect + "invalid_state", status_code=302)

    # 4) Validar provider coincide con el flow iniciado
    if cookie_provider != provider.value:
        return RedirectResponse(url=failure_redirect + "provider_mismatch", status_code=302)

    # 5) PKCE verifier presente
    if not cookie_pkce:
        return RedirectResponse(url=failure_redirect + "missing_verifier", status_code=302)

    # 6) Intercambio code → tokens
    try:
        if provider == OAuthProvider.google:
            tokens = await exchange_code_google(code, cookie_pkce)
            info = await fetch_google_userinfo(tokens.access_token)
        else:
            tokens = await exchange_code_microsoft(code, cookie_pkce)
            info = await fetch_microsoft_userinfo(tokens.access_token)
    except Exception as exc:
        logger.warning("Callback %s error: %s", provider.value, exc)
        log_audit(db, evento=AuditEvento.oauth_callback_error, exitoso=False,
                  ip=_client_ip(request), detalle={"err": str(exc)[:200]})
        return RedirectResponse(url=failure_redirect + "exchange_failed", status_code=302)

    # 7) Upsert user + persistir tokens encriptados
    try:
        user = upsert_user_from_oauth(db, provider=provider, info=info, tokens=tokens)
    except PermissionError:
        log_audit(db, evento=AuditEvento.login_failed, exitoso=False,
                  ip=_client_ip(request), detalle={"reason": "user_disabled"})
        return RedirectResponse(url=failure_redirect + "user_disabled", status_code=302)
    except Exception as exc:
        logger.exception("Upsert user failed: %s", exc)
        return RedirectResponse(url=failure_redirect + "upsert_failed", status_code=302)

    # 8) Emitir JWT + setear cookie de refresh + redirigir a frontend
    refresh = create_refresh_token(user.id)
    redirect_url = f"{settings.frontend_base_url.rstrip('/')}/auth/success"
    response = RedirectResponse(url=redirect_url, status_code=302)
    _set_refresh_cookie(response, refresh)

    # Limpiar cookies del flow
    _clear_cookie(response, COOKIE_STATE)
    _clear_cookie(response, COOKIE_PKCE)
    _clear_cookie(response, COOKIE_PROVIDER)

    log_audit(db, evento=AuditEvento.login_success, user_id=user.id, exitoso=True,
              ip=_client_ip(request),
              user_agent=request.headers.get("user-agent"),
              detalle={"provider": provider.value})
    return response


@router.get("/callback/google")
@limiter.limit("20/minute")
async def callback_google(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    cookie_state: Optional[str] = Cookie(default=None, alias=COOKIE_STATE),
    cookie_pkce: Optional[str] = Cookie(default=None, alias=COOKIE_PKCE),
    cookie_provider: Optional[str] = Cookie(default=None, alias=COOKIE_PROVIDER),
    db: Session = Depends(get_db),
):
    return await _handle_callback(
        request=request, provider=OAuthProvider.google,
        code=code, state=state, error=error,
        cookie_state=cookie_state, cookie_pkce=cookie_pkce, cookie_provider=cookie_provider,
        db=db,
    )


@router.get("/callback/microsoft")
@limiter.limit("20/minute")
async def callback_microsoft(
    request: Request,
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    cookie_state: Optional[str] = Cookie(default=None, alias=COOKIE_STATE),
    cookie_pkce: Optional[str] = Cookie(default=None, alias=COOKIE_PKCE),
    cookie_provider: Optional[str] = Cookie(default=None, alias=COOKIE_PROVIDER),
    db: Session = Depends(get_db),
):
    return await _handle_callback(
        request=request, provider=OAuthProvider.microsoft,
        code=code, state=state, error=error,
        cookie_state=cookie_state, cookie_pkce=cookie_pkce, cookie_provider=cookie_provider,
        db=db,
    )


# ---------------------------------------------------------------------------
# /me — datos del usuario actual
# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)):
    return user


# ---------------------------------------------------------------------------
# /refresh — emite nuevo access_token desde refresh cookie
# ---------------------------------------------------------------------------
@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
def refresh_session(
    request: Request,
    db: Session = Depends(get_db),
    refresh_cookie: Optional[str] = Cookie(default=None, alias=COOKIE_REFRESH),
):
    if not refresh_cookie:
        raise HTTPException(status_code=401, detail="Sin sesión")

    try:
        payload = decode_token(refresh_cookie, expected_type="refresh")
    except ValueError:
        raise HTTPException(status_code=401, detail="Refresh inválido")

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Refresh inválido")

    user: Optional[User] = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no válido")

    access = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=access,
        expires_in=settings.jwt_access_ttl_min * 60,
        user=UserPublic.model_validate(user),
    )


# ---------------------------------------------------------------------------
# /session — obtiene access_token al inicio (igual que refresh, alias semántico)
# ---------------------------------------------------------------------------
@router.get("/session", response_model=TokenResponse)
def get_session(
    request: Request,
    db: Session = Depends(get_db),
    refresh_cookie: Optional[str] = Cookie(default=None, alias=COOKIE_REFRESH),
):
    if not refresh_cookie:
        raise HTTPException(status_code=401, detail="Sin sesión")
    try:
        payload = decode_token(refresh_cookie, expected_type="refresh")
        user_id = int(payload["sub"])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(status_code=401, detail="Sesión inválida")

    user: Optional[User] = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.activo:
        raise HTTPException(status_code=401, detail="Usuario no válido")

    access = create_access_token(user.id, user.email)
    return TokenResponse(
        access_token=access,
        expires_in=settings.jwt_access_ttl_min * 60,
        user=UserPublic.model_validate(user),
    )


# ---------------------------------------------------------------------------
# /logout
# ---------------------------------------------------------------------------
@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    refresh_cookie: Optional[str] = Cookie(default=None, alias=COOKIE_REFRESH),
):
    user_id: Optional[int] = None
    if refresh_cookie:
        try:
            payload = decode_token(refresh_cookie, expected_type="refresh")
            user_id = int(payload.get("sub", 0)) or None
        except Exception:
            pass

    response = JSONResponse(content={"ok": True})
    _clear_cookie(response, COOKIE_REFRESH)
    _clear_cookie(response, COOKIE_STATE)
    _clear_cookie(response, COOKIE_PKCE)
    _clear_cookie(response, COOKIE_PROVIDER)

    if user_id is not None:
        log_audit(db, evento=AuditEvento.logout, user_id=user_id, exitoso=True,
                  ip=_client_ip(request))
    return response
