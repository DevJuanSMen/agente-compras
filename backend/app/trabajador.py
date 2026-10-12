"""Trabajador de estudios de mercado.

La cola vive en la base de datos (estudios con estado `en_cola`), no en
memoria: si el servidor se reinicia a mitad de un estudio, al arrancar se
vuelve a encolar. Corre en un hilo propio, de a un estudio a la vez, porque
los free tier de IA no aguantan paralelismo y porque el navegador headless
de Playwright pertenece al hilo que lo crea.
"""
from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select

from agente_compras.llm import CadenaLLM
from agente_compras.mercado.estudio import estudiar_item
from agente_compras.mercado.modelos import ItemSolicitud, OpcionesEstudio

from . import servicios
from .bd import sesion
from .modelos import EstudioMercado, Requerimiento

log = logging.getLogger("compras.trabajador")

# Verificaciones de precio pedidas desde la API (al generar o aprobar una
# orden): un solo hilo, asi un solo navegador headless atiende todas.
VERIFICADOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="verificador")

_PASOS = (("Analizando", 0.05), ("Consultando", 0.12), ("Buscando en", 0.25),
          ("productos encontrados", 0.5), ("Revisando", 0.55), ("Verificando", 0.7),
          ("Redactando", 0.9), ("Linea lista", 1.0))


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Trabajador(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="trabajador-estudios", daemon=True)
        self._parar = threading.Event()
        self.activo_id: int | None = None

    def detener(self) -> None:
        self._parar.set()

    def run(self) -> None:
        with sesion() as db:
            for e in db.scalars(select(EstudioMercado).where(EstudioMercado.estado == "en_proceso")):
                e.estado = "en_cola"
                e.paso = "Re-encolado tras reinicio del servidor"
        while not self._parar.is_set():
            try:
                estudio_id = self._tomar()
                if estudio_id is None:
                    self._parar.wait(3)
                    continue
                self.activo_id = estudio_id
                self._procesar(estudio_id)
            except Exception:
                log.exception("Fallo inesperado del trabajador")
                self._parar.wait(5)
            finally:
                self.activo_id = None

    def _tomar(self) -> int | None:
        with sesion() as db:
            e = db.scalar(select(EstudioMercado).where(EstudioMercado.estado == "en_cola")
                          .order_by(EstudioMercado.creado_en).limit(1))
            if not e:
                return None
            e.estado = "en_proceso"
            e.iniciado_en = _ahora()
            e.paso = "Iniciando"
            return e.id

    def _procesar(self, estudio_id: int) -> None:
        with sesion() as db:
            e = db.get(EstudioMercado, estudio_id)
            req = e.requerimiento
            items = [i for i in req.items if not i.excluido and (not e.items_ids or i.id in e.items_ids)]
            cfg = servicios.config(db, "estudio")
            opciones = OpcionesEstudio(
                fuentes=list(req.fuentes or []) or list(cfg.get("fuentes_por_defecto") or []),
                sitios_extra=list(req.sitios_extra or []),
                auto_fuentes=bool(cfg.get("auto_fuentes", True)) or not req.fuentes,
                instrucciones=e.instrucciones or "",
                peso_precio=float(cfg.get("peso_precio", 0.6)),
                verificar_top=int(cfg.get("verificar_top", 6)),
                usar_navegador=bool(cfg.get("usar_navegador", True)),
            )
            solicitudes = [
                (i.id, ItemSolicitud(
                    id=i.id, cantidad=i.cantidad, unidad=i.unidad, descripcion=i.descripcion,
                    especificaciones=i.especificaciones, marca_preferida=i.marca_preferida,
                    programa=i.programa, observaciones=i.observaciones,
                    acepta_equivalentes=i.acepta_equivalentes))
                for i in items
            ]
            e.opciones = opciones.model_dump()
            req_id, consecutivo = req.id, req.consecutivo

        bitacora = _Bitacora(estudio_id, len(solicitudes))
        resultado: dict = {}
        llm = CadenaLLM()
        try:
            if not llm.hay_modelo:
                bitacora("Aviso: no hay clave de IA configurada; se usa clasificacion basica")
            for n, (item_id, sol) in enumerate(solicitudes):
                bitacora.item(n, sol.descripcion)
                try:
                    r = estudiar_item(sol, opciones, llm=llm, progreso=bitacora)
                    resultado[str(item_id)] = r.model_dump(mode="json")
                except Exception as exc:  # una linea fallida no tumba el estudio
                    log.exception("Fallo el item %s", item_id)
                    bitacora(f"ERROR en la linea: {str(exc)[:200]}")
                    resultado[str(item_id)] = {"error": str(exc)[:500], "item": sol.model_dump()}
                with sesion() as db:  # resultados parciales visibles en la interfaz
                    est = db.get(EstudioMercado, estudio_id)
                    est.resultado = dict(resultado)
            bitacora.cerrar()
            self._terminar(estudio_id, req_id, consecutivo, resultado, None)
        except Exception as exc:
            log.exception("Fallo el estudio %s", estudio_id)
            bitacora.cerrar()
            self._terminar(estudio_id, req_id, consecutivo, resultado,
                           f"{exc}\n{traceback.format_exc()[-1500:]}")

    def _terminar(self, estudio_id: int, req_id: int, consecutivo: str, resultado: dict,
                  error: str | None) -> None:
        with sesion() as db:
            e = db.get(EstudioMercado, estudio_id)
            req = db.get(Requerimiento, req_id)
            anterior = next((x for x in reversed(req.estudios)
                             if x.id != e.id and x.estado == "listo"), None)
            if anterior and e.items_ids:
                # Re-estudio parcial: las lineas no re-estudiadas conservan su resultado.
                combinado = dict(anterior.resultado or {})
                combinado.update(resultado)
                resultado = combinado
            e.resultado = resultado
            e.terminado_en = _ahora()
            e.progreso = 100
            if error:
                e.estado = "error"
                e.error = error[:4000]
                e.paso = "Error: " + error.splitlines()[0][:200]
            else:
                e.estado = "listo"
                e.paso = "Estudio de mercado listo"
            if req.estado == "en_estudio":
                req.estado = "estudio_listo"
            servicios.registrar(db, "requerimiento", req.id, None,
                                "estudio_error" if error else "estudio_listo",
                                f"Estudio v{e.version}: " + (e.paso if error else f"{len(resultado)} línea(s)"))
            destinatarios = servicios.usuarios_con_rol(db, "compras") + [req.solicitante]
            if error:
                servicios.notificar(db, servicios.usuarios_con_rol(db, "compras"),
                                    f"Falló el estudio de mercado de {consecutivo}",
                                    "Revise la bitácora y reintente el estudio.",
                                    f"/requerimientos/{req.id}", tipo="error")
            else:
                servicios.notificar(db, destinatarios, f"Estudio de mercado listo: {consecutivo}",
                                    "El agente terminó de cotizar. Ya puede revisar las opciones y "
                                    "la recomendación.", f"/requerimientos/{req.id}", tipo="exito")


class _Bitacora:
    """Escribe el progreso en la BD sin martillarla: agrupa mensajes."""

    def __init__(self, estudio_id: int, total_items: int) -> None:
        self.estudio_id = estudio_id
        self.total = max(1, total_items)
        self.n = 0
        self.fraccion = 0.0
        self.pendientes: list[dict] = []
        self.ultimo = 0.0
        self.paso = ""

    def item(self, n: int, descripcion: str) -> None:
        self.n, self.fraccion = n, 0.0
        self(f"Línea {n + 1} de {self.total}: {descripcion[:80]}")

    def __call__(self, mensaje: str) -> None:
        for clave, f in _PASOS:
            if clave in mensaje:
                self.fraccion = max(self.fraccion, f)
        self.paso = mensaje.strip()[:300]
        self.pendientes.append({"t": _ahora().isoformat(timespec="seconds"), "m": mensaje[:400]})
        if time.monotonic() - self.ultimo > 1.5:
            self._volcar()

    def _volcar(self) -> None:
        if not self.pendientes:
            return
        with sesion() as db:
            e = db.get(EstudioMercado, self.estudio_id)
            e.bitacora = (list(e.bitacora or []) + self.pendientes)[-400:]
            e.paso = self.paso
            e.progreso = round(min(99.0, (self.n + self.fraccion) / self.total * 100), 1)
        self.pendientes = []
        self.ultimo = time.monotonic()

    def cerrar(self) -> None:
        self._volcar()


trabajador = Trabajador()
