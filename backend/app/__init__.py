"""Agente de Compras UPARSISTEM v1.0 - servidor."""
import pathlib
import sys

# El cerebro (`agente_compras`) vive en la raiz del proyecto.
RAIZ_PROYECTO = pathlib.Path(__file__).resolve().parents[2]
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

VERSION = "1.0.0"
