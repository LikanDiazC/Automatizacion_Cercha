"""
Configuración centralizada de la aplicación.
NUNCA hardcodear API keys ni credenciales. Siempre usar variables de entorno.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignora variables extra — evita que crashee con vars desconocidas
    )

    # LLM
    llm_api_key:    str = ""
    llm_provider:   str = "openai"   # "openai" | "google"
    llm_model:      str = "gpt-4o"

    # Scraping — delays y rotación de UA
    scraper_delay_min: float = 2.0
    scraper_delay_max: float = 5.0

    # Admin — SIN valores por defecto: si no está en .env, devuelve None.
    # Esto hace que _verificar_admin() retorne 503 en lugar de aceptar
    # credenciales conocidas públicamente.
    admin_token:    Optional[str] = None
    admin_user:     Optional[str] = None

    # Base de datos
    database_url:   str = "sqlite:///./mrp_muebles.db"

    # CORS y paginación
    allowed_origins:    str = "http://localhost:5173"
    default_page_size:  int = 100
    max_page_size:      int = 500

    # Scheduler de sync de precios
    sync_intervalo_horas: int = 6
    sync_hora_inicio:     int = 7
    sync_habilitado:      bool = True

    # SMTP — Email service
    smtp_host:      str = ""
    smtp_port:      int = 587
    smtp_user:      str = ""
    smtp_password:  str = ""
    smtp_from_name: str = "Cercha ERP"
    smtp_use_tls:   bool = True
    app_base_url:   str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"

    # ── OAuth2 — Google ──
    google_oauth_client_id:     str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri:  str = "http://localhost:8000/api/auth/callback/google"

    # ── OAuth2 — Microsoft ──
    microsoft_oauth_client_id:     str = ""
    microsoft_oauth_client_secret: str = ""
    microsoft_oauth_tenant:        str = "common"  # "common" acepta personal + work
    microsoft_oauth_redirect_uri:  str = "http://localhost:8000/api/auth/callback/microsoft"

    # ── JWT (sesión interna del ERP) ──
    # Si no se setea, se autogenera al inicio (NO recomendado para prod, pero
    # útil en dev para no romper el arranque). En prod hay que setearlo.
    jwt_secret_key:        str = ""
    jwt_algorithm:         str = "HS256"
    jwt_access_ttl_min:    int = 15
    jwt_refresh_ttl_days:  int = 30

    # ── Encriptación de tokens OAuth en BD (Fernet AES-128) ──
    inbox_encryption_key:  str = ""

    # ── Inbox sync ──
    inbox_sync_enabled:           bool = True
    inbox_sync_intervalo_minutos: int  = 10
    inbox_sync_limite_por_run:    int  = 100

    # ── Cookies / seguridad ──
    cookie_secure:    bool = False  # ⚠ True en producción (requiere HTTPS)
    cookie_samesite:  str  = "lax"  # "lax" | "strict" | "none"
    cookie_domain:    str  = ""

    # ── Entorno / deployment ──
    # "development" | "staging" | "production"
    # En "production": las claves críticas (JWT, Fernet) son OBLIGATORIAS,
    # se valida que ALLOWED_ORIGINS no tenga http://, se bloquea SQLite, etc.
    environment:   str = "development"

    # Whitelist de emails que pueden ser admin (CSV). Si vacío → nadie
    # se marca admin automáticamente (hay que activarlo a mano en BD).
    admin_emails:  str = ""


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton cacheado — se lee una sola vez al iniciar."""
    return Settings()


settings = get_settings()

# ---------------------------------------------------------------------------
# EXPORTACIÓN DE CONSTANTES (Requeridas por main.py y router.py)
# ---------------------------------------------------------------------------
def _parse_allowed_origins(raw: str, is_production: bool) -> list[str]:
    """
    Valida y parsea ALLOWED_ORIGINS.
    - Rechaza entradas vacías o mal formadas.
    - En producción exige scheme HTTPS y host válido.
    """
    from urllib.parse import urlparse

    origins: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parsed = urlparse(item)
        if not parsed.scheme or not parsed.netloc:
            import warnings
            warnings.warn(f"ALLOWED_ORIGINS ignorado (mal formado): {item}", stacklevel=2)
            continue
        if is_production and parsed.scheme != "https":
            raise RuntimeError(
                f"ENVIRONMENT=production pero ALLOWED_ORIGINS contiene origen no-HTTPS: {item}"
            )
        if parsed.scheme not in ("http", "https"):
            import warnings
            warnings.warn(f"ALLOWED_ORIGINS scheme no http/https: {item}", stacklevel=2)
            continue
        origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return origins


IS_PRODUCTION = settings.environment.lower() == "production"

ALLOWED_ORIGINS = _parse_allowed_origins(settings.allowed_origins, IS_PRODUCTION)

DEFAULT_PAGE_SIZE = settings.default_page_size
MAX_PAGE_SIZE     = settings.max_page_size
ADMIN_TOKEN       = settings.admin_token   # None si no está en .env
ADMIN_USER        = settings.admin_user    # None si no está en .env

# Whitelist de emails con auto-admin (lowercased)
ADMIN_EMAILS = frozenset(
    e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()
)