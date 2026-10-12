"""Fuentes de precios: un adaptador por plataforma de e-commerce.

Cada adaptador sabe dos cosas:

    buscar(consulta, n)          -> ofertas con precio estructurado
    verificar(oferta, cantidad)  -> el precio que ve el cliente HOY

La verificacion va siempre por un camino distinto al de la busqueda cuando la
plataforma lo permite: el simulador de carrito en VTEX (lo que se paga en
caja, con promociones aplicadas), la pagina de producto en Algolia y Falabella.
Asi, un indice desactualizado no llega a una orden de compra.

Plataformas cubiertas sin API key (comprobado contra los sitios reales):

    VTEX      Exito, Carulla, Olimpica, Panamericana, Easy, Jumbo, Metro, Pepeganga
    Algolia   Alkosto, Ktronix, Alkomprar (indice publico que usa su buscador)
    Falabella Falabella, Homecenter (datos de la pagina de resultados)
    Woo/Shopify/VTEX autodetectados para cualquier dominio que escriba el usuario
    Web       cualquier sitio: buscador + marcado schema.org + navegador real

MercadoLibre bloquea el acceso automatico sin credencial (verificacion de
cuenta). Con `ML_ACCESS_TOKEN` se usa su API oficial; sin el, sus resultados
entran como referencia del buscador, marcados como NO verificables.
"""
from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urljoin, urlparse

from .. import busqueda
from . import navegador, precio_pagina, red
from .modelos import Oferta, Verificacion

Progreso = Callable[[str], None]
TOLERANCIA_PRECIO = 0.005  # 0,5 %: por debajo es redondeo, no cambio de precio


def _nada(_: str) -> None:
    return None


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
@dataclass
class Fuente:
    clave: str
    nombre: str
    dominio: str
    rubros: tuple[str, ...] = ("general",)
    descripcion: str = ""

    tipo = "base"

    @property
    def base(self) -> str:
        return f"https://{self.dominio}"

    def buscar(self, consulta: str, n: int = 6, progreso: Progreso = _nada) -> list[Oferta]:
        raise NotImplementedError

    def verificar(self, oferta: Oferta, cantidad: int = 1, usar_navegador: bool = True) -> Verificacion:
        return verificar_en_pagina(oferta, usar_navegador=usar_navegador)

    def _oferta(self, **kw) -> Oferta:
        kw.setdefault("fuente", self.clave)
        kw.setdefault("tienda", self.nombre)
        kw.setdefault("dominio", self.dominio)
        return Oferta(**kw)


def comparar(oferta: Oferta, precio_actual: float | None, metodo: str, detalle: str = "",
             disponible: bool | None = None) -> Verificacion:
    if precio_actual is None or precio_actual <= 0:
        return Verificacion(ok=False, metodo=metodo,
                            detalle=detalle or "No se pudo leer el precio en la tienda")
    if oferta.precio is None:
        oferta.precio = precio_actual
    diferencia = abs(precio_actual - oferta.precio) / oferta.precio
    if disponible is False:
        return Verificacion(ok=False, precio_pagina=precio_actual, metodo=metodo,
                            detalle="La tienda lo muestra agotado")
    if diferencia <= TOLERANCIA_PRECIO:
        return Verificacion(ok=True, precio_pagina=precio_actual, metodo=metodo,
                            detalle=detalle or "Precio confirmado en la tienda")
    sentido = "subio" if precio_actual > oferta.precio else "bajo"
    return Verificacion(
        ok=False, precio_pagina=precio_actual, metodo=metodo,
        detalle=f"El precio {sentido}: buscador ${oferta.precio:,.0f} vs tienda ${precio_actual:,.0f}"
        .replace(",", "."),
    )


def verificar_en_pagina(oferta: Oferta, usar_navegador: bool = True) -> Verificacion:
    """Abre la pagina de producto y lee el precio estructurado."""
    if not oferta.url:
        return Verificacion(ok=False, metodo="pagina", detalle="La oferta no tiene URL")
    try:
        r = red.get(oferta.url)
        if not red.es_bloqueo(r) and r.status_code < 400:
            ficha = precio_pagina.leer(r.text)
            if ficha:
                return comparar(oferta, ficha.precio, f"pagina ({ficha.origen})",
                                disponible=ficha.disponible)
    except red.ErrorRed:
        pass
    if usar_navegador and navegador.disponible():
        try:
            html, _ = navegador.renderizar(oferta.url)
            ficha = precio_pagina.leer(html)
            if ficha:
                return comparar(oferta, ficha.precio, f"navegador ({ficha.origen})",
                                disponible=ficha.disponible)
        except Exception as exc:
            return Verificacion(ok=False, metodo="navegador", detalle=f"Navegador: {str(exc)[:120]}")
    return Verificacion(ok=False, metodo="pagina",
                        detalle="La pagina no publica el precio en formato legible")


# ---------------------------------------------------------------------------
# VTEX
# ---------------------------------------------------------------------------
@dataclass
class FuenteVtex(Fuente):
    tipo = "vtex"
    canal: str = "1"

    def buscar(self, consulta: str, n: int = 6, progreso: Progreso = _nada) -> list[Oferta]:
        url = (f"{self.base}/api/catalog_system/pub/products/search"
               f"?ft={quote(consulta)}&_from=0&_to={max(0, n - 1)}")
        r = red.get(url)
        if r.status_code not in (200, 206):
            raise red.ErrorRed(f"HTTP {r.status_code}")
        try:
            productos = r.json()
        except ValueError:
            raise red.ErrorRed("respuesta no es JSON")
        ofertas = []
        for p in productos[:n]:
            items = p.get("items") or []
            if not items:
                continue
            item = items[0]
            vendedores = item.get("sellers") or []
            vendedor = next(
                (s for s in vendedores if (s.get("commertialOffer") or {}).get("AvailableQuantity", 0) > 0),
                vendedores[0] if vendedores else {},
            )
            co = vendedor.get("commertialOffer") or {}
            precio = co.get("Price") or None
            imagenes = item.get("images") or []
            disponible = (co.get("AvailableQuantity") or 0) > 0
            ofertas.append(self._oferta(
                url=self._enlace(p),
                titulo=p.get("productName") or "",
                marca=p.get("brand") or "",
                sku=f"{item.get('itemId')}|{vendedor.get('sellerId', '1')}",
                vendedor=vendedor.get("sellerName") or self.nombre,
                imagen=imagenes[0].get("imageUrl", "") if imagenes else "",
                precio=float(precio) if precio else None,
                precio_antes=float(co["ListPrice"]) if co.get("ListPrice") and co.get("ListPrice") > (precio or 0) else None,
                disponible=disponible,
                stock=co.get("AvailableQuantity"),
                metodo="api_tienda",
                notas=[f"Vendido por {vendedor.get('sellerName')}"]
                if vendedor.get("sellerId") not in (None, "1") else [],
            ))
        return [o for o in ofertas if o.precio]

    def _enlace(self, p: dict) -> str:
        """Enlace a la ficha en el dominio publico de la tienda.

        El campo `link` de la API puede traer el host interno de VTEX
        (tienda.exito.com, secure.carulla.com): sirve la ficha a un lector
        automatico, pero en el navegador un script redirige a la pagina de
        inicio. Se conserva solo la ruta y se monta sobre el dominio principal."""
        if p.get("linkText"):
            return f"{self.base}/{p['linkText']}/p"
        ruta = urlparse(p.get("link") or "").path
        return urljoin(self.base, ruta) if ruta else self.base

    def verificar(self, oferta: Oferta, cantidad: int = 1, usar_navegador: bool = True) -> Verificacion:
        """Simula el carrito: el precio que cobraria la caja, con promociones."""
        try:
            sku, vendedor = (oferta.sku.split("|") + ["1"])[:2]
            cuerpo = {"items": [{"id": sku, "quantity": max(1, int(cantidad)), "seller": vendedor}],
                      "country": "COL"}
            r = red.post(f"{self.base}/api/checkout/pub/orderForms/simulation?sc={self.canal}",
                         json=cuerpo)
            if r.status_code == 200:
                items = r.json().get("items") or []
                if items:
                    it = items[0]
                    precio = (it.get("sellingPrice") or it.get("price") or 0) / 100.0
                    disp = it.get("availability") == "available"
                    cantidad_ok = (it.get("quantity") or 0) >= max(1, int(cantidad))
                    v = comparar(oferta, precio, "simulador de carrito", disponible=disp)
                    if disp and not cantidad_ok:
                        # No se puede comprar lo pedido en esta tienda: no es un
                        # cambio de precio, es una opcion que no sirve tal cual.
                        return Verificacion(
                            ok=False, precio_pagina=precio, metodo="simulador de carrito",
                            detalle=f"Cantidad insuficiente: la tienda solo permite {it.get('quantity')} "
                                    f"und por pedido y se necesitan {int(cantidad)}")
                    if v.ok and cantidad > 1:
                        v.detalle += f" para {int(cantidad)} unidades"
                    return v
                return Verificacion(ok=False, metodo="simulador de carrito",
                                    detalle="La tienda no acepta este producto en el carrito (agotado)")
        except (red.ErrorRed, ValueError):
            pass
        # Plan B: volver a consultar el catalogo por SKU.
        try:
            sku = oferta.sku.split("|")[0]
            r = red.get(f"{self.base}/api/catalog_system/pub/products/search?fq=skuId:{sku}")
            datos = r.json() if r.status_code in (200, 206) else []
            if datos:
                co = datos[0]["items"][0]["sellers"][0]["commertialOffer"]
                return comparar(oferta, co.get("Price"), "catalogo de la tienda",
                                disponible=(co.get("AvailableQuantity") or 0) > 0)
        except Exception:
            pass
        return Verificacion(ok=False, metodo="vtex", detalle="No se pudo confirmar con la tienda")


# ---------------------------------------------------------------------------
# Algolia (Alkosto, Ktronix, Alkomprar)
# ---------------------------------------------------------------------------
_ALGOLIA_CACHE: dict[str, tuple[str, str, str]] = {}
_ALGOLIA_LOCK = threading.Lock()
_ALGOLIA_RE = re.compile(r'algolia:\{[^}]*?applicationId:"(\w+)",apiKey:"(\w+)",indexName:"(\w+)"')


@dataclass
class FuenteAlgolia(Fuente):
    """Las tiendas de Colombiana de Comercio publican en su HTML la llave de
    solo-busqueda de Algolia que usa su propio buscador. Se lee de la pagina
    (no se guarda en el codigo) para que siga funcionando si la rotan."""

    tipo = "algolia"
    indice_respaldo: str = ""

    def _credenciales(self) -> tuple[str, str, str]:
        with _ALGOLIA_LOCK:
            if self.dominio in _ALGOLIA_CACHE:
                return _ALGOLIA_CACHE[self.dominio]
        r = red.get(f"{self.base}/search?text=producto")
        m = _ALGOLIA_RE.search(r.text)
        if not m:
            raise red.ErrorRed("no se encontro la configuracion del buscador de la tienda")
        cred = (m.group(1), m.group(2), m.group(3))
        with _ALGOLIA_LOCK:
            _ALGOLIA_CACHE[self.dominio] = cred
        return cred

    def buscar(self, consulta: str, n: int = 6, progreso: Progreso = _nada) -> list[Oferta]:
        app, llave, indice = self._credenciales()
        r = red.post(
            f"https://{app.lower()}-dsn.algolia.net/1/indexes/{indice}/query",
            json={"query": consulta, "hitsPerPage": n},
            headers={"X-Algolia-Application-Id": app, "X-Algolia-API-Key": llave,
                     "Referer": self.base + "/"},
        )
        if r.status_code != 200:
            raise red.ErrorRed(f"HTTP {r.status_code}")
        ofertas = []
        for h in r.json().get("hits", [])[:n]:
            precio = h.get("lowestprice_double") or h.get("discountprice_double") or h.get("pricevalue_cop_double")
            lista = h.get("pricevalue_cop_double")
            marcas = h.get("brand_string_mv") or [""]
            ofertas.append(self._oferta(
                url=urljoin(self.base, h.get("url_es_string") or ""),
                titulo=h.get("name_text_es") or "",
                marca=marcas[0] if marcas else "",
                sku=str(h.get("objectID") or h.get("code_string") or ""),
                vendedor=self.nombre,
                imagen=h.get("img-820wx820h_string") or "",
                precio=float(precio) if precio else None,
                precio_antes=float(lista) if lista and precio and lista > precio else None,
                disponible=bool(h.get("instockflag_boolean")),
                stock=h.get("stocklevel_int"),
                calificacion=round(h["averagescore_double"], 2) if h.get("averagescore_double") else None,
                resenas=h.get("totalreviews_int"),
                metodo="api_tienda",
            ))
        return [o for o in ofertas if o.precio]


# ---------------------------------------------------------------------------
# Falabella / Homecenter
# ---------------------------------------------------------------------------
_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


@dataclass
class FuenteFalabella(Fuente):
    tipo = "falabella"
    inquilino: str = "falabella-co"

    def buscar(self, consulta: str, n: int = 6, progreso: Progreso = _nada) -> list[Oferta]:
        r = red.get(f"{self.base}/{self.inquilino}/search", params={"Ntt": consulta})
        if r.status_code >= 400 or red.es_bloqueo(r):
            raise red.ErrorRed(f"HTTP {r.status_code}")
        m = _NEXT.search(r.text)
        if not m:
            raise red.ErrorRed("la pagina de resultados no trae datos")
        props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
        resultados = (props.get("results")
                      or ((props.get("searchProps") or {}).get("searchData") or {}).get("results")
                      or ((props.get("categoryProps") or {}).get("searchData") or {}).get("results")
                      or [])
        ofertas = []
        for x in resultados[:n]:
            precio, normal, nota = _precios_falabella(x.get("prices") or [])
            url = x.get("url") or ""
            if url and not url.startswith("http"):
                url = urljoin(self.base, url)
            if not url and x.get("productId"):
                url = f"{self.base}/{self.inquilino}/product/{x['productId']}/"
            vendedor = x.get("sellerName") or self.nombre
            medios = x.get("mediaUrls") or []
            ofertas.append(self._oferta(
                url=url,
                titulo=x.get("displayName") or "",
                marca=x.get("brand") or "",
                sku=str(x.get("skuId") or x.get("productId") or ""),
                vendedor=vendedor,
                imagen=medios[0] if medios else "",
                precio=precio,
                precio_antes=normal if normal and precio and normal > precio else None,
                calificacion=_num(x.get("rating")),
                resenas=int(x.get("totalReviews") or 0) or None,
                metodo="api_tienda",
                notas=[nota] if nota else [],
            ))
        return [o for o in ofertas if o.precio]

    def verificar(self, oferta: Oferta, cantidad: int = 1, usar_navegador: bool = True) -> Verificacion:
        """La ficha trae el precio en sus datos de pagina (Homecenter no lo pone en JSON-LD)."""
        try:
            r = red.get(oferta.url)
            m = _NEXT.search(r.text) if r.status_code < 400 else None
            if m:
                props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
                lista = _buscar_lista_precios(props.get("productProps") or props)
                if lista:
                    precio, _, _ = _precios_falabella(lista)
                    texto = json.dumps(props)[:400_000]
                    sin_stock = '"hasStock"' in texto and '"hasStock": true' not in texto
                    return comparar(oferta, precio, "pagina de producto",
                                    disponible=False if sin_stock else None)
        except (red.ErrorRed, ValueError):
            pass
        return verificar_en_pagina(oferta, usar_navegador)


def _buscar_lista_precios(nodo, profundidad: int = 0):
    """Primera lista de precios con forma [{type, price...}] dentro de los datos."""
    if profundidad > 8:
        return None
    if isinstance(nodo, dict):
        for clave in ("prices", "price"):
            v = nodo.get(clave)
            if isinstance(v, list) and v and isinstance(v[0], dict) and "type" in v[0]:
                return v
        for v in nodo.values():
            encontrado = _buscar_lista_precios(v, profundidad + 1)
            if encontrado:
                return encontrado
    elif isinstance(nodo, list):
        for v in nodo[:20]:
            encontrado = _buscar_lista_precios(v, profundidad + 1)
            if encontrado:
                return encontrado
    return None


def _precios_falabella(precios: list[dict]) -> tuple[float | None, float | None, str]:
    """Falabella publica varios precios: con tarjeta CMR, internet, normal.
    El de tarjeta CMR exige pagar con esa tarjeta: no es el precio de UPARSISTEM."""
    # Falabella: {"type": "internetPrice", "price": ["7.599.900"]}
    # Homecenter: {"type": "INTERNET", "price": "449.900", "priceWithoutFormatting": 449900}
    alias = {"internet": "internetPrice", "normal": "normalPrice", "cmr": "cmrPrice",
             "event": "eventPrice"}
    por_tipo: dict[str, float] = {}
    for p in precios:
        if p.get("crossed"):
            continue
        tipo = p.get("type", "")
        tipo = alias.get(tipo.lower(), tipo)
        v = _num(p.get("priceWithoutFormatting"))
        if not v:
            valores = p.get("price")
            bruto = valores[0] if isinstance(valores, list) and valores else valores
            if bruto:
                v = _num(str(bruto).replace(".", "").replace(",", "."))
        if v:
            por_tipo[tipo] = v
    precio = por_tipo.get("internetPrice") or por_tipo.get("eventPrice") or por_tipo.get("normalPrice")
    if precio is None and por_tipo:
        precio = max(v for k, v in por_tipo.items() if k != "cmrPrice") if any(
            k != "cmrPrice" for k in por_tipo) else None
    nota = ""
    if "cmrPrice" in por_tipo and precio and por_tipo["cmrPrice"] < precio:
        nota = f"Con tarjeta CMR: ${por_tipo['cmrPrice']:,.0f} (no aplica sin esa tarjeta)".replace(",", ".")
    return precio, por_tipo.get("normalPrice"), nota


# ---------------------------------------------------------------------------
# Plataformas autodetectadas (para dominios que escribe el usuario)
# ---------------------------------------------------------------------------
@dataclass
class FuenteWoo(Fuente):
    tipo = "woocommerce"

    def buscar(self, consulta: str, n: int = 6, progreso: Progreso = _nada) -> list[Oferta]:
        r = red.get(f"{self.base}/wp-json/wc/store/v1/products",
                    params={"search": consulta, "per_page": n})
        if r.status_code != 200:
            raise red.ErrorRed(f"HTTP {r.status_code}")
        ofertas = []
        for p in r.json()[:n]:
            pr = p.get("prices") or {}
            div = 10 ** int(pr.get("currency_minor_unit") or 0)
            precio = _num(pr.get("price"))
            normal = _num(pr.get("regular_price"))
            imgs = p.get("images") or []
            ofertas.append(self._oferta(
                url=p.get("permalink") or "", titulo=_sin_html(p.get("name") or ""),
                sku=str(p.get("id") or ""), vendedor=self.nombre,
                imagen=imgs[0].get("src", "") if imgs else "",
                precio=precio / div if precio else None,
                precio_antes=normal / div if normal and precio and normal > precio else None,
                moneda=pr.get("currency_code") or "COP",
                disponible=p.get("is_in_stock"),
                calificacion=_num(p.get("average_rating")) or None,
                resenas=p.get("review_count") or None,
                metodo="api_tienda",
            ))
        return [o for o in ofertas if o.precio]

    def verificar(self, oferta: Oferta, cantidad: int = 1, usar_navegador: bool = True) -> Verificacion:
        try:
            r = red.get(f"{self.base}/wp-json/wc/store/v1/products/{oferta.sku}")
            if r.status_code == 200:
                pr = r.json().get("prices") or {}
                div = 10 ** int(pr.get("currency_minor_unit") or 0)
                precio = _num(pr.get("price"))
                return comparar(oferta, precio / div if precio else None, "API de la tienda",
                                disponible=r.json().get("is_in_stock"))
        except Exception:
            pass
        return verificar_en_pagina(oferta, usar_navegador)


@dataclass
class FuenteShopify(Fuente):
    tipo = "shopify"

    def buscar(self, consulta: str, n: int = 6, progreso: Progreso = _nada) -> list[Oferta]:
        r = red.get(f"{self.base}/search/suggest.json",
                    params={"q": consulta, "resources[type]": "product", "resources[limit]": n})
        if r.status_code != 200:
            raise red.ErrorRed(f"HTTP {r.status_code}")
        productos = (((r.json().get("resources") or {}).get("results") or {}).get("products") or [])
        ofertas = []
        for p in productos[:n]:
            url = urljoin(self.base, (p.get("url") or "").split("?")[0])
            ofertas.append(self._oferta(
                url=url, titulo=p.get("title") or "", marca=p.get("vendor") or "",
                sku=(p.get("handle") or ""), vendedor=self.nombre, imagen=p.get("image") or "",
                precio=_num(p.get("price")), precio_antes=_num(p.get("compare_at_price_max")) or None,
                disponible=p.get("available"), metodo="api_tienda",
            ))
        return [o for o in ofertas if o.precio]

    def verificar(self, oferta: Oferta, cantidad: int = 1, usar_navegador: bool = True) -> Verificacion:
        try:
            r = red.get(oferta.url.rstrip("/") + ".js")
            if r.status_code == 200:
                d = r.json()
                return comparar(oferta, (d.get("price") or 0) / 100.0, "API de la tienda",
                                disponible=d.get("available"))
        except Exception:
            pass
        return verificar_en_pagina(oferta, usar_navegador)


# ---------------------------------------------------------------------------
# Web generica: buscador + pagina + navegador
# ---------------------------------------------------------------------------
_PRECIO_SNIPPET = re.compile(r"\$\s?(\d{1,3}(?:[.,]\d{3})+|\d{4,9})(?![\d.,]*\s*(?:cuotas|mes))")


@dataclass
class FuenteWeb(Fuente):
    """Cualquier sitio. Si `dominio` esta vacio, busca en toda la web."""

    tipo = "web"
    usar_navegador: bool = True
    excluir: tuple[str, ...] = ()

    def buscar(self, consulta: str, n: int = 6, progreso: Progreso = _nada) -> list[Oferta]:
        if self.dominio:
            resultados = busqueda.buscar(consulta, max_resultados=n + 2, sitio=self.dominio)
        else:
            resultados = busqueda.buscar(f"{consulta} precio comprar Colombia", max_resultados=n + 4)
        resultados = [r for r in resultados if r.url and not _excluida(r.url, self.excluir)]
        resultados.sort(key=lambda r: not busqueda.es_ficha_producto(r.url))
        ofertas: list[Oferta] = []
        leidas = 0
        for r in resultados:
            if leidas >= n:
                break
            leidas += 1
            oferta = self._leer_resultado(r, progreso)
            if oferta:
                ofertas.append(oferta)
        return ofertas

    def _leer_resultado(self, r: busqueda.Resultado, progreso: Progreso) -> Oferta | None:
        dominio = urlparse(r.url).netloc.replace("www.", "")
        tienda = self.nombre if self.dominio else _nombre_conocido(dominio)
        html, metodo = "", "marcado_estructurado"
        try:
            resp = red.get(r.url, intentos=2)
            if resp.status_code < 400 and not red.es_bloqueo(resp):
                html = resp.text
        except red.ErrorRed:
            pass
        ficha = precio_pagina.leer(html) if html else None
        # El navegador cuesta segundos por pagina: solo para fichas de producto,
        # un listado o una categoria no tiene un precio unico que leer.
        if (not ficha and self.usar_navegador and navegador.disponible()
                and busqueda.es_ficha_producto(r.url)):
            try:
                progreso(f"  abriendo en navegador: {r.url[:70]}")
                html, _ = navegador.renderizar(r.url)
                ficha = precio_pagina.leer(html)
                metodo = "navegador"
            except Exception:
                ficha = None
        if ficha:
            return Oferta(
                fuente=self.clave, tienda=tienda, dominio=dominio, url=r.url,
                titulo=ficha.nombre or r.titulo, marca=ficha.marca, sku=ficha.sku,
                vendedor=tienda, imagen=ficha.imagen, precio=ficha.precio,
                moneda=ficha.moneda or "COP", disponible=ficha.disponible,
                calificacion=ficha.calificacion, resenas=ficha.resenas, metodo=metodo,
                notas=[f"Precio leido del marcado de la pagina ({ficha.origen})"],
            )
        # Ultimo recurso: el precio del extracto del buscador. Se conserva como
        # referencia porque es un indicio util, pero NUNCA se recomienda.
        m = _PRECIO_SNIPPET.search(f"{r.titulo} {r.resumen}")
        if m:
            from ..estructurados import _numero

            return Oferta(
                fuente=self.clave, tienda=tienda, dominio=dominio, url=r.url, titulo=r.titulo,
                precio=_numero(m.group(1)), metodo="buscador",
                notas=["Precio tomado del extracto del buscador: confirmar en la tienda"],
            )
        return None


@dataclass
class FuenteMercadoLibre(Fuente):
    tipo = "mercadolibre"

    def buscar(self, consulta: str, n: int = 6, progreso: Progreso = _nada) -> list[Oferta]:
        token = os.getenv("ML_ACCESS_TOKEN")
        if token:
            r = red.get("https://api.mercadolibre.com/sites/MCO/search",
                        params={"q": consulta, "limit": n},
                        headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 200:
                ofertas = []
                for x in r.json().get("results", [])[:n]:
                    ofertas.append(self._oferta(
                        url=x.get("permalink") or "", titulo=x.get("title") or "",
                        sku=x.get("id") or "", precio=_num(x.get("price")),
                        precio_antes=_num(x.get("original_price")) or None,
                        vendedor=((x.get("seller") or {}).get("nickname") or "MercadoLibre"),
                        imagen=x.get("thumbnail") or "", disponible=True,
                        stock=x.get("available_quantity"), metodo="api_tienda",
                        notas=["Condicion: " + x.get("condition", "")] if x.get("condition") else [],
                    ))
                return [o for o in ofertas if o.precio]
        # Sin credencial: solo indicios del buscador.
        web = FuenteWeb(clave=self.clave, nombre=self.nombre, dominio=self.dominio,
                        usar_navegador=False)
        ofertas = web.buscar(consulta, n, progreso)
        for o in ofertas:
            o.metodo = "buscador"
            o.notas = ["MercadoLibre no permite verificar el precio sin credencial de su API: "
                       "es una referencia, confirmar en el enlace"]
        return ofertas

    def verificar(self, oferta: Oferta, cantidad: int = 1, usar_navegador: bool = True) -> Verificacion:
        token = os.getenv("ML_ACCESS_TOKEN")
        if token and oferta.sku:
            try:
                r = red.get(f"https://api.mercadolibre.com/items/{oferta.sku}",
                            headers={"Authorization": f"Bearer {token}"})
                if r.status_code == 200:
                    d = r.json()
                    return comparar(oferta, _num(d.get("price")), "API MercadoLibre",
                                    disponible=d.get("status") == "active")
            except Exception:
                pass
        return Verificacion(ok=False, metodo="mercadolibre",
                            detalle="MercadoLibre bloquea la verificacion automatica sin credencial")


# ---------------------------------------------------------------------------
# Catalogo
# ---------------------------------------------------------------------------
RUBROS = {
    "papeleria": "Papeleria y utiles",
    "oficina": "Oficina y mobiliario",
    "tecnologia": "Tecnologia y computo",
    "electrodomesticos": "Electrodomesticos",
    "ferreteria": "Ferreteria, herramienta y construccion",
    "electricidad": "Material electrico y electronico",
    "aseo": "Aseo y limpieza",
    "cafeteria": "Cafeteria y alimentos",
    "hogar": "Hogar y menaje",
    "salud": "Salud, enfermeria y laboratorio",
    "deportes": "Deportes y bienestar",
    "general": "General",
}

CATALOGO: list[Fuente] = [
    FuenteVtex("exito", "Éxito", "www.exito.com",
               ("general", "tecnologia", "electrodomesticos", "aseo", "cafeteria", "papeleria", "hogar", "oficina", "deportes")),
    FuenteVtex("panamericana", "Panamericana", "www.panamericana.com.co",
               ("papeleria", "oficina", "tecnologia")),
    FuenteVtex("olimpica", "Olímpica", "www.olimpica.com",
               ("general", "aseo", "cafeteria", "electrodomesticos", "tecnologia", "hogar")),
    FuenteVtex("carulla", "Carulla", "www.carulla.com", ("cafeteria", "aseo")),
    FuenteVtex("easy", "Easy", "www.easy.com.co",
               ("ferreteria", "electricidad", "hogar", "electrodomesticos", "aseo")),
    FuenteVtex("jumbo", "Jumbo", "www.tiendasjumbo.co",
               ("general", "aseo", "cafeteria", "hogar", "electrodomesticos")),
    FuenteVtex("metro", "Metro", "www.tiendasmetro.co", ("aseo", "cafeteria", "general")),
    FuenteVtex("pepeganga", "Pepe Ganga", "www.pepeganga.com", ("hogar", "deportes", "papeleria", "general")),
    FuenteAlgolia("alkosto", "Alkosto", "www.alkosto.com",
                  ("tecnologia", "electrodomesticos", "hogar", "general")),
    FuenteAlgolia("ktronix", "Ktronix", "www.ktronix.com", ("tecnologia",)),
    FuenteAlgolia("alkomprar", "Alkomprar", "www.alkomprar.com", ("tecnologia", "electrodomesticos")),
    FuenteFalabella("falabella", "Falabella", "www.falabella.com.co",
                    ("tecnologia", "electrodomesticos", "hogar", "oficina", "deportes", "general"),
                    inquilino="falabella-co"),
    FuenteFalabella("homecenter", "Homecenter", "www.homecenter.com.co",
                    ("ferreteria", "electricidad", "hogar", "oficina", "aseo", "electrodomesticos"),
                    inquilino="homecenter-co"),
    FuenteMercadoLibre("mercadolibre", "MercadoLibre", "mercadolibre.com.co", ("general",)),
    FuenteWeb("web", "Búsqueda abierta en internet", "", ("general",),
              excluir=("mercadolibre.", "facebook.", "instagram.", "youtube.", "tiktok.",
                       "pinterest.", "wikipedia.")),
]

POR_CLAVE = {f.clave: f for f in CATALOGO}


def describir() -> list[dict]:
    return [
        {"clave": f.clave, "nombre": f.nombre, "dominio": f.dominio, "tipo": f.tipo,
         "rubros": list(f.rubros),
         "verificable": f.tipo not in ("mercadolibre",) or bool(os.getenv("ML_ACCESS_TOKEN"))}
        for f in CATALOGO
    ]


def para_rubro(rubro: str, maximo: int = 6) -> list[str]:
    """Tiendas que mejor cubren un rubro, en orden del catalogo."""
    claves = [f.clave for f in CATALOGO if rubro in f.rubros and f.tipo != "web"]
    if len(claves) < 3:
        claves += [f.clave for f in CATALOGO if "general" in f.rubros and f.clave not in claves
                   and f.tipo not in ("web",)]
    return claves[:maximo]


_DETECTADAS: dict[str, Fuente] = {}


def fuente_para_sitio(texto: str, progreso: Progreso = _nada) -> Fuente:
    """Convierte lo que escribio el usuario ("ferreteria x.com", una URL, un nombre
    del catalogo) en una fuente, detectando la plataforma de e-commerce."""
    limpio = texto.strip()
    for f in CATALOGO:
        if limpio.lower() in (f.clave, f.nombre.lower(), f.dominio, f.dominio.replace("www.", "")):
            return f
    dominio = _dominio(limpio)
    if not dominio:
        # Un nombre sin dominio ("Ferreteria El Tornillo"): busqueda abierta con ese nombre.
        return FuenteWeb(clave=f"web:{limpio[:40]}", nombre=limpio[:60], dominio="")
    if dominio in _DETECTADAS:
        return _DETECTADAS[dominio]
    nombre = _nombre_de(dominio)
    fuente: Fuente | None = None
    for candidato in (FuenteVtex, FuenteWoo, FuenteShopify):
        f = candidato(clave=f"sitio:{dominio}", nombre=nombre, dominio=dominio)
        if _responde(f):
            fuente = f
            break
    if fuente is None:
        fuente = FuenteWeb(clave=f"sitio:{dominio}", nombre=nombre, dominio=dominio)
    progreso(f"{nombre}: plataforma detectada = {fuente.tipo}")
    _DETECTADAS[dominio] = fuente
    return fuente


def _responde(f: Fuente) -> bool:
    try:
        return bool(f.buscar("papel", 1)) or bool(f.buscar("cable", 1))
    except Exception:
        return False


def _dominio(texto: str) -> str:
    t = texto.lower().strip()
    if " " in t and not t.startswith("http"):
        m = re.search(r"([a-z0-9-]+\.)+[a-z]{2,}", t)
        if not m:
            return ""
        t = m.group(0)
    t = re.sub(r"^https?://", "", t).split("/")[0]
    return t if "." in t else ""


def _nombre_conocido(dominio: str) -> str:
    for f in CATALOGO:
        if f.dominio and f.dominio.replace("www.", "") == dominio.replace("www.", ""):
            return f.nombre
    return _nombre_de(dominio)


def _nombre_de(dominio: str) -> str:
    base = dominio.replace("www.", "").split(".")[0]
    return base.replace("-", " ").title()


def _excluida(url: str, excluir: tuple[str, ...]) -> bool:
    return any(e in url.lower() for e in excluir)


def _num(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        from ..estructurados import _numero

        return _numero(v)


def _sin_html(t: str) -> str:
    return re.sub(r"<[^>]+>", "", t).strip()
