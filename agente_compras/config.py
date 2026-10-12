"""Configuracion central del agente de compras."""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Proveedor de inferencia: "gemini" | "groq" | "nvidia" | "anthropic"
# Gemini es el default porque su cuota de free tier es la que aguanta una
# corrida completa sin quedarse esperando cupo.
PROVEEDOR = os.getenv("AGENTE_PROVEEDOR", "gemini").lower()

PROVEEDORES = ("gemini", "groq", "nvidia", "anthropic")

# --- Modelos ---------------------------------------------------------------
# Los alias `-latest` evitan que se rompa al retirarse una version concreta
# (gemini-2.5-flash quedo cerrado para cuentas nuevas). Se usa el "lite" porque
# su cuota diaria de free tier es mucho mayor: `gemini-flash-latest` resuelve
# al flash de punta, que da solo 20 peticiones por dia.
MODELO_GEMINI = os.getenv("AGENTE_GEMINI_MODELO", "gemini-flash-lite-latest")
MODELO_GROQ = os.getenv("AGENTE_GROQ_MODELO", "openai/gpt-oss-120b")
MODELO_NVIDIA = os.getenv("AGENTE_NVIDIA_MODELO", "nvidia/nemotron-3-super-120b-a12b")
MODELO_ANTHROPIC = os.getenv("AGENTE_MODELO", "claude-opus-5")

BASE_URL = {
    "groq": "https://api.groq.com/openai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}

# Que proveedores aceptan el parametro `reasoning_effort`.
ADMITE_ESFUERZO = {"groq": True, "nvidia": False}

CREDENCIAL = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "groq": ("GROQ_API_KEY",),
    "nvidia": ("NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
}

DONDE_CONSEGUIRLA = {
    "gemini": "aistudio.google.com/apikey (free tier amplio)",
    "groq": "console.groq.com/keys (gratis, pero 8.000 tokens/minuto)",
    "nvidia": "build.nvidia.com (gratis con creditos)",
    "anthropic": "console.anthropic.com (requiere credito)",
}

# Esfuerzo de razonamiento (solo Anthropic): low | medium | high | xhigh | max
ESFUERZO_EXTRACCION = os.getenv("AGENTE_ESFUERZO_EXTRACCION", "low")
ESFUERZO_INVESTIGACION = os.getenv("AGENTE_ESFUERZO_INVESTIGACION", "high")
ESFUERZO_SINTESIS = os.getenv("AGENTE_ESFUERZO_SINTESIS", "high")

# --- Limites de investigacion ---------------------------------------------
MAX_BUSQUEDAS = int(os.getenv("AGENTE_MAX_BUSQUEDAS", "8"))
MAX_FETCHS = int(os.getenv("AGENTE_MAX_FETCHS", "6"))
MAX_TIENDAS = int(os.getenv("AGENTE_MAX_TIENDAS", "6"))

MAX_REINTENTOS_PAUSA = 4

# --- Tokens ----------------------------------------------------------------
MAX_TOKENS_EXTRACCION = 8_000
MAX_TOKENS_INVESTIGACION = 32_000
MAX_TOKENS_SINTESIS = 16_000
# Salida de las llamadas en modo JSON. El esquema del analisis es grande.
MAX_TOKENS_JSON = int(os.getenv("AGENTE_MAX_TOKENS_JSON", "8000"))
MAX_TOKENS_GROQ = int(os.getenv("AGENTE_GROQ_MAX_TOKENS", "5000"))

# Tokens por minuto del plan de Groq (free tier: 8.000).
GROQ_TPM = int(os.getenv("AGENTE_GROQ_TPM", "8000"))

TIMEOUT_SEGUNDOS = float(os.getenv("AGENTE_TIMEOUT", "1800"))

# --- Contexto comercial ----------------------------------------------------
PAIS_DEFAULT = os.getenv("AGENTE_PAIS", "Colombia")
MONEDA_DEFAULT = os.getenv("AGENTE_MONEDA", "COP")

# --- Precios por millon de tokens (USD) ------------------------------------
# Los free tier quedan en 0; el costo solo importa en los planes de pago.
PRECIOS: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def precios_de(modelo: str) -> tuple[float, float]:
    entrada = os.getenv("AGENTE_PRECIO_ENTRADA")
    salida = os.getenv("AGENTE_PRECIO_SALIDA")
    if entrada and salida:
        return float(entrada), float(salida)
    return PRECIOS.get(modelo, (0.0, 0.0))


def modelo_actual(proveedor: str | None = None) -> str:
    return {
        "gemini": MODELO_GEMINI,
        "groq": MODELO_GROQ,
        "nvidia": MODELO_NVIDIA,
        "anthropic": MODELO_ANTHROPIC,
    }.get(proveedor or PROVEEDOR, MODELO_GEMINI)


def clave_de(proveedor: str | None = None) -> str | None:
    for nombre in CREDENCIAL.get(proveedor or PROVEEDOR, ()):
        valor = os.getenv(nombre)
        if valor:
            return valor
    return None


def hay_credenciales(proveedor: str | None = None) -> bool:
    return bool(clave_de(proveedor))


def nombre_credencial(proveedor: str | None = None) -> str:
    nombres = CREDENCIAL.get(proveedor or PROVEEDOR, ("API_KEY",))
    return nombres[0]


def proveedores_disponibles() -> list[str]:
    """Los que tienen credencial cargada, en orden de preferencia."""
    return [p for p in PROVEEDORES if hay_credenciales(p)]
