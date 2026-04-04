"""
Schemas Pydantic v2 para el módulo CRM.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from .models import (
    EstadoDeal, TipoActividad, OrigenContacto, EstadoEmail, CarpetaEmail,
    EstadoTarea, PrioridadTarea, TipoLlamada, ResultadoLlamada, EstadoCotizacion,
)


# ---------------------------------------------------------------------------
# Empresa
# ---------------------------------------------------------------------------

class EmpresaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    rut: Optional[str] = Field(None, max_length=20)
    giro: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    region: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    sitio_web: Optional[str] = None
    notas: Optional[str] = None
    industria: Optional[str] = None
    tamano: Optional[str] = None


class EmpresaCreate(EmpresaBase):
    pass


class EmpresaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    rut: Optional[str] = None
    giro: Optional[str] = None
    direccion: Optional[str] = None
    ciudad: Optional[str] = None
    region: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    sitio_web: Optional[str] = None
    notas: Optional[str] = None
    industria: Optional[str] = None
    tamano: Optional[str] = None


class EmpresaRead(EmpresaBase):
    id: int
    created_at: datetime
    updated_at: datetime
    n_contactos: int = 0
    n_deals: int = 0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Contacto
# ---------------------------------------------------------------------------

class ContactoBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    apellido: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    cargo: Optional[str] = None
    origen: OrigenContacto = OrigenContacto.OTRO
    empresa_id: Optional[int] = None
    notas: Optional[str] = None


class ContactoCreate(ContactoBase):
    pass


class ContactoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=1, max_length=100)
    apellido: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    cargo: Optional[str] = None
    origen: Optional[OrigenContacto] = None
    empresa_id: Optional[int] = None
    activo: Optional[bool] = None
    notas: Optional[str] = None


class ContactoRead(ContactoBase):
    id: int
    activo: bool
    created_at: datetime
    updated_at: datetime
    empresa_nombre: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Deal
# ---------------------------------------------------------------------------

class DealBase(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    descripcion: Optional[str] = None
    estado: EstadoDeal = EstadoDeal.PROSPECTO
    valor: float = 0.0
    probabilidad: float = Field(0.0, ge=0.0, le=1.0)
    empresa_id: Optional[int] = None
    contacto_id: Optional[int] = None
    fecha_cierre_esperada: Optional[datetime] = None


class DealCreate(DealBase):
    pass


class DealUpdate(BaseModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[EstadoDeal] = None
    valor: Optional[float] = None
    probabilidad: Optional[float] = Field(None, ge=0.0, le=1.0)
    empresa_id: Optional[int] = None
    contacto_id: Optional[int] = None
    orden_trabajo_id: Optional[int] = None
    fecha_cierre_esperada: Optional[datetime] = None
    fecha_cierre_real: Optional[datetime] = None
    razon_perdida: Optional[str] = None


class DealRead(DealBase):
    id: int
    orden_trabajo_id: Optional[int] = None
    fecha_cierre_real: Optional[datetime] = None
    razon_perdida: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    empresa_nombre: Optional[str] = None
    contacto_nombre: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# ActividadTimeline
# ---------------------------------------------------------------------------

class ActividadCreate(BaseModel):
    deal_id: int
    tipo: TipoActividad
    titulo: Optional[str] = None
    contenido: Optional[str] = None
    email_asunto: Optional[str] = None
    email_destinatario: Optional[str] = None
    duracion_min: Optional[int] = None
    estado_anterior: Optional[str] = None
    estado_nuevo: Optional[str] = None
    usuario: Optional[str] = None


class ActividadRead(BaseModel):
    id: int
    deal_id: int
    tipo: TipoActividad
    titulo: Optional[str] = None
    contenido: Optional[str] = None
    email_asunto: Optional[str] = None
    email_destinatario: Optional[str] = None
    email_abierto: bool = False
    email_clicked: bool = False
    duracion_min: Optional[int] = None
    estado_anterior: Optional[str] = None
    estado_nuevo: Optional[str] = None
    usuario: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Pipeline / Dashboard
# ---------------------------------------------------------------------------

class PipelineResumen(BaseModel):
    """Resumen del pipeline para el dashboard Kanban."""
    estado: EstadoDeal
    cantidad: int
    valor_total: float


class DealKanbanColumn(BaseModel):
    """Columna del Kanban con deals."""
    estado: EstadoDeal
    deals: list[DealRead]
    valor_total: float


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

class EmailCreate(BaseModel):
    para_email: str = Field(..., min_length=3, max_length=200)
    para_nombre: Optional[str] = None
    asunto: str = Field(..., min_length=1, max_length=500)
    cuerpo_html: str = ""
    cuerpo_texto: str = ""
    cc: Optional[str] = None
    cco: Optional[str] = None
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None


class EmailRead(BaseModel):
    id: int
    tracking_id: str
    de_email: str
    de_nombre: Optional[str] = None
    para_email: str
    para_nombre: Optional[str] = None
    asunto: str
    cuerpo_html: Optional[str] = None
    cuerpo_texto: Optional[str] = None
    cc: Optional[str] = None
    estado: EstadoEmail
    carpeta: CarpetaEmail
    email_abierto: bool = False
    veces_abierto: int = 0
    email_clicked: bool = False
    veces_clicked: int = 0
    enviado_at: Optional[datetime] = None
    abierto_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    created_at: datetime
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None
    error_mensaje: Optional[str] = None

    model_config = {"from_attributes": True}


class EmailEstadisticas(BaseModel):
    total: int
    enviados: int
    abiertos: int
    clicked: int
    errores: int
    borradores: int
    tasa_apertura: float
    tasa_click: float


# ---------------------------------------------------------------------------
# Tarea
# ---------------------------------------------------------------------------

class TareaCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    descripcion: Optional[str] = None
    estado: EstadoTarea = EstadoTarea.PENDIENTE
    prioridad: PrioridadTarea = PrioridadTarea.MEDIA
    fecha_vencimiento: Optional[datetime] = None
    asignado_a: Optional[str] = None
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None


class TareaUpdate(BaseModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[EstadoTarea] = None
    prioridad: Optional[PrioridadTarea] = None
    fecha_vencimiento: Optional[datetime] = None
    asignado_a: Optional[str] = None
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None


class TareaRead(BaseModel):
    id: int
    titulo: str
    descripcion: Optional[str] = None
    estado: EstadoTarea
    prioridad: PrioridadTarea
    fecha_vencimiento: Optional[datetime] = None
    completada_at: Optional[datetime] = None
    asignado_a: Optional[str] = None
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    # Campos computados
    deal_titulo: Optional[str] = None
    contacto_nombre: Optional[str] = None
    empresa_nombre: Optional[str] = None
    vencida: bool = False

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Llamada
# ---------------------------------------------------------------------------

class LlamadaCreate(BaseModel):
    tipo: TipoLlamada = TipoLlamada.SALIENTE
    resultado: ResultadoLlamada = ResultadoLlamada.CONECTADA
    numero: Optional[str] = None
    duracion_seg: int = 0
    notas: Optional[str] = None
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None


class LlamadaRead(BaseModel):
    id: int
    tipo: TipoLlamada
    resultado: ResultadoLlamada
    numero: Optional[str] = None
    duracion_seg: int = 0
    notas: Optional[str] = None
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None
    created_at: datetime
    contacto_nombre: Optional[str] = None
    empresa_nombre: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# PlantillaEmail
# ---------------------------------------------------------------------------

class PlantillaCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    categoria: Optional[str] = None
    asunto: str = Field(..., min_length=1, max_length=500)
    cuerpo_html: str = ""
    cuerpo_texto: str = ""


class PlantillaUpdate(BaseModel):
    nombre: Optional[str] = None
    categoria: Optional[str] = None
    asunto: Optional[str] = None
    cuerpo_html: Optional[str] = None
    cuerpo_texto: Optional[str] = None


class PlantillaRead(BaseModel):
    id: int
    nombre: str
    categoria: Optional[str] = None
    asunto: str
    cuerpo_html: Optional[str] = None
    cuerpo_texto: Optional[str] = None
    veces_usada: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Cotizacion
# ---------------------------------------------------------------------------

class CotizacionItemSchema(BaseModel):
    descripcion: str
    cantidad: float = 1.0
    precio_unitario: float = 0.0
    total: float = 0.0


class CotizacionCreate(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=300)
    descripcion: Optional[str] = None
    items: list[CotizacionItemSchema] = []
    descuento_pct: float = 0.0
    iva_pct: float = 19.0
    moneda: str = "CLP"
    notas: Optional[str] = None
    fecha_expiracion: Optional[datetime] = None
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None


class CotizacionUpdate(BaseModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[EstadoCotizacion] = None
    items: Optional[list[CotizacionItemSchema]] = None
    descuento_pct: Optional[float] = None
    iva_pct: Optional[float] = None
    notas: Optional[str] = None
    fecha_expiracion: Optional[datetime] = None


class CotizacionRead(BaseModel):
    id: int
    numero: str
    estado: EstadoCotizacion
    titulo: str
    descripcion: Optional[str] = None
    items_json: Optional[str] = None
    subtotal: float = 0.0
    descuento_pct: float = 0.0
    iva_pct: float = 19.0
    total: float = 0.0
    moneda: str = "CLP"
    notas: Optional[str] = None
    fecha_emision: Optional[datetime] = None
    fecha_expiracion: Optional[datetime] = None
    deal_id: Optional[int] = None
    contacto_id: Optional[int] = None
    empresa_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    deal_titulo: Optional[str] = None
    contacto_nombre: Optional[str] = None
    empresa_nombre: Optional[str] = None

    model_config = {"from_attributes": True}
