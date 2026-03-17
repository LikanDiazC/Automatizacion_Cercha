import os
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
from core.database import get_db
from . import models, schemas

router = APIRouter(prefix="/api/inventario", tags=["Inventario"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "Admin2046")
ADMIN_USER = os.getenv("ADMIN_USER", "Admin2046")

@router.post("/articulos", response_model=schemas.ArticuloResponse)
def crear_articulo(articulo: schemas.ArticuloCreate, db: Session = Depends(get_db)):
    nuevo_articulo = models.Articulo(**articulo.model_dump())
    db.add(nuevo_articulo)
    
    try:
        db.commit()
        db.refresh(nuevo_articulo)
        return nuevo_articulo
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, 
            detail=f"El artículo con el SKU '{articulo.codigo_sku}' ya existe."
        )

@router.get("/articulos", response_model=List[schemas.ArticuloResponse])
def obtener_articulos(db: Session = Depends(get_db)):
    articulos = db.query(models.Articulo).all()
    return articulos


@router.delete("/articulos/{articulo_id}")
def eliminar_articulo(
    articulo_id: int,
    db: Session = Depends(get_db),
    x_admin_user: str | None = Header(default=None, alias="X-Admin-User"),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    if not x_admin_user or not x_admin_token:
        raise HTTPException(status_code=403, detail="No autorizado: credenciales de admin requeridas.")
    if x_admin_user != ADMIN_USER or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="No autorizado: credenciales de admin inválidas.")

    articulo = db.query(models.Articulo).filter(models.Articulo.id == articulo_id).first()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado.")

    db.delete(articulo)
    db.commit()
    return {"ok": True, "deleted_id": articulo_id, "deleted_by": x_admin_user}
