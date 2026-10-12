"""Serializacion para la API y calculo de acciones permitidas por usuario."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import flujo
from .modelos import (
    ESTADOS_OC, ESTADOS_REQ, CotizacionManual, Evento, Factura, OrdenCompra, Requerimiento, Usuario,
)


def usuario_dict(u: Usuario | None) -> dict | None:
    if not u:
        return None
    return {"id": u.id, "nombre": u.nombre, "email": u.email, "cargo": u.cargo, "area": u.area,
            "roles": u.roles or [], "activo": u.activo, "debe_cambiar_clave": u.debe_cambiar_clave,
            "notificar_correo": u.notificar_correo}


def puede_ver(u: Usuario, req: Requerimiento) -> bool:
    return req.solicitante_id == u.id or u.tiene("verificador", "compras", "aprobador", "tesoreria")


def acciones_req(u: Usuario, req: Requerimiento) -> list[str]:
    a: list[str] = []
    dueno = req.solicitante_id == u.id or u.tiene("admin")
    if req.estado in ("borrador", "rechazado") and dueno:
        a += ["editar", "enviar"]
    if req.estado == "pendiente_verificacion" and u.tiene("verificador"):
        a += ["verificar"]
    if u.tiene("compras"):
        if req.estado == "estudio_listo":
            a += ["seleccionar", "reestudiar", "cotizacion_manual", "generar_ordenes"]
        if req.estado in ("en_aprobacion",):
            a += ["cotizacion_manual"]
        if req.estado not in ("cerrado", "cancelado"):
            a += ["cancelar"]
    elif dueno and req.estado in ("borrador", "pendiente_verificacion", "rechazado", "en_estudio", "estudio_listo"):
        a += ["cancelar"]
    return a


def req_resumen(req: Requerimiento) -> dict:
    estudio = req.estudios[-1] if req.estudios else None
    total_oc = sum(o.total_pagar for o in req.ordenes if o.estado not in ("anulada", "rechazada"))
    return {
        "id": req.id, "consecutivo": req.consecutivo, "estado": req.estado,
        "estado_texto": ESTADOS_REQ.get(req.estado, req.estado),
        "solicitante": req.solicitante.nombre if req.solicitante else "", "nombre_cargo": req.nombre_cargo,
        "area": req.area, "destino": req.destino, "tipo": req.tipo, "prioridad": req.prioridad,
        "fecha_solicitud": req.fecha_solicitud.isoformat(),
        "fecha_requerida": req.fecha_requerida.isoformat() if req.fecha_requerida else None,
        "n_items": len(req.items), "creado_en": req.creado_en.isoformat(),
        "actualizado_en": req.actualizado_en.isoformat() if req.actualizado_en else None,
        "estudio": {"estado": estudio.estado, "progreso": estudio.progreso, "paso": estudio.paso,
                    "version": estudio.version} if estudio else None,
        "total_ordenes": total_oc,
    }


def item_dict(i) -> dict:
    return {"id": i.id, "orden": i.orden, "cantidad": i.cantidad, "unidad": i.unidad, "programa": i.programa,
            "descripcion": i.descripcion, "especificaciones": i.especificaciones,
            "marca_preferida": i.marca_preferida, "acepta_equivalentes": i.acepta_equivalentes,
            "observaciones": i.observaciones, "imagen": i.imagen, "seleccion": i.seleccion,
            "excluido": i.excluido}


def eventos(db: Session, entidad: str, entidad_id: int) -> list[dict]:
    filas = db.scalars(select(Evento).where(Evento.entidad == entidad, Evento.entidad_id == entidad_id)
                       .order_by(Evento.creado_en)).all()
    return [{"accion": e.accion, "detalle": e.detalle, "fecha": e.creado_en.isoformat(),
             "usuario": e.usuario.nombre if e.usuario else "Agente"} for e in filas]


def req_detalle(db: Session, u: Usuario, req: Requerimiento) -> dict:
    d = req_resumen(req)
    d.update({
        "justificacion": req.justificacion, "fuentes": req.fuentes or [], "sitios_extra": req.sitios_extra or [],
        "proveedores_sugeridos": req.proveedores_sugeridos or [], "motivo_rechazo": req.motivo_rechazo,
        "solicitante_id": req.solicitante_id,
        "items": [item_dict(i) for i in req.items],
        "estudios": [{"id": e.id, "version": e.version, "estado": e.estado, "progreso": e.progreso,
                      "paso": e.paso, "instrucciones": e.instrucciones, "creado_en": e.creado_en.isoformat(),
                      "terminado_en": e.terminado_en.isoformat() if e.terminado_en else None,
                      "error": e.error[:400] if e.error else ""} for e in req.estudios],
        "ordenes": [oc_resumen(o) for o in req.ordenes],
        "eventos": eventos(db, "requerimiento", req.id),
        "acciones": acciones_req(u, req),
    })
    return d


def estudio_vista(db: Session, req: Requerimiento) -> dict:
    """Estudio vigente + cotizaciones manuales, por item, listo para pintar."""
    ultimo = req.estudios[-1] if req.estudios else None
    vigente = flujo.estudio_vigente(req)
    fuente = ultimo if ultimo and ultimo.estado in ("en_cola", "en_proceso") else vigente
    lineas = []
    for i in req.items:
        datos = ((fuente.resultado if fuente else {}) or {}).get(str(i.id)) or {}
        ofertas = [o.model_dump(mode="json") for o in flujo.ofertas_item(db, req, i)] if vigente else []
        if fuente is not vigente:
            # Estudio en curso: mostrar lo parcial de este estudio sin mezclar.
            ofertas = datos.get("ofertas", [])
            ofertas += [flujo.oferta_de_cotizacion(c, i).model_dump(mode="json") for c in
                        db.scalars(select(CotizacionManual).where(CotizacionManual.item_id == i.id))]
        cotizaciones = [{"id": c.id, "proveedor_nombre": c.proveedor_nombre, "precio_unitario": c.precio_unitario,
                         "archivo": c.archivo} for c in
                        db.scalars(select(CotizacionManual).where(CotizacionManual.item_id == i.id))]
        lineas.append({
            "item": item_dict(i),
            "plan": datos.get("plan"), "resumen": datos.get("resumen", ""),
            "justificacion": datos.get("justificacion", ""), "alertas": datos.get("alertas", []),
            "estadisticas": datos.get("estadisticas", {}), "fuentes": datos.get("fuentes", []),
            "recomendada_id": datos.get("recomendada_id"), "mas_barata_id": datos.get("mas_barata_id"),
            "mejor_calificada_id": datos.get("mejor_calificada_id"), "error": datos.get("error"),
            "generado_en": datos.get("generado_en"), "duracion_s": datos.get("duracion_s"),
            "ofertas": ofertas, "cotizaciones": cotizaciones,
        })
    return {
        "estudio": None if not ultimo else {
            "id": ultimo.id, "version": ultimo.version, "estado": ultimo.estado, "progreso": ultimo.progreso,
            "paso": ultimo.paso, "bitacora": (ultimo.bitacora or [])[-120:], "error": ultimo.error[:600],
            "creado_en": ultimo.creado_en.isoformat(),
            "iniciado_en": ultimo.iniciado_en.isoformat() if ultimo.iniciado_en else None,
            "terminado_en": ultimo.terminado_en.isoformat() if ultimo.terminado_en else None,
            "instrucciones": ultimo.instrucciones, "opciones": ultimo.opciones,
        },
        "vigente_version": vigente.version if vigente else None,
        "lineas": lineas,
    }


def oc_resumen(o: OrdenCompra) -> dict:
    return {"id": o.id, "numero": o.numero, "estado": o.estado, "estado_texto": ESTADOS_OC.get(o.estado, o.estado),
            "proveedor_nombre": o.proveedor_nombre, "proveedor_nit": o.proveedor_nit, "canal": o.canal,
            "fecha": o.fecha.isoformat(), "total_pagar": o.total_pagar, "forma_pago": o.forma_pago,
            "requerimiento_id": o.requerimiento_id,
            "requerimiento": o.requerimiento.consecutivo if o.requerimiento else "",
            "n_lineas": len(o.lineas), "precios_cambiaron": o.precios_cambiaron,
            "verificada_en": o.verificada_en.isoformat() if o.verificada_en else None,
            "creada_en": o.creada_en.isoformat()}


def acciones_oc(u: Usuario, o: OrdenCompra) -> list[str]:
    a = []
    if o.estado == "pendiente_aprobacion":
        if u.tiene("aprobador"):
            a += ["aprobar", "rechazar", "reverificar"]
        if u.tiene("compras"):
            a += ["editar", "anular", "reverificar"]
    if o.estado == "aprobada" and u.tiene("tesoreria"):
        a += ["pagar"]
    if o.estado in ("aprobada", "pagada", "devolucion") and u.tiene("tesoreria", "compras"):
        a += ["recibir"]
    if o.estado == "aprobada" and u.tiene("aprobador", "compras"):
        a += ["anular"]
    return sorted(set(a))


def oc_detalle(db: Session, u: Usuario, o: OrdenCompra) -> dict:
    d = oc_resumen(o)
    d.update({
        "proveedor_id": o.proveedor_id, "proveedor_contacto": o.proveedor_contacto,
        "observaciones": o.observaciones, "retefuente_pct": o.retefuente_pct, "reteica_x_mil": o.reteica_x_mil,
        "total_bruto": o.total_bruto, "descuentos": o.descuentos, "subtotal": o.subtotal, "iva_total": o.iva_total,
        "retefuente": o.retefuente, "reteica": o.reteica, "motivo_rechazo": o.motivo_rechazo,
        "verificacion": o.verificacion, "referencia_pago": o.referencia_pago, "soporte_pago": o.soporte_pago,
        "notas_recepcion": o.notas_recepcion,
        "creada_por": o.creada_por.nombre if o.creada_por else "",
        "aprobada_por": o.aprobada_por.nombre if o.aprobada_por else "",
        "aprobada_en": o.aprobada_en.isoformat() if o.aprobada_en else None,
        "pagada_en": o.pagada_en.isoformat() if o.pagada_en else None,
        "recibida_en": o.recibida_en.isoformat() if o.recibida_en else None,
        "lineas": [{"id": l.id, "posicion": l.posicion, "item_id": l.item_id, "descripcion": l.descripcion,
                    "cantidad": l.cantidad, "vr_unitario": l.vr_unitario, "descuento": l.descuento,
                    "iva_pct": l.iva_pct, "rete_pct": l.rete_pct, "total": l.total, "url_fuente": l.url_fuente,
                    "tienda": (l.oferta or {}).get("tienda", ""), "titulo": (l.oferta or {}).get("titulo", ""),
                    "verificacion": (l.oferta or {}).get("verificacion")} for l in o.lineas],
        "facturas": [factura_dict(f) for f in o.facturas],
        "eventos": eventos(db, "orden", o.id),
        "acciones": acciones_oc(u, o),
    })
    return d


def factura_dict(f: Factura) -> dict:
    return {"id": f.id, "numero": f.numero, "orden_id": f.orden_id, "orden": f.orden.numero if f.orden else "",
            "proveedor_nombre": f.orden.proveedor_nombre if f.orden else "", "fecha": f.fecha.isoformat(),
            "estado": f.estado, "total_pagar": f.total_pagar, "numero_proveedor": f.numero_proveedor,
            "archivo_proveedor": f.archivo_proveedor,
            "requerimiento": f.orden.requerimiento.consecutivo if f.orden and f.orden.requerimiento else ""}
