"""Contrato comun de los agentes y fabrica de proveedores.

Un agente implementa siempre las mismas tres fases, sin importar el proveedor:

    extraer()      documento o texto libre -> Cotizacion
    investigar()   item -> dossier de texto con URLs
    sintetizar()   dossier -> AnalisisItem

Lo que cambia entre proveedores es COMO se resuelve la fase 2. Con Anthropic,
la busqueda web corre del lado del servidor. Con Groq hay que darle al modelo
herramientas locales (ver `busqueda.py`) y manejar el bucle nosotros.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from . import config
from .models import AnalisisItem, Cotizacion, LineaCotizacion

Progreso = Callable[[str], None]


def _nada(_: str) -> None:
    return None


@dataclass
class Uso:
    """Contabilidad de tokens y costo. Los precios salen de `config.PRECIOS`."""

    entrada: int = 0
    salida: int = 0
    precio_entrada_mtok: float = 0.0
    precio_salida_mtok: float = 0.0

    def sumar(self, usage) -> None:
        if usage is None:
            return
        self.entrada += getattr(usage, "input_tokens", None) or getattr(
            usage, "prompt_tokens", 0
        ) or 0
        self.salida += getattr(usage, "output_tokens", None) or getattr(
            usage, "completion_tokens", 0
        ) or 0

    @property
    def costo_usd(self) -> float:
        return (
            self.entrada / 1_000_000 * self.precio_entrada_mtok
            + self.salida / 1_000_000 * self.precio_salida_mtok
        )


@dataclass
class AgenteBase(ABC):
    uso: Uso = field(default_factory=Uso)

    @abstractmethod
    def extraer(
        self,
        *,
        texto: str | None = None,
        pdf_bytes: bytes | None = None,
        nombre_pdf: str = "cotizacion.pdf",
        progreso: Progreso = _nada,
    ) -> Cotizacion:
        ...

    @abstractmethod
    def investigar(
        self,
        item: LineaCotizacion,
        *,
        pais: str,
        moneda: str,
        competidores: list[str],
        progreso: Progreso = _nada,
        dominios: list[str] | None = None,
    ) -> str:
        ...

    @abstractmethod
    def sintetizar(
        self,
        dossier: str,
        item: LineaCotizacion,
        *,
        pais: str,
        moneda: str,
        progreso: Progreso = _nada,
    ) -> AnalisisItem:
        ...


def crear_agente(proveedor: str | None = None) -> AgenteBase:
    """Devuelve el agente del proveedor configurado.

    Se importa de forma perezosa para que no haga falta tener instalados los
    SDK de todos los proveedores.
    """
    nombre = (proveedor or config.PROVEEDOR).lower()
    if nombre == "gemini":
        from .proveedor_gemini import AgenteGemini

        return AgenteGemini()
    if nombre == "groq":
        from .proveedor_openai_compat import AgenteGroq

        return AgenteGroq()
    if nombre == "nvidia":
        from .proveedor_openai_compat import AgenteNvidia

        return AgenteNvidia()
    if nombre == "anthropic":
        from .proveedor_anthropic import AgenteAnthropic

        return AgenteAnthropic()
    raise ValueError(
        f"Proveedor desconocido: '{nombre}'. Usa uno de {', '.join(config.PROVEEDORES)}."
    )


# ---------------------------------------------------------------------------
# Utilidades compartidas
# ---------------------------------------------------------------------------
def _formatear_precio(item: LineaCotizacion) -> str:
    if item.precio_unitario is None:
        return "no se indico precio (el comprador solo describio lo que quiere comprar)"
    moneda = item.moneda or ""
    return f"{moneda} {item.precio_unitario:,.2f} por unidad x {item.cantidad:g}".strip()


# Desviacion a partir de la cual el rango deja de ser creible. Una diferencia
# asi casi siempre significa que el rango mezclo modelos, estados o monedas, no
# que el vendedor este pidiendo el triple.
DESVIACION_SOSPECHOSA = 80.0

_AVISO_RANGO = (
    "El rango de mercado no es comparable con lo cotizado: la diferencia de "
    "{pct:+.0f}% casi siempre viene de mezclar modelos, anos, estados o monedas "
    "distintas. Verifica los precios en las fuentes antes de decidir."
)


def fijar_precio_cotizado(analisis: AnalisisItem, item: LineaCotizacion, moneda: str) -> AnalisisItem:
    """Ajustes que no se le pueden delegar al modelo.

    1. Repetir el precio de entrada, que el modelo a veces omite.
    2. Recalcular la desviacion en vez de confiar en su aritmetica.
    3. Degradar la confianza cuando la desviacion es absurda. Esto estaba pedido
       en el prompt y el modelo lo ignoraba: reportaba +266% con confianza
       "alta", que es justo el error que mas dano hace -- desaconsejar una
       compra razonable con aplomo. Una regla asi va en codigo, no en el prompt.
    """
    if item.precio_unitario is not None:
        analisis.precio_cotizado = item.precio_unitario
        analisis.moneda_cotizada = item.moneda or moneda

    tipico = analisis.rango_mercado.tipico
    cotizado = analisis.precio_cotizado
    misma_moneda = (
        analisis.moneda_cotizada or ""
    ).upper() == (analisis.rango_mercado.moneda or "").upper()

    if cotizado and tipico and misma_moneda:
        analisis.desviacion_pct = (cotizado - tipico) / tipico * 100.0

    desviacion = analisis.desviacion_pct
    if desviacion is not None and abs(desviacion) > DESVIACION_SOSPECHOSA:
        analisis.confianza_analisis = "baja"
        analisis.rango_mercado.confianza = "baja"
        aviso = _AVISO_RANGO.format(pct=desviacion)
        if not any("no es comparable" in b for b in analisis.banderas_rojas):
            analisis.banderas_rojas.insert(0, aviso)
    return analisis
