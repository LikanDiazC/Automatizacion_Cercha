"""
Schemas Pydantic v2 para el módulo de Compras Inteligentes.

Convenciones de seguridad:
  - Todos los campos String tienen max_length definido para evitar payload flooding.
  - Las URLs se validan con AnyHttpUrl — nunca almacenamos strings arbitrarios.
  - Los confidence_score son Field(..., ge=0.0, le=1.0) — nunca fuera de rango.
  - Ningún schema expone el embedding_json al cliente.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import (
    BaseModel, Field, AnyHttpUrl,
    field_validator, model_validator, ConfigDict
)

from .models import NombreProveedor, EstadoCarrito, EstadoScraping


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

class _BaseSchema(BaseModel):
    """Config base compartida por todos los schemas."""
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# ProductoProveedor
# ---------------------------------------------------------------------------

class ProductoProveedorCreate(_BaseSchema):
    """
    Input del scraper al persistir un producto.
    El scraper debe validar estos datos antes de llamar al endpoint.
    """
    proveedor:      NombreProveedor
    sku_proveedor:  str         = Field(..., min_length=1, max_length=120)
    url_producto:   AnyHttpUrl
    nombre_raw:     str         = Field(..., min_length=2, max_length=400)
    marca:          Optional[str] = Field(None, max_length=120)
    precio_clp:     float       = Field(..., gt=0, description="Precio en CLP, debe ser > 0")
    precio_oferta:  Optional[float] = Field(None, gt=0)
    unidad:         Optional[str] = Field(None, max_length=60)
    imagen_url:     Optional[AnyHttpUrl] = None
    disponible:     bool        = True

    @field_validator("precio_oferta")
    @classmethod
    def oferta_menor_que_precio(cls, v: Optional[float], info) -> Optional[float]:
        """La oferta no puede ser mayor que el precio regular."""
        if v is not None and "precio_clp" in info.data:
            if v > info.data["precio_clp"]:
                raise ValueError("precio_oferta no puede superar precio_clp")
        return v


class ProductoProveedorResponse(_BaseSchema):
    """
    Lo que el cliente ve. NUNCA incluir embedding_json aquí.
    """
    id:             int
    proveedor:      NombreProveedor
    sku_proveedor:  str
    url_producto:   str
    nombre_raw:     str
    marca:          Optional[str]
    precio_clp:     float
    precio_oferta:  Optional[float]
    unidad:         Optional[str]
    imagen_url:     Optional[str]
    disponible:     bool
    estado_scraping: EstadoScraping
    scraped_at:     datetime
    canonical_id:   Optional[int]


# ---------------------------------------------------------------------------
# ProductoCanonical
# ---------------------------------------------------------------------------

class ProductoCanonicalCreate(_BaseSchema):
    nombre_normalizado: str = Field(..., min_length=3, max_length=300)
    descripcion:        Optional[str] = Field(None, max_length=1000)
    unidad_base:        Optional[str] = Field(None, max_length=60)
    categoria:          Optional[str] = Field(None, max_length=120)


class ProductoCanonicalResponse(_BaseSchema):
    id:                 int
    nombre_normalizado: str
    descripcion:        Optional[str]
    unidad_base:        Optional[str]
    categoria:          Optional[str]
    created_at:         datetime
    # embedding_json NO se expone


# ---------------------------------------------------------------------------
# ComparacionPrecios
# ---------------------------------------------------------------------------

class ComparacionCreate(_BaseSchema):
    canonical_id:   int     = Field(..., gt=0)
    producto_a_id:  int     = Field(..., gt=0)
    producto_b_id:  int     = Field(..., gt=0)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    razon_ia:       Optional[str] = Field(None, max_length=2000)

    @model_validator(mode="after")
    def productos_distintos(self) -> "ComparacionCreate":
        if self.producto_a_id == self.producto_b_id:
            raise ValueError("producto_a_id y producto_b_id deben ser distintos")
        return self


class ComparacionResponse(_BaseSchema):
    id:               int
    canonical_id:     int
    proveedor_a:      NombreProveedor
    proveedor_b:      NombreProveedor
    producto_a_id:    int
    producto_b_id:    int
    confidence_score: float
    precio_diff_pct:  Optional[float]
    precio_minimo:    Optional[float]
    proveedor_minimo: Optional[NombreProveedor]
    calculado_at:     datetime


# ---------------------------------------------------------------------------
# BusquedaProducto (input del usuario desde el frontend)
# ---------------------------------------------------------------------------

class BusquedaProductoRequest(_BaseSchema):
    """
    Lo que el usuario escribe en la barra de búsqueda del Cotizador.
    Validación estricta para evitar inyecciones y payloads gigantes.
    """
    query: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Texto de búsqueda. Ej: 'Tornillo 1/4 pulgada zincado'"
    )
    proveedores: List[NombreProveedor] = Field(
        default=[NombreProveedor.SODIMAC, NombreProveedor.EASY],
        min_length=1,
        max_length=5,
        description="Lista de proveedores a consultar"
    )
    max_resultados: int = Field(default=10, ge=1, le=50)

    @field_validator("query")
    @classmethod
    def sanitizar_query(cls, v: str) -> str:
        """
        Sanitización de defensa en profundidad para la query de búsqueda.

        Rechaza caracteres que:
        - Podrían usarse en inyección SQL si la query llega a un LIKE sin ORM (SQLi)
        - Son vectores de XSS si la query se refleja en HTML (XSS)
        - Son inusuales en búsquedas legítimas de materiales de construcción

        Nota: SQLAlchemy parametriza todas las queries, por lo que el riesgo de
        SQLi ya está mitigado a nivel ORM. Esta validación es una capa adicional.
        """
        import re
        v = v.strip()
        # Bloquear caracteres de inyección: SQL (', ", ;, --), XSS (<, >),
        # y shell/path injection ({, }, |, ^, `, \)
        if re.search(r"""[<>{}|\\^`'";]""", v):
            raise ValueError(
                "La búsqueda contiene caracteres no permitidos. "
                "Usa letras, números, espacios, guiones y barras."
            )
        # Bloquear secuencias de comentario SQL (-- y /*) aunque los chars individuales
        # ya fueron rechazados arriba, esta línea bloquea variantes codificadas
        if "--" in v or "/*" in v or "*/" in v:
            raise ValueError("La búsqueda contiene secuencias no permitidas.")
        return v


class ResultadoBusqueda(_BaseSchema):
    """Respuesta del endpoint de búsqueda — lista de canónicos con sus variantes."""
    canonical:          ProductoCanonicalResponse
    variantes:          List[ProductoProveedorResponse]
    mejor_precio:       Optional[float]
    proveedor_optimo:   Optional[NombreProveedor]
    diferencia_precio:  Optional[float]     # En CLP
    confidence_score:   Optional[float]     # 0-1 de que las variantes son "el mismo producto"


# ---------------------------------------------------------------------------
# CarritoCompras
# ---------------------------------------------------------------------------

class AgregarItemRequest(_BaseSchema):
    canonical_id:   int   = Field(..., gt=0)
    cantidad:       float = Field(..., gt=0, le=99999)
    query_original: Optional[str] = Field(None, max_length=300)


class ItemCarritoResponse(_BaseSchema):
    id:             int
    canonical_id:   int
    cantidad:       float
    query_original: Optional[str]
    precio_sodimac: Optional[float]
    precio_easy:    Optional[float]
    canonical:      Optional[ProductoCanonicalResponse] = None


class CarritoResponse(_BaseSchema):
    id:               int
    session_key:      str
    estado:           EstadoCarrito
    items:            List[ItemCarritoResponse] = []
    total_sodimac:    Optional[float]
    total_easy:       Optional[float]
    ahorro_potencial: Optional[float]
    proveedor_optimo: Optional[NombreProveedor]
    created_at:       datetime
    procesado_at:     Optional[datetime]


class ResumenCotizacion(_BaseSchema):
    """
    Dashboard final que ve el usuario al procesar su carrito.
    Incluye el desglose por tienda y la recomendación.
    """
    carrito_id:       int
    items_count:      int
    total_sodimac:    float
    total_easy:       float
    ahorro_potencial: float
    proveedor_optimo: NombreProveedor
    ahorro_porcentaje: float = Field(..., ge=0.0)
    detalle:          List[ItemCarritoResponse]
    advertencias:     List[str] = []  # Ej: "Producto X no disponible en Easy"