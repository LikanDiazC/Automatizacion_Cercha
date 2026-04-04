"""
Modelos SQLAlchemy para el módulo de Compras Inteligentes.

NOTA DE MIGRACIÓN:
  - Actualmente usa SQLite. El campo `embedding_json` debe reemplazarse
    por `Vector(1536)` de pgvector al migrar a PostgreSQL.
  - Comando de migración futura:
      ALTER TABLE productos_proveedor
        ADD COLUMN embedding vector(1536);
      CREATE INDEX ON productos_proveedor
        USING hnsw (embedding vector_cosine_ops);
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text,
    Boolean, DateTime, ForeignKey, Enum as SAEnum, Index,
)
from sqlalchemy.orm import relationship
import enum

from core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NombreProveedor(str, enum.Enum):
    """
    Proveedores soportados. Extender aquí antes de agregar un scraper nuevo.
    Nunca usar strings literales en el código — siempre referenciar este enum.
    """
    SODIMAC = "Sodimac"
    EASY    = "Easy"
    # CONSTRUMART = "Construmart"  # Ejemplo de expansión futura


class EstadoCarrito(str, enum.Enum):
    ACTIVO    = "activo"
    PROCESADO = "procesado"
    ARCHIVADO = "archivado"


class EstadoScraping(str, enum.Enum):
    PENDIENTE = "pendiente"
    EXITO     = "exito"
    BLOQUEADO = "bloqueado"   # WAF/bot-detection activado
    ERROR     = "error"


# ---------------------------------------------------------------------------
# ProductoProveedor
# ---------------------------------------------------------------------------

class ProductoProveedor(Base):
    """
    Snapshot de un producto tal como fue raspado de un proveedor externo.
    
    Cada fila representa UN producto en UNA tienda en UN momento en el tiempo.
    No se modifica después de creado — si el precio cambia, se crea una nueva fila.
    
    Seguridad: imagen_url se valida en el schema (HttpUrl) antes de persistir.
    """
    __tablename__ = "productos_proveedor"

    id              = Column(Integer, primary_key=True, index=True)
    
    # Identificadores del proveedor
    proveedor       = Column(SAEnum(NombreProveedor), nullable=False, index=True)
    sku_proveedor   = Column(String(120), nullable=False, index=True)
    url_producto    = Column(Text, nullable=False)
    
    # Datos del producto (tal como los devuelve el scraper — sin normalizar)
    nombre_raw      = Column(String(400), nullable=False)
    marca           = Column(String(120))
    precio_clp      = Column(Float, nullable=False)      # Precio en CLP
    precio_oferta   = Column(Float)                      # Precio con descuento si existe
    unidad          = Column(String(60))                 # "unidad", "caja x100", "kg"
    imagen_url      = Column(Text)
    disponible      = Column(Boolean, default=True)
    
    # IA / similitud
    # MIGRACIÓN: reemplazar por Vector(1536) con pgvector en PostgreSQL
    embedding_json  = Column(Text)  # JSON-encoded list[float] — generado por ai_matcher
    
    # Metadata de scraping
    estado_scraping = Column(SAEnum(EstadoScraping), default=EstadoScraping.PENDIENTE)
    scraped_at      = Column(DateTime, default=datetime.utcnow)
    
    # Relación al producto canónico (puede ser NULL hasta que la IA lo empare)
    canonical_id    = Column(Integer, ForeignKey("productos_canonical.id"), nullable=True)
    canonical       = relationship("ProductoCanonical", back_populates="variantes")
    historial_precios = relationship("HistorialPrecios", back_populates="producto")

    def __repr__(self) -> str:
        return f"<ProductoProveedor id={self.id} proveedor={self.proveedor} sku={self.sku_proveedor}>"


# ---------------------------------------------------------------------------
# HistorialPrecios (tracking estilo SoloTodo)
# ---------------------------------------------------------------------------

class HistorialPrecios(Base):
    """
    Registro histórico de precios de un producto.
    Cada vez que el sync detecta un cambio de precio, se crea una fila.
    Permite gráficos de evolución de precios estilo SoloTodo.
    """
    __tablename__ = "historial_precios"

    id              = Column(Integer, primary_key=True, index=True)
    producto_id     = Column(Integer, ForeignKey("productos_proveedor.id"), nullable=False, index=True)
    canonical_id    = Column(Integer, ForeignKey("productos_canonical.id"), nullable=True, index=True)

    precio_normal   = Column(Float, nullable=False)
    precio_oferta   = Column(Float)
    disponible      = Column(Boolean, default=True)

    registrado_at   = Column(DateTime, default=datetime.utcnow, index=True)

    producto        = relationship("ProductoProveedor", back_populates="historial_precios")

    __table_args__ = (
        Index("ix_historial_prod_fecha", "producto_id", "registrado_at"),
        Index("ix_historial_canon_fecha", "canonical_id", "registrado_at"),
    )


# ---------------------------------------------------------------------------
# ProductoCanonical
# ---------------------------------------------------------------------------

class ProductoCanonical(Base):
    """
    Representa el concepto abstracto de UN producto normalizado,
    independiente del proveedor. La IA decide qué productos de distintas
    tiendas son "el mismo" y los agrupa aquí.
    
    Ejemplo: "Tornillo hexagonal 1/4 x 2 pulgadas zincado" es el canonical,
    y sus variantes son el SKU específico en Sodimac y Easy.
    """
    __tablename__ = "productos_canonical"

    id                  = Column(Integer, primary_key=True, index=True)
    nombre_normalizado  = Column(String(300), nullable=False)
    descripcion         = Column(Text)
    unidad_base         = Column(String(60))             # Unidad estándar para comparar
    categoria           = Column(String(120), index=True)
    
    # Embedding del nombre canónico para búsqueda semántica
    # MIGRACIÓN: reemplazar por Vector(1536) en PostgreSQL
    embedding_json      = Column(Text)
    
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    variantes           = relationship("ProductoProveedor", back_populates="canonical")
    items_carrito       = relationship("ItemCarrito", back_populates="canonical")


# ---------------------------------------------------------------------------
# ComparacionPrecios
# ---------------------------------------------------------------------------

class ComparacionPrecios(Base):
    """
    Resultado del análisis de IA para un par de productos de distintos proveedores.
    Guarda el confidence_score para no recalcular en cada request.
    
    Se invalida automáticamente si algún producto supera MAX_AGE_HOURS.
    """
    __tablename__ = "comparaciones_precios"

    id               = Column(Integer, primary_key=True, index=True)
    canonical_id     = Column(Integer, ForeignKey("productos_canonical.id"), nullable=False)
    proveedor_a      = Column(SAEnum(NombreProveedor), nullable=False)
    proveedor_b      = Column(SAEnum(NombreProveedor), nullable=False)
    producto_a_id    = Column(Integer, ForeignKey("productos_proveedor.id"), nullable=False)
    producto_b_id    = Column(Integer, ForeignKey("productos_proveedor.id"), nullable=False)
    
    # Resultado de la IA
    confidence_score = Column(Float, nullable=False)    # 0.0 - 1.0
    razon_ia         = Column(Text)                     # Justificación del LLM (JSON)
    precio_diff_pct  = Column(Float)                    # % diferencia de precio
    precio_minimo    = Column(Float)                    # El más barato de los dos
    proveedor_minimo = Column(SAEnum(NombreProveedor))
    
    calculado_at     = Column(DateTime, default=datetime.utcnow)
    
    producto_a       = relationship("ProductoProveedor", foreign_keys=[producto_a_id])
    producto_b       = relationship("ProductoProveedor", foreign_keys=[producto_b_id])


# ---------------------------------------------------------------------------
# CarritoCompras
# ---------------------------------------------------------------------------

class CarritoCompras(Base):
    """
    Sesión de cotización del usuario. No es un carrito de e-commerce —
    es una herramienta de análisis de costos para el ERP.
    
    No almacenar datos personales aquí. session_key es un UUID anónimo.
    """
    __tablename__ = "carritos_compras"

    id              = Column(Integer, primary_key=True, index=True)
    session_key     = Column(String(64), unique=True, nullable=False, index=True)
    estado          = Column(SAEnum(EstadoCarrito), default=EstadoCarrito.ACTIVO)
    
    # Resumen calculado (actualizado cuando se "procesa" el carrito)
    total_sodimac   = Column(Float)
    total_easy      = Column(Float)
    ahorro_potencial= Column(Float)
    proveedor_optimo= Column(SAEnum(NombreProveedor))
    
    created_at      = Column(DateTime, default=datetime.utcnow)
    procesado_at    = Column(DateTime)
    
    items           = relationship(
        "ItemCarrito",
        back_populates="carrito",
        cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# ItemCarrito
# ---------------------------------------------------------------------------

class ItemCarrito(Base):
    """
    Un ítem dentro de un CarritoCompras.
    Referencia a un ProductoCanonical, no a un proveedor específico
    — la comparación entre proveedores ocurre al procesar el carrito.
    """
    __tablename__ = "items_carrito"

    id              = Column(Integer, primary_key=True, index=True)
    carrito_id      = Column(Integer, ForeignKey("carritos_compras.id"), nullable=False)
    canonical_id    = Column(Integer, ForeignKey("productos_canonical.id"), nullable=False)
    
    cantidad        = Column(Float, nullable=False, default=1.0)
    query_original  = Column(String(300))   # Lo que el usuario buscó ("tornillo 1/4")
    
    # Snapshot de precios al momento de agregar (desnormalizado para rendimiento)
    precio_sodimac  = Column(Float)
    precio_easy     = Column(Float)
    
    carrito         = relationship("CarritoCompras", back_populates="items")
    canonical       = relationship("ProductoCanonical", back_populates="items_carrito")