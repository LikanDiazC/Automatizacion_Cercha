from fastapi import APIRouter, Depends, HTTPException, Header, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import update
from typing import List

from core.database import get_db
from core.config import ADMIN_TOKEN, ADMIN_USER, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from . import models, schemas

router = APIRouter(prefix="/api/inventario", tags=["Inventario"])


def _verificar_admin(x_admin_user: str | None, x_admin_token: str | None) -> None:
    """Centralises admin credential check. Raises 403 on failure."""
    if not ADMIN_USER or not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Las credenciales de admin no están configuradas en el servidor.",
        )
    if not x_admin_user or not x_admin_token:
        raise HTTPException(
            status_code=403,
            detail="No autorizado: se requieren credenciales de admin.",
        )
    if x_admin_user != ADMIN_USER or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="No autorizado: credenciales inválidas.",
        )


@router.post("/articulos", response_model=schemas.ArticuloResponse, status_code=201)
def crear_articulo(articulo: schemas.ArticuloCreate, db: Session = Depends(get_db)):
    nuevo = models.Articulo(**articulo.model_dump())
    db.add(nuevo)
    try:
        db.commit()
        db.refresh(nuevo)
        return nuevo
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un artículo con el SKU '{articulo.codigo_sku}'.",
        )


@router.get("/articulos", response_model=List[schemas.ArticuloResponse])
def obtener_articulos(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    tipo: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(models.Articulo)
    if tipo:
        q = q.filter(models.Articulo.tipo == tipo)
    return q.offset(skip).limit(limit).all()


@router.get("/articulos/{articulo_id}", response_model=schemas.ArticuloResponse)
def obtener_articulo(articulo_id: int, db: Session = Depends(get_db)):
    articulo = db.query(models.Articulo).filter(models.Articulo.id == articulo_id).first()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado.")
    return articulo


@router.patch("/articulos/{articulo_id}/stock")
def actualizar_stock(
    articulo_id: int,
    delta: float,
    db: Session = Depends(get_db),
    x_admin_user: str | None = Header(default=None, alias="X-Admin-User"),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _verificar_admin(x_admin_user, x_admin_token)

    # Verificar existencia antes de operar
    articulo = db.query(models.Articulo).filter(models.Articulo.id == articulo_id).first()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado.")

    # Validar que el delta no deje el stock negativo
    if articulo.stock_actual + delta < 0:
        raise HTTPException(status_code=400, detail="El stock no puede quedar negativo.")

    # UPDATE atómico: una sola instrucción SQL sin race condition.
    # Funciona correctamente en SQLite y PostgreSQL.
    db.execute(
        update(models.Articulo)
        .where(models.Articulo.id == articulo_id)
        .values(stock_actual=models.Articulo.stock_actual + delta)
    )
    db.commit()

    # Refrescar para devolver el valor actualizado
    db.refresh(articulo)
    return {"id": articulo_id, "stock_actual": articulo.stock_actual}


@router.delete("/articulos/{articulo_id}")
def eliminar_articulo(
    articulo_id: int,
    db: Session = Depends(get_db),
    x_admin_user: str | None = Header(default=None, alias="X-Admin-User"),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    _verificar_admin(x_admin_user, x_admin_token)
    articulo = db.query(models.Articulo).filter(models.Articulo.id == articulo_id).first()
    if not articulo:
        raise HTTPException(status_code=404, detail="Artículo no encontrado.")
    db.delete(articulo)
    db.commit()
    return {"ok": True, "deleted_id": articulo_id}
