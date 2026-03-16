from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List
from core.database import get_db
from . import models, schemas

router = APIRouter(prefix="/api/inventario", tags=["Inventario"])

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