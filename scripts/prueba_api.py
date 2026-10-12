"""Prueba de punta a punta del flujo de compras sobre la API.

    python scripts/prueba_api.py          # estudio simulado (sin red, ~10 s)
    python scripts/prueba_api.py --real   # estudio real contra las tiendas (minutos)

Usa una base de datos temporal: no toca `backend/datos`.
Recorre: solicitante crea -> agente estudia -> compras elige y carga una
cotizacion manual -> genera ordenes -> aprobador aprueba -> factura ->
tesoreria paga y recibe -> requerimiento cerrado. Verifica permisos por rol,
notificaciones, documentos y la aritmetica de la orden contra el formato.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import time

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
REAL = "--real" in sys.argv
TMP = pathlib.Path(tempfile.mkdtemp(prefix="compras_prueba_"))
os.environ["COMPRAS_DIR_DATOS"] = str(TMP)
os.environ["COMPRAS_DATABASE_URL"] = f"sqlite:///{(TMP / 'prueba.db').as_posix()}"

from fastapi.testclient import TestClient  # noqa: E402

from agente_compras.mercado.modelos import (  # noqa: E402
    Estadisticas, EstudioItem, Oferta, Verificacion,
)
from backend.app import calculos, flujo, trabajador  # noqa: E402
from backend.app.ajustes import CLAVE_INICIAL  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.modelos import LineaOrden, OrdenCompra  # noqa: E402

FALLAS: list[str] = []


def ok(cond: bool, mensaje: str) -> None:
    print(("  OK  " if cond else "  XX  ") + mensaje)
    if not cond:
        FALLAS.append(mensaje)


# ---------------------------------------------------------------------------
def prueba_calculos() -> None:
    print("\n== Aritmetica de la orden (formato OC-1-3621) ==")
    lineas = [(1, 33000), (4, 6300), (22, 3300), (88, 150), (44, 600), (18, 1800), (22, 300), (22, 3200),
              (22, 1200), (22, 2300), (22, 200), (22, 300), (22, 100), (15, 20000), (12, 13000), (22, 8000),
              (6, 30000), (22, 3800), (22, 8000), (15, 14000), (15, 14000), (15, 16000), (15, 15000),
              (15, 15000), (2, 33000), (12, 800)]
    oc = OrdenCompra(retefuente_pct=2.5, reteica_x_mil=10)
    oc.lineas = [LineaOrden(descripcion="x", cantidad=c, vr_unitario=v, descuento=0, iva_pct=0, rete_pct=2.5)
                 for c, v in lineas]
    calculos.recalcular(oc)
    ok(oc.lineas[0].total == 32175, f"linea 1 = 32.175 (obtenido {oc.lineas[0].total:,.0f})")
    ok(oc.total_bruto == 2627200, f"total bruto 2.627.200 ({oc.total_bruto:,.0f})")
    ok(oc.retefuente == 65680, f"retefuente 65.680 ({oc.retefuente:,.0f})")
    ok(oc.reteica == 26272, f"reteICA 26.272 ({oc.reteica:,.0f})")
    ok(oc.total_pagar == 2535248, f"total a pagar 2.535.248 ({oc.total_pagar:,.0f})")


# ---------------------------------------------------------------------------
def estudio_falso(item, opciones, llm=None, progreso=lambda m: None):
    progreso("Analizando la solicitud")
    time.sleep(0.3)
    progreso("Verificando 2 precios directamente en las tiendas...")
    base = 10000 if "resma" in item.descripcion.lower() else 50000
    ofertas = [
        Oferta(fuente="exito", tienda="Éxito", dominio="www.exito.com", url="https://www.exito.com/p1/p",
               titulo=f"{item.descripcion} marca A", precio=base, sku="1|1", metodo="api_tienda",
               relevancia="exacto", unidades_paquete=1, calificacion=4.5, resenas=40,
               verificacion=Verificacion(ok=True, precio_pagina=base, metodo="simulador de carrito")),
        Oferta(fuente="panamericana", tienda="Panamericana", dominio="www.panamericana.com.co",
               url="https://www.panamericana.com.co/p2/p", titulo=f"{item.descripcion} marca B x 5",
               precio=base * 4, sku="2|1", metodo="api_tienda", relevancia="equivalente", unidades_paquete=5,
               verificacion=Verificacion(ok=True, precio_pagina=base * 4, metodo="simulador de carrito")),
        Oferta(fuente="exito", tienda="Éxito", url="https://www.exito.com/p3/p", titulo="accesorio",
               precio=900, metodo="api_tienda", relevancia="descartado"),
    ]
    from agente_compras.mercado import estudio as E

    E._normalizar(item, ofertas)
    E._puntuar(item, ofertas, opciones)
    r = EstudioItem(item=item, ofertas=ofertas, resumen="Mercado simulado.", justificacion="Simulado.")
    E._elegir(r, ofertas)
    r.estadisticas = Estadisticas(ofertas_validas=2, tiendas=2)
    return r


def verificar_falso(o, cantidad=1, usar_navegador=True, fuente=None):
    v = Verificacion(ok=True, precio_pagina=o.precio, metodo="simulado", detalle="Precio confirmado")
    o.verificacion = v
    return v


# ---------------------------------------------------------------------------
def prueba_flujo() -> None:
    if not REAL:
        trabajador.estudiar_item = estudio_falso
        flujo.verificar_oferta = verificar_falso

    with TestClient(app) as c:
        print("\n== Sesion y roles ==")
        tokens = {}
        nueva = "ClaveNueva2026!"
        for rol in ("admin", "solicitante", "verificador", "compras", "aprobador", "tesoreria"):
            r = c.post("/api/auth/login", json={"email": f"{rol}@uparsistem.edu.co", "clave": CLAVE_INICIAL})
            ok(r.status_code == 200, f"login {rol}")
            t = r.json()["token"]
            ok(r.json()["usuario"]["debe_cambiar_clave"], f"{rol} debe cambiar clave al primer ingreso")
            r = c.post("/api/auth/cambiar-clave", json={"actual": CLAVE_INICIAL, "nueva": nueva},
                       headers={"Authorization": f"Bearer {t}"})
            ok(r.status_code == 200, f"{rol} cambia su clave")
            tokens[rol] = {"Authorization": f"Bearer {t}"}
        ok(c.post("/api/auth/login", json={"email": "admin@uparsistem.edu.co", "clave": "mala"}).status_code == 401,
           "clave incorrecta rechazada")
        ok(c.get("/api/usuarios", headers=tokens["solicitante"]).status_code == 403, "solicitante no administra usuarios")
        provs = c.get("/api/proveedores?q=CENCOSUD", headers=tokens["compras"]).json()
        ok(bool(provs) and provs[0]["nit"].startswith("900.155.107"), "proveedores importados del Excel (CENCOSUD)")

        print("\n== Requerimiento ==")
        cuerpo = {
            "nombre_cargo": "Solicitante de prueba - Docente", "area": "Sede principal - Académica",
            "destino": "Diplomado en lactancia humana", "tipo": "Académico", "prioridad": "normal",
            "items": [
                {"cantidad": 10, "unidad": "RESMA", "programa": "Diplomado", "descripcion": "Resma papel carta",
                 "especificaciones": "75 g, 500 hojas"},
                {"cantidad": 3, "unidad": "UND", "programa": "Diplomado", "descripcion": "Grapadora industrial"},
            ],
            "enviar": True,
        }
        ok(c.post("/api/requerimientos", json=cuerpo, headers=tokens["aprobador"]).status_code == 403,
           "aprobador no crea requerimientos")
        r = c.post("/api/requerimientos", json=cuerpo, headers=tokens["solicitante"])
        ok(r.status_code == 200, f"solicitante crea y envia ({r.status_code})")
        req = r.json()
        rid = req["id"]
        ok(req["estado"] == "en_estudio", f"entra directo al agente (estado {req['estado']})")
        ok(req["consecutivo"].startswith("REQ-2026-"), f"consecutivo {req['consecutivo']}")

        print("\n== Estudio de mercado en segundo plano ==")
        limite = time.time() + (1200 if REAL else 60)
        while time.time() < limite:
            e = c.get(f"/api/requerimientos/{rid}/estudio", headers=tokens["compras"]).json()
            if e["estudio"]["estado"] in ("listo", "error"):
                break
            time.sleep(2 if not REAL else 10)
            if REAL:
                print(f"     {e['estudio']['progreso']:.0f}% {e['estudio']['paso'][:90]}")
        ok(e["estudio"]["estado"] == "listo", f"estudio terminado ({e['estudio']['estado']})")
        lineas = e["lineas"]
        ok(all(l["recomendada_id"] for l in lineas), "cada linea tiene recomendacion")
        notis = c.get("/api/notificaciones", headers=tokens["compras"]).json()
        ok(any("Estudio de mercado listo" in n["titulo"] for n in notis["items"]), "compras recibe aviso del estudio")
        notis = c.get("/api/notificaciones", headers=tokens["solicitante"]).json()
        ok(any("Estudio de mercado listo" in n["titulo"] for n in notis["items"]), "solicitante recibe aviso")

        print("\n== Revision de compras ==")
        ok(c.post(f"/api/requerimientos/{rid}/usar-recomendadas", headers=tokens["solicitante"]).status_code == 403,
           "solicitante no puede elegir cotizaciones")
        r = c.post(f"/api/requerimientos/{rid}/usar-recomendadas", headers=tokens["compras"])
        ok(r.status_code == 200 and r.json()["seleccionados"] == 2, "compras usa las recomendadas")
        item2 = lineas[1]["item"]["id"]
        descartada = next((o for o in lineas[0]["ofertas"] if o["relevancia"] == "descartado"), None)
        if descartada:
            r = c.post(f"/api/requerimientos/{rid}/items/{lineas[0]['item']['id']}/seleccion",
                       json={"oferta_id": descartada["id"]}, headers=tokens["compras"])
            ok(r.status_code == 400, "no deja elegir una opcion descartada")
        prov = c.get("/api/proveedores?q=Anderson", headers=tokens["compras"]).json()[0]
        r = c.post(f"/api/requerimientos/{rid}/cotizaciones", headers=tokens["compras"],
                   data={"item_id": item2, "proveedor_id": prov["id"], "precio_unitario": "41000",
                         "vigencia": "30 días", "plazo_entrega": "2 días"})
        ok(r.status_code == 200, "cotizacion manual de proveedor local")
        r = c.post(f"/api/requerimientos/{rid}/items/{item2}/seleccion", json={"oferta_id": r.json()["oferta_id"]},
                   headers=tokens["compras"])
        ok(r.status_code == 200, "elige la cotizacion del proveedor local para la linea 2")
        sol = c.get(f"/api/requerimientos/{rid}/solicitud-cotizacion?proveedor_id={prov['id']}",
                    headers=tokens["compras"]).json()
        ok("Resma papel carta" in sol["cuerpo"], "genera texto de solicitud de cotizacion")

        r = c.post(f"/api/requerimientos/{rid}/ordenes", json={"forma_pago": "contado", "observaciones": "Diplomado"},
                   headers=tokens["compras"])
        if r.status_code == 409 and REAL:
            print("     precios cambiaron al re-verificar; se confirman:", r.json()["detail"]["cambios"])
            r = c.post(f"/api/requerimientos/{rid}/ordenes",
                       json={"forma_pago": "contado", "observaciones": "Diplomado", "confirmar_cambios": True},
                       headers=tokens["compras"])
        ok(r.status_code == 200, f"genera ordenes ({r.status_code} {r.text[:200]})")
        ordenes = r.json()["ordenes"]
        ok(len(ordenes) == 2, f"una orden por proveedor ({len(ordenes)})")
        det = c.get(f"/api/requerimientos/{rid}", headers=tokens["solicitante"]).json()
        ok(det["estado"] == "en_aprobacion", "requerimiento en aprobacion de pago")
        notis = c.get("/api/notificaciones", headers=tokens["aprobador"]).json()
        ok(any("Órdenes por aprobar" in n["titulo"] for n in notis["items"]), "aprobador recibe aviso")

        manual = None
        for oid in ordenes:
            o = c.get(f"/api/ordenes/{oid}", headers=tokens["aprobador"]).json()
            if o["canal"] == "proveedor_directo":
                manual = o
        ok(manual is not None and manual["proveedor_nit"].startswith("1.065.635.845"),
           "la orden del proveedor local lleva su NIT del listado")
        ok(manual and manual["lineas"][0]["vr_unitario"] == 41000, "precio de la cotizacion manual en la orden")

        print("\n== Aprobacion, factura, pago y recepcion ==")
        ok(c.post(f"/api/ordenes/{ordenes[0]}/aprobar", headers=tokens["compras"]).status_code == 403,
           "compras no puede aprobar el pago")
        r = c.post(f"/api/ordenes/{ordenes[0]}/rechazar", json={"motivo": ""}, headers=tokens["aprobador"])
        ok(r.status_code == 400, "rechazo exige motivo")
        sin_nit = [oid for oid in ordenes if not c.get(f"/api/ordenes/{oid}", headers=tokens["compras"]).json()["proveedor_nit"]]
        for oid in sin_nit:
            r = c.post(f"/api/ordenes/{oid}/aprobar", headers=tokens["aprobador"])
            ok(r.status_code == 409, "no se aprueba una orden sin NIT del proveedor")
            o = c.get(f"/api/ordenes/{oid}", headers=tokens["compras"]).json()
            r = c.put(f"/api/ordenes/{oid}", headers=tokens["compras"], json={
                "proveedor_nombre": o["proveedor_nombre"], "proveedor_nit": "800.000.000-1", "forma_pago": "contado",
                "observaciones": o["observaciones"], "retefuente_pct": 2.5, "reteica_x_mil": 10})
            ok(r.status_code == 200 and r.json()["proveedor_nit"] == "800.000.000-1", "compras completa el NIT")
        facturas = []
        for oid in ordenes:
            r = c.post(f"/api/ordenes/{oid}/aprobar", headers=tokens["aprobador"])
            ok(r.status_code == 200, f"aprobador aprueba orden {oid} ({r.status_code} {r.text[:150]})")
            if r.status_code == 200:
                facturas.append(r.json()["factura"])
        ok(len(facturas) == 2 and all(f["numero"].startswith("FC-1-") for f in facturas), "factura por orden aprobada")
        det = c.get(f"/api/requerimientos/{rid}", headers=tokens["solicitante"]).json()
        ok(det["estado"] == "aprobado", f"requerimiento aprobado ({det['estado']})")
        for oid in ordenes:
            r = c.post(f"/api/ordenes/{oid}/pago", data={"referencia": "TRF-001"}, headers=tokens["tesoreria"])
            ok(r.status_code == 200 and r.json()["estado"] == "pagada", "tesoreria registra el pago")
            r = c.post(f"/api/ordenes/{oid}/recepcion", json={"cumple": True, "notas": "Completo"},
                       headers=tokens["tesoreria"])
            ok(r.status_code == 200 and r.json()["estado"] == "recibida", "recepcion a satisfaccion")
        det = c.get(f"/api/requerimientos/{rid}", headers=tokens["solicitante"]).json()
        ok(det["estado"] == "cerrado", f"requerimiento cerrado ({det['estado']})")
        ok(len(det["eventos"]) >= 8, f"bitacora de auditoria con {len(det['eventos'])} eventos")

        print("\n== Documentos ==")
        t = tokens["compras"]["Authorization"].split()[1]
        salida = TMP / "documentos"
        salida.mkdir()
        for nombre, url, tipo in (
            ("estudio.pdf", f"/api/requerimientos/{rid}/documentos/estudio.pdf", "application/pdf"),
            ("cuadro.xlsx", f"/api/requerimientos/{rid}/documentos/cuadro.xlsx", "spreadsheet"),
            ("requerimiento.xlsx", f"/api/requerimientos/{rid}/documentos/requerimiento.xlsx", "spreadsheet"),
            ("orden.pdf", f"/api/ordenes/{ordenes[0]}/pdf", "application/pdf"),
            ("factura.pdf", f"/api/facturas/{facturas[0]['id']}/pdf", "application/pdf"),
        ):
            r = c.get(url + f"?token={t}")
            ok(r.status_code == 200 and tipo in r.headers["content-type"] and len(r.content) > 2000,
               f"{nombre} ({len(r.content) // 1024} KB)")
            (salida / nombre).write_bytes(r.content)
        ok(c.get(f"/api/ordenes/{ordenes[0]}/pdf?token=falso").status_code == 401, "descarga sin sesion rechazada")
        print(f"     documentos de muestra en {salida}")
        tab = c.get("/api/tablero", headers=tokens["compras"]).json()
        ok(tab["total_requerimientos"] == 1, "tablero responde")


if __name__ == "__main__":
    try:
        prueba_calculos()
        prueba_flujo()
    finally:
        trabajador.trabajador.detener()
    print("\n" + ("TODO OK" if not FALLAS else f"{len(FALLAS)} FALLA(S):\n - " + "\n - ".join(FALLAS)))
    if not FALLAS and "--conservar" not in sys.argv:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FALLAS else 0)
