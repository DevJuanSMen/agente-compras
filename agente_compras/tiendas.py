"""Catalogo de tiendas donde buscar precios, por pais.

El usuario puede darle al agente la lista de comercios donde quiere que mire.
Cada entrada es (nombre visible, dominio). El dominio se usa para acotar la
busqueda con `site:` y para reconocer de que tienda viene una URL.

No hace falta que la tienda este aqui: cualquier dominio que escriba el usuario
sirve igual. Esta lista solo da los valores por defecto de la interfaz.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tienda:
    nombre: str
    dominio: str


CATALOGO: dict[str, list[Tienda]] = {
    "Colombia": [
        Tienda("Homecenter", "homecenter.com.co"),
        Tienda("Alkosto", "alkosto.com"),
        Tienda("Falabella", "falabella.com.co"),
        Tienda("Éxito", "exito.com"),
        Tienda("MercadoLibre CO", "mercadolibre.com.co"),
        Tienda("Ktronix", "ktronix.com"),
        Tienda("Jumbo", "tiendasjumbo.co"),
        Tienda("Panamericana", "panamericana.com.co"),
        Tienda("Makro", "makro.com.co"),
        Tienda("Easy", "easy.com.co"),
    ],
    "México": [
        Tienda("Home Depot MX", "homedepot.com.mx"),
        Tienda("Liverpool", "liverpool.com.mx"),
        Tienda("Coppel", "coppel.com"),
        Tienda("MercadoLibre MX", "mercadolibre.com.mx"),
        Tienda("Amazon MX", "amazon.com.mx"),
        Tienda("Walmart MX", "walmart.com.mx"),
    ],
    "Chile": [
        Tienda("Sodimac", "sodimac.cl"),
        Tienda("Falabella CL", "falabella.com"),
        Tienda("Paris", "paris.cl"),
        Tienda("Ripley", "ripley.cl"),
        Tienda("MercadoLibre CL", "mercadolibre.cl"),
        Tienda("Easy CL", "easy.cl"),
    ],
    "Perú": [
        Tienda("Sodimac PE", "sodimac.com.pe"),
        Tienda("Falabella PE", "falabella.com.pe"),
        Tienda("Ripley PE", "ripley.com.pe"),
        Tienda("MercadoLibre PE", "mercadolibre.com.pe"),
        Tienda("Oechsle", "oechsle.pe"),
    ],
    "Argentina": [
        Tienda("MercadoLibre AR", "mercadolibre.com.ar"),
        Tienda("Fravega", "fravega.com"),
        Tienda("Garbarino", "garbarino.com"),
        Tienda("Musimundo", "musimundo.com"),
        Tienda("Easy AR", "easy.com.ar"),
    ],
}

# Sitios de maquinaria y equipo industrial: aplican a cualquier pais porque el
# mercado de usados es regional o global.
INDUSTRIALES: list[Tienda] = [
    Tienda("MachineryLine", "machineryline.com.co"),
    Tienda("Mascus", "mascus.com"),
    Tienda("MachineryZone", "machineryzone.com"),
    Tienda("TuCarro Maquinaria", "tucarro.com.co"),
]


def por_defecto(pais: str) -> list[Tienda]:
    """Tiendas sugeridas para un pais. Cae a Colombia si no esta en el catalogo."""
    return CATALOGO.get(pais, CATALOGO["Colombia"])


def nombres_y_dominios(pais: str) -> list[str]:
    """Etiquetas 'Nombre (dominio)' para poblar la interfaz."""
    return [f"{t.nombre} ({t.dominio})" for t in por_defecto(pais)]


def dominio_de(etiqueta: str) -> str:
    """Saca el dominio de 'Homecenter (homecenter.com.co)' o de texto libre.

    Acepta que el usuario escriba el dominio pelado, una URL completa, o el
    formato con parentesis que produce la interfaz.
    """
    texto = etiqueta.strip()
    if "(" in texto and texto.endswith(")"):
        texto = texto[texto.rindex("(") + 1 : -1]
    texto = texto.strip().rstrip("/")
    for prefijo in ("https://", "http://", "www."):
        if texto.startswith(prefijo):
            texto = texto[len(prefijo):]
    return texto.split("/")[0].strip()


def nombre_de_dominio(dominio: str, personalizadas: dict[str, str] | None = None) -> str:
    """Nombre visible de un dominio, para etiquetar una opcion de compra."""
    if personalizadas and dominio in personalizadas:
        return personalizadas[dominio]
    for tiendas in list(CATALOGO.values()) + [INDUSTRIALES]:
        for t in tiendas:
            if t.dominio == dominio:
                return t.nombre
    # homecenter.com.co -> Homecenter
    return dominio.split(".")[0].capitalize()
