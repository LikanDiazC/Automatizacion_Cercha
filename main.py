from contextlib import asynccontextmanager
import sys
import asyncio
import logging
import warnings

# --- FIX PARA PLAYWRIGHT EN WINDOWS ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.config import ALLOWED_ORIGINS, settings
from core.database import engine, Base
from core.rate_limit import limiter

from modulos.inventario import models as inventario_models  # noqa: F401
from modulos.mrp import models as mrp_models  # noqa: F401
from modulos.ordenes import models as ordenes_models  # noqa: F401
from modulos.inventario import router as inventario_router
from modulos.mrp import router as mrp_router
from modulos.ordenes import router as ordenes_router
from modulos.compras import models as compras_models
from modulos.compras.router import router as compras_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Advertencia de seguridad si las credenciales de admin no están configuradas
    if not settings.admin_user or not settings.admin_token:
        warnings.warn(
            "\n"
            "=" * 70 + "\n"
            "⚠️  SEGURIDAD: ADMIN_USER y ADMIN_TOKEN no están configurados.\n"
            "   Las operaciones de administración (stock, eliminación) devolverán 503.\n"
            "   Configura estas variables en tu archivo .env para habilitarlas.\n"
            "=" * 70,
            stacklevel=2,
        )
        logger.warning("Admin credentials not configured — admin endpoints disabled.")

    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="MRP Manufactura de Muebles",
    description="Sistema de Planificación y Corte",
    version="2.0.0",
    lifespan=lifespan,
    # Ocultar docs en producción si se desea: docs_url=None, redoc_url=None
)

# --- Rate Limiting ---
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Global exception handlers ---
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor. Consulta los logs."},
    )


# --- Routers ---
app.include_router(inventario_router.router)
app.include_router(mrp_router.router)
app.include_router(ordenes_router.router)
app.include_router(compras_router)


# Información mínima — sin revelar el stack tecnológico completo
@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "version": app.version}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}

# ---------------------------------------------------------------------------
# ARRANQUE DIRECTO (Bypass para el error de Playwright en Windows)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    import sys
    import asyncio

    # 1. Forzamos la política ANTES de que Uvicorn exista
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    # 2. Arrancamos Uvicorn pasando el objeto 'app' directamente y SIN reload
    # (El reload crea subprocesos que rompen a Playwright en Windows)
    uvicorn.run(app, host="127.0.0.1", port=8000)