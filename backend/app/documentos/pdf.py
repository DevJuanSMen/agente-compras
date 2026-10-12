"""PDF de orden de compra, factura y estudio de mercado.

La orden y la factura replican el formato "FORMATO ORDEN DE COMPRA" entregado
(encabezado con logo, bloque Para/Nit/Fecha, tabla de 8 columnas, totales con
Retefuente y ReteICA). Se agrega al final un anexo de soporte de precios
(tienda, enlace y momento de verificacion de cada linea): es lo que permite
auditar de donde salio cada valor.
"""
from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from ..ajustes import LOGO
from ..modelos import ESTADOS_OC, Factura, OrdenCompra, Requerimiento

TZ = timezone(timedelta(hours=-5), "COT")  # Colombia no tiene horario de verano
GRIS = colors.HexColor("#E6E6E6")
GRIS_CLARO = colors.HexColor("#F4F4F4")
BORDE = colors.HexColor("#BDBDBD")
VERDE = colors.HexColor("#8DC63F")

_ss = getSampleStyleSheet()
E_NORMAL = ParagraphStyle("n", parent=_ss["Normal"], fontName="Helvetica", fontSize=8.5, leading=10.5)
E_PEQ = ParagraphStyle("p", parent=E_NORMAL, fontSize=7, leading=8.5, textColor=colors.HexColor("#555555"))
E_CENTRO = ParagraphStyle("c", parent=E_NORMAL, alignment=TA_CENTER)
E_DER = ParagraphStyle("d", parent=E_NORMAL, alignment=TA_RIGHT)
E_TIT = ParagraphStyle("t", parent=E_NORMAL, fontName="Helvetica-Bold", fontSize=17, leading=20, alignment=TA_RIGHT)
E_H2 = ParagraphStyle("h2", parent=E_NORMAL, fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=6, spaceAfter=3)
E_NEG = ParagraphStyle("b", parent=E_NORMAL, fontName="Helvetica-Bold")
E_CAB = ParagraphStyle("cab", parent=E_NORMAL, fontName="Helvetica-Bold", alignment=TA_CENTER, fontSize=8)


def num(v: float | None) -> str:
    """Formato del documento original: 2,627,200.00"""
    return f"{(v or 0):,.2f}"


def pesos(v: float | None) -> str:
    return "n/d" if v is None else f"${v:,.0f}".replace(",", ".")


def _local(d: datetime | str | None) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        try:
            d = datetime.fromisoformat(d)
        except ValueError:
            return d
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(TZ).strftime("%Y-%m-%d %H:%M")


def _esc(t: str) -> str:
    return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _logo(ancho_mm: float = 30) -> Image | str:
    if not LOGO.exists():
        return ""
    img = Image(str(LOGO))
    proporcion = img.imageHeight / img.imageWidth
    img.drawWidth = ancho_mm * mm
    img.drawHeight = ancho_mm * mm * proporcion
    return img


def _encabezado_empresa(empresa: dict) -> list:
    return [
        _logo(30),
        Paragraph(f"<b>{_esc(empresa['nombre'])}</b>", E_CENTRO),
        Paragraph(f"Nit {_esc(empresa['nit'])}", E_CENTRO),
        Spacer(1, 3 * mm),
        Paragraph(_esc(empresa["direccion"]), E_CENTRO),
        Paragraph(f"Tel: {_esc(empresa['telefono'])}", E_CENTRO),
        Paragraph(_esc(empresa["ciudad"]), E_CENTRO),
    ]


def _pie_vertical(texto: str):
    def dibujar(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.setFillColor(colors.HexColor("#333333"))
        canvas.translate(doc.pagesize[0] - 9 * mm, doc.pagesize[1] - 15 * mm)
        canvas.rotate(-90)
        canvas.drawString(0, 0, texto)
        canvas.restoreState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawRightString(doc.pagesize[0] - 15 * mm, 9 * mm, f"Página {doc.page}")
    return dibujar


def _documento_compra(oc: OrdenCompra, empresa: dict, *, titulo: str, numero: str,
                      fecha: str, extra_bloque: list[tuple[str, str]], notas_finales: list) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=14 * mm, rightMargin=16 * mm,
                            topMargin=12 * mm, bottomMargin=14 * mm,
                            title=f"{titulo} {numero}", author=empresa["nombre"])
    ancho = doc.width

    bloque = [["Para", Paragraph(_esc(oc.proveedor_nombre), E_DER)],
              ["Nit", Paragraph(_esc(oc.proveedor_nit) or "<font color='#C62828'>POR COMPLETAR</font>", E_DER)],
              ["Fecha", Paragraph(fecha, E_DER)]] + [[k, Paragraph(_esc(v), E_DER)] for k, v in extra_bloque]
    t_bloque = Table(bloque, colWidths=[30 * mm, 52 * mm])
    t_bloque.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRIS), ("BACKGROUND", (1, 0), (1, -1), GRIS_CLARO),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (0, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    derecha = [Paragraph(titulo, E_TIT), Paragraph(f"No. {numero}", ParagraphStyle(
        "no", parent=E_DER, fontSize=11, leading=13)), Spacer(1, 3 * mm), t_bloque]
    cab = Table([[_encabezado_empresa(empresa), derecha]], colWidths=[ancho * 0.45, ancho * 0.55])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                             ("BOX", (0, 0), (-1, -1), 0.4, BORDE)]))
    historia = [cab, Spacer(1, 5 * mm)]

    filas = [[Paragraph(x, E_CAB) for x in ("Ítem", "Descripción", "Cantidad", "Vr. Unitario",
                                              "Valor desc.", "Impto. Cargo", "Impto. Rete.", "Vr. Total")]]
    for n, l in enumerate(oc.lineas, start=1):
        filas.append([str(n), Paragraph(_esc(l.descripcion), E_NORMAL), num(l.cantidad), num(l.vr_unitario),
                      num(l.descuento), f"{l.iva_pct:g} %", f"{l.rete_pct:g} %".replace(".", ","), num(l.total)])
    cw = [12 * mm, None, 17 * mm, 21 * mm, 15 * mm, 15 * mm, 15 * mm, 22 * mm]
    cw[1] = ancho - sum(c for c in cw if c)
    t = Table(filas, colWidths=cw, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRIS), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"), ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRIS_CLARO]),
    ]))
    historia += [t, Spacer(1, 3 * mm)]

    totales = [["Total Bruto", num(oc.total_bruto)], ["Descuentos", num(oc.descuentos)],
               ["Subtotal", num(oc.subtotal)]]
    if oc.iva_total:
        totales.append(["IVA", num(oc.iva_total)])
    totales += [[f"Retefuente {oc.retefuente_pct:g}%".replace(".", ","), num(oc.retefuente)],
                [f"ReteICA {oc.reteica_x_mil:g}", num(oc.reteica)], ["Total a Pagar COP", num(oc.total_pagar)]]
    t_tot = Table(totales, colWidths=[38 * mm, 28 * mm])
    t_tot.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"), ("BACKGROUND", (0, -1), (-1, -1), GRIS),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    obs = [Paragraph("<b>Observaciones:</b>", E_NORMAL),
           Paragraph(_esc(oc.observaciones or "").replace("\n", "<br/>") or "&nbsp;", E_NORMAL)]
    pie = Table([[obs, t_tot]], colWidths=[ancho - 70 * mm, 70 * mm])
    pie.setStyle(TableStyle([("VALIGN", (0, 0), (0, 0), "MIDDLE"), ("VALIGN", (1, 0), (1, 0), "TOP")]))
    historia += [KeepTogether([pie])] + notas_finales

    doc.build(historia, onFirstPage=_pie_vertical(f"Elaborado por Agente de Compras {empresa['nombre']}"),
              onLaterPages=_pie_vertical(f"Elaborado por Agente de Compras {empresa['nombre']}"))
    return buf.getvalue()


def _anexo_soporte(oc: OrdenCompra, requerimiento: Requerimiento) -> list:
    filas = [[Paragraph(x, E_CAB) for x in ("Ítem", "Tienda / proveedor", "Producto publicado", "Verificación")]]
    for n, l in enumerate(oc.lineas, start=1):
        o = l.oferta or {}
        v = o.get("verificacion") or {}
        enlace = o.get("url") or ""
        prod = _esc(o.get("titulo", ""))[:160]
        if enlace:
            prod += f'<br/><link href="{_esc(enlace)}"><font color="#1565C0">{_esc(enlace[:95])}</font></link>'
        estado = ("Confirmado" if v.get("ok") else "Sin confirmar") + (
            f" · {_local(v.get('momento'))}" if v.get("momento") else "")
        if v.get("metodo"):
            estado += f"<br/>{_esc(v.get('metodo'))}"
        filas.append([str(n), Paragraph(_esc(o.get("tienda", oc.proveedor_nombre)), E_PEQ),
                      Paragraph(prod, E_PEQ), Paragraph(estado, E_PEQ)])
    t = Table(filas, colWidths=[12 * mm, 32 * mm, 96 * mm, 40 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), GRIS), ("GRID", (0, 0), (-1, -1), 0.3, BORDE),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("FONTSIZE", (0, 0), (-1, -1), 7)]))
    aprob = []
    if oc.aprobada_en:
        quien = oc.aprobada_por.nombre if oc.aprobada_por else ""
        aprob.append(Paragraph(f"<b>Pago aprobado por:</b> {_esc(quien)} · {_local(oc.aprobada_en)}", E_NORMAL))
    return [Spacer(1, 6 * mm), Paragraph("Soporte de precios", E_H2),
            Paragraph(f"Requerimiento {requerimiento.consecutivo} · Solicitante: "
                      f"{_esc(requerimiento.nombre_cargo)} · Forma de pago: {oc.forma_pago.capitalize()} · "
                      f"Elaborada por: {_esc(oc.creada_por.nombre if oc.creada_por else '')}", E_PEQ),
            Spacer(1, 2 * mm), t, Spacer(1, 3 * mm)] + aprob


def pdf_orden(oc: OrdenCompra, empresa: dict) -> bytes:
    estado = ESTADOS_OC.get(oc.estado, oc.estado)
    extra = [] if oc.estado == "aprobada" else [("Estado", estado)]
    return _documento_compra(oc, empresa, titulo="Orden de compra", numero=oc.numero,
                             fecha=oc.fecha.isoformat(), extra_bloque=extra,
                             notas_finales=_anexo_soporte(oc, oc.requerimiento))


def pdf_factura(f: Factura, empresa: dict) -> bytes:
    oc = f.orden
    estado = {"pendiente_pago": "Pendiente de pago", "pagada": "Pagada", "anulada": "Anulada"}.get(f.estado, f.estado)
    extra = [("Orden", oc.numero), ("Estado", estado)]
    if f.numero_proveedor:
        extra.append(("Fact. proveedor", f.numero_proveedor))
    notas = [Spacer(1, 5 * mm), Paragraph(
        f"Documento soporte de la orden de compra {oc.numero} del requerimiento "
        f"{oc.requerimiento.consecutivo}. Forma de pago: {oc.forma_pago}."
        + (f" Pago registrado el {_local(oc.pagada_en)} con referencia {_esc(oc.referencia_pago)}."
           if oc.pagada_en else ""), E_PEQ)]
    return _documento_compra(oc, empresa, titulo="Factura de compra", numero=f.numero,
                             fecha=f.fecha.isoformat(), extra_bloque=extra, notas_finales=notas)


# ---------------------------------------------------------------------------
# Estudio de mercado
# ---------------------------------------------------------------------------
def pdf_estudio(req: Requerimiento, resultado: dict, items: list, empresa: dict, version: int,
                fecha: datetime | None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=14 * mm,
                            topMargin=10 * mm, bottomMargin=12 * mm,
                            title=f"Estudio de mercado {req.consecutivo}", author=empresa["nombre"])
    ancho = doc.width
    cab = Table([[_logo(24), [Paragraph("Estudio de mercado", ParagraphStyle(
        "t2", parent=E_TIT, alignment=0)), Paragraph(
        f"Requerimiento <b>{req.consecutivo}</b> · {_esc(req.nombre_cargo)} · {_esc(req.area)} · "
        f"Destino: {_esc(req.destino)}", E_NORMAL), Paragraph(
        f"Versión {version} · generado {_local(fecha)} · {empresa['nombre']} NIT {empresa['nit']}", E_PEQ)]]],
        colWidths=[32 * mm, ancho - 32 * mm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                             ("LINEBELOW", (0, 0), (-1, 0), 1.2, VERDE)]))
    h = [cab, Spacer(1, 3 * mm), Paragraph(
        "Todos los precios fueron leídos de fuentes estructuradas de cada tienda (catálogo, índice de "
        "búsqueda o marcado de la página) y las opciones marcadas como verificadas se confirmaron en la "
        "tienda (simulador de carrito o página de producto) en el momento indicado. Los precios de "
        "tienda incluyen IVA.", E_PEQ)]

    for n, item in enumerate(items, start=1):
        datos = resultado.get(str(item.id)) or {}
        h.append(Paragraph(f"{n}. {_esc(item.descripcion)} — {item.cantidad:g} {item.unidad}", E_H2))
        if datos.get("error"):
            h.append(Paragraph(f"<font color='#C62828'>No se pudo estudiar esta línea: {_esc(datos['error'])}</font>", E_NORMAL))
            continue
        ofertas = datos.get("ofertas") or []
        rec = next((o for o in ofertas if o["id"] == datos.get("recomendada_id")), None)
        est = datos.get("estadisticas") or {}
        if rec:
            h.append(Table([[Paragraph(
                f"<b>Recomendada:</b> {_esc(rec['tienda'])} — {_esc(rec['titulo'][:120])} · "
                f"{pesos(rec.get('precio'))} x {rec.get('unidades_paquete', 1):g} und · "
                f"<b>{pesos(rec.get('precio_unitario'))}/und</b> · total {pesos(rec.get('costo_total'))}"
                + (" · verificada en tienda" if (rec.get('verificacion') or {}).get('ok') else ""), E_NORMAL)]],
                colWidths=[ancho], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF7E1")),
                                                     ("BOX", (0, 0), (-1, -1), 0.6, VERDE)])))
        h.append(Paragraph(
            f"{est.get('ofertas_validas', 0)} opciones válidas en {est.get('tiendas', 0)} tiendas · por unidad: "
            f"mín {pesos(est.get('precio_unitario_min'))}, mediana {pesos(est.get('precio_unitario_mediana'))}, "
            f"máx {pesos(est.get('precio_unitario_max'))}", E_PEQ))
        if datos.get("resumen"):
            h.append(Paragraph(_esc(datos["resumen"]), E_NORMAL))
        if datos.get("justificacion"):
            h.append(Paragraph(f"<i>{_esc(datos['justificacion'])}</i>", E_NORMAL))
        for a in datos.get("alertas") or []:
            h.append(Paragraph(f"<b>Alerta:</b> {_esc(a)}", ParagraphStyle("al", parent=E_PEQ, textColor=colors.HexColor("#B26A00"))))
        filas = [[Paragraph(x, E_CAB) for x in ("Tienda", "Producto", "Relev.", "Precio", "Pres.",
                                                  "$/und", "Total pedido", "Calif.", "Verificación")]]
        visibles = [o for o in ofertas if o.get("relevancia") in ("exacto", "equivalente", "relacionado")][:12]
        for o in visibles:
            v = o.get("verificacion") or {}
            prod = _esc(o["titulo"][:110])
            if o.get("url"):
                prod = f'<link href="{_esc(o["url"])}"><font color="#1565C0">{prod}</font></link>'
            marca = "<b>[REC]</b> " if o["id"] == datos.get("recomendada_id") else ""
            filas.append([
                Paragraph(marca + _esc(o["tienda"]), E_PEQ), Paragraph(prod, E_PEQ),
                Paragraph(o.get("relevancia", ""), E_PEQ), pesos(o.get("precio")),
                f"x{o.get('unidades_paquete', 1):g}", pesos(o.get("precio_unitario")), pesos(o.get("costo_total")),
                f"{o['calificacion']:.1f} ({o.get('resenas') or 0})" if o.get("calificacion") else "-",
                Paragraph(("OK " + _local(v.get("momento"))) if v.get("ok") else
                          ("No: " + _esc(v.get("detalle", ""))[:60] if v else o.get("metodo", "")), E_PEQ),
            ])
        if len(filas) > 1:
            cw = [30 * mm, 92 * mm, 18 * mm, 22 * mm, 12 * mm, 20 * mm, 24 * mm, 16 * mm]
            cw.append(ancho - sum(cw))
            t = Table(filas, colWidths=cw, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), GRIS), ("GRID", (0, 0), (-1, -1), 0.3, BORDE),
                ("FONTSIZE", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (3, 1), (7, -1), "RIGHT"),
            ]))
            h += [Spacer(1, 2 * mm), t]
        h.append(Spacer(1, 4 * mm))
    doc.build(h, onFirstPage=_pie_vertical(f"Agente de Compras {empresa['nombre']}"),
              onLaterPages=_pie_vertical(f"Agente de Compras {empresa['nombre']}"))
    return buf.getvalue()
