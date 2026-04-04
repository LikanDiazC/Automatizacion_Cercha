"""
Motor de corte avanzado v2 — soporte de veta y tapacantos.

Extensión del cutting_engine original que agrega:
  1. Sentido de veta: restringe rotación cuando la pieza tiene veta definida
  2. Tapacantos: suma el grosor del tapacanto a las dimensiones de corte
  3. Remnant-first: intenta usar retazos existentes antes de planchas nuevas
  4. Metadata enriquecida en el resultado (área utilizada, desperdicio %)

Importar este módulo NO reemplaza cutting_engine.py — es un upgrade opcional.
Los callers existentes siguen funcionando sin cambios.
"""

from __future__ import annotations

import enum
from typing import Any, Optional

from rectpack import newPacker, guillotine, maxrects

from .cutting_engine import AREA_MINIMA_UTIL, MIN_LADO_UTIL, _calcular_retazos_libres


# ---------------------------------------------------------------------------
# Enums y constantes
# ---------------------------------------------------------------------------

class SentidoVeta(str, enum.Enum):
    """Dirección de la veta en la plancha."""
    LARGO = "largo"      # Veta corre paralela al eje X (largo de la plancha)
    ANCHO = "ancho"      # Veta corre paralela al eje Y (ancho de la plancha)
    NINGUNO = "ninguno"  # Sin veta (melamina lisa, MDF, etc.)


# Grosor estándar de tapacantos en mm
TAPACANTO_GRUESO = 2.0   # PVC 2mm
TAPACANTO_DELGADO = 0.4  # PVC 0.4mm


# ---------------------------------------------------------------------------
# Pieza con metadata de manufactura
# ---------------------------------------------------------------------------

def preparar_pieza_v2(
    id_pieza: str,
    largo: float,
    ancho: float,
    cantidad: int = 1,
    sentido_veta: SentidoVeta = SentidoVeta.NINGUNO,
    tapacanto_largo_1: float = 0.0,  # tapacanto en borde largo lado 1
    tapacanto_largo_2: float = 0.0,  # tapacanto en borde largo lado 2
    tapacanto_ancho_1: float = 0.0,  # tapacanto en borde ancho lado 1
    tapacanto_ancho_2: float = 0.0,  # tapacanto en borde ancho lado 2
) -> dict:
    """
    Prepara una pieza para el motor de corte v2.

    Las dimensiones de corte se ajustan sumando el grosor del tapacanto
    a cada borde correspondiente.

    Returns:
        Dict con las dimensiones originales, de corte (ajustadas), y metadata.
    """
    # Dimensiones de CORTE = dimensión original + tapacantos
    largo_corte = largo + tapacanto_largo_1 + tapacanto_largo_2
    ancho_corte = ancho + tapacanto_ancho_1 + tapacanto_ancho_2

    return {
        "id_pieza": id_pieza,
        "largo": largo,
        "ancho": ancho,
        "largo_corte": largo_corte,
        "ancho_corte": ancho_corte,
        "cantidad": cantidad,
        "sentido_veta": sentido_veta,
        "tapacantos": {
            "largo_1": tapacanto_largo_1,
            "largo_2": tapacanto_largo_2,
            "ancho_1": tapacanto_ancho_1,
            "ancho_2": tapacanto_ancho_2,
        },
    }


# ---------------------------------------------------------------------------
# Motor de corte v2
# ---------------------------------------------------------------------------

def optimizar_corte_v2(
    largo_plancha: float,
    ancho_plancha: float,
    lista_piezas: list[dict],
    grosor_sierra: float = 4.0,
    max_planchas: int = 50,
    retazos_disponibles: Optional[list[dict]] = None,
    sentido_veta_plancha: SentidoVeta = SentidoVeta.LARGO,
) -> dict[str, Any]:
    """
    Motor de corte v2 con soporte de veta, tapacantos y remnant-first.

    Args:
        largo_plancha: Ancho del tablero en mm (eje X).
        ancho_plancha: Alto del tablero en mm (eje Y).
        lista_piezas: Lista de dicts (usar preparar_pieza_v2 para generar).
        grosor_sierra: Kerf en mm.
        max_planchas: Límite de tableros nuevos.
        retazos_disponibles: Retazos existentes [{largo, ancho, id_retazo}].
        sentido_veta_plancha: Dirección de la veta en las planchas nuevas.

    Returns:
        Resultado enriquecido con metadata de veta, tapacantos, y eficiencia.
    """
    if not lista_piezas:
        return {"planchas_usadas": 0, "cortes": [], "retazos_usados": 0, "eficiencia_pct": 0}

    # Determinar si se puede rotar cada pieza según la veta
    allow_rotation = True  # Default para piezas sin veta

    # Preparar piezas con dimensiones de corte (incluyendo tapacantos)
    piezas_rectpack = []
    orig_dims: dict[str, dict] = {}

    for p in lista_piezas:
        largo_c = p.get("largo_corte", p["largo"])
        ancho_c = p.get("ancho_corte", p["ancho"])
        veta = p.get("sentido_veta", SentidoVeta.NINGUNO)

        orig_dims[p["id_pieza"]] = {
            "largo": p["largo"],
            "ancho": p["ancho"],
            "largo_corte": largo_c,
            "ancho_corte": ancho_c,
            "sentido_veta": veta,
            "tapacantos": p.get("tapacantos", {}),
        }

        # Si tiene veta, no permitir rotación individual
        # (rectpack no soporta rotación por pieza, así que hacemos un workaround)
        pieza_rotation = veta == SentidoVeta.NINGUNO

        for _ in range(int(p.get("cantidad", 1))):
            piezas_rectpack.append({
                "width": largo_c + grosor_sierra,
                "height": ancho_c + grosor_sierra,
                "rid": p["id_pieza"],
                "can_rotate": pieza_rotation,
            })

    # Si hay piezas con veta, no podemos usar rotación global
    any_veta = any(p.get("sentido_veta", SentidoVeta.NINGUNO) != SentidoVeta.NINGUNO for p in lista_piezas)

    # Fase 1: Intentar usar retazos primero (remnant-first)
    retazos_usados = 0
    piezas_en_retazo: list[dict] = []

    if retazos_disponibles:
        # Ordenar retazos de menor a mayor (usar el más chico que sirva)
        retazos_sorted = sorted(retazos_disponibles, key=lambda r: r["largo"] * r["ancho"])

        for retazo in retazos_sorted:
            if not piezas_rectpack:
                break

            p_retazo = newPacker(
                pack_algo=maxrects.MaxRectsBssf,
                rotation=not any_veta,
            )
            p_retazo.add_bin(width=retazo["largo"], height=retazo["ancho"])

            for pr in piezas_rectpack:
                p_retazo.add_rect(width=pr["width"], height=pr["height"], rid=pr["rid"])

            p_retazo.pack()

            if len(p_retazo) > 0 and len(list(p_retazo[0])) > 0:
                retazos_usados += 1
                colocados_rids = set()
                piezas_ret = []
                for rect in p_retazo[0]:
                    colocados_rids.add(rect.rid)
                    l_orig, a_orig = orig_dims[rect.rid]["largo"], orig_dims[rect.rid]["ancho"]
                    EPS = 1e-6
                    rotada = abs(rect.width - (orig_dims[rect.rid]["largo_corte"] + grosor_sierra)) > EPS

                    piezas_ret.append({
                        "id_pieza": rect.rid,
                        "x": rect.x, "y": rect.y,
                        "svg_w": rect.width, "svg_h": rect.height,
                        "largo": a_orig if rotada else l_orig,
                        "ancho": l_orig if rotada else a_orig,
                        "rotada": rotada,
                        "tapacantos": orig_dims[rect.rid].get("tapacantos", {}),
                        "sentido_veta": orig_dims[rect.rid].get("sentido_veta", "ninguno"),
                    })

                piezas_en_retazo.append({
                    "tipo": "retazo",
                    "id_retazo": retazo.get("id_retazo", "retazo"),
                    "largo_retazo": retazo["largo"],
                    "ancho_retazo": retazo["ancho"],
                    "piezas": piezas_ret,
                })

                # Remover piezas ya colocadas
                piezas_rectpack = [p for p in piezas_rectpack if p["rid"] not in colocados_rids]

    # Fase 2: Planchas nuevas para las piezas restantes
    resultado_planchas: list[dict] = []

    if piezas_rectpack:
        packer = None
        for algo in (maxrects.MaxRectsBssf, guillotine.GuillotineBssfSas):
            p = newPacker(pack_algo=algo, rotation=not any_veta)
            for pr in piezas_rectpack:
                p.add_rect(width=pr["width"], height=pr["height"], rid=pr["rid"])
            for _ in range(max_planchas):
                p.add_bin(width=largo_plancha, height=ancho_plancha)
            p.pack()
            packer = p

            total_colocadas = sum(len(b) for b in p)
            if total_colocadas >= len(piezas_rectpack):
                break

        EPS = 1e-6
        for idx_plancha, bin_ in enumerate(packer):
            piezas_data: list[dict] = []
            for rect in bin_:
                info = orig_dims.get(rect.rid, {})
                l_orig = info.get("largo", rect.width)
                a_orig = info.get("ancho", rect.height)
                l_corte = info.get("largo_corte", l_orig)
                rotada = abs(rect.width - (l_corte + grosor_sierra)) > EPS

                piezas_data.append({
                    "id_pieza": rect.rid,
                    "x": rect.x, "y": rect.y,
                    "svg_w": rect.width, "svg_h": rect.height,
                    "largo": a_orig if rotada else l_orig,
                    "ancho": l_orig if rotada else a_orig,
                    "rotada": rotada,
                    "tapacantos": info.get("tapacantos", {}),
                    "sentido_veta": str(info.get("sentido_veta", "ninguno")),
                })

            retazos = _calcular_retazos_libres(bin_, piezas_data, largo_plancha, ancho_plancha)

            # Calcular eficiencia de la plancha
            area_plancha = largo_plancha * ancho_plancha
            area_usada = sum(p["svg_w"] * p["svg_h"] for p in piezas_data)
            eficiencia = (area_usada / area_plancha * 100) if area_plancha > 0 else 0

            resultado_planchas.append({
                "tipo": "plancha_nueva",
                "numero_plancha": idx_plancha + 1,
                "piezas": piezas_data,
                "retazos_utiles": retazos,
                "eficiencia_pct": round(eficiencia, 1),
                "sentido_veta_plancha": sentido_veta_plancha.value,
            })

    # Combinar resultados
    todos_cortes = piezas_en_retazo + resultado_planchas
    total_planchas = len(resultado_planchas)
    total_piezas = sum(
        len(c["piezas"]) for c in todos_cortes
    )

    # Eficiencia global
    area_total = total_planchas * largo_plancha * ancho_plancha
    area_total += sum(
        c.get("largo_retazo", 0) * c.get("ancho_retazo", 0)
        for c in piezas_en_retazo
    )
    area_piezas = sum(
        p["svg_w"] * p["svg_h"]
        for c in todos_cortes
        for p in c["piezas"]
    )
    eficiencia_global = (area_piezas / area_total * 100) if area_total > 0 else 0

    return {
        "planchas_usadas": total_planchas,
        "retazos_usados": retazos_usados,
        "total_piezas_colocadas": total_piezas,
        "eficiencia_pct": round(eficiencia_global, 1),
        "cortes": todos_cortes,
    }
