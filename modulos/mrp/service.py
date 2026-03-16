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
    
    # Un retazo es útil si mide más de 20x20 cm
    AREA_MINIMA_UTIL = 200.0 * 200.0 
    
    for index_plancha, bin in enumerate(packer):
        plancha_data = {
            "numero_plancha": index_plancha + 1, 
            "piezas": [],
            "retazos_utiles": []
        }
        
        max_y_total = 0.0 
        filas = {} # Agruparemos las piezas por su altura (coordenada Y)
        
        for rect in bin:
            pieza_limpia = {
                "id_pieza": rect.rid,
                "x": rect.x,
                "y": rect.y,
                "ancho": rect.width - grosor_sierra,
                "largo": rect.height - grosor_sierra
            }
            plancha_data["piezas"].append(pieza_limpia)
            
            # Agrupamos por fila para buscar huecos
            y_coord = rect.y
            if y_coord not in filas:
                filas[y_coord] = []
            filas[y_coord].append(pieza_limpia)

            if rect.y + rect.height > max_y_total:
                max_y_total = rect.y + rect.height
        
        # --- NUEVA LÓGICA DE RETAZOS ---
        
        # 1. RETAZOS AL FINAL DE CADA FILA (Como el hueco de tu Plancha #1)
        for y_coord, piezas_en_fila in filas.items():
            # Buscamos dónde termina la última pieza de esta fila
            max_x_fila = max([p["x"] + p["ancho"] + grosor_sierra for p in piezas_en_fila])
            altura_fila = piezas_en_fila[0]["largo"] # Asumimos la altura de la primera pieza
            
            ancho_sobrante = largo_plancha - max_x_fila
            
            if (ancho_sobrante * altura_fila) >= AREA_MINIMA_UTIL and ancho_sobrante > 100:
                plancha_data["retazos_utiles"].append({
                    "id_pieza": "RETAZO_FILA",
                    "x": max_x_fila,
                    "y": y_coord,
                    "ancho": ancho_sobrante,
                    "largo": altura_fila
                })

        # 2. RETAZO GIGANTE SUPERIOR (Arriba de todas las piezas)
        largo_superior = ancho_plancha - max_y_total
        if (largo_plancha * largo_superior) >= AREA_MINIMA_UTIL and largo_superior > 100:
            plancha_data["retazos_utiles"].append({
                "id_pieza": "RETAZO_SUPERIOR",
                "x": 0,
                "y": max_y_total,
                "ancho": largo_plancha, 
                "largo": largo_superior
            })

        resultado["cortes"].append(plancha_data)
        
    return resultado