"""Busqueda y lectura de paginas web, para proveedores que no traen estas
herramientas del lado del servidor (Groq y cualquier modelo abierto).

Anthropic no usa este modulo: alli `web_search` y `web_fetch` corren en la
infraestructura del proveedor. Aqui tenemos que hacerlo nosotros.

Backends de busqueda:
  - `ddg`    DuckDuckGo via el paquete `ddgs`. No necesita API key. Default.
  - `tavily` Tavily. Necesita TAVILY_API_KEY, pero da resultados mas limpios.
"""
from __future__ import annotations

import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser

AGENTE_USUARIO = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
TIMEOUT_HTTP = 20
MAX_CARACTERES_PAGINA = 6_000

# DuckDuckGo limita si se le pegan muchas consultas seguidas.
INTENTOS_BUSQUEDA = 3
PAUSA_ENTRE_BUSQUEDAS = float(os.getenv("AGENTE_PAUSA_BUSQUEDA", "1.5"))
PAUSA_REINTENTO = 4.0

_ultima_busqueda = 0.0
_candado = threading.Lock()


def _respetar_pausa() -> None:
    """Espacia las consultas al buscador para no gatillar su limite."""
    global _ultima_busqueda
    with _candado:
        falta = PAUSA_ENTRE_BUSQUEDAS - (time.monotonic() - _ultima_busqueda)
        if falta > 0:
            time.sleep(falta)
        _ultima_busqueda = time.monotonic()


@dataclass
class Resultado:
    titulo: str
    url: str
    resumen: str

    def como_texto(self) -> str:
        return f"- {self.titulo}\n  URL: {self.url}\n  {self.resumen}"


# ---------------------------------------------------------------------------
# Busqueda
# ---------------------------------------------------------------------------
def buscar(
    consulta: str,
    *,
    max_resultados: int = 6,
    region: str = "co-es",
    sitio: str | None = None,
) -> list[Resultado]:
    """Busca en la web. Con `sitio`, restringe a ese dominio con `site:`."""
    if sitio:
        consulta = f"site:{sitio} {consulta}"
    backend = os.getenv("AGENTE_BUSCADOR", "ddg").lower()
    if backend == "tavily":
        return _buscar_tavily(consulta, max_resultados)
    return _buscar_ddg(consulta, max_resultados, region)


def buscar_en_tiendas(
    consulta: str, dominios: list[str], *, por_tienda: int = 3, region: str = "co-es"
) -> dict[str, list[Resultado]]:
    """Corre la misma consulta acotada a cada tienda. Devuelve {dominio: resultados}.

    Una busqueda por tienda es mas cara en tiempo, pero es la unica forma de
    garantizar cobertura: una busqueda global suele devolver solo los dos o tres
    comercios mejor posicionados en SEO, e ignora al resto.
    """
    salida: dict[str, list[Resultado]] = {}
    for dominio in dominios:
        encontrados = [
            r for r in buscar(consulta, max_resultados=por_tienda, region=region, sitio=dominio)
            if r.url and dominio.split(".")[0] in r.url.lower()
        ]
        if encontrados:
            # Primero las fichas de producto: una pagina de categoria no tiene
            # un precio unico que reportar, y es lo que mas devuelve el buscador
            # cuando la consulta no trae modelo.
            salida[dominio] = sorted(encontrados, key=lambda r: not es_ficha_producto(r.url))
    return salida


# Patrones de URL de ficha de producto en los e-commerce mas comunes.
_RUTAS_PRODUCTO = (
    "/p/", "/product/", "/producto/", "/dp/", "/item/", "/ip/", "/mlc-", "/mco-",
    "/mla-", "/mlm-", "/mpe-", "/sku", "/prod/",
)
_RUTAS_CATEGORIA = ("/c/", "/category/", "/categoria/", "/k/", "/listado", "/search",
                    "/buscar", "/brand/", "/marca/", "/collections/")


def es_ficha_producto(url: str) -> bool:
    """Distingue la pagina de UN producto de un listado o una categoria."""
    u = url.lower()
    if any(p in u for p in _RUTAS_PRODUCTO) or u.rstrip("/").endswith("/p"):
        return True
    if any(c in u for c in _RUTAS_CATEGORIA):
        return False
    # Sin pistas en la ruta, un id numerico largo al final suele ser un producto.
    return bool(re.search(r"[-/]\d{6,}/?$", u))


def _buscar_ddg(consulta: str, max_resultados: int, region: str) -> list[Resultado]:
    """DuckDuckGo con reintentos.

    Una corrida hace ~20 busquedas (una por tienda, mas las generales y las de
    rivales) y DDG empieza a responder 202/429 a partir de la tercera seguida.
    Sin espaciado y reintentos, la mitad de las tiendas se quedaria sin precio.
    """
    from ddgs import DDGS

    ultimo = ""
    for intento in range(INTENTOS_BUSQUEDA):
        _respetar_pausa()
        try:
            with DDGS() as ddgs:
                crudos = list(ddgs.text(consulta, region=region, max_results=max_resultados))
            if crudos:
                return _a_resultados(crudos)
            ultimo = "sin resultados"
        except Exception as exc:
            ultimo = str(exc)[:120]
        if intento < INTENTOS_BUSQUEDA - 1:
            time.sleep(PAUSA_REINTENTO * (intento + 1))
    return [Resultado("Busqueda fallida", "", f"El buscador no respondio: {ultimo}")]


def _a_resultados(crudos: list[dict]) -> list[Resultado]:

    return [
        Resultado(
            titulo=r.get("title", "") or "sin titulo",
            url=r.get("href", "") or r.get("url", "") or "",
            resumen=(r.get("body", "") or "")[:400],
        )
        for r in crudos
    ]


def _buscar_tavily(consulta: str, max_resultados: int) -> list[Resultado]:
    import json

    clave = os.getenv("TAVILY_API_KEY")
    if not clave:
        return [Resultado("Sin credencial", "", "AGENTE_BUSCADOR=tavily pero falta TAVILY_API_KEY")]

    cuerpo = json.dumps(
        {"api_key": clave, "query": consulta, "max_results": max_resultados,
         "search_depth": "basic"}
    ).encode()
    peticion = urllib.request.Request(
        "https://api.tavily.com/search",
        data=cuerpo,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_HTTP) as r:
            datos = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as exc:
        return [Resultado("Busqueda fallida", "", f"Tavily no respondio: {exc}")]

    return [
        Resultado(
            titulo=x.get("title", "sin titulo"),
            url=x.get("url", ""),
            resumen=(x.get("content", "") or "")[:400],
        )
        for x in datos.get("results", [])
    ]


# ---------------------------------------------------------------------------
# Lectura de paginas
# ---------------------------------------------------------------------------
class _ExtractorTexto(HTMLParser):
    """Saca el texto visible, descartando script, style, nav y footer."""

    IGNORAR = {"script", "style", "noscript", "svg", "nav", "footer", "header", "form"}
    BLOQUE = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._saltar = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORAR:
            self._saltar += 1
        elif tag in self.BLOQUE:
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORAR and self._saltar:
            self._saltar -= 1

    def handle_data(self, data):
        if not self._saltar:
            texto = data.strip()
            if texto:
                self.partes.append(texto + " ")

    def resultado(self) -> str:
        texto = "".join(self.partes)
        texto = re.sub(r"[ \t]+", " ", texto)
        texto = re.sub(r"\n\s*\n+", "\n", texto)
        return texto.strip()


def leer(url: str, *, max_caracteres: int = MAX_CARACTERES_PAGINA) -> str:
    """Descarga una pagina y devuelve su texto plano, recortado."""
    if not url.startswith(("http://", "https://")):
        return f"URL invalida: {url}"

    peticion = urllib.request.Request(
        url, headers={"User-Agent": AGENTE_USUARIO, "Accept-Language": "es,en;q=0.8"}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=TIMEOUT_HTTP) as r:
            tipo = r.headers.get_content_type()
            if tipo not in ("text/html", "text/plain", "application/xhtml+xml"):
                return f"No es una pagina de texto ({tipo}); no se pudo leer."
            crudo = r.read(2_000_000)
            codificacion = r.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as exc:
        return f"El sitio respondio {exc.code}; probablemente bloquea lectores automaticos."
    except Exception as exc:
        return f"No se pudo leer la pagina: {exc}"

    html = crudo.decode(codificacion, "replace")

    # El precio suele venir en el JSON-LD que la tienda emite para Google, no
    # en el texto visible: se antepone para que el modelo lo vea primero.
    from . import estructurados

    ficha = estructurados.extraer(html)
    cabecera = (ficha.como_texto() + "\n\n") if ficha else ""

    extractor = _ExtractorTexto()
    try:
        extractor.feed(html)
    except Exception:
        pass
    texto = extractor.resultado()
    if not texto and not cabecera:
        return "La pagina no expuso texto legible (probablemente se arma con JavaScript)."
    if len(texto) > max_caracteres:
        texto = texto[:max_caracteres] + "\n[...texto recortado...]"
    return cabecera + texto
