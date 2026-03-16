from pydantic import BaseModel
from typing import List, Optional

# --- Esquemas para los Componentes (ItemBOM) ---
class ItemBOMCreate(BaseModel):
    articulo_inventario_id: int  # El ID del material en tu inventario (ej. 1 para tu MDF)
    cantidad_requerida: float    # Cuánto se necesita para un mueble

class ItemBOMResponse(ItemBOMCreate):
    id: int
    producto_id: int

    class Config:
        from_attributes = True

# --- Esquemas para el Producto Final (Ej. Escritorio) ---
class ProductoFinalCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None

class ProductoFinalResponse(ProductoFinalCreate):
    id: int
    componentes: List[ItemBOMResponse] = [] # Aquí mostraremos la "receta" completa

    class Config:
        from_attributes = True

# --- Esquemas para el Motor de Optimización de Cortes ---

class PiezaCorte(BaseModel):
    id_pieza: str       # Ej: "Lateral Izquierdo"
    largo: float        # En milímetros
    ancho: float        # En milímetros
    cantidad: int       # Cuántas piezas iguales necesitamos

class SolicitudOptimizacion(BaseModel):
    largo_plancha: float       # Ej: 2440 (Largo estándar de un tablero en mm)
    ancho_plancha: float       # Ej: 1220 (Ancho estándar de un tablero en mm)
    grosor_sierra: float = 4.0 # El Kerf (por defecto 4mm)
    piezas: List[PiezaCorte]   # La lista de rectángulos que queremos cortar