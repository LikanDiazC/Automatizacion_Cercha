"""
Tests unitarios para el motor de matching — foco en la Capa 1.5
(Cruce de Grafos Determinista).

Objetivo crítico:
  * "Perno hexagonal 8x1" vs "Perno hexagonal 8x2"  → rechazo con
    confidence 0.0 ANTES de llegar a la Capa 2 (embeddings / LLM).

Se ejecutan con:
    pytest tests/test_ai_matcher.py -v
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modulos.compras import ai_matcher  # noqa: E402
from modulos.compras.ai_matcher import (  # noqa: E402
    MatchResult,
    comparar_productos,
    cruzar_grafos_deterministas,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _mock_producto(
    pid: int,
    nombre: str,
    marca: str = "Stanley",
    proveedor: str = "SODIMAC",
    sku: Optional[str] = None,
    unidad: str = "unidad",
    precio: float = 1000.0,
) -> MagicMock:
    """Crea un mock de ProductoProveedor con los atributos mínimos."""
    p = MagicMock(name=f"ProductoProveedor<{pid}>")
    p.id = pid
    p.nombre_raw = nombre
    p.marca = marca
    p.proveedor = proveedor
    p.sku_proveedor = sku or f"SKU-{pid}"
    p.unidad = unidad
    p.unidad_normalizada = unidad
    p.precio_clp = precio
    p.precio_oferta = None
    p.embedding_json = None
    p.canonical_id = None
    p.etim_class_code = None
    return p


from typing import Optional  # noqa: E402 (usado por _mock_producto anotation)


class _FakeSession:
    """Stub de sqlalchemy.orm.Session: absorbe llamadas sin efectos."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        pass

    def rollback(self):
        pass

    def flush(self):
        pass

    def query(self, *a, **kw):
        q = MagicMock()
        q.filter.return_value = q
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.first.return_value = None
        q.all.return_value = []
        return q

    def get(self, model, pk):
        return None


@pytest.fixture
def fake_db():
    return _FakeSession()


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    """Forzamos modo sin API key para no disparar HTTP ni LLM."""
    monkeypatch.setattr(ai_matcher, "_tiene_api_key_valida", lambda: False)
    # Neutralizamos el guardado de AICallLog / ComparacionPrecios
    monkeypatch.setattr(ai_matcher, "_log_ai_call", lambda *a, **kw: None)
    monkeypatch.setattr(ai_matcher, "_guardar_comparacion", lambda *a, **kw: None)


@pytest.fixture
def _bypass_unit_normalizer(monkeypatch):
    """
    Saltea la Capa 1 (quantulum3/pint) para que el test pueda aislar
    el comportamiento de la Capa 1.5. En producción, Capa 1 podría ya
    haber interceptado ciertos casos — este bypass verifica que, aún si
    pasan Capa 1, la Capa 1.5 los rechaza por nodos físicos.
    """
    fake_result = SimpleNamespace(
        compatible=True,
        razon="bypass test — capa1 ok",
        qty_a=None,
        qty_b=None,
        ratio=1.0,
    )
    monkeypatch.setattr(ai_matcher, "compare_units", lambda *a, **kw: fake_result)


# ---------------------------------------------------------------------------
# Test 1 — Capa 1.5 rechaza 8x1 vs 8x2 (test CRÍTICO)
# ---------------------------------------------------------------------------

def test_capa_15_rechaza_dimensiones_incompatibles_8x1_vs_8x2(fake_db, _bypass_unit_normalizer):
    """
    Test obligatorio: "Perno hexagonal 8x1" vs "Perno hexagonal 8x2"
    debe ser rechazado por la Capa 1.5 con confidence 0.0 y NO llegar
    a la Capa 2 (embeddings).
    """
    a = _mock_producto(1, "Perno hexagonal 8x1 zincado")
    b = _mock_producto(2, "Perno hexagonal 8x2 zincado")

    # Espiamos generar_y_guardar_embedding para comprobar que NO se llama
    with patch.object(ai_matcher, "generar_y_guardar_embedding") as mock_emb:
        resultado: MatchResult = asyncio.run(comparar_productos(a, b, fake_db))

    assert resultado.es_mismo_producto is False
    assert resultado.confidence_score == 0.0
    assert "graph_cross_rechazo" in resultado.metodo
    assert "largo_raw" in resultado.razon or "8x1" in resultado.razon or "nodos" in resultado.razon.lower()
    mock_emb.assert_not_called(), "La Capa 2 (embeddings) NO debe ejecutarse"


# ---------------------------------------------------------------------------
# Test 2 — Capa 1.5 permite pasar cuando nodos son compatibles
# ---------------------------------------------------------------------------

def test_capa_15_permite_paso_cuando_nodos_coinciden(fake_db, _bypass_unit_normalizer):
    """
    Mismas dimensiones → Capa 1.5 NO debe cortar; debe delegar a Capa 4
    (Jaccard fallback) porque _no_api_key está activo.
    """
    a = _mock_producto(10, "Perno hexagonal 1/2 x 3 zincado Stanley")
    b = _mock_producto(11, "Perno Hex 1/2 x 3 Zn Stanley")

    resultado = asyncio.run(comparar_productos(a, b, fake_db))

    assert resultado.metodo != "graph_cross_rechazo"
    # Debe haber lineage de unit + graph_cross
    assert "graph_cross" in resultado.lineage
    assert resultado.lineage["graph_cross"]["compatible"] is True


# ---------------------------------------------------------------------------
# Test 3 — Unit test puro de cruzar_grafos_deterministas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "nombre_a,nombre_b,esperado_compatible",
    [
        ("Perno hexagonal 8x1 zincado", "Perno hexagonal 8x2 zincado", False),
        ("Tornillo M6x20 inox",         "Tornillo M6x30 inox",         False),
        ("Clavo 50mm acero",            "Clavo 60mm acero",            False),
        ("Perno hex 1/2 x 3 zincado",   "Perno hex 1/2 x 3 zincado",   True),
        ("Tornillo allen",              "Tornillo hexagonal",          False),
    ],
)
def test_cruzar_grafos_deterministas(nombre_a, nombre_b, esperado_compatible):
    compat, razon, debug = cruzar_grafos_deterministas(nombre_a, "", nombre_b, "")
    assert compat is esperado_compatible, (
        f"Falló cruce: {nombre_a!r} vs {nombre_b!r} — razon={razon!r} debug={debug!r}"
    )


# ---------------------------------------------------------------------------
# Test 4 — Sanity check: no rompe cuando sólo uno de los dos tiene nodo
# ---------------------------------------------------------------------------

def test_cruzar_grafos_sin_nodos_comunes_no_rechaza():
    """
    Si sólo uno de los productos tiene dimensiones extraíbles, la Capa 1.5
    no puede rechazar por grafos (no hay evidencia de conflicto).
    """
    compat, razon, debug = cruzar_grafos_deterministas(
        "Perno hexagonal 8x1", "", "Perno hexagonal zincado", "",
    )
    assert compat is True
    assert debug["conflictos"] == []


# ---------------------------------------------------------------------------
# Test 5 — Capa 0.5: rechazo por marcas distintas
# ---------------------------------------------------------------------------

def test_capa_05_rechaza_marcas_distintas(fake_db):
    """
    Dos productos textualmente idénticos pero con marcas distintas
    (Stanley vs Bosch) deben ser rechazados por la Capa 0.5 ANTES
    de llegar a la Capa 1 (unit normalizer) o 1.5 (graph cross).
    """
    a = _mock_producto(100, "Perno hexagonal 1/2 x 3 zincado", marca="Stanley")
    b = _mock_producto(101, "Perno hexagonal 1/2 x 3 zincado", marca="Bosch")

    # Si alguna capa posterior fuera invocada, se verá en el método devuelto
    with patch.object(ai_matcher, "generar_y_guardar_embedding") as mock_emb, \
         patch.object(ai_matcher, "compare_units") as mock_units:
        resultado = asyncio.run(comparar_productos(a, b, fake_db))

    assert resultado.es_mismo_producto is False
    assert resultado.confidence_score == 0.0
    assert resultado.metodo == "marca_rechazo"
    assert "stanley" in resultado.razon.lower() or "bosch" in resultado.razon.lower()
    # Capa 1 y Capa 2 NUNCA deben haberse ejecutado
    mock_units.assert_not_called()
    mock_emb.assert_not_called()
    # Lineage debe documentarlo
    assert resultado.lineage["marca_check"]["compatible"] is False


def test_capa_05_acepta_marcas_sinonimas(fake_db, _bypass_unit_normalizer):
    """
    Marcas que son sinónimos según el diccionario JSON (ej. 'stanley' y
    'Stanley Tools') NO deben bloquear el pipeline — debe avanzar a capas
    posteriores.
    """
    a = _mock_producto(102, "Perno hexagonal 1/2 x 3 zincado", marca="stanley")
    b = _mock_producto(103, "Perno hexagonal 1/2 x 3 zincado", marca="Stanley Tools")

    resultado = asyncio.run(comparar_productos(a, b, fake_db))
    assert resultado.metodo != "marca_rechazo"
    assert resultado.lineage["marca_check"]["compatible"] is True


# ---------------------------------------------------------------------------
# Test 6 — Capa 1.25 + 1.5: pulgadas ≡ milímetros (match, no rechazo)
# ---------------------------------------------------------------------------

def test_capa_125_equivalencia_pulgadas_mm(fake_db, _bypass_unit_normalizer):
    """
    "Golilla plana 1/2\"" vs "Golilla plana 12.7mm" deben resolver como
    nodos equivalentes tras la normalización a mm (Capa 1.25), y por
    tanto NO ser rechazados por la Capa 1.5.
    """
    a = _mock_producto(200, 'Golilla plana 1/2" acero', marca="Stanley")
    b = _mock_producto(201, "Golilla plana 12.7mm acero", marca="Stanley")

    resultado = asyncio.run(comparar_productos(a, b, fake_db))

    # Capa 1.5 no debe rechazar
    assert resultado.metodo != "graph_cross_rechazo", (
        f"Capa 1.5 debió aceptar 1/2\" ≡ 12.7mm; resultado={resultado}"
    )
    assert resultado.lineage["graph_cross"]["compatible"] is True
    assert resultado.lineage["graph_cross"]["conflictos"] == []


def test_to_millimeters_directo():
    """Unit test del normalizador a mm."""
    from modulos.compras.unit_normalizer import to_millimeters, mm_equivalent

    assert abs(to_millimeters('1/2"') - 12.7) < 0.01
    assert abs(to_millimeters('1/2 pulg') - 12.7) < 0.01
    assert abs(to_millimeters("M6") - 6.0) < 0.01
    assert abs(to_millimeters("50mm") - 50.0) < 0.01
    assert abs(to_millimeters("5cm") - 50.0) < 0.01
    assert mm_equivalent('1/2"', "12.7mm")
    assert mm_equivalent("M8", "8mm")
    assert not mm_equivalent("M6", "M8")
