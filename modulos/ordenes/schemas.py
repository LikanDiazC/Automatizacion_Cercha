from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class PiezaCorte(BaseModel):
    id_pieza: str = Field(..., min_length=1, max_length=100)
    largo: float = Field(..., gt=0, le=5000)
    ancho: float = Field(..., gt=0, le=5000)
    cantidad: int = Field(..., ge=1, le=500)


class MuebleBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    largo: float = Field(..., gt=0, le=10000)
    ancho: float = Field(..., gt=0, le=10000)
    alto: float = Field(..., gt=0, le=10000)
    tornillos: float = Field(default=0.0, ge=0)
    pegamento_ml: float = Field(default=0.0, ge=0)
    pintura_ml: float = Field(default=0.0, ge=0)
    perfiles_m: float = Field(default=0.0, ge=0)
    piezas: List[PiezaCorte] = []


class MuebleCreate(MuebleBase):
    pass


class MuebleResponse(MuebleBase):
    id: int

    class Config:
        from_attributes = True


class OrdenCreate(BaseModel):
    mueble_id: int = Field(..., gt=0)
    cantidad: int = Field(default=1, ge=1, le=500)
    notas: Optional[str] = Field(default=None, max_length=1000)
    largo_plancha: float = Field(default=2440.0, gt=100, le=10000)
    ancho_plancha: float = Field(default=1220.0, gt=100, le=10000)
    grosor_sierra: float = Field(default=4.0, ge=0.5, le=30)


class OrdenPrioridadUpdate(BaseModel):
    prioridad: int = Field(..., ge=1, le=5)


class OrdenEstadoUpdate(BaseModel):
    estado: str = Field(..., pattern="^(Pendiente|En progreso|Completado|Cancelado)$")


class OrdenResponse(BaseModel):
    id: int
    mueble_id: int
    mueble_nombre: str
    cantidad: int
    notas: Optional[str] = None
    created_at: datetime
    largo_plancha: float
    ancho_plancha: float
    grosor_sierra: float
    total_tornillos: float
    total_pegamento_ml: float
    total_pintura_ml: float
    total_perfiles_m: float
    cortes_total: int
    planchas_usadas: int
    retazos_total: int
    retazos_por_plancha: List[int]
    prioridad: Optional[int] = None
    estado: Optional[str] = None
    cortes: Optional[list] = None
