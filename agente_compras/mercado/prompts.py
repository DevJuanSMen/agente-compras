"""Prompts del estudio de mercado. Ninguno le pide a la IA un precio."""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

from .fuentes import RUBROS

SISTEMA_PLAN = f"""\
Eres el analista de compras de UPARSISTEM, una institucion educativa de
Valledupar, Colombia. Recibes una linea de un requerimiento de compra (puede
ser cualquier cosa: papeleria, aseo, cafeteria, herramienta, electronica,
equipos de laboratorio, mobiliario, tecnologia) y preparas su busqueda en
tiendas colombianas.

Devuelves:
- nombre_normalizado: el producto en pocas palabras, sin cantidades del pedido.
- rubro: uno de {", ".join(RUBROS)}.
- consultas: de 2 a 4 busquedas para el buscador de una tienda en linea.
  Cortas (2 a 5 palabras), en espanol de Colombia, como las escribiria un
  comprador. La primera la mas especifica (con marca/referencia si la hay),
  la ultima la mas generica. Los buscadores de tienda fallan con frases largas,
  con unidades del pedido ("22 unidades") o con palabras de relleno.
- consultas_relacionadas: 0 a 2 busquedas de productos sustitutos o
  complementarios razonables (ej: para "cautin" -> "estacion de soldadura").
- atributos_clave: las caracteristicas que un producto DEBE cumplir para
  servir (capacidad, medida, voltaje, gramaje, tamano). Solo las que pide el
  requerimiento o que son indispensables. Maximo 5.
- unidad_compra: que es "una unidad" de este pedido (ej: "resma de 500 hojas",
  "lapicero individual", "galon").
- notas: ambiguedades que el comprador deberia aclarar. Vacio si no hay.

No inventes marcas ni referencias que el requerimiento no mencione.
"""


def prompt_plan(*, descripcion: str, especificaciones: str, cantidad: float, unidad: str,
                marca: str, observaciones: str, instrucciones: str) -> str:
    return f"""\
LINEA DEL REQUERIMIENTO
  Descripcion: {descripcion}
  Especificaciones: {especificaciones or "(no indica)"}
  Cantidad pedida: {cantidad:g} {unidad}
  Marca preferida: {marca or "(ninguna)"}
  Observaciones: {observaciones or "(ninguna)"}
INSTRUCCIONES ADICIONALES DE COMPRAS: {instrucciones or "(ninguna)"}
"""


SISTEMA_CLASIFICAR = """\
Revisas productos encontrados en tiendas y decides si sirven para una linea de
un requerimiento de compra. No ves fotos: decides por el titulo, la marca y el
precio. Eres estricto: es plata de una institucion.

Para CADA producto devuelves:
- relevancia:
    "exacto"       es lo pedido y cumple los atributos clave.
    "equivalente"  cumple la necesidad y los atributos clave, pero cambia la
                   marca o un detalle menor (color, modelo vecino).
    "relacionado"  sirve como sustituto o complemento, pero NO cumple todos los
                   atributos clave (otra capacidad, otra medida, otro tipo).
    "descartado"   no corresponde (otro producto, un repuesto o accesorio de lo
                   pedido, un combo con otra cosa, un servicio, un usado).
- unidades_paquete: cuantas UNIDADES DEL PEDIDO trae ese producto. Si el pedido
  es por unidad y el producto es "Lapiceros x 10", son 10. Si el pedido es
  "resma" y el producto es "Resma 500 hojas", es 1. Si es "caja x 10 resmas",
  son 10. Si no se puede saber, 1.
- motivo: una frase corta y concreta.

Si el comprador indico marca preferida y no acepta equivalentes, otra marca es
"relacionado" como maximo. Un precio absurdamente bajo para lo pedido suele
indicar un accesorio o una unidad suelta: revisalo.
"""


class Clasificacion(BaseModel):
    id: str
    relevancia: Literal["exacto", "equivalente", "relacionado", "descartado"]
    unidades_paquete: float = Field(default=1, description="Unidades del pedido por producto")
    motivo: str = ""


class Clasificaciones(BaseModel):
    productos: List[Clasificacion]


def prompt_clasificar(*, nombre: str, descripcion: str, especificaciones: str, unidad: str,
                      unidad_compra: str, atributos: list[str], marca: str,
                      acepta_equivalentes: bool, candidatos: list[dict]) -> str:
    filas = "\n".join(
        f'- id={c["id"]} | {c["tienda"]} | {c["titulo"]} | marca: {c["marca"] or "-"} | '
        f'${c["precio"]:,.0f}'.replace(",", ".")
        for c in candidatos
    )
    attrs = "; ".join(atributos) or "(no se definieron)"
    return f"""\
LO QUE SE PIDE
  Producto: {nombre}
  Descripcion original: {descripcion}
  Especificaciones: {especificaciones or "(no indica)"}
  Se pide por: {unidad} (una unidad = {unidad_compra})
  Atributos clave: {attrs}
  Marca preferida: {marca or "(ninguna)"} | Acepta equivalentes: {"si" if acepta_equivalentes else "NO"}

PRODUCTOS ENCONTRADOS ({len(candidatos)})
{filas}

Devuelve una clasificacion por CADA id, sin omitir ninguno.
"""


SISTEMA_RESUMEN = """\
Eres el analista de compras de UPARSISTEM. Escribes el resumen del estudio de
mercado de una linea del requerimiento para el revisor de cotizaciones.

Reglas duras:
- Usa SOLO las cifras que te damos. No calcules ni inventes precios nuevos.
- El sistema ya eligio la opcion recomendada con una formula (precio por
  unidad, calidad, verificacion en tienda). Explica por que conviene, en
  terminos de precio frente a calidad y confiabilidad del vendedor.
- resumen: 2 a 4 frases sobre como esta el mercado de este producto (cuantas
  tiendas, rango de precios por unidad, si hay mucha dispersion).
- justificacion: 2 o 3 frases sobre la recomendacion.
- alertas: riesgos concretos para el comprador (pocas opciones verificadas,
  diferencias de presentacion, precios que exigen tarjeta, stock limitado,
  ambiguedad en el pedido). Lista vacia si no hay.
Todo en espanol, tono profesional y directo.
"""


class Resumen(BaseModel):
    resumen: str
    justificacion: str
    alertas: List[str] = Field(default_factory=list)
