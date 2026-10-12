"""Excel en los formatos de UPARSISTEM.

- `cuadro_comparativo`: replica "Cuadro Comparativo de Cotizaciones.xlsx"
  (3 cotizaciones por item + proveedor elegido + observaciones, con las firmas
  de Director, Profesional Financiero y Aprobo).
- `formato_requerimiento`: replica "REQUERIMIENTOS UPARSISTEM SAS 2026.xlsx".
"""
from __future__ import annotations

import io
from collections import Counter

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from ..ajustes import LOGO
from ..modelos import Requerimiento

FINO = Side(style="thin", color="999999")
BORDE = Border(left=FINO, right=FINO, top=FINO, bottom=FINO)
CAB = PatternFill("solid", fgColor="D9E7C5")
GRIS = PatternFill("solid", fgColor="EDEDED")
NEG = Font(bold=True, name="Arial", size=9)
NORMAL = Font(name="Arial", size=9)
CENTRO = Alignment(horizontal="center", vertical="center", wrap_text=True)
IZQ = Alignment(horizontal="left", vertical="center", wrap_text=True)
MONEDA = '"$"#,##0'


def _celda(ws, ref, valor=None, *, fuente=NORMAL, alin=IZQ, relleno=None, borde=True, formato=None):
    c = ws[ref]
    if valor is not None:
        c.value = valor
    c.font = fuente
    c.alignment = alin
    if relleno:
        c.fill = relleno
    if borde:
        c.border = BORDE
    if formato:
        c.number_format = formato
    return c


def _rango(ws, rango, valor=None, **kw):
    ws.merge_cells(rango)
    inicio = rango.split(":")[0]
    _celda(ws, inicio, valor, **kw)
    if kw.get("borde", True):
        for fila in ws[rango]:
            for c in fila:
                c.border = BORDE


def _logo(ws, ancla: str, alto_px: int = 60) -> None:
    if LOGO.exists():
        img = XLImage(str(LOGO))
        prop = img.width / img.height
        img.height = alto_px
        img.width = int(alto_px * prop)
        ws.add_image(img, ancla)


def _a_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
def cuadro_comparativo(req: Requerimiento, filas: list[dict], empresa: dict, firmas: dict) -> bytes:
    """`filas`: una por item con {item, ofertas validas ordenadas, seleccion}."""
    # Las 3 tiendas con mas cobertura del requerimiento son las columnas.
    conteo = Counter()
    for f in filas:
        for t in {o["tienda"] for o in f["ofertas"]}:
            conteo[t] += 1
        if f["seleccion"]:
            conteo[f["seleccion"]["tienda"]] += 0.5  # desempata a favor de lo elegido
    tiendas = [t for t, _ in conteo.most_common(3)]
    while len(tiendas) < 3:
        tiendas.append("")

    wb = Workbook()
    ws = wb.active
    ws.title = "COTIZACIONES"
    anchos = {"A": 6, "B": 16, "C": 16, "D": 16, "E": 8, "F": 9, "G": 13, "H": 14, "I": 13, "J": 14,
              "K": 13, "L": 14, "M": 13, "N": 14, "O": 34}
    for col, w in anchos.items():
        ws.column_dimensions[col].width = w

    _rango(ws, "A1:O1", "CUADRO COMPARATIVO DE COTIZACIONES", fuente=Font(bold=True, name="Arial", size=12),
           alin=CENTRO, borde=False)
    ws.row_dimensions[1].height = 48
    _logo(ws, "A1", 56)
    _rango(ws, "A2:O2", f"1. PROGRAMA / REQUERIMIENTO: {req.consecutivo} - {req.area} - {req.destino}", fuente=NEG)
    _rango(ws, "A3:O3", f"ENTIDAD-ORGANIZACIÓN : {empresa['nombre']}", fuente=NEG)
    _rango(ws, "A4:O4", f"2. RUBRO: {req.tipo or ''} - Solicitante: {req.nombre_cargo}", fuente=NEG)
    _rango(ws, "A5:O5", f"3. FECHA PRESENTACIÓN : {req.fecha_solicitud.strftime('%d/%m/%Y')}", fuente=NEG)

    _rango(ws, "A6:A9", "4. ITEM", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "B6:D9", "5. DESCRIPCIÓN", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "E6:E9", "6. CANT.", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "F6:F9", "7. UNIDAD", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "G6:L6", "8. PROVEEDORES", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "M6:N7", "9. PROVEEDOR ELEGIDO\nVALORES SELECCIONADOS", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "O6:O9", "OBSERVACIONES", fuente=NEG, alin=CENTRO, relleno=CAB)
    for n, (c1, c2) in enumerate((("G", "H"), ("I", "J"), ("K", "L"))):
        _rango(ws, f"{c1}7:{c2}7", f"Cotización {n + 1}", fuente=NEG, alin=CENTRO, relleno=CAB)
        _rango(ws, f"{c1}8:{c2}8", tiendas[n], fuente=NEG, alin=CENTRO, relleno=CAB)
        _celda(ws, f"{c1}9", "V/R UNITARIO", fuente=NEG, alin=CENTRO, relleno=CAB)
        _celda(ws, f"{c2}9", "V/R TOTAL", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "M8:N8", "Nombre del Proveedor", fuente=NEG, alin=CENTRO, relleno=CAB)
    _celda(ws, "M9", "V/R UNITARIO", fuente=NEG, alin=CENTRO, relleno=CAB)
    _celda(ws, "N9", "V/R TOTAL", fuente=NEG, alin=CENTRO, relleno=CAB)

    fila = 10
    for n, f in enumerate(filas, start=1):
        item = f["item"]
        _celda(ws, f"A{fila}", n, alin=CENTRO)
        _rango(ws, f"B{fila}:D{fila}", item.descripcion)
        _celda(ws, f"E{fila}", item.cantidad, alin=CENTRO)
        _celda(ws, f"F{fila}", item.unidad, alin=CENTRO)
        for c1, c2, tienda in zip(("G", "I", "K"), ("H", "J", "L"), tiendas):
            o = next((x for x in f["ofertas"] if x["tienda"] == tienda), None) if tienda else None
            if o and o.get("precio_unitario"):
                _celda(ws, f"{c1}{fila}", o["precio_unitario"], formato=MONEDA)
                _celda(ws, f"{c2}{fila}", f"=E{fila}*{c1}{fila}", formato=MONEDA)
            else:
                _celda(ws, f"{c1}{fila}", None)
                _celda(ws, f"{c2}{fila}", None)
        sel = f["seleccion"]
        if sel:
            _celda(ws, f"M{fila}", sel.get("precio_unitario") or sel.get("precio"), formato=MONEDA)
            _celda(ws, f"N{fila}", f"=E{fila}*M{fila}", formato=MONEDA)
            obs = f"{sel.get('tienda')}: {sel.get('titulo', '')[:90]}"
            if sel.get("unidades_paquete", 1) != 1:
                obs += f" (presentación x{sel['unidades_paquete']:g})"
            _celda(ws, f"O{fila}", obs)
        else:
            _celda(ws, f"M{fila}", None)
            _celda(ws, f"N{fila}", 0, formato=MONEDA)
            _celda(ws, f"O{fila}", "Sin selección")
        ws.row_dimensions[fila].height = 30
        fila += 1

    ultima = fila - 1
    _rango(ws, f"A{fila}:F{fila}", "TOTAL", fuente=NEG, alin=CENTRO, relleno=GRIS)
    for col in ("H", "J", "L", "N"):
        _celda(ws, f"{col}{fila}", f"=SUM({col}10:{col}{ultima})", fuente=NEG, formato=MONEDA, relleno=GRIS)
    for col in ("G", "I", "K", "M", "O"):
        _celda(ws, f"{col}{fila}", None, relleno=GRIS)
    fila += 1
    _rango(ws, f"A{fila}:F{fila}", "IVA O INC", fuente=NEG, alin=CENTRO)
    _rango(ws, f"G{fila}:O{fila}", "Precios de tienda con IVA incluido", alin=CENTRO)
    fila += 2
    for etiqueta, valor in (("10. FECHA DE COTIZACIÓN", req.fecha_solicitud.strftime("%d/%m/%Y")),
                            ("11. VIGENCIA DE LA COTIZACIÓN", "Precio de tienda verificado; sujeto a cambios"),
                            ("12. FORMA DE PAGO", "Según orden de compra"),
                            ("13. PLAZO DE ENTREGA", "Según tienda / proveedor"),
                            ("14. GARANTÍAS ESTABLECIDAS", "Las de la tienda / fabricante")):
        _rango(ws, f"A{fila}:F{fila}", etiqueta, fuente=NEG)
        _rango(ws, f"G{fila}:O{fila}", valor)
        fila += 1
    fila += 4
    for col_ini, col_fin, cargo, nombre in (("B", "F", "Director", firmas.get("director", "")),
                                            ("H", "J", "Profesional Financiero", firmas.get("profesional_financiero", "")),
                                            ("L", "N", "Aprobó", firmas.get("aprobo", ""))):
        _rango(ws, f"{col_ini}{fila}:{col_fin}{fila}", cargo, fuente=NEG, alin=CENTRO, borde=False)
        ws[f"{col_ini}{fila}"].border = Border(top=Side(style="thin"))
        _rango(ws, f"{col_ini}{fila + 1}:{col_fin}{fila + 1}", nombre, alin=CENTRO, borde=False)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    return _a_bytes(wb)


# ---------------------------------------------------------------------------
def formato_requerimiento(req: Requerimiento, empresa: dict) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "REQUERIMIENTO UPARSISTEM SAS"
    for col, w in {"A": 12, "B": 30, "C": 30, "D": 30, "E": 38}.items():
        ws.column_dimensions[col].width = w
    _rango(ws, "A1:E2", f"FORMATO DE REQUERIMIENTO - {empresa['nombre']}   ({req.consecutivo})",
           fuente=Font(bold=True, name="Arial", size=12), alin=CENTRO)
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 30
    _logo(ws, "A1", 54)
    _rango(ws, "A3:E3", "1. ESPACIO EXCLUSIVO PARA DILIGENCIAR EL REQUERIMIENTO", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "A4:B4", "Nombre y Cargo del solicitante", fuente=NEG)
    _celda(ws, "C4", req.nombre_cargo)
    _celda(ws, "D4", f"Fecha de solicitud: {req.fecha_solicitud.strftime('%d/%m/%Y')}", fuente=NEG)
    _celda(ws, "E4", f"Área: {req.area}")
    _rango(ws, "A5:B5", "Destino de la compra:", fuente=NEG)
    _celda(ws, "C5", req.destino)
    fecha_req = req.fecha_requerida.strftime("%d/%m/%Y") if req.fecha_requerida else ""
    _celda(ws, "D5", f"Fecha en que lo requiere: {fecha_req}", fuente=NEG)
    _celda(ws, "E5", f"Tipo: {req.tipo}")
    _rango(ws, "A6:A7", "# Cant. Elementos", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "B6:B7", "Programa / proceso / laboratorio", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "C6:D7", "Descripción Del Insumo / Elemento Requerido", fuente=NEG, alin=CENTRO, relleno=CAB)
    _rango(ws, "E6:E7", "Imagen de referencia del elemento - Observaciones", fuente=NEG, alin=CENTRO, relleno=CAB)
    fila = 8
    for i in req.items:
        _celda(ws, f"A{fila}", f"{i.cantidad:g} {i.unidad}", alin=CENTRO)
        _celda(ws, f"B{fila}", i.programa)
        desc = i.descripcion + (f"\n{i.especificaciones}" if i.especificaciones else "")
        if i.marca_preferida:
            desc += f"\nMarca preferida: {i.marca_preferida}" + ("" if i.acepta_equivalentes else " (sin equivalentes)")
        _rango(ws, f"C{fila}:D{fila}", desc)
        _celda(ws, f"E{fila}", (i.observaciones or "") + (" [con imagen adjunta en el sistema]" if i.imagen else ""))
        ws.row_dimensions[fila].height = max(30, 15 * (desc.count("\n") + 1))
        fila += 1
    for _ in range(max(0, 11 - len(req.items))):
        for col in "ABE":
            _celda(ws, f"{col}{fila}", "")
        _rango(ws, f"C{fila}:D{fila}", "")
        fila += 1
    _rango(ws, f"A{fila}:E{fila}", "Nota. Agregar las casillas que considere necesarias, recuerde que este documento "
                                   f"debe ser enviado al siguiente correo electrónico: {empresa.get('correo_inventario', '')}",
           fuente=Font(italic=True, name="Arial", size=8))
    if req.justificacion:
        fila += 1
        _rango(ws, f"A{fila}:E{fila}", f"Justificación: {req.justificacion}")
    return _a_bytes(wb)


def _col(n: int) -> str:
    return get_column_letter(n)
