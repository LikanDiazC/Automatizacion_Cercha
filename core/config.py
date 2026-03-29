"""
Configuración centralizada de la aplicación.
NUNCA hardcodear API keys. Siempre usar variables de entorno.

Uso:
    from core.config import settings
    api_key = settings.openai_api_key
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )

    # LLM — usa la variable de entorno LLM_API_KEY
    # Soporta OpenAI o Google Gemini (configurar en ai_matcher.py)
    llm_api_key:    str = ""
    llm_provider:   str = "openai"   # "openai" | "google"
    llm_model:      str = "gpt-4o"

    # Scraping — delays y rotación de UA
    scraper_delay_min: float = 2.0   # segundos entre requests
    scraper_delay_max: float = 5.0
    
    # Admin
    admin_token:    str = "Admin2046"
    admin_user:     str = "Admin2046"
    
    # Base de datos
    database_url:   str = "sqlite:///./mrp_muebles.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton cacheado — se lee una sola vez al iniciar."""
    return Settings()

settings = get_settings()