"""
Diagnóstico de scraper — guarda dumps JSON crudos por búsqueda.

Carpeta: debug/scraper_dumps/
Formato: {timestamp}_{proveedor}_{query}.json

Cada archivo contiene:
  - query original
  - proveedor
  - método de extracción (network / apollo_state / dom / next_data)
  - items crudos ANTES de normalizar
  - productos finales DESPUÉS de normalizar
  - metadata (duración, cantidad, errores)
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Carpeta de dumps relativa a la raíz del proyecto
_DUMPS_DIR = Path(__file__).parent.parent.parent / "debug" / "scraper_dumps"


def _sanitize_filename(text: str, max_len: int = 40) -> str:
    """Limpia texto para usar como nombre de archivo."""
    clean = re.sub(r"[^\w\s-]", "", text.lower().strip())
    clean = re.sub(r"\s+", "_", clean)
    return clean[:max_len]


def dump_scraper_data(
    query: str,
    proveedor: str,
    metodo: str,
    items_crudos: Any,
    productos_finales: list,
    duracion_seg: float = 0.0,
    error_msg: Optional[str] = None,
    extra: Optional[dict] = None,
) -> Optional[str]:
    """
    Guarda un dump JSON con los datos crudos y procesados del scraper.
    Retorna la ruta del archivo creado, o None si falla.
    """
    try:
        _DUMPS_DIR.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        prov = _sanitize_filename(proveedor, 10)
        q = _sanitize_filename(query, 30)
        filename = f"{ts}_{prov}_{q}.json"
        filepath = _DUMPS_DIR / filename

        # Serializar productos finales (Pydantic → dict)
        productos_serializados = []
        for p in productos_finales:
            if hasattr(p, "model_dump"):
                productos_serializados.append(p.model_dump(mode="json"))
            elif hasattr(p, "dict"):
                productos_serializados.append(p.dict())
            elif isinstance(p, dict):
                productos_serializados.append(p)
            else:
                productos_serializados.append(str(p))

        # Limitar items crudos a 50 para no generar archivos enormes
        items_limitados = items_crudos
        items_total = 0
        if isinstance(items_crudos, list):
            items_total = len(items_crudos)
            items_limitados = items_crudos[:50]
        elif isinstance(items_crudos, dict):
            items_total = len(items_crudos)
            # Para dicts grandes (como __STATE__), tomar solo keys de producto
            if items_total > 100:
                items_limitados = {
                    k: v for k, v in list(items_crudos.items())[:50]
                }

        dump = {
            "meta": {
                "query": query,
                "proveedor": proveedor,
                "metodo": metodo,
                "timestamp": datetime.now().isoformat(),
                "duracion_seg": duracion_seg,
                "items_crudos_total": items_total,
                "items_crudos_guardados": len(items_limitados) if isinstance(items_limitados, (list, dict)) else 0,
                "productos_finales": len(productos_serializados),
                "error": error_msg,
            },
            "items_crudos": items_limitados,
            "productos_finales": productos_serializados,
        }

        if extra:
            dump["extra"] = extra

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=2, default=str)

        logger.info("Dump guardado: %s (%d items crudos, %d productos)",
                     filename, items_total, len(productos_serializados))
        print(f"   📋 [Debug] Dump guardado: {filename}")
        return str(filepath)

    except Exception as exc:
        logger.warning("No se pudo guardar dump de diagnóstico: %s", exc)
        return None


def listar_dumps(limite: int = 20) -> list[dict]:
    """Lista los dumps más recientes."""
    if not _DUMPS_DIR.exists():
        return []
    archivos = sorted(_DUMPS_DIR.glob("*.json"), reverse=True)[:limite]
    resultado = []
    for f in archivos:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            resultado.append({
                "archivo": f.name,
                "query": data.get("meta", {}).get("query"),
                "proveedor": data.get("meta", {}).get("proveedor"),
                "metodo": data.get("meta", {}).get("metodo"),
                "items_crudos": data.get("meta", {}).get("items_crudos_total"),
                "productos_finales": data.get("meta", {}).get("productos_finales"),
                "timestamp": data.get("meta", {}).get("timestamp"),
                "error": data.get("meta", {}).get("error"),
            })
        except Exception:
            resultado.append({"archivo": f.name, "error": "No se pudo leer"})
    return resultado
