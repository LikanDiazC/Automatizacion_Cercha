from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from core.database import Base


class Mueble(Base):
    __tablename__ = "muebles"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, unique=True, index=True, nullable=False)
    largo = Column(Float, nullable=False)
    ancho = Column(Float, nullable=False)
    alto = Column(Float, nullable=False)
    tornillos = Column(Float, default=0.0)
    pegamento_ml = Column(Float, default=0.0)
    pintura_ml = Column(Float, default=0.0)
    perfiles_m = Column(Float, default=0.0)
    piezas_json = Column(Text, nullable=False, default="[]")

    ordenes = relationship("OrdenTrabajo", back_populates="mueble")


class OrdenTrabajo(Base):
    __tablename__ = "ordenes_trabajo"

    id = Column(Integer, primary_key=True, index=True)
    mueble_id = Column(Integer, ForeignKey("muebles.id"))
    cantidad = Column(Integer, nullable=False, default=1)
    notas = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    largo_plancha = Column(Float, default=2440.0)
    ancho_plancha = Column(Float, default=1220.0)
    grosor_sierra = Column(Float, default=4.0)

    total_tornillos = Column(Float, default=0.0)
    total_pegamento_ml = Column(Float, default=0.0)
    total_pintura_ml = Column(Float, default=0.0)
    total_perfiles_m = Column(Float, default=0.0)

    cortes_total = Column(Integer, default=0)
    planchas_usadas = Column(Integer, default=0)
    retazos_total = Column(Integer, default=0)
    retazos_por_plancha_json = Column(Text, default="[]")

    mueble = relationship("Mueble", back_populates="ordenes")
