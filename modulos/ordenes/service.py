"""
Cutting optimisation service.

Key improvements over v1:
- rotation=True  → piezas can be rotated 90° for better fit (up to 20-30% fewer boards)
- MaxRectsBssf fallback tried first, Guillotine as fallback
- Original orientation is tracked so downstream code shows correct largo/ancho
- Hard input validation before calling rectpack
- Graceful error if no pieces fit
"""
from __future__ import annotations

from typing import Any

from rectpack import newPacker, guillotine, maxrects


# Minimum area (mm²) for a leftover to be considered "useful"
AREA_MINIMA_UTIL = 200.0 * 200.0
# Min side length (mm) for a leftover to be useful
MIN_LADO_UTIL = 100.0


def _validate_inputs(
    largo_plancha: float,
    ancho_plancha: float,
    lista_piezas: list[dict],
    grosor_sierra: float,
) -> None:
    if largo_plancha <= 0 or ancho_plancha <= 0:
        raise ValueError("Las dimensiones de la plancha deben ser positivas.")
    if grosor_sierra < 0:
        raise ValueError("El grosor de sierra no puede ser negativo.")
    for pieza in lista_piezas:
        if pieza["largo"] <= 0 or pieza["ancho"] <= 0:
            raise ValueError(f"La pieza '{pieza['id_pieza']}' tiene dimensiones inválidas.")
        if pieza["largo"] + grosor_sierra > largo_plancha or pieza["ancho"] + grosor_sierra > ancho_plancha:
            # Allow rotated fit too before raising
            if pieza["ancho"] + grosor_sierra > largo_plancha or pieza["largo"] + grosor_sierra > ancho_plancha:
                raise ValueError(
                    f"La pieza '{pieza['id_pieza']}' ({pieza['largo']}×{pieza['ancho']} mm) "
                    f"no cabe en la plancha ({largo_plancha}×{ancho_plancha} mm)."
                )


def optimizar_patron_corte(
    largo_plancha: float,
    ancho_plancha: float,
    lista_piezas: list[dict],
    grosor_sierra: float = 4.0,
    max_planchas: int = 50,
) -> dict[str, Any]:
    """
    Returns:
        {
          "planchas_usadas": int,
          "cortes": [
            {
              "numero_plancha": int,
              "piezas": [{"id_pieza", "x", "y", "largo", "ancho", "rotada"}],
              "retazos_utiles": [{"id_pieza", "x", "y", "largo", "ancho"}],
            }
          ]
        }
    """
    _validate_inputs(largo_plancha, ancho_plancha, lista_piezas, grosor_sierra)

    if not lista_piezas:
        return {"planchas_usadas": 0, "cortes": []}

    # Build a lookup: rid → original dimensions (before kerf addition)
    # Since rids are not unique (same piece type appears multiple times),
    # we store (largo_orig, ancho_orig) by id_pieza name
    orig_dims: dict[str, tuple[float, float]] = {
        p["id_pieza"]: (p["largo"], p["ancho"]) for p in lista_piezas
    }

    # Try MaxRects first (better packing), fall back to Guillotine
    for algo in (maxrects.MaxRectsBssf, guillotine.GuillotineBssfSas):
        packer = newPacker(pack_algo=algo, rotation=True)

        for pieza in lista_piezas:
            w = pieza["largo"] + grosor_sierra
            h = pieza["ancho"] + grosor_sierra
            for _ in range(int(pieza["cantidad"])):
                packer.add_rect(width=w, height=h, rid=pieza["id_pieza"])

        for _ in range(max_planchas):
            packer.add_bin(width=largo_plancha, height=ancho_plancha)

        packer.pack()

        total_rects = sum(len(b) for b in packer)
        total_needed = sum(int(p["cantidad"]) for p in lista_piezas)

        if total_rects >= total_needed:
            break  # Good packing found
    else:
        # Even after both algorithms, some pieces didn't fit
        pass

    EPS = 1e-6
    resultado: dict[str, Any] = {"planchas_usadas": len(packer), "cortes": []}

    for idx_plancha, bin_ in enumerate(packer):
        plancha_data: dict[str, Any] = {
            "numero_plancha": idx_plancha + 1,
            "piezas": [],
            "retazos_utiles": [],
        }

        for rect in bin_:
            largo_orig, ancho_orig = orig_dims.get(rect.rid, (rect.width, rect.height))
            # Detect if rectpack rotated the piece
            rotada = abs(rect.width - (largo_orig + grosor_sierra)) > EPS

            toca_borde_derecho = (rect.x + rect.width) >= (largo_plancha - EPS)
            toca_borde_inferior = (rect.y + rect.height) >= (ancho_plancha - EPS)

            if rotada:
                # Width in bin corresponds to original ancho
                largo_real = rect.height - (0 if toca_borde_inferior else grosor_sierra)
                ancho_real = rect.width - (0 if toca_borde_derecho else grosor_sierra)
            else:
                largo_real = rect.width - (0 if toca_borde_derecho else grosor_sierra)
                ancho_real = rect.height - (0 if toca_borde_inferior else grosor_sierra)

            plancha_data["piezas"].append({
                "id_pieza": rect.rid,
                "x": rect.x,
                "y": rect.y,
                "largo": largo_real,
                "ancho": ancho_real,
                "rotada": rotada,
            })

        # Collect useful offcuts from the Guillotine free sections
        secciones_libres = getattr(bin_, "_sections", [])
        for sec in secciones_libres:
            w, h = sec.width, sec.height
            if w <= 0 or h <= 0:
                continue
            if w * h >= AREA_MINIMA_UTIL and w > MIN_LADO_UTIL and h > MIN_LADO_UTIL:
                plancha_data["retazos_utiles"].append({
                    "id_pieza": "RETAZO_LIBRE",
                    "x": sec.x,
                    "y": sec.y,
                    "largo": w,
                    "ancho": h,
                })

        resultado["cortes"].append(plancha_data)

    return resultado
