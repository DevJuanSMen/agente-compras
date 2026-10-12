"""Navegador real (Chromium headless via Playwright) para paginas que arman
el precio con JavaScript.

Es el "simulador" de una persona entrando a la tienda: abre la pagina, espera
a que cargue, y lee el precio del marcado ya renderizado. Es lento (3-8 s por
pagina), asi que solo se usa cuando la lectura HTTP directa no trae precio.

Playwright sync no puede compartirse entre hilos: cada hilo tiene su propia
instancia, y el estudio de mercado corre en un hilo trabajador dedicado.
Si Playwright no esta instalado, `disponible()` devuelve False y el motor
sigue sin navegador.
"""
from __future__ import annotations

import atexit
import threading

from .red import AGENTE_USUARIO

_local = threading.local()
_instancias: list = []


def disponible() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def _pagina():
    estado = getattr(_local, "estado", None)
    if estado is None:
        from playwright.sync_api import sync_playwright

        pw = sync_playwright().start()
        navegador = pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        contexto = navegador.new_context(
            user_agent=AGENTE_USUARIO, locale="es-CO", viewport={"width": 1366, "height": 900},
            extra_http_headers={"Accept-Language": "es-CO,es;q=0.9"},
        )
        # Imagenes, fuentes y video no hacen falta para leer un precio.
        contexto.route(
            "**/*",
            lambda ruta: ruta.abort()
            if ruta.request.resource_type in ("image", "media", "font")
            else ruta.continue_(),
        )
        estado = (pw, navegador, contexto)
        _local.estado = estado
        _instancias.append(estado)
    return estado[2].new_page()


def renderizar(url: str, *, espera_ms: int = 2500, timeout_ms: int = 45_000) -> tuple[str, str]:
    """Devuelve (html renderizado, url final)."""
    pagina = _pagina()
    try:
        pagina.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            pagina.wait_for_load_state("networkidle", timeout=12_000)
        except Exception:
            pass  # sitios con sondeo permanente nunca llegan a networkidle
        pagina.wait_for_timeout(espera_ms)
        return pagina.content(), pagina.url
    finally:
        pagina.close()


def cerrar() -> None:
    while _instancias:
        pw, navegador, _ = _instancias.pop()
        try:
            navegador.close()
            pw.stop()
        except Exception:
            pass


atexit.register(cerrar)
