"""
Motor de Web Scraping Asíncrono — Sodimac y Easy Chile.
Versión 2.0 — Estrategia dual: httpx JSON API + Camoufox fallback.

CAMBIOS RESPECTO A v1:
    - Playwright Chromium reemplazado por Camoufox (Firefox anti-detect)
    - Estrategia primaria: httpx directo a la API JSON interna del sitio
    - Camoufox solo se activa si la API JSON falla (fallback)
    - Cloudflare detecta Chromium por TLS fingerprint — Firefox es mucho
      menos detectado porque tiene un JA3 fingerprint diferente y más común
    - puppeteer-extra-stealth deprecado en feb 2025, no usar

INSTALACIÓN (una sola vez):
    pip install camoufox[geoip]
    python -m camoufox fetch

FLUJO POR PROVEEDOR:
    1. httpx → API JSON interna del sitio (rápido, sin browser)
    2. Si falla → Camoufox Firefox (lento pero más invisible)
    3. Si falla → Estado BLOQUEADO, logs detallados
"""

import asyncio
import json
import logging
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import httpx
import subprocess

from .models import EstadoScraping, NombreProveedor
from .schemas import ProductoProveedorCreate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Camoufox — import condicional (puede no estar instalado en dev)
# ---------------------------------------------------------------------------
try:
    from camoufox.async_api import AsyncCamoufox
    CAMOUFOX_DISPONIBLE = True
except ImportError:
    CAMOUFOX_DISPONIBLE = False
    logger.warning(
        "Camoufox no instalado. Fallback a browser desactivado. "
        "Instalar con: pip install camoufox[geoip] && python -m camoufox fetch"
    )

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TIMEOUT_API_SEG    = 15     # Timeout para llamadas httpx a la API JSON
TIMEOUT_BROWSER_MS = 28_000 # Timeout para Camoufox (ms)
DELAY_MIN          = 1.5
DELAY_MAX          = 4.0

# Headers que imitan Chrome en Windows — usados en llamadas httpx
HEADERS_BASE = {
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "es-CL,es;q=0.9,en-US;q=0.8",
    "Accept-Encoding":  "gzip, deflate, br",
    "DNT":              "1",
    "Connection":       "keep-alive",
    "Sec-Fetch-Dest":   "empty",
    "Sec-Fetch-Mode":   "cors",
    "Sec-Fetch-Site":   "same-origin",
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------

@dataclass
class ResultadoScraper:
    proveedor:     NombreProveedor
    estado:        EstadoScraping
    productos:     list[ProductoProveedorCreate] = field(default_factory=list)
    error_msg:     Optional[str] = None
    duracion_seg:  float = 0.0
    metodo:        str = "sin_datos"  # "api_json" | "browser" | "error"
    timestamp:     datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------
def _verificar_camoufox() -> bool:
    """
    Verifica si el binario de Camoufox existe.
    Si no existe, intenta descargarlo automáticamente.
    Devuelve True si está disponible después del intento.
    """
    if not CAMOUFOX_DISPONIBLE:
        return False
    try:
        from camoufox import get_executable
        import os
        exe = get_executable()
        if os.path.exists(exe):
            return True
        # Binario no existe → intentar descarga automática
        logger.warning("Camoufox: binario no encontrado en %s — descargando...", exe)
        resultado = subprocess.run(
            [sys.executable, "-m", "camoufox", "fetch"],
            capture_output=True, text=True, timeout=120,
        )
        if resultado.returncode == 0:
            logger.info("Camoufox descargado correctamente.")
            return True
        logger.error("Error descargando Camoufox: %s", resultado.stderr[:300])
        return False
    except Exception as exc:
        logger.error("Error verificando Camoufox: %s", exc)
        return False
    
_CAMOUFOX_LISTO = _verificar_camoufox()

def _ua_aleatorio() -> str:
    return random.choice(USER_AGENTS)


def _limpiar_precio(texto: str) -> Optional[float]:
    """
    Extrae valor numérico de strings de precio chileno.
    Soporta: '$12.990', '12990', '$12.990,00', '12990.0'
    """
    if not texto:
        return None
    limpio = re.sub(r"[^\d.,]", "", str(texto).strip())
    limpio = limpio.replace(".", "").replace(",", ".")
    try:
        v = float(limpio)
        return v if v > 0 else None
    except ValueError:
        return None


def _es_bloqueado(texto: str) -> bool:
    señales = [
        "access denied", "cloudflare", "robot", "captcha",
        "bloqueado", "forbidden", "503 service", "429 too many",
        "cf-browser-verification", "just a moment", "checking your browser",
        "enable javascript", "ddos protection",
    ]
    t = texto.lower()
    return any(s in t for s in señales)


async def _delay_humano() -> None:
    await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


# ---------------------------------------------------------------------------
# Capa 1: Scraper por API JSON (sin browser)
# ---------------------------------------------------------------------------

class _ApiJsonScraper:
    """
    Intenta obtener datos directamente de la API JSON interna del sitio.
    Estos endpoints son usados por el frontend del sitio y suelen tener
    menos protección que la página HTML (Cloudflare no los inspecciona tan
    agresivamente porque son llamadas XHR, no navegación directa).
    """

    async def get(
        self,
        url:     str,
        params:  dict,
        referer: str,
    ) -> Optional[dict | list]:
        headers = {
            **HEADERS_BASE,
            "User-Agent": _ua_aleatorio(),
            "Referer":    referer,
        }
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_API_SEG,
                follow_redirects=True,
                headers=headers,
            ) as client:
                resp = await client.get(url, params=params)

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code in (403, 429, 503):
                logger.warning(
                    "API JSON bloqueada [%d] → %s", resp.status_code, url
                )
                return None
            else:
                logger.debug("API JSON status %d → %s", resp.status_code, url)
                return None

        except (httpx.TimeoutException, httpx.RequestError) as exc:
            logger.debug("Error httpx en %s: %s", url, exc)
            return None
        except Exception as exc:
            logger.debug("Error inesperado API JSON %s: %s", url, exc)
            return None


# ---------------------------------------------------------------------------
# Scraper Sodimac Chile
# ---------------------------------------------------------------------------

class SodimacScraper:
    """
    Sodimac Chile — sodimac.cl

    Estrategia 1 — API JSON interna (ATG Oracle Commerce):
        Sodimac usa Oracle ATG. Su endpoint de búsqueda acepta ?format=json
        devolviendo un JSON estructurado con productos, precios y URLs.
        Este endpoint tiene menos protección de Cloudflare porque el
        frontend lo llama como XHR.

    Estrategia 2 — Camoufox (Firefox anti-detect):
        Si el JSON falla (Cloudflare bloquea también el XHR), se usa
        Camoufox con Firefox. Firefox tiene un JA3 TLS fingerprint
        completamente diferente a Chromium — mucho menos detectado.

    Selectores CSS (actualizar si el DOM cambia):
        Los selectores están en _SELECTORES_CSS como constante de clase
        para facilitar mantenimiento. Si Sodimac cambia su frontend,
        solo hay que actualizar esta constante.
    """

    proveedor = NombreProveedor.SODIMAC

    # URL base de búsqueda
    _BASE_URL      = "https://www.sodimac.cl/sodimac-cl/search"
    # Parámetros ATG para obtener JSON
    _PARAMS_JSON   = {"format": "json", "No": "0", "Nrpp": "24"}

    # Selectores CSS en orden de preferencia — el primero que funcione gana
    _SELECTORES_CSS = [
        "[data-pod]",
        ".pod-plp",
        "[data-testid='product-card']",
        ".product-item",
        "[class*='ProductCard']",
    ]

    def __init__(self) -> None:
        self._api = _ApiJsonScraper()

    async def buscar(
        self,
        query:          str,
        max_resultados: int,
    ) -> ResultadoScraper:
        inicio = asyncio.get_event_loop().time()

        # --- Estrategia 1: API JSON ---
        productos = await self._intentar_api_json(query, max_resultados)
        if productos is not None:
            return ResultadoScraper(
                proveedor   =self.proveedor,
                estado      =EstadoScraping.EXITO,
                productos   =productos,
                duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
                metodo      ="api_json",
            )

        # --- Estrategia 2: Camoufox ---
        if _CAMOUFOX_LISTO:
            logger.info("[Sodimac] API JSON falló → intentando con Camoufox")
            productos = await self._intentar_camoufox(query, max_resultados)
            if productos is not None:
                return ResultadoScraper(
                    proveedor   =self.proveedor,
                    estado      =EstadoScraping.EXITO,
                    productos   =productos,
                    duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
                    metodo      ="browser",
                )

        return ResultadoScraper(
            proveedor   =self.proveedor,
            estado      =EstadoScraping.BLOQUEADO,
            error_msg   ="Cloudflare bloqueó ambas estrategias (API JSON + Camoufox).",
            duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
            metodo      ="error",
        )

    async def _intentar_api_json(
        self, query: str, max_resultados: int
    ) -> Optional[list[ProductoProveedorCreate]]:
        """
        Llama al endpoint ATG de Sodimac que devuelve JSON.
        Si funciona es mucho más rápido y limpio que el browser.
        """
        params = {
            **self._PARAMS_JSON,
            "Ntt":  query,
            "Nrpp": str(max_resultados),
        }

        data = await self._api.get(
            url     =self._BASE_URL,
            params  =params,
            referer ="https://www.sodimac.cl/",
        )

        if not data:
            return None

        # ATG devuelve los productos en data.resultList.productSummaryList
        try:
            productos_raw = (
                data.get("resultList", {})
                    .get("productSummaryList", [])
            )
        except AttributeError:
            logger.debug("[Sodimac] Estructura JSON inesperada: %s", str(data)[:200])
            return None

        if not productos_raw:
            # El JSON vino pero vacío — puede ser un bloqueo soft de Cloudflare
            logger.debug("[Sodimac] JSON recibido pero sin productos")
            return None

        return self._normalizar_atg(productos_raw, max_resultados)

    def _normalizar_atg(
        self, items: list, max_resultados: int
    ) -> list[ProductoProveedorCreate]:
        """Convierte la estructura ATG de Sodimac al schema interno."""
        from pydantic import ValidationError

        productos = []
        for item in items[:max_resultados]:
            precio_raw = (
                item.get("price")
                or item.get("offerPrice")
                or item.get("listPrice")
                or item.get("prices", {}).get("offerPrice")
            )
            precio = _limpiar_precio(str(precio_raw)) if precio_raw else None
            if not precio:
                continue

            url_rel = item.get("url", "")
            url = (
                f"https://www.sodimac.cl{url_rel}"
                if url_rel.startswith("/")
                else url_rel or "https://www.sodimac.cl"
            )

            sku = (
                item.get("productId")
                or item.get("skuId")
                or item.get("id")
                or f"SOD-{hash(url) % 999999:06d}"
            )

            imagen = (
                item.get("defaultImage", {}).get("url")
                or item.get("imageUrl")
                or item.get("image")
            )
            if imagen and not imagen.startswith("http"):
                imagen = f"https://www.sodimac.cl{imagen}"

            try:
                p = ProductoProveedorCreate(
                    proveedor     =NombreProveedor.SODIMAC,
                    sku_proveedor =str(sku)[:120],
                    url_producto  =url,
                    nombre_raw    =(item.get("displayName") or item.get("name") or "Sin nombre")[:400],
                    marca         =item.get("brand") or item.get("brandName") or None,
                    precio_clp    =precio,
                    precio_oferta =_limpiar_precio(str(item.get("offerPrice", ""))) if item.get("offerPrice") else None,
                    unidad        =item.get("unit") or None,
                    imagen_url    =imagen or None,
                    disponible    =True,
                )
                productos.append(p)
            except ValidationError as exc:
                logger.debug("[Sodimac ATG] Producto inválido: %s", exc)

        return productos

    async def _intentar_camoufox(
        self, query: str, max_resultados: int
    ) -> Optional[list[ProductoProveedorCreate]]:
        """
        Usa Camoufox (Firefox anti-detect) si la API JSON falla.
        Firefox tiene un TLS fingerprint completamente diferente a Chromium
        — Cloudflare lo detecta mucho menos agresivamente.
        """
        url = f"{self._BASE_URL}?Ntt={quote_plus(query)}"

        try:
            async with AsyncCamoufox(
                headless  =True,
                geoip     =True,          # Ajusta timezone/locale a la IP
                os        ="windows",     # Fingerprintear como Windows
                locale    ="es-CL",
            ) as browser:
                page = await browser.new_page()

                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout   =TIMEOUT_BROWSER_MS,
                )
                await _delay_humano()

                # Verificar bloqueo
                contenido = await page.content()
                if _es_bloqueado(contenido):
                    logger.warning("[Sodimac Camoufox] WAF detectado")
                    return None

                # Scroll humano para activar lazy loading
                await self._scroll_humano(page)

                # Intentar extraer via JavaScript
                productos_raw = await self._extraer_js(page, max_resultados)
                await page.close()

                if not productos_raw:
                    return None

                return self._normalizar_html(productos_raw)

        except Exception as exc:
            logger.error("[Sodimac Camoufox] Error: %s", exc)
            return None

    async def _scroll_humano(self, page) -> None:
        """Scroll progresivo que activa lazy loading de productos."""
        for _ in range(4):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.7)")
            await asyncio.sleep(random.uniform(0.4, 0.9))

    async def _extraer_js(self, page, max_resultados: int) -> list[dict]:
        """
        Extrae productos via JavaScript corriendo en el contexto del browser.
        Usa múltiples selectores en cascada — si uno falla, prueba el siguiente.
        """
        selector_lista = ", ".join(self._SELECTORES_CSS)

        script = f"""
        (() => {{
            const items = [];
            const pods = document.querySelectorAll('{selector_lista}');
            const max = {max_resultados};

            for (let i = 0; i < Math.min(pods.length, max); i++) {{
                const p = pods[i];

                const nombre = (
                    p.querySelector('[data-testid="pod-name"], .pod-title, h2, h3, [class*="name"], [class*="title"]')
                    ?.innerText?.trim() || ''
                );

                // Buscar precio NO tachado (sin crossed/original/old en la clase)
                const precioEl = p.querySelector(
                    '[data-testid="price-text"], .pod-price, [class*="price"]:not([class*="crossed"]):not([class*="original"]):not([class*="old"])'
                );
                const precio = precioEl?.innerText?.trim() || '';

                const link = p.querySelector('a[href]');
                const img  = p.querySelector('img[src], img[data-src]');
                const marca = p.querySelector('[class*="brand"], [data-testid="pod-brand"]')?.innerText?.trim() || '';

                const sku = p.getAttribute('data-product-id')
                    || p.getAttribute('data-id')
                    || p.getAttribute('data-sku')
                    || '';

                if (nombre && precio) {{
                    items.push({{
                        nombre, precio, sku,
                        url:    link?.href || '',
                        imagen: img?.src || img?.dataset?.src || '',
                        marca,
                    }});
                }}
            }}
            return items;
        }})()
        """
        try:
            return await page.evaluate(script) or []
        except Exception as exc:
            logger.debug("[Sodimac JS] Error en extracción: %s", exc)
            return []

    def _normalizar_html(
        self, items: list[dict]
    ) -> list[ProductoProveedorCreate]:
        from pydantic import ValidationError

        productos = []
        for item in items:
            precio = _limpiar_precio(item.get("precio", ""))
            if not precio:
                continue

            url = item.get("url", "")
            if not url.startswith("http"):
                url = "https://www.sodimac.cl" + url

            sku = item.get("sku") or f"SOD-{hash(url) % 999999:06d}"

            try:
                p = ProductoProveedorCreate(
                    proveedor    =NombreProveedor.SODIMAC,
                    sku_proveedor=sku[:120],
                    url_producto =url,
                    nombre_raw   =item.get("nombre", "Sin nombre")[:400],
                    marca        =item.get("marca") or None,
                    precio_clp   =precio,
                    imagen_url   =item.get("imagen") or None,
                    disponible   =True,
                )
                productos.append(p)
            except ValidationError as exc:
                logger.debug("[Sodimac HTML] Inválido: %s", exc)

        return productos


# ---------------------------------------------------------------------------
# Scraper Easy Chile
# ---------------------------------------------------------------------------

class EasyScraper:
    """
    Easy Chile — easy.cl

    Easy cambió su plataforma. Probamos 4 endpoints en orden:
      1. API de búsqueda VTEX v2 (más común en tiendas VTEX Chile 2024)
      2. API search GraphQL de VTEX Intelligent Search
      3. API catálogo VTEX clásica (la que teníamos antes)
      4. Camoufox como último recurso

    Si easy.cl no está en VTEX, el endpoint correcto puede variar.
    Los logs muestran qué estrategia funcionó para ajustar en el futuro.
    """

    proveedor = NombreProveedor.EASY

    # Endpoints a probar en orden — el primero que devuelva datos gana
    _ENDPOINTS = [
        # VTEX Intelligent Search API (2023+)
        {
            "url":    "https://www.easy.cl/_v/api/search-graphql/v0",
            "metodo": "graphql",
        },
        # VTEX Search REST v2
        {
            "url":    "https://www.easy.cl/search",
            "metodo": "vtex_rest_v2",
        },
        # VTEX Catalog clásico
        {
            "url":    "https://www.easy.cl/api/catalog_system/pub/products/search",
            "metodo": "vtex_catalog",
        },
    ]

    _SELECTORES_CSS = [
        "[class*='ProductCard']",
        "[class*='product-card']",
        ".product-item",
        ".shelf-item",
        "[data-testid='product']",
        "[class*='vtex-product-summary']",
        "[class*='productContainer']",
    ]

    def __init__(self) -> None:
        self._api = _ApiJsonScraper()

    async def buscar(
        self,
        query:          str,
        max_resultados: int,
    ) -> ResultadoScraper:
        inicio = asyncio.get_event_loop().time()

        # --- Probar todos los endpoints JSON ---
        for endpoint in self._ENDPOINTS:
            logger.debug("[Easy] Probando endpoint: %s", endpoint["metodo"])
            productos = await self._probar_endpoint(
                endpoint, query, max_resultados
            )
            if productos is not None and len(productos) > 0:
                logger.info(
                    "[Easy] Éxito con endpoint '%s' — %d productos",
                    endpoint["metodo"], len(productos),
                )
                return ResultadoScraper(
                    proveedor   =self.proveedor,
                    estado      =EstadoScraping.EXITO,
                    productos   =productos,
                    duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
                    metodo      =f"api_{endpoint['metodo']}",
                )

        # --- Camoufox como último recurso ---
        if _CAMOUFOX_LISTO:
            logger.info("[Easy] Todos los endpoints JSON fallaron → Camoufox")
            productos = await self._intentar_camoufox(query, max_resultados)
            if productos is not None and len(productos) > 0:
                return ResultadoScraper(
                    proveedor   =self.proveedor,
                    estado      =EstadoScraping.EXITO,
                    productos   =productos,
                    duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
                    metodo      ="browser_camoufox",
                )

        dur = round(asyncio.get_event_loop().time() - inicio, 2)
        logger.warning("[Easy] Bloqueado en todas las estrategias (%.1fs)", dur)
        return ResultadoScraper(
            proveedor   =self.proveedor,
            estado      =EstadoScraping.BLOQUEADO,
            error_msg   ="Todos los endpoints fallaron. Revisar logs para detalles.",
            duracion_seg=dur,
            metodo      ="error",
        )

    async def _probar_endpoint(
        self,
        endpoint:       dict,
        query:          str,
        max_resultados: int,
    ) -> Optional[list[ProductoProveedorCreate]]:
        """Despacha al método correcto según el tipo de endpoint."""
        metodo = endpoint["metodo"]
        url    = endpoint["url"]

        try:
            if metodo == "graphql":
                return await self._buscar_graphql(url, query, max_resultados)
            elif metodo == "vtex_rest_v2":
                return await self._buscar_vtex_v2(url, query, max_resultados)
            elif metodo == "vtex_catalog":
                return await self._buscar_vtex_catalog(url, query, max_resultados)
        except Exception as exc:
            logger.debug("[Easy %s] Error: %s", metodo, exc)
        return None

    async def _buscar_graphql(
        self, url: str, query: str, max_resultados: int
    ) -> Optional[list[ProductoProveedorCreate]]:
        """
        VTEX Intelligent Search — GraphQL POST.
        Esta es la API moderna que usan las tiendas VTEX IO 2022+.
        """
        payload = {
            "query": """
              query search($query: String, $from: Int, $to: Int) {
                productSearch(query: $query, from: $from, to: $to) {
                  products {
                    productId productName brand linkText
                    items {
                      images { imageUrl }
                      sellers { commertialOffer { Price ListPrice } }
                    }
                  }
                }
              }
            """,
            "variables": {
                "query": query,
                "from":  0,
                "to":    max_resultados - 1,
            },
        }
        headers = {
            **HEADERS_BASE,
            "User-Agent":   _ua_aleatorio(),
            "Content-Type": "application/json",
            "Referer":      f"https://www.easy.cl/search?q={quote_plus(query)}",
        }
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_API_SEG,
                follow_redirects=True,
                headers=headers,
            ) as client:
                resp = await client.post(url, json=payload)

            if resp.status_code != 200:
                logger.debug("[Easy GraphQL] Status %d", resp.status_code)
                return None

            data     = resp.json()
            products = (
                data.get("data", {})
                    .get("productSearch", {})
                    .get("products", [])
            )
            if not products:
                return None

            return self._normalizar_vtex(products, max_resultados)

        except Exception as exc:
            logger.debug("[Easy GraphQL] Error: %s", exc)
            return None

    async def _buscar_vtex_v2(
        self, url: str, query: str, max_resultados: int
    ) -> Optional[list[ProductoProveedorCreate]]:
        """
        Endpoint REST de VTEX con parámetros de búsqueda modernos.
        Algunas tiendas VTEX exponen el HTML con data-json embebido.
        """
        params  = {"q": query, "_from": "0", "_to": str(max_resultados - 1)}
        headers = {
            **HEADERS_BASE,
            "User-Agent": _ua_aleatorio(),
            "Accept":     "application/json",
            "Referer":    "https://www.easy.cl/",
        }
        try:
            async with httpx.AsyncClient(
                timeout=TIMEOUT_API_SEG,
                follow_redirects=True,
                headers=headers,
            ) as client:
                resp = await client.get(url, params=params)

            if resp.status_code != 200:
                logger.debug("[Easy REST v2] Status %d", resp.status_code)
                return None

            # Intentar JSON directo
            try:
                data = resp.json()
                if isinstance(data, list) and data:
                    return self._normalizar_vtex(data, max_resultados)
            except Exception:
                pass

            # Si no es JSON, buscar datos embebidos en el HTML
            return self._extraer_json_embebido(resp.text, max_resultados)

        except Exception as exc:
            logger.debug("[Easy REST v2] Error: %s", exc)
            return None

    async def _buscar_vtex_catalog(
        self, url: str, query: str, max_resultados: int
    ) -> Optional[list[ProductoProveedorCreate]]:
        """VTEX Catalog API clásica."""
        params = {
            "ft":    query,
            "_from": "0",
            "_to":   str(max_resultados - 1),
        }
        data = await self._api.get(
            url     =url,
            params  =params,
            referer =f"https://www.easy.cl/search?q={quote_plus(query)}",
        )
        if not data or not isinstance(data, list):
            return None
        return self._normalizar_vtex(data, max_resultados)

    def _extraer_json_embebido(
        self, html: str, max_resultados: int
    ) -> Optional[list[ProductoProveedorCreate]]:
        """
        Algunas SPAs embeben el estado inicial como JSON en el HTML.
        Busca patrones comunes: __STATE__, __NEXT_DATA__, __PRELOADED_STATE__
        """
        patrones = [
            r'__STATE__\s*=\s*(\{.+?\});',
            r'__NEXT_DATA__\s*=\s*(\{.+?\})\s*</script>',
            r'"products"\s*:\s*(\[.+?\])',
        ]
        for patron in patrones:
            match = re.search(patron, html, re.DOTALL)
            if not match:
                continue
            try:
                data = json.loads(match.group(1))
                # Navegar el árbol buscando listas de productos
                productos = self._buscar_productos_en_arbol(data)
                if productos:
                    return self._normalizar_vtex(productos, max_resultados)
            except (json.JSONDecodeError, Exception):
                continue
        return None

    def _buscar_productos_en_arbol(self, data, profundidad: int = 0) -> list:
        """Busca recursivamente listas que parezcan productos."""
        if profundidad > 5:
            return []
        if isinstance(data, list) and data and isinstance(data[0], dict):
            # Verificar si parece una lista de productos
            primer = data[0]
            if any(k in primer for k in ["productId", "productName", "Price", "name"]):
                return data
        if isinstance(data, dict):
            for key in ["products", "items", "productSearch", "data"]:
                if key in data:
                    resultado = self._buscar_productos_en_arbol(
                        data[key], profundidad + 1
                    )
                    if resultado:
                        return resultado
        return []

    def _normalizar_vtex(
        self, items: list, max_resultados: int
    ) -> list[ProductoProveedorCreate]:
        from pydantic import ValidationError

        productos = []
        for item in items[:max_resultados]:
            try:
                precio        = None
                precio_oferta = None

                skus = item.get("items", [])
                if skus:
                    sellers = skus[0].get("sellers", [])
                    if sellers:
                        oferta       = sellers[0].get("commertialOffer", {})
                        precio       = oferta.get("ListPrice") or oferta.get("Price")
                        precio_sale  = oferta.get("Price")
                        if precio_sale and precio and precio_sale < precio:
                            precio_oferta = precio_sale

                # Fallback: precio en raíz del objeto
                if not precio:
                    precio = (
                        item.get("price")
                        or item.get("Price")
                        or item.get("offerPrice")
                        or item.get("listPrice")
                    )

                if not precio:
                    continue

                url = (
                    item.get("link")
                    or item.get("url")
                    or f"https://www.easy.cl/{item.get('linkText', '')}"
                )
                if not url.startswith("http"):
                    url = "https://www.easy.cl" + url

                imagen = None
                if skus and skus[0].get("images"):
                    imagen = skus[0]["images"][0].get("imageUrl")
                imagen = imagen or item.get("imageUrl") or item.get("image")

                sku = (
                    str(item.get("productId", ""))
                    or str(item.get("id", ""))
                    or f"EASY-{hash(url) % 999999:06d}"
                )

                p = ProductoProveedorCreate(
                    proveedor    =NombreProveedor.EASY,
                    sku_proveedor=sku[:120],
                    url_producto =url,
                    nombre_raw   =(
                        item.get("productName")
                        or item.get("name")
                        or "Sin nombre"
                    )[:400],
                    marca        =item.get("brand") or None,
                    precio_clp   =float(precio),
                    precio_oferta=float(precio_oferta) if precio_oferta else None,
                    imagen_url   =imagen or None,
                    disponible   =True,
                )
                productos.append(p)

            except (ValidationError, KeyError, TypeError, ValueError) as exc:
                logger.debug("[Easy normalizar] Producto inválido: %s", exc)

        return productos

    async def _intentar_camoufox(
        self, query: str, max_resultados: int
    ) -> Optional[list[ProductoProveedorCreate]]:
        url = f"https://www.easy.cl/search?q={quote_plus(query)}"
        try:
            async with AsyncCamoufox(
                headless=True,
                geoip   =True,
                os      ="windows",
                locale  ="es-CL",
            ) as browser:
                page = await browser.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_BROWSER_MS)
                await asyncio.sleep(3)
                await _delay_humano()

                contenido = await page.content()
                if _es_bloqueado(contenido):
                    logger.warning("[Easy Camoufox] WAF detectado")
                    return None

                for _ in range(3):
                    await page.evaluate("window.scrollBy(0, window.innerHeight * 0.6)")
                    await asyncio.sleep(random.uniform(0.5, 1.1))

                productos_raw = await self._extraer_js(page, max_resultados)
                await page.close()
                return self._normalizar_html(productos_raw) if productos_raw else None

        except Exception as exc:
            logger.error("[Easy Camoufox] Error: %s", exc)
            return None

    async def _extraer_js(self, page, max_resultados: int) -> list[dict]:
        selector_lista = ", ".join(self._SELECTORES_CSS)
        script = f"""
        (() => {{
            const items = [];
            const cards = document.querySelectorAll('{selector_lista}');
            for (let i = 0; i < Math.min(cards.length, {max_resultados}); i++) {{
                const c = cards[i];
                const nombre  = c.querySelector('[class*="productName"],[class*="product-name"],[class*="title"],h2,h3,h4')?.innerText?.trim() || '';
                const precioEl = c.querySelector('[class*="sellingPrice"],[class*="price"]:not([class*="original"]):not([class*="old"]),[class*="Price"]:not([class*="Original"])');
                const precio   = precioEl?.innerText?.trim() || '';
                const link     = c.querySelector('a[href]');
                const img      = c.querySelector('img');
                const marca    = c.querySelector('[class*="brand"],[class*="Brand"]')?.innerText?.trim() || '';
                const sku      = c.getAttribute('data-product-id') || c.getAttribute('data-sku') || '';
                if (nombre && precio) items.push({{ nombre, precio, sku, url: link?.href||'', imagen: img?.src||img?.dataset?.src||'', marca }});
            }}
            return items;
        }})()
        """
        try:
            return await page.evaluate(script) or []
        except Exception:
            return []

    def _normalizar_html(self, items: list[dict]) -> list[ProductoProveedorCreate]:
        from pydantic import ValidationError
        productos = []
        for item in items:
            precio = _limpiar_precio(item.get("precio", ""))
            if not precio:
                continue
            url = item.get("url", "")
            if not url.startswith("http"):
                url = "https://www.easy.cl" + url
            try:
                productos.append(ProductoProveedorCreate(
                    proveedor    =NombreProveedor.EASY,
                    sku_proveedor=(item.get("sku") or f"EASY-{hash(url) % 999999:06d}")[:120],
                    url_producto =url,
                    nombre_raw   =item.get("nombre", "Sin nombre")[:400],
                    marca        =item.get("marca") or None,
                    precio_clp   =precio,
                    imagen_url   =item.get("imagen") or None,
                    disponible   =True,
                ))
            except ValidationError:
                pass
        return productos


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

class ScraperOrchestrator:
    """
    Lanza los scrapers en paralelo con asyncio.gather.
    Si uno falla, devuelve los resultados del resto.
    """

    _SCRAPERS = {
        NombreProveedor.SODIMAC: SodimacScraper,
        NombreProveedor.EASY:    EasyScraper,
    }

    async def buscar(
        self,
        query:          str,
        proveedores:    list[NombreProveedor],
        max_resultados: int = 10,
    ) -> list[ResultadoScraper]:

        validos = [p for p in proveedores if p in self._SCRAPERS]
        if not validos:
            return []

        tareas = [
            self._SCRAPERS[p]().buscar(query, max_resultados)
            for p in validos
        ]

        resultados_raw = await asyncio.gather(*tareas, return_exceptions=True)

        resultados: list[ResultadoScraper] = []
        for proveedor, resultado in zip(validos, resultados_raw):
            if isinstance(resultado, Exception):
                logger.error("Error no capturado en %s: %s", proveedor, resultado)
                resultados.append(ResultadoScraper(
                    proveedor=proveedor,
                    estado   =EstadoScraping.ERROR,
                    error_msg=str(resultado)[:500],
                ))
            else:
                resultados.append(resultado)
                logger.info(
                    "[%s] estado=%s productos=%d método=%s duración=%.1fs",
                    resultado.proveedor,
                    resultado.estado,
                    len(resultado.productos),
                    resultado.metodo,
                    resultado.duracion_seg,
                )

        return resultados


# ---------------------------------------------------------------------------
# Punto de entrada público
# ---------------------------------------------------------------------------

async def ejecutar_busqueda(
    query:          str,
    proveedores:    list[NombreProveedor],
    max_resultados: int = 10,
) -> list[ResultadoScraper]:
    return await ScraperOrchestrator().buscar(query, proveedores, max_resultados)