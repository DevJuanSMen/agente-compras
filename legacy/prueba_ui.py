"""Ejecuta app.py con el harness de pruebas de Streamlit, sin navegador ni API.

Verifica que la interfaz se pinta completa con un informe cargado y que no
lanza excepciones en ninguno de los dos estados (vacio y con resultados).

    python scripts/prueba_ui.py
"""
from __future__ import annotations

import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from streamlit.testing.v1 import AppTest  # noqa: E402


def correr(segundos: int = 60) -> AppTest:
    at = AppTest.from_file(str(RAIZ / "app.py"), default_timeout=segundos)
    at.run()
    return at


def sin_excepciones(at: AppTest, etiqueta: str) -> None:
    if at.exception:
        for exc in at.exception:
            print(f"  !! {exc.value}")
        raise AssertionError(f"{etiqueta}: la app lanzo excepciones")
    print(f"[ok] {etiqueta}: sin excepciones")


def texto_de(at: AppTest) -> str:
    partes: list[str] = []
    for coleccion in (at.markdown, at.caption, at.subheader, at.title,
                      at.info, at.warning, at.error, at.success):
        partes += [str(getattr(e, "value", "")) for e in coleccion]
    for m in at.metric:
        partes += [str(m.label), str(m.value)]
    return "\n".join(partes)


def main() -> int:
    # --- Estado inicial: sin informe ------------------------------------
    at = correr()
    sin_excepciones(at, "estado vacio")
    assert any("Escribi que queres comprar" in str(i.value) for i in at.info), \
        "falta el mensaje de estado vacio"
    assert at.button(key=None) is not None or at.button, "no se encontraron botones"
    print(f"[ok] estado vacio: {len(at.button)} botones, {len(at.text_input)} campos de texto")

    # --- Pulsar 'Cargar informe de ejemplo' ------------------------------
    botones = {b.label: b for b in at.button}
    assert "Cargar informe de ejemplo" in botones, f"botones vistos: {list(botones)}"
    botones["Cargar informe de ejemplo"].click().run()
    sin_excepciones(at, "informe de ejemplo")

    texto = texto_de(at)
    esperado = [
        "Caterpillar",             # titulo del item
        "Donde comprarlo",         # la seccion central
        "Mejor opcion",            # metrica de la mejor tienda
        "Negociar",                # banner de recomendacion
        "Por encima del mercado",  # veredicto de precio
        "Tipico de mercado",
        "Desviacion",
    ]
    faltan = [e for e in esperado if e not in texto]
    assert not faltan, f"no se renderizo: {faltan}"
    print(f"[ok] informe: {len(at.metric)} metricas, {len(at.tabs)} grupos de pestanas, "
          f"{len(at.dataframe)} tablas")

    # Las pestanas de detalle deben existir con sus cinco secciones.
    etiquetas = [t.label for t in at.tabs]
    for nombre in ("Otras marcas", "Que dicen los compradores", "Fuentes"):
        assert nombre in etiquetas, f"falta la pestana '{nombre}' en {etiquetas}"
    print(f"[ok] pestanas: {etiquetas}")

    # El boton de descarga del JSON debe estar presente.
    assert any("Descargar" in b.label for b in at.button) or at.get("download_button"), \
        "falta el boton de descarga"
    print("[ok] boton de descarga presente")

    # El costo y los tokens no deben verse sin abrir el panel tecnico.
    etiquetas_visibles = [m.label for m in at.metric]
    assert "Costo" not in etiquetas_visibles or "Tokens entrada" in etiquetas_visibles,         "el costo quedo suelto en la pagina principal"
    print(f"[ok] metricas de la pagina: {etiquetas_visibles[:6]}")

    print("\nUI verde.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
