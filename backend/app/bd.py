"""Conexion a la base de datos.

SQLite por defecto (un archivo en `backend/datos`), PostgreSQL cambiando
`COMPRAS_DATABASE_URL`. El modo WAL deja leer mientras el trabajador escribe
el progreso de un estudio.
"""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .ajustes import DATABASE_URL

_es_sqlite = DATABASE_URL.startswith("sqlite")
motor = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if _es_sqlite else {},
    pool_pre_ping=True,
)

if _es_sqlite:
    @event.listens_for(motor, "connect")
    def _pragmas(conexion, _):
        cur = conexion.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


Sesion = sessionmaker(bind=motor, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def obtener_sesion():
    """Dependencia de FastAPI."""
    s = Sesion()
    try:
        yield s
    finally:
        s.close()


@contextmanager
def sesion():
    s = Sesion()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
