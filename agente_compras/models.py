"""Esquemas Pydantic: contrato de datos entre el modelo y la interfaz.

Regla que atraviesa todo el archivo: **nada sin fuente**. Cada precio, cada
opinion y cada opcion de compra lleva su URL para poder comprobarla. Los campos
`url` son obligatorios a proposito: si el modelo no tiene el link, no deberia
existir la fila.
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

Sentimiento = Literal["positivo", "neutral", "negativo"]
Confianza = Literal["alta", "media", "baja"]
VeredictoPrecio = Literal[
    "muy_barato", "buen_precio", "precio_justo", "caro", "muy_caro", "sin_datos"
]


def _clamp_1_a_5(valor: Any) -> Any:
    """El esquema ya limita el rango; esto evita que un 5.2 tumbe el parseo."""
    if isinstance(valor, (int, float)):
        return min(5.0, max(1.0, float(valor)))
    return valor


# --------------------------------------------------------------------------
# Fase 1 - Lectura de la cotizacion o de la intencion de compra
# --------------------------------------------------------------------------
class LineaCotizacion(BaseModel):
    descripcion: str = Field(description="Descripcion del item tal como aparece")
    marca: Optional[str] = Field(description="Marca detectada, null si no aparece")
    modelo: Optional[str] = Field(description="Modelo o referencia, null si no aparece")
    categoria: str = Field(
        description="Categoria generica: 'nevera no frost', 'taladro percutor', "
        "'excavadora sobre orugas', 'silla ergonomica'"
    )
    cantidad: float = Field(description="Cantidad, 1 si no se indica")
    precio_unitario: Optional[float] = Field(
        description="Precio unitario sin simbolos ni separadores, null si no aparece"
    )
    moneda: Optional[str] = Field(description="Codigo ISO de la moneda, ej: COP, USD")
    especificaciones: List[str] = Field(
        description="Specs relevantes: capacidad, potencia, medidas, ano, garantia"
    )


class Cotizacion(BaseModel):
    proveedor: Optional[str] = Field(description="Nombre del proveedor que emite")
    fecha: Optional[str] = Field(description="Fecha del documento en formato libre")
    moneda: Optional[str] = Field(description="Moneda predominante del documento")
    total: Optional[float] = Field(description="Total del documento si aparece")
    items: List[LineaCotizacion]
    condiciones: List[str] = Field(
        description="Condiciones comerciales: entrega, garantia, forma de pago, validez"
    )
    notas: str = Field(description="Observaciones del lector sobre el documento")


# --------------------------------------------------------------------------
# Fase 3 - Analisis final por item
# --------------------------------------------------------------------------
class Fuente(BaseModel):
    titulo: str
    url: str
    tipo: Literal[
        "tienda", "marketplace", "distribuidor", "foro", "review",
        "ficha_tecnica", "noticia", "otro"
    ]


class OpcionCompra(BaseModel):
    """Un lugar concreto donde comprar ESTE producto, con su link.

    Es la entrega central de la herramienta: responde "donde lo compro y a que
    precio", con el link para comprobarlo.
    """

    tienda: str = Field(description="Nombre del comercio: Homecenter, Alkosto, MercadoLibre...")
    producto: str = Field(description="Nombre del producto tal como lo publica esa tienda")
    precio: Optional[float] = Field(
        description="Precio numerico sin simbolos, null si la pagina no lo publica"
    )
    moneda: str = Field(description="Codigo de la moneda del precio, ej: COP")
    url: str = Field(description="Link directo al producto. OBLIGATORIO: sin link no va la fila")
    disponibilidad: str = Field(description="Disponible, agotado, bajo pedido, o 'no indicada'")
    envio: Optional[str] = Field(description="Costo o plazo de envio si la pagina lo dice")
    garantia: Optional[str] = Field(description="Garantia que ofrece esa tienda, si la dice")
    observaciones: str = Field(
        description="Diferencias frente a las otras opciones: version, kit incluido, "
        "condiciones de la oferta, vigencia"
    )


class ComentarioCliente(BaseModel):
    texto: str = Field(description="Cita textual o parafraseo fiel del comentario")
    autor: Optional[str] = Field(description="Usuario o medio, null si es anonimo")
    fuente: str = Field(description="Sitio donde se encontro")
    url: str = Field(description="Link al comentario. OBLIGATORIO: sin link no va la fila")
    sentimiento: Sentimiento


class RangoPrecioMercado(BaseModel):
    minimo: Optional[float]
    maximo: Optional[float]
    tipico: Optional[float] = Field(description="Precio mas representativo del mercado")
    moneda: str = Field(description="Debe ser la misma moneda del precio consultado")
    base: str = Field(
        description="A que corresponde el rango: modelo exacto, estado, ano, region"
    )
    confianza: Confianza


class Alternativa(BaseModel):
    """Otro producto comparable, de otra marca o referencia."""

    marca: str
    modelo: str
    equivalencia: str = Field(description="Por que es comparable al item consultado")
    precio_estimado: Optional[str] = Field(description="Precio con moneda, texto libre")
    url: Optional[str] = Field(description="Link donde se ve ese precio")
    calificacion: float = Field(ge=1, le=5, description="Calificacion 1 a 5")
    ventajas: List[str]
    desventajas: List[str]
    disponibilidad_local: str = Field(description="Se consigue en el pais del comprador?")
    fuentes: List[str] = Field(description="URLs que respaldan esta alternativa")

    _ajustar = field_validator("calificacion", mode="before")(_clamp_1_a_5)


class AnalisisItem(BaseModel):
    producto: str
    marca: str
    modelo: Optional[str]

    calificacion_producto: float = Field(ge=1, le=5)
    calificacion_marca: float = Field(ge=1, le=5)
    calificacion_precio: float = Field(ge=1, le=5, description="5 = precio excelente")
    calificacion_global: float = Field(ge=1, le=5)

    _ajustar = field_validator(
        "calificacion_producto",
        "calificacion_marca",
        "calificacion_precio",
        "calificacion_global",
        mode="before",
    )(_clamp_1_a_5)

    resumen: str = Field(description="Veredicto en 2 o 3 frases, en espanol")
    fortalezas: List[str]
    debilidades: List[str]

    # --- El corazon de la herramienta: donde comprarlo -------------------
    donde_comprar: List[OpcionCompra] = Field(
        description="Opciones de compra ordenadas de mejor a peor. Cada una con su link"
    )
    mejor_opcion: str = Field(
        description="Cual conviene y POR QUE: precio, garantia, envio, confiabilidad "
        "del vendedor. Menciona la tienda por su nombre"
    )
    ahorro_posible: Optional[str] = Field(
        description="Cuanto se ahorra comprando en la mejor opcion frente a la peor "
        "o frente al precio consultado. Null si no hay con que comparar"
    )

    comentarios_clientes: List[ComentarioCliente]

    precio_cotizado: Optional[float]
    moneda_cotizada: Optional[str]
    rango_mercado: RangoPrecioMercado
    veredicto_precio: VeredictoPrecio
    desviacion_pct: Optional[float] = Field(
        description="(cotizado - tipico) / tipico * 100. Positivo = mas caro. "
        "Null solo si no hay precio consultado"
    )
    justificacion_precio: str

    alternativas: List[Alternativa]

    costo_total_propiedad: List[str] = Field(
        description="Consumibles, repuestos, mantenimiento, consumo, reventa"
    )
    banderas_rojas: List[str]
    preguntas_al_proveedor: List[str]
    recomendacion: Literal["comprar", "negociar", "comparar_mas", "no_comprar"]

    fuentes: List[Fuente]
    confianza_analisis: Confianza


class Informe(BaseModel):
    """Resultado completo de una corrida del agente."""

    cotizacion: Optional[Cotizacion] = None
    analisis: List[AnalisisItem] = Field(default_factory=list)
    notas_investigacion: List[str] = Field(default_factory=list)
    # Evidencia cruda por item. Sirve para auditar de donde salio cada dato
    # del analisis, y para depurar cuando una seccion sale vacia.
    dossieres: List[str] = Field(default_factory=list)
    costo_usd: float = 0.0
    tokens_entrada: int = 0
    tokens_salida: int = 0
    proveedor: str = ""
    modelo: str = ""
