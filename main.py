from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import ALLOWED_ORIGINS
from core.database import engine, Base

from modulos.inventario import models as inventario_models  # noqa: F401
from modulos.mrp import models as mrp_models  # noqa: F401
from modulos.ordenes import models as ordenes_models  # noqa: F401
from modulos.inventario import router as inventario_router
from modulos.mrp import router as mrp_router
from modulos.ordenes import router as ordenes_router
from modulos.compras import models as compras_models
from modulos.compras import router as compras_router
from modulos.compras import models as compras_models   # noqa: F401 (activa create_all)
from modulos.compras.router import router as compras_router



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    Base.metadata.create_all(bind=engine)
    yield
    # Cleanup on shutdown (nothing needed for SQLite)


app = FastAPI(
    title="MRP Manufactura de Muebles",
    description="Sistema de Planificación y Corte",
    version="2.0.0",
    lifespan=lifespan,
)

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
    # Log the real error server-side; don't leak internals to client
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
app.include_router(compras_router.router)
app.include_router(compras_router)


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "version": app.version}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
