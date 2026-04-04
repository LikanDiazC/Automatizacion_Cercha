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