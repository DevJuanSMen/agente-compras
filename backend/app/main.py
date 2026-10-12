"""Punto de entrada: `uvicorn backend.app.main:app` desde la raiz del proyecto."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import VERSION
from .ajustes import DIR_FRONTEND
from .bd import Base, Sesion, motor
from .routers import general, ordenes, requerimientos, usuarios
from .semilla import sembrar
from .trabajador import trabajador

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def ciclo_vida(_: FastAPI):
    Base.metadata.create_all(motor)
    with Sesion() as db:
        sembrar(db)
    if not trabajador.is_alive():
        trabajador.start()
    yield
    trabajador.detener()


app = FastAPI(title="Agente de Compras UPARSISTEM", version=VERSION, lifespan=ciclo_vida)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

for r in (usuarios.router, requerimientos.router, ordenes.router, general.router):
    app.include_router(r)


@app.exception_handler(Exception)
async def error_no_controlado(_: Request, exc: Exception):
    logging.getLogger("compras").exception("Error no controlado")
    return JSONResponse(status_code=500, content={"detail": f"Error interno: {type(exc).__name__}"})


# --- Interfaz compilada (frontend/dist) -------------------------------------
if (DIR_FRONTEND / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIR_FRONTEND / "assets"), name="assets")


@app.get("/{ruta:path}", include_in_schema=False)
def spa(ruta: str):
    if ruta.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Ruta no encontrada"})
    archivo = DIR_FRONTEND / ruta
    if ruta and archivo.is_file() and DIR_FRONTEND in archivo.resolve().parents:
        return FileResponse(archivo)
    indice = DIR_FRONTEND / "index.html"
    if indice.exists():
        return FileResponse(indice)
    return JSONResponse({"mensaje": "API del Agente de Compras activa. Compile el frontend con "
                                    "`npm run build` en /frontend para ver la interfaz.", "docs": "/docs"})
