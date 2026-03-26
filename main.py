from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # <-- 1. IMPORTA ESTO
from core.database import engine, Base

from modulos.inventario import models as inventario_models
from modulos.mrp import models as mrp_models
from modulos.ordenes import models as ordenes_models
from modulos.inventario import router as inventario_router
from modulos.mrp import router as mrp_router
from modulos.ordenes import router as ordenes_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MRP Manufactura de Muebles",
    description="Sistema de Planificación y Corte",
    version="1.0.0"
)

# --- INICIO MIDDLEWARE DE CORS ---
app.add_middleware(
    CORSMiddleware,
    # Aquí le decimos a Python quiénes pueden entrar:
    allow_origins=[
        "http://localhost:5173",            # Para cuando pruebas en tu PC
        "https://suplee.pages.dev"          # El Pase VIP para Cloudflare
    ],
    allow_credentials=True,
    allow_methods=["*"],                    # Permitir GET, POST, DELETE, etc.
    allow_headers=["*"],
)
# --- FIN MIDDLEWARE DE CORS ---

app.include_router(inventario_router.router)
app.include_router(mrp_router.router)
app.include_router(ordenes_router.router)

@app.get("/")
def ruta_raiz():
    return {"mensaje": "¡El servidor del MRP está en línea y funcionando!"}
