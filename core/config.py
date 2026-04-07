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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton cacheado — se lee una sola vez al iniciar."""
    return Settings()


settings = get_settings()

# ---------------------------------------------------------------------------
# EXPORTACIÓN DE CONSTANTES (Requeridas por main.py y router.py)
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in settings.allowed_origins.split(",")
    if origin.strip()
]
DEFAULT_PAGE_SIZE = settings.default_page_size
MAX_PAGE_SIZE     = settings.max_page_size
ADMIN_TOKEN       = settings.admin_token   # None si no está en .env
ADMIN_USER        = settings.admin_user    # None si no está en .env