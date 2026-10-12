"""Aritmetica de la orden de compra, identica al formato de UPARSISTEM.

Comprobado contra la orden OC-1-3621 del formato entregado:

    linea:  base  = cantidad x vr_unitario - descuento
            total = base + IVA - retencion      (1 x 33.000 con 2,5 % -> 32.175)
    orden:  Total bruto = suma de cantidad x vr_unitario          2.627.200
            Subtotal    = bruto - descuentos                      2.627.200
            Retefuente  = suma de retenciones de linea (2,5 %)       65.680
            ReteICA     = subtotal x tarifa por mil (10)             26.272
            Total a pagar = subtotal + IVA - retefuente - reteICA  2.535.248

Se redondea a pesos en cada paso, como la factura electronica.
"""
from __future__ import annotations

from .modelos import LineaOrden, OrdenCompra


def _r(v: float) -> float:
    return float(round(v + 1e-9, 2))


def calcular_linea(l: LineaOrden) -> None:
    base = l.cantidad * l.vr_unitario - (l.descuento or 0)
    iva = base * (l.iva_pct or 0) / 100
    rete = base * (l.rete_pct or 0) / 100
    l.total = _r(base + iva - rete)


def recalcular(oc: OrdenCompra, base_minima_retencion: float = 0) -> None:
    bruto = sum(l.cantidad * l.vr_unitario for l in oc.lineas)
    # Si la compra no alcanza la base minima, no se practica retencion.
    aplica_retencion = bruto >= (base_minima_retencion or 0)
    for l in oc.lineas:
        if not aplica_retencion:
            l.rete_pct = 0
        calcular_linea(l)
    descuentos = sum(l.descuento or 0 for l in oc.lineas)
    subtotal = bruto - descuentos
    iva = sum((l.cantidad * l.vr_unitario - (l.descuento or 0)) * (l.iva_pct or 0) / 100 for l in oc.lineas)
    retefuente = sum((l.cantidad * l.vr_unitario - (l.descuento or 0)) * (l.rete_pct or 0) / 100
                     for l in oc.lineas)
    reteica = subtotal * (oc.reteica_x_mil or 0) / 1000 if aplica_retencion else 0
    oc.total_bruto = _r(bruto)
    oc.descuentos = _r(descuentos)
    oc.subtotal = _r(subtotal)
    oc.iva_total = _r(iva)
    oc.retefuente = _r(retefuente)
    oc.reteica = _r(reteica)
    oc.total_pagar = _r(subtotal + iva - retefuente - reteica)
