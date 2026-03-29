"""
Motor de Web Scraping Asíncrono — Sodimac y Easy Chile.

ADVERTENCIA LEGAL (PoC):
    Este módulo es un prototipo de demostración. En producción se debe
    reemplazar por la API oficial del proveedor o un acuerdo comercial.
    El scraping sin autorización puede violar los ToS del sitio.

Estrategias de evasión implementadas:
    - Rotación de User-Agents reales (Chrome/Firefox/Edge en distintos OS)
    - Headers HTTP realistas con orden correcto (browser fingerprint)
    - Delays aleatorios entre requests (no ritmo de bot)
    - Viewport y deviceScaleFactor aleatorios
    - Desactivar navigator.webdriver (stealth básico)
    - Timeout por scraper individual (no bloquea al otro)

Graceful degradation:
    Si un scraper falla (bloqueo, timeout, DOM cambiado), devuelve
    ResultadoScraper con estado BLOQUEADO o ERROR y datos vacíos.
    El orquestador siempre devuelve algo al cliente.
"""

import asyncio
import json
import logging
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
)

from .models import EstadoScraping, NombreProveedor
from .schemas import ProductoProveedorCreate

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de configuración
# ---------------------------------------------------------------------------

# Timeout total por scraper en milisegundos
SCRAPER_TIMEOUT_MS = 25_000

# Tiempo mínimo y máximo de espera entre acciones (segundos)
DELAY_MIN = 1.8
DELAY_MAX = 4.5

# User-Agents reales recientes — actualizar periódicamente
USER_AGENTS = [
    # Chrome en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome en macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    # Edge en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Safari en macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
]

# ---------------------------------------------------------------------------
# Dataclasses de resultado
# ---------------------------------------------------------------------------

@dataclass
class ResultadoScraper:
    """
    Resultado normalizado de UN scraper (un proveedor).
    Siempre se devuelve aunque haya error — nunca se propaga una excepción.
    """
    proveedor:     NombreProveedor
    estado:        EstadoScraping
    productos:     list[ProductoProveedorCreate] = field(default_factory=list)
    error_msg:     Optional[str] = None
    duracion_seg:  float = 0.0
    timestamp:     datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Helpers de evasión
# ---------------------------------------------------------------------------

def _headers_realistas(user_agent: str) -> dict[str, str]:
    """
    Construye headers HTTP que imitan un navegador real.
    El orden de los headers importa para algunos WAF (fingerprinting).
    """
    return {
        "User-Agent":      user_agent,
        "Accept":          "text/html,application/xhtml+xml,application/xml;"
                           "q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "es-CL,es;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT":             "1",
        "Connection":      "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest":  "document",
        "Sec-Fetch-Mode":  "navigate",
        "Sec-Fetch-Site":  "none",
        "Sec-Fetch-User":  "?1",
        "Cache-Control":   "max-age=0",
    }


async def _delay_humano() -> None:
    """Pausa aleatoria para no parecer bot."""
    await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


async def _crear_contexto_stealth(browser: Browser) -> BrowserContext:
    """
    Crea un contexto de navegador con configuración anti-detección básica.
    No es invulnerable a Cloudflare Enterprise, pero pasa la mayoría de WAFs.
    """
    ua = random.choice(USER_AGENTS)
    viewport_w = random.choice([1280, 1366, 1440, 1920])
    viewport_h = random.choice([768,  800,  900,  1080])

    context = await browser.new_context(
        user_agent=ua,
        viewport={"width": viewport_w, "height": viewport_h},
        locale="es-CL",
        timezone_id="America/Santiago",
        extra_http_headers=_headers_realistas(ua),
        java_script_enabled=True,
        # No descargar imágenes acelera el scraping
        # pero puede activar detección en algunos sitios — ajustar según pruebas
    )

    # Ocultar navigator.webdriver — señal clásica de Playwright/Selenium
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['es-CL', 'es', 'en-US'],
        });
        window.chrome = { runtime: {} };
    """)

    return context


def _limpiar_precio(texto: str) -> Optional[float]:
    """
    Extrae el valor numérico de un string de precio chileno.
    Ejemplos: '$12.990', '12990', '$12.990,00', '$ 1.200'
    """
    if not texto:
        return None
    # Eliminar todo excepto dígitos y puntos/comas
    limpio = re.sub(r"[^\d.,]", "", texto.strip())
    # Formato chileno: punto = separador de miles, coma = decimales
    # Quitar puntos de miles, reemplazar coma decimal por punto
    limpio = limpio.replace(".", "").replace(",", ".")
    try:
        valor = float(limpio)
        return valor if valor > 0 else None
    except ValueError:
        logger.warning("No se pudo parsear precio: '%s'", texto)
        return None


def _es_bloqueado(contenido: str) -> bool:
    """
    Detecta señales comunes de que el sitio bloqueó el bot.
    Lista de señales que pueden cambiar — mantener actualizada.
    """
    señales = [
        "access denied",
        "cloudflare",
        "robot",
        "captcha",
        "bloqueado",
        "forbidden",
        "503 service",
        "429 too many",
    ]
    contenido_lower = contenido.lower()
    return any(s in contenido_lower for s in señales)


# ---------------------------------------------------------------------------
# Scraper base (clase abstracta ligera)
# ---------------------------------------------------------------------------

class _ScraperBase:
    """
    Clase base con lógica común. Cada proveedor hereda y sobreescribe
    `_construir_url_busqueda` y `_extraer_productos`.
    """

    proveedor: NombreProveedor  # Definir en subclase

    async def buscar(
        self,
        query: str,
        max_resultados: int,
        browser: Browser,
    ) -> ResultadoScraper:
        """
        Método público. Maneja todos los errores — nunca propaga excepciones.
        """
        inicio = asyncio.get_event_loop().time()
        context: Optional[BrowserContext] = None

        try:
            context = await _crear_contexto_stealth(browser)
            productos = await asyncio.wait_for(
                self._scrape(query, max_resultados, context),
                timeout=SCRAPER_TIMEOUT_MS / 1000,
            )
            duracion = asyncio.get_event_loop().time() - inicio
            return ResultadoScraper(
                proveedor=self.proveedor,
                estado=EstadoScraping.EXITO,
                productos=productos,
                duracion_seg=round(duracion, 2),
            )

        except asyncio.TimeoutError:
            logger.warning("[%s] Timeout tras %ss", self.proveedor, SCRAPER_TIMEOUT_MS / 1000)
            return ResultadoScraper(
                proveedor=self.proveedor,
                estado=EstadoScraping.BLOQUEADO,
                error_msg="Timeout — posible bloqueo o sitio lento",
                duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
            )

        except Exception as exc:
            logger.error("[%s] Error inesperado: %s", self.proveedor, exc, exc_info=True)
            return ResultadoScraper(
                proveedor=self.proveedor,
                estado=EstadoScraping.ERROR,
                error_msg=str(exc)[:500],  # Truncar para no llenar la BD
                duracion_seg=round(asyncio.get_event_loop().time() - inicio, 2),
            )

        finally:
            if context:
                await context.close()

    async def _scrape(
        self,
        query: str,
        max_resultados: int,
        context: BrowserContext,
    ) -> list[ProductoProveedorCreate]:
        """Implementar en subclase."""
        raise NotImplementedError

    def _construir_url_busqueda(self, query: str) -> str:
        """Implementar en subclase."""
        raise NotImplementedError

    async def _extraer_productos(
        self,
        page: Page,
        max_resultados: int,
    ) -> list[dict]:
        """Implementar en subclase."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Scraper Sodimac Chile
# ---------------------------------------------------------------------------

class SodimacScraper(_ScraperBase):
    """
    Scraper para sodimac.cl.

    NOTAS DE DOM (verificar periódicamente, los sitios cambian):
        - URL de búsqueda: /search?Ntt={query}
        - Contenedor de productos: [data-testid="product-card"] o .pod
        - Los selectores CSS son los puntos más frágiles de este módulo.
          Si dejan de funcionar, revisar el DOM con DevTools.
    """

    proveedor = NombreProveedor.SODIMAC

    def _construir_url_busqueda(self, query: str) -> str:
        from urllib.parse import quote_plus
        return f"https://www.sodimac.cl/sodimac-cl/search?Ntt={quote_plus(query)}"

    async def _scrape(
        self,
        query: str,
        max_resultados: int,
        context: BrowserContext,
    ) -> list[ProductoProveedorCreate]:

        page: Page = await context.new_page()
        url = self._construir_url_busqueda(query)

        logger.info("[Sodimac] Navegando a: %s", url)
        await page.goto(url, wait_until="domcontentloaded", timeout=SCRAPER_TIMEOUT_MS)
        await _delay_humano()

        # Verificar bloqueo antes de parsear
        contenido = await page.content()
        if _es_bloqueado(contenido):
            logger.warning("[Sodimac] WAF detectado")
            raise Exception("WAF/bot-detection activado en Sodimac")

        # Esperar que carguen los productos (puede variar el selector)
        try:
            await page.wait_for_selector(
                "[data-pod='pod-plp'], .pod-plp, [data-testid='product-card']",
                timeout=8_000,
            )
        except PlaywrightTimeout:
            logger.warning("[Sodimac] Selector de productos no encontrado — DOM puede haber cambiado")
            return []

        datos_crudos = await self._extraer_productos(page, max_resultados)
        await page.close()

        return self._normalizar(datos_crudos, query)

    async def _extraer_productos(
        self,
        page: Page,
        max_resultados: int,
    ) -> list[dict]:
        """
        Extrae datos de la página de resultados de Sodimac.
        Usa JavaScript en el contexto del navegador para mayor robustez
        que BeautifulSoup — el JS puede acceder a datos dinámicos.

        IMPORTANTE: Este script puede romperse si Sodimac cambia su DOM.
        Mantener un test de integración que alerte cuando falle.
        """
        script = """
        (maxResultados) => {
            const items = [];
            // Intentar múltiples selectores — el DOM cambia frecuentemente
            const pods = document.querySelectorAll(
                '[data-pod], .pod-plp, [data-testid="product-card"]'
            );

            for (let i = 0; i < Math.min(pods.length, maxResultados); i++) {
                const pod = pods[i];

                // Nombre del producto
                const nombreEl = pod.querySelector(
                    '[data-testid="pod-name"], .pod-title, .product-name, h2, h3'
                );

                // Precio — buscar el precio actual (no el tachado)
                const precioEl = pod.querySelector(
                    '[data-testid="price-text"], .pod-price, .price-box .price, '
                    + '.prices-sale, [class*="price"]:not([class*="crossed"])'
                );

                // SKU / ID interno
                const skuAttr = pod.getAttribute('data-product-id')
                    || pod.getAttribute('data-id')
                    || pod.getAttribute('id')
                    || '';

                // URL del producto
                const linkEl = pod.querySelector('a[href]');

                // Imagen
                const imgEl = pod.querySelector('img[src], img[data-src]');

                // Marca
                const marcaEl = pod.querySelector(
                    '[data-testid="pod-brand"], .pod-brand, .brand-name'
                );

                if (nombreEl && precioEl) {
                    items.push({
                        nombre:    nombreEl.innerText?.trim() || '',
                        precio:    precioEl.innerText?.trim() || '',
                        sku:       skuAttr.trim(),
                        url:       linkEl?.href || '',
                        imagen:    imgEl?.src || imgEl?.dataset?.src || '',
                        marca:     marcaEl?.innerText?.trim() || '',
                    });
                }
            }
            return items;
        }
        """
        try:
            return await page.evaluate(script, max_resultados)
        except Exception as exc:
            logger.error("[Sodimac] Error en extracción JS: %s", exc)
            return []

    def _normalizar(
        self,
        datos: list[dict],
        query: str,
    ) -> list[ProductoProveedorCreate]:
        """
        Convierte los datos crudos del scraper al schema Pydantic.
        Descarta filas con datos inválidos sin crashear.
        """
        from pydantic import ValidationError

        productos = []
        for item in datos:
            precio = _limpiar_precio(item.get("precio", ""))
            if not precio:
                continue  # Sin precio = no sirve para cotización

            url = item.get("url", "")
            if not url.startswith("http"):
                url = "https://www.sodimac.cl" + url

            # Asignar un SKU sintético si el sitio no lo expone
            sku = item.get("sku") or f"SOD-{hash(url) % 999999:06d}"

            try:
                producto = ProductoProveedorCreate(
                    proveedor=NombreProveedor.SODIMAC,
                    sku_proveedor=sku[:120],
                    url_producto=url,
                    nombre_raw=item.get("nombre", "Sin nombre")[:400],
                    marca=item.get("marca") or None,
                    precio_clp=precio,
                    imagen_url=item.get("imagen") or None,
                    disponible=True,
                )
                productos.append(producto)
            except ValidationError as exc:
                logger.debug("[Sodimac] Producto descartado por validación: %s", exc)

        return productos


# ---------------------------------------------------------------------------
# Scraper Easy Chile
# ---------------------------------------------------------------------------

class EasyScraper(_ScraperBase):
    """
    Scraper para easy.cl.

    NOTAS DE DOM:
        - URL de búsqueda: /search?q={query}
        - Easy usa una SPA — requiere esperar hidratación React
        - El scraper espera networkidle para dar tiempo al JS
    """

    proveedor = NombreProveedor.EASY

    def _construir_url_busqueda(self, query: str) -> str:
        from urllib.parse import quote_plus
        return f"https://www.easy.cl/search?q={quote_plus(query)}"

    async def _scrape(
        self,
        query: str,
        max_resultados: int,
        context: BrowserContext,
    ) -> list[ProductoProveedorCreate]:

        page: Page = await context.new_page()
        url = self._construir_url_busqueda(query)

        logger.info("[Easy] Navegando a: %s", url)

        # Easy es una SPA — necesita más tiempo para hidratar
        await page.goto(url, wait_until="networkidle", timeout=SCRAPER_TIMEOUT_MS)
        await _delay_humano()

        contenido = await page.content()
        if _es_bloqueado(contenido):
            logger.warning("[Easy] WAF detectado")
            raise Exception("WAF/bot-detection activado en Easy")

        try:
            await page.wait_for_selector(
                ".product-item, [data-testid='product'], .shelf-item, "
                "[class*='ProductCard'], [class*='product-card']",
                timeout=10_000,
            )
        except PlaywrightTimeout:
            logger.warning("[Easy] Selector de productos no encontrado — DOM puede haber cambiado")
            return []

        # Scroll suave para activar lazy-loading
        await self._scroll_gradual(page)
        await _delay_humano()

        datos_crudos = await self._extraer_productos(page, max_resultados)
        await page.close()

        return self._normalizar(datos_crudos)

    async def _scroll_gradual(self, page: Page) -> None:
        """
        Simula scroll humano — activa lazy-loading sin parecer bot.
        """
        for _ in range(3):
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.6)")
            await asyncio.sleep(random.uniform(0.6, 1.2))

    async def _extraer_productos(
        self,
        page: Page,
        max_resultados: int,
    ) -> list[dict]:
        script = """
        (maxResultados) => {
            const items = [];
            const cards = document.querySelectorAll(
                '.product-item, [class*="ProductCard"], [class*="product-card"], '
                + '.shelf-item, [data-testid="product"]'
            );

            for (let i = 0; i < Math.min(cards.length, maxResultados); i++) {
                const card = cards[i];

                const nombreEl = card.querySelector(
                    '[class*="product-name"], [class*="ProductName"], '
                    + '[class*="title"], h2, h3, h4'
                );
                const precioEl = card.querySelector(
                    '[class*="price"]:not([class*="original"]):not([class*="old"]), '
                    + '[class*="Price"]:not([class*="Original"]):not([class*="Old"]), '
                    + '[data-testid*="price"]'
                );
                const linkEl   = card.querySelector('a[href]');
                const imgEl    = card.querySelector('img');
                const marcaEl  = card.querySelector('[class*="brand"], [class*="Brand"]');
                const skuAttr  = card.getAttribute('data-product-id')
                    || card.getAttribute('data-sku')
                    || card.getAttribute('data-id')
                    || '';

                if (nombreEl && precioEl) {
                    items.push({
                        nombre: nombreEl.innerText?.trim() || '',
                        precio: precioEl.innerText?.trim() || '',
                        sku:    skuAttr.trim(),
                        url:    linkEl?.href || '',
                        imagen: imgEl?.src || imgEl?.dataset?.src || '',
                        marca:  marcaEl?.innerText?.trim() || '',
                    });
                }
            }
            return items;
        }
        """
        try:
            return await page.evaluate(script, max_resultados)
        except Exception as exc:
            logger.error("[Easy] Error en extracción JS: %s", exc)
            return []

    def _normalizar(self, datos: list[dict]) -> list[ProductoProveedorCreate]:
        from pydantic import ValidationError

        productos = []
        for item in datos:
            precio = _limpiar_precio(item.get("precio", ""))
            if not precio:
                continue

            url = item.get("url", "")
            if not url.startswith("http"):
                url = "https://www.easy.cl" + url

            sku = item.get("sku") or f"EASY-{hash(url) % 999999:06d}"

            try:
                producto = ProductoProveedorCreate(
                    proveedor=NombreProveedor.EASY,
                    sku_proveedor=sku[:120],
                    url_producto=url,
                    nombre_raw=item.get("nombre", "Sin nombre")[:400],
                    marca=item.get("marca") or None,
                    precio_clp=precio,
                    imagen_url=item.get("imagen") or None,
                    disponible=True,
                )
                productos.append(producto)
            except ValidationError as exc:
                logger.debug("[Easy] Producto descartado por validación: %s", exc)

        return productos


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

class ScraperOrchestrator:
    """
    Lanza todos los scrapers en paralelo y agrega los resultados.
    Si un scraper falla, devuelve lo que obtuvo del resto.
    Nunca bloquea la respuesta al cliente.
    """

    # Mapa proveedor → clase scraper. Agregar aquí al añadir nuevos.
    _SCRAPERS: dict[NombreProveedor, type[_ScraperBase]] = {
        NombreProveedor.SODIMAC: SodimacScraper,
        NombreProveedor.EASY:    EasyScraper,
    }

    async def buscar(
        self,
        query: str,
        proveedores: list[NombreProveedor],
        max_resultados: int = 10,
    ) -> list[ResultadoScraper]:
        """
        Entrada pública. Devuelve resultados de todos los proveedores
        solicitados, con graceful degradation por proveedor.
        """
        # Validar que los proveedores solicitados tienen scraper
        proveedores_validos = [p for p in proveedores if p in self._SCRAPERS]
        if not proveedores_validos:
            logger.error("Ningún proveedor válido en la lista: %s", proveedores)
            return []

        async with async_playwright() as pw:
            # Un solo browser para todos los scrapers — más eficiente
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    # Deshabilitar WebRTC — puede exponer IP real
                    "--disable-webrtc",
                ],
            )

            try:
                tareas = [
                    self._SCRAPERS[proveedor]().buscar(query, max_resultados, browser)
                    for proveedor in proveedores_validos
                ]
                # gather con return_exceptions=True — un crash no cancela los otros
                resultados_raw = await asyncio.gather(*tareas, return_exceptions=True)
            finally:
                await browser.close()

        # Normalizar resultados (convertir excepciones no capturadas a ERROR)
        resultados: list[ResultadoScraper] = []
        for proveedor, resultado in zip(proveedores_validos, resultados_raw):
            if isinstance(resultado, Exception):
                logger.error(
                    "Error no capturado en scraper %s: %s", proveedor, resultado
                )
                resultados.append(ResultadoScraper(
                    proveedor=proveedor,
                    estado=EstadoScraping.ERROR,
                    error_msg=str(resultado)[:500],
                ))
            else:
                resultados.append(resultado)

        self._log_resumen(query, resultados)
        return resultados

    def _log_resumen(self, query: str, resultados: list[ResultadoScraper]) -> None:
        for r in resultados:
            logger.info(
                "[Scraper] query='%s' proveedor=%s estado=%s productos=%d duración=%.1fs",
                query, r.proveedor, r.estado, len(r.productos), r.duracion_seg,
            )


# ---------------------------------------------------------------------------
# Función de conveniencia para usar desde el router
# ---------------------------------------------------------------------------

async def ejecutar_busqueda(
    query: str,
    proveedores: list[NombreProveedor],
    max_resultados: int = 10,
) -> list[ResultadoScraper]:
    """
    Punto de entrada desde router.py.
    Uso:
        resultados = await ejecutar_busqueda("tornillo 1/4", [NombreProveedor.SODIMAC])
    """
    orchestrator = ScraperOrchestrator()
    return await orchestrator.buscar(query, proveedores, max_resultados)