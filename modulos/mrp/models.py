from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base

class ProductoFinal(Base):
    __tablename__ = "productos_finales"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False) # Ej: "Escritorio L-Shape"
    descripcion = Column(String)
    
    componentes = relationship("ItemBOM", back_populates="producto")

class ItemBOM(Base):
    __tablename__ = "items_bom"

    id = Column(Integer, primary_key=True, index=True)
    
    # Conectamos con el Producto Final
    producto_id = Column(Integer, ForeignKey("productos_finales.id"))
    
    # Conectamos con tu Inventario (busca la tabla articulos)
    articulo_inventario_id = Column(Integer, ForeignKey("articulos.id")) 
    
    # Cantidad necesaria para fabricar el mueble
    cantidad_requerida = Column(Float, nullable=False) 

    producto = relationship("ProductoFinal", back_populates="componentes")