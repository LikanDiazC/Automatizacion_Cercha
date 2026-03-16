from fastapi import FastAPI
from core.database import engine, Base

from modulos.inventario import models as inventario_models
from modulos.mrp import models as mrp_models

from modulos.inventario import router as inventario_router
from modulos.mrp import router as mrp_router # <-- 1. IMPORTA EL NUEVO ROUTER

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MRP Manufactura de Muebles",
    version="1.0.0"
)

app.include_router(inventario_router.router)
app.include_router(mrp_router.router) # <-- 2. CONÉCTALO A LA APLICACIÓN

@app.get("/")
def ruta_raiz():
    return {"mensaje": "¡El servidor del MRP está en línea y funcionando!"}