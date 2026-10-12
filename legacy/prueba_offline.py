"""Prueba el pipeline y el render sin gastar llamadas a la API.

Sustituye las tres fases del Agente por datos enlatados y verifica que
los esquemas, la orquestacion y el formateo funcionan de punta a punta.

    python scripts/prueba_offline.py
"""
from __future__ import annotations

import pathlib
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from agente_compras import core, models  # noqa: E402
from agente_compras.ejemplo import ANALISIS, COTIZACION  # noqa: E402
from agente_compras.pipeline import analizar, competidores_sugeridos  # noqa: E402

class AgenteFalso(core.AgenteBase):
    """Agente con las tres fases enlatadas; no toca la red."""

    def __init__(self) -> None:
        self.uso = core.Uso(
            entrada=41_200, salida=9_800,
            precio_entrada_mtok=5.0, precio_salida_mtok=25.0,
        )

    def extraer(self, **kw):
        kw.get("progreso", lambda _: None)("Leyendo (simulado)...")
        return COTIZACION

    def investigar(self, item, **kw):
        p = kw.get("progreso", lambda _: None)
        for linea in ("Buscando: Caterpillar 320 GC precio usado",
                      "Leyendo: https://ejemplo.test/mt",
                      "Redactando el dossier..."):
            p(linea)
        return "DOSSIER SIMULADO"

    def sintetizar(self, dossier, item, **kw):
        kw.get("progreso", lambda _: None)("Consolidando el veredicto...")
        return ANALISIS


def probar_eventos() -> None:
    """Verifica el traductor de eventos de stream a lineas de progreso."""
    from agente_compras.proveedor_anthropic import _eventos_legibles as _eventos_anthropic

    def ev(tipo, **kw):
        return types.SimpleNamespace(type=tipo, **kw)

    stream = [
        ev("content_block_start", content_block=types.SimpleNamespace(type="thinking")),
        ev("content_block_stop"),
        ev("content_block_start",
           content_block=types.SimpleNamespace(type="server_tool_use", name="web_search")),
        ev("content_block_delta",
           delta=types.SimpleNamespace(type="input_json_delta", partial_json='{"query": "CAT 320')),
        ev("content_block_delta",
           delta=types.SimpleNamespace(type="input_json_delta", partial_json=' GC precio"}')),
        ev("content_block_stop"),
        ev("content_block_start",
           content_block=types.SimpleNamespace(type="server_tool_use", name="web_fetch")),
        ev("content_block_delta",
           delta=types.SimpleNamespace(type="input_json_delta", partial_json='{"url":"https://x.test"}')),
        ev("content_block_stop"),
        ev("content_block_start", content_block=types.SimpleNamespace(type="text")),
        ev("content_block_delta", delta=types.SimpleNamespace(type="text_delta", text="hola")),
        ev("content_block_stop"),
    ]
    salida = list(_eventos_anthropic(stream))
    esperado = [
        "Razonando...",
        "Buscando: CAT 320 GC precio",
        "Leyendo: https://x.test",
        "Redactando el dossier...",
    ]
    assert salida == esperado, f"eventos inesperados: {salida}"
    print("[ok] traductor de eventos de stream")


def probar_precio() -> None:
    sin_precio = models.LineaCotizacion(
        descripcion="x", marca=None, modelo=None, categoria="y",
        cantidad=1, precio_unitario=None, moneda=None, especificaciones=[],
    )
    assert "no se indico precio" in core._formatear_precio(sin_precio)
    assert core._formatear_precio(COTIZACION.items[0]) == "USD 165,000.00 por unidad x 1"
    print("[ok] formateo de precio")


def probar_categorias() -> None:
    assert "Hitachi" in competidores_sugeridos("excavadora sobre orugas")
    assert "Lenovo" in competidores_sugeridos("computador portatil")
    assert competidores_sugeridos("resma de papel carta") == []
    print("[ok] deduccion de marcas rivales")


def probar_costo() -> None:
    u = core.Uso(entrada=1_000_000, salida=1_000_000,
                 precio_entrada_mtok=5.0, precio_salida_mtok=25.0)
    assert abs(u.costo_usd - 30.0) < 1e-9, u.costo_usd
    print("[ok] calculo de costo")


def probar_pipeline() -> None:
    informe = analizar(
        texto="excavadora CAT 320 GC en USD 165.000",
        agente=AgenteFalso(),
        max_items=1,
        progreso=lambda l: print(f"    - {l}"),
    )
    assert informe.cotizacion is not None
    assert len(informe.analisis) == 1
    assert informe.costo_usd > 0
    # El JSON debe serializar completo (es lo que descarga la UI).
    datos = informe.model_dump()
    assert datos["analisis"][0]["alternativas"][0]["marca"] == "Hitachi"
    print(f"[ok] pipeline completo - costo simulado US$ {informe.costo_usd:.2f}")
    return informe


def probar_render_cli(informe) -> None:
    """Reusa el formateo del CLI para asegurar que no rompe con datos reales."""
    a = informe.analisis[0]
    linea = (f"{a.marca} {a.modelo} | {a.recomendacion} | {a.veredicto_precio} "
             f"({a.desviacion_pct:+.1f}%) | global {a.calificacion_global}/5")
    assert "Caterpillar 320 GC" in linea
    print(f"[ok] render: {linea}")


if __name__ == "__main__":
    probar_eventos()
    probar_precio()
    probar_categorias()
    probar_costo()
    inf = probar_pipeline()
    probar_render_cli(inf)
    print("\nTodo verde.")
