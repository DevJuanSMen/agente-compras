"""Lectura de los datos de producto que las tiendas publican en JSON-LD.

Casi todo e-commerce emite `schema.org/Product` en un `<script type=
"application/ld+json">` para que Google muestre precio y disponibilidad en los
resultados. Ese bloque lo genera el servidor, asi que esta ahi aunque la pagina
pinte el precio con JavaScript.

Es la diferencia entre "precio n/d" y un precio real: el extractor de texto
descarta los `<script>`, y con ellos se iba justo el dato que buscamos.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_BLOQUES = re.compile(
    r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class Producto:
    nombre: str = ""
    marca: str = ""
    sku: str = ""
    precio: float | None = None
    moneda: str = ""
    precio_anterior: float | None = None
    disponibilidad: str = ""
    calificacion: str = ""
    resenas: str = ""
    vendedor: str = ""
    comentarios: list[str] = field(default_factory=list)

    def como_texto(self) -> str:
        lineas = ["DATOS PUBLICADOS POR LA TIENDA (marcado estructurado, no inferidos):"]
        if self.nombre:
            lineas.append(f"  PRODUCTO: {self.nombre}")
        if self.marca:
            lineas.append(f"  MARCA: {self.marca}")
        if self.sku:
            lineas.append(f"  SKU/REFERENCIA: {self.sku}")
        if self.precio is not None:
            precio = f"  PRECIO: {self.moneda} {self.precio:,.0f}".replace(",", ".")
            if self.precio_anterior and self.precio_anterior > self.precio:
                precio += f"  (antes {self.moneda} {self.precio_anterior:,.0f})".replace(",", ".")
            lineas.append(precio)
        if self.disponibilidad:
            lineas.append(f"  DISPONIBILIDAD: {self.disponibilidad}")
        if self.vendedor:
            lineas.append(f"  VENDEDOR: {self.vendedor}")
        if self.calificacion:
            lineas.append(f"  CALIFICACION: {self.calificacion}"
                          + (f" sobre {self.resenas} resenas" if self.resenas else ""))
        for c in self.comentarios[:3]:
            lineas.append(f"  COMENTARIO: {c}")
        return "\n".join(lineas) if len(lineas) > 1 else ""

    def __bool__(self) -> bool:
        return bool(self.nombre or self.precio is not None)


def extraer(html: str) -> Producto:
    """Devuelve el Producto del primer bloque JSON-LD que lo declare."""
    for bruto in _BLOQUES.findall(html):
        for nodo in _nodos(bruto):
            if _es_producto(nodo):
                return _leer_producto(nodo)
    return Producto()


# ---------------------------------------------------------------------------
def _nodos(bruto: str):
    """Aplana el JSON-LD: puede ser un objeto, una lista o traer un @graph."""
    try:
        datos = json.loads(bruto.strip())
    except (json.JSONDecodeError, ValueError):
        return
    pendientes = datos if isinstance(datos, list) else [datos]
    while pendientes:
        nodo = pendientes.pop(0)
        if not isinstance(nodo, dict):
            continue
        grafo = nodo.get("@graph")
        if isinstance(grafo, list):
            pendientes += grafo
        yield nodo


def _es_producto(nodo: dict) -> bool:
    tipo = nodo.get("@type", "")
    tipos = tipo if isinstance(tipo, list) else [tipo]
    return any("Product" in str(t) for t in tipos)


def _leer_producto(nodo: dict) -> Producto:
    oferta = _primera(nodo.get("offers"))
    valoracion = nodo.get("aggregateRating") or {}
    p = Producto(
        nombre=_texto(nodo.get("name")),
        marca=_texto(_campo(nodo.get("brand"), "name")),
        sku=_texto(nodo.get("sku") or nodo.get("mpn") or nodo.get("gtin13")),
        precio=_numero(oferta.get("price") or _campo(oferta.get("priceSpecification"), "price")),
        moneda=_texto(oferta.get("priceCurrency")
                      or _campo(oferta.get("priceSpecification"), "priceCurrency")),
        precio_anterior=_numero(oferta.get("highPrice")),
        disponibilidad=_disponibilidad(oferta.get("availability")),
        calificacion=_texto(valoracion.get("ratingValue")) if valoracion else "",
        resenas=_texto(valoracion.get("reviewCount") or valoracion.get("ratingCount"))
        if valoracion else "",
        vendedor=_texto(_campo(oferta.get("seller"), "name")),
    )
    for resena in (nodo.get("review") or [])[:3] if isinstance(nodo.get("review"), list) else []:
        if isinstance(resena, dict):
            cuerpo = _texto(resena.get("reviewBody") or resena.get("description"))
            if cuerpo:
                autor = _texto(_campo(resena.get("author"), "name"))
                p.comentarios.append(f'"{cuerpo[:280]}"' + (f" — {autor}" if autor else ""))
    return p


def _primera(valor):
    if isinstance(valor, list):
        return valor[0] if valor and isinstance(valor[0], dict) else {}
    return valor if isinstance(valor, dict) else {}


def _campo(valor, clave: str):
    if isinstance(valor, dict):
        return valor.get(clave)
    if isinstance(valor, list) and valor:
        return _campo(valor[0], clave)
    return valor if isinstance(valor, str) else None


def _texto(valor) -> str:
    if valor is None:
        return ""
    return str(valor).strip()[:200]


def _numero(valor) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    # "1.899.900,00" (es) y "1,899,900.00" (en) conviven en el mismo pais.
    texto = re.sub(r"[^\d.,]", "", str(valor))
    if not texto:
        return None
    if "," in texto and "." in texto:
        # El que aparece mas a la derecha es el decimal: "1.899.900,00" o "1,899,900.00".
        decimal = "," if texto.rindex(",") > texto.rindex(".") else "."
        miles = "." if decimal == "," else ","
        texto = texto.replace(miles, "").replace(decimal, ".")
    elif texto.count(",") == 1 and len(texto.split(",")[-1]) <= 2:
        texto = texto.replace(",", ".")          # "19,99"
    elif texto.count(".") == 1 and len(texto.split(".")[-1]) <= 2:
        pass                                      # "1899900.50" ya es float valido
    else:
        # Un solo tipo de separador repetido, o grupos de 3: son miles.
        texto = texto.replace(",", "").replace(".", "")
    try:
        return float(texto)
    except ValueError:
        return None


def _disponibilidad(valor) -> str:
    texto = _texto(valor).rsplit("/", 1)[-1]
    return {
        "InStock": "disponible",
        "OutOfStock": "agotado",
        "PreOrder": "preventa",
        "BackOrder": "bajo pedido",
        "LimitedAvailability": "disponibilidad limitada",
        "Discontinued": "descontinuado",
        "SoldOut": "agotado",
    }.get(texto, texto)
