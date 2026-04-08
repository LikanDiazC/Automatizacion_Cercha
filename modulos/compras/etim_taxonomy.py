"""
Taxonomía ETIM (European Technical Information Model) para materiales de construcción.

Define clases de productos con atributos técnicos predefinidos,
permitiendo clasificación estructurada y comparación semántica.

REFERENCIA: https://www.etim-international.com/
Adaptado al mercado chileno de ferretería/construcción.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses ETIM
# ---------------------------------------------------------------------------

@dataclass
class ETIMAttribute:
    """Atributo técnico de una clase ETIM."""
    code: str           # Ej: "EF000001"
    name: str           # Ej: "Diámetro nominal"
    attr_type: str      # "numeric" | "alpha" | "logical" | "range"
    unit: str = ""      # Ej: "mm", "inch", ""
    allowed_values: list[str] = field(default_factory=list)
    is_critical: bool = False  # Si cambia el valor, ¿cambia la identidad del producto?


@dataclass
class ETIMClass:
    """Clase de producto ETIM."""
    code: str           # Ej: "EC010101"
    name: str           # Ej: "Tornillo autoperforante"
    group: str          # Familia / grupo padre
    description: str = ""
    attributes: list[ETIMAttribute] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)  # Para clasificación por texto


@dataclass
class ClassificationResult:
    """Resultado de clasificar un producto."""
    etim_class: Optional[ETIMClass]
    confidence: float       # 0.0 - 1.0
    matched_keywords: list[str] = field(default_factory=list)
    extracted_attrs: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Catálogo ETIM — Clases para ferretería chilena
# ---------------------------------------------------------------------------

# Atributos reutilizables
_ATTR_DIAMETRO = ETIMAttribute("EF000001", "Diámetro", "numeric", "mm", is_critical=True)
_ATTR_LARGO = ETIMAttribute("EF000002", "Largo", "numeric", "mm", is_critical=True)
_ATTR_MATERIAL = ETIMAttribute(
    "EF000003", "Material", "alpha", "",
    ["acero", "acero inoxidable", "bronce", "aluminio", "galvanizado", "cobre"],
    is_critical=True,
)
_ATTR_ACABADO = ETIMAttribute(
    "EF000004", "Acabado", "alpha", "",
    ["zincado", "pavonado", "galvanizado", "cromado", "negro", "blanco", "natural"],
    is_critical=True,
)
_ATTR_CABEZA = ETIMAttribute(
    "EF000005", "Tipo cabeza", "alpha", "",
    ["hexagonal", "phillips", "allen", "estrella", "torx", "avellanada", "redonda", "plana"],
    is_critical=True,
)
_ATTR_ROSCA = ETIMAttribute(
    "EF000006", "Tipo rosca", "alpha", "",
    ["métrica", "whitworth", "autoperforante", "madera", "máquina"],
    is_critical=True,
)
_ATTR_NORMA = ETIMAttribute("EF000007", "Norma", "alpha", "", ["DIN", "ISO", "SAE", "ASTM"])
_ATTR_RESISTENCIA = ETIMAttribute("EF000008", "Grado resistencia", "alpha", "", ["4.8", "8.8", "10.9", "12.9", "A2", "A4"])
_ATTR_ESPESOR = ETIMAttribute("EF000009", "Espesor", "numeric", "mm", is_critical=True)
_ATTR_ANCHO = ETIMAttribute("EF000010", "Ancho", "numeric", "mm", is_critical=True)
_ATTR_VOLUMEN = ETIMAttribute("EF000011", "Volumen", "numeric", "ml")
_ATTR_COLOR = ETIMAttribute("EF000012", "Color", "alpha", "", is_critical=False)
_ATTR_POTENCIA = ETIMAttribute("EF000013", "Potencia", "numeric", "W", is_critical=True)
_ATTR_VOLTAJE = ETIMAttribute("EF000014", "Voltaje", "numeric", "V", is_critical=True)


# Catálogo de clases
ETIM_CLASSES: dict[str, ETIMClass] = {}

def _register(*classes: ETIMClass) -> None:
    for c in classes:
        ETIM_CLASSES[c.code] = c

_register(
    # ═══════════════════════════════════════════════════
    # TORNILLOS
    # ═══════════════════════════════════════════════════
    ETIMClass(
        "EC010101", "Tornillo autoperforante", "Tornillos",
        "Tornillos con punta de broca para perforar y fijar en metal o madera",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL, _ATTR_ACABADO, _ATTR_CABEZA],
        ["autoperforante", "autoroscante", "drywall", "volcanita", "gyplac", "punta broca"],
    ),
    ETIMClass(
        "EC010102", "Tornillo para madera", "Tornillos",
        "Tornillos con rosca para madera (punta aguda)",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL, _ATTR_ACABADO, _ATTR_CABEZA],
        ["madera", "aglomerado", "mdf", "melamina", "soberbio", "chipboard"],
    ),
    ETIMClass(
        "EC010103", "Tornillo de máquina", "Tornillos",
        "Tornillos con rosca métrica para usar con tuerca",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL, _ATTR_ACABADO, _ATTR_CABEZA, _ATTR_ROSCA, _ATTR_RESISTENCIA],
        ["maquina", "metrico", "métrico", "din", "iso"],
    ),
    ETIMClass(
        "EC010104", "Tornillo para concreto", "Tornillos",
        "Tornillos para anclaje directo en concreto/hormigón",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL, _ATTR_ACABADO],
        ["concreto", "hormigon", "hormigón", "tapcon", "anclaje", "mamposteria", "mampostería"],
    ),

    # ═══════════════════════════════════════════════════
    # CLAVOS
    # ═══════════════════════════════════════════════════
    ETIMClass(
        "EC010201", "Clavo liso", "Clavos",
        "Clavos lisos de acero para madera",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL, _ATTR_ACABADO],
        ["clavo", "liso", "comun", "común", "cabeza plana"],
    ),
    ETIMClass(
        "EC010202", "Clavo helicoidal", "Clavos",
        "Clavos con cuerpo helicoidal para mayor sujeción",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL],
        ["helicoidal", "espiral", "twist"],
    ),
    ETIMClass(
        "EC010203", "Clavo de acero", "Clavos",
        "Clavos de acero endurecido para concreto",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL],
        ["acero", "concreto", "hormigon", "hormigón", "impacto"],
    ),

    # ═══════════════════════════════════════════════════
    # PERNOS
    # ═══════════════════════════════════════════════════
    ETIMClass(
        "EC010301", "Perno hexagonal", "Pernos",
        "Perno con cabeza hexagonal y rosca parcial o total",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL, _ATTR_ACABADO, _ATTR_RESISTENCIA, _ATTR_NORMA],
        ["perno", "hexagonal", "hex", "maquina", "din 931", "din 933"],
    ),
    ETIMClass(
        "EC010302", "Perno de anclaje", "Pernos",
        "Perno con expansor para anclaje en concreto",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL],
        ["anclaje", "expansion", "expansión", "wedge", "hilti"],
    ),
    ETIMClass(
        "EC010303", "Perno estructural", "Pernos",
        "Perno de alta resistencia para estructuras metálicas",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL, _ATTR_RESISTENCIA, _ATTR_NORMA],
        ["estructural", "alta resistencia", "astm a325", "astm a490", "a325", "a490"],
    ),

    # ═══════════════════════════════════════════════════
    # TUERCAS Y GOLILLAS
    # ═══════════════════════════════════════════════════
    ETIMClass(
        "EC010401", "Tuerca hexagonal", "Tuercas y Golillas",
        "Tuerca hexagonal estándar",
        [_ATTR_DIAMETRO, _ATTR_MATERIAL, _ATTR_ACABADO, _ATTR_RESISTENCIA],
        ["tuerca", "hexagonal", "hex"],
    ),
    ETIMClass(
        "EC010402", "Golilla plana", "Tuercas y Golillas",
        "Arandela/golilla plana estándar",
        [_ATTR_DIAMETRO, _ATTR_ESPESOR, _ATTR_MATERIAL],
        ["golilla", "arandela", "washer", "plana"],
    ),
    ETIMClass(
        "EC010403", "Golilla de presión", "Tuercas y Golillas",
        "Arandela/golilla de presión (split lock washer)",
        [_ATTR_DIAMETRO, _ATTR_MATERIAL],
        ["presion", "presión", "lock", "split", "grower"],
    ),

    # ═══════════════════════════════════════════════════
    # TIRAFONDOS
    # ═══════════════════════════════════════════════════
    ETIMClass(
        "EC010501", "Tirafondo hexagonal", "Tirafondos",
        "Tirafondo con cabeza hexagonal para madera pesada",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL, _ATTR_ACABADO],
        ["tirafondo", "lag screw", "lag bolt", "hexagonal", "madera"],
    ),
    ETIMClass(
        "EC010502", "Tirafondo para techo", "Tirafondos",
        "Tirafondo con sello de neopreno para techumbre",
        [_ATTR_DIAMETRO, _ATTR_LARGO, _ATTR_MATERIAL],
        ["techo", "techumbre", "neopreno", "sello", "cubierta"],
    ),

    # ═══════════════════════════════════════════════════
    # PLACAS Y CONECTORES
    # ═══════════════════════════════════════════════════
    ETIMClass(
        "EC010601", "Placa de unión", "Placas y Conectores",
        "Placa metálica perforada para unión de maderas",
        [_ATTR_LARGO, _ATTR_ANCHO, _ATTR_ESPESOR, _ATTR_MATERIAL],
        ["placa", "union", "unión", "perforada", "nail plate"],
    ),
    ETIMClass(
        "EC010602", "Conector angular", "Placas y Conectores",
        "Conector metálico en ángulo (escuadra)",
        [_ATTR_LARGO, _ATTR_ANCHO, _ATTR_ESPESOR, _ATTR_MATERIAL],
        ["conector", "angular", "escuadra", "angulo", "ángulo", "bracket", "simpson"],
    ),

    # ═══════════════════════════════════════════════════
    # ADHESIVOS Y SELLANTES
    # ═══════════════════════════════════════════════════
    ETIMClass(
        "EC010701", "Adhesivo de montaje", "Adhesivos y Sellantes",
        "Adhesivo para montaje y fijación",
        [_ATTR_VOLUMEN, _ATTR_COLOR],
        ["adhesivo", "montaje", "no mas clavos", "no más clavos", "pegamento", "construccion", "construcción"],
    ),
    ETIMClass(
        "EC010702", "Silicona", "Adhesivos y Sellantes",
        "Sellante de silicona",
        [_ATTR_VOLUMEN, _ATTR_COLOR],
        ["silicona", "sellante", "sello", "sellador", "acético", "neutro"],
    ),
    ETIMClass(
        "EC010703", "Espuma expansiva", "Adhesivos y Sellantes",
        "Espuma de poliuretano expansiva",
        [_ATTR_VOLUMEN],
        ["espuma", "expansiva", "poliuretano", "pu"],
    ),
)


# ---------------------------------------------------------------------------
# Extracción de atributos — Pipeline NER (spaCy)
# ---------------------------------------------------------------------------
#
# Reemplaza el enfoque puramente regex por un pipeline basado en spaCy
# `Matcher` + `PhraseMatcher` operando sobre tokens. Esto nos da:
#   - Robustez frente a espaciados/puntuación
#   - Separación limpia entre “tokenización” y “extracción semántica”
#   - Base para migrar a un NER entrenado (ej. custom ner pipeline)
#
# Si spaCy no está instalado, hacemos fallback a los regex legacy para
# no romper el pipeline ni los tests en CI mínimos.

_MATERIAL_KEYWORDS = {
    "acero inoxidable": ["inoxidable", "inox", "stainless", "a2", "a4", "304", "316"],
    "acero galvanizado": ["galvanizado", "galvanized", "hdg"],
    "acero zincado": ["zincado", "zinc", "zn", "electrozincado"],
    "acero pavonado": ["pavonado", "fosfatado", "negro", "black"],
    "bronce": ["bronce", "bronze", "latón", "laton", "brass"],
    "aluminio": ["aluminio", "aluminum"],
    "acero": ["acero", "steel"],
}

_CABEZA_VOCAB = [
    "hexagonal", "hex", "phillips", "allen", "torx", "estrella",
    "avellanada", "redonda", "plana", "pan",
]

# Regex fallback (también usados por el tokenizador de spaCy para dimensiones
# que spaCy tokeniza como un solo token — ej. "8x1", "M6x20", "1/4").
_RE_NXN = re.compile(r"^(\d+(?:\.\d+)?(?:/\d+)?)[xX×](\d+(?:\.\d+)?(?:/\d+)?)$")
_RE_METRIC_NXN = re.compile(r"^[mM](\d+(?:\.\d+)?)[xX×](\d+(?:\.\d+)?)$")
_RE_MM = re.compile(r"^(\d+(?:\.\d+)?)\s*mm$", re.IGNORECASE)
_RE_INCH = re.compile(r"^(\d+/\d+|\d+)(?:\"|pulg|plg|pulgadas?)?$", re.IGNORECASE)


_SPACY_NLP = None          # Pipeline cargado perezosamente
_SPACY_MATCHER = None
_SPACY_AVAILABLE = None    # None = sin comprobar; True/False luego


def _load_spacy_pipeline():
    """
    Carga perezosa de un pipeline spaCy ligero.

    Estrategia:
      1. Intentar `es_core_news_sm` (español, NER real si está disponible)
      2. Fallback a `spacy.blank("es")` (tokenizer-only) que es suficiente
         para Matcher/PhraseMatcher sobre dimensiones/materiales.
      3. Si spaCy no está instalado → None (fallback a regex legacy).

    Returns:
        (nlp, matcher) o (None, None) si no hay spaCy.
    """
    global _SPACY_NLP, _SPACY_MATCHER, _SPACY_AVAILABLE
    if _SPACY_AVAILABLE is False:
        return None, None
    if _SPACY_NLP is not None:
        return _SPACY_NLP, _SPACY_MATCHER

    try:
        import spacy
        from spacy.matcher import Matcher
    except ImportError:
        logger.warning("spaCy no disponible — usando fallback regex")
        _SPACY_AVAILABLE = False
        return None, None

    nlp = None
    try:
        nlp = spacy.load("es_core_news_sm", disable=["parser", "lemmatizer"])
        logger.info("spaCy pipeline 'es_core_news_sm' cargado")
    except Exception:
        try:
            nlp = spacy.blank("es")
            logger.info("spaCy pipeline blank('es') cargado (fallback)")
        except Exception as exc:
            logger.warning("No se pudo cargar ningún pipeline spaCy: %s", exc)
            _SPACY_AVAILABLE = False
            return None, None

    matcher = Matcher(nlp.vocab)

    # Patrón 1 — Dimensión NxN (ej: "8x1", "1/4x2"), con o sin sufijo
    matcher.add("DIM_NXN", [
        [{"TEXT": {"REGEX": r"^\d+(?:\.\d+)?(?:/\d+)?$"}},
         {"LOWER": {"IN": ["x", "×"]}},
         {"TEXT": {"REGEX": r"^\d+(?:\.\d+)?(?:/\d+)?$"}}],
        # Caso ya tokenizado como un único token "8x1"
        [{"TEXT": {"REGEX": r"^\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?$"}}],
    ])

    # Patrón 2 — Dimensión métrica M<d>x<l> (ej: "M6x20")
    matcher.add("DIM_METRIC", [
        [{"TEXT": {"REGEX": r"^[mM]\d+(?:\.\d+)?[xX×]\d+(?:\.\d+)?$"}}],
        [{"LOWER": {"REGEX": r"^m\d+$"}},
         {"LOWER": {"IN": ["x", "×"]}},
         {"TEXT": {"REGEX": r"^\d+(?:\.\d+)?$"}}],
    ])

    # Patrón 3 — Medida en milímetros ("50mm" o "50 mm")
    matcher.add("DIM_MM", [
        [{"TEXT": {"REGEX": r"^\d+(?:\.\d+)?mm$"}}],
        [{"LIKE_NUM": True}, {"LOWER": "mm"}],
    ])

    # Patrón 4 — Medida en pulgadas ("1/4\"" o "1/4 pulg")
    matcher.add("DIM_INCH", [
        [{"TEXT": {"REGEX": r"^\d+/\d+$"}},
         {"LOWER": {"IN": ["\"", "pulg", "plg", "pulgada", "pulgadas"]}}],
        [{"TEXT": {"REGEX": r"^\d+(?:/\d+)?\"$"}}],
    ])

    # Patrón 5 — Material (lista cerrada)
    material_terms = set()
    for kws in _MATERIAL_KEYWORDS.values():
        material_terms.update(k.lower() for k in kws)
    matcher.add("MATERIAL", [
        [{"LOWER": {"IN": sorted(material_terms)}}],
    ])

    # Patrón 6 — Tipo de cabeza
    matcher.add("CABEZA", [
        [{"LOWER": {"IN": _CABEZA_VOCAB}}],
    ])

    _SPACY_NLP = nlp
    _SPACY_MATCHER = matcher
    _SPACY_AVAILABLE = True
    return nlp, matcher


def _material_from_token(token_text: str) -> Optional[str]:
    t = token_text.lower()
    for material, keywords in _MATERIAL_KEYWORDS.items():
        if t in (k.lower() for k in keywords):
            return material
    return None


def _parse_dim_token(text: str) -> dict:
    """
    Dado un token tipo '8x1', 'M6x20', '50mm', '1/4"', devuelve dict parcial.
    """
    out: dict = {}
    t = text.strip()

    m = _RE_METRIC_NXN.match(t)
    if m:
        out["diametro_raw"] = f"M{m.group(1)}"
        out["largo_raw"] = m.group(2)
        return out

    m = _RE_NXN.match(t)
    if m:
        out["diametro_raw"] = m.group(1)
        out["largo_raw"] = m.group(2)
        return out

    m = _RE_MM.match(t)
    if m:
        out["medida_mm"] = float(m.group(1))
        return out

    m = _RE_INCH.match(t)
    if m:
        out["diametro_raw"] = m.group(1)
        return out

    return out


def _extract_with_spacy(nombre: str) -> dict:
    """Extracción usando pipeline spaCy + Matcher."""
    nlp, matcher = _load_spacy_pipeline()
    if nlp is None:
        return _extract_with_regex(nombre)

    attrs: dict = {}
    doc = nlp(nombre)
    matches = matcher(doc)

    for match_id, start, end in matches:
        label = nlp.vocab.strings[match_id]
        span_text = doc[start:end].text

        if label in ("DIM_NXN", "DIM_METRIC", "DIM_MM", "DIM_INCH"):
            # Para spans multi-token, re-aplicamos el parser sobre el texto
            # concatenado sin espacios (ej: "8 x 1" → "8x1").
            compact = span_text.replace(" ", "")
            parsed = _parse_dim_token(compact)
            # No sobreescribir si ya extrajimos una dim más específica
            for k, v in parsed.items():
                attrs.setdefault(k, v)

        elif label == "MATERIAL":
            material = _material_from_token(span_text)
            if material and "material" not in attrs:
                attrs["material"] = material

        elif label == "CABEZA":
            if "cabeza" not in attrs:
                cabeza = span_text.lower()
                attrs["cabeza"] = "hexagonal" if cabeza == "hex" else cabeza

    return attrs


def _extract_with_regex(nombre: str) -> dict:
    """Fallback puro regex (cuando spaCy no está instalado)."""
    attrs: dict = {}
    nombre_lower = nombre.lower()

    # Dimensiones NxN (genérico) — "Perno hex 8x1"
    m = re.search(r"(\d+(?:\.\d+)?(?:/\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?(?:/\d+)?)", nombre)
    if m:
        attrs["diametro_raw"] = m.group(1)
        attrs["largo_raw"] = m.group(2)

    # Métrico M6x20
    m = re.search(r"[mM](\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)", nombre)
    if m and "diametro_raw" not in attrs:
        attrs["diametro_raw"] = f"M{m.group(1)}"
        attrs["largo_raw"] = m.group(2)

    # Milímetros
    m = re.search(r"(\d+(?:\.\d+)?)\s*mm\b", nombre, re.IGNORECASE)
    if m:
        attrs["medida_mm"] = float(m.group(1))

    # Pulgadas simples
    m = re.search(r"(\d+/\d+|\d+)\s*(?:\"|pulgadas?|pulg|plg)", nombre, re.IGNORECASE)
    if m and "diametro_raw" not in attrs:
        attrs["diametro_raw"] = m.group(1)

    # Material
    for material, keywords in _MATERIAL_KEYWORDS.items():
        if any(kw in nombre_lower for kw in keywords):
            attrs["material"] = material
            break

    # Cabeza
    for cabeza in _CABEZA_VOCAB:
        if cabeza in nombre_lower:
            attrs["cabeza"] = "hexagonal" if cabeza == "hex" else cabeza
            break

    return attrs


def extract_product_attributes(
    nombre: str,
    marca: str = "",
    etim_class: Optional[ETIMClass] = None,
) -> dict:
    """
    Extrae atributos técnicos del nombre de un producto usando NER/Matcher.

    Compatible con la firma y el formato de retorno de la versión regex:
    devuelve un dict con claves entre:
        diametro_raw, largo_raw, medida_mm, material, cabeza, marca

    Internamente usa spaCy `Matcher` si está disponible, con fallback
    automático a regex puro si spaCy no está instalado.
    """
    try:
        attrs = _extract_with_spacy(nombre)
    except Exception as exc:
        logger.debug("Fallo pipeline spaCy, usando regex: %s", exc)
        attrs = _extract_with_regex(nombre)

    if marca:
        attrs["marca"] = marca

    return attrs


# ---------------------------------------------------------------------------
# Clasificación de productos
# ---------------------------------------------------------------------------

def classify_product(nombre: str, marca: str = "") -> ClassificationResult:
    """
    Clasifica un producto en una clase ETIM basándose en keywords del nombre.

    Usa matching por keywords ponderado — cada keyword match suma puntos,
    y se selecciona la clase con mayor score.
    """
    nombre_norm = nombre.lower()
    # Normalizar tildes
    for a, b in [("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")]:
        nombre_norm = nombre_norm.replace(a, b)

    best_class: Optional[ETIMClass] = None
    best_score = 0
    best_keywords: list[str] = []

    for etim_class in ETIM_CLASSES.values():
        matched = [kw for kw in etim_class.keywords if kw in nombre_norm]
        score = len(matched)

        # Bonus por keyword de grupo
        group_lower = etim_class.group.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        if group_lower in nombre_norm:
            score += 0.5

        if score > best_score:
            best_score = score
            best_class = etim_class
            best_keywords = matched

    if not best_class or best_score < 1:
        return ClassificationResult(etim_class=None, confidence=0.0)

    # Confidence basado en proporción de keywords matcheados
    max_possible = len(best_class.keywords)
    confidence = min(best_score / max(max_possible, 1), 1.0)

    # Extraer atributos específicos de la clase
    extracted = extract_product_attributes(nombre, marca, best_class)

    return ClassificationResult(
        etim_class=best_class,
        confidence=round(confidence, 4),
        matched_keywords=best_keywords,
        extracted_attrs=extracted,
    )


def are_same_etim_class(nombre_a: str, nombre_b: str) -> tuple[bool, str]:
    """
    Verifica si dos productos pertenecen a la misma clase ETIM.

    Returns:
        (same_class, explanation)
    """
    class_a = classify_product(nombre_a)
    class_b = classify_product(nombre_b)

    if class_a.etim_class is None or class_b.etim_class is None:
        return True, "No se pudo clasificar — no se puede rechazar por taxonomía"

    if class_a.etim_class.code != class_b.etim_class.code:
        return False, (
            f"Clases ETIM diferentes: A='{class_a.etim_class.name}' ({class_a.etim_class.code}) "
            f"vs B='{class_b.etim_class.name}' ({class_b.etim_class.code})"
        )

    return True, f"Misma clase ETIM: {class_a.etim_class.name} ({class_a.etim_class.code})"


def get_critical_attributes_diff(
    nombre_a: str, marca_a: str,
    nombre_b: str, marca_b: str,
) -> list[str]:
    """
    Compara atributos técnicos críticos entre dos productos.
    Retorna lista de diferencias encontradas.
    """
    class_a = classify_product(nombre_a)
    class_b = classify_product(nombre_b)

    attrs_a = extract_product_attributes(nombre_a, marca_a, class_a.etim_class if class_a else None)
    attrs_b = extract_product_attributes(nombre_b, marca_b, class_b.etim_class if class_b else None)

    diffs = []

    # Comparar atributos comunes
    common_keys = set(attrs_a.keys()) & set(attrs_b.keys())
    for key in common_keys:
        if attrs_a[key] != attrs_b[key]:
            diffs.append(f"{key}: '{attrs_a[key]}' vs '{attrs_b[key]}'")

    return diffs
