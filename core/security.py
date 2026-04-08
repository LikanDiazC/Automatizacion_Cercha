"""
Helpers de seguridad centralizados para el ERP Cercha.

Contenido:
- Encriptación simétrica Fernet (AES-128 + HMAC) para tokens OAuth en BD.
- Emisión y verificación de JWT internos (sesión del ERP).
- Helpers PKCE + state aleatorio para flujo OAuth2.
- Sanitización de HTML de correos entrantes (defensa contra XSS).
- Redacción de secretos antes de loguear.
- Middleware de cabeceras de seguridad estándar.
- Validación estricta de formato de email (anti header-injection).

⚠ Reglas de oro:
- NUNCA loguear access_token, refresh_token, code, password ni JWT crudos.
- TODA query que toque tokens/inbox debe filtrar por user_id en el ORM.
- SIEMPRE pasar HTML de correo por `sanitize_email_html` antes de persistir.
- NUNCA construir SQL con f-strings; usar ORM o parámetros bind.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Encriptación simétrica de tokens OAuth (Fernet)
# ---------------------------------------------------------------------------
# Fernet acepta una clave URL-safe base64-encoded de 32 bytes.
# Si el .env no la trae, generamos una efímera y avisamos por logs.

_fernet_singleton: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    global _fernet_singleton
    if _fernet_singleton is not None:
        return _fernet_singleton

    raw = settings.inbox_encryption_key.strip() if settings.inbox_encryption_key else ""

    if not raw:
        # En producción esto es fatal — nunca levantamos con clave efímera.
        if settings.environment.lower() == "production":
            raise RuntimeError(
                "INBOX_ENCRYPTION_KEY es obligatoria en ENVIRONMENT=production. "
                "Genera una con: python -c \"from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())\""
            )
        # ⚠ Modo dev: generar clave efímera. NUNCA persistir nada importante con esto.
        ephemeral = Fernet.generate_key()
        logger.warning(
            "INBOX_ENCRYPTION_KEY no está definida en .env — se generó una clave "
            "efímera SOLO para esta sesión. Los tokens persistidos NO podrán "
            "descifrarse tras un reinicio. Configura INBOX_ENCRYPTION_KEY en .env."
        )
        _fernet_singleton = Fernet(ephemeral)
        return _fernet_singleton

    # Validar formato (Fernet exige 32 bytes base64 url-safe)
    try:
        _fernet_singleton = Fernet(raw.encode() if isinstance(raw, str) else raw)
    except Exception as exc:
        raise RuntimeError(
            "INBOX_ENCRYPTION_KEY tiene formato inválido. Genera una válida con: "
            "python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ) from exc

    return _fernet_singleton


def encrypt_token(plain: str) -> str:
    """Encripta un token y devuelve string ASCII listo para guardar en VARCHAR/TEXT."""
    if plain is None:
        raise ValueError("encrypt_token: plain no puede ser None")
    if not isinstance(plain, str):
        raise TypeError("encrypt_token: plain debe ser str")
    return _get_fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_token(ciphertext: str) -> str:
    """Desencripta un token. Lanza ValueError si está corrupto o la clave cambió."""
    if not ciphertext:
        raise ValueError("decrypt_token: ciphertext vacío")
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Token cifrado inválido o clave Fernet incorrecta") from exc


# ---------------------------------------------------------------------------
# 2. JWT interno del ERP (sesión)
# ---------------------------------------------------------------------------
# Usamos HS256 con un secreto compartido. Si no se setea, generamos uno
# efímero (lo cual invalida tokens emitidos antes de un restart, intencional).

_jwt_secret_singleton: Optional[str] = None


def _get_jwt_secret() -> str:
    global _jwt_secret_singleton
    if _jwt_secret_singleton is not None:
        return _jwt_secret_singleton

    raw = settings.jwt_secret_key.strip() if settings.jwt_secret_key else ""
    if not raw:
        if settings.environment.lower() == "production":
            raise RuntimeError(
                "JWT_SECRET_KEY es obligatoria en ENVIRONMENT=production. "
                "Genera una con: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        ephemeral = secrets.token_urlsafe(64)
        logger.warning(
            "JWT_SECRET_KEY no está definida en .env — se generó una clave efímera. "
            "Los tokens emitidos no sobrevivirán a un reinicio. "
            "Configura JWT_SECRET_KEY en .env (mínimo 64 chars random)."
        )
        _jwt_secret_singleton = ephemeral
        return _jwt_secret_singleton

    if len(raw) < 32:
        raise RuntimeError("JWT_SECRET_KEY debe tener al menos 32 caracteres.")

    _jwt_secret_singleton = raw
    return _jwt_secret_singleton


def create_access_token(user_id: int, email: str, extra: Optional[dict] = None) -> str:
    """Crea un JWT corto (acceso). Sólo lleva campos no sensibles."""
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_access_ttl_min)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if extra:
        # Nunca dejar que extra sobrescriba campos críticos
        for k in ("sub", "exp", "iat", "type", "jti"):
            extra.pop(k, None)
        payload.update(extra)
    return jwt.encode(payload, _get_jwt_secret(), algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int) -> str:
    """Crea un JWT largo para refresh. Va en cookie HttpOnly, no en JS."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.jwt_refresh_ttl_days)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    """
    Valida firma + expiración + tipo. Lanza ValueError si falla.
    Nunca expone el detalle exacto al cliente (lo logueamos).
    """
    try:
        payload = jwt.decode(
            token,
            _get_jwt_secret(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub", "type"]},
        )
    except JWTError as exc:
        logger.debug("decode_token: JWTError %s", exc)
        raise ValueError("Token inválido") from exc

    if payload.get("type") != expected_type:
        raise ValueError("Tipo de token incorrecto")
    return payload


# ---------------------------------------------------------------------------
# 3. PKCE + state para OAuth2
# ---------------------------------------------------------------------------
def generate_oauth_state() -> str:
    """State CSRF: 32 bytes random URL-safe."""
    return secrets.token_urlsafe(32)


def generate_pkce_pair() -> tuple[str, str]:
    """
    Devuelve (code_verifier, code_challenge) usando S256.
    code_verifier: 43-128 chars URL-safe (RFC 7636).
    """
    verifier = secrets.token_urlsafe(64)[:128]
    challenge_bytes = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b"=").decode("ascii")
    return verifier, challenge


# ---------------------------------------------------------------------------
# 4. Sanitización de HTML de correos (anti-XSS)
# ---------------------------------------------------------------------------
# Usamos bleach con whitelist conservadora. Bloqueamos:
# - <script>, <style>, <iframe>, <object>, <embed>, <form>, <input>
# - Atributos on*, javascript:, data:text/html, vbscript:
# - Imágenes externas opcionalmente (configurable luego)

import bleach  # noqa: E402

_ALLOWED_TAGS = frozenset({
    "p", "br", "hr", "div", "span", "blockquote", "pre", "code",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "b", "i", "u", "s", "sub", "sup", "small",
    "ul", "ol", "li",
    "table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
    "a", "img",
    "figure", "figcaption",
})

_ALLOWED_ATTRIBUTES = {
    "*": ["class", "id", "title", "lang", "dir"],
    "a": ["href", "rel", "target"],
    "img": ["src", "alt", "width", "height"],
    "td": ["colspan", "rowspan", "align", "valign"],
    "th": ["colspan", "rowspan", "align", "valign", "scope"],
    "table": ["align", "summary"],
}

# Sólo permitimos protocolos seguros. NO data:, NO javascript:, NO vbscript:.
_ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto", "tel", "cid"})


def sanitize_email_html(html: str | None) -> str:
    """
    Sanitiza HTML de correos entrantes con whitelist estricta.
    Devuelve string vacío si el input es None o vacío.
    """
    if not html:
        return ""
    if not isinstance(html, str):
        return ""

    # Limitar tamaño bruto a 2 MB para evitar DoS por bombas de HTML
    if len(html) > 2 * 1024 * 1024:
        html = html[: 2 * 1024 * 1024]

    cleaned = bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,           # elimina tags no permitidos en lugar de escaparlos
        strip_comments=True,
    )

    # Linkify es opcional — NO lo activamos aquí para no introducir
    # transformaciones inesperadas sobre input ya sanitizado.
    return cleaned


# ---------------------------------------------------------------------------
# 5. Redacción de secretos para logs
# ---------------------------------------------------------------------------
_REDACT_KEYS = {
    "access_token", "refresh_token", "id_token", "code", "code_verifier",
    "client_secret", "password", "token", "authorization", "cookie",
    "set-cookie", "x-admin-token", "jwt",
}


def redact(value: Any) -> Any:
    """
    Devuelve una versión segura para loguear:
    - dict: enmascara valores cuyas keys son sensibles.
    - str largos sospechosos: muestra prefijo+sufijo.
    - otros tipos: pasa tal cual.
    """
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if isinstance(k, str) and k.lower() in _REDACT_KEYS:
                out[k] = "***REDACTED***"
            else:
                out[k] = redact(v)
        return out
    if isinstance(value, (list, tuple)):
        return type(value)(redact(v) for v in value)
    if isinstance(value, str) and len(value) > 40 and " " not in value:
        # heurística: parece un token
        return f"{value[:6]}…{value[-4:]}"
    return value


# ---------------------------------------------------------------------------
# 6. Validación estricta de email
# ---------------------------------------------------------------------------
# RFC 5322 simplificado. Rechazamos saltos de línea (anti header-injection),
# espacios, y caracteres de control.
_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)


def is_valid_email(email: str | None) -> bool:
    if not email or not isinstance(email, str):
        return False
    if len(email) > 254:
        return False
    if any(c in email for c in ("\r", "\n", "\t", " ")):
        return False
    return bool(_EMAIL_RE.match(email))


def extract_domain(email: str) -> str:
    """Devuelve el dominio en lowercase. Asume email ya validado."""
    return email.split("@", 1)[1].strip().lower()


# ---------------------------------------------------------------------------
# 7. Middleware de cabeceras de seguridad
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Añade cabeceras de seguridad estándar a todas las respuestas.
    No incluye CSP estricto porque rompería frontends de dev (Vite HMR).
    En producción se debe agregar CSP en el reverse proxy (nginx/cloudflare).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), microphone=(), camera=(), payment=()",
        )
        # HSTS sólo si estamos detrás de HTTPS (cookie_secure=True es nuestra señal)
        if settings.cookie_secure:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
