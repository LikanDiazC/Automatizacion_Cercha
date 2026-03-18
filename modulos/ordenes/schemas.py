from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class PiezaCorte(BaseModel):
    id_pieza: str
    largo: float
    ancho: float
    cantidad: int


class MuebleBase(BaseModel):
    nombre: str
    largo: float
    ancho: float
    alto: float
    tornillos: float = 0.0
    pegamento_ml: float = 0.0
    pintura_ml: float = 0.0
    perfiles_m: float = 0.0
    piezas: List[PiezaCorte] = []


class MuebleCreate(MuebleBase):
    pass


class MuebleResponse(MuebleBase):
    id: int

    class Config:
        from_attributes = True


class OrdenCreate(BaseModel):
    mueble_id: int
    cantidad: int = 1
    notas: Optional[str] = None
    largo_plancha: float = 2440.0
    ancho_plancha: float = 1220.0
    grosor_sierra: float = 4.0


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
    cortes: Optional[list] = None

