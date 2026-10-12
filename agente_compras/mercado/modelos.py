"""Contrato de datos del estudio de mercado."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# Como se obtuvo el precio. Ordenado de mas a menos confiable.
Metodo = Literal[
    "manual",                # cotizacion formal cargada por una persona
    "api_tienda",            # API de catalogo o indice de busqueda de la tienda
    "marcado_estructurado",  # schema.org / JSON-LD / microdatos de la pagina
    "navegador",             # pagina renderizada con navegador real
    "buscador",              # solo el extracto del buscador: NO verificable
]

Relevancia = Literal["exacto", "equivalente", "relacionado", "descartado", "sin_clasificar"]

METODOS_CONFIABLES = {"manual", "api_tienda", "marcado_estructurado", "navegador"}


def ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ItemSolicitud(BaseModel):
    """Una linea del formato de requerimiento de UPARSISTEM."""

    id: int | str = 0
    cantidad: float = 1
    unidad: str = "UND"
    descripcion: str
    especificaciones: str = ""
    marca_preferida: str = ""
    programa: str = ""
    observaciones: str = ""
    acepta_equivalentes: bool = True


class OpcionesEstudio(BaseModel):
    """Que fuentes consultar y como ponderar."""

    fuentes: List[str] = Field(default_factory=list, description="Claves del catalogo")
    sitios_extra: List[str] = Field(
        default_factory=list, description="Dominios o nombres de tiendas que escribio el usuario"
    )
    auto_fuentes: bool = True  # agregar las tiendas que mejor cubren el rubro
    instrucciones: str = ""  # ej: "solo marca Norma", "buscar en presentacion x 12"
    peso_precio: float = 0.6
    max_ofertas_por_fuente: int = 6
    verificar_top: int = 6
    usar_navegador: bool = True


class Verificacion(BaseModel):
    ok: bool
    precio_pagina: Optional[float] = None
    metodo: str = ""
    momento: str = Field(default_factory=ahora_iso)
    detalle: str = ""


class Oferta(BaseModel):
    id: str = ""
    fuente: str  # clave del catalogo o "web" / "manual"
    tienda: str
    dominio: str = ""
    url: str = ""
    titulo: str
    marca: str = ""
    sku: str = ""  # identificador nativo de la fuente, para re-verificar
    vendedor: str = ""
    imagen: str = ""

    precio: Optional[float] = None
    precio_antes: Optional[float] = None
    moneda: str = "COP"
    disponible: Optional[bool] = None
    stock: Optional[int] = None
    calificacion: Optional[float] = None  # sobre 5
    resenas: Optional[int] = None
    envio: str = ""
    notas: List[str] = Field(default_factory=list)

    metodo: Metodo = "api_tienda"
    capturado_en: str = Field(default_factory=ahora_iso)
    verificacion: Optional[Verificacion] = None

    # Lo llena la clasificacion y el puntaje
    relevancia: Relevancia = "sin_clasificar"
    motivo: str = ""
    unidades_paquete: float = 1
    precio_unitario: Optional[float] = None
    paquetes_necesarios: Optional[float] = None
    costo_total: Optional[float] = None
    puntaje_precio: float = 0
    puntaje_calidad: float = 0
    puntaje: float = 0

    def model_post_init(self, _ctx) -> None:
        if not self.id:
            base = f"{self.fuente}|{self.url or self.titulo}|{self.sku}"
            self.id = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]

    @property
    def verificada(self) -> bool:
        return bool(self.verificacion and self.verificacion.ok)

    @property
    def confiable(self) -> bool:
        return self.metodo in METODOS_CONFIABLES and self.precio is not None


class EstadoFuente(BaseModel):
    fuente: str
    nombre: str
    estado: Literal["ok", "sin_resultados", "error", "omitida"]
    resultados: int = 0
    detalle: str = ""


class Estadisticas(BaseModel):
    ofertas_validas: int = 0
    tiendas: int = 0
    precio_unitario_min: Optional[float] = None
    precio_unitario_max: Optional[float] = None
    precio_unitario_mediana: Optional[float] = None
    costo_total_min: Optional[float] = None
    costo_total_recomendado: Optional[float] = None
    ahorro_vs_mediana: Optional[float] = None


class Plan(BaseModel):
    """Lo que la IA entendio de la linea del requerimiento."""

    nombre_normalizado: str
    rubro: str = "general"
    consultas: List[str] = Field(default_factory=list)
    consultas_relacionadas: List[str] = Field(default_factory=list)
    atributos_clave: List[str] = Field(default_factory=list)
    unidad_compra: str = "unidad"
    notas: str = ""


class EstudioItem(BaseModel):
    item: ItemSolicitud
    plan: Optional[Plan] = None
    ofertas: List[Oferta] = Field(default_factory=list)
    recomendada_id: Optional[str] = None
    mas_barata_id: Optional[str] = None
    mejor_calificada_id: Optional[str] = None
    estadisticas: Estadisticas = Field(default_factory=Estadisticas)
    fuentes: List[EstadoFuente] = Field(default_factory=list)
    resumen: str = ""
    justificacion: str = ""
    alertas: List[str] = Field(default_factory=list)
    generado_en: str = Field(default_factory=ahora_iso)
    duracion_s: float = 0

    def oferta(self, oferta_id: str | None) -> Oferta | None:
        return next((o for o in self.ofertas if o.id == oferta_id), None)
