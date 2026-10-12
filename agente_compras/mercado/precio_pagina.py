"""Lectura del precio publicado en una pagina de producto.

Solo se aceptan fuentes estructuradas, en este orden:

1. JSON-LD `schema.org/Product` (lo que la tienda le entrega a Google)
2. Microdatos `itemprop="price"`
3. Metadatos `product:price:amount` / `og:price:amount`
4. Datos de analitica de e-commerce (`GAProductData`, `dataLayer` con `price`)

No se raspa "el primer $ que aparezca en la pagina": en una ficha conviven el
precio, el precio tachado, la cuota mensual, el envio y los productos
sugeridos. Un precio mal tomado en una orden de compra es peor que ninguno.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .. import estructurados


@dataclass
class PrecioPagina:
    precio: float | None
    moneda: str = ""
    nombre: str = ""
    marca: str = ""
    sku: str = ""
    disponible: bool | None = None
    calificacion: float | None = None
    resenas: int | None = None
    imagen: str = ""
    origen: str = ""  # json-ld | microdatos | meta | analitica

    def __bool__(self) -> bool:
        return self.precio is not None and self.precio > 0


_ITEMPROP = re.compile(
    r'<[^>]+itemprop=["\']price["\'][^>]*?(?:content=["\']([^"\']+)["\'])[^>]*>', re.I
)
_ITEMPROP_ALT = re.compile(
    r'<[^>]+content=["\']([^"\']+)["\'][^>]*itemprop=["\']price["\'][^>]*>', re.I
)
_META = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:product:price:amount|og:price:amount)["\'][^>]*'
    r'content=["\']([^"\']+)["\']', re.I
)
_META_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']'
    r'(?:product:price:amount|og:price:amount)["\']', re.I
)
_ANALITICA = re.compile(r'GAProductData\s*:\s*\[\s*\{[^}]*?price\s*:\s*"?([\d.]+)"?', re.S)
_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_OG_IMG = re.compile(r'<meta[^>]+property=["\']og:image["\'][^>]*content=["\']([^"\']+)', re.I)


def leer(html: str) -> PrecioPagina:
    ficha = estructurados.extraer(html)
    titulo = ficha.nombre or _titulo(html)
    imagen = (_OG_IMG.search(html) or [None, ""])[1] if _OG_IMG.search(html) else ""
    base = dict(
        nombre=titulo,
        marca=ficha.marca,
        sku=ficha.sku,
        disponible=_disp(ficha.disponibilidad),
        calificacion=_float(ficha.calificacion),
        resenas=_int(ficha.resenas),
        imagen=imagen,
    )
    if ficha.precio and ficha.precio > 0:
        return PrecioPagina(precio=ficha.precio, moneda=ficha.moneda or "COP",
                            origen="json-ld", **base)

    for patron, origen in ((_ITEMPROP, "microdatos"), (_ITEMPROP_ALT, "microdatos"),
                           (_META, "meta"), (_META_ALT, "meta"), (_ANALITICA, "analitica")):
        m = patron.search(html)
        if m:
            valor = estructurados._numero(m.group(1))
            if valor and valor > 0:
                return PrecioPagina(precio=valor, moneda="COP", origen=origen, **base)
    return PrecioPagina(precio=None, origen="", **base)


def _titulo(html: str) -> str:
    m = _TITULO.search(html)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()[:200]


def _disp(texto: str) -> bool | None:
    if not texto:
        return None
    t = texto.lower()
    if t in ("disponible", "disponibilidad limitada", "preventa", "bajo pedido"):
        return True
    if t in ("agotado", "descontinuado"):
        return False
    return None


def _float(v) -> float | None:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except ValueError:
        return None


def _int(v) -> int | None:
    try:
        return int(float(str(v))) if v not in (None, "") else None
    except ValueError:
        return None
