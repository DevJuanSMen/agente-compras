"""Tablas de la base de datos."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .bd import Base


def ahora() -> datetime:
    return datetime.now(timezone.utc)


class FechaUTC(TypeDecorator):
    """SQLite guarda las fechas sin zona horaria; aqui se devuelven como UTC
    para que la interfaz las muestre en hora de Colombia sin correrlas."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, valor, dialecto):
        if valor is not None and valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc) if valor is not None else None

    def process_result_value(self, valor, dialecto):
        if valor is not None and valor.tzinfo is None:
            valor = valor.replace(tzinfo=timezone.utc)
        return valor


# --- Roles -----------------------------------------------------------------
# Derivados del flujograma de compras. Un usuario puede tener varios.
ROLES = {
    "solicitante": "Solicitante (crea requerimientos)",
    "verificador": "Verificador de área (aprueba la solicitud)",
    "compras": "Compras (revisa cotizaciones y genera órdenes)",
    "aprobador": "Aprobador financiero (aprueba el pago)",
    "tesoreria": "Tesorería / contabilidad (pago, factura y recepción)",
    "admin": "Administrador del sistema",
}


class Usuario(Base):
    __tablename__ = "usuarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    cargo: Mapped[str] = mapped_column(String(120), default="")
    area: Mapped[str] = mapped_column(String(160), default="")
    clave_hash: Mapped[str] = mapped_column(String(300))
    roles: Mapped[list] = mapped_column(JSON, default=list)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    debe_cambiar_clave: Mapped[bool] = mapped_column(Boolean, default=True)
    notificar_correo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)

    def tiene(self, *roles: str) -> bool:
        return "admin" in (self.roles or []) or any(r in (self.roles or []) for r in roles)


# --- Requerimientos --------------------------------------------------------
ESTADOS_REQ = {
    "borrador": "Borrador",
    "pendiente_verificacion": "Pendiente de verificación del área",
    "rechazado": "Rechazado",
    "en_estudio": "Estudio de mercado en curso",
    "estudio_listo": "Estudio listo - revisión de compras",
    "en_aprobacion": "Orden(es) en aprobación de pago",
    "aprobado": "Aprobado - en compra",
    "cerrado": "Recibido y cerrado",
    "cancelado": "Cancelado",
}


class Requerimiento(Base):
    __tablename__ = "requerimientos"
    id: Mapped[int] = mapped_column(primary_key=True)
    consecutivo: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    nombre_cargo: Mapped[str] = mapped_column(String(200))
    area: Mapped[str] = mapped_column(String(160), default="")
    destino: Mapped[str] = mapped_column(String(300), default="")
    tipo: Mapped[str] = mapped_column(String(60), default="")
    fecha_solicitud: Mapped[date] = mapped_column(Date, default=date.today)
    fecha_requerida: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    prioridad: Mapped[str] = mapped_column(String(20), default="normal")
    justificacion: Mapped[str] = mapped_column(Text, default="")
    estado: Mapped[str] = mapped_column(String(40), default="borrador", index=True)

    fuentes: Mapped[list] = mapped_column(JSON, default=list)
    sitios_extra: Mapped[list] = mapped_column(JSON, default=list)
    proveedores_sugeridos: Mapped[list] = mapped_column(JSON, default=list)

    verificado_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    motivo_rechazo: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora, onupdate=ahora)

    solicitante: Mapped[Usuario] = relationship(foreign_keys=[solicitante_id])
    items: Mapped[list["ItemRequerimiento"]] = relationship(
        back_populates="requerimiento", cascade="all, delete-orphan", order_by="ItemRequerimiento.orden")
    estudios: Mapped[list["EstudioMercado"]] = relationship(
        back_populates="requerimiento", cascade="all, delete-orphan", order_by="EstudioMercado.version")
    ordenes: Mapped[list["OrdenCompra"]] = relationship(back_populates="requerimiento")


class ItemRequerimiento(Base):
    __tablename__ = "items_requerimiento"
    id: Mapped[int] = mapped_column(primary_key=True)
    requerimiento_id: Mapped[int] = mapped_column(ForeignKey("requerimientos.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(Integer, default=0)
    cantidad: Mapped[float] = mapped_column(Float, default=1)
    unidad: Mapped[str] = mapped_column(String(30), default="UND")
    programa: Mapped[str] = mapped_column(String(200), default="")
    descripcion: Mapped[str] = mapped_column(Text)
    especificaciones: Mapped[str] = mapped_column(Text, default="")
    marca_preferida: Mapped[str] = mapped_column(String(120), default="")
    acepta_equivalentes: Mapped[bool] = mapped_column(Boolean, default=True)
    observaciones: Mapped[str] = mapped_column(Text, default="")
    imagen: Mapped[str] = mapped_column(String(300), default="")
    # Eleccion de compras: copia congelada de la oferta (precio, tienda, URL,
    # verificacion). Se congela para que un re-estudio no cambie lo elegido.
    seleccion: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    excluido: Mapped[bool] = mapped_column(Boolean, default=False)  # compras decide no comprarlo

    requerimiento: Mapped[Requerimiento] = relationship(back_populates="items")


class EstudioMercado(Base):
    __tablename__ = "estudios"
    id: Mapped[int] = mapped_column(primary_key=True)
    requerimiento_id: Mapped[int] = mapped_column(ForeignKey("requerimientos.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    estado: Mapped[str] = mapped_column(String(20), default="en_cola", index=True)
    progreso: Mapped[float] = mapped_column(Float, default=0)
    paso: Mapped[str] = mapped_column(String(300), default="En cola")
    bitacora: Mapped[list] = mapped_column(JSON, default=list)
    opciones: Mapped[dict] = mapped_column(JSON, default=dict)
    instrucciones: Mapped[str] = mapped_column(Text, default="")
    items_ids: Mapped[list] = mapped_column(JSON, default=list)  # vacio = todos
    resultado: Mapped[dict] = mapped_column(JSON, default=dict)  # {item_id: EstudioItem}
    error: Mapped[str] = mapped_column(Text, default="")
    solicitado_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)
    iniciado_en: Mapped[Optional[datetime]] = mapped_column(FechaUTC(), nullable=True)
    terminado_en: Mapped[Optional[datetime]] = mapped_column(FechaUTC(), nullable=True)

    requerimiento: Mapped[Requerimiento] = relationship(back_populates="estudios")


class CotizacionManual(Base):
    """Cotizacion formal de un proveedor (local, sin tienda en linea)."""

    __tablename__ = "cotizaciones_manuales"
    id: Mapped[int] = mapped_column(primary_key=True)
    requerimiento_id: Mapped[int] = mapped_column(ForeignKey("requerimientos.id", ondelete="CASCADE"))
    item_id: Mapped[int] = mapped_column(ForeignKey("items_requerimiento.id", ondelete="CASCADE"))
    proveedor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("proveedores.id"), nullable=True)
    proveedor_nombre: Mapped[str] = mapped_column(String(200))
    descripcion: Mapped[str] = mapped_column(Text, default="")
    precio_unitario: Mapped[float] = mapped_column(Float)
    unidades_paquete: Mapped[float] = mapped_column(Float, default=1)
    incluye_iva: Mapped[bool] = mapped_column(Boolean, default=True)
    vigencia: Mapped[str] = mapped_column(String(60), default="")
    plazo_entrega: Mapped[str] = mapped_column(String(120), default="")
    forma_pago: Mapped[str] = mapped_column(String(120), default="")
    garantia: Mapped[str] = mapped_column(String(160), default="")
    observaciones: Mapped[str] = mapped_column(Text, default="")
    archivo: Mapped[str] = mapped_column(String(300), default="")
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)


# --- Proveedores -----------------------------------------------------------
class Proveedor(Base):
    __tablename__ = "proveedores"
    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(200), index=True)
    tipo_identificacion: Mapped[str] = mapped_column(String(60), default="NIT")
    identificacion: Mapped[str] = mapped_column(String(40), default="", index=True)
    dv: Mapped[str] = mapped_column(String(4), default="")
    direccion: Mapped[str] = mapped_column(String(200), default="")
    ciudad: Mapped[str] = mapped_column(String(80), default="")
    telefono: Mapped[str] = mapped_column(String(80), default="")
    email: Mapped[str] = mapped_column(String(160), default="")
    sitio_web: Mapped[str] = mapped_column(String(200), default="")
    rubros: Mapped[list] = mapped_column(JSON, default=list)
    recurrente: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)

    @property
    def nit_completo(self) -> str:
        if not self.identificacion:
            return ""
        try:
            base = f"{int(self.identificacion):,}".replace(",", ".")
        except ValueError:
            base = self.identificacion
        return f"{base}-{self.dv}" if self.dv not in ("", None) else base


# --- Ordenes de compra -----------------------------------------------------
ESTADOS_OC = {
    "pendiente_aprobacion": "Pendiente de aprobación de pago",
    "aprobada": "Aprobada",
    "rechazada": "Rechazada",
    "pagada": "Pagada",
    "recibida": "Recibida a satisfacción",
    "devolucion": "En devolución",
    "anulada": "Anulada",
}


class OrdenCompra(Base):
    __tablename__ = "ordenes"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    requerimiento_id: Mapped[int] = mapped_column(ForeignKey("requerimientos.id"))
    proveedor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("proveedores.id"), nullable=True)
    proveedor_nombre: Mapped[str] = mapped_column(String(200))
    proveedor_nit: Mapped[str] = mapped_column(String(60), default="")
    proveedor_contacto: Mapped[str] = mapped_column(String(300), default="")
    canal: Mapped[str] = mapped_column(String(30), default="tienda_en_linea")  # o proveedor_directo
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    estado: Mapped[str] = mapped_column(String(30), default="pendiente_aprobacion", index=True)
    forma_pago: Mapped[str] = mapped_column(String(20), default="contado")
    observaciones: Mapped[str] = mapped_column(Text, default="")

    retefuente_pct: Mapped[float] = mapped_column(Float, default=2.5)
    reteica_x_mil: Mapped[float] = mapped_column(Float, default=10.0)
    total_bruto: Mapped[float] = mapped_column(Float, default=0)
    descuentos: Mapped[float] = mapped_column(Float, default=0)
    subtotal: Mapped[float] = mapped_column(Float, default=0)
    iva_total: Mapped[float] = mapped_column(Float, default=0)
    retefuente: Mapped[float] = mapped_column(Float, default=0)
    reteica: Mapped[float] = mapped_column(Float, default=0)
    total_pagar: Mapped[float] = mapped_column(Float, default=0)

    verificacion: Mapped[dict] = mapped_column(JSON, default=dict)  # ultimo informe de precios
    verificada_en: Mapped[Optional[datetime]] = mapped_column(FechaUTC(), nullable=True)
    precios_cambiaron: Mapped[bool] = mapped_column(Boolean, default=False)

    creada_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    creada_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)
    aprobada_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    aprobada_en: Mapped[Optional[datetime]] = mapped_column(FechaUTC(), nullable=True)
    motivo_rechazo: Mapped[str] = mapped_column(Text, default="")
    pagada_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    pagada_en: Mapped[Optional[datetime]] = mapped_column(FechaUTC(), nullable=True)
    referencia_pago: Mapped[str] = mapped_column(String(200), default="")
    soporte_pago: Mapped[str] = mapped_column(String(300), default="")
    recibida_por_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    recibida_en: Mapped[Optional[datetime]] = mapped_column(FechaUTC(), nullable=True)
    notas_recepcion: Mapped[str] = mapped_column(Text, default="")

    requerimiento: Mapped[Requerimiento] = relationship(back_populates="ordenes")
    lineas: Mapped[list["LineaOrden"]] = relationship(
        back_populates="orden_compra", cascade="all, delete-orphan", order_by="LineaOrden.posicion")
    facturas: Mapped[list["Factura"]] = relationship(back_populates="orden")
    creada_por: Mapped[Usuario] = relationship(foreign_keys=[creada_por_id])
    aprobada_por: Mapped[Optional[Usuario]] = relationship(foreign_keys=[aprobada_por_id])


class LineaOrden(Base):
    __tablename__ = "lineas_orden"
    id: Mapped[int] = mapped_column(primary_key=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes.id", ondelete="CASCADE"))
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items_requerimiento.id"), nullable=True)
    posicion: Mapped[int] = mapped_column(Integer, default=0)
    descripcion: Mapped[str] = mapped_column(Text)
    cantidad: Mapped[float] = mapped_column(Float)
    vr_unitario: Mapped[float] = mapped_column(Float)
    descuento: Mapped[float] = mapped_column(Float, default=0)
    iva_pct: Mapped[float] = mapped_column(Float, default=0)
    rete_pct: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[float] = mapped_column(Float, default=0)
    url_fuente: Mapped[str] = mapped_column(String(600), default="")
    oferta: Mapped[dict] = mapped_column(JSON, default=dict)

    orden_compra: Mapped[OrdenCompra] = relationship(back_populates="lineas")


class Factura(Base):
    __tablename__ = "facturas"
    id: Mapped[int] = mapped_column(primary_key=True)
    numero: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    orden_id: Mapped[int] = mapped_column(ForeignKey("ordenes.id"))
    fecha: Mapped[date] = mapped_column(Date, default=date.today)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente_pago")
    total_pagar: Mapped[float] = mapped_column(Float, default=0)
    numero_proveedor: Mapped[str] = mapped_column(String(80), default="")  # factura real del proveedor
    archivo_proveedor: Mapped[str] = mapped_column(String(300), default="")
    creada_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)

    orden: Mapped[OrdenCompra] = relationship(back_populates="facturas")


# --- Soporte ---------------------------------------------------------------
class Notificacion(Base):
    __tablename__ = "notificaciones"
    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id", ondelete="CASCADE"), index=True)
    titulo: Mapped[str] = mapped_column(String(200))
    mensaje: Mapped[str] = mapped_column(Text, default="")
    enlace: Mapped[str] = mapped_column(String(300), default="")
    tipo: Mapped[str] = mapped_column(String(30), default="info")
    leida: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    creada_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)


class Evento(Base):
    """Bitacora de auditoria: quien hizo que y cuando. No se borra."""

    __tablename__ = "eventos"
    id: Mapped[int] = mapped_column(primary_key=True)
    entidad: Mapped[str] = mapped_column(String(40), index=True)
    entidad_id: Mapped[int] = mapped_column(Integer, index=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    accion: Mapped[str] = mapped_column(String(80))
    detalle: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(FechaUTC(), default=ahora)

    usuario: Mapped[Optional[Usuario]] = relationship()


class Configuracion(Base):
    __tablename__ = "configuracion"
    __table_args__ = (UniqueConstraint("clave"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    clave: Mapped[str] = mapped_column(String(60))
    valor: Mapped[dict | list] = mapped_column(JSON)
