"""
Normalizador de Unidades — quantulum3 + pint

Reemplaza la detección regex de unidades incompatibles con una pipeline
de procesamiento de lenguaje natural para cantidades físicas.

PIPELINE:
  1. quantulum3 extrae magnitudes del texto no estructurado (español)
  2. pint convierte a unidades base SI para comparación matemática
  3. Lógica de compatibilidad decide si dos productos son comparables

REFERENCIA:
  - quantulum3: https://github.com/nielstron/quantulum3
  - pint: https://pint.readthedocs.io/
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import pint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Registro de unidades pint — con extensiones para ferretería chilena
# ---------------------------------------------------------------------------

ureg = pint.UnitRegistry()

# Unidades chilenas / coloquiales para construcción
_CUSTOM_DEFS = [
    "pulgada = inch",
    "pulg = inch",
    'plg = inch',
    "vara = 0.836 * meter",
    "pie = foot",
    "libra = pound",
    "lb = pound",
    # Unidades de conteo / envase (dimensionless con escala)
    "unidad = [] = un = u = und = uni",
    "pieza = unidad = pza = pz",
    "par = 2 * unidad",
    "docena = 12 * unidad",
    "ciento = 100 * unidad",
    "millar = 1000 * unidad",
    # Unidades de venta típicas en ferretería chilena
    "tira = unidad = tiras",            # perfiles, varillas, listones
    "plancha = unidad = planchas = pln",  # OSB, terciado, melamina, fierro
    "saco = unidad = sacos = sk",         # cemento, áridos, mortero
    "rollo_v = unidad = rollos",          # cables, mallas, mangueras
    "bolsa_v = unidad = bolsas",          # tornillos, pernos a granel
]

for _def in _CUSTOM_DEFS:
    try:
        ureg.define(_def)
    except (pint.errors.RedefinitionError, Exception):
        pass  # Ya definida o conflicto con built-in


# ---------------------------------------------------------------------------
# Capa 1.25 — Normalización de dimensiones a milímetros
# ---------------------------------------------------------------------------
#
# Convierte cualquier expresión de longitud (pulgadas, fracciones, métrica)
# a un valor flotante en MILÍMETROS. Se usa desde Capa 1.5 para que
# "1/2\"" y "12.7mm" sean reconocidos como el mismo nodo.
#
# Tabla de roscas métricas M = diámetro nominal en mm (es igual al número).
# Para casos raros como M1.6, M2.5 se respeta el decimal literal.

# Tolerancia cuando se comparan dos mm "equivalentes"
MM_EQUIVALENCE_TOLERANCE: float = 0.5  # ±0.5 mm ≈ 0.02"

_RE_FRACTION = re.compile(r"^(\d+)\s*/\s*(\d+)$")
_RE_MIXED_FRACTION = re.compile(r"^(\d+)\s+(\d+)/(\d+)$")  # "1 1/2"
_RE_METRIC = re.compile(r"^[mM](\d+(?:\.\d+)?)$")
_RE_INCH_LITERAL = re.compile(
    r"^(\d+(?:\.\d+)?(?:/\d+)?|\d+\s+\d+/\d+)\s*(?:\"|pulg|plg|pulgadas?)?$",
    re.IGNORECASE,
)
_RE_MM_LITERAL = re.compile(r"^(\d+(?:\.\d+)?)\s*mm$", re.IGNORECASE)
_RE_CM_LITERAL = re.compile(r"^(\d+(?:\.\d+)?)\s*cm$", re.IGNORECASE)


def _parse_numeric_token(token: str) -> Optional[float]:
    """Parsea '1/2', '1 1/2', '3.5', '3' a float."""
    if not token:
        return None
    t = token.strip()

    m = _RE_MIXED_FRACTION.match(t)
    if m:
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return whole + (num / den) if den else None

    m = _RE_FRACTION.match(t)
    if m:
        num, den = int(m.group(1)), int(m.group(2))
        return (num / den) if den else None

    try:
        return float(t)
    except ValueError:
        return None


def to_millimeters(value) -> Optional[float]:
    """
    Normaliza una dimensión a milímetros (float).

    Acepta:
      • Números (int/float)        → se asumen mm si > 0.5, si no se asumen pulgadas
      • Strings 'M6', 'M8', 'M1.6' → mm directo (norma ISO: M<d> == d mm)
      • Strings '1/2', '3/8', '1'  → pulgadas → mm (×25.4)
      • Strings '1/2"', '1 1/2 pulg', '3/8 plg' → pulgadas → mm
      • Strings '50mm', '12.7mm'   → mm directo
      • Strings '5cm'              → cm → mm

    Returns:
        float en mm, o None si no se pudo parsear.
    """
    if value is None:
        return None

    # Número puro → heurística: valores pequeños (<1) se asumen pulgadas
    if isinstance(value, (int, float)):
        v = float(value)
        # Rangos ambiguos los dejamos tal cual en mm
        return v

    s = str(value).strip()
    if not s:
        return None

    # Normalizamos comillas curvas y espacios
    s_clean = s.replace("“", '"').replace("”", '"').replace("''", '"').strip()

    # 1) mm literal
    m = _RE_MM_LITERAL.match(s_clean)
    if m:
        return float(m.group(1))

    # 2) cm literal
    m = _RE_CM_LITERAL.match(s_clean)
    if m:
        return float(m.group(1)) * 10.0

    # 3) Métrica M<d>
    m = _RE_METRIC.match(s_clean)
    if m:
        return float(m.group(1))

    # 4) Pulgadas (con o sin sufijo) — incluye fracciones y mixtas
    m = _RE_INCH_LITERAL.match(s_clean)
    if m:
        parsed = _parse_numeric_token(m.group(1))
        if parsed is not None:
            has_suffix = any(x in s_clean.lower() for x in ('"', "pulg", "plg", "pulgada"))
            if has_suffix or "/" in s_clean:
                # Explicitamente pulgadas (o fracción → convencionalmente pulgada en ferretería)
                return parsed * 25.4
            # Sin sufijo y sin fracción → ambigüo; devolvemos mm literal
            return parsed

    # 5) Fallback genérico: intentar con pint
    try:
        q = ureg.parse_expression(s_clean)
        if hasattr(q, "to"):
            return float(q.to("millimeter").magnitude)
    except Exception:
        pass

    return None


def mm_equivalent(a, b, tol: float = MM_EQUIVALENCE_TOLERANCE) -> bool:
    """True si dos dimensiones (en cualquier formato) son equivalentes en mm."""
    ma = to_millimeters(a)
    mb = to_millimeters(b)
    if ma is None or mb is None:
        return False
    return abs(ma - mb) <= tol


# ---------------------------------------------------------------------------
# Dataclass de resultado
# ---------------------------------------------------------------------------

@dataclass
class ParsedQuantity:
    """Cantidad física extraída de un texto de producto."""
    value: float
    unit_str: str           # Unidad tal como apareció en el texto
    unit_pint: Optional[pint.Quantity] = None  # Convertida a pint (puede fallar)
    surface_form: str = ""  # Texto original que generó esta cantidad
    source: str = ""        # "nombre" | "unidad_campo" | "precio_ratio"
    is_count: bool = False  # True si es conteo (pack, caja, unidades)


@dataclass
class UnitComparisonResult:
    """Resultado de comparar unidades de dos productos."""
    compatible: bool
    razon: str
    qty_a: Optional[ParsedQuantity] = None
    qty_b: Optional[ParsedQuantity] = None
    ratio: Optional[float] = None   # ratio entre cantidades si son de misma dimensión
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Extracción con quantulum3
# ---------------------------------------------------------------------------

def _safe_quantulum_parse(text: str) -> list:
    """Wrapper seguro para quantulum3 que captura errores."""
    try:
        from quantulum3 import parser as q3_parser
        return q3_parser.parse(text)
    except Exception as exc:
        logger.debug("quantulum3 falló para '%s': %s", text[:80], exc)
        return []


# ---------------------------------------------------------------------------
# Patrones regex de respaldo (para lo que quantulum3 no captura)
# ---------------------------------------------------------------------------

_PACK_PATTERNS = re.compile(
    r'(?:pack|caja|bolsa|rollo|paquete|saco|estuche|set|kit|display|tira|plancha)\s*'
    r'(?:de\s*)?(?:x\s*)?(\d+)\s*(?:un(?:idades?)?|pzas?|piezas?|u\.?)?|'
    r'x\s*(\d+)\s*(?:un(?:idades?)?|pzas?)?|'
    r'(\d+)\s*(?:un(?:idades?)?|pzas?|piezas?|tiras?|planchas?|sacos?|cientos?|millares?)\b',
    re.IGNORECASE,
)

_WEIGHT_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(kg|g|gr|gramos?|kilos?|kilogramos?|lb|libras?)\b',
    re.IGNORECASE,
)

_LENGTH_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(mm|cm|m|mts?|metros?|pulgadas?|pulg|plg|")\b',
    re.IGNORECASE,
)

_VOLUME_PATTERN = re.compile(
    r'(\d+(?:[.,]\d+)?)\s*(ml|lt?|litros?|cc|gal|galones?)\b',
    re.IGNORECASE,
)

# Mapeo de strings coloquiales a unidades pint
_UNIT_MAP = {
    # Peso
    "kg": "kilogram", "kilo": "kilogram", "kilos": "kilogram", "kilogramo": "kilogram",
    "kilogramos": "kilogram", "g": "gram", "gr": "gram", "gramo": "gram",
    "gramos": "gram", "lb": "pound", "libra": "pound", "libras": "pound",
    # Longitud
    "mm": "millimeter", "cm": "centimeter", "m": "meter", "mt": "meter",
    "mts": "meter", "metro": "meter", "metros": "meter",
    "pulgada": "inch", "pulgadas": "inch", "pulg": "inch", "plg": "inch",
    '"': "inch",
    # Volumen
    "ml": "milliliter", "l": "liter", "lt": "liter", "litro": "liter",
    "litros": "liter", "cc": "milliliter", "gal": "gallon", "galon": "gallon",
    "galones": "gallon",
    # Conteo
    "un": "unidad", "und": "unidad", "uni": "unidad", "unidad": "unidad",
    "unidades": "unidad", "pza": "unidad", "pz": "unidad", "pieza": "unidad",
    "piezas": "unidad",
    # Conteo / venta chileno
    "tira": "tira", "tiras": "tira",
    "plancha": "plancha", "planchas": "plancha", "pln": "plancha",
    "saco": "saco", "sacos": "saco", "sk": "saco",
    "ciento": "ciento", "cientos": "ciento",
    "millar": "millar", "millares": "millar",
}


def _regex_extract_quantity(text: str) -> Optional[ParsedQuantity]:
    """Extracción de respaldo con regex cuando quantulum3 no encuentra nada."""
    text_lower = text.lower()

    # 1. Pack / conteo
    for m in _PACK_PATTERNS.finditer(text_lower):
        for g in m.groups():
            if g:
                val = int(g)
                if val > 1:
                    return ParsedQuantity(
                        value=float(val),
                        unit_str="unidad",
                        unit_pint=ureg.Quantity(val, "unidad"),
                        surface_form=m.group(0),
                        source="nombre_regex",
                        is_count=True,
                    )

    # 2. Peso
    m = _WEIGHT_PATTERN.search(text_lower)
    if m:
        val = float(m.group(1).replace(",", "."))
        unit_raw = m.group(2).lower()
        pint_unit = _UNIT_MAP.get(unit_raw, "kilogram")
        try:
            return ParsedQuantity(
                value=val,
                unit_str=unit_raw,
                unit_pint=ureg.Quantity(val, pint_unit),
                surface_form=m.group(0),
                source="nombre_regex",
            )
        except pint.errors.UndefinedUnitError:
            pass

    # 3. Longitud
    m = _LENGTH_PATTERN.search(text_lower)
    if m:
        val = float(m.group(1).replace(",", "."))
        unit_raw = m.group(2).lower()
        pint_unit = _UNIT_MAP.get(unit_raw, "meter")
        try:
            return ParsedQuantity(
                value=val,
                unit_str=unit_raw,
                unit_pint=ureg.Quantity(val, pint_unit),
                surface_form=m.group(0),
                source="nombre_regex",
            )
        except pint.errors.UndefinedUnitError:
            pass

    # 4. Volumen
    m = _VOLUME_PATTERN.search(text_lower)
    if m:
        val = float(m.group(1).replace(",", "."))
        unit_raw = m.group(2).lower()
        pint_unit = _UNIT_MAP.get(unit_raw, "liter")
        try:
            return ParsedQuantity(
                value=val,
                unit_str=unit_raw,
                unit_pint=ureg.Quantity(val, pint_unit),
                surface_form=m.group(0),
                source="nombre_regex",
            )
        except pint.errors.UndefinedUnitError:
            pass

    return None


# ---------------------------------------------------------------------------
# Pipeline principal de extracción
# ---------------------------------------------------------------------------

def extract_quantities(nombre: str, unidad_campo: str = "") -> list[ParsedQuantity]:
    """
    Extrae todas las cantidades físicas de un producto usando quantulum3 + regex.

    Args:
        nombre: Nombre del producto (ej: "Tornillo autoperforante 8x1 Pack 100")
        unidad_campo: Campo 'unidad' del scraper (ej: "Pack", "Kg", "Un")

    Returns:
        Lista de cantidades detectadas, ordenadas por relevancia.
    """
    resultados: list[ParsedQuantity] = []

    # Fase 1: quantulum3 sobre el nombre
    q3_results = _safe_quantulum_parse(nombre)
    for q in q3_results:
        try:
            unit_name = q.unit.name if hasattr(q, 'unit') and q.unit else "dimensionless"
            pint_unit_str = _UNIT_MAP.get(unit_name.lower(), unit_name)
            try:
                pint_qty = ureg.Quantity(q.value, pint_unit_str)
            except (pint.errors.UndefinedUnitError, pint.errors.DimensionalityError):
                pint_qty = None

            resultados.append(ParsedQuantity(
                value=q.value,
                unit_str=unit_name,
                unit_pint=pint_qty,
                surface_form=q.surface if hasattr(q, 'surface') else str(q),
                source="quantulum3",
                is_count=unit_name.lower() in ("dimensionless", "unidad", "unit", "piece"),
            ))
        except Exception as exc:
            logger.debug("Error procesando resultado quantulum3: %s", exc)

    # Fase 2: regex de respaldo sobre el nombre
    regex_qty = _regex_extract_quantity(nombre)
    if regex_qty:
        # Solo agregar si quantulum3 no encontró algo similar
        ya_encontrado = any(
            abs(r.value - regex_qty.value) < 0.01 and r.unit_str == regex_qty.unit_str
            for r in resultados
        )
        if not ya_encontrado:
            resultados.append(regex_qty)

    # Fase 3: campo 'unidad' del scraper
    if unidad_campo and unidad_campo.strip():
        campo_lower = unidad_campo.strip().lower()
        # Intentar parsear el campo como cantidad
        campo_qty = _regex_extract_quantity(unidad_campo)
        if campo_qty:
            campo_qty.source = "unidad_campo"
            resultados.append(campo_qty)
        elif campo_lower in _UNIT_MAP:
            # Campo es solo una unidad sin cantidad (ej: "Kg", "Un")
            pint_unit = _UNIT_MAP[campo_lower]
            try:
                resultados.append(ParsedQuantity(
                    value=1.0,
                    unit_str=campo_lower,
                    unit_pint=ureg.Quantity(1.0, pint_unit),
                    surface_form=unidad_campo,
                    source="unidad_campo",
                    is_count=pint_unit == "unidad",
                ))
            except pint.errors.UndefinedUnitError:
                pass

    return resultados


def get_selling_quantity(nombre: str, unidad_campo: str = "") -> Optional[ParsedQuantity]:
    """
    Retorna la cantidad de venta más relevante para un producto.
    Prioriza: pack/bulk > peso > volumen > campo unidad > longitud.

    IMPORTANTE: No confundir dimensiones del producto (ej: "2 pulgadas")
    con la unidad de venta. Las dimensiones son atributos del producto,
    la unidad de venta es cómo se compra (pack, kg, metro, unidad).
    """
    all_qty = extract_quantities(nombre, unidad_campo)
    if not all_qty:
        return None

    # Priorizar packs (is_count con value > 1)
    packs = [q for q in all_qty if q.is_count and q.value > 1]
    if packs:
        return max(packs, key=lambda q: q.value)

    # Luego pesos (señal fuerte de unidad de venta)
    weights = [q for q in all_qty if q.unit_pint is not None and _safe_check(q.unit_pint, "[mass]")]
    if weights:
        return weights[0]

    # Luego volumen
    volumes = [q for q in all_qty if q.unit_pint is not None and _safe_check(q.unit_pint, "[length] ** 3")]
    if volumes:
        return volumes[0]

    # Campo unidad del scraper tiene prioridad sobre dimensiones del nombre
    campo_qty = [q for q in all_qty if q.source == "unidad_campo"]
    if campo_qty:
        return campo_qty[0]

    # Longitudes del nombre son probablemente dimensiones del producto, NO unidad de venta
    # Solo usar si parece ser longitud de venta (ej: "rollo 25 m", "metro lineal")
    lengths = [q for q in all_qty if q.unit_pint is not None and _safe_check(q.unit_pint, "[length]")]
    selling_length_keywords = ["rollo", "metro lineal", "bobina", "tramo"]
    nombre_lower = nombre.lower()
    if lengths and any(kw in nombre_lower for kw in selling_length_keywords):
        return lengths[0]

    # Si solo hay cantidades de conteo == 1, retornarla
    unit_qty = [q for q in all_qty if q.is_count and q.value == 1]
    if unit_qty:
        return unit_qty[0]

    return None


def _safe_check(qty: 'pint.Quantity', dim: str) -> bool:
    """Check dimensionality safely."""
    try:
        return qty.check(dim)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Comparación de unidades entre dos productos
# ---------------------------------------------------------------------------

def compare_units(
    nombre_a: str, unidad_a: str,
    nombre_b: str, unidad_b: str,
    precio_a: float = 0, precio_b: float = 0,
) -> UnitComparisonResult:
    """
    Compara las unidades de venta de dos productos.

    Retorna UnitComparisonResult con:
    - compatible: True si se pueden comparar directamente
    - razon: Explicación humana de por qué son o no compatibles
    - ratio: Factor de conversión si aplica
    """
    t0 = time.perf_counter()

    qty_a = get_selling_quantity(nombre_a, unidad_a)
    qty_b = get_selling_quantity(nombre_b, unidad_b)

    latency = (time.perf_counter() - t0) * 1000

    # Si ninguno tiene cantidad detectada → no podemos rechazar, dejar pasar
    if qty_a is None and qty_b is None:
        return UnitComparisonResult(
            compatible=True,
            razon="Sin cantidades detectadas en ningún producto — no se puede determinar incompatibilidad",
            latency_ms=latency,
        )

    # Si solo uno tiene cantidad → probable incompatibilidad si es pack
    if qty_a is None and qty_b is not None:
        if qty_b.is_count and qty_b.value > 1:
            return UnitComparisonResult(
                compatible=False,
                razon=f"Producto B es pack de {int(qty_b.value)} {qty_b.unit_str}, Producto A parece unitario",
                qty_a=qty_a, qty_b=qty_b, latency_ms=latency,
            )
        return UnitComparisonResult(
            compatible=True,
            razon=f"Solo B tiene cantidad detectada ({qty_b.surface_form}) — no concluyente",
            qty_a=qty_a, qty_b=qty_b, latency_ms=latency,
        )

    if qty_b is None and qty_a is not None:
        if qty_a.is_count and qty_a.value > 1:
            return UnitComparisonResult(
                compatible=False,
                razon=f"Producto A es pack de {int(qty_a.value)} {qty_a.unit_str}, Producto B parece unitario",
                qty_a=qty_a, qty_b=qty_b, latency_ms=latency,
            )
        return UnitComparisonResult(
            compatible=True,
            razon=f"Solo A tiene cantidad detectada ({qty_a.surface_form}) — no concluyente",
            qty_a=qty_a, qty_b=qty_b, latency_ms=latency,
        )

    # Ambos tienen cantidad — comparar con pint
    if qty_a.unit_pint is not None and qty_b.unit_pint is not None:
        try:
            # ¿Misma dimensionalidad? (masa vs longitud vs conteo)
            if qty_a.unit_pint.dimensionality != qty_b.unit_pint.dimensionality:
                return UnitComparisonResult(
                    compatible=False,
                    razon=(
                        f"Dimensiones incompatibles: A={qty_a.value} {qty_a.unit_str} "
                        f"({qty_a.unit_pint.dimensionality}) vs "
                        f"B={qty_b.value} {qty_b.unit_str} ({qty_b.unit_pint.dimensionality})"
                    ),
                    qty_a=qty_a, qty_b=qty_b, latency_ms=latency,
                )

            # Misma dimensionalidad — calcular ratio
            ratio = (qty_a.unit_pint / qty_b.unit_pint).to("").magnitude
            if abs(ratio - 1.0) < 0.05:
                return UnitComparisonResult(
                    compatible=True,
                    razon=f"Misma cantidad: {qty_a.value} {qty_a.unit_str} ≈ {qty_b.value} {qty_b.unit_str}",
                    qty_a=qty_a, qty_b=qty_b, ratio=ratio, latency_ms=latency,
                )
            else:
                return UnitComparisonResult(
                    compatible=False,
                    razon=(
                        f"Cantidades diferentes ({ratio:.1f}x): "
                        f"A={qty_a.value} {qty_a.unit_str} vs B={qty_b.value} {qty_b.unit_str}"
                    ),
                    qty_a=qty_a, qty_b=qty_b, ratio=ratio, latency_ms=latency,
                )
        except (pint.errors.DimensionalityError, pint.errors.OffsetUnitCalculusError) as exc:
            logger.debug("pint error comparando unidades: %s", exc)

    # Fallback: comparar por conteo si ambos son is_count
    if qty_a.is_count and qty_b.is_count:
        if qty_a.value == qty_b.value:
            return UnitComparisonResult(
                compatible=True,
                razon=f"Misma cantidad de conteo: {int(qty_a.value)} unidades",
                qty_a=qty_a, qty_b=qty_b, ratio=1.0, latency_ms=latency,
            )
        else:
            ratio = qty_a.value / qty_b.value if qty_b.value > 0 else 0
            return UnitComparisonResult(
                compatible=False,
                razon=f"Pack diferente: A={int(qty_a.value)} vs B={int(qty_b.value)} unidades",
                qty_a=qty_a, qty_b=qty_b, ratio=ratio, latency_ms=latency,
            )

    # Señal de precio como última línea de defensa
    if precio_a > 0 and precio_b > 0:
        price_ratio = max(precio_a, precio_b) / min(precio_a, precio_b)
        if price_ratio > 10:
            return UnitComparisonResult(
                compatible=False,
                razon=(
                    f"Ratio de precios muy alto ({price_ratio:.0f}x) con unidades "
                    f"A='{qty_a.surface_form}' B='{qty_b.surface_form}' — probable diferencia de envase"
                ),
                qty_a=qty_a, qty_b=qty_b, latency_ms=latency,
            )

    return UnitComparisonResult(
        compatible=True,
        razon=f"Unidades no concluyentes: A='{qty_a.surface_form}' B='{qty_b.surface_form}'",
        qty_a=qty_a, qty_b=qty_b, latency_ms=latency,
    )


# ---------------------------------------------------------------------------
# Texto normalizado para embeddings (incluye unidad parseada)
# ---------------------------------------------------------------------------

def normalized_unit_text(nombre: str, unidad_campo: str = "") -> str:
    """
    Genera una representación textual normalizada de la unidad de venta,
    útil para mejorar la calidad de embeddings.

    Ej: "Tornillo 8x1 Pack 100 un" → "100 unidad"
        "Adhesivo 300ml"            → "300 milliliter"
        "Clavo 2 pulgadas"         → "1 unidad" (sin pack detectado)
    """
    qty = get_selling_quantity(nombre, unidad_campo)
    if qty and qty.unit_pint:
        return f"{qty.value:g} {qty.unit_pint.units}"
    elif qty:
        return f"{qty.value:g} {qty.unit_str}"
    return "1 unidad"
