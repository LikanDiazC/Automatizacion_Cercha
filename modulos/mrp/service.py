from rectpack import newPacker, guillotine


def optimizar_patron_corte(largo_plancha: float, ancho_plancha: float, lista_piezas: list, grosor_sierra: float = 4.0):
    packer = newPacker(pack_algo=guillotine.GuillotineBssfSas, rotation=False)

    for pieza in lista_piezas:
        largo_real = pieza["largo"] + grosor_sierra
        ancho_real = pieza["ancho"] + grosor_sierra
        for _ in range(pieza["cantidad"]):
            packer.add_rect(width=largo_real, height=ancho_real, rid=pieza["id_pieza"])

    for _ in range(10):
        packer.add_bin(width=largo_plancha, height=ancho_plancha)

    packer.pack()

    resultado = {"planchas_usadas": len(packer), "cortes": []}

    # Un retazo es util si mide mas de 20x20 cm
    AREA_MINIMA_UTIL = 200.0 * 200.0

    EPS = 1e-6

    for index_plancha, bin in enumerate(packer):
        plancha_data = {
            "numero_plancha": index_plancha + 1,
            "piezas": [],
            "retazos_utiles": []
        }

        for rect in bin:
            toca_borde_derecho = (rect.x + rect.width) >= (largo_plancha - EPS)
            toca_borde_inferior = (rect.y + rect.height) >= (ancho_plancha - EPS)

            pieza_limpia = {
                "id_pieza": rect.rid,
                "x": rect.x,
                "y": rect.y,
                "largo": rect.width - (0 if toca_borde_derecho else grosor_sierra),
                "ancho": rect.height - (0 if toca_borde_inferior else grosor_sierra)
            }
            plancha_data["piezas"].append(pieza_limpia)

        # NUEVA LOGICA DE RETAZOS (sin solapamientos)
        # Usamos los espacios libres que mantiene el algoritmo Guillotine.
        secciones_libres = getattr(bin, "_sections", [])
        for seccion in secciones_libres:
            largo_libre = seccion.width
            ancho_libre = seccion.height
            if largo_libre <= 0 or ancho_libre <= 0:
                continue
            if (largo_libre * ancho_libre) >= AREA_MINIMA_UTIL and largo_libre > 100 and ancho_libre > 100:
                plancha_data["retazos_utiles"].append({
                    "id_pieza": "RETAZO_LIBRE",
                    "x": seccion.x,
                    "y": seccion.y,
                    "largo": largo_libre,
                    "ancho": ancho_libre
                })

        resultado["cortes"].append(plancha_data)

    return resultado
