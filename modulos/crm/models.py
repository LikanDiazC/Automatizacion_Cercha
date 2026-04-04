"""
Modelos CRM — Gestión de clientes estilo HubSpot.

Entidades principales:
  - Empresa: empresa/organización cliente
  - Contacto: persona dentro de una empresa
  - Deal: oportunidad de venta (Kanban pipeline)
  - Nota: notas libres asociadas a cualquier entidad
  - ActividadTimeline: timeline polimórfico de eventos
  - EmailMessage: correos enviados/recibidos con tracking

Pipeline de ventas:
  Prospecto → Cotización → Negociación → Ganado / Perdido
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean,
    DateTime, ForeignKey, Enum as SAEnum, Index,
)
from sqlalchemy.orm import relationship
import enum

from core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EstadoDeal(str, enum.Enum):
    """Pipeline Kanban stages."""
    PROSPECTO    = "prospecto"
    COTIZACION   = "cotizacion"
    NEGOCIACION  = "negociacion"
    GANADO       = "ganado"
    PERDIDO      = "perdido"


class TipoActividad(str, enum.Enum):
    """Tipos de evento en el timeline polimórfico."""
    NOTA         = "nota"
    EMAIL        = "email"
    LLAMADA      = "llamada"
    REUNION      = "reunion"
    COTIZACION   = "cotizacion"
    ORDEN        = "orden"
    CAMBIO_ESTADO = "cambio_estado"
    SISTEMA      = "sistema"


class OrigenContacto(str, enum.Enum):
    """Cómo llegó el contacto."""
    REFERIDO     = "referido"
    WEB          = "web"
    FERIA        = "feria"
    LLAMADA_FRIA = "llamada_fria"
    REDES_SOCIAL = "redes_sociales"
    OTRO         = "otro"


class EstadoEmail(str, enum.Enum):
    """Estado de un correo."""
    BORRADOR   = "borrador"
    ENVIADO    = "enviado"
    ENTREGADO  = "entregado"
    ABIERTO    = "abierto"
    CLICKED    = "clicked"
    REBOTADO   = "rebotado"
    ERROR      = "error"


class CarpetaEmail(str, enum.Enum):
    """Carpeta de organización."""
    ENVIADOS   = "enviados"
    BORRADORES = "borradores"
    INBOX      = "inbox"


class EstadoTarea(str, enum.Enum):
    """Estado de una tarea."""
    PENDIENTE    = "pendiente"
    EN_PROGRESO  = "en_progreso"
    COMPLETADA   = "completada"
    CANCELADA    = "cancelada"


class PrioridadTarea(str, enum.Enum):
    """Prioridad de una tarea."""
    BAJA   = "baja"
    MEDIA  = "media"
    ALTA   = "alta"
    URGENTE = "urgente"


class TipoLlamada(str, enum.Enum):
    """Tipo de llamada."""
    ENTRANTE = "entrante"
    SALIENTE = "saliente"
    PERDIDA  = "perdida"


class ResultadoLlamada(str, enum.Enum):
    """Resultado de una llamada."""
    CONECTADA    = "conectada"
    BUZON        = "buzon"
    NO_CONTESTA  = "no_contesta"
    OCUPADO      = "ocupado"
    NUMERO_MALO  = "numero_malo"


class EstadoCotizacion(str, enum.Enum):
    """Estado de una cotización."""
    BORRADOR    = "borrador"
    ENVIADA     = "enviada"
    VISTA       = "vista"
    ACEPTADA    = "aceptada"
    RECHAZADA   = "rechazada"
    EXPIRADA    = "expirada"


# ---------------------------------------------------------------------------
# Empresa
# ---------------------------------------------------------------------------

class Empresa(Base):
    """
    Empresa u organización cliente.
    Una empresa puede tener múltiples contactos y deals.
    """
    __tablename__ = "empresas"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(200), nullable=False, index=True)
    rut             = Column(String(20), unique=True, index=True)  # RUT chileno
    giro            = Column(String(200))
    direccion       = Column(Text)
    ciudad          = Column(String(100))
    region          = Column(String(100))
    telefono        = Column(String(30))
    email           = Column(String(200))
    sitio_web       = Column(String(300))
    notas           = Column(Text)

    # Clasificación
    industria       = Column(String(100))
    tamano          = Column(String(50))  # "micro", "pyme", "mediana", "grande"

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    contactos       = relationship("Contacto", back_populates="empresa", cascade="all, delete-orphan")
    deals           = relationship("Deal", back_populates="empresa")


# ---------------------------------------------------------------------------
# Contacto
# ---------------------------------------------------------------------------

class Contacto(Base):
    """
    Persona individual dentro de una empresa.
    Puede existir sin empresa (freelancer).
    """
    __tablename__ = "contactos"

    id              = Column(Integer, primary_key=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("empresas.id"), nullable=True, index=True)

    nombre          = Column(String(100), nullable=False)
    apellido        = Column(String(100))
    email           = Column(String(200), index=True)
    telefono        = Column(String(30))
    cargo           = Column(String(150))
    origen          = Column(SAEnum(OrigenContacto), default=OrigenContacto.OTRO)

    # Estado
    activo          = Column(Boolean, default=True)
    notas           = Column(Text)

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    empresa         = relationship("Empresa", back_populates="contactos")
    deals           = relationship("Deal", back_populates="contacto")


# ---------------------------------------------------------------------------
# Deal (Oportunidad de venta — Kanban)
# ---------------------------------------------------------------------------

class Deal(Base):
    """
    Oportunidad de venta en el pipeline.
    Cada deal se mueve por las etapas del Kanban:
      Prospecto → Cotización → Negociación → Ganado/Perdido

    Asociado opcionalmente a una empresa y un contacto.
    Puede vincularse a una OrdenTrabajo cuando se cierra.
    """
    __tablename__ = "deals"

    id              = Column(Integer, primary_key=True, index=True)
    titulo          = Column(String(300), nullable=False)
    descripcion     = Column(Text)

    # Pipeline
    estado          = Column(SAEnum(EstadoDeal), default=EstadoDeal.PROSPECTO, index=True)
    valor           = Column(Float, default=0.0)  # Valor estimado en CLP
    probabilidad    = Column(Float, default=0.0)  # 0.0 - 1.0

    # Relaciones con CRM
    empresa_id      = Column(Integer, ForeignKey("empresas.id"), nullable=True, index=True)
    contacto_id     = Column(Integer, ForeignKey("contactos.id"), nullable=True, index=True)

    # Vinculación con producción (cuando se cierra la venta)
    orden_trabajo_id = Column(Integer, ForeignKey("ordenes_trabajo.id"), nullable=True)

    # Fechas
    fecha_cierre_esperada = Column(DateTime)
    fecha_cierre_real     = Column(DateTime)
    razon_perdida         = Column(Text)  # Solo si estado = PERDIDO

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    empresa         = relationship("Empresa", back_populates="deals")
    contacto        = relationship("Contacto", back_populates="deals")
    orden_trabajo   = relationship("OrdenTrabajo")
    actividades     = relationship("ActividadTimeline", back_populates="deal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_deals_estado_empresa", "estado", "empresa_id"),
    )


# ---------------------------------------------------------------------------
# ActividadTimeline (Timeline polimórfico)
# ---------------------------------------------------------------------------

class ActividadTimeline(Base):
    """
    Evento en el timeline de un deal.
    Diseño polimórfico por tipo: el campo `tipo` determina qué campos
    son relevantes (nota → contenido, email → asunto+cuerpo, etc.)

    No usamos herencia de tabla — un solo modelo con campos opcionales
    es más simple para SQLite y migra fácil a PostgreSQL.
    """
    __tablename__ = "actividades_timeline"

    id              = Column(Integer, primary_key=True, index=True)
    deal_id         = Column(Integer, ForeignKey("deals.id"), nullable=False, index=True)
    tipo            = Column(SAEnum(TipoActividad), nullable=False, index=True)

    # Contenido genérico
    titulo          = Column(String(300))
    contenido       = Column(Text)  # Cuerpo del evento (nota, email body, etc.)

    # Campos específicos por tipo (opcionales)
    # Email
    email_asunto    = Column(String(300))
    email_destinatario = Column(String(200))
    email_abierto   = Column(Boolean, default=False)
    email_clicked   = Column(Boolean, default=False)

    # Llamada/Reunión
    duracion_min    = Column(Integer)  # Duración en minutos

    # Cambio de estado
    estado_anterior = Column(String(50))
    estado_nuevo    = Column(String(50))

    # Metadata
    usuario         = Column(String(100))  # Quién generó el evento
    created_at      = Column(DateTime, default=datetime.utcnow)

    # Relaciones
    deal            = relationship("Deal", back_populates="actividades")

    __table_args__ = (
        Index("ix_timeline_deal_fecha", "deal_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# EmailMessage — Correos enviados/recibidos con tracking
# ---------------------------------------------------------------------------

class EmailMessage(Base):
    """
    Correo electrónico vinculado al CRM.

    Tracking:
      - Pixel de apertura: al abrir el email, el cliente carga una imagen
        transparente 1x1 desde /api/crm/email/track/{tracking_id}/open
        que marca email_abierto=True y registra abierto_at.
      - Click tracking: los links del cuerpo se reescriben a
        /api/crm/email/track/{tracking_id}/click?url=... que registra
        el click y redirige al destino original.
    """
    __tablename__ = "emails_crm"

    id              = Column(Integer, primary_key=True, index=True)
    tracking_id     = Column(String(64), unique=True, nullable=False, index=True)

    # Remitente / Destinatario
    de_email        = Column(String(200), nullable=False)
    de_nombre       = Column(String(200))
    para_email      = Column(String(200), nullable=False)
    para_nombre     = Column(String(200))
    cc              = Column(Text)         # emails separados por coma
    cco             = Column(Text)         # BCC

    # Contenido
    asunto          = Column(String(500), nullable=False)
    cuerpo_html     = Column(Text)         # HTML del email
    cuerpo_texto    = Column(Text)         # Versión plaintext

    # Estado y tracking
    estado          = Column(SAEnum(EstadoEmail), default=EstadoEmail.BORRADOR, index=True)
    carpeta         = Column(SAEnum(CarpetaEmail), default=CarpetaEmail.BORRADORES, index=True)
    email_abierto   = Column(Boolean, default=False)
    veces_abierto   = Column(Integer, default=0)
    email_clicked   = Column(Boolean, default=False)
    veces_clicked   = Column(Integer, default=0)

    # Timestamps
    enviado_at      = Column(DateTime)
    abierto_at      = Column(DateTime)     # Primera apertura
    clicked_at      = Column(DateTime)     # Primer click
    created_at      = Column(DateTime, default=datetime.utcnow)

    # Vinculación CRM (todos opcionales)
    deal_id         = Column(Integer, ForeignKey("deals.id"), nullable=True, index=True)
    contacto_id     = Column(Integer, ForeignKey("contactos.id"), nullable=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("empresas.id"), nullable=True, index=True)

    # Error de envío
    error_mensaje   = Column(Text)

    # Relaciones
    deal            = relationship("Deal")
    contacto        = relationship("Contacto")
    empresa         = relationship("Empresa")

    __table_args__ = (
        Index("ix_email_estado_carpeta", "estado", "carpeta"),
        Index("ix_email_para", "para_email"),
    )


# ---------------------------------------------------------------------------
# Tarea — Gestión de tareas vinculadas al CRM
# ---------------------------------------------------------------------------

class Tarea(Base):
    """
    Tarea de seguimiento estilo HubSpot.
    Puede vincularse a deal, contacto o empresa.
    """
    __tablename__ = "tareas_crm"

    id              = Column(Integer, primary_key=True, index=True)
    titulo          = Column(String(300), nullable=False)
    descripcion     = Column(Text)
    estado          = Column(SAEnum(EstadoTarea), default=EstadoTarea.PENDIENTE, index=True)
    prioridad       = Column(SAEnum(PrioridadTarea), default=PrioridadTarea.MEDIA, index=True)

    # Fechas
    fecha_vencimiento = Column(DateTime, index=True)
    completada_at     = Column(DateTime)
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Asignación
    asignado_a      = Column(String(100))  # usuario responsable

    # Vinculación CRM
    deal_id         = Column(Integer, ForeignKey("deals.id"), nullable=True, index=True)
    contacto_id     = Column(Integer, ForeignKey("contactos.id"), nullable=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("empresas.id"), nullable=True, index=True)

    # Relaciones
    deal            = relationship("Deal")
    contacto        = relationship("Contacto")
    empresa         = relationship("Empresa")

    __table_args__ = (
        Index("ix_tarea_estado_venc", "estado", "fecha_vencimiento"),
    )


# ---------------------------------------------------------------------------
# Llamada — Registro de llamadas
# ---------------------------------------------------------------------------

class Llamada(Base):
    """
    Registro de llamada telefónica vinculada al CRM.
    """
    __tablename__ = "llamadas_crm"

    id              = Column(Integer, primary_key=True, index=True)
    tipo            = Column(SAEnum(TipoLlamada), nullable=False, default=TipoLlamada.SALIENTE)
    resultado       = Column(SAEnum(ResultadoLlamada), default=ResultadoLlamada.CONECTADA)
    numero          = Column(String(30))
    duracion_seg    = Column(Integer, default=0)
    notas           = Column(Text)

    created_at      = Column(DateTime, default=datetime.utcnow)

    # Vinculación CRM
    deal_id         = Column(Integer, ForeignKey("deals.id"), nullable=True, index=True)
    contacto_id     = Column(Integer, ForeignKey("contactos.id"), nullable=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("empresas.id"), nullable=True, index=True)

    # Relaciones
    deal            = relationship("Deal")
    contacto        = relationship("Contacto")
    empresa         = relationship("Empresa")


# ---------------------------------------------------------------------------
# PlantillaEmail — Plantillas de mensajes reutilizables
# ---------------------------------------------------------------------------

class PlantillaEmail(Base):
    """
    Plantilla de email reutilizable.
    Variables soportadas: {{nombre}}, {{empresa}}, {{deal}}, etc.
    """
    __tablename__ = "plantillas_email"

    id              = Column(Integer, primary_key=True, index=True)
    nombre          = Column(String(200), nullable=False, index=True)
    categoria       = Column(String(100), index=True)
    asunto          = Column(String(500), nullable=False)
    cuerpo_html     = Column(Text)
    cuerpo_texto    = Column(Text)
    veces_usada     = Column(Integer, default=0)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Cotizacion — Propuestas comerciales
# ---------------------------------------------------------------------------

class Cotizacion(Base):
    """
    Cotización/propuesta comercial vinculada a un deal.
    """
    __tablename__ = "cotizaciones_crm"

    id              = Column(Integer, primary_key=True, index=True)
    numero          = Column(String(50), unique=True, nullable=False, index=True)
    estado          = Column(SAEnum(EstadoCotizacion), default=EstadoCotizacion.BORRADOR, index=True)

    # Contenido
    titulo          = Column(String(300), nullable=False)
    descripcion     = Column(Text)
    items_json      = Column(Text, default="[]")  # JSON: [{descripcion, cantidad, precio_unitario, total}]
    subtotal        = Column(Float, default=0.0)
    descuento_pct   = Column(Float, default=0.0)
    iva_pct         = Column(Float, default=19.0)  # IVA chileno
    total           = Column(Float, default=0.0)
    moneda          = Column(String(10), default="CLP")
    notas           = Column(Text)

    # Vigencia
    fecha_emision   = Column(DateTime, default=datetime.utcnow)
    fecha_expiracion = Column(DateTime)

    # Vinculación CRM
    deal_id         = Column(Integer, ForeignKey("deals.id"), nullable=True, index=True)
    contacto_id     = Column(Integer, ForeignKey("contactos.id"), nullable=True, index=True)
    empresa_id      = Column(Integer, ForeignKey("empresas.id"), nullable=True, index=True)

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relaciones
    deal            = relationship("Deal")
    contacto        = relationship("Contacto")
    empresa         = relationship("Empresa")
