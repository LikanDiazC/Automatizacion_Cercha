"""
Motor de Web Scraping Asíncrono — Sodimac y Easy Chile.
Sodimac: Aspiradora Cuántica (JSON) | Easy: Emulación Humana (Escritura en Buscador) + GraphQL
"""

import asyncio
import logging
import re
import json
import traceback
from datetime import datetime
from typing import Optional, Any, List, Dict
from urllib.parse import quote_plus

from playwright.async_api import async_playwright

from .models import EstadoScraping, NombreProveedor
from .schemas import ProductoProveedorCreate

logger = logging.getLogger(__name__)

TIMEOUT_BROWSER_MS = 35_000

class ResultadoScraper:
    def __init__(self, proveedor: NombreProveedor, estado: EstadoScraping, productos: list = None, error_msg: str = None, duracion_seg: float = 0.0, metodo: str = "auditoria_ruidosa"):
        self.proveedor = proveedor
        self.estado = estado
        self.productos = productos or []
        self.error_msg = error_msg
        self.duracion_seg = duracion_seg
        self.metodo = metodo
        self.timestamp = datetime.utcnow()

# --- Helpers Universales ---
def _limpiar_precio(texto: Any) -> Optional[float]:
    if texto is None: return None
    if isinstance(texto, (int, float)): return float(texto)
    limpio = re.sub(r"[^\d.,]", "", str(texto).strip())
    if not limpio: return None
    limpio = limpio.replace(".", "").replace(",", ".")
    try:
        val = float(limpio)
        return val if val > 0 else None
    except ValueError:
        return None

def _encontrar_precio(obj: Any, max_depth: int = 5) -> Optional[float]:
    if max_depth <= 0: return None
    if isinstance(obj, dict):
        for k in ["priceWithoutFormatting", "Price", "price", "sellingPrice", "offerPrice", "bestPrice"]:
            val = obj.get(k)
            if val is not None and val != "":
                v = _limpiar_precio(val)
                if v and v > 0: return v
        for v in obj.values():
            res = _encontrar_precio(v, max_depth - 1)
            if res: return res
    elif isinstance(obj, list):
        for v in obj:
            res = _encontrar_precio(v, max_depth - 1)
            if res: return res
    return None

def _encontrar_imagen(obj: Any, max_depth: int = 5) -> Optional[str]:
    if max_depth <= 0: return None
    if isinstance(obj, dict):
        for k in ["imageUrl", "image", "url", "src", "defaultImage"]:
            val = obj.get(k)
            if isinstance(val, str) and (val.startswith("http") or ".jpg" in val or ".png" in val or ".webp" in val):
                return val
        for v in obj.values():
            res = _encontrar_imagen(v, max_depth - 1)
            if res: return res
    elif isinstance(obj, list):
        for v in obj:
            res = _encontrar_imagen(v, max_depth - 1)
            if res: return res
    return None

def _aspirar_productos(data: Any, recolectados: list):
    if isinstance(data, dict):
        keys = data.keys()
        if any(k in keys for k in ["productId", "skuId", "id", "itemId"]) and any(k in keys for k in ["productName", "displayName", "name", "title"]):
            recolectados.append(data)
        for val in data.values():
            _aspirar_productos(val, recolectados)
    elif isinstance(data, list):
        for item in data:
            _aspirar_productos(item, recolectados)

# ---------------------------------------------------------------------------
# Scraper SODIMAC (NO TOCAR - FUNCIONA PERFECTO)
# ---------------------------------------------------------------------------
class SodimacScraper:
    proveedor = NombreProveedor.SODIMAC

    async def buscar(self, query: str, max_resultados: int, browser) -> ResultadoScraper:
        inicio = asyncio.get_event_loop().time()
        print(f"🟢 [Sodimac] Iniciando búsqueda de: {query}")
        
        try:
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"

            print(f"🟢 [Sodimac] Navegando a {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_BROWSER_MS)
            await asyncio.sleep(2)

            html = await page.content()
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            
            if not match:
                return ResultadoScraper(self.proveedor, EstadoScraping.ERROR, error_msg="__NEXT_DATA__ no encontrado")

            json_data = json.loads(match.group(1))
            productos_crudos = []
            _aspirar_productos(json_data, productos_crudos)
            
            productos = []
            vistos = set()
            for item in productos_crudos:
                if len(productos) >= max_resultados: break
                sku = str(item.get("productId") or item.get("skuId") or item.get("id") or "")
                if not sku or sku in vistos: continue
                nombre = str(item.get("displayName") or item.get("name") or "")
                if len(nombre) < 3: continue
                precio_clp = _encontrar_precio(item)
                if not precio_clp or precio_clp < 10: continue
                
                url_str = item.get("url", "")
                if not url_str.startswith("http"): url_str = "https://www.sodimac.cl" + url_str
                img = _encontrar_imagen(item) or f"https://sodimac.scene7.com/is/image/SodimacCL/{sku}"
                
                productos.append(ProductoProveedorCreate(
                    proveedor=self.proveedor, sku_proveedor=sku[:120], url_producto=url_str,
                    nombre_raw=nombre[:400], marca=str(item.get("brandName") or "")[:120] or None,
                    precio_clp=precio_clp, imagen_url=img, disponible=True
                ))
                vistos.add(sku)
            
            print(f"✅ [Sodimac] ¡ÉXITO! {len(productos)} productos extraídos.")
            return ResultadoScraper(self.proveedor, EstadoScraping.EXITO, productos, duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2))

        except Exception as e:
            return ResultadoScraper(self.proveedor, EstadoScraping.ERROR, error_msg=str(e), duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2))
        finally:
            await context.close()


# ---------------------------------------------------------------------------
# Scraper EASY (Emulación Humana en Buscador)
# ---------------------------------------------------------------------------
class EasyScraper:
    proveedor = NombreProveedor.EASY

    async def buscar(self, query: str, max_resultados: int, browser) -> ResultadoScraper:
        inicio = asyncio.get_event_loop().time()
        print(f"🔵 [Easy] Iniciando búsqueda HUMANA de: {query}")
        
        try:
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            
            productos_capturados = None

            # 🕵️‍♂️ EL ESPÍA (Escucha GraphQL mientras navegamos)
            async def interceptar_respuesta(response):
                nonlocal productos_capturados
                if response.request.method == "OPTIONS": return
                
                resp_url = response.url.lower()
                if "graphql" in resp_url or "search" in resp_url:
                    try:
                        data = await response.json()
                        dump = str(data)
                        
                        if "productId" in dump or "productName" in dump:
                            if isinstance(data, list):
                                for query_res in data:
                                    if isinstance(query_res, dict) and "data" in query_res:
                                        ps = query_res["data"].get("productSearch", {})
                                        if ps and "products" in ps and ps["products"]:
                                            productos_capturados = ps["products"]
                                            print(f"   🚀 [Easy Network] ¡BINGO! GraphQL atrapó {len(productos_capturados)} productos.")
                                            return
                            elif isinstance(data, dict) and "data" in data:
                                ps = data["data"].get("productSearch", {})
                                if ps and "products" in ps and ps["products"]:
                                    productos_capturados = ps["products"]
                                    print(f"   🚀 [Easy Network] ¡BINGO! GraphQL atrapó {len(productos_capturados)} productos.")
                                    return
                    except Exception:
                        pass

            page.on("response", interceptar_respuesta)

            # 1. Navegamos a la HOME para no activar bloqueos de URL directa
            print(f"🔵 [Easy] Entrando por la puerta principal (Home)...")
            await page.goto("https://www.easy.cl/", wait_until="domcontentloaded", timeout=TIMEOUT_BROWSER_MS)
            await asyncio.sleep(2)

            # 2. Simulamos que somos un humano buscando en la barra
            print(f"🔵 [Easy] Escribiendo '{query}' en el buscador de la página...")
            
            # Buscamos el Input del buscador (VTEX usa estos selectores)
            search_selectors = [
                'input[placeholder*="uscar"]',
                'input[type="search"]',
                '[class*="searchBar"] input'
            ]
            
            busqueda_lanzada = False
            for sel in search_selectors:
                try:
                    if await page.locator(sel).count() > 0:
                        await page.fill(sel, query) # Escribe el texto
                        await asyncio.sleep(0.5)
                        await page.press(sel, "Enter") # Presiona Enter
                        busqueda_lanzada = True
                        print(f"🔵 [Easy] Búsqueda lanzada con Enter con éxito.")
                        break
                except:
                    pass
            
            # Si por alguna razón no encuentra el buscador, forzamos la URL como plan de emergencia
            if not busqueda_lanzada:
                print("🔵 [Easy] No se encontró el buscador visual, usando URL directa...")
                await page.goto(f"https://www.easy.cl/search?q={quote_plus(query)}", wait_until="domcontentloaded")
            
            print("🔵 [Easy] Esperando resultados...")
            for _ in range(6):
                await page.evaluate("window.scrollBy(0, 900)")
                await asyncio.sleep(1.5)
                if productos_capturados: 
                    break
                
            # 🛡️ PLAN B: Extracción Visual DOM RUIDOSA
            if not productos_capturados:
                print("🔵 [Easy] La red falló. Activando Plan B (DOM Scraping)...")
                script_visual = """
                () => {
                    const items = [];
                    const cards = document.querySelectorAll('section.vtex-product-summary-2-x-container, .vtex-search-result-3-x-galleryItem section, article, [class*="productSummary"], .product-item');
                    
                    cards.forEach(card => {
                        const nameEl = card.querySelector('[class*="productName"], [class*="productBrand"], [class*="nameComplete"], h2, h3');
                        const priceEl = card.querySelector('[class*="sellingPrice"], [class*="price_sellingPrice"], [class*="price"]:not([class*="listPrice"])');
                        const imgEl = card.querySelector('img');
                        const linkEl = card.tagName.toLowerCase() === 'a' ? card : card.querySelector('a');
                        
                        if (nameEl && priceEl && priceEl.innerText.match(/\\d/)) {
                            items.push({
                                name: nameEl.innerText.trim(),
                                price: priceEl.innerText.trim(),
                                link: linkEl ? linkEl.href : '',
                                image: imgEl ? imgEl.src : '',
                                sku: card.getAttribute('data-product-id') || card.getAttribute('id') || ''
                            });
                        }
                    });
                    return items;
                }
                """
                productos_dom = await page.evaluate(script_visual)
                if productos_dom and len(productos_dom) > 0:
                    productos_capturados = productos_dom

            if not productos_capturados:
                print("🔴 [Easy] FATAL ERROR: Ni la Red ni el DOM encontraron productos.")
                return ResultadoScraper(self.proveedor, EstadoScraping.BLOQUEADO, error_msg="GraphQL y DOM fallaron", duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2))

            # Normalizar
            if isinstance(productos_capturados[0], dict) and "price" in productos_capturados[0] and "name" in productos_capturados[0]:
                productos = self._normalizar_dom(productos_capturados, max_resultados)
            else:
                productos = self._normalizar_graphql(productos_capturados, max_resultados)
            
            print(f"✅ [Easy] ¡ÉXITO FINAL! {len(productos)} productos listos.")
            return ResultadoScraper(self.proveedor, EstadoScraping.EXITO, productos, duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2))

        except Exception as e:
            print(f"🔴 [Easy] CRASHEO INTERNO: {e}")
            traceback.print_exc()
            return ResultadoScraper(self.proveedor, EstadoScraping.ERROR, error_msg=str(e), duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2))
        finally:
            await context.close()

    def _normalizar_graphql(self, items: list, max_res: int) -> List[ProductoProveedorCreate]:
        productos = []
        for item in items[:max_res]:
            sku = str(item.get("productId") or "")
            nombre = str(item.get("productName") or "")
            link_text = item.get("linkText", "")
            url = f"https://www.easy.cl/{link_text}"
            
            precio = None
            img = None
            sub_items = item.get("items", [])
            if sub_items:
                images = sub_items[0].get("images", [])
                if images: img = images[0].get("imageUrl")
                sellers = sub_items[0].get("sellers", [])
                if sellers:
                    oferta = sellers[0].get("commertialOffer", {})
                    precio = oferta.get("Price") or oferta.get("ListPrice")
            
            if not precio or not sku or not nombre: continue
            try:
                productos.append(ProductoProveedorCreate(
                    proveedor=self.proveedor, sku_proveedor=sku[:120], url_producto=url,
                    nombre_raw=nombre[:400], marca=item.get("brand"),
                    precio_clp=float(precio), imagen_url=img, disponible=True
                ))
            except Exception: pass
        return productos

    def _normalizar_dom(self, items: list, max_res: int) -> List[ProductoProveedorCreate]:
        productos = []
        vistos = set()
        for item in items[:max_res]:
            precio_clp = _limpiar_precio(item.get("price"))
            if not precio_clp: continue
            
            url = item.get("link", "")
            if not url.startswith("http"): url = "https://www.easy.cl" + url
            
            sku = str(item.get("sku") or "")
            if not sku: sku = f"EASY-{hash(url)%999999:06d}"
            if sku in vistos: continue
            
            try:
                productos.append(ProductoProveedorCreate(
                    proveedor=self.proveedor, sku_proveedor=sku[:120], url_producto=url,
                    nombre_raw=item.get("name", "Sin nombre")[:400], marca=item.get("brand") or None,
                    precio_clp=precio_clp, imagen_url=item.get("image"), disponible=True
                ))
                vistos.add(sku)
            except Exception: pass
        return productos


# ---------------------------------------------------------------------------
# Orquestador Principal
# ---------------------------------------------------------------------------
class ScraperOrchestrator:
    _SCRAPERS = {NombreProveedor.SODIMAC: SodimacScraper, NombreProveedor.EASY: EasyScraper}

    async def buscar(self, query: str, proveedores: list[NombreProveedor], max_resultados: int = 10) -> list[ResultadoScraper]:
        print(f"\n=======================================================")
        print(f"🔥 INICIANDO EXTRACCIÓN DEFINITIVA PARA: '{query}'")
        print(f"=======================================================\n")
        
        prov_validos = [p for p in proveedores if p in self._SCRAPERS]
        if not prov_validos: return []

        try:
            async with async_playwright() as pw:
                # Ventana visible para que VEAS cómo escribe solito en el buscador
                browser = await pw.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
                
                tareas = [self._SCRAPERS[p]().buscar(query, max_resultados, browser) for p in prov_validos]
                resultados_raw = await asyncio.gather(*tareas, return_exceptions=True)
                
                resultados = []
                for p, r in zip(prov_validos, resultados_raw):
                    if isinstance(r, Exception):
                        print(f"🔴 ERROR FATAL en tarea de {p}: {r}")
                        resultados.append(ResultadoScraper(p, EstadoScraping.ERROR, error_msg=str(r)))
                    else:
                        resultados.append(r)
                
                print("🛑 Cerrando navegador...")
                await browser.close()
                return resultados
        except Exception as e:
            print(f"💥 CRASHEO DEL SISTEMA: {e}")
            traceback.print_exc()
            return []

async def ejecutar_busqueda(query: str, proveedores: list[NombreProveedor], max_resultados: int = 10) -> list[ResultadoScraper]:
    return await ScraperOrchestrator().buscar(query, proveedores, max_resultados)