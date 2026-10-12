"""Sesion y administracion de usuarios."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import servicios
from ..ajustes import CLAVE_INICIAL
from ..bd import obtener_sesion
from ..modelos import ROLES, Usuario
from ..seguridad import crear_token, hashear, requiere, usuario_actual, validar_clave_nueva, verificar_clave
from ..vistas import usuario_dict

router = APIRouter(prefix="/api", tags=["usuarios"])


class Login(BaseModel):
    email: str
    clave: str


class CambioClave(BaseModel):
    actual: str
    nueva: str


class UsuarioEntrada(BaseModel):
    nombre: str = Field(min_length=3)
    email: str = Field(min_length=5)
    cargo: str = ""
    area: str = ""
    roles: list[str] = ["solicitante"]
    activo: bool = True
    notificar_correo: bool = True


class Preferencias(BaseModel):
    notificar_correo: bool


@router.post("/auth/login")
def login(datos: Login, db: Session = Depends(obtener_sesion)):
    u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == datos.email.strip().lower()))
    if not u or not verificar_clave(datos.clave, u.clave_hash):
        raise HTTPException(401, "Correo o clave incorrectos")
    if not u.activo:
        raise HTTPException(403, "Usuario inactivo. Contacte al administrador.")
    return {"token": crear_token(u.id), "usuario": usuario_dict(u)}


@router.get("/auth/yo")
def yo(u: Usuario = Depends(usuario_actual)):
    return usuario_dict(u)


@router.post("/auth/cambiar-clave")
def cambiar_clave(datos: CambioClave, u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    if not verificar_clave(datos.actual, u.clave_hash):
        raise HTTPException(400, "La clave actual no es correcta")
    validar_clave_nueva(datos.nueva)
    u = db.merge(u)
    u.clave_hash = hashear(datos.nueva)
    u.debe_cambiar_clave = False
    servicios.registrar(db, "usuario", u.id, u, "clave_cambiada")
    db.commit()
    return {"ok": True}


@router.put("/auth/preferencias")
def preferencias(datos: Preferencias, u: Usuario = Depends(usuario_actual), db: Session = Depends(obtener_sesion)):
    u = db.merge(u)
    u.notificar_correo = datos.notificar_correo
    db.commit()
    return usuario_dict(u)


@router.get("/usuarios")
def listar(_: Usuario = Depends(requiere("admin")), db: Session = Depends(obtener_sesion)):
    return [usuario_dict(u) for u in db.scalars(select(Usuario).order_by(Usuario.nombre))]


def _validar_roles(roles: list[str]) -> list[str]:
    malos = [r for r in roles if r not in ROLES]
    if malos:
        raise HTTPException(400, f"Roles inválidos: {', '.join(malos)}")
    if not roles:
        raise HTTPException(400, "Asigne al menos un rol")
    return roles


@router.post("/usuarios")
def crear(datos: UsuarioEntrada, admin: Usuario = Depends(requiere("admin")), db: Session = Depends(obtener_sesion)):
    email = datos.email.strip().lower()
    if db.scalar(select(Usuario).where(func.lower(Usuario.email) == email)):
        raise HTTPException(409, "Ya existe un usuario con ese correo")
    u = Usuario(nombre=datos.nombre.strip(), email=email, cargo=datos.cargo, area=datos.area,
                roles=_validar_roles(datos.roles), activo=datos.activo, notificar_correo=datos.notificar_correo,
                clave_hash=hashear(CLAVE_INICIAL), debe_cambiar_clave=True)
    db.add(u)
    db.flush()
    servicios.registrar(db, "usuario", u.id, admin, "creado", ", ".join(u.roles))
    db.commit()
    return usuario_dict(u) | {"clave_inicial": CLAVE_INICIAL}


@router.put("/usuarios/{uid}")
def editar(uid: int, datos: UsuarioEntrada, admin: Usuario = Depends(requiere("admin")),
           db: Session = Depends(obtener_sesion)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    if u.id == admin.id and ("admin" not in datos.roles or not datos.activo):
        raise HTTPException(400, "No puede quitarse el rol de administrador ni desactivarse a sí mismo")
    u.nombre, u.cargo, u.area = datos.nombre.strip(), datos.cargo, datos.area
    u.email = datos.email.strip().lower()
    u.roles = _validar_roles(datos.roles)
    u.activo = datos.activo
    u.notificar_correo = datos.notificar_correo
    servicios.registrar(db, "usuario", u.id, admin, "editado", ", ".join(u.roles))
    db.commit()
    return usuario_dict(u)


@router.post("/usuarios/{uid}/restablecer-clave")
def restablecer(uid: int, admin: Usuario = Depends(requiere("admin")), db: Session = Depends(obtener_sesion)):
    u = db.get(Usuario, uid)
    if not u:
        raise HTTPException(404, "Usuario no encontrado")
    u.clave_hash = hashear(CLAVE_INICIAL)
    u.debe_cambiar_clave = True
    servicios.registrar(db, "usuario", u.id, admin, "clave_restablecida")
    db.commit()
    return {"clave_inicial": CLAVE_INICIAL}
