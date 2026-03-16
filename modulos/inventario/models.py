from sqlalchemy import Column, Integer, String, Float
from core.database import Base
import enum

class TipoMaterial(enum.Enum):
    PLANCHA = "Plancha/Tablero"
    LINEAL = "Lineal"
    UNIDAD = "Unidad"

class Articulo(Base):
    __tablename__ = "articulos"

    id = Column(Integer, primary_key=True, index=True)
    codigo_sku = Column(String, unique=True, index=True)
    nombre = Column(String, nullable=False)
    tipo = Column(String, default=TipoMaterial.PLANCHA.value)
    
    # Las 3 Unidades de Medida Críticas
    unidad_compra = Column(String)       
    unidad_almacenamiento = Column(String) 
    unidad_consumo = Column(String)      
    
    stock_actual = Column(Float, default=0.0)