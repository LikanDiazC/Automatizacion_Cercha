from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import uuid 
from typing import List
from core.database import get_db
from . import models, schemas, service
from modulos.inventario.models import Articulo, TipoMaterial

# ¡ESTA ES LA LÍNEA QUE FALTABA! Inicializamos el router del MRP
router = APIRouter(prefix="/api/mrp", tags=["MRP - Lista de Materiales"])

# --- RUTAS DE PRODUCTOS Y COMPONENTES ---

@router.post("/productos", response_model=schemas.ProductoFinalResponse)
def crear_producto(producto: schemas.ProductoFinalCreate, db: Session = Depends(get_db)):
    nuevo_producto = models.ProductoFinal(**producto.model_dump())
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)
    return nuevo_producto

@router.get("/productos", response_model=List[schemas.ProductoFinalResponse])
def obtener_productos(db: Session = Depends(get_db)):
    return db.query(models.ProductoFinal).all()

@router.post("/productos/{producto_id}/componentes", response_model=schemas.ItemBOMResponse)
def agregar_componente_a_mueble(producto_id: int, item: schemas.ItemBOMCreate, db: Session = Depends(get_db)):
    producto = db.query(models.ProductoFinal).filter(models.ProductoFinal.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto final no encontrado")
        
    material = db.query(Articulo).filter(Articulo.id == item.articulo_inventario_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="El artículo de inventario no existe")

    nuevo_componente = models.ItemBOM(
        producto_id=producto_id,
        articulo_inventario_id=item.articulo_inventario_id,
        cantidad_requerida=item.cantidad_requerida
    )
    db.add(nuevo_componente)
    db.commit()
    db.refresh(nuevo_componente)
    return nuevo_componente

# --- RUTA DEL MOTOR DE CORTES (Con guardado de retazos) ---

@router.post("/optimizar-cortes")
def calcular_cortes(solicitud: schemas.SolicitudOptimizacion, db: Session = Depends(get_db)):
    piezas_dict = [pieza.model_dump() for pieza in solicitud.piezas]
    
    # 1. Calculamos los cortes y los retazos [cite: 8, 125, 127]
    resultado = service.optimizar_patron_corte(
        largo_plancha=solicitud.largo_plancha,
        ancho_plancha=solicitud.ancho_plancha,
        lista_piezas=piezas_dict,
        grosor_sierra=solicitud.grosor_sierra
    )
    
    # 2. AUTOMATIZACIÓN DE INVENTARIO: Guardar retazos útiles [cite: 107]
    for plancha in resultado["cortes"]:
        for retazo in plancha["retazos_utiles"]:
            
            codigo_retazo = f"RET-{int(retazo['ancho'])}x{int(retazo['largo'])}-{str(uuid.uuid4())[:4]}"
            retazo["sku"] = codigo_retazo
            
            nuevo_articulo_retazo = Articulo(
                codigo_sku=codigo_retazo,
                nombre=f"Retazo Utilizable {int(retazo['ancho'])}x{int(retazo['largo'])} mm",
                tipo=TipoMaterial.PLANCHA.value,
                unidad_compra="Retazo",
                unidad_almacenamiento=f"Plancha {int(retazo['ancho'])}x{int(retazo['largo'])}",
                unidad_consumo="Metros Cuadrados",
                stock_actual=1.0 
            )
            
            db.add(nuevo_articulo_retazo)
    
    db.commit()
    return resultado
