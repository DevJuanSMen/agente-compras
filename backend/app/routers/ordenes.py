"""Ordenes de compra y facturas."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import flujo, servicios
from ..bd import obtener_sesion
from ..calculos import recalcular
from ..documentos import pdf
from ..modelos import Factura, OrdenCompra, Proveedor, Usuario
from ..seguridad import requiere, usuario_actual
from ..vistas import factura_dict, oc_detalle, oc_resumen
from .requerimientos import EXT_DOC, _archivo, _usuario_descarga, guardar_archivo

router = APIRouter(prefix="/api", tags=["ordenes"])

ROLES_OC = ("compras", "aprobador", "tesoreria")


def _oc(db: Session, u: Usuario, oid: int) -> OrdenCompra:
    o = db.get(OrdenCompra, oid)
    if not o:
        raise HTTPException(404, "Orden no encontrada")
    if not (u.tiene(*ROLES_OC) or o.requerimiento.solicitante_id == u.id):
        raise HTTPException(404, "Orden no encontrada")
    return o


@router.get("/ordenes")
def listar(estado: str = "", u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    q = select(OrdenCompra).order_by(OrdenCompra.creada_en.desc())
    if estado:
        q = q.where(OrdenCompra.estado.in_(estado.split(",")))
    ordenes = db.scalars(q.limit(500)).all()
    if not u.tiene(*ROLES_OC):
        ordenes = [o for o in ordenes if o.requerimiento.solicitante_id == u.id]
    return [oc_resumen(o) for o in ordenes]


@router.get("/ordenes/{oid}")
def detalle(oid: int, u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    return oc_detalle(db, u, _oc(db, u, oid))


class LineaEdicion(BaseModel):
    id: int
    descuento: float = Field(ge=0, default=0)
    iva_pct: float = Field(ge=0, le=100, default=0)
    rete_pct: float = Field(ge=0, le=100, default=0)


class EdicionOrden(BaseModel):
    proveedor_id: Optional[int] = None
    proveedor_nombre: str = ""
    proveedor_nit: str = ""
    forma_pago: str = "contado"
    observaciones: str = ""
    retefuente_pct: float = Field(ge=0, le=100, default=2.5)
    reteica_x_mil: float = Field(ge=0, le=100, default=10)
    lineas: list[LineaEdicion] = []


@router.put("/ordenes/{oid}")
def editar(oid: int, datos: EdicionOrden, u: Usuario = Depends(requiere("compras")),
           db: Session = Depends(obtener_sesion)):
    """Compras ajusta proveedor, retenciones y descuentos antes de la aprobacion.
    El precio unitario NO se edita a mano: sale de la tienda verificada."""
    o = _oc(db, u, oid)
    flujo.exigir_estado(o, "pendiente_aprobacion")
    if datos.proveedor_id:
        p = db.get(Proveedor, datos.proveedor_id)
        if not p:
            raise HTTPException(404, "Proveedor no encontrado")
        o.proveedor_id, o.proveedor_nombre, o.proveedor_nit = p.id, p.nombre, p.nit_completo
        o.proveedor_contacto = " · ".join(x for x in [p.direccion, p.ciudad, p.telefono, p.email] if x)
    else:
        if datos.proveedor_nombre.strip():
            o.proveedor_nombre = datos.proveedor_nombre.strip()
        o.proveedor_nit = datos.proveedor_nit.strip()
    if datos.forma_pago not in ("contado", "credito"):
        raise HTTPException(400, "Forma de pago inválida")
    o.forma_pago, o.observaciones = datos.forma_pago, datos.observaciones
    o.retefuente_pct, o.reteica_x_mil = datos.retefuente_pct, datos.reteica_x_mil
    por_id = {l.id: l for l in datos.lineas}
    for l in o.lineas:
        if l.id in por_id:
            e = por_id[l.id]
            if e.descuento > l.cantidad * l.vr_unitario:
                raise HTTPException(400, f"El descuento de la línea {l.posicion + 1} supera su valor")
            l.descuento, l.iva_pct, l.rete_pct = e.descuento, e.iva_pct, e.rete_pct
        elif not datos.lineas:
            l.rete_pct = datos.retefuente_pct
    recalcular(o, servicios.config(db, "impuestos").get("base_minima_retencion", 0))
    servicios.registrar(db, "orden", o.id, u, "editada", f"Total ${o.total_pagar:,.0f}".replace(",", "."))
    db.commit()
    return oc_detalle(db, u, o)


@router.post("/ordenes/{oid}/reverificar")
def reverificar(oid: int, u: Usuario = Depends(requiere("compras", "aprobador")), db: Session = Depends(obtener_sesion)):
    o = _oc(db, u, oid)
    r = flujo.reverificar_orden(db, o, u)
    db.commit()
    return r


@router.post("/ordenes/{oid}/aprobar")
def aprobar(oid: int, u: Usuario = Depends(requiere("aprobador")), db: Session = Depends(obtener_sesion)):
    o = _oc(db, u, oid)
    f = flujo.aprobar_orden(db, o, u)
    db.commit()
    return {"orden": oc_detalle(db, u, o), "factura": factura_dict(f)}


class Motivo(BaseModel):
    motivo: str = ""


@router.post("/ordenes/{oid}/rechazar")
def rechazar(oid: int, datos: Motivo, u: Usuario = Depends(requiere("aprobador")), db: Session = Depends(obtener_sesion)):
    o = _oc(db, u, oid)
    flujo.rechazar_orden(db, o, u, datos.motivo)
    db.commit()
    return oc_detalle(db, u, o)


@router.post("/ordenes/{oid}/anular")
def anular(oid: int, datos: Motivo, u: Usuario = Depends(requiere("compras", "aprobador")),
           db: Session = Depends(obtener_sesion)):
    o = _oc(db, u, oid)
    if not datos.motivo.strip():
        raise HTTPException(400, "Indique el motivo de la anulación")
    flujo.anular_orden(db, o, u, datos.motivo)
    db.commit()
    return oc_detalle(db, u, o)


@router.post("/ordenes/{oid}/pago")
def pagar(oid: int, referencia: str = Form(..., min_length=2), soporte: Optional[UploadFile] = File(None),
          u: Usuario = Depends(requiere("tesoreria")), db: Session = Depends(obtener_sesion)):
    o = _oc(db, u, oid)
    ruta = guardar_archivo(soporte, f"oc{o.id}", EXT_DOC) if soporte and soporte.filename else ""
    flujo.registrar_pago(db, o, u, referencia, ruta)
    db.commit()
    return oc_detalle(db, u, o)


class Recepcion(BaseModel):
    cumple: bool
    notas: str = ""


@router.post("/ordenes/{oid}/recepcion")
def recepcion(oid: int, datos: Recepcion, u: Usuario = Depends(requiere("tesoreria", "compras")),
              db: Session = Depends(obtener_sesion)):
    o = _oc(db, u, oid)
    if not datos.cumple and not datos.notas.strip():
        raise HTTPException(400, "Describa qué no cumple para iniciar la devolución")
    flujo.registrar_recepcion(db, o, u, datos.cumple, datos.notas)
    db.commit()
    return oc_detalle(db, u, o)


@router.get("/ordenes/{oid}/pdf")
def orden_pdf(oid: int, token: str = Query(...), db: Session = Depends(obtener_sesion)):
    u = _usuario_descarga(token, db)
    o = _oc(db, u, oid)
    return _archivo(pdf.pdf_orden(o, servicios.config(db, "empresa")), f"{o.numero}.pdf", "application/pdf")


# --- Facturas ---------------------------------------------------------------
@router.get("/facturas")
def facturas(u: Usuario = Depends(requiere(*ROLES_OC)), db: Session = Depends(obtener_sesion)):
    return [factura_dict(f) for f in db.scalars(select(Factura).order_by(Factura.creada_en.desc()).limit(500))]


@router.post("/facturas/{fid}")
def actualizar_factura(fid: int, numero_proveedor: str = Form(""), archivo: Optional[UploadFile] = File(None),
                       u: Usuario = Depends(requiere("tesoreria", "compras")), db: Session = Depends(obtener_sesion)):
    """Asocia la factura electronica real del proveedor (numero y archivo)."""
    f = db.get(Factura, fid)
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    f.numero_proveedor = numero_proveedor.strip()
    if archivo and archivo.filename:
        f.archivo_proveedor = guardar_archivo(archivo, f"oc{f.orden_id}", EXT_DOC)
    servicios.registrar(db, "orden", f.orden_id, u, "factura_proveedor", f"{f.numero}: {f.numero_proveedor}")
    db.commit()
    return factura_dict(f)


@router.get("/facturas/{fid}/pdf")
def factura_pdf(fid: int, token: str = Query(...), db: Session = Depends(obtener_sesion)):
    u = _usuario_descarga(token, db)
    f = db.get(Factura, fid)
    if not f:
        raise HTTPException(404, "Factura no encontrada")
    _oc(db, u, f.orden_id)
    return _archivo(pdf.pdf_factura(f, servicios.config(db, "empresa")), f"{f.numero}.pdf", "application/pdf")
