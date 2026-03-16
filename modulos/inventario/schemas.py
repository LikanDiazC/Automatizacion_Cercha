from pydantic import BaseModel

class ArticuloCreate(BaseModel):
    codigo_sku: str
    nombre: str
    tipo: str
    unidad_compra: str
    unidad_almacenamiento: str
    unidad_consumo: str
    stock_actual: float = 0.0

class ArticuloResponse(ArticuloCreate):
    id: int

    class Config:
        from_attributes = True