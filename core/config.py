import os

# --- Auth ---
# REQUIRED: set these in your environment or .env file
# Never commit real values to source control
ADMIN_USER: str = os.getenv("ADMIN_USER", "")
ADMIN_TOKEN: str = os.getenv("ADMIN_TOKEN", "")

# Warn loudly at startup if not set
if not ADMIN_USER or not ADMIN_TOKEN:
    import warnings
    warnings.warn(
        "ADMIN_USER / ADMIN_TOKEN are not set via environment variables. "
        "Admin endpoints will reject all requests until they are configured.",
        stacklevel=1,
    )

# --- CORS ---
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,https://suplee.pages.dev",
)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# --- Rate limiting (requests per minute per IP) ---
RATE_LIMIT_ORDENES: str = os.getenv("RATE_LIMIT_ORDENES", "20/minute")
RATE_LIMIT_INVENTARIO: str = os.getenv("RATE_LIMIT_INVENTARIO", "60/minute")

# --- Pagination defaults ---
DEFAULT_PAGE_SIZE: int = int(os.getenv("DEFAULT_PAGE_SIZE", "100"))
MAX_PAGE_SIZE: int = int(os.getenv("MAX_PAGE_SIZE", "500"))
