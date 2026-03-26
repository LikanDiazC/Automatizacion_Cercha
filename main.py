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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # El "*" significa "Dejar entrar a todos" (luego lo cambiaremos por tu dominio)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- INICIO MIDDLEWARE DE CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","https://suplee.pages.dev"], # Le damos permiso específico a tu frontend de React
    allow_credentials=True,
    allow_methods=["*"], # Permite GET, POST, PUT, DELETE
    allow_headers=["*"],
)
# --- FIN MIDDLEWARE DE CORS ---

app.include_router(inventario_router.router)
app.include_router(mrp_router.router)
app.include_router(ordenes_router.router)

@app.get("/")
def ruta_raiz():
    return {"mensaje": "¡El servidor del MRP está en línea y funcionando!"}
