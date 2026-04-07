"""
Servicio de tareas programadas en segundo plano.

Usa APScheduler para ejecutar el sync del catálogo de precios
automáticamente cada N horas sin intervención del usuario.

Tareas registradas:
  1. sync_precios: Scrapea proveedores, actualiza precios, registra historial
  2. cleanup_datos: Limpia datos antiguos de scraping (>30 días)

Configuración via .env:
  SYNC_INTERVALO_HORAS=6   (default: cada 6 horas)
  SYNC_HORA_INICIO=7       (default: primera ejecución a las 7:00)
  SYNC_HABILITADO=true     (default: true)
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from core.database import SessionLocal

logger = logging.getLogger(__name__)

# Estado global del scheduler
_scheduler: Optional[AsyncIOScheduler] = None
_ultimo_sync: Optional[dict] = None


def get_scheduler() -> Optional[AsyncIOScheduler]:
    return _scheduler


def get_ultimo_sync() -> Optional[dict]:
    return _ultimo_sync


# ---------------------------------------------------------------------------
# Tarea: Sync de precios
# ---------------------------------------------------------------------------

async def _tarea_sync_precios():
    """
    Ejecuta el sync completo del catálogo:
    1. Scrapea todos los queries predefinidos
    2. Persiste productos nuevos/actualizados
    3. Crea canonicals con AI matching
    4. Registra cambios de precio en historial
    """
    global _ultimo_sync

    logger.info("=== SYNC AUTOMÁTICO INICIADO ===")
    inicio = datetime.utcnow()

    db = SessionLocal()
    try:
        from modulos.compras.catalogo import sync_catalogo
        from modulos.compras.models import HistorialPrecios, ProductoProveedor, EstadoScraping

        # 1. Guardar precios actuales antes del sync (para detectar cambios)
        productos_antes = {}
        for p in db.query(ProductoProveedor).filter(
            ProductoProveedor.estado_scraping == EstadoScraping.EXITO
        ).all():
            productos_antes[f"{p.proveedor}_{p.sku_proveedor}"] = {
                "id": p.id,
                "precio_clp": p.precio_clp,
                "precio_oferta": p.precio_oferta,
            }

        # 2. Ejecutar sync
        resumen = await sync_catalogo(db, max_resultados=5)

        # 3. Detectar cambios de precio y registrar en historial
        cambios_precio = 0
        for p in db.query(ProductoProveedor).filter(
            ProductoProveedor.estado_scraping == EstadoScraping.EXITO
        ).all():
            key = f"{p.proveedor}_{p.sku_proveedor}"
            antes = productos_antes.get(key)

            # Si es producto nuevo o cambió el precio → registrar en historial
            if antes is None or antes["precio_clp"] != p.precio_clp or antes.get("precio_oferta") != p.precio_oferta:
                historial = HistorialPrecios(
                    producto_id=p.id,
                    canonical_id=p.canonical_id,
                    precio_normal=p.precio_clp,
                    precio_oferta=p.precio_oferta,
                    disponible=p.disponible,
                )
                db.add(historial)
                cambios_precio += 1

        db.commit()

        resumen["cambios_precio_detectados"] = cambios_precio
        _ultimo_sync = {
            "timestamp": datetime.utcnow().isoformat(),
            "duracion_seg": (datetime.utcnow() - inicio).total_seconds(),
            "resumen": resumen,
        }

        logger.info(
            "=== SYNC COMPLETADO: %d productos, %d cambios de precio ===",
            resumen.get("productos_guardados", 0),
            cambios_precio,
        )

    except Exception as exc:
        logger.error("Error en sync automático: %s", exc, exc_info=True)
        _ultimo_sync = {
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(exc),
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tarea: Cleanup de datos antiguos
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tarea: Sync de inbox OAuth (Gmail / Microsoft) para todos los usuarios
# ---------------------------------------------------------------------------

async def _tarea_sync_inbox():
    """
    Sincroniza la bandeja de entrada de todos los usuarios con sync habilitado.
    Ejecuta en segundo plano, jamás lanza excepciones hacia el scheduler.
    """
    logger.info("=== SYNC INBOX INICIADO ===")
    db = SessionLocal()
    try:
        from modulos.crm.inbox_sync_service import sincronizar_todos_los_usuarios
        resumen = await sincronizar_todos_los_usuarios(db)
        logger.info(
            "=== SYNC INBOX COMPLETADO: ok=%d err=%d nuevos=%d ===",
            resumen.get("ok", 0),
            resumen.get("errores", 0),
            resumen.get("nuevos_total", 0),
        )
    except Exception as exc:
        logger.error("Error en sync inbox: %s", exc, exc_info=True)
    finally:
        db.close()


async def _tarea_cleanup():
    """Limpia datos de scraping con más de 30 días."""
    from datetime import timedelta
    from modulos.compras.models import ProductoProveedor, HistorialPrecios

    logger.info("Cleanup: eliminando datos antiguos...")
    db = SessionLocal()
    try:
        limite = datetime.utcnow() - timedelta(days=30)

        # Eliminar historial de precios antiguo
        eliminados = db.query(HistorialPrecios).filter(
            HistorialPrecios.registrado_at < limite
        ).delete()

        db.commit()
        logger.info("Cleanup completado: %d registros de historial eliminados", eliminados)
    except Exception as exc:
        logger.error("Error en cleanup: %s", exc)
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Inicialización y control del scheduler
# ---------------------------------------------------------------------------

def iniciar_scheduler(
    intervalo_horas: int = 6,
    hora_inicio: int = 7,
    habilitado: bool = True,
):
    """
    Inicia el scheduler de tareas en segundo plano.
    Debe llamarse desde el lifespan de FastAPI.
    """
    global _scheduler

    if not habilitado:
        logger.info("Scheduler deshabilitado por configuración")
        return

    _scheduler = AsyncIOScheduler()

    # Sync de precios cada N horas
    _scheduler.add_job(
        _tarea_sync_precios,
        trigger=IntervalTrigger(hours=intervalo_horas),
        id="sync_precios",
        name="Sync de precios del catálogo",
        replace_existing=True,
        max_instances=1,  # No ejecutar en paralelo
    )

    # Sync de inbox OAuth cada 10 minutos (multi-usuario)
    _scheduler.add_job(
        _tarea_sync_inbox,
        trigger=IntervalTrigger(minutes=10),
        id="sync_inbox",
        name="Sync de bandeja de entrada OAuth",
        replace_existing=True,
        max_instances=1,
    )

    # Cleanup diario a las 3:00 AM
    _scheduler.add_job(
        _tarea_cleanup,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_datos",
        name="Limpieza de datos antiguos",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler iniciado: sync cada %d horas, cleanup diario a las 3:00",
        intervalo_horas,
    )


def detener_scheduler():
    """Detiene el scheduler limpiamente."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler detenido")
        _scheduler = None


async def ejecutar_sync_manual():
    """Ejecuta el sync manualmente (desde endpoint API)."""
    await _tarea_sync_precios()
    return _ultimo_sync
