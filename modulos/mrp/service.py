"""
Cutting optimisation service.

Convention used throughout:
  largo = dimension along X axis (width in SVG)
  ancho = dimension along Y axis (height in SVG)

Each pieza in the result carries:
  x, y          → SVG top-left position
  svg_w, svg_h  → actual pixel size to draw in the SVG  (rect.width / rect.height)
  largo, ancho  → ORIGINAL design dimensions to show in the label
  rotada        → True when rectpack rotated the piece 90°
"""
from __future__ import annotations
from typing import Any
from rectpack import newPacker, guillotine, maxrects

AREA_MINIMA_UTIL = 200.0 * 200.0
MIN_LADO_UTIL = 100.0


def _validate_inputs(largo_plancha, ancho_plancha, lista_piezas, grosor_sierra):
    if largo_plancha <= 0 or ancho_plancha <= 0:
        raise ValueError("Las dimensiones de la plancha deben ser positivas.")
    if grosor_sierra < 0:
        raise ValueError("El grosor de sierra no puede ser negativo.")
    for p in lista_piezas:
        if p["largo"] <= 0 or p["ancho"] <= 0:
            raise ValueError(f"La pieza '{p['id_pieza']}' tiene dimensiones inválidas.")
        cabe_normal = (
            p["largo"] + grosor_sierra <= largo_plancha and
            p["ancho"] + grosor_sierra <= ancho_plancha
        )
        cabe_rotada = (
            p["ancho"] + grosor_sierra <= largo_plancha and
            p["largo"] + grosor_sierra <= ancho_plancha
        )
        if not cabe_normal and not cabe_rotada:
            raise ValueError(
                f"La pieza '{p['id_pieza']}' ({p['largo']}×{p['ancho']} mm) "
                f"no cabe en la plancha ({largo_plancha}×{ancho_plancha} mm)."
            )


def _calcular_retazos_libres(
    bin_,
    piezas_colocadas: list[dict],
    largo_plancha: float,
    ancho_plancha: float,
) -> list[dict]:
    """
    Calcula retazos útiles usando dos fuentes:
    1. _sections de Guillotine (si existe)
    2. Cálculo geométrico propio basado en el espacio libre restante
    """
    retazos = []

    # Fuente 1: secciones internas de Guillotine
    secciones = getattr(bin_, "_sections", [])
    for sec in secciones:
        w, h = sec.width, sec.height
        if w > MIN_LADO_UTIL and h > MIN_LADO_UTIL and w * h >= AREA_MINIMA_UTIL:
            # Verificar que no se solape con piezas ya reportadas
            retazos.append({
                "id_pieza": "RETAZO_LIBRE",
                "x": sec.x,
                "y": sec.y,
                "largo": w,
                "ancho": h,
            })

    if retazos:
        return retazos

    # Fuente 2: si Guillotine no tiene _sections (MaxRects),
    # calculamos el rectángulo libre más grande a la derecha y abajo
    if not piezas_colocadas:
        return [{
            "id_pieza": "RETAZO_LIBRE",
            "x": 0, "y": 0,
            "largo": largo_plancha,
            "ancho": ancho_plancha,
        }]

    # Borde derecho usado y borde inferior usado
    max_x = max(p["x"] + p["svg_w"] for p in piezas_colocadas)
    max_y = max(p["y"] + p["svg_h"] for p in piezas_colocadas)

    # Franja derecha
    franja_der_w = largo_plancha - max_x
    franja_der_h = ancho_plancha
    if franja_der_w > MIN_LADO_UTIL and franja_der_h > MIN_LADO_UTIL and franja_der_w * franja_der_h >= AREA_MINIMA_UTIL:
        retazos.append({
            "id_pieza": "RETAZO_LIBRE",
            "x": max_x,
            "y": 0,
            "largo": franja_der_w,
            "ancho": franja_der_h,
        })

    # Franja inferior (solo hasta donde no se solapa con la franja derecha)
    franja_inf_w = max_x
    franja_inf_h = ancho_plancha - max_y
    if franja_inf_w > MIN_LADO_UTIL and franja_inf_h > MIN_LADO_UTIL and franja_inf_w * franja_inf_h >= AREA_MINIMA_UTIL:
        retazos.append({
            "id_pieza": "RETAZO_LIBRE",
            "x": 0,
            "y": max_y,
            "largo": franja_inf_w,
            "ancho": franja_inf_h,
        })

    return retazos


def optimizar_patron_corte(
    largo_plancha: float,
    ancho_plancha: float,
    lista_piezas: list[dict],
    grosor_sierra: float = 4.0,
    max_planchas: int = 50,
) -> dict[str, Any]:
    _validate_inputs(largo_plancha, ancho_plancha, lista_piezas, grosor_sierra)

    if not lista_piezas:
        return {"planchas_usadas": 0, "cortes": []}

    # Dimensiones originales por nombre de pieza (para el label)
    orig_dims: dict[str, tuple[float, float]] = {
        p["id_pieza"]: (float(p["largo"]), float(p["ancho"])) for p in lista_piezas
    }

    # Intentar MaxRects primero, luego Guillotine como fallback
    packer = None
    for algo in (maxrects.MaxRectsBssf, guillotine.GuillotineBssfSas):
        p = newPacker(pack_algo=algo, rotation=True)
        for pieza in lista_piezas:
            for _ in range(int(pieza["cantidad"])):
                p.add_rect(
                    width=pieza["largo"] + grosor_sierra,
                    height=pieza["ancho"] + grosor_sierra,
                    rid=pieza["id_pieza"],
                )
        for _ in range(max_planchas):
            p.add_bin(width=largo_plancha, height=ancho_plancha)
        p.pack()

        total_colocadas = sum(len(b) for b in p)
        total_necesarias = sum(int(pieza["cantidad"]) for pieza in lista_piezas)
        packer = p
        if total_colocadas >= total_necesarias:
            break

    EPS = 1e-6
    resultado: dict[str, Any] = {"planchas_usadas": len(packer), "cortes": []}

    for idx_plancha, bin_ in enumerate(packer):
        piezas_data = []

        for rect in bin_:
            largo_orig, ancho_orig = orig_dims.get(rect.rid, (rect.width, rect.height))

            # rectpack coloca la pieza con width=rect.width, height=rect.height en el SVG.
            # Si rotó: rect.width ≈ ancho_orig+kerf  y  rect.height ≈ largo_orig+kerf
            rotada = abs(rect.width - (largo_orig + grosor_sierra)) > EPS

            # svg_w / svg_h: tamaño real del rectángulo a dibujar (con kerf incluido)
            svg_w = rect.width
            svg_h = rect.height

            # largo/ancho para el label: siempre las dimensiones originales de diseño
            if rotada:
                label_largo = ancho_orig  # lo que era ancho ahora ocupa el eje X
                label_ancho = largo_orig  # lo que era largo ahora ocupa el eje Y
            else:
                label_largo = largo_orig
                label_ancho = ancho_orig

            piezas_data.append({
                "id_pieza": rect.rid,
                "x": rect.x,
                "y": rect.y,
                # SVG drawing dimensions (what the rect actually occupies on the board)
                "svg_w": svg_w,
                "svg_h": svg_h,
                # Label dimensions (original design dimensions)
                "largo": label_largo,
                "ancho": label_ancho,
                "rotada": rotada,
            })

        retazos = _calcular_retazos_libres(bin_, piezas_data, largo_plancha, ancho_plancha)

        resultado["cortes"].append({
            "numero_plancha": idx_plancha + 1,
            "piezas": piezas_data,
            "retazos_utiles": retazos,
        })

    return resultado
