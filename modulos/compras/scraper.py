"""
Motor de Web Scraping Asíncrono — Sodimac y Easy Chile.

Sodimac : Aspiradora Cuántica — parsea __NEXT_DATA__ (Next.js JSON)
Easy    : Triple fallback VTEX IO
           Fase 1 → Network Interception (GraphQL batched / XHR)
           Fase 2 → window.__STATE__ (Apollo Client cache)
           Fase 3 → DOM Scraping con scroll forzado + JS agresivo

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

from playwright.async_api import Page, Response, async_playwright

from .models import EstadoScraping, NombreProveedor
from .schemas import ProductoProveedorCreate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes globales
# ---------------------------------------------------------------------------

TIMEOUT_BROWSER_MS = 35_000
_EASY_BASE = "https://www.easy.cl"
_EASY_SEARCH = f"{_EASY_BASE}/search?q={{query}}&O=OrderByScoreDESC"

# Señales en URLs que indican respuesta con datos de producto
_URL_PRODUCT_SIGNALS = [
    "graphql",
    "search-graphql",
    "product",
    "search?q=",
    "search?Q=",
    "_v/api",
    "catalog_system",
]

# Selectores DOM VTEX IO, de más a menos específico
_VTEX_SELECTORS = [
    "[class*='vtex-product-summary-2-x-container']",
    "[class*='productSummary']",
    "[class*='galleryItem'] section",
    "[data-product-id]",
    "section[class*='product']",
    "article[class*='product']",
    ".shelf-item",
]

# Campos de precio VTEX según versión de la plataforma
_PRICE_KEYS = [
    "Price", "price", "sellingPrice", "SellingPrice",
    "bestPrice", "offerPrice", "priceWithoutFormatting",
]


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


def _encontrar_imagen(obj: Any, max_depth: int = 5) -> Optional[str]:
    if max_depth <= 0:
        return None
    if isinstance(obj, dict):
        for k in ["imageUrl", "image", "url", "src", "defaultImage"]:
            val = obj.get(k)
            if isinstance(val, str) and (
                val.startswith("http")
                or ".jpg" in val
                or ".png" in val
                or ".webp" in val
            ):
                return val
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


async def _human_delay(min_ms: int = 300, max_ms: int = 1000) -> None:
    await asyncio.sleep(random.uniform(min_ms / 1000, max_ms / 1000))


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
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            url = f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"

            print(f"🟢 [Sodimac] Navegando a {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_BROWSER_MS)
            await asyncio.sleep(2)

            html = await page.content()
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                html,
                re.DOTALL,
            )

            if not match:
                return ResultadoScraper(
                    self.proveedor, EstadoScraping.ERROR,
                    error_msg="__NEXT_DATA__ no encontrado",
                )

            json_data = json.loads(match.group(1))
            productos_crudos: list = []
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
                img = _encontrar_imagen(item) or f"https://sodimac.scene7.com/is/image/SodimacCL/{sku}"

                productos.append(
                    ProductoProveedorCreate(
                        proveedor=self.proveedor,
                        sku_proveedor=sku[:120],
                        url_producto=url_str,
                        nombre_raw=nombre[:400],
                        marca=str(item.get("brandName") or "")[:120] or None,
                        precio_clp=precio_clp,
                        imagen_url=img,
                        disponible=True,
                    )
                )
                vistos.add(sku)

            print(f"✅ [Sodimac] ¡ÉXITO! {len(productos)} productos extraídos.")
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
#  SCRAPER EASY  —  Triple fallback VTEX IO
# ════════════════════════════════════════════════════════════════════════════
# ---------------------------------------------------------------------------

class EasyScraper:
    """
    Scraper robusto para Easy.cl (VTEX IO / Cencosud).

    Estrategia en cascada:
      Fase 1 → Network Interception  (GraphQL batched / XHR)
      Fase 2 → window.__STATE__      (Apollo Client cache)
      Fase 3 → DOM Scraping          (scroll forzado + JS agresivo)
    """

    proveedor = NombreProveedor.EASY

    def __init__(self):
        # Acumulador de payloads de red capturados por el interceptor
        self._payloads_red: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Punto de entrada (misma firma que SodimacScraper)
    # ------------------------------------------------------------------
    async def buscar(self, query: str, max_resultados: int, browser) -> ResultadoScraper:
        inicio = asyncio.get_event_loop().time()
        print(f"\n🔵 [Easy] ═══════════════════════════════════════")
        print(f"🔵 [Easy] Iniciando búsqueda de: '{query}'")
        print(f"🔵 [Easy] ═══════════════════════════════════════")

        self._payloads_red.clear()
        context = None

        try:
            # ── Context con stealth ────────────────────────────────────
            context = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="es-CL",
                extra_http_headers={
                    "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
                    "sec-ch-ua": (
                        '"Chromium";v="124", "Google Chrome";v="124",'
                        ' "Not-A.Brand";v="99"'
                    ),
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-ch-ua-mobile": "?0",
                },
            )

            # Ocultar navigator.webdriver — señal principal de bot detection
            await context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['es-CL', 'es', 'en-US'] });
                window.chrome = { runtime: {} };
                """
            )

            page: Page = await context.new_page()

            # Bloquear assets pesados que no aportan datos de producto
            await page.route(
                "**/*.{png,jpg,jpeg,gif,webp,svg,ico,woff,woff2,ttf}",
                lambda r: r.abort(),
            )

            # ── Interceptor de red activo ─────────────────────────────
            page.on("response", self._capturar_respuesta)

            # ── Fase 0: Warm-up en Home (establece cookies VTEX) ──────
            await self._warmup(page)

            # ── Navegar a la página de resultados ─────────────────────
            await self._navegar_a_resultados(page, query)

            # ── Fase 1: Procesar lo que capturó la red ─────────────────
            print(f"🔵 [Easy] [Fase 1] Procesando {len(self._payloads_red)} payloads de red...")
            productos = self._procesar_red(max_resultados)

            if productos:
                print(f"✅ [Easy] [Fase 1] ÉXITO — {len(productos)} productos via red")
                return self._resultado_ok(productos, inicio, "network")

            print(f"⚠️  [Easy] [Fase 1] Sin resultados. Pasando a Fase 2...")

            # ── Fase 2: window.__STATE__ / Apollo cache ─────────────────
            print(f"🔵 [Easy] [Fase 2] Extrayendo window.__STATE__...")
            productos = await self._fase_state(page, max_resultados)

            if productos:
                print(f"✅ [Easy] [Fase 2] ÉXITO — {len(productos)} productos via __STATE__")
                return self._resultado_ok(productos, inicio, "apollo_state")

            print(f"⚠️  [Easy] [Fase 2] Sin resultados. Pasando a Fase 3...")

            # ── Fase 3: DOM Scraping ────────────────────────────────────
            print(f"🔵 [Easy] [Fase 3] Iniciando DOM scraping con scroll...")
            productos = await self._fase_dom(page, max_resultados)

            if productos:
                print(f"✅ [Easy] [Fase 3] ÉXITO — {len(productos)} productos via DOM")
                return self._resultado_ok(productos, inicio, "dom")

            print(f"🔴 [Easy] FATAL: Todas las fases fallaron para '{query}'")
            return ResultadoScraper(
                self.proveedor,
                EstadoScraping.BLOQUEADO,
                error_msg="Fases 1+2+3 sin resultados",
                duracion_seg=self._duracion(inicio),
            )

        except Exception as exc:
            print(f"🔴 [Easy] EXCEPCIÓN NO MANEJADA: {exc}")
            traceback.print_exc()
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
    # Fase 0 — Warm-up (cookies VTEX)
    # ------------------------------------------------------------------
    async def _warmup(self, page: Page) -> None:
        """
        Visita la Home para que VTEX establezca vtex_segment y vtex_session.
        Sin estas cookies, la búsqueda directa puede redirigir al inicio.
        """
        print(f"🔵 [Easy] [Warmup] Visitando Home para cookies VTEX...")
        try:
            await page.goto(_EASY_BASE + "/", wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(random.uniform(1.2, 2.5))

            for _ in range(2):
                await page.mouse.move(random.randint(200, 1100), random.randint(100, 500))
                await asyncio.sleep(random.uniform(0.1, 0.3))

            print(f"🔵 [Easy] [Warmup] Cookies OK. URL: {page.url}")
        except Exception as exc:
            print(f"⚠️  [Easy] [Warmup] Falló ({exc}). Continuando de todas formas...")

    # ------------------------------------------------------------------
    # Navegación a resultados
    # ------------------------------------------------------------------
    async def _navegar_a_resultados(self, page: Page, query: str) -> None:
        exitoso = await self._buscar_con_input(page, query)

        if not exitoso:
            url_directa = _EASY_SEARCH.format(query=quote_plus(query))
            print(f"🔵 [Easy] Fallback URL directa: {url_directa}")
            try:
                await page.goto(url_directa, wait_until="domcontentloaded", timeout=30_000)
            except Exception:
                await page.goto(url_directa, wait_until="load", timeout=30_000)

        print(f"🔵 [Easy] Página de resultados cargada. URL: {page.url}")
        await asyncio.sleep(random.uniform(2.0, 3.5))

    async def _buscar_con_input(self, page: Page, query: str) -> bool:
        """Escribe en el buscador de la Home como lo haría un humano."""
        selectores = [
            'input[placeholder*="uscar"]',
            'input[placeholder*="earch"]',
            'input[type="search"]',
            '[class*="searchBar"] input',
            '[class*="search-bar"] input',
            'header input',
        ]
        for sel in selectores:
            try:
                loc = page.locator(sel).first
                if await loc.count() == 0:
                    continue
                print(f"🔵 [Easy] Input encontrado con: {sel}")
                await loc.click()
                await asyncio.sleep(0.3)
                await loc.type(query, delay=random.randint(40, 90))
                await asyncio.sleep(0.4)
                await page.keyboard.press("Enter")
                print(f"🔵 [Easy] Búsqueda lanzada desde input visual.")
                await asyncio.sleep(random.uniform(2.5, 4.0))
                return True
            except Exception as exc:
                print(f"⚠️  [Easy] Selector '{sel}' falló: {exc}")
        print(f"⚠️  [Easy] No se encontró buscador visual.")
        return False

    # ------------------------------------------------------------------
    # Interceptor de red (callback asíncrono)
    # ------------------------------------------------------------------
    async def _capturar_respuesta(self, response: Response) -> None:
        if response.status != 200:
            return
        ct = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        url = response.url
        if any(x in url for x in ["gtm", "analytics", "pixel", "hotjar", "insider"]):
            return
        if not any(sig in url.lower() for sig in _URL_PRODUCT_SIGNALS):
            return
        try:
            data = await response.json()
            texto = json.dumps(data) if not isinstance(data, str) else data
            if any(s in texto for s in ["productId", "productName", "commertialOffer", "CommercialOffer"]):
                self._payloads_red.append({"url": url, "data": data})
                print(f"   🕵️  [Easy Net] Payload capturado: {url[:70]}...")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Fase 1 — Procesar payloads de red
    # ------------------------------------------------------------------
    def _procesar_red(self, max_resultados: int) -> List[ProductoProveedorCreate]:
        items_crudos: list = []
        for payload in self._payloads_red:
            data = payload["data"]
            url = payload["url"]
            print(f"   🔍 [Fase 1] Analizando: {url[:60]}...")

            # Búsqueda recursiva general
            _aspirar_productos(data, items_crudos)

            # Rutas específicas de GraphQL VTEX
            items_crudos.extend(self._rutas_vtex(data))

        print(f"   🔍 [Fase 1] Items crudos en red: {len(items_crudos)}")
        return self._normalizar_items(items_crudos, max_resultados, "network")

    def _rutas_vtex(self, data: Any) -> list:
        encontrados: list = []
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    encontrados.extend(self._extraer_de_graphql_data(entry.get("data", {})))
        elif isinstance(data, dict):
            encontrados.extend(self._extraer_de_graphql_data(data.get("data", data)))
        return encontrados

    def _extraer_de_graphql_data(self, data: dict) -> list:
        if not isinstance(data, dict):
            return []
        encontrados = []
        for raiz in [
            data.get("productSearch", {}),
            data.get("search", {}),
            data.get("products", {}),
            data.get("searchResult", {}),
        ]:
            if not isinstance(raiz, dict):
                continue
            prods = raiz.get("products") or raiz.get("items") or []
            if isinstance(prods, list) and prods:
                print(f"   ✨ [Fase 1] Ruta GraphQL → {len(prods)} productos")
                encontrados.extend(prods)
        return encontrados

    # ------------------------------------------------------------------
    # Fase 2 — Apollo / VTEX __STATE__
    # ------------------------------------------------------------------
    async def _fase_state(self, page: Page, max_resultados: int) -> List[ProductoProveedorCreate]:
        state_str: Optional[str] = await page.evaluate(
            """
            () => {
                if (window.__STATE__) return JSON.stringify(window.__STATE__);
                if (window.__NEXT_DATA__) return JSON.stringify(window.__NEXT_DATA__);
                if (window.__RUNTIME__ && window.__RUNTIME__.queryData)
                    return JSON.stringify(window.__RUNTIME__.queryData);
                for (const el of document.querySelectorAll('script[type="application/json"]')) {
                    const t = el.textContent || '';
                    if (t.includes('productId')) return t;
                }
                for (const el of document.querySelectorAll('script:not([src])')) {
                    const t = el.textContent || '';
                    if (t.startsWith('window.__STATE__'))
                        return t.replace(/^window\\.__STATE__\\s*=\\s*/, '').replace(/;\\s*$/, '');
                }
                return null;
            }
            """
        )

        if not state_str:
            print(f"   ⚠️  [Fase 2] No se encontró __STATE__.")
            return []

        print(f"   🟢 [Fase 2] __STATE__ encontrado ({len(state_str):,} chars). Parseando...")

        try:
            state = json.loads(state_str)
        except json.JSONDecodeError as exc:
            print(f"   🔴 [Fase 2] JSON inválido: {exc}")
            return []

        items_crudos: list = []
        if isinstance(state, dict):
            for key, val in state.items():
                if not isinstance(val, dict):
                    continue
                # Claves Apollo: "Product:ID", "StoreProduct:ID", etc.
                if any(key.startswith(p) for p in ("Product:", "StoreProduct:", "SKU:", "Item:")):
                    items_crudos.append(val)
                elif "data" in val:
                    _aspirar_productos(val["data"], items_crudos)

        if not items_crudos:
            print(f"   ⚠️  [Fase 2] Cache Apollo vacío, intentando recursivo...")
            _aspirar_productos(state, items_crudos)

        print(f"   🔍 [Fase 2] Items en __STATE__: {len(items_crudos)}")
        return self._normalizar_items(items_crudos, max_resultados, "apollo_state")

    # ------------------------------------------------------------------
    # Fase 3 — DOM Scraping
    # ------------------------------------------------------------------
    async def _fase_dom(self, page: Page, max_resultados: int) -> List[ProductoProveedorCreate]:
        await self._scroll_lazy_load(page)

        for sel in _VTEX_SELECTORS:
            try:
                elems = await page.query_selector_all(sel)
                if not elems:
                    continue
                print(f"   🔍 [Fase 3] Selector '{sel}' → {len(elems)} elementos")
                items_dom = await self._extraer_dom_js(page)
                if items_dom:
                    return self._normalizar_dom(items_dom, max_resultados)
            except Exception as exc:
                print(f"   ⚠️  [Fase 3] Selector '{sel}' falló: {exc}")

        # Último recurso: JS agresivo
        print(f"   🔵 [Fase 3] JS agresivo...")
        return await self._js_agresivo(page, max_resultados)

    async def _scroll_lazy_load(self, page: Page) -> None:
        print(f"   🔵 [Fase 3] Scroll para lazy loading...")
        altura: int = await page.evaluate("document.body.scrollHeight")
        pos, paso, iters = 0, 700, 0
        while pos < altura and iters < 20:
            pos = min(pos + paso, altura)
            await page.evaluate(f"window.scrollTo(0, {pos})")
            await asyncio.sleep(random.uniform(0.4, 0.9))
            nueva: int = await page.evaluate("document.body.scrollHeight")
            if nueva > altura:
                print(f"   📏 Página creció: {altura:,} → {nueva:,}px")
                altura = nueva
            iters += 1
        await asyncio.sleep(0.8)
        print(f"   ✅ Scroll completado ({iters} pasos).")

    async def _extraer_dom_js(self, page: Page) -> list:
        return await page.evaluate(
            """
            () => {
                const items = [];
                const SELS = [
                    '[class*="vtex-product-summary-2-x-container"]',
                    '[class*="productSummary"]',
                    '[class*="galleryItem"] section',
                    '[data-product-id]',
                    'section[class*="product"]',
                    'article[class*="product"]',
                    '.shelf-item',
                ];
                let cards = [];
                for (const s of SELS) {
                    const found = document.querySelectorAll(s);
                    if (found.length > 0) { cards = Array.from(found); break; }
                }
                if (!cards.length) return items;
                for (const card of cards) {
                    const nameEl  = card.querySelector(
                        '[class*="productName"],[class*="nameComplete"],' +
                        '[class*="productTitle"],h2,h3,h4');
                    const priceEl = card.querySelector(
                        '[class*="sellingPrice"]:not([class*="list"]),' +
                        '[class*="spotPrice"],[class*="price_sellingPrice"]')
                        || card.querySelector('[class*="price"],[class*="Price"]');
                    const imgEl   = card.querySelector('img[src],img[data-src]');
                    const linkEl  = card.tagName === 'A' ? card : card.querySelector('a[href]');
                    if (!nameEl || !priceEl) continue;
                    const rawPrice = priceEl.innerText || priceEl.textContent || '';
                    if (!rawPrice.match(/\\d/)) continue;
                    items.push({
                        name:  (nameEl.innerText || '').trim(),
                        price: rawPrice.trim(),
                        link:  linkEl ? (linkEl.href || '') : '',
                        image: imgEl  ? (imgEl.src || imgEl.dataset.src || '') : '',
                        sku:   card.dataset.productId || card.dataset.sku || card.id || '',
                    });
                }
                return items;
            }
            """
        )

    async def _js_agresivo(self, page: Page, max_resultados: int) -> List[ProductoProveedorCreate]:
        items_raw: list = await page.evaluate(
            """
            () => {
                const items = [];
                const priceEls = document.querySelectorAll(
                    '[class*="price"],[class*="Price"],[class*="valor"],[class*="monto"]'
                );
                for (const pEl of priceEls) {
                    const txt = pEl.innerText || '';
                    if (!txt.match(/\\$[\\s\\d.,]+/)) continue;
                    let container = pEl.parentElement;
                    let nombre = '';
                    for (let i = 0; i < 5; i++) {
                        if (!container) break;
                        const h = container.querySelector('h1,h2,h3,h4,[class*="name"],[class*="Name"]');
                        if (h) { nombre = (h.innerText || '').trim(); break; }
                        container = container.parentElement;
                    }
                    if (!nombre || nombre.length < 4) continue;
                    const linkEl = container ? container.querySelector('a[href]') : null;
                    const imgEl  = container ? container.querySelector('img') : null;
                    items.push({
                        name:  nombre,
                        price: txt.trim(),
                        link:  linkEl ? (linkEl.href || '') : window.location.href,
                        image: imgEl  ? (imgEl.src || '') : '',
                        sku:   '',
                    });
                }
                return items;
            }
            """
        )
        print(f"   🔍 [Fase 3-JS] JS agresivo → {len(items_raw)} candidatos")
        return self._normalizar_dom(items_raw, max_resultados)

    # ------------------------------------------------------------------
    # Normalización VTEX JSON → ProductoProveedorCreate
    # ------------------------------------------------------------------
    def _normalizar_items(
        self, items: list, max_resultados: int, fuente: str
    ) -> List[ProductoProveedorCreate]:
        productos: List[ProductoProveedorCreate] = []
        vistos: set = set()

        for item in items:
            if len(productos) >= max_resultados:
                break
            if not isinstance(item, dict):
                continue

            nombre = str(
                item.get("productName") or item.get("name") or
                item.get("Name") or item.get("title") or ""
            ).strip()
            if not nombre or len(nombre) < 3:
                continue

            sku = str(
                item.get("productId") or item.get("skuId") or
                item.get("id") or item.get("sku") or ""
            ).strip()
            if not sku:
                sku = f"EASY-{abs(hash(nombre)) % 999_999:06d}"
            if sku in vistos:
                continue

            precio = self._extraer_precio_vtex(item) or _encontrar_precio(item)
            if not precio or precio < 1:
                continue

            link = str(item.get("link") or item.get("linkText") or item.get("slug") or "")
            if link and not link.startswith("http"):
                suffix = "/p" if not link.endswith("/p") else ""
                link = f"{_EASY_BASE}/{link.lstrip('/')}{suffix}"
            if not link:
                link = _EASY_BASE

            img = _encontrar_imagen(item) or ""
            marca = str(item.get("brand") or item.get("brandName") or item.get("Brand") or "") or None

            try:
                productos.append(
                    ProductoProveedorCreate(
                        proveedor=self.proveedor,
                        sku_proveedor=sku[:120],
                        url_producto=link,
                        nombre_raw=nombre[:400],
                        marca=marca,
                        precio_clp=float(precio),
                        imagen_url=img or None,
                        disponible=True,
                    )
                )
                vistos.add(sku)
            except Exception as exc:
                print(f"   ⚠️  [Normalizar] {exc}")

        return productos

    def _normalizar_dom(self, items: list, max_resultados: int) -> List[ProductoProveedorCreate]:
        """Normaliza items que vienen del DOM (formato name/price/link/image/sku)."""
        productos: List[ProductoProveedorCreate] = []
        vistos: set = set()

        for item in items[:max_resultados]:
            precio_clp = _limpiar_precio(item.get("price"))
            if not precio_clp or precio_clp < 1:
                continue
            nombre = str(item.get("name") or "").strip()
            if not nombre or len(nombre) < 3:
                continue
            url = str(item.get("link") or "")
            if url and not url.startswith("http"):
                url = _EASY_BASE + url
            if not url:
                url = _EASY_BASE
            sku = str(item.get("sku") or "").strip()
            if not sku:
                sku = f"EASY-{abs(hash(nombre + url)) % 999_999:06d}"
            if sku in vistos:
                continue
            try:
                productos.append(
                    ProductoProveedorCreate(
                        proveedor=self.proveedor,
                        sku_proveedor=sku[:120],
                        url_producto=url,
                        nombre_raw=nombre[:400],
                        marca=None,
                        precio_clp=precio_clp,
                        imagen_url=item.get("image") or None,
                        disponible=True,
                    )
                )
                vistos.add(sku)
            except Exception as exc:
                print(f"   ⚠️  [Normalizar DOM] {exc}")

        return productos

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------
    def _extraer_precio_vtex(self, item: dict) -> Optional[float]:
        """
        Sigue la jerarquía VTEX: items → sellers → commertialOffer → Price.
        Nota: 'commertialOffer' (con 'e') es el typo histórico de VTEX.
        """
        for items_key in ("items", "Items"):
            skus = item.get(items_key, [])
            if not (isinstance(skus, list) and skus):
                continue
            for seller_key in ("sellers", "Sellers"):
                sellers = skus[0].get(seller_key, [])
                if not (isinstance(sellers, list) and sellers):
                    continue
                offer = sellers[0].get(
                    "commertialOffer",
                    sellers[0].get("CommercialOffer", {}),
                )
                for key in _PRICE_KEYS:
                    val = offer.get(key)
                    if val and float(val) > 0:
                        return float(val)

        # priceRange (VTEX IO GraphQL moderno)
        pr = item.get("priceRange") or {}
        sp = pr.get("sellingPrice") or {}
        low = sp.get("lowPrice") or sp.get("high") or 0
        if low:
            return float(low)

        for key in _PRICE_KEYS:
            val = item.get(key)
            if val and isinstance(val, (int, float)) and float(val) > 0:
                return float(val)

        return None

    def _resultado_ok(
        self, productos: List[ProductoProveedorCreate], inicio: float, metodo: str
    ) -> ResultadoScraper:
        return ResultadoScraper(
            self.proveedor,
            EstadoScraping.EXITO,
            productos,
            duracion_seg=self._duracion(inicio),
            metodo=metodo,
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