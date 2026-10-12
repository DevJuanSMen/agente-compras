"""Datos enlatados de ejemplo.

Sirven para dos cosas: probar el pipeline sin gastar llamadas a la API y
mostrar la interfaz completa en una demo cuando no hay credenciales a mano.
Los precios y las URLs son ficticios.
"""
from __future__ import annotations

from . import models


COTIZACION = models.Cotizacion(
    proveedor="Maquinarias del Norte S.A.S.",
    fecha="2026-09-18",
    moneda="USD",
    total=165000.0,
    items=[
        models.LineaCotizacion(
            descripcion="Excavadora hidraulica sobre orugas Caterpillar 320 GC",
            marca="Caterpillar",
            modelo="320 GC",
            categoria="excavadora sobre orugas",
            cantidad=1,
            precio_unitario=165000.0,
            moneda="USD",
            especificaciones=["Ano 2021", "3.050 horas", "Motor C4.4 121 HP", "Peso 22.2 t"],
        )
    ],
    condiciones=["Entrega 45 dias", "Garantia 6 meses", "Pago 50/50"],
    notas="Documento legible, sin desglose de impuestos.",
)

ANALISIS = models.AnalisisItem(
    producto="Excavadora hidraulica sobre orugas",
    marca="Caterpillar",
    modelo="320 GC",
    calificacion_producto=4.3,
    calificacion_marca=4.7,
    calificacion_precio=2.0,
    calificacion_global=3.7,
    resumen="Maquina solida y con la mejor red de repuestos de la region, pero la "
    "cotizacion esta por encima del mercado para una unidad 2021 con 3.050 horas.",
    fortalezas=["Red de servicio amplia", "Alta retencion de valor", "Consumo competitivo"],
    debilidades=["Electronica costosa de reparar", "Menos potencia que la serie 320 estandar"],
    donde_comprar=[
        models.OpcionCompra(
            tienda="Maquinarias del Norte",
            producto="Excavadora CAT 320 GC 2021 - 3.050 h",
            precio=165000.0, moneda="USD",
            url="https://ejemplo.test/maqnorte/320gc",
            disponibilidad="disponible",
            envio="Flete a obra incluido (Bogota)",
            garantia="6 meses o 500 horas, solo tren motriz",
            observaciones="Es la cotizacion recibida. Garantia corta para una usada.",
        ),
        models.OpcionCompra(
            tienda="MachineryLine",
            producto="Caterpillar 320GC 2021, 2.800 h",
            precio=141000.0, moneda="USD",
            url="https://ejemplo.test/machineryline/320gc",
            disponibilidad="disponible",
            envio="No incluye nacionalizacion",
            garantia="no indica",
            observaciones="Importada; hay que sumar nacionalizacion y flete.",
        ),
        models.OpcionCompra(
            tienda="TuCarro",
            producto="Excavadora Caterpillar 320 GC",
            precio=152000.0, moneda="USD",
            url="https://ejemplo.test/tucarro/320gc",
            disponibilidad="disponible",
            envio="A convenir",
            garantia="no indica",
            observaciones="Vendedor particular; sin respaldo de distribuidor.",
        ),
    ],
    mejor_opcion="MachineryLine tiene el precio mas bajo (USD 141.000), pero sin "
    "garantia y hay que nacionalizar. Para una obra que necesita respaldo, conviene "
    "negociar con Maquinarias del Norte hasta USD 145.000 pidiendo 12 meses de garantia: "
    "el flete y el servicio local justifican la diferencia.",
    ahorro_posible="USD 24.000 frente a la cotizacion, comprando en MachineryLine "
    "(sin contar nacionalizacion, estimada en USD 8.000-12.000)",
    comentarios_clientes=[
        models.ComentarioCliente(
            texto="La 320 GC es economica en combustible pero se siente lenta en excavacion profunda.",
            autor="operador_co",
            fuente="HeavyEquipmentForums",
            url="https://ejemplo.test/foro/320gc",
            sentimiento="neutral",
        ),
        models.ComentarioCliente(
            texto="Dos anos sin una sola falla mayor, el soporte respondio en 24 horas.",
            autor=None,
            fuente="Reddit r/heavyequipment",
            url="https://ejemplo.test/reddit/320gc",
            sentimiento="positivo",
        ),
    ],
    precio_cotizado=165000.0,
    moneda_cotizada="USD",
    rango_mercado=models.RangoPrecioMercado(
        minimo=118000.0,
        maximo=152000.0,
        tipico=134000.0,
        moneda="USD",
        base="usado 2020-2022, 2.500-4.000 horas, mercado US",
        confianza="media",
    ),
    veredicto_precio="caro",
    desviacion_pct=23.1,
    justificacion_precio="El precio supera en ~23% el tipico observado en listados comparables.",
    alternativas=[
        models.Alternativa(
            marca="Hitachi",
            modelo="ZX210LC-6",
            equivalencia="Mismo rango de 20-22 t y potencia similar.",
            precio_estimado="USD 125.000 aprox.",
            url="https://ejemplo.test/hitachi",
            calificacion=4.2,
            ventajas=["Hidraulica mas rapida", "Precio menor"],
            desventajas=["Red de repuestos menor en la region"],
            disponibilidad_local="Distribuidor unico en la capital",
            fuentes=["https://ejemplo.test/hitachi"],
        ),
        models.Alternativa(
            marca="Volvo CE",
            modelo="EC220E",
            equivalencia="Competidor directo en el segmento 22 t.",
            precio_estimado="USD 131.000 aprox.",
            url="https://ejemplo.test/volvo",
            calificacion=4.0,
            ventajas=["Cabina y ergonomia superiores", "Buen consumo"],
            desventajas=["Costo de repuestos alto"],
            disponibilidad_local="Dos sucursales",
            fuentes=["https://ejemplo.test/volvo"],
        ),
    ],
    costo_total_propiedad=["Mantenimiento 500h economico", "Reventa fuerte a 5 anos"],
    banderas_rojas=["Garantia de solo 6 meses para una maquina usada"],
    preguntas_al_proveedor=[
        "Puede entregar el historial de mantenimiento certificado?",
        "Acepta ajustar a USD 140.000 con garantia de 12 meses?",
    ],
    recomendacion="negociar",
    fuentes=[
        models.Fuente(titulo="Listado MachineryTrader", url="https://ejemplo.test/mt", tipo="marketplace"),
        models.Fuente(titulo="Foro de operadores", url="https://ejemplo.test/foro", tipo="foro"),
    ],
    confianza_analisis="media",
)


def informe_ejemplo() -> models.Informe:
    """Un Informe completo listo para pintar en la UI."""
    return models.Informe(
        cotizacion=COTIZACION,
        analisis=[ANALISIS],
        notas_investigacion=["Informe de ejemplo: datos ficticios, no se consulto la web."],
        costo_usd=0.45,
        tokens_entrada=41_200,
        tokens_salida=9_800,
    )
