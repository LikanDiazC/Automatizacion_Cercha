"""
Alias de compatibilidad — la lógica vive en core/cutting_engine.py.

Se mantiene este módulo para no romper imports existentes.
"""
from core.cutting_engine import (  # noqa: F401
    optimizar_patron_corte,
    AREA_MINIMA_UTIL,
    MIN_LADO_UTIL,
)
