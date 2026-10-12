"""Ajustes del servidor (variables de entorno) y datos fijos de la empresa."""
from __future__ import annotations

import os
import pathlib
import secrets

from dotenv import load_dotenv

from . import RAIZ_PROYECTO

load_dotenv(RAIZ_PROYECTO / ".env")

DIR_BACKEND = pathlib.Path(__file__).resolve().parents[1]
DIR_DATOS = pathlib.Path(os.getenv("COMPRAS_DIR_DATOS", DIR_BACKEND / "datos"))
DIR_ARCHIVOS = DIR_DATOS / "archivos"
DIR_RECURSOS = DIR_BACKEND / "recursos"
DIR_FRONTEND = RAIZ_PROYECTO / "frontend" / "dist"
LOGO = DIR_RECURSOS / "logo_uparsistem.png"
LISTADO_PROVEEDORES = RAIZ_PROYECTO / "recursos" / "LISTADO PROVEEDORES RECURRENTES - UPARSISTEM.xlsx"

for d in (DIR_DATOS, DIR_ARCHIVOS):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("COMPRAS_DATABASE_URL", f"sqlite:///{(DIR_DATOS / 'compras.db').as_posix()}")


def _secreto() -> str:
    """El secreto de los tokens se genera una vez y se guarda junto a la BD."""
    env = os.getenv("COMPRAS_JWT_SECRETO")
    if env:
        return env
    archivo = DIR_DATOS / ".secreto_jwt"
    if archivo.exists():
        return archivo.read_text().strip()
    valor = secrets.token_urlsafe(48)
    archivo.write_text(valor)
    return valor


JWT_SECRETO = _secreto()
JWT_HORAS = int(os.getenv("COMPRAS_JWT_HORAS", "12"))

# Correo (opcional). Sin SMTP_HOST las notificaciones quedan solo en la app.
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USUARIO = os.getenv("SMTP_USUARIO", "")
SMTP_CLAVE = os.getenv("SMTP_CLAVE", "")
SMTP_REMITENTE = os.getenv("SMTP_REMITENTE", SMTP_USUARIO)
URL_PUBLICA = os.getenv("COMPRAS_URL_PUBLICA", "http://localhost:8000")

CLAVE_INICIAL = os.getenv("COMPRAS_CLAVE_INICIAL", "Uparsistem2026*")

# Valores por defecto de la configuracion editable (tabla `configuracion`).
CONFIG_INICIAL: dict = {
    "empresa": {
        "nombre": "UPARSISTEM SAS",
        "nit": "901.715.627-5",
        "direccion": "CL 16A 12 36",
        "telefono": "(3106410913)",
        "ciudad": "Valledupar - Colombia",
        "correo_inventario": "inventario@uparsistem.edu.co",
    },
    "flujo": {
        # Paso "Verificacion y aprobacion de la solicitud" del flujograma.
        # Apagado: el requerimiento entra directo al agente al enviarlo.
        "verificacion_area": False,
        # Horas tras las cuales un precio verificado se vuelve a comprobar
        # antes de aprobar el pago.
        "horas_validez_precio": 24,
        # Tolerancia de cambio de precio entre la orden y la tienda.
        "tolerancia_precio_pct": 0.5,
    },
    "impuestos": {
        "iva_pct": 0.0,           # Impto. Cargo por defecto (precios de tienda ya incluyen IVA)
        "retefuente_pct": 2.5,
        "reteica_x_mil": 10.0,
        "base_minima_retencion": 0,
    },
    "consecutivos": {
        "requerimiento_prefijo": "REQ-2026-",
        "requerimiento_siguiente": 1,
        "orden_prefijo": "OC-1-",
        "orden_siguiente": 3622,
        "factura_prefijo": "FC-1-",
        "factura_siguiente": 1,
    },
    "estudio": {
        "fuentes_por_defecto": [],
        "auto_fuentes": True,
        "peso_precio": 0.6,
        "verificar_top": 6,
        "usar_navegador": True,
    },
    "firmas": {
        "director": "Doriana Margarita Buelvas Rodriguez",
        "profesional_financiero": "Daniel Arturo Rivera Beltran",
        "aprobo": "Sandra Patricia Angel Sastre",
    },
    # Del flujograma "V2 Proceso de compra e inventario".
    "areas": [
        "Sede principal - Papelería", "Sede principal - Elementos de aseo y SST",
        "Sede principal - Bienestar", "Sede principal - Producción audiovisual",
        "Sede principal - Relaciones corporativas", "Sede principal - Académica",
        "Centro de práctica", "CEA", "Enfermería", "Colegio técnico", "GBJP", "Vehículos",
        "Equipos de cómputo y comunicación", "Aires acondicionados", "Cocina",
        "Archivo general", "Mantenimiento e infraestructura",
    ],
    "laboratorios": [
        "Enfermería (quirófano, maternidad, PYP, farmacia, salud oral, simuladores, RCP)",
        "Enfermería (electrónica, sistemas, caja registradora, lab. farmacia)",
        "Refrigeración", "Electricidad industrial / energía solar fotovoltaica",
        "Laboratorio de alturas / Proyecto Drummond", "Laboratorio de mecánica", "Soldadura",
        "Maquinaria (camión, montacarga, JCB, John Deere)", "Criminalística, archivo",
        "Ambientes de sistemas / zona administrativa", "Cocina", "Laboratorio de electrónica",
    ],
    "tipos": ["Académico", "Infraestructura", "Publicidad / Papelería", "Extracurricular"],
    "unidades": ["UND", "PAQ", "CAJA", "RESMA", "ROLLO", "GALÓN", "LITRO", "KG", "METRO", "PAR",
                 "JUEGO", "KIT", "SERVICIO"],
}
