import json

def generar_svg(datos_json, archivo_salida="plano_corte.html"):
    # Tomamos las medidas de la plancha (ajustado para que quepa en pantalla)
    escala = 0.4
    
    html = "<html><body style='background-color: #f0f0f0; font-family: sans-serif; padding: 20px;'>"
    html += "<h2>Planos de Corte Optimizados</h2>"
    
    # Recorremos cada plancha que arrojó el algoritmo
    for plancha in datos_json["cortes"]:
        html += f"<h3>Plancha #{plancha['numero_plancha']}</h3>"
        
        # El contenedor principal de la plancha (SVG)
        html += f"<svg width='1000' height='500' viewBox='0 0 2440 1220' style='border: 2px solid #333; background-color: #e6c280; margin-bottom: 30px;'>"
        
        # Dibujamos las piezas útiles (en color madera clara)
        for pieza in plancha["piezas"]:
            html += f"<rect x='{pieza['x']}' y='{pieza['y']}' width='{pieza['ancho']}' height='{pieza['largo']}' fill='#f4e3c5' stroke='#8b5a2b' stroke-width='4' />"
            html += f"<text x='{pieza['x'] + 10}' y='{pieza['y'] + 30}' fill='#333' font-size='24' font-weight='bold'>{pieza['id_pieza']}</text>"
            html += f"<text x='{pieza['x'] + 10}' y='{pieza['y'] + 60}' fill='#666' font-size='20'>{pieza['ancho']} x {pieza['largo']} mm</text>"

        # Dibujamos los retazos que guardamos (en color verde translúcido)
        for retazo in plancha["retazos_utiles"]:
            html += f"<rect x='{retazo['x']}' y='{retazo['y']}' width='{retazo['ancho']}' height='{retazo['largo']}' fill='rgba(144, 238, 144, 0.5)' stroke='#006400' stroke-width='4' stroke-dasharray='10,10' />"
            html += f"<text x='{retazo['x'] + 10}' y='{retazo['y'] + 30}' fill='#006400' font-size='24' font-weight='bold'>{retazo['id_pieza']}</text>"
            html += f"<text x='{retazo['x'] + 10}' y='{retazo['y'] + 60}' fill='#006400' font-size='20'>Guardado en BD</text>"

        html += "</svg>"
        
    html += "</body></html>"

    with open(archivo_salida, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"¡Plano generado con éxito! Abre el archivo {archivo_salida} en tu navegador.")

# Aquí pegamos la respuesta exacta que te dio Swagger hace un rato:
respuesta_swagger = {
  "planchas_usadas": 2,
  "cortes": [
    {
      "numero_plancha": 1,
      "piezas": [
        {
          "id_pieza": "Puerta_Armario",
          "x": 0,
          "y": 0,
          "ancho": 1800,
          "largo": 500
        },
        {
          "id_pieza": "Puerta_Armario",
          "x": 0,
          "y": 504,
          "ancho": 1800,
          "largo": 500
        },
        {
          "id_pieza": "Frente_Cajon",
          "x": 0,
          "y": 1008,
          "ancho": 600,
          "largo": 200
        },
        {
          "id_pieza": "Frente_Cajon",
          "x": 604,
          "y": 1008,
          "ancho": 600,
          "largo": 200
        },
        {
          "id_pieza": "Frente_Cajon",
          "x": 1804,
          "y": 0,
          "ancho": 600,
          "largo": 200
        },
        {
          "id_pieza": "Frente_Cajon",
          "x": 1804,
          "y": 204,
          "ancho": 600,
          "largo": 200
        }
      ],
      "retazos_utiles": [
        {
          "id_pieza": "RETAZO_FILA",
          "x": 1804,
          "y": 504,
          "ancho": 636,
          "largo": 500
        },
        {
          "id_pieza": "RETAZO_FILA",
          "x": 1208,
          "y": 1008,
          "ancho": 1232,
          "largo": 200
        }
      ]
    },
    {
      "numero_plancha": 2,
      "piezas": [
        {
          "id_pieza": "Repisa_Superior",
          "x": 0,
          "y": 0,
          "ancho": 2000,
          "largo": 300
        }
      ],
      "retazos_utiles": [
        {
          "id_pieza": "RETAZO_FILA",
          "x": 2004,
          "y": 0,
          "ancho": 436,
          "largo": 300
        },
        {
          "id_pieza": "RETAZO_SUPERIOR",
          "x": 0,
          "y": 304,
          "ancho": 2440,
          "largo": 916
        }
      ]
    }
  ]
}

generar_svg(respuesta_swagger)