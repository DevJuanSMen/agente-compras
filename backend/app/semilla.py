"""Datos iniciales: usuarios por rol y proveedores recurrentes del Excel."""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .ajustes import CLAVE_INICIAL, LISTADO_PROVEEDORES
from .modelos import Proveedor, Usuario
from .seguridad import hashear

log = logging.getLogger("compras.semilla")

# Cuentas iniciales, una por rol del flujograma. Todas deben cambiar la clave
# en el primer ingreso. El administrador las renombra con los responsables
# reales (Maria Isabel Daza en compras, Jose Alberto Morillo / Doriana Buelvas
# en aprobacion, Dayana Tovar en ordenes, etc.).
USUARIOS_INICIALES = [
    ("Administrador del sistema", "admin@uparsistem.edu.co", "Administrador", "Sistemas", ["admin"]),
    ("Solicitante de prueba", "solicitante@uparsistem.edu.co", "Docente", "Sede principal - Académica", ["solicitante"]),
    ("Verificador de área", "verificador@uparsistem.edu.co", "Inventario y mantenimiento", "Inventario", ["verificador", "solicitante"]),
    ("Analista de compras", "compras@uparsistem.edu.co", "Compras", "Compras", ["compras", "solicitante"]),
    ("Aprobador financiero", "aprobador@uparsistem.edu.co", "Dirección financiera", "Gerencia", ["aprobador"]),
    ("Tesorería", "tesoreria@uparsistem.edu.co", "Tesorería y contabilidad", "Contabilidad", ["tesoreria"]),
]


HOSTS_INTERNOS = {"https://tienda.exito.com/": "https://www.exito.com/",
                  "https://secure.carulla.com/": "https://www.carulla.com/"}


def _corregir(valor):
    if isinstance(valor, str):
        for viejo, nuevo in HOSTS_INTERNOS.items():
            valor = valor.replace(viejo, nuevo)
        return valor
    if isinstance(valor, dict):
        return {k: _corregir(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_corregir(v) for v in valor]
    return valor


def corregir_enlaces(db: Session) -> int:
    """Enlaces guardados con el host interno de VTEX (redirigian al inicio)."""
    from .modelos import EstudioMercado, ItemRequerimiento, LineaOrden

    n = 0
    for e in db.scalars(select(EstudioMercado)):
        nuevo = _corregir(e.resultado or {})
        if nuevo != e.resultado:
            e.resultado = nuevo
            n += 1
    for i in db.scalars(select(ItemRequerimiento).where(ItemRequerimiento.seleccion.is_not(None))):
        nuevo = _corregir(i.seleccion)
        if nuevo != i.seleccion:
            i.seleccion = nuevo
            n += 1
    for l in db.scalars(select(LineaOrden)):
        url, oferta = _corregir(l.url_fuente), _corregir(l.oferta or {})
        if url != l.url_fuente or oferta != l.oferta:
            l.url_fuente, l.oferta = url, oferta
            n += 1
    return n


def sembrar(db: Session) -> None:
    if not db.scalar(select(func.count()).select_from(Usuario)):
        clave = hashear(CLAVE_INICIAL)
        for nombre, email, cargo, area, roles in USUARIOS_INICIALES:
            db.add(Usuario(nombre=nombre, email=email, cargo=cargo, area=area, roles=roles, clave_hash=clave,
                           debe_cambiar_clave=True))
        log.info("Usuarios iniciales creados (clave inicial: %s)", CLAVE_INICIAL)
    if not db.scalar(select(func.count()).select_from(Proveedor)):
        n = importar_proveedores(db)
        log.info("Proveedores importados del listado: %s", n)
    corregidos = corregir_enlaces(db)
    if corregidos:
        log.info("Enlaces de tienda corregidos: %s registros", corregidos)
    db.commit()


def importar_proveedores(db: Session) -> int:
    if not LISTADO_PROVEEDORES.exists():
        return 0
    import openpyxl

    wb = openpyxl.load_workbook(LISTADO_PROVEEDORES, data_only=True, read_only=True)
    ws = wb.active
    existentes = {p.identificacion for p in db.scalars(select(Proveedor))}
    n = 0
    for fila in ws.iter_rows(min_row=8, values_only=True):
        nombre, tipo, ident, dv, direccion, ciudad, tel, email, recurrente = (list(fila) + [None] * 9)[:9]
        if not nombre or not ident:
            continue
        ident = str(ident).strip()
        if ident in existentes:
            continue
        existentes.add(ident)
        db.add(Proveedor(
            nombre=str(nombre).strip(), tipo_identificacion=str(tipo or "NIT").strip(), identificacion=ident,
            dv=str(dv).strip() if dv is not None else "", direccion=_limpio(direccion), ciudad=_limpio(ciudad),
            telefono=_telefono(tel), email=_email(email), recurrente=str(recurrente).strip().lower() == "si",
        ))
        n += 1
    return n


def _limpio(v) -> str:
    t = str(v or "").strip()
    return "" if t.lower() in ("no aplica", "none") else t


def _telefono(v) -> str:
    # El listado trae "605-3164807435-" o "605-0000000-": se deja solo lo util.
    partes = [p for p in str(v or "").replace("@", "-").split("-") if p.strip() and set(p.strip()) != {"0"}]
    partes = [p for p in partes if p.strip() not in ("605", "000")]
    return " / ".join(p.strip() for p in partes)


def _email(v) -> str:
    t = str(v or "").strip().lower()
    return "" if not t or t.startswith("notiene") or "@" not in t else t
