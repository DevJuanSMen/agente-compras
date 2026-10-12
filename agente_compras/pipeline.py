"""Orquestacion: de una entrada cualquiera a un Informe completo."""
from __future__ import annotations

from typing import Callable

from . import config
from .core import AgenteBase, Progreso, _nada, crear_agente
from .models import Cotizacion, Informe

# Competidores sugeridos por categoria. Sirven de arranque; el modelo puede
# proponer otros si la categoria no coincide con ninguna entrada.
COMPETIDORES_POR_CATEGORIA: dict[str, list[str]] = {
    "maquinaria_pesada": ["Caterpillar", "Komatsu", "Hitachi", "Volvo CE", "JCB", "Liebherr", "Doosan", "SANY", "XCMG"],
    "camiones": ["Volvo Trucks", "Scania", "Mercedes-Benz", "Kenworth", "International", "Freightliner", "Hino"],
    "herramienta_electrica": ["Bosch", "Makita", "DeWalt", "Milwaukee", "Hilti", "Stanley"],
    "computo": ["Dell", "HP", "Lenovo", "Apple", "ASUS", "Acer"],
    "servidores_red": ["Dell EMC", "HPE", "Lenovo", "Supermicro", "Cisco", "Fortinet"],
    "generadores": ["Caterpillar", "Cummins", "Kohler", "Generac", "Perkins", "SDMO"],
    "agricola": ["John Deere", "New Holland", "Case IH", "Massey Ferguson", "Kubota", "Fendt"],
    "montacargas": ["Toyota", "Hyster", "Yale", "Linde", "Crown", "Mitsubishi"],
    "bombas_compresores": ["Grundfos", "Atlas Copco", "KSB", "Ingersoll Rand", "Sullair"],
    "mobiliario": ["Herman Miller", "Steelcase", "Haworth", "Knoll"],
    "otro": [],
}


def competidores_sugeridos(categoria: str) -> list[str]:
    """Adivina la lista de marcas rivales a partir del texto de la categoria."""
    texto = categoria.lower()
    reglas = [
        ("maquinaria_pesada", ("excavadora", "retroexcavadora", "bulldozer", "buldozer",
                               "cargador", "motoniveladora", "compactador", "minicargador",
                               "maquinaria pesada", "grua", "vibrocompactador")),
        ("camiones", ("camion", "tracto", "volqueta", "tractomula", "chasis")),
        ("agricola", ("tractor", "cosechadora", "agricol", "sembradora", "fumigadora")),
        ("montacargas", ("montacarga", "elevador de carga", "apilador")),
        ("generadores", ("generador", "planta electrica", "grupo electrogeno")),
        ("bombas_compresores", ("bomba", "compresor", "motobomba")),
        ("herramienta_electrica", ("taladro", "pulidora", "herramienta", "sierra", "rotomartillo")),
        ("servidores_red", ("servidor", "switch", "firewall", "rack", "storage", "nas")),
        ("computo", ("portatil", "laptop", "computador", "pc ", "monitor", "impresora", "workstation")),
        ("mobiliario", ("silla", "escritorio", "mobiliario", "mueble")),
    ]
    for clave, palabras in reglas:
        if any(p in texto for p in palabras):
            return COMPETIDORES_POR_CATEGORIA[clave]
    return COMPETIDORES_POR_CATEGORIA["otro"]


def analizar(
    *,
    texto: str | None = None,
    pdf_bytes: bytes | None = None,
    nombre_pdf: str = "cotizacion.pdf",
    pais: str = config.PAIS_DEFAULT,
    moneda: str = config.MONEDA_DEFAULT,
    competidores: list[str] | None = None,
    dominios: list[str] | None = None,
    max_items: int = 3,
    agente: AgenteBase | None = None,
    progreso: Progreso = _nada,
    al_terminar_item: Callable[[Informe], None] | None = None,
) -> Informe:
    """Corre el pipeline completo y devuelve el Informe.

    `al_terminar_item` se llama despues de cada item para poder pintar
    resultados parciales en la interfaz sin esperar a que termine todo.
    """
    agente = agente or crear_agente()
    informe = Informe()

    progreso("Fase 1 de 3 - leyendo la solicitud")
    cotizacion: Cotizacion = agente.extraer(
        texto=texto, pdf_bytes=pdf_bytes, nombre_pdf=nombre_pdf, progreso=progreso
    )
    informe.cotizacion = cotizacion

    items = cotizacion.items[:max_items]
    if len(cotizacion.items) > max_items:
        informe.notas_investigacion.append(
            f"Se analizaron los primeros {max_items} de {len(cotizacion.items)} items."
        )

    for n, item in enumerate(items, start=1):
        etiqueta = item.modelo or item.descripcion[:60]
        progreso(f"Fase 2 de 3 - investigando item {n}/{len(items)}: {etiqueta}")
        rivales = competidores or competidores_sugeridos(item.categoria or item.descripcion)
        if item.marca:
            rivales = [m for m in rivales if m.lower() != item.marca.lower()]

        try:
            dossier = agente.investigar(
                item, pais=pais, moneda=moneda, competidores=rivales,
                progreso=progreso, dominios=dominios,
            )
        except Exception as exc:  # una falla en un item no debe tumbar el informe
            informe.notas_investigacion.append(f"Item '{etiqueta}': fallo la investigacion ({exc}).")
            continue

        informe.dossieres.append(f"===== {etiqueta} =====\n{dossier}")

        progreso(f"Fase 3 de 3 - evaluando item {n}/{len(items)}")
        try:
            informe.analisis.append(
                agente.sintetizar(dossier, item, pais=pais, moneda=moneda, progreso=progreso)
            )
        except Exception as exc:
            informe.notas_investigacion.append(f"Item '{etiqueta}': fallo la sintesis ({exc}).")
            continue

        informe.tokens_entrada = agente.uso.entrada
        informe.tokens_salida = agente.uso.salida
        informe.costo_usd = agente.uso.costo_usd
        if al_terminar_item:
            al_terminar_item(informe)

    informe.tokens_entrada = agente.uso.entrada
    informe.tokens_salida = agente.uso.salida
    informe.costo_usd = agente.uso.costo_usd
    informe.proveedor = config.PROVEEDOR
    informe.modelo = config.modelo_actual()
    progreso("Listo.")
    return informe
