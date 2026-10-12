"""Proveedores con API compatible con OpenAI: Groq y NVIDIA NIM.

Los dos hablan el mismo protocolo `/chat/completions`, asi que comparten toda
la implementacion y solo cambian la URL base, la credencial y el modelo.

Se usa HTTP directo en vez del SDK de OpenAI a proposito: el entorno tiene
`openai` 0.28 (anterior a la reescritura 1.x) y actualizarlo romperia otros
proyectos de la maquina. El protocolo es simple y estable; no vale la pena el
riesgo de dependencias por tres llamadas.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from . import config
from .core import Progreso, Uso, _nada
from .limitador import LimitadorTPM, con_reintentos
from .proveedor_comun import AgenteTexto, Respuesta

TIMEOUT = 180

# Sin User-Agent, Cloudflare bloquea a Groq con un 403 "Access denied".
AGENTE_USUARIO = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


@dataclass
class AgenteOpenAICompat(AgenteTexto):
    """Base para cualquier endpoint compatible con OpenAI."""

    proveedor: str = "groq"
    uso: Uso = field(default_factory=Uso)

    @property
    def nombre_modelo(self) -> str:
        return config.modelo_actual(self.proveedor)

    @property
    def _url(self) -> str:
        return config.BASE_URL[self.proveedor].rstrip("/") + "/chat/completions"

    def _completar(
        self,
        mensajes: list[dict],
        *,
        max_tokens: int,
        esfuerzo: str,
        formato_json: bool,
        progreso: Progreso = _nada,
    ) -> Respuesta:
        cuerpo: dict = {
            "model": self.nombre_modelo,
            "messages": mensajes,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }
        if formato_json:
            cuerpo["response_format"] = {"type": "json_object"}
        if config.ADMITE_ESFUERZO.get(self.proveedor):
            cuerpo["reasoning_effort"] = esfuerzo

        def llamar():
            return self._post(cuerpo)

        try:
            datos = con_reintentos(llamar, avisar=progreso)
        except RuntimeError as exc:
            if "reasoning_effort" in str(exc):
                # El modelo no es de razonamiento: repetir sin ese parametro.
                cuerpo.pop("reasoning_effort", None)
                datos = con_reintentos(lambda: self._post(cuerpo), avisar=progreso)
            else:
                raise

        eleccion = (datos.get("choices") or [{}])[0]
        uso = datos.get("usage") or {}
        return Respuesta(
            texto=(eleccion.get("message") or {}).get("content") or "",
            entrada=uso.get("prompt_tokens", 0) or 0,
            salida=uso.get("completion_tokens", 0) or 0,
            motivo_fin=eleccion.get("finish_reason") or "?",
        )

    def _post(self, cuerpo: dict) -> dict:
        clave = config.clave_de(self.proveedor)
        if not clave:
            raise RuntimeError(
                f"Falta {config.nombre_credencial(self.proveedor)} en el entorno o en .env"
            )
        peticion = urllib.request.Request(
            self._url,
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {clave}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": AGENTE_USUARIO,
            },
        )
        try:
            with urllib.request.urlopen(peticion, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detalle = exc.read().decode("utf-8", "replace")[:900]
            # El texto del error viaja en el mensaje para que `con_reintentos`
            # pueda clasificarlo (limite de tasa, cupo diario, 5xx).
            raise RuntimeError(f"Error code: {exc.code} - {detalle}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Connection error: {exc.reason}") from exc


def _uso_de(proveedor: str) -> Uso:
    entrada, salida = config.precios_de(config.modelo_actual(proveedor))
    return Uso(precio_entrada_mtok=entrada, precio_salida_mtok=salida)


@dataclass
class AgenteGroq(AgenteOpenAICompat):
    proveedor: str = "groq"
    uso: Uso = field(default_factory=lambda: _uso_de("groq"))
    # Groq free tier: 8.000 tokens/minuto. Sin este limitador, la corrida muere
    # a la tercera pagina leida.
    limitador: LimitadorTPM | None = field(
        default_factory=lambda: LimitadorTPM(config.GROQ_TPM)
    )


@dataclass
class AgenteNvidia(AgenteOpenAICompat):
    proveedor: str = "nvidia"
    uso: Uso = field(default_factory=lambda: _uso_de("nvidia"))
    # NVIDIA NIM no publica un TPM tan ajustado como Groq; se deja sin limitador
    # y se confia en los reintentos si alguna vez responde 429.
    limitador: LimitadorTPM | None = None
    paginas_por_llamada: int = 3
