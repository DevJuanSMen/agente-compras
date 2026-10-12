"""Proveedor Gemini (google-genai).

Es el recomendado para trabajar con free tier: su cuota por minuto es de orden
de magnitud mayor que la de Groq, asi que el agente no se queda esperando cupo
ni se agota a las pocas consultas.

El contrato con `AgenteTexto` es una sola funcion: mandar mensajes, devolver
texto. Aqui se traduce el formato de OpenAI (roles system/user/assistant) al
de Gemini (system_instruction aparte + contents con roles user/model).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import config
from .core import Progreso, Uso, _nada
from .limitador import con_reintentos
from .proveedor_comun import AgenteTexto, Respuesta


def _cliente():
    from google import genai

    clave = config.clave_de("gemini")
    if not clave:
        raise RuntimeError("Falta GEMINI_API_KEY en el entorno o en .env")
    return genai.Client(api_key=clave)


def _uso_inicial() -> Uso:
    entrada, salida = config.precios_de(config.MODELO_GEMINI)
    return Uso(precio_entrada_mtok=entrada, precio_salida_mtok=salida)


@dataclass
class AgenteGemini(AgenteTexto):
    cliente: object = field(default_factory=_cliente)
    uso: Uso = field(default_factory=_uso_inicial)
    # El free tier de Gemini limita peticiones por dia, no tokens: conviene
    # mandar todas las paginas en una sola llamada y gastar contexto, no cuota.
    paginas_por_llamada: int = 0  # 0 = todas juntas
    # Se apaga sola en la primera llamada si el modelo la rechaza.
    admite_thinking_config: bool = True

    @property
    def nombre_modelo(self) -> str:
        return config.MODELO_GEMINI

    def _completar(
        self,
        mensajes: list[dict],
        *,
        max_tokens: int,
        esfuerzo: str,
        formato_json: bool,
        progreso: Progreso = _nada,
    ) -> Respuesta:
        from google.genai import types

        sistema, contenidos = _traducir(mensajes)

        cfg: dict = {
            "max_output_tokens": max_tokens,
            "temperature": 0.2,
        }
        if sistema:
            cfg["system_instruction"] = sistema
        if formato_json:
            cfg["response_mime_type"] = "application/json"
        # Los modelos "thinking" gastan presupuesto razonando; en extraccion
        # queremos el texto, no el razonamiento. Pero no todos lo aceptan: los
        # "lite" rechazan thinking_budget con un 400 generico que ni siquiera
        # menciona thinking, asi que hay que descubrirlo probando.
        if esfuerzo == "low" and self.admite_thinking_config:
            cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

        def llamar():
            return self.cliente.models.generate_content(
                model=config.MODELO_GEMINI,
                contents=contenidos,
                config=types.GenerateContentConfig(**cfg),
            )

        try:
            r = con_reintentos(llamar, avisar=progreso)
        except Exception as exc:
            es_400 = "INVALID_ARGUMENT" in str(exc) or "400" in str(exc)
            if es_400 and "thinking_config" in cfg:
                # Se anota para no repetir la llamada fallida en cada paso.
                self.admite_thinking_config = False
                cfg.pop("thinking_config")
                progreso("Este modelo no acepta desactivar el razonamiento; se omite.")
                r = con_reintentos(llamar, avisar=progreso)
            else:
                raise

        uso = getattr(r, "usage_metadata", None)
        return Respuesta(
            texto=_texto_de(r),
            entrada=getattr(uso, "prompt_token_count", 0) or 0,
            salida=getattr(uso, "candidates_token_count", 0) or 0,
            motivo_fin=str(_motivo_fin(r)),
        )


def _traducir(mensajes: list[dict]) -> tuple[str, list[dict]]:
    """OpenAI (system/user/assistant) -> Gemini (system aparte, user/model)."""
    sistema = "\n\n".join(m["content"] for m in mensajes if m["role"] == "system")
    contenidos = [
        {"role": "model" if m["role"] == "assistant" else "user",
         "parts": [{"text": m["content"]}]}
        for m in mensajes
        if m["role"] != "system"
    ]
    return sistema, contenidos


def _texto_de(respuesta) -> str:
    """`.text` puede venir vacio o lanzar; se arma desde las partes si hace falta."""
    try:
        directo = respuesta.text
        if directo:
            return directo
    except Exception:
        pass
    trozos: list[str] = []
    for cand in getattr(respuesta, "candidates", None) or []:
        contenido = getattr(cand, "content", None)
        for parte in getattr(contenido, "parts", None) or []:
            texto = getattr(parte, "text", None)
            if texto:
                trozos.append(texto)
    return "".join(trozos)


def _motivo_fin(respuesta) -> str:
    for cand in getattr(respuesta, "candidates", None) or []:
        motivo = getattr(cand, "finish_reason", None)
        if motivo:
            return getattr(motivo, "name", str(motivo))
    return "?"
