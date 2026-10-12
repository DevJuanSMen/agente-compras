"""Claves, tokens y permisos.

Sin dependencias externas: scrypt de la libreria estandar para las claves y
JWT HS256 firmado con hmac. Son algoritmos estandar; se evita sumar paquetes
(passlib/bcrypt/pyjwt) que en esta maquina no estan instalados.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .ajustes import JWT_HORAS, JWT_SECRETO
from .bd import obtener_sesion
from .modelos import Usuario

_N, _R, _P = 2**14, 8, 1


def hashear(clave: str) -> str:
    sal = os.urandom(16)
    h = hashlib.scrypt(clave.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${base64.b64encode(sal).decode()}${base64.b64encode(h).decode()}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        _, n, r, p, sal, h = guardado.split("$")
        calc = hashlib.scrypt(clave.encode(), salt=base64.b64decode(sal), n=int(n), r=int(r),
                              p=int(p), dklen=32)
        return hmac.compare_digest(calc, base64.b64decode(h))
    except Exception:
        return False


def validar_clave_nueva(clave: str) -> None:
    if len(clave) < 8 or clave.isalpha() or clave.isdigit():
        raise HTTPException(400, "La clave debe tener al menos 8 caracteres y combinar letras con números o símbolos")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def crear_token(usuario_id: int) -> str:
    cab = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    cuerpo = _b64(json.dumps({"sub": usuario_id, "exp": int(time.time()) + JWT_HORAS * 3600}).encode())
    firma = _b64(hmac.new(JWT_SECRETO.encode(), f"{cab}.{cuerpo}".encode(), hashlib.sha256).digest())
    return f"{cab}.{cuerpo}.{firma}"


def leer_token(token: str) -> int | None:
    try:
        cab, cuerpo, firma = token.split(".")
        esperada = _b64(hmac.new(JWT_SECRETO.encode(), f"{cab}.{cuerpo}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(firma, esperada):
            return None
        datos = json.loads(_unb64(cuerpo))
        if datos.get("exp", 0) < time.time():
            return None
        return int(datos["sub"])
    except Exception:
        return None


_bearer = HTTPBearer(auto_error=False)


def usuario_actual(
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(obtener_sesion),
) -> Usuario:
    uid = leer_token(cred.credentials) if cred else None
    if uid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión vencida o inválida")
    u = db.get(Usuario, uid)
    if not u or not u.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo")
    return u


def usuario_por_token(token: str, db: Session) -> Usuario | None:
    """Para descargas abiertas en otra pestana (?token=...)."""
    uid = leer_token(token)
    u = db.get(Usuario, uid) if uid else None
    return u if u and u.activo else None


def requiere(*roles: str):
    def dependencia(u: Usuario = Depends(usuario_actual)) -> Usuario:
        if not u.tiene(*roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "No tiene permiso para esta acción")
        return u
    return dependencia
