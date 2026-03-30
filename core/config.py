"""
Configuración centralizada de la aplicación.
NUNCA hardcodear API keys. Siempre usar variables de entorno.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # 🛡️ Ciberseguridad: Ignora variables extra y evita que crashee
    )

    # LLM
    llm_api_key:    str = ""
    llm_provider:   str = "openai"   # "openai" | "google"
    llm_model:      str = "gpt-4o"

    # Scraping — delays y rotación de UA
    scraper_delay_min: float = 2.0   
    scraper_delay_max: float = 5.0
    
    # Admin
    admin_token:    str = "Admin2046"
    admin_user:     str = "Admin2046"
    
    # Base de datos
    database_url:   str = "sqlite:///./mrp_muebles.db"

    # --- VARIABLES FALTANTES (Añadidas para mapear el .env) ---
    allowed_origins: str = "http://localhost:5173"
    default_page_size: int = 100
    max_page_size: int = 500


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton cacheado — se lee una sola vez al iniciar."""
    return Settings()

settings = get_settings()

# ---------------------------------------------------------------------------
# EXPORTACIÓN DE CONSTANTES (Requeridas por main.py y router.py)
# ---------------------------------------------------------------------------
ALLOWED_ORIGINS = [origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()]
DEFAULT_PAGE_SIZE = settings.default_page_size
MAX_PAGE_SIZE = settings.max_page_size
ADMIN_TOKEN = settings.admin_token
ADMIN_USER = settings.admin_user