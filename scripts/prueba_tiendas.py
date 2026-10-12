"""Prueba la logica de tiendas y el map-reduce, sin red y sin API.

Cubre lo que se rompio de verdad durante el desarrollo:
  - las fichas de tienda llegan al dossier con su nombre y su URL
  - ninguna llamada acumula historial (el contexto no crece al cuadrado)
  - las paginas bloqueadas caen al extracto del buscador en vez de perderse
  - el porte del producto sale del tamano, nunca de la potencia
  - no quedan caracteres de control en el codigo (un \\b mal escrito se cuela
    como byte 0x08 y rompe un regex en silencio)

    python scripts/prueba_tiendas.py
"""
from __future__ import annotations

import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from agente_compras import busqueda, config, tiendas  # noqa: E402
from agente_compras.core import Uso  # noqa: E402
from agente_compras.models import Cotizacion, LineaCotizacion  # noqa: E402
from agente_compras.proveedor_comun import (  # noqa: E402
    AgenteTexto, Respuesta, _clase_tamano, _consultas_rivales, _priorizar,
)

ITEM = LineaCotizacion(
    descripcion="Nevera no frost 300 litros", marca="Samsung", modelo="RT38K5930",
    categoria="nevera no frost", cantidad=1, precio_unitario=1899900.0, moneda="COP",
    especificaciones=["Capacidad 300 litros", "Tecnologia Digital Inverter"],
)


class AgenteFalso(AgenteTexto):
    """Responde segun la fase que detecta en el system prompt."""

    def __init__(self, json_guion=None):
        self.uso = Uso()
        self.limitador = None
        self.llamadas: list[list[dict]] = []
        self.json_guion = list(json_guion or [])

    def _completar(self, mensajes, *, max_tokens, esfuerzo, formato_json, progreso):
        self.llamadas.append(mensajes)
        if formato_json:
            if not self.json_guion:
                raise AssertionError("no habia respuesta JSON preparada")
            return Respuesta(self.json_guion.pop(0), 100, 50)
        sistema = mensajes[0]["content"]
        if "datos de compra" in sistema:
            return Respuesta("PRODUCTO: Nevera Samsung RT38\nPRECIO: COP 1.899.900\n"
                             "DISPONIBILIDAD: disponible", 100, 50)
        if "datos duros" in sistema:
            return Respuesta("PRECIOS: Samsung RT38 | 2024 | COP 1899900 | nuevo", 100, 50)
        return Respuesta("2. DONDE COMPRARLO\n" + "x" * 400, 200, 100)


class RedFalsa:
    """Sustituye busqueda.* sin tocar la red."""

    def __init__(self, bloqueadas: set[str] | None = None):
        self.bloqueadas = bloqueadas or set()
        self.leidas: list[str] = []
        self.consultas: list[str] = []
        self._orig = (busqueda.buscar, busqueda.buscar_en_tiendas, busqueda.leer)

    def __enter__(self):
        busqueda.buscar = self._buscar
        busqueda.buscar_en_tiendas = self._por_tienda
        busqueda.leer = self._leer
        return self

    def __exit__(self, *_):
        busqueda.buscar, busqueda.buscar_en_tiendas, busqueda.leer = self._orig

    def _buscar(self, consulta, **kw):
        self.consultas.append(consulta)
        return [busqueda.Resultado("opiniones", "https://review.test/opiniones", "gente opina")]

    def _por_tienda(self, consulta, dominios, **kw):
        self.consultas.append(f"[tiendas] {consulta}")
        return {
            d: [busqueda.Resultado(f"Producto en {d}", f"https://{d}/p/123", "COP 1.899.900")]
            for d in dominios
        }

    def _leer(self, url, **kw):
        self.leidas.append(url)
        if url in self.bloqueadas:
            return "El sitio respondio 403; probablemente bloquea lectores automaticos."
        return f"Pagina {url}. Precio COP 1.899.900. Disponible. Envio gratis."


# ---------------------------------------------------------------------------
def probar_catalogo_de_tiendas() -> None:
    assert "homecenter.com.co" in [t.dominio for t in tiendas.por_defecto("Colombia")]
    assert "sodimac.cl" in [t.dominio for t in tiendas.por_defecto("Chile")]
    # Un pais no listado cae a Colombia en vez de romper.
    assert tiendas.por_defecto("Narnia") == tiendas.por_defecto("Colombia")

    casos = [
        ("Homecenter (homecenter.com.co)", "homecenter.com.co"),
        ("https://www.alkosto.com/", "alkosto.com"),
        ("exito.com", "exito.com"),
        ("  mitienda.com.co/catalogo  ", "mitienda.com.co"),
    ]
    for entrada, esperado in casos:
        assert tiendas.dominio_de(entrada) == esperado, f"{entrada} -> {tiendas.dominio_de(entrada)}"
    assert tiendas.nombre_de_dominio("homecenter.com.co") == "Homecenter"
    assert tiendas.nombre_de_dominio("miproveedor.com") == "Miproveedor"
    print("[ok] catalogo de tiendas y parseo de dominios")


def probar_fichas_llegan_al_dossier() -> None:
    agente = AgenteFalso()
    dominios = ["homecenter.com.co", "alkosto.com", "exito.com"]
    with RedFalsa() as red:
        dossier = agente.investigar(
            ITEM, pais="Colombia", moneda="COP", competidores=["LG"],
            progreso=lambda _: None, dominios=dominios,
        )
    assert dossier.startswith("2. DONDE COMPRARLO")

    reduce = agente.llamadas[-1]
    assert len(reduce) == 2, f"el reduce debe ser system+user, llegaron {len(reduce)}"
    contenido = reduce[1]["content"]
    assert "FICHAS DE TIENDA" in contenido
    for d in dominios:
        assert d in contenido, f"falta la tienda {d} en el dossier"
    assert "Homecenter" in contenido, "no se resolvio el nombre visible de la tienda"
    assert "300 litros" in contenido, "las especificaciones no llegaron"
    print(f"[ok] fichas de {len(dominios)} tiendas con su URL en el dossier")


def probar_sin_acumular_historial() -> None:
    agente = AgenteFalso()
    with RedFalsa():
        agente.investigar(ITEM, pais="Colombia", moneda="COP", competidores=["LG", "Mabe"],
                          progreso=lambda _: None, dominios=["alkosto.com", "exito.com"])
    tamanos = [len(json.dumps(m)) for m in agente.llamadas[:-1]]
    assert max(tamanos) < 3 * min(tamanos), f"el contexto esta acumulando: {tamanos}"
    assert all(len(m) == 2 for m in agente.llamadas), "alguna llamada arrastra historial"
    print(f"[ok] {len(agente.llamadas)} llamadas independientes, sin acumular contexto")


def probar_tienda_bloqueada() -> None:
    """Si la tienda bloquea, el extracto del buscador entra igual: trae el precio."""
    bloqueada = "https://alkosto.com/p/123"
    agente = AgenteFalso()
    with RedFalsa(bloqueadas={bloqueada}) as red:
        agente.investigar(ITEM, pais="Colombia", moneda="COP", competidores=[],
                          progreso=lambda _: None,
                          dominios=["homecenter.com.co", "alkosto.com"])
    contenido = agente.llamadas[-1][1]["content"]
    assert "alkosto.com" in contenido, "la tienda bloqueada desaparecio del dossier"
    assert "no se pudo leer la pagina" in contenido, "no se marco como no leida"
    assert "403" not in contenido, "el mensaje de error entro como si fuera contenido"
    print("[ok] tienda bloqueada cae al extracto del buscador, marcada como tal")


def probar_clase_tamano() -> None:
    """Sirve para cualquier rubro, y nunca usa la potencia."""
    casos = [
        (["Capacidad 300 litros"], "300 litros"),
        (["Pantalla 55 pulgadas"], "55 pulgadas"),
        (["Peso operativo: 22.200 kg"], "22 toneladas"),
        (["Peso 22.2 t"], "22 toneladas"),
        (["Motor 121 HP"], ""),            # la potencia sola no define el porte
        ([], ""),
    ]
    for specs, esperado in casos:
        got = _clase_tamano(specs)
        assert got == esperado, f"{specs} -> {got!r}, se esperaba {esperado!r}"
    print("[ok] porte del producto: litros, pulgadas o toneladas; nunca potencia")


def probar_consultas_rivales() -> None:
    item = LineaCotizacion(
        descripcion="Excavadora", marca="Caterpillar", modelo="320 GC",
        categoria="excavadora sobre orugas", cantidad=1, precio_unitario=1.0, moneda="USD",
        especificaciones=["Motor C4.4 ACERT, 121 HP", "Peso operativo: 22.200 kg"],
    )
    q = _consultas_rivales(item, ["Hitachi"])["Hitachi"][0]
    assert "22 toneladas" in q, q
    assert "HP" not in q and "C4.4" not in q, f"la potencia envenena la consulta: {q}"
    assert "  " not in q, f"doble espacio en {q!r}"

    sin_specs = LineaCotizacion(
        descripcion="Nevera", marca="Samsung", modelo="X", categoria="nevera",
        cantidad=1, precio_unitario=None, moneda=None, especificaciones=[],
    )
    assert "  " not in _consultas_rivales(sin_specs, ["LG"])["LG"][0]
    print(f"[ok] consultas de rival acotadas por porte: {q!r}")


def probar_prioridad_de_fuentes() -> None:
    candidatos = [
        busqueda.Resultado("listado", "https://mercadolibre.com.co/listado", ""),
        busqueda.Resultado("opiniones", "https://mercadolibre.com.co/reviews/x", ""),
        busqueda.Resultado("anuncio", "https://www.bing.com/aclick?ld=xyz", ""),
        busqueda.Resultado("fb", "https://facebook.com/grupo", ""),
    ]
    orden = _priorizar(candidatos)
    assert orden[0].titulo == "opiniones", [r.titulo for r in orden]
    assert all(r.titulo not in ("fb", "anuncio") for r in orden), "entro basura"

    espejos = [busqueda.Resultado(f"m{t}", f"https://machineryline.{t}/x", "")
               for t in ("mx", "es", "uk", "info", "com")]
    assert len(_priorizar(espejos)) == 2, "los dominios espejo deben limitarse a 2"
    print("[ok] prioriza opiniones, descarta anuncios y limita dominios espejo")


def probar_json_obliga_links() -> None:
    """El esquema exige URL en cada opcion de compra y en cada comentario."""
    from agente_compras.models import AnalisisItem, ComentarioCliente, OpcionCompra

    for modelo in (OpcionCompra, ComentarioCliente):
        req = modelo.model_json_schema().get("required", [])
        assert "url" in req, f"{modelo.__name__} deberia exigir url"

    props = AnalisisItem.model_json_schema()["properties"]
    for campo in ("donde_comprar", "mejor_opcion", "ahorro_posible"):
        assert campo in props, f"falta {campo} en el analisis"
    print("[ok] el esquema exige link en opciones de compra y comentarios")


def probar_reparacion_json() -> None:
    bueno = Cotizacion(
        proveedor=None, fecha=None, moneda="COP", total=None,
        items=[ITEM], condiciones=[], notas="",
    ).model_dump_json()
    agente = AgenteFalso(json_guion=['{"proveedor": "X"}', f"```json\n{bueno}\n```"])
    lineas: list[str] = []
    cot = agente._pedir_json(sistema="s", usuario="u", esquema=Cotizacion,
                             progreso=lineas.append)
    assert isinstance(cot, Cotizacion) and cot.items[0].marca == "Samsung"
    assert any("reparando" in l for l in lineas), lineas
    assert len(agente.llamadas[-1]) == 4, "el reintento debe llevar exactamente 4 mensajes"
    print("[ok] reparacion de JSON sin acumular intentos previos")


def probar_sin_caracteres_de_control() -> None:
    sucios = []
    for archivo in RAIZ.rglob("*.py"):
        if "__pycache__" in str(archivo):
            continue
        datos = archivo.read_bytes()
        malos = [hex(b) for b in (0x07, 0x08, 0x0B, 0x0C, 0x1B) if bytes([b]) in datos]
        if malos:
            sucios.append((archivo.name, malos))
    assert not sucios, f"caracteres de control en el codigo: {sucios}"
    print("[ok] sin caracteres de control en el codigo fuente")


def probar_proveedores_registrados() -> None:
    """Los cuatro proveedores deben poder resolverse sin credencial cargada."""
    from agente_compras.core import crear_agente

    for p in config.PROVEEDORES:
        try:
            crear_agente(p)
        except Exception as exc:
            # Sin key debe quejarse de la credencial, no de un import roto.
            assert "API_KEY" in str(exc) or "api_key" in str(exc).lower(), \
                f"{p} fallo por algo que no es la credencial: {exc}"
    try:
        crear_agente("inexistente")
    except ValueError as exc:
        assert "Proveedor desconocido" in str(exc)
    else:
        raise AssertionError("un proveedor inexistente deberia fallar")
    print(f"[ok] los {len(config.PROVEEDORES)} proveedores resuelven: "
          f"{', '.join(config.PROVEEDORES)}")


def probar_etiqueta_de_busqueda() -> None:
    """Sin modelo, la marca sola no sirve: "Samsung" devuelve celulares."""
    from agente_compras.proveedor_comun import _etiqueta

    def L(**kw):
        base = dict(descripcion="", marca=None, modelo=None, categoria="", cantidad=1,
                    precio_unitario=None, moneda=None, especificaciones=[])
        base.update(kw)
        return LineaCotizacion(**base)

    casos = [
        # Sin modelo manda la descripcion completa, no la marca sola.
        (L(descripcion="nevera Samsung no frost de 300 litros", marca="Samsung",
           categoria="nevera no frost"), "nevera Samsung no frost de 300 litros"),
        # Con modelo, marca + modelo es preciso y basta.
        (L(descripcion="Excavadora CAT", marca="Caterpillar", modelo="320 GC",
           categoria="excavadora"), "Caterpillar 320 GC"),
        # Sin descripcion, se arma con marca y categoria.
        (L(marca="LG", categoria="lavadora carga frontal"), "LG lavadora carga frontal"),
        # "puLGadas" contiene "lg": la marca debe compararse por palabra.
        (L(descripcion="televisor 55 pulgadas", marca="LG", categoria="smart tv 4k"),
         "LG televisor 55 pulgadas smart tv 4k"),
        (L(descripcion="taladro percutor", categoria="taladro percutor"), "taladro percutor"),
    ]
    for item, esperado in casos:
        got = _etiqueta(item)
        assert got == esperado, f"{item.descripcion!r} -> {got!r}, se esperaba {esperado!r}"
    print("[ok] etiqueta de busqueda: nunca la marca sola, comparacion por palabra")


def probar_lotes_por_proveedor() -> None:
    """Cada proveedor agrupa paginas segun su cuello de botella."""
    from agente_compras.proveedor_comun import _en_lotes

    assert _en_lotes([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert _en_lotes([1, 2, 3], 0) == [[1, 2, 3]], "0 debe significar 'todas juntas'"
    assert _en_lotes([1, 2, 3], 9) == [[1, 2, 3]], "un lote mayor que la lista es una sola"
    assert _en_lotes([], 3) == []

    # Gemini: pocas peticiones por dia -> todas las paginas en una llamada.
    agente = AgenteFalso()
    agente.paginas_por_llamada = 0
    with RedFalsa():
        agente.investigar(ITEM, pais="Colombia", moneda="COP", competidores=[],
                          progreso=lambda _: None,
                          dominios=["homecenter.com.co", "alkosto.com", "exito.com"])
    con_lote = len(agente.llamadas)

    # Groq: pocos tokens por minuto -> una pagina por llamada.
    agente2 = AgenteFalso()
    agente2.paginas_por_llamada = 1
    with RedFalsa():
        agente2.investigar(ITEM, pais="Colombia", moneda="COP", competidores=[],
                           progreso=lambda _: None,
                           dominios=["homecenter.com.co", "alkosto.com", "exito.com"])
    sin_lote = len(agente2.llamadas)

    assert con_lote < sin_lote, (
        f"agrupar deberia gastar menos peticiones: {con_lote} vs {sin_lote}"
    )
    print(f"[ok] lotes: {con_lote} llamadas agrupando vs {sin_lote} de a una")


def probar_json_ld() -> None:
    """El precio vive en el JSON-LD que la tienda emite para Google."""
    from agente_compras import estructurados

    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Product",
     "name":"Nevera SAMSUNG No Frost 307 Lts RB30N4160B",
     "sku":"1587531","brand":{"@type":"Brand","name":"SAMSUNG"},
     "aggregateRating":{"ratingValue":4.78,"reviewCount":14},
     "offers":{"@type":"Offer","price":"2798345","priceCurrency":"COP",
               "availability":"http://schema.org/InStock",
               "seller":{"@type":"Organization","name":"exito"}}}
    </script></head><body><p>El precio lo pinta JavaScript</p></body></html>
    """
    ficha = estructurados.extraer(html)
    assert ficha, "no se detecto el producto"
    assert ficha.precio == 2798345.0, ficha.precio
    assert ficha.moneda == "COP" and ficha.marca == "SAMSUNG"
    assert ficha.disponibilidad == "disponible", ficha.disponibilidad
    assert ficha.vendedor == "exito"
    texto = ficha.como_texto()
    assert "2.798.345" in texto and "4.78" in texto, texto
    print("[ok] JSON-LD: precio, disponibilidad, vendedor y calificacion")


def probar_formatos_de_precio() -> None:
    """Los separadores conviven: "1.899.900,00" y "1,899,900.00"."""
    from agente_compras.estructurados import _numero

    casos = [
        ("2798345", 2798345.0), (2798345, 2798345.0), ("1.899.900,00", 1899900.0),
        ("1,899,900.00", 1899900.0), ("1899900.50", 1899900.5), ("$ 1.899.900", 1899900.0),
        ("19,99", 19.99), ("", None), (None, None), ("agotado", None),
    ]
    for entrada, esperado in casos:
        got = _numero(entrada)
        assert got == esperado, f"{entrada!r} -> {got}, se esperaba {esperado}"
    print("[ok] precios con separadores es/en y con simbolo de moneda")


def probar_ficha_vs_categoria() -> None:
    """Una pagina de categoria no tiene un precio unico que reportar."""
    from agente_compras.busqueda import es_ficha_producto

    fichas = [
        "https://www.exito.com/refrigerador-313lt-959544/p",
        "https://articulo.mercadolibre.com.co/MCO-2831389456-nevera-_JM",
        "https://www.homecenter.com.co/homecenter-co/product/333831/nevera",
        "https://www.amazon.com/dp/B08XYZ",
    ]
    categorias = [
        "https://www.homecenter.com.co/homecenter-co/k/nevera-300-litros",
        "https://www.alkosto.com/nevera-samsung/c/nevera-samsung",
        "https://www.falabella.com.co/falabella-co/category/cat1040982/Neveras",
        "https://listado.mercadolibre.com.co/300-litros-no-frost",
    ]
    for u in fichas:
        assert es_ficha_producto(u), f"deberia ser ficha: {u}"
    for u in categorias:
        assert not es_ficha_producto(u), f"deberia ser categoria: {u}"
    print(f"[ok] distingue {len(fichas)} fichas de {len(categorias)} categorias")


def probar_guardia_de_desviacion() -> None:
    """Una desviacion absurda no puede reportarse con confianza alta.

    Paso de verdad: el agente dijo +266% con confianza "alta" para una
    excavadora, porque tomo el precio "desde" de una pagina de listado. El
    prompt ya pedia bajar la confianza y el modelo lo ignoro, asi que la regla
    vive en codigo.
    """
    from agente_compras.core import fijar_precio_cotizado
    from agente_compras.ejemplo import ANALISIS

    item = LineaCotizacion(
        descripcion="Excavadora", marca="Caterpillar", modelo="320 GC",
        categoria="excavadora", cantidad=1, precio_unitario=165000.0, moneda="USD",
        especificaciones=[],
    )
    a = ANALISIS.model_copy(deep=True)
    a.rango_mercado.moneda = "USD"
    a.rango_mercado.tipico = 45000.0
    a.rango_mercado.confianza = "alta"
    a.confianza_analisis = "alta"
    a.banderas_rojas = []

    fijar_precio_cotizado(a, item, "USD")
    assert a.desviacion_pct is not None and a.desviacion_pct > 250, a.desviacion_pct
    assert a.confianza_analisis == "baja", "la confianza global debio bajar"
    assert a.rango_mercado.confianza == "baja", "la confianza del rango debio bajar"
    assert any("no es comparable" in b for b in a.banderas_rojas), a.banderas_rojas

    # Una desviacion normal no se toca.
    b = ANALISIS.model_copy(deep=True)
    b.rango_mercado.moneda = "USD"
    b.rango_mercado.tipico = 150000.0
    b.rango_mercado.confianza = "alta"
    b.confianza_analisis = "alta"
    b.banderas_rojas = []
    fijar_precio_cotizado(b, item, "USD")
    assert abs(b.desviacion_pct - 10.0) < 0.01, b.desviacion_pct
    assert b.confianza_analisis == "alta", "una desviacion del 10% no debe degradarse"
    assert not b.banderas_rojas

    # Con monedas distintas no se recalcula: la resta no tendria sentido.
    c = ANALISIS.model_copy(deep=True)
    c.rango_mercado.moneda = "COP"
    c.rango_mercado.tipico = 600_000_000.0
    c.desviacion_pct = None
    fijar_precio_cotizado(c, item, "USD")
    assert c.desviacion_pct is None, "no debe comparar USD contra COP"
    print("[ok] desviacion absurda degrada la confianza y avisa; la normal no")


if __name__ == "__main__":
    probar_catalogo_de_tiendas()
    probar_json_ld()
    probar_guardia_de_desviacion()
    probar_formatos_de_precio()
    probar_ficha_vs_categoria()
    probar_fichas_llegan_al_dossier()
    probar_sin_acumular_historial()
    probar_tienda_bloqueada()
    probar_etiqueta_de_busqueda()
    probar_lotes_por_proveedor()
    probar_clase_tamano()
    probar_consultas_rivales()
    probar_prioridad_de_fuentes()
    probar_json_obliga_links()
    probar_reparacion_json()
    probar_proveedores_registrados()
    probar_sin_caracteres_de_control()
    print("\nTiendas y proveedores: verde.")
