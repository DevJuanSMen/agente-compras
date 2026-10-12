"""Proveedores, notificaciones, configuracion, catalogos, tablero y archivos."""
from __future__ import annotations

import mimetypes
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from agente_compras import config as config_ia
from agente_compras.mercado import fuentes as catalogo_fuentes
from agente_compras.mercado import navegador

from .. import VERSION, servicios
from ..ajustes import CONFIG_INICIAL, DIR_ARCHIVOS, SMTP_HOST
from ..bd import obtener_sesion
from ..modelos import (
    ESTADOS_OC, ESTADOS_REQ, ROLES, EstudioMercado, Evento, Notificacion, OrdenCompra, Proveedor, Requerimiento,
    Usuario,
)
from ..seguridad import requiere, usuario_actual, usuario_por_token
from ..trabajador import trabajador
from ..vistas import oc_resumen, req_resumen

router = APIRouter(prefix="/api", tags=["general"])


# --- Catalogos y salud ------------------------------------------------------
@router.get("/catalogos")
def catalogos(_: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    return {
        "areas": servicios.config(db, "areas"), "laboratorios": servicios.config(db, "laboratorios"),
        "tipos": servicios.config(db, "tipos"), "unidades": servicios.config(db, "unidades"),
        "fuentes": catalogo_fuentes.describir(), "rubros": catalogo_fuentes.RUBROS,
        "estados_req": ESTADOS_REQ, "estados_oc": ESTADOS_OC, "roles": ROLES,
        "flujo": servicios.config(db, "flujo"),
    }


@router.get("/empresa")
def empresa(_: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    return servicios.config(db, "empresa")


@router.get("/salud")
def salud(db: Session = Depends(obtener_sesion)):
    cola = db.scalar(select(func.count()).select_from(EstudioMercado).where(EstudioMercado.estado == "en_cola"))
    return {"version": VERSION, "trabajador_activo": trabajador.is_alive(), "estudio_en_proceso": trabajador.activo_id,
            "en_cola": cola, "ia": config_ia.proveedores_disponibles(), "navegador": navegador.disponible(),
            "correo": bool(SMTP_HOST)}


# --- Proveedores ------------------------------------------------------------
class ProveedorEntrada(BaseModel):
    nombre: str = Field(min_length=2)
    tipo_identificacion: str = "NIT"
    identificacion: str = ""
    dv: str = ""
    direccion: str = ""
    ciudad: str = "Valledupar"
    telefono: str = ""
    email: str = ""
    sitio_web: str = ""
    rubros: list[str] = []
    recurrente: bool = True
    activo: bool = True
    notas: str = ""


def proveedor_dict(p: Proveedor) -> dict:
    return {"id": p.id, "nombre": p.nombre, "tipo_identificacion": p.tipo_identificacion,
            "identificacion": p.identificacion, "dv": p.dv, "nit": p.nit_completo, "direccion": p.direccion,
            "ciudad": p.ciudad, "telefono": p.telefono, "email": p.email, "sitio_web": p.sitio_web,
            "rubros": p.rubros or [], "recurrente": p.recurrente, "activo": p.activo, "notas": p.notas}


@router.get("/proveedores")
def proveedores(q: str = "", ciudad: str = "", solo_activos: bool = True, limite: int = 400,
                _: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    consulta = select(Proveedor).order_by(Proveedor.nombre)
    if solo_activos:
        consulta = consulta.where(Proveedor.activo.is_(True))
    if q:
        like = f"%{q}%"
        consulta = consulta.where(or_(Proveedor.nombre.ilike(like), Proveedor.identificacion.ilike(like),
                                      Proveedor.email.ilike(like), Proveedor.notas.ilike(like)))
    if ciudad:
        consulta = consulta.where(Proveedor.ciudad.ilike(f"%{ciudad}%"))
    return [proveedor_dict(p) for p in db.scalars(consulta.limit(min(limite, 1000)))]


@router.post("/proveedores")
def crear_proveedor(datos: ProveedorEntrada, u: Usuario = Depends(requiere("compras")),
                    db: Session = Depends(obtener_sesion)):
    p = Proveedor(**datos.model_dump())
    db.add(p)
    db.flush()
    servicios.registrar(db, "proveedor", p.id, u, "creado", p.nombre)
    db.commit()
    return proveedor_dict(p)


@router.put("/proveedores/{pid}")
def editar_proveedor(pid: int, datos: ProveedorEntrada, u: Usuario = Depends(requiere("compras")),
                     db: Session = Depends(obtener_sesion)):
    p = db.get(Proveedor, pid)
    if not p:
        raise HTTPException(404, "Proveedor no encontrado")
    for k, v in datos.model_dump().items():
        setattr(p, k, v)
    servicios.registrar(db, "proveedor", p.id, u, "editado", p.nombre)
    db.commit()
    return proveedor_dict(p)


# --- Notificaciones ---------------------------------------------------------
@router.get("/notificaciones")
def notificaciones(u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    filas = db.scalars(select(Notificacion).where(Notificacion.usuario_id == u.id)
                       .order_by(Notificacion.creada_en.desc()).limit(60)).all()
    no_leidas = db.scalar(select(func.count()).select_from(Notificacion)
                          .where(Notificacion.usuario_id == u.id, Notificacion.leida.is_(False)))
    return {"no_leidas": no_leidas,
            "items": [{"id": n.id, "titulo": n.titulo, "mensaje": n.mensaje, "enlace": n.enlace, "tipo": n.tipo,
                       "leida": n.leida, "creada_en": n.creada_en.isoformat()} for n in filas]}


@router.post("/notificaciones/{nid}/leer")
def leer(nid: int, u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    n = db.get(Notificacion, nid)
    if n and n.usuario_id == u.id:
        n.leida = True
        db.commit()
    return {"ok": True}


@router.post("/notificaciones/leer-todas")
def leer_todas(u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    for n in db.scalars(select(Notificacion).where(Notificacion.usuario_id == u.id, Notificacion.leida.is_(False))):
        n.leida = True
    db.commit()
    return {"ok": True}


# --- Configuracion ----------------------------------------------------------
@router.get("/configuracion")
def ver_config(_: Usuario = Depends(requiere("admin")), db: Session = Depends(obtener_sesion)):
    return servicios.config_completa(db)


@router.put("/configuracion/{clave}")
def guardar_config(clave: str, valor: dict | list, u: Usuario = Depends(requiere("admin")),
                   db: Session = Depends(obtener_sesion)):
    if clave not in CONFIG_INICIAL:
        raise HTTPException(404, "Sección desconocida")
    if type(valor) is not type(CONFIG_INICIAL[clave]):
        raise HTTPException(400, "Formato inválido para esta sección")
    servicios.guardar_config(db, clave, valor)
    servicios.registrar(db, "configuracion", 0, u, f"config_{clave}", str(valor)[:1000])
    db.commit()
    return servicios.config(db, clave)


# --- Tablero ----------------------------------------------------------------
@router.get("/tablero")
def tablero(u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    ve_todo = u.tiene("verificador", "compras", "aprobador", "tesoreria")
    reqs = db.scalars(select(Requerimiento)).all()
    if not ve_todo:
        reqs = [r for r in reqs if r.solicitante_id == u.id]
    por_estado: dict[str, int] = {}
    for r in reqs:
        por_estado[r.estado] = por_estado.get(r.estado, 0) + 1

    tareas: list[dict] = []
    def tarea(titulo: str, lista: list, tipo: str):
        if lista:
            tareas.append({"titulo": titulo, "tipo": tipo, "elementos": lista[:8], "total": len(lista)})

    if u.tiene("verificador"):
        tarea("Requerimientos por verificar", [req_resumen(r) for r in reqs if r.estado == "pendiente_verificacion"], "req")
    if u.tiene("compras"):
        tarea("Estudios listos para revisar", [req_resumen(r) for r in reqs if r.estado == "estudio_listo"], "req")
    ordenes = db.scalars(select(OrdenCompra).order_by(OrdenCompra.creada_en.desc())).all()
    if u.tiene("aprobador"):
        tarea("Órdenes por aprobar", [oc_resumen(o) for o in ordenes if o.estado == "pendiente_aprobacion"], "oc")
    if u.tiene("tesoreria"):
        tarea("Órdenes por pagar", [oc_resumen(o) for o in ordenes if o.estado == "aprobada"], "oc")
        tarea("Pedidos por recibir", [oc_resumen(o) for o in ordenes if o.estado == "pagada"], "oc")
    propios = [r for r in reqs if r.solicitante_id == u.id and r.estado in ("borrador", "rechazado")]
    tarea("Mis borradores y rechazados", [req_resumen(r) for r in propios], "req")

    inicio_mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    aprobadas_mes = [o for o in ordenes if o.estado in ("aprobada", "pagada", "recibida") and o.aprobada_en
                     and (o.aprobada_en if o.aprobada_en.tzinfo else o.aprobada_en.replace(tzinfo=timezone.utc)) >= inicio_mes]
    estudios = db.scalars(select(EstudioMercado).where(EstudioMercado.estado == "listo")
                          .order_by(EstudioMercado.terminado_en.desc()).limit(30)).all()
    duraciones = [(e.terminado_en - e.iniciado_en).total_seconds() for e in estudios if e.terminado_en and e.iniciado_en]
    ahorro = 0.0
    for e in estudios:
        for datos in (e.resultado or {}).values():
            a = (datos.get("estadisticas") or {}).get("ahorro_vs_mediana") if isinstance(datos, dict) else None
            if a and a > 0:
                ahorro += a
    actividad = db.scalars(select(Evento).where(Evento.entidad.in_(["requerimiento", "orden"]))
                           .order_by(Evento.creado_en.desc()).limit(15)).all()
    visibles_req = {r.id for r in reqs}
    return {
        "por_estado": por_estado, "total_requerimientos": len(reqs), "tareas": tareas,
        "comprometido_mes": sum(o.total_pagar for o in aprobadas_mes), "ordenes_mes": len(aprobadas_mes),
        "duracion_media_estudio_s": sum(duraciones) / len(duraciones) if duraciones else None,
        "ahorro_estimado": ahorro,
        "en_estudio": [req_resumen(r) for r in reqs if r.estado == "en_estudio"],
        "actividad": [{"accion": e.accion, "detalle": e.detalle, "fecha": e.creado_en.isoformat(),
                       "usuario": e.usuario.nombre if e.usuario else "Agente", "entidad": e.entidad,
                       "entidad_id": e.entidad_id} for e in actividad
                      if ve_todo or (e.entidad == "requerimiento" and e.entidad_id in visibles_req)][:12],
    }


# --- Archivos subidos -------------------------------------------------------
@router.get("/archivos/{ruta:path}")
def archivo(ruta: str, token: str = Query(...), db: Session = Depends(obtener_sesion)):
    if not usuario_por_token(token, db):
        raise HTTPException(401, "Sesión vencida")
    destino = (DIR_ARCHIVOS / ruta).resolve()
    if DIR_ARCHIVOS.resolve() not in destino.parents or not destino.is_file():
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(destino, media_type=mimetypes.guess_type(destino.name)[0] or "application/octet-stream")
