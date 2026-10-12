"""Preflight: confirma que todo esta listo antes de la primera corrida real.

Prueba el proveedor configurado en AGENTE_PROVEEDOR (gemini, groq, nvidia o
anthropic): credencial, modelo vigente, modo JSON y busqueda web.

    python scripts/verificar.py
    python scripts/verificar.py --todos    # prueba todos los que tengan key
"""
from __future__ import annotations

import json
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from agente_compras import config  # noqa: E402

OK, FALLA, AVISO = "[ok]   ", "[FALLA]", "[aviso]"

# Peticion de tamano realista: un "hola" no revela si quedan tokens del dia.
RELLENO = "producto " * 800


def paso_dependencias(proveedor: str) -> bool:
    base = ["pydantic", "dotenv", "streamlit", "ddgs", "fitz"]
    extra = {"gemini": ["google.genai"], "anthropic": ["anthropic"]}.get(proveedor, [])
    faltan = []
    for modulo in base + extra:
        try:
            __import__(modulo)
        except ImportError:
            faltan.append(modulo)
    if faltan:
        print(f"{FALLA} faltan dependencias: {', '.join(faltan)}")
        print("        pip install -r requirements.txt")
        return False
    print(f"{OK} dependencias instaladas")
    return True


def paso_credencial(proveedor: str) -> bool:
    nombre = config.nombre_credencial(proveedor)
    if not config.hay_credenciales(proveedor):
        print(f"{FALLA} no hay {nombre}")
        print(f"        se obtiene en {config.DONDE_CONSEGUIRLA.get(proveedor, '')}")
        print(f"        ponla en .env como  {nombre}=...")
        otros = [p for p in config.proveedores_disponibles() if p != proveedor]
        if otros:
            print(f"        o cambia a uno que si tiene key: AGENTE_PROVEEDOR={otros[0]}")
        return False
    print(f"{OK} credencial {nombre} detectada")
    return True


def paso_modelo(proveedor: str) -> bool:
    """Una llamada de texto y otra en modo JSON, que es lo que usa el agente."""
    from agente_compras.core import crear_agente

    try:
        agente = crear_agente(proveedor)
    except Exception as exc:
        print(f"{FALLA} no se pudo crear el agente: {exc}")
        return False

    modelo = config.modelo_actual(proveedor)
    mensajes = [
        {"role": "system", "content": "Responde en una palabra."},
        {"role": "user", "content": RELLENO + "\nDi: listo"},
    ]
    try:
        r = agente._completar(mensajes, max_tokens=64, esfuerzo="low",
                              formato_json=False, progreso=lambda _: None)
    except Exception as exc:
        texto = str(exc)
        if "per day" in texto or "tokens per day" in texto:
            print(f"{FALLA} '{modelo}' agoto su cuota de tokens del dia")
        elif "404" in texto or "not found" in texto.lower():
            print(f"{FALLA} el modelo '{modelo}' no existe para esta cuenta")
            print(f"        ajusta el modelo en .env y vuelve a correr")
        else:
            print(f"{FALLA} el modelo no respondio: {texto[:250]}")
        _sugerir_alternativa(proveedor)
        return False
    if not r.texto.strip():
        print(f"{AVISO} el modelo respondio vacio (fin={r.motivo_fin}). "
              "El agente reintenta solo, pero valida con una corrida real.")
    else:
        print(f"{OK} modelo {modelo} responde ({r.entrada}+{r.salida} tokens)")

    # Modo JSON: lo usan la extraccion y el veredicto.
    mensajes_json = [
        {"role": "system", "content": "Responde solo json valido."},
        {"role": "user", "content": 'Devuelve este json: {"ok": true, "n": 5}'},
    ]
    try:
        r = agente._completar(mensajes_json, max_tokens=512, esfuerzo="low",
                              formato_json=True, progreso=lambda _: None)
        json.loads(r.texto[r.texto.find("{") : r.texto.rfind("}") + 1])
    except Exception as exc:
        print(f"{FALLA} el modelo no soporta modo JSON: {str(exc)[:200]}")
        print("        prueba otro modelo; el agente lo necesita para el veredicto")
        return False
    print(f"{OK} modo JSON operativo")
    return True


def _sugerir_alternativa(proveedor: str) -> None:
    otros = [p for p in config.proveedores_disponibles() if p != proveedor]
    if otros:
        print(f"        tienes key de: {', '.join(otros)}")
        print(f"        prueba  AGENTE_PROVEEDOR={otros[0]}  en .env")


def paso_busqueda() -> bool:
    """La busqueda corre en esta maquina para todos los proveedores menos Anthropic."""
    from agente_compras import busqueda, tiendas

    resultados = busqueda.buscar("nevera no frost samsung", max_resultados=3)
    utiles = [r for r in resultados if r.url]
    if not utiles:
        print(f"{FALLA} el buscador no devolvio resultados")
        print("        si es rate limit de DuckDuckGo, espera un minuto, o usa Tavily:")
        print("        AGENTE_BUSCADOR=tavily y TAVILY_API_KEY=... en .env")
        return False
    print(f"{OK} busqueda web ({len(utiles)} resultados)")

    # Lo importante para esta herramienta: poder buscar dentro de una tienda.
    dominios = [t.dominio for t in tiendas.por_defecto(config.PAIS_DEFAULT)[:3]]
    por_tienda = busqueda.buscar_en_tiendas("nevera samsung", dominios, por_tienda=1)
    if not por_tienda:
        print(f"{AVISO} la busqueda por tienda no devolvio nada. Puede ser el buscador; "
              "valida con una corrida real.")
    else:
        print(f"{OK} busqueda dentro de tiendas ({len(por_tienda)} de {len(dominios)}: "
              f"{', '.join(por_tienda)})")

    texto = busqueda.leer(utiles[0].url)
    if texto.startswith(("El sitio respondio", "No se pudo leer")):
        print(f"{AVISO} la primera pagina bloqueo la lectura. Es normal; "
              "el agente sigue con otras fuentes.")
    else:
        print(f"{OK} lectura de paginas ({len(texto)} caracteres)")
    return True


def verificar(proveedor: str) -> bool:
    print(f"\nProveedor: {proveedor}  |  Modelo: {config.modelo_actual(proveedor)}")
    print("-" * 60)
    if not paso_dependencias(proveedor):
        return False
    if not paso_credencial(proveedor):
        return False
    if proveedor == "anthropic":
        print(f"{OK} la busqueda web corre del lado de Anthropic; no se prueba local")
        return paso_modelo(proveedor)
    return paso_modelo(proveedor) and paso_busqueda()


def main() -> int:
    print("Verificando el asistente de compras")
    disponibles = config.proveedores_disponibles()
    print(f"Proveedores con credencial: {', '.join(disponibles) or 'ninguno'}")

    if "--todos" in sys.argv:
        if not disponibles:
            print(f"\n{FALLA} no hay ninguna credencial configurada. Copia .env.example a .env.")
            return 1
        resultados = {p: verificar(p) for p in disponibles}
        print("\n" + "=" * 60)
        for p, ok in resultados.items():
            print(f"  {'LISTO ' if ok else 'FALLA '} {p}")
        return 0 if any(resultados.values()) else 1

    if not verificar(config.PROVEEDOR):
        return 1

    pdf = RAIZ / "ejemplos" / "cotizacion_ejemplo.pdf"
    print(f"{OK if pdf.exists() else AVISO} cotizacion de ejemplo "
          f"{'lista' if pdf.exists() else 'no generada'}")
    print("-" * 60)
    print("Todo listo.\n")
    print("  streamlit run app.py")
    print('  python cli.py "una nevera Samsung no frost de 300 litros"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
