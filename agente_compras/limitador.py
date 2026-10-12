"""Control de tasa por tokens/minuto.

El free tier de Groq da 8.000 tokens por minuto y 1.000 peticiones por minuto.
Es decir: las peticiones sobran y los tokens escasean. Eso obliga a dos cosas,
y las dos viven aqui:

  1. Esperar antes de cada llamada si la ventana de 60 s ya esta llena.
  2. Reintentar con espera cuando el servidor igual responde 429/413.
"""
from __future__ import annotations

import re
import time
from collections import deque
from typing import Callable, TypeVar

T = TypeVar("T")

# Fraccion del limite que usamos; el resto es colchon porque nuestra estimacion
# de tokens de entrada es aproximada.
MARGEN = 0.80


def estimar_tokens(texto: str) -> int:
    """Aproximacion barata: ~4 caracteres por token."""
    return max(1, len(texto) // 4)


def estimar_tokens_mensajes(mensajes: list[dict]) -> int:
    total = 0
    for m in mensajes:
        contenido = m.get("content") or ""
        if isinstance(contenido, str):
            total += estimar_tokens(contenido)
        total += 4  # sobrecarga por mensaje
    return total


class LimitadorTPM:
    """Ventana deslizante de 60 segundos sobre los tokens consumidos."""

    def __init__(self, limite_por_minuto: int = 8_000, margen: float = MARGEN) -> None:
        self.limite = int(limite_por_minuto * margen)
        self.ventana: deque[tuple[float, int]] = deque()

    def _purgar(self, ahora: float) -> None:
        while self.ventana and ahora - self.ventana[0][0] > 60.0:
            self.ventana.popleft()

    @property
    def usados(self) -> int:
        self._purgar(time.monotonic())
        return sum(t for _, t in self.ventana)

    def esperar_cupo(self, tokens: int, avisar: Callable[[str], None] | None = None) -> None:
        """Bloquea hasta que quepan `tokens` en la ventana."""
        while True:
            ahora = time.monotonic()
            self._purgar(ahora)
            usados = sum(t for _, t in self.ventana)
            if usados + tokens <= self.limite or not self.ventana:
                return
            espera = 60.0 - (ahora - self.ventana[0][0]) + 0.5
            if avisar:
                avisar(f"Limite de tokens por minuto: esperando {espera:.0f}s "
                       f"({usados}/{self.limite} usados)")
            time.sleep(max(0.5, espera))

    def registrar(self, tokens: int) -> None:
        self.ventana.append((time.monotonic(), tokens))


def segundos_sugeridos(mensaje_error: str, tope: float = 70.0) -> float:
    """Saca el 'try again in ...' de Groq.

    El formato varia: "6.9s", "16m19.776s", "28m48s". Leer solo los segundos
    hace esperar 20s contra un limite que necesita 16 minutos.
    """
    # Groq: "try again in 6.9s" / "try again in 16m19.776s"
    # Gemini: "Please retry in 42.770923115s" y retryDelay: '42s'
    for patron in (r"try again in\s+(?:(\d+)m)?\s*([\d.]+)s",
                   r"retry in\s+(?:(\d+)m)?\s*([\d.]+)s",
                   r"retryDelay['\"]?:\s*['\"]?(?:(\d+)m)?([\d.]+)s"):
        m = re.search(patron, mensaje_error, re.IGNORECASE)
        if m:
            minutos = int(m.group(1) or 0)
            return min(tope, minutos * 60 + float(m.group(2)) + 1.0)
    return 20.0


def es_limite_diario(mensaje_error: str) -> bool:
    """Un cupo por dia no se recupera esperando unos segundos.

    Groq lo dice como "tokens per day (TPD)". Gemini usa el quotaId
    `GenerateRequestsPerDayPerProjectPerModel-FreeTier`. Pero Gemini repone de
    forma continua: si su propio mensaje sugiere una espera corta, conviene
    esperar en vez de abortar.
    """
    if "tokens per day" in mensaje_error or "(TPD)" in mensaje_error:
        return True
    if "PerDay" in mensaje_error or "RequestsPerDay" in mensaje_error:
        # Solo se considera agotado si la espera sugerida es larga de verdad.
        return segundos_sugeridos(mensaje_error, tope=86_400.0) > 300.0
    return False


class CupoDiarioAgotado(RuntimeError):
    """El plan gasto su cuota del dia. Reintentar no sirve de nada."""


def _clasificar(exc: Exception) -> tuple[bool, float, str]:
    """(reintentable, segundos a esperar, motivo)."""
    texto = str(exc)
    if es_limite_diario(texto):
        return False, 0.0, "cupo diario agotado"
    if (
        "rate_limit_exceeded" in texto
        or "Request too large" in texto
        or "RESOURCE_EXHAUSTED" in texto   # Gemini
        or "429" in texto
    ):
        return True, segundos_sugeridos(texto), "limite de tasa"
    # Un parpadeo de red no debe costar el item entero: una corrida completa
    # hace decenas de llamadas y basta una caida de DNS para perderlo todo.
    if any(
        p in texto.lower()
        for p in ("connection error", "getaddrinfo", "timed out", "timeout",
                  "temporarily unavailable", "connection reset", "connection aborted")
    ) or type(exc).__name__ in ("APIConnectionError", "APITimeoutError", "InternalServerError"):
        return True, 5.0, "problema de red"
    if any(c in texto for c in (" 500", " 502", " 503", " 504")):
        return True, 10.0, "error del servidor"
    return False, 0.0, ""


def con_reintentos(
    fn: Callable[[], T],
    *,
    intentos: int = 4,
    avisar: Callable[[str], None] | None = None,
) -> T:
    """Ejecuta `fn`, reintentando limites de tasa y fallas transitorias de red."""
    for intento in range(1, intentos + 1):
        try:
            return fn()
        except Exception as exc:
            reintentable, espera, motivo = _clasificar(exc)
            if motivo == "cupo diario agotado":
                espera_real = segundos_sugeridos(str(exc), tope=86_400.0)
                raise CupoDiarioAgotado(
                    "Se agoto la cuota del dia de este modelo. "
                    f"Se libera en unos {espera_real / 60:.0f} minutos. Mientras tanto: "
                    "cambia de modelo (cada uno tiene su propia cuota), cambia de "
                    "proveedor con AGENTE_PROVEEDOR, o sube de plan."
                ) from exc
            if not reintentable or intento == intentos:
                raise
            if avisar:
                avisar(f"{motivo.capitalize()}, reintentando en {espera:.0f}s "
                       f"({intento}/{intentos - 1})")
            time.sleep(espera)
    raise AssertionError("inalcanzable")  # pragma: no cover
