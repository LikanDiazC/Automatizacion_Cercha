from pydantic import BaseModel, Field, field_validator


class ArticuloCreate(BaseModel):
    codigo_sku: str = Field(..., min_length=1, max_length=100)
    nombre: str = Field(..., min_length=1, max_length=200)
    tipo: str = Field(..., pattern="^(Plancha/Tablero|Lineal|Unidad)$")
    unidad_compra: str = Field(..., min_length=1, max_length=50)
    unidad_almacenamiento: str = Field(..., min_length=1, max_length=50)
    unidad_consumo: str = Field(..., min_length=1, max_length=50)
    stock_actual: float = Field(default=0.0, ge=0)

    @field_validator("codigo_sku")
    @classmethod
    def sku_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("El SKU no puede contener espacios")
        return v.upper()


class ArticuloResponse(ArticuloCreate):
    id: int

    class Config:
        from_attributes = True
