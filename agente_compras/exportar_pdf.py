"""Exporta un Informe a PDF, para archivarlo o adjuntarlo a una orden de compra.

Se usa PyMuPDF, que ya esta entre las dependencias por la lectura de PDF. El
layout es deliberadamente simple: un cursor vertical que baja, con salto de
pagina automatico. No hace falta un motor de maquetacion para un informe de
una a tres paginas, y evita agregar otra dependencia.

Los enlaces quedan clicables: el valor del informe es poder comprobar cada
precio en la tienda, y eso se pierde si el PDF los imprime como texto muerto.
"""
from __future__ import annotations

import datetime as _dt
import pathlib

from .models import AnalisisItem, Informe

# Carta, en puntos.
ANCHO, ALTO = 612, 792
MARGEN = 48
ANCHO_UTIL = ANCHO - 2 * MARGEN

TINTA = (0.13, 0.14, 0.16)
SUAVE = (0.42, 0.45, 0.50)
LINEA = (0.85, 0.86, 0.88)
ENLACE = (0.10, 0.36, 0.66)

COLOR_RECOMENDACION = {
    "comprar": (0.11, 0.50, 0.29),
    "negociar": (0.54, 0.43, 0.04),
    "comparar_mas": (0.70, 0.33, 0.04),
    "no_comprar": (0.69, 0.16, 0.16),
}
TEXTO_RECOMENDACION = {
    "comprar": "COMPRAR",
    "negociar": "NEGOCIAR ANTES DE COMPRAR",
    "comparar_mas": "COMPARAR MAS OPCIONES",
    "no_comprar": "NO COMPRAR",
}
TEXTO_VEREDICTO = {
    "muy_barato": "Muy por debajo del mercado",
    "buen_precio": "Buen precio",
    "precio_justo": "Precio de mercado",
    "caro": "Por encima del mercado",
    "muy_caro": "Muy por encima del mercado",
    "sin_datos": "Sin precio que evaluar",
}


class _Lienzo:
    """Cursor vertical sobre un documento, con salto de pagina automatico."""

    def __init__(self, doc):
        self.doc = doc
        self.pagina = None
        self.y = 0.0
        self._nueva_pagina()

    def _nueva_pagina(self) -> None:
        self.pagina = self.doc.new_page(width=ANCHO, height=ALTO)
        self.y = MARGEN

    def espacio(self, alto: float) -> None:
        """Reserva alto; si no cabe en la pagina, abre una nueva."""
        if self.y + alto > ALTO - MARGEN:
            self._nueva_pagina()

    def texto(
        self, contenido: str, *, tam: float = 9.5, fuente: str = "helv",
        color=TINTA, sangria: float = 0.0, ancho: float | None = None,
        interlinea: float = 1.35,
    ) -> None:
        if not contenido:
            return
        ancho = ancho or (ANCHO_UTIL - sangria)
        alto_linea = tam * interlinea
        for parrafo in str(contenido).split("\n"):
            for linea in _ajustar(parrafo, ancho, tam):
                self.espacio(alto_linea)
                self.pagina.insert_text(
                    (MARGEN + sangria, self.y + tam), linea,
                    fontname=fuente, fontsize=tam, color=color,
                )
                self.y += alto_linea

    def titulo(self, contenido: str, *, tam: float = 13) -> None:
        self.espacio(tam * 2.4)
        self.y += tam * 0.7
        self.texto(contenido, tam=tam, fuente="hebo")
        self.y += 3
        self.regla()
        self.y += 5

    def regla(self, color=LINEA) -> None:
        self.espacio(6)
        self.pagina.draw_line(
            (MARGEN, self.y), (ANCHO - MARGEN, self.y), color=color, width=0.6
        )
        self.y += 6

    def enlace(self, url: str, *, sangria: float = 0.0, tam: float = 7.5) -> None:
        """Escribe la URL y la deja clicable."""
        if not url:
            return
        visible = url if len(url) <= 105 else url[:102] + "..."
        alto = tam * 1.35
        self.espacio(alto)
        punto = (MARGEN + sangria, self.y + tam)
        self.pagina.insert_text(punto, visible, fontname="helv", fontsize=tam, color=ENLACE)
        import fitz  # PyMuPDF

        ancho_txt = _ancho_texto(visible, tam)
        # `from` tiene que ser un Rect de fitz: con una tupla el enlace se
        # inserta sin error pero no queda clicable.
        rect = fitz.Rect(punto[0], self.y, punto[0] + ancho_txt, self.y + alto)
        try:
            self.pagina.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": url})
        except Exception:
            pass  # un enlace roto no debe impedir exportar el informe
        self.y += alto

    def banda(self, texto: str, color) -> None:
        alto = 22
        self.espacio(alto + 6)
        self.pagina.draw_rect(
            (MARGEN, self.y, ANCHO - MARGEN, self.y + alto),
            color=None, fill=_aclarar(color), width=0,
        )
        self.pagina.draw_line((MARGEN, self.y), (MARGEN, self.y + alto), color=color, width=2.5)
        self.pagina.insert_text(
            (MARGEN + 10, self.y + 15), texto, fontname="hebo", fontsize=11, color=color
        )
        self.y += alto + 8

    def fila(self, celdas: list[str], anchos: list[float], *, negrita=False, tam=8.5) -> None:
        alto = tam * 1.5
        self.espacio(alto)
        x = MARGEN
        fuente = "hebo" if negrita else "helv"
        for celda, ancho in zip(celdas, anchos):
            recortado = _recortar(str(celda), ancho - 6, tam)
            self.pagina.insert_text(
                (x + 3, self.y + tam), recortado, fontname=fuente, fontsize=tam, color=TINTA
            )
            x += ancho
        self.y += alto


def _aclarar(color, factor: float = 0.90):
    return tuple(c + (1 - c) * factor for c in color)


def _ancho_texto(texto: str, tam: float) -> float:
    return len(texto) * tam * 0.50


def _ajustar(parrafo: str, ancho: float, tam: float) -> list[str]:
    """Corta un parrafo en lineas que entren en `ancho`."""
    if not parrafo.strip():
        return [""]
    lineas, actual = [], ""
    for palabra in parrafo.split():
        prueba = f"{actual} {palabra}".strip()
        if _ancho_texto(prueba, tam) <= ancho:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _recortar(texto: str, ancho: float, tam: float) -> str:
    if _ancho_texto(texto, tam) <= ancho:
        return texto
    caben = max(1, int(ancho / (tam * 0.50)) - 1)
    return texto[:caben] + "…"


def _money(valor, moneda: str = "") -> str:
    if valor is None:
        return "no publica"
    return f"{moneda} {valor:,.0f}".replace(",", ".").strip()


# ---------------------------------------------------------------------------
def _pintar_item(lz: _Lienzo, a: AnalisisItem) -> None:
    lz.titulo(f"{a.marca} {a.modelo or ''} — {a.producto}".strip(), tam=13)

    color = COLOR_RECOMENDACION.get(a.recomendacion, SUAVE)
    lz.banda(TEXTO_RECOMENDACION.get(a.recomendacion, a.recomendacion.upper()), color)
    lz.texto(a.resumen, tam=9.5)
    lz.y += 4

    lz.texto(
        f"Producto {a.calificacion_producto:.1f}/5    "
        f"Marca {a.calificacion_marca:.1f}/5    "
        f"Precio {a.calificacion_precio:.1f}/5    "
        f"Global {a.calificacion_global:.1f}/5",
        tam=9, fuente="hebo", color=SUAVE,
    )
    lz.y += 6

    # --- Donde comprarlo ---------------------------------------------------
    lz.titulo("Donde comprarlo", tam=11)
    if not a.donde_comprar:
        lz.texto("No se encontro el producto publicado en las tiendas consultadas.",
                 tam=9, color=SUAVE)
    else:
        anchos = [110, 95, 90, 80, 141]
        lz.fila(["Tienda", "Precio", "Disponibilidad", "Envio", "Garantia"],
                anchos, negrita=True)
        lz.regla()
        for o in a.donde_comprar:
            lz.fila(
                [o.tienda, _money(o.precio, o.moneda), o.disponibilidad,
                 o.envio or "no indica", o.garantia or "no indica"],
                anchos,
            )
            lz.enlace(o.url, sangria=6)
            lz.y += 2
        lz.y += 4
        if a.mejor_opcion:
            lz.texto("Mejor opcion", tam=9.5, fuente="hebo")
            lz.texto(a.mejor_opcion, tam=9, sangria=8)
        if a.ahorro_posible:
            lz.texto(f"Ahorro posible: {a.ahorro_posible}", tam=9, fuente="hebo",
                     color=COLOR_RECOMENDACION["comprar"])

    # --- Precio de mercado -------------------------------------------------
    lz.titulo("Precio de mercado", tam=11)
    r = a.rango_mercado
    lz.texto(
        f"Consultado: {_money(a.precio_cotizado, a.moneda_cotizada or '')}     "
        f"Tipico: {_money(r.tipico, r.moneda)}     "
        f"Rango: {_money(r.minimo, r.moneda)} – {_money(r.maximo, r.moneda)}"
        + (f"     Desviacion: {a.desviacion_pct:+.1f}%" if a.desviacion_pct is not None else ""),
        tam=9, fuente="hebo",
    )
    lz.texto(f"{TEXTO_VEREDICTO.get(a.veredicto_precio, a.veredicto_precio)}. "
             f"{a.justificacion_precio}", tam=9)
    lz.texto(f"Base del rango: {r.base} (confianza {r.confianza})", tam=8, color=SUAVE)

    # --- Opiniones ---------------------------------------------------------
    if a.comentarios_clientes:
        lz.titulo("Que dicen los compradores", tam=11)
        for c in a.comentarios_clientes:
            marca = {"positivo": "[+]", "neutral": "[=]", "negativo": "[-]"}[c.sentimiento]
            lz.texto(f'{marca} "{c.texto}"', tam=9, sangria=6)
            lz.texto(f"{c.autor or 'comprador anonimo'} — {c.fuente}", tam=8,
                     color=SUAVE, sangria=18)
            lz.enlace(c.url, sangria=18)
            lz.y += 3

    # --- Alternativas ------------------------------------------------------
    if a.alternativas:
        lz.titulo("Otras marcas comparables", tam=11)
        for alt in a.alternativas:
            lz.texto(f"{alt.marca} {alt.modelo}  —  {alt.calificacion:.1f}/5  —  "
                     f"{alt.precio_estimado or 'precio no encontrado'}",
                     tam=9, fuente="hebo")
            lz.texto(alt.equivalencia, tam=8.5, sangria=8, color=SUAVE)
            if alt.ventajas:
                lz.texto("+ " + "; ".join(alt.ventajas), tam=8.5, sangria=8)
            if alt.desventajas:
                lz.texto("- " + "; ".join(alt.desventajas), tam=8.5, sangria=8)
            if alt.url:
                lz.enlace(alt.url, sangria=8)
            lz.y += 3

    # --- Riesgos y negociacion --------------------------------------------
    if a.banderas_rojas:
        lz.titulo("Banderas rojas", tam=11)
        for x in a.banderas_rojas:
            lz.texto(f"!  {x}", tam=9, color=COLOR_RECOMENDACION["no_comprar"], sangria=4)
    if a.preguntas_al_proveedor:
        lz.titulo("Preguntas para el vendedor", tam=11)
        for q in a.preguntas_al_proveedor:
            lz.texto(f"?  {q}", tam=9, sangria=4)
    if a.costo_total_propiedad:
        lz.titulo("Costo total de propiedad", tam=11)
        for x in a.costo_total_propiedad:
            lz.texto(f"•  {x}", tam=9, sangria=4)

    # --- Fuentes -----------------------------------------------------------
    if a.fuentes:
        lz.titulo("Fuentes", tam=11)
        lz.texto(f"Confianza del analisis: {a.confianza_analisis}", tam=8.5, color=SUAVE)
        for f in a.fuentes:
            lz.texto(f"{f.titulo}  ({f.tipo})", tam=8.5, sangria=4)
            lz.enlace(f.url, sangria=12)


def exportar(informe: Informe, destino: str | pathlib.Path) -> pathlib.Path:
    """Escribe el informe como PDF y devuelve la ruta."""
    import fitz  # PyMuPDF

    destino = pathlib.Path(destino)
    doc = fitz.open()
    lz = _Lienzo(doc)

    # Portada breve, no una pagina entera: el informe suele tener un solo item.
    lz.texto("INFORME DE COMPRA", tam=8, fuente="hebo", color=SUAVE)
    lz.texto("Asistente de Compras", tam=20, fuente="hebo")
    lz.texto(_dt.datetime.now().strftime("Generado el %d/%m/%Y a las %H:%M"),
             tam=8.5, color=SUAVE)
    cot = informe.cotizacion
    if cot and cot.proveedor:
        lz.texto(f"Cotizacion de: {cot.proveedor}"
                 + (f"   ({cot.fecha})" if cot.fecha else ""), tam=9)
    lz.y += 4
    lz.regla()

    if not informe.analisis:
        lz.texto("No se pudo completar el analisis.", tam=11, fuente="hebo")
        for nota in informe.notas_investigacion:
            lz.texto(f"- {nota}", tam=9, color=SUAVE)
    for a in informe.analisis:
        _pintar_item(lz, a)

    if informe.notas_investigacion and informe.analisis:
        lz.titulo("Notas de la corrida", tam=10)
        for nota in informe.notas_investigacion:
            lz.texto(f"- {nota}", tam=8.5, color=SUAVE)

    # Pie tecnico, discreto: sirve para auditar con que se genero.
    lz.y += 8
    lz.regla()
    pie = "Los precios y comentarios provienen de las paginas enlazadas y pueden cambiar. "
    if informe.proveedor:
        pie += f"Generado con {informe.proveedor} / {informe.modelo}."
    lz.texto(pie, tam=7.5, color=SUAVE)

    doc.save(str(destino))
    doc.close()
    return destino


def a_bytes(informe: Informe) -> bytes:
    """El PDF en memoria, para el boton de descarga de la interfaz."""
    import io
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ruta = exportar(informe, pathlib.Path(tmp) / "informe.pdf")
        return io.BytesIO(ruta.read_bytes()).getvalue()
