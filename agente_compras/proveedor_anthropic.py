"""Implementacion con la API de Anthropic.

La fase de investigacion usa las herramientas de servidor `web_search` y
`web_fetch`: corren en la infraestructura de Anthropic, asi que aqui no hay
que scrapear nada ni manejar bloqueos.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Iterable

import anthropic

from . import config
from .core import AgenteBase, Progreso, Uso, _formatear_precio, _nada, fijar_precio_cotizado
from .models import AnalisisItem, Cotizacion, LineaCotizacion
from .prompts import (
    SISTEMA_EXTRACCION,
    SISTEMA_INVESTIGACION,
    SISTEMA_SINTESIS,
    prompt_investigacion,
    prompt_sintesis,
)


def _cliente() -> anthropic.Anthropic:
    return anthropic.Anthropic(timeout=config.TIMEOUT_SEGUNDOS)


def _uso_inicial() -> Uso:
    entrada, salida = config.precios_de(config.MODELO_ANTHROPIC)
    return Uso(precio_entrada_mtok=entrada, precio_salida_mtok=salida)


@dataclass
class AgenteAnthropic(AgenteBase):
    cliente: anthropic.Anthropic = field(default_factory=_cliente)
    uso: Uso = field(default_factory=_uso_inicial)

    # ------------------------------------------------------------------
    # Fase 1 - lectura
    # ------------------------------------------------------------------
    def extraer(
        self,
        *,
        texto: str | None = None,
        pdf_bytes: bytes | None = None,
        nombre_pdf: str = "cotizacion.pdf",
        progreso: Progreso = _nada,
    ) -> Cotizacion:
        if not texto and not pdf_bytes:
            raise ValueError("Se necesita un PDF o un texto de entrada.")

        contenido: list[dict] = []
        if pdf_bytes:
            progreso(f"Leyendo {nombre_pdf} ({len(pdf_bytes) / 1024:.0f} KB)...")
            contenido.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(pdf_bytes).decode("utf-8"),
                    },
                }
            )
        instruccion = (
            "Extrae la cotizacion del documento adjunto."
            if pdf_bytes
            else "El usuario describe lo que quiere comprar. Estructuralo como una cotizacion."
        )
        if texto:
            instruccion += f"\n\nTexto del usuario:\n{texto}"
        contenido.append({"type": "text", "text": instruccion})

        respuesta = self.cliente.messages.parse(
            model=config.MODELO_ANTHROPIC,
            max_tokens=config.MAX_TOKENS_EXTRACCION,
            system=SISTEMA_EXTRACCION,
            output_config={"effort": config.ESFUERZO_EXTRACCION},
            messages=[{"role": "user", "content": contenido}],
            output_format=Cotizacion,
        )
        self.uso.sumar(respuesta.usage)
        cot = respuesta.parsed_output
        progreso(f"Detectados {len(cot.items)} item(s).")
        return cot

    # ------------------------------------------------------------------
    # Fase 2 - investigacion con herramientas de servidor
    # ------------------------------------------------------------------
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
        herramientas = [
            {"type": "web_search_20260209", "name": "web_search",
             "max_uses": config.MAX_BUSQUEDAS},
            {"type": "web_fetch_20260209", "name": "web_fetch",
             "max_uses": config.MAX_FETCHS},
        ]
        pregunta = prompt_investigacion(
            producto=item.descripcion,
            marca=item.marca,
            modelo=item.modelo,
            categoria=item.categoria,
            especificaciones=item.especificaciones,
            precio=_formatear_precio(item),
            pais=pais,
            moneda=moneda,
            competidores=competidores,
        )

        mensajes: list[dict] = [{"role": "user", "content": pregunta}]
        final = None

        for intento in range(config.MAX_REINTENTOS_PAUSA + 1):
            with self.cliente.messages.stream(
                model=config.MODELO_ANTHROPIC,
                max_tokens=config.MAX_TOKENS_INVESTIGACION,
                system=SISTEMA_INVESTIGACION,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": config.ESFUERZO_INVESTIGACION},
                tools=herramientas,
                messages=mensajes,
            ) as stream:
                for evento in _eventos_legibles(stream):
                    progreso(evento)
                final = stream.get_final_message()

            self.uso.sumar(final.usage)
            mensajes.append({"role": "assistant", "content": final.content})

            if final.stop_reason != "pause_turn":
                break
            progreso(
                f"El turno se pauso, reanudando "
                f"({intento + 1}/{config.MAX_REINTENTOS_PAUSA})..."
            )
        else:
            progreso("Limite de reanudaciones alcanzado; se usa lo investigado hasta ahora.")

        if final is not None and final.stop_reason == "refusal":
            detalle = getattr(final, "stop_details", None)
            categoria = getattr(detalle, "category", "sin categoria")
            raise RuntimeError(f"El modelo declino la peticion ({categoria}).")

        dossier = "\n\n".join(
            bloque.text
            for mensaje in mensajes
            if mensaje["role"] == "assistant"
            for bloque in mensaje["content"]
            if getattr(bloque, "type", None) == "text" and bloque.text.strip()
        )
        if not dossier.strip():
            raise RuntimeError("La investigacion no devolvio texto utilizable.")
        return dossier

    # ------------------------------------------------------------------
    # Fase 3 - veredicto estructurado
    # ------------------------------------------------------------------
    def sintetizar(
        self,
        dossier: str,
        item: LineaCotizacion,
        *,
        pais: str,
        moneda: str,
        progreso: Progreso = _nada,
    ) -> AnalisisItem:
        progreso("Consolidando el veredicto...")
        respuesta = self.cliente.messages.parse(
            model=config.MODELO_ANTHROPIC,
            max_tokens=config.MAX_TOKENS_SINTESIS,
            system=SISTEMA_SINTESIS,
            output_config={"effort": config.ESFUERZO_SINTESIS},
            messages=[
                {
                    "role": "user",
                    "content": prompt_sintesis(
                        dossier,
                        precio_cotizado=_formatear_precio(item),
                        moneda=moneda,
                        pais=pais,
                    ),
                }
            ],
            output_format=AnalisisItem,
        )
        self.uso.sumar(respuesta.usage)
        return fijar_precio_cotizado(respuesta.parsed_output, item, moneda)


# ----------------------------------------------------------------------
# Traduccion del stream a lineas de progreso
# ----------------------------------------------------------------------
def _eventos_legibles(stream: Iterable) -> Iterable[str]:
    parcial = ""
    herramienta = None
    for evento in stream:
        tipo = evento.type
        if tipo == "content_block_start":
            bloque = evento.content_block
            if bloque.type == "server_tool_use":
                herramienta, parcial = bloque.name, ""
            elif bloque.type == "thinking":
                yield "Razonando..."
            elif bloque.type == "text":
                yield "Redactando el dossier..."
        elif tipo == "content_block_delta":
            if evento.delta.type == "input_json_delta" and herramienta:
                parcial += evento.delta.partial_json
        elif tipo == "content_block_stop":
            if herramienta:
                yield _describir_llamada(herramienta, parcial)
                herramienta, parcial = None, ""


def _describir_llamada(nombre: str, json_parcial: str) -> str:
    try:
        datos = json.loads(json_parcial or "{}")
    except json.JSONDecodeError:
        datos = {}
    if nombre == "web_search":
        return "Buscando: " + str(datos.get("query", "..."))
    if nombre == "web_fetch":
        return "Leyendo: " + str(datos.get("url", "..."))
    return f"Herramienta {nombre}"
