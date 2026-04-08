"""
Motor de Web Scraping Asíncrono — Sodimac y Easy Chile.

Sodimac : Aspiradora Cuántica — parsea __NEXT_DATA__ (Next.js JSON)
Easy    : Next.js __NEXT_DATA__ → pageProps.serverProductsResponse.productList
          (Easy migró de VTEX IO a Next.js en 2025/2026)

IMPORTANTE: este archivo no importa nada de sí mismo.
Todos los helpers (_limpiar_precio, etc.) están definidos aquí.
"""

import asyncio
import json
import logging
import random
import re
import traceback
from datetime import datetime
from typing import Any, List, Optional
from urllib.parse import quote_plus

from playwright.async_api import BrowserContext, Page, Response, async_playwright

# playwright-stealth: soft import. Si no está instalado el scraper sigue
# funcionando, sólo pierde la capa anti-bot. Instalar con:
#   pip install playwright-stealth
try:
    from playwright_stealth import stealth_async  # type: ignore
    _STEALTH_AVAILABLE = True
except Exception:  # pragma: no cover
    stealth_async = None  # type: ignore
    _STEALTH_AVAILABLE = False

from .models import EstadoScraping, NombreProveedor
from .schemas import ProductoProveedorCreate
from .scraper_debug import dump_scraper_data

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes globales
# ---------------------------------------------------------------------------

TIMEOUT_BROWSER_MS = 35_000
_EASY_BASE = "https://www.easy.cl"

# Pool de User-Agents reales y recientes (Chrome stable Win/Mac, Edge,
# Firefox). Se rota uno aleatorio por cada nueva sesión de scraping.
# Mantener actualizado: WAFs detectan UAs viejos como bots.
_USER_AGENTS_POOL: tuple[str, ...] = (
    # Chrome 130/131 Win
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome 131 Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Edge 131 Win
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    # Firefox 132 Win
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) "
    "Gecko/20100101 Firefox/132.0",
)


def _pick_user_agent() -> str:
    """Devuelve un UA aleatorio del pool. Llamar una vez por contexto."""
    return random.choice(_USER_AGENTS_POOL)


async def _aplicar_stealth(page: Page) -> None:
    """
    Aplica playwright-stealth si está disponible. Es no-op silencioso si
    la dependencia no está instalada — el scraper sigue funcionando con
    los workarounds manuales (init_script con webdriver=undefined, etc.).
    """
    if _STEALTH_AVAILABLE and stealth_async is not None:
        try:
            await stealth_async(page)
        except Exception as exc:
            logger.debug("stealth_async falló (no fatal): %s", exc)


async def _crear_contexto_evasivo(
    browser, *, viewport: Optional[dict] = None, locale: str = "es-CL"
) -> "BrowserContext":
    """
    Crea un BrowserContext endurecido contra detección de bots:
      - User-Agent aleatorio del pool
      - Headers Accept-Language y sec-ch-ua coherentes
      - init_script que neutraliza señales clásicas de webdriver
      - Viewport por defecto Full HD
    """
    ua = _pick_user_agent()
    context = await browser.new_context(
        viewport=viewport or {"width": 1366, "height": 768},
        user_agent=ua,
        locale=locale,
        extra_http_headers={
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "Upgrade-Insecure-Requests": "1",
        },
    )
    await context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins',  { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages',{ get: () => ['es-CL','es','en-US'] });
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        window.chrome = { runtime: {} };
        const oq = window.navigator.permissions && window.navigator.permissions.query;
        if (oq) {
            window.navigator.permissions.query = (p) => (
                p && p.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : oq(p)
            );
        }
        """
    )
    logger.debug("Contexto evasivo creado UA=%s", ua[:60])
    return context


# ---------------------------------------------------------------------------
# Clase de resultado de scraping
# ---------------------------------------------------------------------------

class ResultadoScraper:
    def __init__(
        self,
        proveedor: NombreProveedor,
        estado: EstadoScraping,
        productos: list = None,
        error_msg: str = None,
        duracion_seg: float = 0.0,
        metodo: str = "auditoria_ruidosa",
    ):
        self.proveedor = proveedor
        self.estado = estado
        self.productos = productos or []
        self.error_msg = error_msg
        self.duracion_seg = duracion_seg
        self.metodo = metodo
        self.timestamp = datetime.utcnow()


# ---------------------------------------------------------------------------
# Helpers universales (usados por ambos scrapers)
# ---------------------------------------------------------------------------

def _limpiar_precio(texto: Any) -> Optional[float]:
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    limpio = re.sub(r"[^\d.,]", "", str(texto).strip())
    if not limpio:
        return None
    limpio = limpio.replace(".", "").replace(",", ".")
    try:
        val = float(limpio)
        return val if val > 0 else None
    except ValueError:
        return None


def _encontrar_precio(obj: Any, max_depth: int = 5) -> Optional[float]:
    if max_depth <= 0:
        return None
    if isinstance(obj, dict):
        # Estructura Easy: { "prices": { "salePrice": X, "normalPrice": Y } }
        prices_obj = obj.get("prices")
        if isinstance(prices_obj, dict):
            for k in ("salePrice", "offerPrice", "normalPrice"):
                val = prices_obj.get(k)
                if val is not None and val != "" and val != 0:
                    v = _limpiar_precio(val)
                    if v and v > 10:
                        return v

        for k in ["priceWithoutFormatting", "Price", "price", "sellingPrice", "offerPrice", "bestPrice"]:
            val = obj.get(k)
            if val is not None and val != "":
                v = _limpiar_precio(val)
                if v and v > 0:
                    return v
        for v in obj.values():
            res = _encontrar_precio(v, max_depth - 1)
            if res:
                return res
    elif isinstance(obj, list):
        for v in obj:
            res = _encontrar_precio(v, max_depth - 1)
            if res:
                return res
    return None



# Patrones que confirman que una URL es de imagen (no una página de producto)
_IMAGE_CDN_PATTERNS = (
    "scene7.com/is/image",
    "/is/image/",
    "media.falabella.com",
    "cloudinary.com",
    "easy.cl/arquivos",
    "arquivos/",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
)

# Claves de dict que con certeza apuntan a imágenes
_IMAGE_DEDICATED_KEYS = (
    "imageUrl", "mediumUrl", "thumbUrl", "smallUrl", "largeUrl",
    "lowResolution", "highResolution", "defaultImage", "primaryImage",
    "thumbnailUrl", "mainImageUrl",
)


def _es_url_imagen(val: str) -> bool:
    """True si la URL parece un recurso de imagen (no una página web)."""
    if not isinstance(val, str) or not val.strip():
        return False
    return any(p in val for p in _IMAGE_CDN_PATTERNS)


def _encontrar_imagen(obj: Any, max_depth: int = 5) -> Optional[str]:
    if max_depth <= 0:
        return None
    if isinstance(obj, dict):
        # 0) Sodimac: "mediaUrls" → lista de strings con CDN Falabella
        media_urls = obj.get("mediaUrls")
        if isinstance(media_urls, list) and media_urls:
            for mu in media_urls:
                if isinstance(mu, str) and mu.startswith("http"):
                    return mu
        # 1) Claves específicamente de imagen → aceptar cualquier URL http
        for k in _IMAGE_DEDICATED_KEYS:
            val = obj.get(k)
            if isinstance(val, str) and val.startswith("http") and val.strip():
                return val
        # 2) Clave "src" → aceptar si parece imagen
        val = obj.get("src")
        if isinstance(val, str) and _es_url_imagen(val):
            return val
        # 3) Claves genéricas "image" / "url" → exigir patrón de CDN de imagen
        for k in ("image", "url"):
            val = obj.get(k)
            if isinstance(val, str) and _es_url_imagen(val):
                return val
        # 4) Recursión
        for v in obj.values():
            res = _encontrar_imagen(v, max_depth - 1)
            if res:
                return res
    elif isinstance(obj, list):
        for v in obj:
            res = _encontrar_imagen(v, max_depth - 1)
            if res:
                return res
    return None


def _aspirar_productos(data: Any, recolectados: list) -> None:
    """Búsqueda recursiva de objetos que parezcan productos (Sodimac y Easy)."""
    if isinstance(data, dict):
        keys = data.keys()
        if any(k in keys for k in ["productId", "skuId", "id", "itemId"]) and any(
            k in keys for k in ["productName", "displayName", "name", "title"]
        ):
            recolectados.append(data)
        for val in data.values():
            _aspirar_productos(val, recolectados)
    elif isinstance(data, list):
        for item in data:
            _aspirar_productos(item, recolectados)


async def _human_delay(min_ms: int = 1000, max_ms: int = 3000) -> None:
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


def _extraer_next_f_push(html: str) -> Optional[Any]:
    """
    Extrae datos de hidratación de Next.js App Router (self.__next_f.push).

    Next.js App Router transmite datos como:
      <script>self.__next_f.push([1,"...JSON_PAYLOAD..."])</script>

    Esto es común cuando el sitio usa RSC (React Server Components)
    y __NEXT_DATA__ está vacío o ausente.
    """
    # Buscar todos los chunks de next_f.push
    patron = re.compile(r'self\.__next_f\.push\(\[(\d+),\s*"((?:[^"\\]|\\.)*)"\]\)', re.DOTALL)
    matches = patron.findall(html)

    if not matches:
        return None

    logger.debug("Encontrados %d chunks de self.__next_f.push", len(matches))

    # Concatenar payloads de texto (type=1 son datos, type=0 son metadatos)
    data_chunks = []
    for chunk_type, payload in matches:
        if chunk_type == "1":
            # Desescapar el string
            try:
                unescaped = payload.encode().decode('unicode_escape')
                data_chunks.append(unescaped)
            except Exception:
                data_chunks.append(payload)

    if not data_chunks:
        return None

    # Buscar JSON válido dentro de los chunks
    combined = "".join(data_chunks)
    productos_encontrados = []

    # Buscar objetos JSON que parezcan productos
    for m in re.finditer(r'\{[^{}]{50,}\}', combined):
        try:
            obj = json.loads(m.group())
            if isinstance(obj, dict):
                keys = obj.keys()
                if any(k in keys for k in ["productId", "skuId", "id"]) and \
                   any(k in keys for k in ["productName", "displayName", "name"]):
                    productos_encontrados.append(obj)
        except json.JSONDecodeError:
            continue

    if productos_encontrados:
        logger.info("self.__next_f.push: %d productos extraídos", len(productos_encontrados))
        return productos_encontrados

    return None


# ---------------------------------------------------------------------------
# ════════════════════════════════════════════════════════════════════════════
#  SCRAPER SODIMAC  ←  NO TOCAR — FUNCIONA PERFECTO
# ════════════════════════════════════════════════════════════════════════════
# ---------------------------------------------------------------------------

class SodimacScraper:
    proveedor = NombreProveedor.SODIMAC

    async def buscar(self, query: str, max_resultados: int, browser) -> ResultadoScraper:
        inicio = asyncio.get_event_loop().time()
        print(f"🟢 [Sodimac] Iniciando búsqueda de: {query}")

        context = None
        try:
            context = await _crear_contexto_evasivo(
                browser, viewport={"width": 1280, "height": 800}
            )
            page = await context.new_page()
            await _aplicar_stealth(page)
            url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"

            print(f"🟢 [Sodimac] Navegando a {url}")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_BROWSER_MS)
            if resp and resp.status in (403, 429):
                logger.warning("[Sodimac] WAF bloqueó la request: status=%s", resp.status)
                return ResultadoScraper(
                    proveedor=NombreProveedor.SODIMAC,
                    estado=EstadoScraping.BLOQUEADO,
                    error_msg=f"WAF bloqueó la request (HTTP {resp.status})",
                    duracion_seg=asyncio.get_event_loop().time() - inicio,
                )
            await _human_delay()

            html = await page.content()
            html = html[:10_000_000]  # limitar a 10MB para evitar OOM
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                html,
                re.DOTALL,
            )

            json_data: Any = None
            productos_crudos: list = []

            if match:
                try:
                    json_data = json.loads(match.group(1))
                except json.JSONDecodeError as exc:
                    logger.warning("[Sodimac] __NEXT_DATA__ JSON inválido: %s", exc)
                    json_data = None

            if json_data is None:
                # Fallback: buscar self.__next_f.push hydration chunks (App Router)
                print(f"[Sodimac] __NEXT_DATA__ no encontrado, intentando self.__next_f.push...")
                next_f_data = _extraer_next_f_push(html)
                if next_f_data:
                    json_data = next_f_data
                    # Para hydration chunks dispersos, usamos extracción recursiva
                    _aspirar_productos(next_f_data, productos_crudos)
                    print(
                        f"[Sodimac] self.__next_f.push: {len(productos_crudos)} productos encontrados"
                    )

                if json_data is None:
                    dump_scraper_data(
                        query=query, proveedor="Sodimac", metodo="next_data",
                        items_crudos=[], productos_finales=[],
                        duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
                        error_msg="__NEXT_DATA__ y self.__next_f.push no encontrados",
                        extra={"html_length": len(html), "url": url},
                    )
                    return ResultadoScraper(
                        self.proveedor, EstadoScraping.ERROR,
                        error_msg="__NEXT_DATA__ no encontrado",
                    )

            # ── Parseo DIRECTO (AAWR/anti-basura): props.pageProps.initialState.products ──
            if not productos_crudos and isinstance(json_data, dict):
                page_props = (
                    json_data.get("props", {}).get("pageProps", {})
                    if isinstance(json_data.get("props"), dict)
                    else {}
                )
                initial_state = page_props.get("initialState") or {}
                direct_products = initial_state.get("products")
                if isinstance(direct_products, list) and direct_products:
                    productos_crudos = direct_products
                    print(
                        f"[Sodimac] Parseo directo initialState.products: "
                        f"{len(productos_crudos)} items"
                    )
                else:
                    # Fallback recursivo si la estructura cambió
                    logger.info(
                        "[Sodimac] initialState.products vacío; fallback recursivo"
                    )
                    _aspirar_productos(json_data, productos_crudos)

            productos: List[ProductoProveedorCreate] = []
            vistos: set = set()

            for item in productos_crudos:
                if len(productos) >= max_resultados:
                    break
                sku = str(item.get("productId") or item.get("skuId") or item.get("id") or "")
                if not sku or sku in vistos:
                    continue
                nombre = str(item.get("displayName") or item.get("name") or "")
                if len(nombre) < 3:
                    continue
                precio_clp = _encontrar_precio(item)
                if not precio_clp or precio_clp < 10:
                    continue

                url_str = item.get("url", "")
                if not url_str.startswith("http"):
                    url_str = "https://www.sodimac.cl" + url_str
                img = _encontrar_imagen(item) or f"https://media.falabella.com/sodimacCL/{sku}/public"

                # Extraer unidad de venta de __NEXT_DATA__
                unidad = (
                    str(item.get("sellUnit") or item.get("unitName") or
                        item.get("unitOfMeasure") or "")[:60] or None
                )
                # Buscar en specifications si no se encontró
                if not unidad:
                    specs = item.get("specifications") or item.get("attributes") or {}
                    if isinstance(specs, dict):
                        for k in ("sellUnit", "unitOfMeasure", "Unidad", "Unidad de venta"):
                            if k in specs:
                                unidad = str(specs[k])[:60]
                                break
                    elif isinstance(specs, list):
                        for spec in specs:
                            if isinstance(spec, dict):
                                spec_name = str(spec.get("name") or spec.get("key") or "").lower()
                                if "unidad" in spec_name or "unit" in spec_name:
                                    unidad = str(spec.get("value") or spec.get("values", [""])[0])[:60]
                                    break

                productos.append(
                    ProductoProveedorCreate(
                        proveedor=self.proveedor,
                        sku_proveedor=sku[:120],
                        url_producto=url_str,
                        nombre_raw=nombre[:400],
                        marca=str(item.get("brandName") or "")[:120] or None,
                        precio_clp=precio_clp,
                        unidad=unidad,
                        imagen_url=img,
                        disponible=True,
                    )
                )
                vistos.add(sku)

            print(f"✅ [Sodimac] ¡ÉXITO! {len(productos)} productos extraídos.")
            dump_scraper_data(
                query=query, proveedor="Sodimac", metodo="next_data",
                items_crudos=productos_crudos, productos_finales=productos,
                duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
            )
            return ResultadoScraper(
                self.proveedor,
                EstadoScraping.EXITO,
                productos,
                duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
            )

        except Exception as exc:
            return ResultadoScraper(
                self.proveedor,
                EstadoScraping.ERROR,
                error_msg=str(exc),
                duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
            )
        finally:
            if context:
                await context.close()


# ---------------------------------------------------------------------------
# ════════════════════════════════════════════════════════════════════════════
#  SCRAPER EASY  —  Next.js __NEXT_DATA__ (migrado desde VTEX IO en 2025)
# ════════════════════════════════════════════════════════════════════════════
# ---------------------------------------------------------------------------

class EasyScraper:
    """
    Scraper para Easy.cl — Next.js con __NEXT_DATA__.

    Easy migró de VTEX IO a Next.js. Los productos de búsqueda se encuentran en:
      __NEXT_DATA__.props.pageProps.serverProductsResponse.productList

    Cada producto tiene: productName, sku, prices.normalPrice, imageUrl, linkText, brand.

    Estrategia:
      Fase 1 → __NEXT_DATA__ del HTML (parsear JSON del script tag)
      Fase 2 → _next/data/{buildId}/search/{query}.json (API directa)
    """

    proveedor = NombreProveedor.EASY

    async def buscar(self, query: str, max_resultados: int, browser) -> ResultadoScraper:
        inicio = asyncio.get_event_loop().time()
        print(f"\n[Easy] ===================================================")
        print(f"[Easy] Iniciando busqueda de: '{query}'")
        print(f"[Easy] ===================================================")

        context = None

        try:
            context = await _crear_contexto_evasivo(
                browser, viewport={"width": 1366, "height": 768}
            )

            page: Page = await context.new_page()
            await _aplicar_stealth(page)

            # Bloquear assets pesados
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf}",
                lambda r: r.abort(),
            )

            # ── Fase 1: Navegar a búsqueda y extraer __NEXT_DATA__ ────
            search_url = f"{_EASY_BASE}/search/{quote_plus(query)}"
            print(f"[Easy] Navegando a {search_url}")
            try:
                easy_resp = await page.goto(search_url, wait_until="domcontentloaded", timeout=TIMEOUT_BROWSER_MS)
            except Exception:
                # Fallback: URL legacy
                search_url = f"{_EASY_BASE}/search?q={quote_plus(query)}"
                print(f"[Easy] Fallback URL: {search_url}")
                easy_resp = await page.goto(search_url, wait_until="domcontentloaded", timeout=TIMEOUT_BROWSER_MS)

            if easy_resp and easy_resp.status in (403, 429):
                logger.warning("[Easy] WAF bloqueó la request: status=%s", easy_resp.status)
                return ResultadoScraper(
                    proveedor=NombreProveedor.EASY,
                    estado=EstadoScraping.BLOQUEADO,
                    error_msg=f"WAF bloqueó la request (HTTP {easy_resp.status})",
                    duracion_seg=asyncio.get_event_loop().time() - inicio,
                )
            await _human_delay()

            html = await page.content()
            html = html[:10_000_000]  # limitar a 10MB para evitar OOM

            # Extraer __NEXT_DATA__
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                html,
                re.DOTALL,
            )

            product_list = []
            build_id = None

            if match:
                print(f"[Easy] [Fase 1] __NEXT_DATA__ encontrado ({len(match.group(1)):,} chars)")
                try:
                    next_data = json.loads(match.group(1))
                    build_id = next_data.get("buildId")
                    product_list = self._extraer_product_list(next_data)
                    print(f"[Easy] [Fase 1] productList tiene {len(product_list)} items")
                except json.JSONDecodeError as exc:
                    print(f"[Easy] [Fase 1] JSON invalido: {exc}")

            if not product_list:
                print(f"[Easy] [Fase 1] Sin productos. Pasando a Fase 2 (API directa)...")

                # ── Fase 2: Obtener buildId y llamar API _next/data ───
                if not build_id:
                    build_id = await self._obtener_build_id(page, html)

                if build_id:
                    product_list = await self._fase_api_next_data(page, build_id, query)
                else:
                    print(f"[Easy] [Fase 2] No se pudo obtener buildId")

            if not product_list:
                print(f"[Easy] FATAL: No se encontraron productos para '{query}'")
                dump_scraper_data(
                    query=query, proveedor="Easy", metodo="next_data_fallido",
                    items_crudos=[], productos_finales=[],
                    duracion_seg=self._duracion(inicio),
                    error_msg="__NEXT_DATA__ sin productList y API fallida",
                    extra={"html_length": len(html), "url": page.url, "build_id": build_id},
                )
                return ResultadoScraper(
                    self.proveedor,
                    EstadoScraping.BLOQUEADO,
                    error_msg="Sin productos en __NEXT_DATA__",
                    duracion_seg=self._duracion(inicio),
                )

            # ── Normalizar productList → ProductoProveedorCreate ──
            productos = self._normalizar_next_data(product_list, max_resultados, query)
            print(f"[Easy] {len(productos)} productos normalizados de {len(product_list)} crudos")

            if productos:
                dump_scraper_data(
                    query=query, proveedor="Easy", metodo="next_data",
                    items_crudos=product_list[:50], productos_finales=productos,
                    duracion_seg=self._duracion(inicio),
                )
                return ResultadoScraper(
                    self.proveedor,
                    EstadoScraping.EXITO,
                    productos,
                    duracion_seg=self._duracion(inicio),
                    metodo="next_data",
                )
            else:
                dump_scraper_data(
                    query=query, proveedor="Easy", metodo="next_data_sin_relevantes",
                    items_crudos=product_list[:50], productos_finales=[],
                    duracion_seg=self._duracion(inicio),
                    error_msg="productList tenia items pero ninguno normalizo correctamente",
                )
                return ResultadoScraper(
                    self.proveedor,
                    EstadoScraping.BLOQUEADO,
                    error_msg="Productos encontrados pero sin precio/nombre valido",
                    duracion_seg=self._duracion(inicio),
                )

        except Exception as exc:
            print(f"[Easy] EXCEPCION NO MANEJADA: {exc}")
            traceback.print_exc()
            dump_scraper_data(
                query=query, proveedor="Easy", metodo="excepcion",
                items_crudos=[], productos_finales=[],
                duracion_seg=self._duracion(inicio),
                error_msg=str(exc),
            )
            return ResultadoScraper(
                self.proveedor,
                EstadoScraping.ERROR,
                error_msg=str(exc),
                duracion_seg=self._duracion(inicio),
            )
        finally:
            if context:
                await context.close()

    # ------------------------------------------------------------------
    # Extracción de productList desde __NEXT_DATA__
    # ------------------------------------------------------------------
    def _extraer_product_list(self, next_data: dict) -> list:
        """
        Navega: props.pageProps.serverProductsResponse.productList
        También intenta pageProps directamente (por si la estructura varía).
        """
        try:
            page_props = next_data.get("props", {}).get("pageProps", {})
            if not page_props:
                page_props = next_data.get("pageProps", {})

            server_resp = page_props.get("serverProductsResponse", {})
            product_list = server_resp.get("productList", [])

            if isinstance(product_list, list) and product_list:
                return product_list

            # Fallback: buscar recursivamente cualquier lista de productos
            return self._buscar_product_list_recursivo(next_data)
        except Exception as exc:
            print(f"[Easy] Error extrayendo productList: {exc}")
            return []

    def _buscar_product_list_recursivo(self, data: Any, depth: int = 5) -> list:
        """Busca recursivamente una lista que contenga objetos con productName."""
        if depth <= 0:
            return []
        if isinstance(data, dict):
            # Buscar claves conocidas
            for key in ("productList", "products", "items", "results"):
                val = data.get(key)
                if isinstance(val, list) and len(val) > 0:
                    if isinstance(val[0], dict) and ("productName" in val[0] or "sku" in val[0]):
                        return val
            for val in data.values():
                result = self._buscar_product_list_recursivo(val, depth - 1)
                if result:
                    return result
        elif isinstance(data, list):
            # Si esta lista parece ser productList
            if len(data) > 0 and isinstance(data[0], dict) and ("productName" in data[0] or "sku" in data[0]):
                return data
            for item in data:
                result = self._buscar_product_list_recursivo(item, depth - 1)
                if result:
                    return result
        return []

    # ------------------------------------------------------------------
    # Fase 2 — API _next/data directa
    # ------------------------------------------------------------------
    async def _obtener_build_id(self, page: Page, html: str) -> Optional[str]:
        """Intenta extraer el buildId de Next.js desde el HTML o JS."""
        # Método 1: regex en HTML
        m = re.search(r'"buildId"\s*:\s*"([^"]+)"', html)
        if m:
            print(f"[Easy] BuildId encontrado en HTML: {m.group(1)}")
            return m.group(1)

        # Método 2: _buildManifest.js URL
        m = re.search(r'/_next/static/([^/]+)/_buildManifest\.js', html)
        if m:
            print(f"[Easy] BuildId encontrado en _buildManifest: {m.group(1)}")
            return m.group(1)

        # Método 3: desde window.__NEXT_DATA__ via JS
        try:
            bid = await page.evaluate("() => window.__NEXT_DATA__?.buildId || null")
            if bid:
                print(f"[Easy] BuildId encontrado via JS: {bid}")
                return bid
        except Exception:
            pass

        return None

    async def _fase_api_next_data(self, page: Page, build_id: str, query: str) -> list:
        """Llama directamente a la API _next/data para obtener productos."""
        api_url = f"{_EASY_BASE}/_next/data/{build_id}/search/{quote_plus(query)}.json?search={quote_plus(query)}"
        print(f"[Easy] [Fase 2] Llamando API: {api_url[:80]}...")

        try:
            response = await page.evaluate(
                """
                async (url) => {
                    try {
                        const resp = await fetch(url, {
                            headers: { 'Accept': 'application/json' }
                        });
                        if (!resp.ok) return { error: resp.status };
                        return await resp.json();
                    } catch(e) {
                        return { error: e.message };
                    }
                }
                """,
                api_url,
            )

            if isinstance(response, dict) and "error" in response:
                print(f"[Easy] [Fase 2] Error API: {response['error']}")
                return []

            # Extraer productList del response
            page_props = response.get("pageProps", {})
            server_resp = page_props.get("serverProductsResponse", {})
            product_list = server_resp.get("productList", [])

            if isinstance(product_list, list):
                print(f"[Easy] [Fase 2] API retorno {len(product_list)} productos")
                return product_list

        except Exception as exc:
            print(f"[Easy] [Fase 2] Excepcion en API: {exc}")

        return []

    # ------------------------------------------------------------------
    # Normalización Next.js productList → ProductoProveedorCreate
    # ------------------------------------------------------------------
    def _normalizar_next_data(
        self, product_list: list, max_resultados: int, query: str
    ) -> List[ProductoProveedorCreate]:
        """
        Mapea los objetos de productList de Easy Next.js a ProductoProveedorCreate.

        Campos del producto Easy Next.js:
          productName  → nombre
          sku          → SKU
          prices.normalPrice / prices.offerPrice → precio
          imageUrl     → imagen
          linkText     → URL (prefijo https://www.easy.cl/)
          brand        → marca
        """
        productos: List[ProductoProveedorCreate] = []
        vistos: set = set()

        # Preparar filtro de relevancia
        query_norm = self._normalizar_texto(query)
        palabras_query = {p for p in query_norm.split() if len(p) >= 3}

        for item in product_list:
            if len(productos) >= max_resultados:
                break
            if not isinstance(item, dict):
                continue

            nombre = str(item.get("productName") or "").strip()
            if not nombre or len(nombre) < 3:
                continue

            # Filtro de relevancia: al menos una palabra del query en el nombre
            if palabras_query:
                nombre_norm = self._normalizar_texto(nombre)
                if not any(p in nombre_norm for p in palabras_query):
                    continue

            sku = str(item.get("sku") or item.get("productId") or "").strip()
            if not sku:
                sku = f"EASY-{abs(hash(nombre)) % 999_999:06d}"
            if sku in vistos:
                continue

            # Precio: offerPrice (descuento) > normalPrice
            precio = self._extraer_precio_easy(item)
            if not precio or precio < 10:
                continue

            # URL del producto
            link_text = str(item.get("linkText") or "").strip()
            if link_text:
                url_producto = f"{_EASY_BASE}/{link_text.lstrip('/')}"
            else:
                url_producto = _EASY_BASE

            # Imagen
            imagen = str(item.get("imageUrl") or "").strip()
            if not imagen:
                imagen = _encontrar_imagen(item) or ""

            # Marca
            marca = str(item.get("brand") or "").strip() or None

            # Unidad de venta — buscar en campos Easy Next.js
            unidad = (
                str(item.get("sellUnit") or item.get("unitOfMeasure") or
                    item.get("unitName") or "").strip()[:60] or None
            )
            if not unidad:
                # Buscar en specifications/attributes
                specs = item.get("specifications") or item.get("attributes") or {}
                if isinstance(specs, dict):
                    for k in ("sellUnit", "unitOfMeasure", "Unidad", "Unidad de venta"):
                        if k in specs:
                            unidad = str(specs[k])[:60]
                            break
                elif isinstance(specs, list):
                    for spec in specs:
                        if isinstance(spec, dict):
                            sn = str(spec.get("name") or spec.get("key") or "").lower()
                            if "unidad" in sn or "unit" in sn:
                                unidad = str(spec.get("value") or "")[:60]
                                break

            try:
                productos.append(
                    ProductoProveedorCreate(
                        proveedor=self.proveedor,
                        sku_proveedor=sku[:120],
                        url_producto=url_producto,
                        nombre_raw=nombre[:400],
                        marca=marca,
                        precio_clp=float(precio),
                        unidad=unidad,
                        imagen_url=imagen or None,
                        disponible=True,
                    )
                )
                vistos.add(sku)
                print(f"  [Easy] + {nombre[:60]} | SKU:{sku} | ${precio:,.0f}")
            except Exception as exc:
                print(f"  [Easy] Error normalizando: {exc}")

        return productos

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------
    @staticmethod
    def _extraer_precio_easy(item: dict) -> Optional[float]:
        """
        Extrae precio del objeto Easy Next.js.
        Prioridad: offerPrice (descuento) > normalPrice > commercialOffer.
        Los precios son enteros en CLP.
        """
        prices = item.get("prices")
        if isinstance(prices, dict):
            # Preferir offerPrice si existe (precio con descuento)
            offer = prices.get("offerPrice")
            if offer is not None:
                try:
                    val = float(offer)
                    if val > 0:
                        return val
                except (TypeError, ValueError):
                    pass
            # Precio normal
            normal = prices.get("normalPrice")
            if normal is not None:
                try:
                    val = float(normal)
                    if val > 0:
                        return val
                except (TypeError, ValueError):
                    pass

        # Fallback: commercialOffer.defaultOffer.prices
        comm = item.get("commercialOffer", {})
        if isinstance(comm, dict):
            default_offer = comm.get("defaultOffer", {})
            if isinstance(default_offer, dict):
                inner_prices = default_offer.get("prices", {})
                if isinstance(inner_prices, dict):
                    for key in ("offerPrice", "normalPrice"):
                        val = inner_prices.get(key)
                        if val is not None:
                            try:
                                fval = float(val)
                                if fval > 0:
                                    return fval
                            except (TypeError, ValueError):
                                pass

        # Fallback genérico
        return _encontrar_precio(item)

    @staticmethod
    def _normalizar_texto(texto: str) -> str:
        """Normaliza texto quitando tildes y pasando a minúsculas."""
        return (
            texto.lower().strip()
            .replace("a\u0301", "a").replace("e\u0301", "e").replace("i\u0301", "i")
            .replace("o\u0301", "o").replace("u\u0301", "u")
            .replace("\xe1", "a").replace("\xe9", "e").replace("\xed", "i")
            .replace("\xf3", "o").replace("\xfa", "u").replace("\xf1", "n")
        )

    @staticmethod
    def _duracion(inicio: float) -> float:
        return round(asyncio.get_event_loop().time() - inicio, 2)


# ---------------------------------------------------------------------------
# Orquestador Principal
# ---------------------------------------------------------------------------

class ScraperOrchestrator:
    _SCRAPERS = {
        NombreProveedor.SODIMAC: SodimacScraper,
        NombreProveedor.EASY: EasyScraper,
    }

    async def buscar(
        self,
        query: str,
        proveedores: list[NombreProveedor],
        max_resultados: int = 10,
    ) -> list[ResultadoScraper]:
        print(f"\n{'='*55}")
        print(f"🔥 INICIANDO EXTRACCIÓN PARA: '{query}'")
        print(f"{'='*55}\n")

        prov_validos = [p for p in proveedores if p in self._SCRAPERS]
        if not prov_validos:
            return []

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )

                tareas = [
                    self._SCRAPERS[p]().buscar(query, max_resultados, browser)
                    for p in prov_validos
                ]
                resultados_raw = await asyncio.gather(*tareas, return_exceptions=True)

                resultados = []
                for p, r in zip(prov_validos, resultados_raw):
                    if isinstance(r, Exception):
                        print(f"🔴 ERROR FATAL en tarea de {p}: {r}")
                        resultados.append(
                            ResultadoScraper(p, EstadoScraping.ERROR, error_msg=str(r))
                        )
                    else:
                        resultados.append(r)

                print("🛑 Cerrando navegador...")
                await browser.close()
                return resultados

        except Exception as exc:
            print(f"💥 CRASHEO DEL SISTEMA: {exc}")
            traceback.print_exc()
            return []


async def ejecutar_busqueda(
    query: str,
    proveedores: list[NombreProveedor],
    max_resultados: int = 10,
) -> list[ResultadoScraper]:
    return await ScraperOrchestrator().buscar(query, proveedores, max_resultados)