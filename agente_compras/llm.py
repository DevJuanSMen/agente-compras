"""Cadena de modelos con respaldo.

Los free tier se saturan (Gemini 503/429, Groq 8k TPM) y los proveedores
retiran modelos sin aviso. Un estudio de mercado no puede caerse por eso: si
el primer proveedor falla, se intenta con el siguiente que tenga credencial.

Orden: el de `AGENTE_PROVEEDOR` primero, luego el resto de los configurados.
"""
from __future__ import annotations

import threading
from typing import Callable, TypeVar

from pydantic import BaseModel

from . import config
from .core import crear_agente

T = TypeVar("T", bound=BaseModel)
Progreso = Callable[[str], None]


def _nada(_: str) -> None:
    return None


class SinModeloDisponible(RuntimeError):
    pass


class CadenaLLM:
    def __init__(self, proveedores: list[str] | None = None) -> None:
        if proveedores is None:
            disponibles = config.proveedores_disponibles()
            preferido = config.PROVEEDOR
            proveedores = ([preferido] if preferido in disponibles else []) + [
                p for p in disponibles if p != preferido and p != "anthropic"
            ]
            if "anthropic" in disponibles and "anthropic" not in proveedores:
                proveedores.append("anthropic")
        self.proveedores = proveedores
        self._agentes: dict[str, object] = {}
        self._caidos: set[str] = set()
        self._candado = threading.Lock()

    @property
    def hay_modelo(self) -> bool:
        return bool(self.proveedores)

    def _agente(self, nombre: str):
        with self._candado:
            if nombre not in self._agentes:
                self._agentes[nombre] = crear_agente(nombre)
            return self._agentes[nombre]

    def _descartar_si_definitivo(self, nombre: str, exc: Exception) -> None:
        """Un cupo diario agotado o una credencial invalida no se arreglan en
        este estudio: se salta ese proveedor en las llamadas siguientes. Un 503
        pasajero, en cambio, no lo descarta."""
        from .limitador import CupoDiarioAgotado

        texto = str(exc)
        if isinstance(exc, CupoDiarioAgotado) or "Falta" in texto or " 401" in texto or " 403" in texto:
            self._caidos.add(nombre)

    def _en_orden(self) -> list[str]:
        vivos = [p for p in self.proveedores if p not in self._caidos]
        return vivos or list(self.proveedores)

    def json(self, *, sistema: str, usuario: str, esquema: type[T],
             progreso: Progreso = _nada) -> T:
        errores = []
        for nombre in self._en_orden():
            try:
                agente = self._agente(nombre)
                return agente._pedir_json(sistema=sistema, usuario=usuario, esquema=esquema,
                                          progreso=progreso)
            except Exception as exc:  # cupo, red, json invalido: pasar al siguiente
                errores.append(f"{nombre}: {str(exc)[:160]}")
                self._descartar_si_definitivo(nombre, exc)
                progreso(f"Modelo {nombre} no disponible, probando el siguiente...")
        raise SinModeloDisponible("Ningun modelo respondio. " + " | ".join(errores))

    def texto(self, *, sistema: str, usuario: str, max_tokens: int = 1500,
              progreso: Progreso = _nada) -> str:
        errores = []
        for nombre in self._en_orden():
            try:
                agente = self._agente(nombre)
                mensajes = [{"role": "system", "content": sistema},
                            {"role": "user", "content": usuario}]
                salida = agente._pedir_texto(mensajes, max_tokens=max_tokens, esfuerzo="low",
                                             progreso=progreso)
                if salida:
                    return salida
                errores.append(f"{nombre}: respuesta vacia")
            except Exception as exc:
                errores.append(f"{nombre}: {str(exc)[:160]}")
                self._descartar_si_definitivo(nombre, exc)
        raise SinModeloDisponible("Ningun modelo respondio. " + " | ".join(errores))
