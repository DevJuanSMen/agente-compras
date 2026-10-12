"""Capa HTTP compartida por todas las fuentes.

Tres cosas que la demo no tenia y que importan cuando hay plata de por medio:

- Cortesia por dominio: nunca dos peticiones al mismo sitio en menos de
  `PAUSA_DOMINIO` segundos. Un bloqueo de una tienda a mitad del estudio deja
  un hueco en la comparativa.
- Reintentos con espera ante 429/5xx y fallas de red.
- Certificados del almacen de Windows (`truststore`): algunas tiendas
  (Jumbo, Dollarcity) sirven la cadena incompleta y `certifi` las rechaza.
"""
from __future__ import annotations

import os
import ssl
import threading
import time
from urllib.parse import urlparse

import httpx

AGENTE_USUARIO = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
CABECERAS = {
    "User-Agent": AGENTE_USUARIO,
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.6",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
}
TIMEOUT = float(os.getenv("AGENTE_TIMEOUT_HTTP", "25"))
PAUSA_DOMINIO = float(os.getenv("AGENTE_PAUSA_DOMINIO", "0.8"))
INTENTOS = 3

_ultimo_por_dominio: dict[str, float] = {}
_candado = threading.Lock()
_local = threading.local()


def _contexto_ssl():
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # pragma: no cover - sin truststore se usa certifi
        return True


def cliente() -> httpx.Client:
    """Un cliente por hilo: httpx.Client no es seguro entre hilos con HTTP/2."""
    c = getattr(_local, "cliente", None)
    if c is None:
        c = httpx.Client(
            headers=CABECERAS, follow_redirects=True, timeout=TIMEOUT, verify=_contexto_ssl()
        )
        _local.cliente = c
    return c


def _esperar_turno(url: str) -> None:
    dominio = urlparse(url).netloc
    with _candado:
        falta = PAUSA_DOMINIO - (time.monotonic() - _ultimo_por_dominio.get(dominio, 0))
        _ultimo_por_dominio[dominio] = time.monotonic() + max(0.0, falta)
    if falta > 0:
        time.sleep(falta)


class ErrorRed(RuntimeError):
    pass


def pedir(
    metodo: str,
    url: str,
    *,
    json: dict | None = None,
    headers: dict | None = None,
    params: dict | None = None,
    intentos: int = INTENTOS,
) -> httpx.Response:
    ultimo = ""
    for intento in range(intentos):
        _esperar_turno(url)
        try:
            r = cliente().request(metodo, url, json=json, headers=headers, params=params)
            if r.status_code in (429, 500, 502, 503, 504) and intento < intentos - 1:
                ultimo = f"HTTP {r.status_code}"
                time.sleep(2.0 * (intento + 1))
                continue
            return r
        except httpx.HTTPError as exc:
            ultimo = f"{type(exc).__name__}: {exc}"[:200]
            if intento < intentos - 1:
                time.sleep(1.5 * (intento + 1))
    raise ErrorRed(ultimo or "sin respuesta")


def get(url: str, **kw) -> httpx.Response:
    return pedir("GET", url, **kw)


def post(url: str, **kw) -> httpx.Response:
    return pedir("POST", url, **kw)


def es_bloqueo(r: httpx.Response) -> bool:
    """Detecta paginas de verificacion anti-bot que responden 200."""
    u = str(r.url).lower()
    if any(s in u for s in ("account-verification", "/captcha", "challenge", "/blocked")):
        return True
    if r.status_code in (401, 403):
        return True
    cuerpo = r.text[:4000].lower() if "html" in r.headers.get("content-type", "") else ""
    return any(s in cuerpo for s in ("cf-challenge", "are you a robot", "captcha-delivery",
                                      "verifica que eres humano"))
