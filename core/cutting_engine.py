"""
Motor canónico de optimización de corte — fuente única de verdad.

Convención de ejes usada en todo el sistema:
  largo = dimensión en eje X (ancho en SVG)
  ancho = dimensión en eje Y (alto en SVG)

Cada pieza en el resultado contiene:
  x, y          → posición top-left en el SVG del bin
  svg_w, svg_h  → tamaño real a dibujar en el SVG (rect.width / rect.height con kerf)
  largo, ancho  → dimensiones originales de diseño para mostrar en la etiqueta
  rotada        → True si rectpack rotó la pieza 90°

IMPORTANTE: Este módulo es importado por modulos/mrp/service.py y
modulos/ordenes/service.py. No modifiques la firma de optimizar_patron_corte
sin actualizar también los callers.
"""
from __future__ import annotations

from typing import Any

from rectpack import newPacker, guillotine, maxrects

# Área mínima (mm²) para que un retazo se considere útil
AREA_MINIMA_UTIL: float = 200.0 * 200.0
# Lado mínimo (mm) para que un retazo sea útil
MIN_LADO_UTIL: float = 100.0


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
    for p in lista_piezas:
        if p["largo"] <= 0 or p["ancho"] <= 0:
            raise ValueError(f"La pieza '{p['id_pieza']}' tiene dimensiones inválidas.")
        cabe_normal = (
            p["largo"] + grosor_sierra <= largo_plancha
            and p["ancho"] + grosor_sierra <= ancho_plancha
        )
        cabe_rotada = (
            p["ancho"] + grosor_sierra <= largo_plancha
            and p["largo"] + grosor_sierra <= ancho_plancha
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
    Calcula retazos útiles usando dos fuentes en orden de preferencia:
    1. _sections de Guillotine (secciones internas — más preciso)
    2. Cálculo geométrico basado en el espacio libre restante (fallback para MaxRects)
    """
    retazos: list[dict] = []

    # Fuente 1: secciones internas del algoritmo Guillotine
    secciones = getattr(bin_, "_sections", [])
    for sec in secciones:
        w, h = sec.width, sec.height
        if w > MIN_LADO_UTIL and h > MIN_LADO_UTIL and w * h >= AREA_MINIMA_UTIL:
            retazos.append({
                "id_pieza": "RETAZO_LIBRE",
                "x": sec.x,
                "y": sec.y,
                "largo": w,
                "ancho": h,
            })

    if retazos:
        return retazos

    # Fuente 2: fallback geométrico cuando MaxRects no expone _sections
    if not piezas_colocadas:
        return [{
            "id_pieza": "RETAZO_LIBRE",
            "x": 0, "y": 0,
            "largo": largo_plancha,
            "ancho": ancho_plancha,
        }]

    max_x = max(p["x"] + p["svg_w"] for p in piezas_colocadas)
    max_y = max(p["y"] + p["svg_h"] for p in piezas_colocadas)

    # Franja derecha
    franja_der_w = largo_plancha - max_x
    franja_der_h = ancho_plancha
    if (
        franja_der_w > MIN_LADO_UTIL
        and franja_der_h > MIN_LADO_UTIL
        and franja_der_w * franja_der_h >= AREA_MINIMA_UTIL
    ):
        retazos.append({
            "id_pieza": "RETAZO_LIBRE",
            "x": max_x, "y": 0,
            "largo": franja_der_w,
            "ancho": franja_der_h,
        })

    # Franja inferior (hasta donde no se solapa con la franja derecha)
    franja_inf_w = max_x
    franja_inf_h = ancho_plancha - max_y
    if (
        franja_inf_w > MIN_LADO_UTIL
        and franja_inf_h > MIN_LADO_UTIL
        and franja_inf_w * franja_inf_h >= AREA_MINIMA_UTIL
    ):
        retazos.append({
            "id_pieza": "RETAZO_LIBRE",
            "x": 0, "y": max_y,
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
    """
    Optimiza el patrón de corte usando rectpack.

    Args:
        largo_plancha: Ancho del tablero en mm (eje X).
        ancho_plancha: Alto del tablero en mm (eje Y).
        lista_piezas:  Lista de dicts con {id_pieza, largo, ancho, cantidad}.
        grosor_sierra: Kerf del corte en mm (default 4mm).
        max_planchas:  Límite de tableros a utilizar.

    Returns:
        {
          "planchas_usadas": int,
          "cortes": [
            {
              "numero_plancha": int,
              "piezas": [
                {
                  "id_pieza": str,
                  "x": float, "y": float,
                  "svg_w": float, "svg_h": float,   # tamaño a dibujar (con kerf)
                  "largo": float, "ancho": float,    # dims originales para etiqueta
                  "rotada": bool
                }
              ],
              "retazos_utiles": [{"id_pieza": "RETAZO_LIBRE", "x", "y", "largo", "ancho"}]
            }
          ]
        }
    """
    _validate_inputs(largo_plancha, ancho_plancha, lista_piezas, grosor_sierra)

    if not lista_piezas:
        return {"planchas_usadas": 0, "cortes": []}

    # Tabla de dimensiones originales por nombre de pieza (para la etiqueta)
    orig_dims: dict[str, tuple[float, float]] = {
        p["id_pieza"]: (float(p["largo"]), float(p["ancho"])) for p in lista_piezas
    }

    # Probar MaxRects primero (mejor empaquetado), Guillotine como fallback
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
            break  # Primer algoritmo que encajó todo — listo

    EPS = 1e-6
    resultado: dict[str, Any] = {"planchas_usadas": len(packer), "cortes": []}

    for idx_plancha, bin_ in enumerate(packer):
        piezas_data: list[dict] = []

        for rect in bin_:
            largo_orig, ancho_orig = orig_dims.get(rect.rid, (rect.width, rect.height))

            # Detectar rotación: si rect.width ≈ ancho_orig+kerf, la pieza fue rotada 90°
            rotada = abs(rect.width - (largo_orig + grosor_sierra)) > EPS

            # svg_w / svg_h: tamaño real del rectángulo a dibujar (incluye kerf)
            svg_w = rect.width
            svg_h = rect.height

            # largo/ancho para la etiqueta: siempre las dims originales de diseño
            if rotada:
                label_largo = ancho_orig  # el eje X ahora tiene el ancho original
                label_ancho = largo_orig  # el eje Y ahora tiene el largo original
            else:
                label_largo = largo_orig
                label_ancho = ancho_orig

            piezas_data.append({
                "id_pieza": rect.rid,
                "x": rect.x,
                "y": rect.y,
                "svg_w": svg_w,
                "svg_h": svg_h,
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
