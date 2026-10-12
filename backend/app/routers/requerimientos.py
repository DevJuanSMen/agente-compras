"""Requerimientos, estudio de mercado, seleccion y generacion de ordenes."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from agente_compras.mercado import fuentes as catalogo_fuentes

from .. import flujo, servicios
from ..ajustes import DIR_ARCHIVOS
from ..bd import obtener_sesion
from ..documentos import excel, pdf
from ..modelos import CotizacionManual, ItemRequerimiento, Proveedor, Requerimiento, Usuario
from ..seguridad import requiere, usuario_actual, usuario_por_token
from ..vistas import puede_ver, req_detalle, req_resumen, estudio_vista

router = APIRouter(prefix="/api/requerimientos", tags=["requerimientos"])

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
EXT_DOC = EXT_IMAGEN | {".pdf", ".xlsx", ".xls", ".docx", ".doc"}
MAX_ARCHIVO = 8 * 1024 * 1024


class ItemEntrada(BaseModel):
    cantidad: float = Field(gt=0)
    unidad: str = "UND"
    programa: str = ""
    descripcion: str = Field(min_length=2)
    especificaciones: str = ""
    marca_preferida: str = ""
    acepta_equivalentes: bool = True
    observaciones: str = ""


class RequerimientoEntrada(BaseModel):
    nombre_cargo: str = Field(min_length=3)
    area: str = ""
    destino: str = Field(min_length=2)
    tipo: str = ""
    fecha_requerida: Optional[date] = None
    prioridad: str = "normal"
    justificacion: str = ""
    fuentes: list[str] = []
    sitios_extra: list[str] = []
    proveedores_sugeridos: list[int] = []
    items: list[ItemEntrada] = Field(min_length=1)
    enviar: bool = False


def guardar_archivo(archivo: UploadFile, carpeta: str, permitidas: set[str]) -> str:
    nombre = (archivo.filename or "archivo").replace("\\", "/").split("/")[-1]
    ext = ("." + nombre.rsplit(".", 1)[-1].lower()) if "." in nombre else ""
    if ext not in permitidas:
        raise HTTPException(400, f"Tipo de archivo no permitido ({ext or 'sin extensión'})")
    datos = archivo.file.read(MAX_ARCHIVO + 1)
    if len(datos) > MAX_ARCHIVO:
        raise HTTPException(400, "El archivo supera 8 MB")
    destino = DIR_ARCHIVOS / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    final = f"{uuid.uuid4().hex[:12]}{ext}"
    (destino / final).write_bytes(datos)
    return f"{carpeta}/{final}"


def obtener(db: Session, u: Usuario, rid: int) -> Requerimiento:
    req = db.get(Requerimiento, rid)
    if not req or not puede_ver(u, req):
        raise HTTPException(404, "Requerimiento no encontrado")
    return req


def _item(req: Requerimiento, item_id: int) -> ItemRequerimiento:
    item = next((i for i in req.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Ítem no encontrado")
    return item


def _validar_fuentes(datos: RequerimientoEntrada) -> None:
    malas = [f for f in datos.fuentes if f not in catalogo_fuentes.POR_CLAVE]
    if malas:
        raise HTTPException(400, f"Fuentes desconocidas: {', '.join(malas)}")


def _aplicar(req: Requerimiento, datos: RequerimientoEntrada) -> None:
    req.nombre_cargo, req.area, req.destino, req.tipo = datos.nombre_cargo, datos.area, datos.destino, datos.tipo
    req.fecha_requerida, req.prioridad, req.justificacion = datos.fecha_requerida, datos.prioridad, datos.justificacion
    req.fuentes = datos.fuentes
    req.sitios_extra = [s.strip() for s in datos.sitios_extra if s.strip()][:8]
    req.proveedores_sugeridos = datos.proveedores_sugeridos
    imagenes = {i.orden: i.imagen for i in req.items}
    req.items.clear()
    for n, it in enumerate(datos.items):
        req.items.append(ItemRequerimiento(orden=n, imagen=imagenes.get(n, ""), **it.model_dump()))


# ---------------------------------------------------------------------------
@router.get("")
def listar(estado: str = "", q: str = "", mios: bool = False, u: Usuario = Depends(usuario_actual),
           db: Session = Depends(obtener_sesion)):
    consulta = select(Requerimiento).order_by(Requerimiento.creado_en.desc())
    if mios or not u.tiene("verificador", "compras", "aprobador", "tesoreria"):
        consulta = consulta.where(Requerimiento.solicitante_id == u.id)
    if estado:
        consulta = consulta.where(Requerimiento.estado.in_(estado.split(",")))
    if q:
        like = f"%{q}%"
        consulta = consulta.where(or_(Requerimiento.consecutivo.ilike(like), Requerimiento.destino.ilike(like),
                                      Requerimiento.nombre_cargo.ilike(like), Requerimiento.area.ilike(like)))
    return [req_resumen(r) for r in db.scalars(consulta.limit(500))]


@router.post("")
def crear(datos: RequerimientoEntrada, u: Usuario = Depends(requiere("solicitante", "compras")),
          db: Session = Depends(obtener_sesion)):
    _validar_fuentes(datos)
    req = Requerimiento(consecutivo=servicios.siguiente_consecutivo(db, "requerimiento"), solicitante_id=u.id,
                        fecha_solicitud=date.today())
    _aplicar(req, datos)
    db.add(req)
    db.flush()
    servicios.registrar(db, "requerimiento", req.id, u, "creado", f"{len(req.items)} ítem(s)")
    if datos.enviar:
        flujo.enviar(db, req, u)
    db.commit()
    return req_detalle(db, u, req)


@router.get("/{rid}")
def detalle(rid: int, u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    return req_detalle(db, u, obtener(db, u, rid))


@router.put("/{rid}")
def editar(rid: int, datos: RequerimientoEntrada, u: Usuario = Depends(usuario_actual),
           db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    if "editar" not in req_detalle(db, u, req)["acciones"]:
        raise HTTPException(403, "Solo el solicitante puede editar un borrador o un requerimiento rechazado")
    _validar_fuentes(datos)
    _aplicar(req, datos)
    servicios.registrar(db, "requerimiento", req.id, u, "editado")
    if datos.enviar:
        flujo.enviar(db, req, u)
    db.commit()
    return req_detalle(db, u, req)


@router.post("/{rid}/enviar")
def enviar(rid: int, u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    if req.solicitante_id != u.id and not u.tiene("admin"):
        raise HTTPException(403, "Solo el solicitante puede enviar el requerimiento")
    flujo.enviar(db, req, u)
    db.commit()
    return req_detalle(db, u, req)


class Decision(BaseModel):
    aprobado: bool
    motivo: str = ""


@router.post("/{rid}/verificar")
def verificar(rid: int, datos: Decision, u: Usuario = Depends(requiere("verificador")),
              db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    flujo.verificar(db, req, u, datos.aprobado, datos.motivo)
    db.commit()
    return req_detalle(db, u, req)


class Motivo(BaseModel):
    motivo: str = ""


@router.post("/{rid}/cancelar")
def cancelar(rid: int, datos: Motivo, u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    from ..vistas import acciones_req

    if "cancelar" not in acciones_req(u, req):
        raise HTTPException(403, "No puede cancelar este requerimiento")
    flujo.cancelar(db, req, u, datos.motivo)
    db.commit()
    return req_detalle(db, u, req)


@router.post("/{rid}/items/{item_id}/imagen")
def subir_imagen(rid: int, item_id: int, archivo: UploadFile = File(...), u: Usuario = Depends(usuario_actual),
                 db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    if req.solicitante_id != u.id and not u.tiene("compras"):
        raise HTTPException(403, "No puede modificar este requerimiento")
    item = _item(req, item_id)
    item.imagen = guardar_archivo(archivo, f"req{req.id}", EXT_IMAGEN)
    db.commit()
    return {"imagen": item.imagen}


# --- Estudio de mercado -----------------------------------------------------
@router.get("/{rid}/estudio")
def ver_estudio(rid: int, u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    return estudio_vista(db, obtener(db, u, rid))


class Reestudio(BaseModel):
    instrucciones: str = ""
    items_ids: list[int] = []


@router.post("/{rid}/estudio")
def reestudiar(rid: int, datos: Reestudio, u: Usuario = Depends(requiere("compras")),
               db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    if req.estado not in ("estudio_listo",) and not (req.estado == "en_estudio" and req.estudios
                                                    and req.estudios[-1].estado == "error"):
        raise HTTPException(409, "Solo se puede re-estudiar cuando el estudio está listo")
    flujo.iniciar_estudio(db, req, u, datos.instrucciones.strip(), datos.items_ids or None)
    db.commit()
    return estudio_vista(db, req)


class Seleccion(BaseModel):
    oferta_id: Optional[str] = None


@router.post("/{rid}/items/{item_id}/seleccion")
def seleccionar(rid: int, item_id: int, datos: Seleccion, u: Usuario = Depends(requiere("compras")),
                db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    flujo.seleccionar(db, req, _item(req, item_id), datos.oferta_id, u)
    db.commit()
    return {"ok": True}


class Exclusion(BaseModel):
    excluido: bool
    motivo: str = ""


@router.post("/{rid}/items/{item_id}/excluir")
def excluir(rid: int, item_id: int, datos: Exclusion, u: Usuario = Depends(requiere("compras")),
            db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    flujo.exigir_estado(req, "estudio_listo")
    item = _item(req, item_id)
    item.excluido = datos.excluido
    if datos.excluido:
        item.seleccion = None
    servicios.registrar(db, "requerimiento", req.id, u, "item_excluido" if datos.excluido else "item_incluido",
                        f"Ítem {item.orden + 1}: {datos.motivo}")
    db.commit()
    return {"ok": True}


@router.post("/{rid}/usar-recomendadas")
def usar_recomendadas(rid: int, u: Usuario = Depends(requiere("compras")), db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    n = flujo.usar_recomendadas(db, req, u)
    db.commit()
    return {"seleccionados": n}


@router.post("/{rid}/cotizaciones")
def agregar_cotizacion(
    rid: int, item_id: int = Form(...), proveedor_id: Optional[int] = Form(None),
    proveedor_nombre: str = Form(""), descripcion: str = Form(""), precio_unitario: float = Form(..., gt=0),
    unidades_paquete: float = Form(1, gt=0), incluye_iva: bool = Form(True), vigencia: str = Form(""),
    plazo_entrega: str = Form(""), forma_pago: str = Form(""), garantia: str = Form(""),
    observaciones: str = Form(""), archivo: Optional[UploadFile] = File(None),
    u: Usuario = Depends(requiere("compras")), db: Session = Depends(obtener_sesion),
):
    req = obtener(db, u, rid)
    flujo.exigir_estado(req, "estudio_listo", "en_estudio")
    item = _item(req, item_id)
    prov = db.get(Proveedor, proveedor_id) if proveedor_id else None
    nombre = prov.nombre if prov else proveedor_nombre.strip()
    if not nombre:
        raise HTTPException(400, "Indique el proveedor")
    c = CotizacionManual(requerimiento_id=req.id, item_id=item.id, proveedor_id=prov.id if prov else None,
                         proveedor_nombre=nombre, descripcion=descripcion, precio_unitario=precio_unitario,
                         unidades_paquete=unidades_paquete, incluye_iva=incluye_iva, vigencia=vigencia,
                         plazo_entrega=plazo_entrega, forma_pago=forma_pago, garantia=garantia,
                         observaciones=observaciones, creado_por_id=u.id)
    if archivo and archivo.filename:
        c.archivo = guardar_archivo(archivo, f"req{req.id}", EXT_DOC)
    db.add(c)
    servicios.registrar(db, "requerimiento", req.id, u, "cotizacion_manual",
                        f"Ítem {item.orden + 1}: {nombre} ${precio_unitario:,.0f}".replace(",", "."))
    db.commit()
    return {"id": c.id, "oferta_id": f"manual-{c.id}"}


@router.delete("/{rid}/cotizaciones/{cid}")
def borrar_cotizacion(rid: int, cid: int, u: Usuario = Depends(requiere("compras")),
                      db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    c = db.get(CotizacionManual, cid)
    if not c or c.requerimiento_id != req.id:
        raise HTTPException(404, "Cotización no encontrada")
    for i in req.items:
        if (i.seleccion or {}).get("id") == f"manual-{cid}":
            i.seleccion = None
    db.delete(c)
    servicios.registrar(db, "requerimiento", req.id, u, "cotizacion_eliminada", c.proveedor_nombre)
    db.commit()
    return {"ok": True}


class GenerarOrdenes(BaseModel):
    forma_pago: str = "contado"
    observaciones: str = ""
    confirmar_cambios: bool = False


@router.post("/{rid}/ordenes")
def generar_ordenes(rid: int, datos: GenerarOrdenes, u: Usuario = Depends(requiere("compras")),
                    db: Session = Depends(obtener_sesion)):
    req = obtener(db, u, rid)
    if datos.forma_pago not in ("contado", "credito"):
        raise HTTPException(400, "Forma de pago inválida")
    r = flujo.generar_ordenes(db, req, u, forma_pago=datos.forma_pago, observaciones=datos.observaciones,
                              confirmar_cambios=datos.confirmar_cambios)
    db.commit()
    return r


@router.get("/{rid}/solicitud-cotizacion")
def solicitud_cotizacion(rid: int, proveedor_id: Optional[int] = None, u: Usuario = Depends(requiere("compras")),
                         db: Session = Depends(obtener_sesion)):
    """Texto de solicitud de cotizacion para proveedores locales (paso "enviar
    solicitud de cotizacion al proveedor" del flujograma)."""
    req = obtener(db, u, rid)
    emp = servicios.config(db, "empresa")
    prov = db.get(Proveedor, proveedor_id) if proveedor_id else None
    lineas = "\n".join(
        f"{n}. {i.cantidad:g} {i.unidad} - {i.descripcion}" + (f" ({i.especificaciones})" if i.especificaciones else "")
        for n, i in enumerate([i for i in req.items if not i.excluido], start=1))
    cuerpo = (f"Señores {prov.nombre if prov else '[proveedor]'}:\n\n"
              f"{emp['nombre']} (NIT {emp['nit']}) solicita cotización de los siguientes elementos "
              f"(requerimiento {req.consecutivo}):\n\n{lineas}\n\n"
              "Por favor indicar valor unitario, IVA, vigencia de la oferta, plazo de entrega, forma de pago y "
              "garantía. Adjuntar RUT y certificado de cámara de comercio si no son proveedores registrados.\n\n"
              f"Cordialmente,\n{u.nombre}\n{u.cargo or 'Compras'} - {emp['nombre']}\n{emp['telefono']}")
    return {"asunto": f"Solicitud de cotización {req.consecutivo} - {emp['nombre']}", "cuerpo": cuerpo,
            "para": prov.email if prov else ""}


# --- Documentos -------------------------------------------------------------
def _usuario_descarga(token: str, db: Session) -> Usuario:
    u = usuario_por_token(token, db)
    if not u:
        raise HTTPException(401, "Sesión vencida")
    return u


def _archivo(datos: bytes, nombre: str, tipo: str) -> Response:
    return Response(datos, media_type=tipo, headers={"Content-Disposition": f'inline; filename="{nombre}"'})


@router.get("/{rid}/documentos/estudio.pdf")
def doc_estudio(rid: int, token: str = Query(...), db: Session = Depends(obtener_sesion)):
    u = _usuario_descarga(token, db)
    req = obtener(db, u, rid)
    e = flujo.estudio_vigente(req)
    if not e:
        raise HTTPException(404, "Aún no hay estudio de mercado")
    datos = pdf.pdf_estudio(req, e.resultado or {}, [i for i in req.items], servicios.config(db, "empresa"),
                            e.version, e.terminado_en)
    return _archivo(datos, f"Estudio_mercado_{req.consecutivo}.pdf", "application/pdf")


@router.get("/{rid}/documentos/cuadro.xlsx")
def doc_cuadro(rid: int, token: str = Query(...), db: Session = Depends(obtener_sesion)):
    u = _usuario_descarga(token, db)
    req = obtener(db, u, rid)
    filas = []
    for i in req.items:
        if i.excluido:
            continue
        validas = [o.model_dump(mode="json") for o in flujo.ofertas_item(db, req, i)
                   if o.relevancia in ("exacto", "equivalente") and o.metodo != "buscador" and o.precio]
        validas.sort(key=lambda o: o.get("precio_unitario") or 1e18)
        filas.append({"item": i, "ofertas": validas, "seleccion": i.seleccion})
    datos = excel.cuadro_comparativo(req, filas, servicios.config(db, "empresa"), servicios.config(db, "firmas"))
    return _archivo(datos, f"Cuadro_comparativo_{req.consecutivo}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.get("/{rid}/documentos/requerimiento.xlsx")
def doc_requerimiento(rid: int, token: str = Query(...), db: Session = Depends(obtener_sesion)):
    u = _usuario_descarga(token, db)
    req = obtener(db, u, rid)
    datos = excel.formato_requerimiento(req, servicios.config(db, "empresa"))
    return _archivo(datos, f"Requerimiento_{req.consecutivo}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
