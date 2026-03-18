import json
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from core.database import get_db
from modulos.mrp import service as mrp_service
from modulos.inventario.models import Articulo, TipoMaterial
from . import models, schemas

router = APIRouter(prefix="/api/ordenes", tags=["Órdenes de trabajo"])


DEFAULT_MUEBLES = [
    {
        "nombre": "Mueble de Cocina A20",
        "largo": 1800,
        "ancho": 600,
        "alto": 900,
        "tornillos": 60,
        "pegamento_ml": 150,
        "pintura_ml": 220,
        "perfiles_m": 2.4,
        "piezas": [
            {"id_pieza": "Lateral", "largo": 720, "ancho": 580, "cantidad": 2},
            {"id_pieza": "Base", "largo": 1740, "ancho": 580, "cantidad": 1},
            {"id_pieza": "Repisa", "largo": 1740, "ancho": 500, "cantidad": 1},
            {"id_pieza": "Puerta", "largo": 700, "ancho": 450, "cantidad": 2}
        ]
    },
    {
        "nombre": "Closet Modular C10",
        "largo": 900,
        "ancho": 500,
        "alto": 2100,
        "tornillos": 72,
        "pegamento_ml": 200,
        "pintura_ml": 320,
        "perfiles_m": 4.8,
        "piezas": [
            {"id_pieza": "Lateral", "largo": 2100, "ancho": 500, "cantidad": 2},
            {"id_pieza": "Base", "largo": 860, "ancho": 500, "cantidad": 1},
            {"id_pieza": "Techo", "largo": 860, "ancho": 500, "cantidad": 1},
            {"id_pieza": "Puerta", "largo": 2000, "ancho": 430, "cantidad": 2},
            {"id_pieza": "Repisa", "largo": 860, "ancho": 480, "cantidad": 3}
        ]
    }
]


def seed_muebles(db: Session):
    if db.query(models.Mueble).count() > 0:
        return
    for mueble in DEFAULT_MUEBLES:
        nuevo = models.Mueble(
            nombre=mueble["nombre"],
            largo=mueble["largo"],
            ancho=mueble["ancho"],
            alto=mueble["alto"],
            tornillos=mueble["tornillos"],
            pegamento_ml=mueble["pegamento_ml"],
            pintura_ml=mueble["pintura_ml"],
            perfiles_m=mueble["perfiles_m"],
            piezas_json=json.dumps(mueble["piezas"])
        )
        db.add(nuevo)
    db.commit()


def construir_piezas(mueble: models.Mueble, cantidad: int):
    piezas_base = json.loads(mueble.piezas_json or "[]")
    piezas_orden = []
    for pieza in piezas_base:
        piezas_orden.append({
            "id_pieza": pieza["id_pieza"],
            "largo": pieza["largo"],
            "ancho": pieza["ancho"],
            "cantidad": int(pieza["cantidad"]) * int(cantidad)
        })
    return piezas_orden


def calcular_cortes(piezas_orden, largo_plancha, ancho_plancha, grosor_sierra):
    if not piezas_orden:
        return {"planchas_usadas": 0, "cortes": []}, [], 0

    resultado_cortes = mrp_service.optimizar_patron_corte(
        largo_plancha=largo_plancha,
        ancho_plancha=ancho_plancha,
        lista_piezas=piezas_orden,
        grosor_sierra=grosor_sierra
    )
    retazos_por_plancha = [len(plancha["retazos_utiles"]) for plancha in resultado_cortes["cortes"]]
    retazos_total = sum(retazos_por_plancha)
    return resultado_cortes, retazos_por_plancha, retazos_total


def asignar_skus_retazos(cortes, orden_id: int):
    for plancha_index, plancha in enumerate(cortes, start=1):
        retazos = plancha.get("retazos_utiles", [])
        for retazo_index, retazo in enumerate(retazos, start=1):
            codigo_retazo = (
                f"RET-{orden_id}-P{plancha_index}-R{retazo_index}-"
                f"{int(retazo['ancho'])}x{int(retazo['largo'])}"
            )
            retazo["sku"] = codigo_retazo
    return cortes


def registrar_retazo_en_inventario(db: Session, codigo_retazo: str, retazo):
    if not codigo_retazo:
        return
    existente = db.query(Articulo).filter(Articulo.codigo_sku == codigo_retazo).first()
    if existente:
        return
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


@router.get("/muebles", response_model=list[schemas.MuebleResponse])
def listar_muebles(db: Session = Depends(get_db)):
    seed_muebles(db)
    muebles = db.query(models.Mueble).all()
    respuesta = []
    for mueble in muebles:
        respuesta.append({
            "id": mueble.id,
            "nombre": mueble.nombre,
            "largo": mueble.largo,
            "ancho": mueble.ancho,
            "alto": mueble.alto,
            "tornillos": mueble.tornillos,
            "pegamento_ml": mueble.pegamento_ml,
            "pintura_ml": mueble.pintura_ml,
            "perfiles_m": mueble.perfiles_m,
            "piezas": json.loads(mueble.piezas_json or "[]")
        })
    return respuesta


@router.post("/muebles", response_model=schemas.MuebleResponse)
def crear_mueble(data: schemas.MuebleCreate, db: Session = Depends(get_db)):
    existente = db.query(models.Mueble).filter(models.Mueble.nombre == data.nombre).first()
    if existente:
        raise HTTPException(status_code=400, detail="El mueble ya existe.")

    nuevo = models.Mueble(
        nombre=data.nombre,
        largo=data.largo,
        ancho=data.ancho,
        alto=data.alto,
        tornillos=data.tornillos,
        pegamento_ml=data.pegamento_ml,
        pintura_ml=data.pintura_ml,
        perfiles_m=data.perfiles_m,
        piezas_json=json.dumps([p.model_dump() for p in data.piezas])
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return {
        "id": nuevo.id,
        "nombre": nuevo.nombre,
        "largo": nuevo.largo,
        "ancho": nuevo.ancho,
        "alto": nuevo.alto,
        "tornillos": nuevo.tornillos,
        "pegamento_ml": nuevo.pegamento_ml,
        "pintura_ml": nuevo.pintura_ml,
        "perfiles_m": nuevo.perfiles_m,
        "piezas": json.loads(nuevo.piezas_json or "[]")
    }


@router.post("", response_model=schemas.OrdenResponse)
def crear_orden(data: schemas.OrdenCreate, db: Session = Depends(get_db)):
    mueble = db.query(models.Mueble).filter(models.Mueble.id == data.mueble_id).first()
    if not mueble:
        raise HTTPException(status_code=404, detail="Mueble no encontrado.")

    piezas_orden = construir_piezas(mueble, data.cantidad)
    cortes_total = sum([p["cantidad"] for p in piezas_orden]) if piezas_orden else 0

    resultado_cortes, retazos_por_plancha, retazos_total = calcular_cortes(
        piezas_orden,
        data.largo_plancha,
        data.ancho_plancha,
        data.grosor_sierra
    )

    total_tornillos = mueble.tornillos * data.cantidad
    total_pegamento = mueble.pegamento_ml * data.cantidad
    total_pintura = mueble.pintura_ml * data.cantidad
    total_perfiles = mueble.perfiles_m * data.cantidad

    orden = models.OrdenTrabajo(
        mueble_id=mueble.id,
        cantidad=data.cantidad,
        notas=data.notas,
        largo_plancha=data.largo_plancha,
        ancho_plancha=data.ancho_plancha,
        grosor_sierra=data.grosor_sierra,
        total_tornillos=total_tornillos,
        total_pegamento_ml=total_pegamento,
        total_pintura_ml=total_pintura,
        total_perfiles_m=total_perfiles,
        cortes_total=cortes_total,
        planchas_usadas=resultado_cortes["planchas_usadas"],
        retazos_total=retazos_total,
        retazos_por_plancha_json=json.dumps(retazos_por_plancha)
    )
    db.add(orden)
    db.flush()

    asignar_skus_retazos(resultado_cortes["cortes"], orden.id)

    for plancha in resultado_cortes["cortes"]:
        for retazo in plancha["retazos_utiles"]:
            codigo_retazo = retazo.get("sku") or f"RET-{int(retazo['ancho'])}x{int(retazo['largo'])}-{str(uuid.uuid4())[:4]}"
            registrar_retazo_en_inventario(db, codigo_retazo, retazo)

    db.commit()
    db.refresh(orden)

    return {
        "id": orden.id,
        "mueble_id": mueble.id,
        "mueble_nombre": mueble.nombre,
        "cantidad": orden.cantidad,
        "notas": orden.notas,
        "created_at": orden.created_at,
        "largo_plancha": orden.largo_plancha,
        "ancho_plancha": orden.ancho_plancha,
        "grosor_sierra": orden.grosor_sierra,
        "total_tornillos": total_tornillos,
        "total_pegamento_ml": total_pegamento,
        "total_pintura_ml": total_pintura,
        "total_perfiles_m": total_perfiles,
        "cortes_total": cortes_total,
        "planchas_usadas": resultado_cortes["planchas_usadas"],
        "retazos_total": retazos_total,
        "retazos_por_plancha": retazos_por_plancha,
        "cortes": resultado_cortes["cortes"]
    }


@router.get("", response_model=list[schemas.OrdenResponse])
def listar_ordenes(db: Session = Depends(get_db)):
    ordenes = db.query(models.OrdenTrabajo).order_by(models.OrdenTrabajo.created_at.desc()).all()
    respuesta = []
    for orden in ordenes:
        mueble = db.query(models.Mueble).filter(models.Mueble.id == orden.mueble_id).first()
        respuesta.append({
            "id": orden.id,
            "mueble_id": orden.mueble_id,
            "mueble_nombre": mueble.nombre if mueble else "Desconocido",
            "cantidad": orden.cantidad,
            "notas": orden.notas,
            "created_at": orden.created_at,
            "largo_plancha": orden.largo_plancha,
            "ancho_plancha": orden.ancho_plancha,
            "grosor_sierra": orden.grosor_sierra,
            "total_tornillos": orden.total_tornillos,
            "total_pegamento_ml": orden.total_pegamento_ml,
            "total_pintura_ml": orden.total_pintura_ml,
            "total_perfiles_m": orden.total_perfiles_m,
            "cortes_total": orden.cortes_total,
            "planchas_usadas": orden.planchas_usadas,
            "retazos_total": orden.retazos_total,
            "retazos_por_plancha": json.loads(orden.retazos_por_plancha_json or "[]"),
            "cortes": []
        })
    return respuesta


@router.get("/{orden_id}/cortes")
def obtener_cortes_orden(orden_id: int, db: Session = Depends(get_db)):
    orden = db.query(models.OrdenTrabajo).filter(models.OrdenTrabajo.id == orden_id).first()
    if not orden:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")

    mueble = db.query(models.Mueble).filter(models.Mueble.id == orden.mueble_id).first()
    if not mueble:
        raise HTTPException(status_code=404, detail="Mueble no encontrado.")

    piezas_orden = construir_piezas(mueble, orden.cantidad)
    cortes_total = sum([p["cantidad"] for p in piezas_orden]) if piezas_orden else 0

    resultado_cortes, retazos_por_plancha, retazos_total = calcular_cortes(
        piezas_orden,
        orden.largo_plancha,
        orden.ancho_plancha,
        orden.grosor_sierra
    )
    asignar_skus_retazos(resultado_cortes["cortes"], orden.id)

    for plancha in resultado_cortes["cortes"]:
        for retazo in plancha["retazos_utiles"]:
            registrar_retazo_en_inventario(db, retazo.get("sku"), retazo)

    db.commit()

    return {
        "orden_id": orden.id,
        "mueble_nombre": mueble.nombre,
        "cantidad": orden.cantidad,
        "largo_plancha": orden.largo_plancha,
        "ancho_plancha": orden.ancho_plancha,
        "grosor_sierra": orden.grosor_sierra,
        "cortes_total": cortes_total,
        "planchas_usadas": resultado_cortes["planchas_usadas"],
        "retazos_total": retazos_total,
        "retazos_por_plancha": retazos_por_plancha,
        "cortes": resultado_cortes["cortes"]
    }
