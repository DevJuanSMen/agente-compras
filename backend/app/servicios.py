"""Servicios transversales: configuracion, consecutivos, auditoria y avisos."""
from __future__ import annotations

import copy
import logging
import smtplib
import threading
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import ajustes
from .modelos import Configuracion, Evento, Notificacion, Usuario

log = logging.getLogger("compras")
_candado_consecutivo = threading.Lock()


# --- Configuracion -----------------------------------------------------------
def config(db: Session, clave: str):
    fila = db.scalar(select(Configuracion).where(Configuracion.clave == clave))
    base = copy.deepcopy(ajustes.CONFIG_INICIAL.get(clave))
    if fila is None:
        return base
    if isinstance(base, dict) and isinstance(fila.valor, dict):
        base.update(fila.valor)  # claves nuevas del codigo aparecen aunque la BD sea vieja
        return base
    return fila.valor


def config_completa(db: Session) -> dict:
    return {k: config(db, k) for k in ajustes.CONFIG_INICIAL}


def guardar_config(db: Session, clave: str, valor) -> None:
    fila = db.scalar(select(Configuracion).where(Configuracion.clave == clave))
    if fila is None:
        db.add(Configuracion(clave=clave, valor=valor))
    else:
        fila.valor = valor


def siguiente_consecutivo(db: Session, tipo: str) -> str:
    """tipo: requerimiento | orden | factura. Atomico dentro del proceso."""
    with _candado_consecutivo:
        c = config(db, "consecutivos")
        numero = int(c[f"{tipo}_siguiente"])
        c[f"{tipo}_siguiente"] = numero + 1
        guardar_config(db, "consecutivos", c)
        db.flush()
        ancho = 4 if tipo != "orden" else 0
        return f"{c[f'{tipo}_prefijo']}{numero:0{ancho}d}" if ancho else f"{c[f'{tipo}_prefijo']}{numero}"


# --- Auditoria ---------------------------------------------------------------
def registrar(db: Session, entidad: str, entidad_id: int, usuario: Usuario | None, accion: str,
              detalle: str = "") -> None:
    db.add(Evento(entidad=entidad, entidad_id=entidad_id, usuario_id=usuario.id if usuario else None,
                  accion=accion, detalle=detalle[:4000]))


# --- Notificaciones ----------------------------------------------------------
def notificar(db: Session, usuarios: list[Usuario], titulo: str, mensaje: str = "",
              enlace: str = "", tipo: str = "info", excluir: Usuario | None = None) -> None:
    vistos: set[int] = set()
    correos: list[str] = []
    for u in usuarios:
        if not u or not u.activo or u.id in vistos or (excluir and u.id == excluir.id):
            continue
        vistos.add(u.id)
        db.add(Notificacion(usuario_id=u.id, titulo=titulo, mensaje=mensaje, enlace=enlace, tipo=tipo))
        if u.notificar_correo and u.email:
            correos.append(u.email)
    if correos and ajustes.SMTP_HOST:
        threading.Thread(target=_enviar_correo, args=(correos, titulo, mensaje, enlace),
                         daemon=True).start()


def usuarios_con_rol(db: Session, rol: str) -> list[Usuario]:
    todos = db.scalars(select(Usuario).where(Usuario.activo.is_(True))).all()
    return [u for u in todos if rol in (u.roles or [])]


def _enviar_correo(destinos: list[str], asunto: str, mensaje: str, enlace: str) -> None:
    try:
        msg = EmailMessage()
        msg["Subject"] = f"[Compras UPARSISTEM] {asunto}"
        msg["From"] = ajustes.SMTP_REMITENTE
        msg["Bcc"] = ", ".join(destinos)
        url = f"{ajustes.URL_PUBLICA.rstrip('/')}{enlace}" if enlace else ajustes.URL_PUBLICA
        msg.set_content(f"{mensaje}\n\nVer en el sistema: {url}\n\n— Agente de Compras UPARSISTEM")
        with smtplib.SMTP(ajustes.SMTP_HOST, ajustes.SMTP_PORT, timeout=20) as s:
            s.starttls()
            if ajustes.SMTP_USUARIO:
                s.login(ajustes.SMTP_USUARIO, ajustes.SMTP_CLAVE)
            s.send_message(msg)
    except Exception as exc:  # el correo nunca debe tumbar el flujo
        log.warning("No se pudo enviar correo: %s", exc)
