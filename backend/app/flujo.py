"""Reglas del proceso de compra (flujograma "V2 Proceso de compra e inventario").

    Solicitante crea el requerimiento (formato UPARSISTEM)
      -> [opcional] Verificador del area aprueba la solicitud
      -> El agente hace el estudio de mercado (segundo plano) y avisa
      -> Compras revisa, elige opciones o pide re-cotizar, y genera las ordenes
         (una por proveedor), re-verificando cada precio en la tienda
      -> Aprobador financiero aprueba o rechaza el pago de cada orden
         (si el precio verificado es viejo, se vuelve a comprobar)
      -> Al aprobarse, se genera la factura de la orden
      -> Tesoreria registra el pago; se registra la recepcion -> cierre

Todas las transiciones dejan rastro en la bitacora de auditoria.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from agente_compras.mercado.estudio import verificar_oferta
from agente_compras.mercado.modelos import Oferta

from . import servicios
from .calculos import recalcular
from .modelos import (
    CotizacionManual, EstudioMercado, Factura, ItemRequerimiento, LineaOrden, OrdenCompra, Proveedor,
    Requerimiento, Usuario,
)
from .trabajador import VERIFICADOR

# Razon social de las tiendas del catalogo, para asociarlas al proveedor
# registrado. El NIT NO se asume: se toma del listado de proveedores o lo
# completa compras.
RAZON_SOCIAL = {
    "exito": "ALMACENES EXITO", "carulla": "ALMACENES EXITO",
    "easy": "CENCOSUD COLOMBIA", "jumbo": "CENCOSUD COLOMBIA", "metro": "CENCOSUD COLOMBIA",
    "olimpica": "SUPERTIENDAS Y DROGUERIAS OLIMPICA", "panamericana": "PANAMERICANA LIBRERIA Y PAPELERIA",
    "alkosto": "COLOMBIANA DE COMERCIO", "ktronix": "COLOMBIANA DE COMERCIO",
    "alkomprar": "COLOMBIANA DE COMERCIO", "falabella": "FALABELLA DE COLOMBIA",
    "homecenter": "SODIMAC COLOMBIA",
}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _enlace(req: Requerimiento) -> str:
    return f"/requerimientos/{req.id}"


def exigir_estado(obj, *estados: str) -> None:
    if obj.estado not in estados:
        raise HTTPException(409, f"La acción no aplica en el estado actual ({obj.estado})")


# ---------------------------------------------------------------------------
# Requerimiento
# ---------------------------------------------------------------------------
def enviar(db: Session, req: Requerimiento, usuario: Usuario) -> None:
    exigir_estado(req, "borrador", "rechazado")
    if not [i for i in req.items if i.descripcion.strip()]:
        raise HTTPException(400, "El requerimiento no tiene ítems")
    servicios.registrar(db, "requerimiento", req.id, usuario, "enviado")
    if servicios.config(db, "flujo").get("verificacion_area"):
        req.estado = "pendiente_verificacion"
        servicios.notificar(db, servicios.usuarios_con_rol(db, "verificador"),
                            f"Requerimiento por verificar: {req.consecutivo}",
                            f"{req.nombre_cargo} solicita {len(req.items)} ítem(s) para {req.area or req.destino}.",
                            _enlace(req), excluir=usuario)
    else:
        iniciar_estudio(db, req, usuario)


def verificar(db: Session, req: Requerimiento, usuario: Usuario, aprobado: bool, motivo: str) -> None:
    exigir_estado(req, "pendiente_verificacion")
    req.verificado_por_id = usuario.id
    if aprobado:
        servicios.registrar(db, "requerimiento", req.id, usuario, "verificado", motivo)
        iniciar_estudio(db, req, usuario)
    else:
        if not motivo.strip():
            raise HTTPException(400, "Indique el motivo del rechazo")
        req.estado = "rechazado"
        req.motivo_rechazo = motivo
        servicios.registrar(db, "requerimiento", req.id, usuario, "rechazado", motivo)
        servicios.notificar(db, [req.solicitante], f"Requerimiento rechazado: {req.consecutivo}",
                            motivo, _enlace(req), tipo="error")


def iniciar_estudio(db: Session, req: Requerimiento, usuario: Usuario | None,
                    instrucciones: str = "", items_ids: list[int] | None = None) -> EstudioMercado:
    if any(e.estado in ("en_cola", "en_proceso") for e in req.estudios):
        raise HTTPException(409, "Ya hay un estudio de mercado en curso para este requerimiento")
    e = EstudioMercado(requerimiento=req, version=len(req.estudios) + 1, instrucciones=instrucciones,
                       items_ids=items_ids or [], solicitado_por_id=usuario.id if usuario else None)
    db.add(e)
    req.estado = "en_estudio"
    servicios.registrar(db, "requerimiento", req.id, usuario, "estudio_solicitado",
                        f"v{e.version}" + (f" - {instrucciones}" if instrucciones else ""))
    return e


def cancelar(db: Session, req: Requerimiento, usuario: Usuario, motivo: str) -> None:
    if req.estado in ("cerrado", "cancelado"):
        raise HTTPException(409, "El requerimiento ya está cerrado")
    if any(o.estado in ("aprobada", "pagada", "recibida") for o in req.ordenes):
        raise HTTPException(409, "Tiene órdenes aprobadas o pagadas; anúlelas primero")
    for o in req.ordenes:
        if o.estado == "pendiente_aprobacion":
            o.estado = "anulada"
    for e in req.estudios:
        if e.estado in ("en_cola",):
            e.estado = "cancelado"
    req.estado = "cancelado"
    req.motivo_rechazo = motivo
    servicios.registrar(db, "requerimiento", req.id, usuario, "cancelado", motivo)
    servicios.notificar(db, [req.solicitante], f"Requerimiento cancelado: {req.consecutivo}", motivo,
                        _enlace(req), excluir=usuario)


# ---------------------------------------------------------------------------
# Opciones por item (estudio + cotizaciones manuales)
# ---------------------------------------------------------------------------
def estudio_vigente(req: Requerimiento) -> EstudioMercado | None:
    listos = [e for e in req.estudios if e.estado == "listo" or (e.estado == "error" and e.resultado)]
    return listos[-1] if listos else None


def oferta_de_cotizacion(c: CotizacionManual, item: ItemRequerimiento) -> Oferta:
    import math

    unidades = c.unidades_paquete or 1
    paquetes = math.ceil(max(item.cantidad, 1) / unidades - 1e-9)
    o = Oferta(
        id=f"manual-{c.id}", fuente="manual", tienda=c.proveedor_nombre,
        titulo=c.descripcion or item.descripcion, precio=c.precio_unitario, metodo="manual",
        relevancia="exacto", unidades_paquete=unidades, precio_unitario=c.precio_unitario / unidades,
        paquetes_necesarios=paquetes, costo_total=paquetes * c.precio_unitario,
        vendedor=c.proveedor_nombre, disponible=True,
        notas=[x for x in [f"Vigencia: {c.vigencia}" if c.vigencia else "",
                           f"Entrega: {c.plazo_entrega}" if c.plazo_entrega else "",
                           f"Pago: {c.forma_pago}" if c.forma_pago else "",
                           f"Garantía: {c.garantia}" if c.garantia else "",
                           "No incluye IVA" if not c.incluye_iva else "", c.observaciones] if x],
    )
    from agente_compras.mercado.modelos import Verificacion

    o.verificacion = Verificacion(ok=True, precio_pagina=c.precio_unitario, metodo="cotizacion formal",
                                  detalle="Cotización formal del proveedor")
    return o


def ofertas_item(db: Session, req: Requerimiento, item: ItemRequerimiento) -> list[Oferta]:
    salida: list[Oferta] = []
    e = estudio_vigente(req)
    datos = (e.resultado or {}).get(str(item.id)) if e else None
    if datos and "ofertas" in datos:
        salida += [Oferta.model_validate(o) for o in datos["ofertas"]]
    for c in db.scalars(select(CotizacionManual).where(CotizacionManual.item_id == item.id)):
        salida.append(oferta_de_cotizacion(c, item))
    return salida


def seleccionar(db: Session, req: Requerimiento, item: ItemRequerimiento, oferta_id: str | None,
                usuario: Usuario) -> None:
    exigir_estado(req, "estudio_listo")
    if oferta_id is None:
        item.seleccion = None
        return
    oferta = next((o for o in ofertas_item(db, req, item) if o.id == oferta_id), None)
    if oferta is None:
        raise HTTPException(404, "La opción no existe en el estudio vigente")
    if oferta.relevancia == "descartado":
        raise HTTPException(400, "Esa opción fue descartada por no corresponder a lo pedido")
    if oferta.metodo == "buscador":
        raise HTTPException(400, "Esa opción no tiene precio verificable. Cárguela como cotización "
                                 "manual si el proveedor la confirma.")
    item.seleccion = oferta.model_dump(mode="json")
    item.excluido = False
    servicios.registrar(db, "requerimiento", req.id, usuario, "opcion_seleccionada",
                        f"Ítem {item.orden + 1}: {oferta.tienda} - {oferta.titulo[:80]} "
                        f"(${oferta.precio:,.0f})".replace(",", "."))


def usar_recomendadas(db: Session, req: Requerimiento, usuario: Usuario) -> int:
    exigir_estado(req, "estudio_listo")
    e = estudio_vigente(req)
    n = 0
    for item in req.items:
        if item.excluido or item.seleccion:
            continue
        datos = (e.resultado or {}).get(str(item.id)) if e else None
        rec = (datos or {}).get("recomendada_id")
        if rec:
            seleccionar(db, req, item, rec, usuario)
            n += 1
    return n


# ---------------------------------------------------------------------------
# Ordenes de compra
# ---------------------------------------------------------------------------
def _normal(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9 ]", " ", t)


def buscar_proveedor(db: Session, tienda: str, fuente: str) -> Proveedor | None:
    objetivo = _normal(RAZON_SOCIAL.get(fuente, tienda)).strip()
    if len(objetivo) < 4:
        return None
    for p in db.scalars(select(Proveedor).where(Proveedor.activo.is_(True))):
        if objetivo in _normal(p.nombre):
            return p
    return None


def _verificar_seleccion(item: ItemRequerimiento) -> dict:
    """Corre en el hilo verificador. Devuelve un informe por item."""
    sel = item.seleccion or {}
    o = Oferta.model_validate(sel)
    precio_antes = o.precio
    v = verificar_oferta(o, int(o.paquetes_necesarios or 1))
    return {"item_id": item.id, "oferta": o.model_dump(mode="json"), "ok": v.ok,
            "precio_antes": precio_antes, "precio_ahora": o.precio, "detalle": v.detalle,
            "cambio": bool(precio_antes and o.precio and abs(o.precio - precio_antes) > 0.5),
            "agotado": o.disponible is False or "cantidad insuficiente" in v.detalle.lower()}


def verificar_selecciones(items: list[ItemRequerimiento]) -> list[dict]:
    a_verificar = [i for i in items if (i.seleccion or {}).get("metodo") != "manual"]
    futuros = [VERIFICADOR.submit(_verificar_seleccion, i) for i in a_verificar]
    informes = [f.result(timeout=240) for f in futuros]
    for i in items:
        if (i.seleccion or {}).get("metodo") == "manual":
            informes.append({"item_id": i.id, "oferta": i.seleccion, "ok": True, "cambio": False,
                             "agotado": False, "precio_antes": i.seleccion.get("precio"),
                             "precio_ahora": i.seleccion.get("precio"),
                             "detalle": "Cotización formal del proveedor"})
    return informes


def generar_ordenes(db: Session, req: Requerimiento, usuario: Usuario, *, forma_pago: str,
                    observaciones: str, confirmar_cambios: bool) -> dict:
    exigir_estado(req, "estudio_listo")
    items = [i for i in req.items if not i.excluido]
    sin_eleccion = [i for i in items if not i.seleccion]
    if sin_eleccion:
        raise HTTPException(400, "Faltan ítems por elegir: " + ", ".join(
            str(i.orden + 1) for i in sin_eleccion) + ". Elija una opción o exclúyalos.")
    if not items:
        raise HTTPException(400, "No hay ítems para comprar")

    # Re-verificacion en tienda justo antes de comprometer el dinero.
    informes = verificar_selecciones(items)
    por_item = {inf["item_id"]: inf for inf in informes}
    cambios = [inf for inf in informes if inf["cambio"] or inf["agotado"] or not inf["ok"]]
    for i in items:
        inf = por_item[i.id]
        i.seleccion = inf["oferta"]
    if cambios and not confirmar_cambios:
        db.commit()
        raise HTTPException(409, detail={
            "mensaje": "Algunos precios cambiaron o no se pudieron confirmar en la tienda. "
                       "Revise y confirme para generar las órdenes con los precios actualizados.",
            "cambios": [{"item_id": c["item_id"], "precio_antes": c["precio_antes"],
                         "precio_ahora": c["precio_ahora"], "detalle": c["detalle"],
                         "agotado": c["agotado"]} for c in cambios],
        })
    agotados = [c for c in cambios if c["agotado"]]
    if agotados:
        raise HTTPException(409, detail={
            "mensaje": "Hay opciones agotadas o sin cantidad suficiente en la tienda. Elija otra opción "
                       "para esos ítems (o una cotización de proveedor).",
            "cambios": [{"item_id": c["item_id"], "detalle": c["detalle"], "agotado": True} for c in agotados]})

    imp = servicios.config(db, "impuestos")
    grupos: dict[str, list[ItemRequerimiento]] = {}
    for i in items:
        sel = i.seleccion
        clave = f"{sel.get('fuente')}|{sel.get('tienda')}"
        grupos.setdefault(clave, []).append(i)

    creadas: list[OrdenCompra] = []
    for clave, grupo in grupos.items():
        sel0 = grupo[0].seleccion
        fuente = sel0.get("fuente", "")
        proveedor = None
        if fuente == "manual":
            c = db.get(CotizacionManual, int(str(sel0["id"]).split("-")[1]))
            proveedor = db.get(Proveedor, c.proveedor_id) if c and c.proveedor_id else None
        else:
            proveedor = buscar_proveedor(db, sel0.get("tienda", ""), fuente)
        oc = OrdenCompra(
            numero=servicios.siguiente_consecutivo(db, "orden"),
            requerimiento=req,
            proveedor_id=proveedor.id if proveedor else None,
            proveedor_nombre=proveedor.nombre if proveedor else (RAZON_SOCIAL.get(fuente) or sel0.get("tienda")),
            proveedor_nit=proveedor.nit_completo if proveedor else "",
            proveedor_contacto=" · ".join(x for x in [
                proveedor.direccion if proveedor else "", proveedor.ciudad if proveedor else "",
                proveedor.telefono if proveedor else "", proveedor.email if proveedor else "",
                sel0.get("dominio", "") if fuente != "manual" else ""] if x),
            canal="proveedor_directo" if fuente == "manual" else "tienda_en_linea",
            forma_pago=forma_pago, observaciones=observaciones or req.destino or "",
            retefuente_pct=imp["retefuente_pct"], reteica_x_mil=imp["reteica_x_mil"],
            creada_por_id=usuario.id, verificada_en=_ahora(),
            verificacion={"informes": [por_item[i.id] | {"oferta": None} for i in grupo],
                          "momento": _ahora().isoformat()},
        )
        for n, i in enumerate(grupo):
            sel = i.seleccion
            paquetes = sel.get("paquetes_necesarios") or i.cantidad
            unidades = sel.get("unidades_paquete") or 1
            desc = i.descripcion.upper()
            if unidades and unidades != 1:
                desc += f" (PRESENTACIÓN X{unidades:g})"
            oc.lineas.append(LineaOrden(
                item_id=i.id, posicion=n, descripcion=desc[:500], cantidad=float(paquetes),
                vr_unitario=float(sel["precio"]), iva_pct=imp["iva_pct"], rete_pct=imp["retefuente_pct"],
                url_fuente=sel.get("url", ""), oferta=sel,
            ))
        recalcular(oc, imp.get("base_minima_retencion", 0))
        db.add(oc)
        creadas.append(oc)

    req.estado = "en_aprobacion"
    db.flush()
    resumen = ", ".join(f"{o.numero} ({o.proveedor_nombre}: ${o.total_pagar:,.0f})" for o in creadas)
    servicios.registrar(db, "requerimiento", req.id, usuario, "ordenes_generadas", resumen.replace(",", "."))
    for o in creadas:
        servicios.registrar(db, "orden", o.id, usuario, "creada", f"{len(o.lineas)} línea(s)")
    servicios.notificar(db, servicios.usuarios_con_rol(db, "aprobador"),
                        f"Órdenes por aprobar: {req.consecutivo}",
                        f"Compras generó {len(creadas)} orden(es) por un total de "
                        f"${sum(o.total_pagar for o in creadas):,.0f}.".replace(",", "."),
                        "/ordenes?estado=pendiente_aprobacion", excluir=usuario)
    servicios.notificar(db, [req.solicitante], f"Su requerimiento {req.consecutivo} pasó a aprobación de pago",
                        "", _enlace(req), excluir=usuario)
    return {"ordenes": [o.id for o in creadas], "cambios_confirmados": len(cambios)}


def reverificar_orden(db: Session, oc: OrdenCompra, usuario: Usuario | None) -> dict:
    items = []
    for l in oc.lineas:
        if l.oferta and l.oferta.get("metodo") != "manual":
            tmp = ItemRequerimiento(id=l.id, descripcion=l.descripcion, seleccion=dict(l.oferta))
            items.append(tmp)
    informes = verificar_selecciones(items) if items else []
    tolerancia = float(servicios.config(db, "flujo").get("tolerancia_precio_pct", 0.5)) / 100
    cambio = False
    for inf in informes:
        linea = next(l for l in oc.lineas if l.id == inf["item_id"])
        ahora = inf["precio_ahora"]
        if inf["agotado"] or (ahora and abs(ahora - linea.vr_unitario) / linea.vr_unitario > tolerancia):
            cambio = True
        inf["linea"] = linea.posicion + 1
        inf["precio_orden"] = linea.vr_unitario
        inf.pop("oferta", None)
    oc.verificacion = {"informes": informes, "momento": _ahora().isoformat()}
    oc.verificada_en = _ahora()
    oc.precios_cambiaron = cambio
    servicios.registrar(db, "orden", oc.id, usuario, "precios_reverificados",
                        "Cambios detectados" if cambio else "Sin cambios")
    return oc.verificacion | {"precios_cambiaron": cambio}


def aprobar_orden(db: Session, oc: OrdenCompra, usuario: Usuario) -> Factura:
    exigir_estado(oc, "pendiente_aprobacion")
    if not (oc.proveedor_nit or "").strip():
        raise HTTPException(409, "La orden no tiene NIT del proveedor. Compras debe completarlo (Ajustar) "
                                 "antes de aprobar el pago.")
    horas = float(servicios.config(db, "flujo").get("horas_validez_precio", 24))
    vencida = not oc.verificada_en or (_ahora() - _aware(oc.verificada_en)) > timedelta(hours=horas)
    if oc.canal == "tienda_en_linea" and (vencida or oc.precios_cambiaron):
        rep = reverificar_orden(db, oc, usuario)
        if rep["precios_cambiaron"]:
            db.commit()
            raise HTTPException(409, detail={
                "mensaje": "Los precios de la tienda cambiaron desde que se generó la orden. "
                           "Rechace la orden para que compras la ajuste.",
                "informes": rep["informes"]})
    oc.estado = "aprobada"
    oc.aprobada_por_id = usuario.id
    oc.aprobada_en = _ahora()
    factura = Factura(numero=servicios.siguiente_consecutivo(db, "factura"), orden=oc,
                      total_pagar=oc.total_pagar)
    db.add(factura)
    req = oc.requerimiento
    activas = [o for o in req.ordenes if o.estado not in ("anulada", "rechazada")]
    if all(o.estado in ("aprobada", "pagada", "recibida") for o in activas):
        req.estado = "aprobado"
    db.flush()
    servicios.registrar(db, "orden", oc.id, usuario, "aprobada", f"Factura {factura.numero}")
    servicios.registrar(db, "requerimiento", req.id, usuario, "orden_aprobada", oc.numero)
    destinatarios = servicios.usuarios_con_rol(db, "tesoreria") + servicios.usuarios_con_rol(db, "compras") + [req.solicitante]
    servicios.notificar(db, destinatarios, f"Orden {oc.numero} aprobada",
                        f"Pago aprobado por ${oc.total_pagar:,.0f} a {oc.proveedor_nombre}. "
                        f"Factura {factura.numero} generada.".replace(",", "."),
                        f"/ordenes/{oc.id}", tipo="exito", excluir=usuario)
    return factura


def rechazar_orden(db: Session, oc: OrdenCompra, usuario: Usuario, motivo: str) -> None:
    exigir_estado(oc, "pendiente_aprobacion")
    if not motivo.strip():
        raise HTTPException(400, "Indique el motivo del rechazo")
    oc.estado = "rechazada"
    oc.motivo_rechazo = motivo
    req = oc.requerimiento
    # "Generar otra cotizacion que se ajuste a lo indicado": vuelve a compras.
    if req.estado in ("en_aprobacion", "aprobado"):
        req.estado = "estudio_listo"
    servicios.registrar(db, "orden", oc.id, usuario, "rechazada", motivo)
    servicios.registrar(db, "requerimiento", req.id, usuario, "orden_rechazada", f"{oc.numero}: {motivo}")
    servicios.notificar(db, servicios.usuarios_con_rol(db, "compras"), f"Orden {oc.numero} rechazada",
                        f"Motivo: {motivo}. Ajuste la cotización y genere una nueva orden.",
                        _enlace(req), tipo="error", excluir=usuario)


def anular_orden(db: Session, oc: OrdenCompra, usuario: Usuario, motivo: str) -> None:
    if oc.estado in ("pagada", "recibida", "anulada"):
        raise HTTPException(409, "No se puede anular una orden pagada, recibida o ya anulada")
    oc.estado = "anulada"
    oc.motivo_rechazo = motivo
    for f in oc.facturas:
        f.estado = "anulada"
    req = oc.requerimiento
    if req.estado in ("en_aprobacion", "aprobado") and not any(
            o.estado in ("pendiente_aprobacion", "aprobada", "pagada", "recibida") for o in req.ordenes if o.id != oc.id):
        req.estado = "estudio_listo"
    servicios.registrar(db, "orden", oc.id, usuario, "anulada", motivo)


def registrar_pago(db: Session, oc: OrdenCompra, usuario: Usuario, referencia: str, soporte: str) -> None:
    exigir_estado(oc, "aprobada")
    oc.estado = "pagada"
    oc.pagada_por_id = usuario.id
    oc.pagada_en = _ahora()
    oc.referencia_pago = referencia
    if soporte:
        oc.soporte_pago = soporte
    for f in oc.facturas:
        if f.estado == "pendiente_pago":
            f.estado = "pagada"
    servicios.registrar(db, "orden", oc.id, usuario, "pagada", referencia)
    servicios.notificar(db, servicios.usuarios_con_rol(db, "compras") + [oc.requerimiento.solicitante],
                        f"Orden {oc.numero} pagada", f"Referencia: {referencia}", f"/ordenes/{oc.id}",
                        excluir=usuario)


def registrar_recepcion(db: Session, oc: OrdenCompra, usuario: Usuario, cumple: bool, notas: str) -> None:
    exigir_estado(oc, "aprobada", "pagada", "devolucion")
    oc.recibida_por_id = usuario.id
    oc.recibida_en = _ahora()
    oc.notas_recepcion = notas
    req = oc.requerimiento
    if cumple:
        oc.estado = "recibida"
        servicios.registrar(db, "orden", oc.id, usuario, "recibida", notas)
        activas = [o for o in req.ordenes if o.estado not in ("anulada", "rechazada")]
        if activas and all(o.estado == "recibida" for o in activas):
            req.estado = "cerrado"
            servicios.registrar(db, "requerimiento", req.id, usuario, "cerrado")
        servicios.notificar(db, [req.solicitante] + servicios.usuarios_con_rol(db, "compras"),
                            f"Pedido recibido: {oc.numero}", notas or "Recibido a satisfacción.",
                            _enlace(req), tipo="exito", excluir=usuario)
    else:
        # "Inicio de devolucion, informar a contabilidad, gerencia y quien cotizo"
        oc.estado = "devolucion"
        servicios.registrar(db, "orden", oc.id, usuario, "devolucion", notas)
        servicios.notificar(db, servicios.usuarios_con_rol(db, "compras") + servicios.usuarios_con_rol(db, "aprobador")
                            + servicios.usuarios_con_rol(db, "tesoreria"),
                            f"Devolución iniciada: {oc.numero}", notas, f"/ordenes/{oc.id}",
                            tipo="error", excluir=usuario)


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
