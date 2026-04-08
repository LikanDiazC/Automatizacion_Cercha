"""
Loader de diccionarios ferreteros (sinónimos, marcas, normas).

Singleton cacheado en memoria: el JSON se lee UNA sola vez al primer
acceso. Expone estructuras derivadas (maps invertidos alias->canónico)
para lookups O(1) desde el pipeline de matching.
"""
from __future__ import annotations

import json
import logging
import threading
import unicodedata
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_JSON_PATH = Path(__file__).parent / "sinonimos_ferreteria.json"

_lock = threading.Lock()
_raw_data: Optional[dict] = None
_alias_indices: Optional[dict[str, dict[str, str]]] = None


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _norm_key(s: str) -> str:
    """Normaliza una key para el lookup: minúsculas, sin tildes, sin espacios extra."""
    return _strip_accents((s or "").lower()).strip()


def _build_alias_index(section: dict) -> dict[str, str]:
    """
    Convierte {canonical: [aliases...]} en un índice invertido
    {alias_normalizado: canonical} para lookup O(1).
    """
    idx: dict[str, str] = {}
    for canonical, aliases in section.items():
        if not isinstance(aliases, list):
            continue
        idx[_norm_key(canonical)] = canonical
        for alias in aliases:
            idx[_norm_key(alias)] = canonical
    return idx


def _load() -> None:
    """Carga el JSON desde disco y construye índices invertidos (una sola vez)."""
    global _raw_data, _alias_indices
    if _raw_data is not None:
        return
    with _lock:
        if _raw_data is not None:
            return
        try:
            with _JSON_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.warning("Diccionario de sinónimos no encontrado en %s — usando vacío", _JSON_PATH)
            data = {}
        except json.JSONDecodeError as exc:
            logger.error("JSON de sinónimos corrupto (%s): %s — usando vacío", _JSON_PATH, exc)
            data = {}

        indices: dict[str, dict[str, str]] = {}
        for section_name, section in data.items():
            if section_name.startswith("_"):
                continue
            if isinstance(section, dict):
                indices[section_name] = _build_alias_index(section)

        _raw_data = data
        _alias_indices = indices
        logger.info(
            "Diccionario de sinónimos cargado: %d secciones (%s)",
            len(indices), ", ".join(sorted(indices.keys())),
        )


def get_raw() -> dict:
    _load()
    return _raw_data or {}


def canonicalize(section: str, value: str) -> Optional[str]:
    """
    Devuelve la forma canónica de `value` en la sección `section`
    (ej. canonicalize('cabezas', 'Hex') -> 'hexagonal').
    Retorna None si no hay match.
    """
    if not value:
        return None
    _load()
    idx = (_alias_indices or {}).get(section, {})
    return idx.get(_norm_key(value))


def are_synonyms(section: str, a: str, b: str) -> bool:
    """True si `a` y `b` apuntan al mismo canónico en `section`."""
    ca = canonicalize(section, a)
    cb = canonicalize(section, b)
    if ca is None or cb is None:
        # Si alguno no está en el diccionario, caemos a comparación textual normalizada
        return _norm_key(a) == _norm_key(b)
    return ca == cb


def section_values(section: str) -> list[str]:
    """Devuelve TODOS los aliases + canónicos de una sección (para Matcher/vocabulary)."""
    _load()
    idx = (_alias_indices or {}).get(section, {})
    return sorted(set(list(idx.keys()) + list(idx.values())))


def contains_any_alias(section: str, text: str) -> Optional[str]:
    """
    Busca si el texto contiene algún alias de la sección.
    Retorna el canónico del primer match, o None.
    """
    if not text:
        return None
    _load()
    idx = (_alias_indices or {}).get(section, {})
    text_norm = _norm_key(text)
    # Orden descendente por longitud para matchear primero los aliases largos
    for alias in sorted(idx.keys(), key=len, reverse=True):
        if not alias:
            continue
        # Match por límites de palabra aproximados (alias completo o precedido/seguido de separador)
        if alias in text_norm:
            # Verificación básica de borde de token
            i = text_norm.find(alias)
            left_ok = i == 0 or not text_norm[i - 1].isalnum()
            right_end = i + len(alias)
            right_ok = right_end == len(text_norm) or not text_norm[right_end].isalnum()
            if left_ok and right_ok:
                return idx[alias]
    return None
