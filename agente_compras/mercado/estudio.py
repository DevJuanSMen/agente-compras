"""Orquestador del estudio de mercado de una linea de requerimiento."""
from __future__ import annotations

import math
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from ..llm import CadenaLLM, SinModeloDisponible
from . import fuentes as F
from .modelos import (
    METODOS_CONFIABLES, EstadoFuente, Estadisticas, EstudioItem, ItemSolicitud, Oferta,
    OpcionesEstudio, Plan, Verificacion,
)
from .prompts import (
    SISTEMA_CLASIFICAR, SISTEMA_PLAN, SISTEMA_RESUMEN, Clasificaciones, Resumen,
    prompt_clasificar, prompt_plan,
)

Progreso = Callable[[str], None]
MAX_CANDIDATOS = 48
LOTE_CLASIFICACION = 24
HILOS = 6
# Una oferta cuyo precio por unidad se aleja asi de la mediana casi siempre es
# un error de presentacion (se tomo un paquete como unidad o al reves).
FACTOR_ATIPICO = 4.0


def _nada(_: str) -> None:
    return None


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def estudiar_item(
    item: ItemSolicitud,
    opciones: OpcionesEstudio | None = None,
    *,
    llm: CadenaLLM | None = None,
    progreso: Progreso = _nada,
) -> EstudioItem:
    inicio = time.monotonic()
    opciones = opciones or OpcionesEstudio()
    llm = llm or CadenaLLM()
    resultado = EstudioItem(item=item)

    # 1. Entender lo que se pide
    progreso(f"Analizando la solicitud: {item.descripcion[:70]}")
    plan = _planificar(item, opciones, llm, progreso)
    resultado.plan = plan

    # 2. Elegir fuentes
    elegidas = _elegir_fuentes(plan, opciones, progreso)
    progreso("Consultando: " + ", ".join(f.nombre for f in elegidas))

    # 3. Buscar
    ofertas, estados = _buscar(elegidas, plan, opciones, progreso)
    resultado.fuentes = estados
    progreso(f"{len(ofertas)} productos encontrados en {sum(1 for e in estados if e.resultados)} fuentes")
    if not ofertas:
        resultado.alertas.append(
            "No se encontro el producto en ninguna de las fuentes consultadas. Considere "
            "solicitar cotizacion directa a proveedores recurrentes o ajustar la descripcion."
        )
        resultado.resumen = "Sin resultados en las tiendas consultadas."
        resultado.duracion_s = round(time.monotonic() - inicio, 1)
        return resultado

    # 4. Clasificar
    progreso("Revisando que productos corresponden a lo pedido...")
    _clasificar(item, plan, ofertas, llm, progreso)

    # 5-6. Normalizar, verificar y puntuar
    _normalizar(item, ofertas)
    _marcar_atipicos(ofertas)
    _puntuar(item, ofertas, opciones)
    _verificar(item, ofertas, elegidas, opciones, progreso)
    _normalizar(item, ofertas)  # la verificacion pudo actualizar precios
    _marcar_atipicos(ofertas)
    _puntuar(item, ofertas, opciones)
    _elegir(resultado, ofertas)

    resultado.ofertas = sorted(
        ofertas,
        key=lambda o: (o.relevancia not in ("exacto", "equivalente"),
                       o.relevancia == "descartado", -o.puntaje),
    )
    resultado.estadisticas = _estadisticas(resultado)
    resultado.alertas += _alertas_automaticas(resultado)

    # 7. Redactar
    progreso("Redactando el resumen del estudio...")
    _resumir(resultado, llm, progreso)
    resultado.duracion_s = round(time.monotonic() - inicio, 1)
    progreso(f"Linea lista en {resultado.duracion_s:.0f} s")
    return resultado


# ---------------------------------------------------------------------------
# 1. Plan
# ---------------------------------------------------------------------------
def _planificar(item: ItemSolicitud, opciones: OpcionesEstudio, llm: CadenaLLM,
                progreso: Progreso) -> Plan:
    if llm.hay_modelo:
        try:
            plan = llm.json(
                sistema=SISTEMA_PLAN,
                usuario=prompt_plan(
                    descripcion=item.descripcion, especificaciones=item.especificaciones,
                    cantidad=item.cantidad, unidad=item.unidad, marca=item.marca_preferida,
                    observaciones=item.observaciones, instrucciones=opciones.instrucciones,
                ),
                esquema=Plan, progreso=progreso,
            )
            plan.consultas = _limpiar_consultas(plan.consultas) or [_consulta_basica(item)]
            plan.consultas_relacionadas = _limpiar_consultas(plan.consultas_relacionadas)[:2]
            if plan.rubro not in F.RUBROS:
                plan.rubro = "general"
            return plan
        except SinModeloDisponible as exc:
            progreso(f"Sin modelo para planificar ({str(exc)[:80]}); se usa busqueda basica")
    return Plan(nombre_normalizado=item.descripcion[:80], consultas=[_consulta_basica(item)],
                rubro=_rubro_por_palabras(item.descripcion))


def _limpiar_consultas(consultas: list[str]) -> list[str]:
    vistas, salida = set(), []
    for c in consultas:
        c = re.sub(r"\s+", " ", c).strip(" .,\"'")
        if c and c.lower() not in vistas:
            vistas.add(c.lower())
            salida.append(c[:80])
    return salida[:4]


def _consulta_basica(item: ItemSolicitud) -> str:
    palabras = re.findall(r"[\wáéíóúñü\"/.-]+", f"{item.marca_preferida} {item.descripcion}", re.I)
    return " ".join(palabras[:6])


_RUBRO_PALABRAS = {
    "papeleria": ("papel", "resma", "lapicero", "cuaderno", "marcador", "carpeta", "folder",
                  "cartulina", "borrador", "grapadora", "az ", "pegante", "resaltador", "tinta"),
    "tecnologia": ("computador", "portatil", "mouse", "teclado", "monitor", "usb", "memoria",
                   "impresora", "tablet", "router", "disco", "cable hdmi", "proyector"),
    "ferreteria": ("taladro", "alicate", "destornillador", "martillo", "pinza", "sierra",
                   "cortafrio", "pelacable", "llave", "herramienta"),
    "electricidad": ("cautin", "estaño", "diodo", "resistencia", "capacitor", "transformador",
                     "led", "bornera", "fusible", "regulador", "cable", "breaker", "toma"),
    "aseo": ("jabon", "detergente", "escoba", "trapero", "cloro", "desinfectante", "papel higienico",
             "toalla", "bolsa basura", "limpiador"),
    "cafeteria": ("cafe", "azucar", "vaso", "agua", "galleta", "aromatica", "mezcladores"),
    "oficina": ("silla", "escritorio", "archivador", "mesa"),
}


def _rubro_por_palabras(texto: str) -> str:
    t = f" {texto.lower()} "
    for rubro, palabras in _RUBRO_PALABRAS.items():
        if any(p in t for p in palabras):
            return rubro
    return "general"


# ---------------------------------------------------------------------------
# 2-3. Fuentes y busqueda
# ---------------------------------------------------------------------------
def _elegir_fuentes(plan: Plan, opciones: OpcionesEstudio, progreso: Progreso) -> list[F.Fuente]:
    claves = list(dict.fromkeys(opciones.fuentes))
    if opciones.auto_fuentes or not claves:
        for c in F.para_rubro(plan.rubro):
            if c not in claves:
                claves.append(c)
    elegidas = [F.POR_CLAVE[c] for c in claves if c in F.POR_CLAVE]
    for sitio in opciones.sitios_extra:
        try:
            elegidas.append(F.fuente_para_sitio(sitio, progreso))
        except Exception as exc:
            progreso(f"No se pudo preparar el sitio '{sitio}': {str(exc)[:80]}")
    # Busqueda abierta siempre al final: cubre lo que las grandes superficies no
    # venden. Se excluyen los dominios que ya se consultan por su API, para no
    # traer dos veces el mismo producto por caminos distintos.
    elegidas = [f for f in elegidas if f.clave != "web"]
    base = F.POR_CLAVE["web"]
    cubiertos = tuple(f.dominio.replace("www.", "") for f in elegidas if f.dominio)
    elegidas.append(F.FuenteWeb(clave=base.clave, nombre=base.nombre, dominio="",
                                rubros=base.rubros, excluir=base.excluir + cubiertos))
    return elegidas


def _buscar(elegidas: list[F.Fuente], plan: Plan, opciones: OpcionesEstudio,
            progreso: Progreso) -> tuple[list[Oferta], list[EstadoFuente]]:
    consultas = plan.consultas[:3]
    relacionadas = plan.consultas_relacionadas[:1]
    por_api = [f for f in elegidas if f.tipo not in ("web", "mercadolibre")]
    lentas = [f for f in elegidas if f.tipo in ("web", "mercadolibre")]

    hallazgos: dict[str, list[Oferta]] = {f.clave: [] for f in elegidas}
    errores: dict[str, str] = {}

    def tarea(fuente: F.Fuente, consulta: str, n: int):
        try:
            return fuente, fuente.buscar(consulta, n), ""
        except Exception as exc:
            return fuente, [], f"{type(exc).__name__}: {str(exc)[:110]}"

    # Fuentes con API: en paralelo, todas las consultas.
    trabajos = []
    with ThreadPoolExecutor(max_workers=HILOS) as pool:
        for f in por_api:
            for c in consultas:
                trabajos.append(pool.submit(tarea, f, c, opciones.max_ofertas_por_fuente))
            for c in relacionadas:
                trabajos.append(pool.submit(tarea, f, c, 3))
        for t in as_completed(trabajos):
            f, ofs, error = t.result()
            hallazgos[f.clave] += ofs
            if error:
                errores.setdefault(f.clave, error)

    # Fuentes lentas (buscador + navegador): en serie, menos consultas.
    for f in lentas:
        for c in consultas[:2 if f.tipo == "web" else 1]:
            progreso(f"Buscando en {f.nombre}: {c}")
            try:
                hallazgos[f.clave] += f.buscar(c, 4, progreso)
            except Exception as exc:
                errores[f.clave] = str(exc)[:120]

    vistas: set[str] = set()
    ofertas: list[Oferta] = []
    estados: list[EstadoFuente] = []
    for f in elegidas:
        propias = []
        for o in hallazgos[f.clave]:
            clave = _clave_url(o.url) or f"{o.tienda}|{o.titulo}".lower()
            if clave in vistas or not o.precio or o.precio <= 0:
                continue
            vistas.add(clave)
            propias.append(o)
        ofertas += propias
        if propias:
            estados.append(EstadoFuente(fuente=f.clave, nombre=f.nombre, estado="ok",
                                        resultados=len(propias)))
        elif f.clave in errores:
            estados.append(EstadoFuente(fuente=f.clave, nombre=f.nombre, estado="error",
                                        detalle=errores[f.clave]))
        else:
            estados.append(EstadoFuente(fuente=f.clave, nombre=f.nombre, estado="sin_resultados"))
    # Primero las confiables, luego por orden de aparicion; tope para la IA.
    ofertas.sort(key=lambda o: o.metodo not in METODOS_CONFIABLES)
    return ofertas[:MAX_CANDIDATOS], estados


def _clave_url(url: str) -> str:
    """Misma pagina aunque cambie el esquema, el www, la consulta o la barra final."""
    if not url:
        return ""
    u = re.sub(r"^https?://(www\.)?", "", url.lower()).split("?")[0].split("#")[0]
    return u.rstrip("/")


# ---------------------------------------------------------------------------
# 4. Clasificacion
# ---------------------------------------------------------------------------
def _clasificar(item: ItemSolicitud, plan: Plan, ofertas: list[Oferta], llm: CadenaLLM,
                progreso: Progreso) -> None:
    if not llm.hay_modelo:
        _clasificar_por_palabras(item, plan, ofertas)
        return
    for i in range(0, len(ofertas), LOTE_CLASIFICACION):
        lote = ofertas[i:i + LOTE_CLASIFICACION]
        candidatos = [{"id": o.id, "tienda": o.tienda, "titulo": o.titulo[:140],
                       "marca": o.marca, "precio": o.precio or 0} for o in lote]
        try:
            res = llm.json(
                sistema=SISTEMA_CLASIFICAR,
                usuario=prompt_clasificar(
                    nombre=plan.nombre_normalizado, descripcion=item.descripcion,
                    especificaciones=item.especificaciones, unidad=item.unidad,
                    unidad_compra=plan.unidad_compra, atributos=plan.atributos_clave,
                    marca=item.marca_preferida, acepta_equivalentes=item.acepta_equivalentes,
                    candidatos=candidatos,
                ),
                esquema=Clasificaciones, progreso=progreso,
            )
            por_id = {c.id: c for c in res.productos}
            for o in lote:
                c = por_id.get(o.id)
                if c:
                    o.relevancia = c.relevancia
                    o.unidades_paquete = c.unidades_paquete if c.unidades_paquete and c.unidades_paquete > 0 else 1
                    o.motivo = c.motivo[:240]
                else:
                    o.relevancia = "sin_clasificar"
        except SinModeloDisponible as exc:
            progreso(f"Sin modelo para clasificar ({str(exc)[:80]}); se usa coincidencia de palabras")
            _clasificar_por_palabras(item, plan, lote)


def _clasificar_por_palabras(item: ItemSolicitud, plan: Plan, ofertas: list[Oferta]) -> None:
    """Respaldo sin IA: coincidencia de palabras significativas."""
    clave = {w for w in re.findall(r"\w{4,}", plan.nombre_normalizado.lower())}
    for o in ofertas:
        titulo = set(re.findall(r"\w{4,}", o.titulo.lower()))
        cobertura = len(clave & titulo) / max(1, len(clave))
        o.relevancia = "equivalente" if cobertura >= 0.6 else ("relacionado" if cobertura >= 0.3 else "descartado")
        o.unidades_paquete = _unidades_por_titulo(o.titulo)
        o.motivo = "Clasificado por coincidencia de palabras (sin IA): revisar"


def _unidades_por_titulo(titulo: str) -> float:
    m = re.search(r"\b(?:x|por|pack|paquete|caja)\s*(\d{1,4})\s*(?:und|unid|unidades|uds|u)?\b", titulo, re.I)
    return float(m.group(1)) if m and 1 < int(m.group(1)) <= 1000 else 1.0


# ---------------------------------------------------------------------------
# 5. Normalizacion y puntaje
# ---------------------------------------------------------------------------
def _validas(ofertas: list[Oferta]) -> list[Oferta]:
    return [o for o in ofertas if o.relevancia in ("exacto", "equivalente") and o.precio]


def _normalizar(item: ItemSolicitud, ofertas: list[Oferta]) -> None:
    cantidad = max(item.cantidad, 1)
    for o in ofertas:
        if not o.precio:
            continue
        unidades = o.unidades_paquete or 1
        o.precio_unitario = round(o.precio / unidades, 2)
        o.paquetes_necesarios = math.ceil(cantidad / unidades - 1e-9)
        o.costo_total = round(o.paquetes_necesarios * o.precio, 2)


def _marcar_atipicos(ofertas: list[Oferta]) -> None:
    validas = [o for o in _validas(ofertas) if o.precio_unitario]
    if len(validas) < 3:
        return
    mediana = statistics.median(o.precio_unitario for o in validas)
    for o in validas:
        if o.precio_unitario < mediana / FACTOR_ATIPICO or o.precio_unitario > mediana * FACTOR_ATIPICO:
            aviso = "Precio atipico frente al resto del mercado: revisar presentacion o cantidad"
            if aviso not in o.notas:
                o.notas.append(aviso)


def _calidad(item: ItemSolicitud, o: Oferta) -> float:
    relevancia = {"exacto": 1.0, "equivalente": 0.85, "relacionado": 0.5}.get(o.relevancia, 0.0)
    # Promedio bayesiano: 4.8 con 3 resenas no le gana a 4.6 con 400.
    if o.calificacion and o.resenas:
        m, previa = 10, 3.8
        bayes = (o.calificacion * o.resenas + previa * m) / (o.resenas + m)
        valoracion = max(0.0, min(1.0, (bayes - 1) / 4))
    else:
        valoracion = 0.6
    confianza = {"manual": 1.0, "api_tienda": 0.95, "marcado_estructurado": 0.9,
                 "navegador": 0.85, "buscador": 0.3}.get(o.metodo, 0.5)
    if o.verificada:
        confianza = min(1.0, confianza + 0.05)
    if o.vendedor and o.vendedor != o.tienda and o.fuente in F.POR_CLAVE and F.POR_CLAVE[o.fuente].tipo == "vtex":
        confianza *= 0.95  # tercero dentro de un marketplace
    q = 0.5 * relevancia + 0.3 * valoracion + 0.2 * confianza
    if item.marca_preferida and item.marca_preferida.lower() in f"{o.marca} {o.titulo}".lower():
        q += 0.05
    if any("atipico" in n for n in o.notas):
        q *= 0.7
    # Stock insuficiente para el pedido: obligaria a partir la compra.
    if o.stock is not None and o.paquetes_necesarios and o.stock < o.paquetes_necesarios:
        q *= 0.75
    return round(min(1.0, q), 4)


def _puntuar(item: ItemSolicitud, ofertas: list[Oferta], opciones: OpcionesEstudio) -> None:
    validas = [o for o in _validas(ofertas) if o.precio_unitario]
    if not validas:
        for o in ofertas:
            o.puntaje_calidad = _calidad(item, o)
        return
    minimo = min(o.precio_unitario for o in validas)
    peso = max(0.0, min(1.0, opciones.peso_precio))
    for o in ofertas:
        o.puntaje_calidad = _calidad(item, o)
        if o in validas:
            o.puntaje_precio = round(minimo / o.precio_unitario, 4)
            o.puntaje = round(peso * o.puntaje_precio + (1 - peso) * o.puntaje_calidad, 4)
        else:
            o.puntaje_precio = 0
            o.puntaje = round(0.3 * o.puntaje_calidad, 4) if o.relevancia == "relacionado" else 0


# ---------------------------------------------------------------------------
# 6. Verificacion en tienda
# ---------------------------------------------------------------------------
def _fuente_de(o: Oferta, elegidas: list[F.Fuente]) -> F.Fuente | None:
    for f in elegidas:
        if f.clave == o.fuente:
            return f
    return F.POR_CLAVE.get(o.fuente)


def verificar_oferta(o: Oferta, cantidad: int = 1, usar_navegador: bool = True,
                     fuente: F.Fuente | None = None) -> Verificacion:
    """Verifica una oferta contra la tienda. Si el precio cambio, lo actualiza:
    el precio vigente de la tienda manda sobre el del indice de busqueda."""
    if o.metodo == "manual":
        return Verificacion(ok=True, precio_pagina=o.precio, metodo="cotizacion formal",
                            detalle="Cotizacion entregada por el proveedor")
    fuente = fuente or F.POR_CLAVE.get(o.fuente)
    if fuente is None:
        fuente = F.FuenteWeb(clave=o.fuente, nombre=o.tienda, dominio=o.dominio)
    try:
        v = fuente.verificar(o, cantidad=cantidad, usar_navegador=usar_navegador)
    except Exception as exc:
        v = Verificacion(ok=False, metodo=fuente.tipo, detalle=f"Error al verificar: {str(exc)[:120]}")
    insuficiente = "cantidad insuficiente" in v.detalle.lower()
    if not v.ok and v.precio_pagina and "agotado" not in v.detalle.lower() and not insuficiente:
        anterior = o.precio
        o.precio = v.precio_pagina
        if o.metodo == "buscador":
            o.metodo = "marcado_estructurado"
        nota = f"Precio actualizado al verificar en la tienda (antes ${anterior:,.0f})".replace(",", ".")
        o.notas.append(nota)
        v = Verificacion(ok=True, precio_pagina=v.precio_pagina, metodo=v.metodo,
                         detalle="Precio vigente leido en la tienda (cambio respecto a la busqueda)")
    if not v.ok and "agotado" in v.detalle.lower():
        o.disponible = False
    if insuficiente:
        aviso = v.detalle
        if aviso not in o.notas:
            o.notas.append(aviso)
    o.verificacion = v
    return v


def _verificar(item: ItemSolicitud, ofertas: list[Oferta], elegidas: list[F.Fuente],
               opciones: OpcionesEstudio, progreso: Progreso) -> None:
    candidatas = sorted(_validas(ofertas), key=lambda o: -o.puntaje)
    # Siempre se verifica la mas barata ademas de las mejor puntuadas.
    baratas = sorted(_validas(ofertas), key=lambda o: o.precio_unitario or 1e18)[:2]
    lista: list[Oferta] = []
    for o in candidatas[:opciones.verificar_top] + baratas:
        if o not in lista:
            lista.append(o)
    progreso(f"Verificando {len(lista)} precios directamente en las tiendas...")
    for o in lista:
        v = verificar_oferta(o, int(o.paquetes_necesarios or 1), opciones.usar_navegador,
                             _fuente_de(o, elegidas))
        marca = "OK" if v.ok else "X"
        progreso(f"  [{marca}] {o.tienda}: {v.detalle[:80]}")


# ---------------------------------------------------------------------------
# Eleccion, estadisticas y alertas
# ---------------------------------------------------------------------------
def _elegir(resultado: EstudioItem, ofertas: list[Oferta]) -> None:
    validas = [o for o in _validas(ofertas) if o.disponible is not False
               and not any("cantidad insuficiente" in n.lower() for n in o.notas)]
    recomendables = [o for o in validas if o.verificada and o.metodo in METODOS_CONFIABLES]
    if not recomendables:
        recomendables = [o for o in validas if o.metodo in METODOS_CONFIABLES]
    if recomendables:
        resultado.recomendada_id = max(recomendables, key=lambda o: o.puntaje).id
    confiables = [o for o in validas if o.metodo in METODOS_CONFIABLES]
    if confiables:
        resultado.mas_barata_id = min(confiables, key=lambda o: o.costo_total or 1e18).id
        con_resenas = [o for o in confiables if o.calificacion and (o.resenas or 0) >= 5]
        if con_resenas:
            resultado.mejor_calificada_id = max(
                con_resenas, key=lambda o: (o.calificacion or 0, o.resenas or 0)).id


def _estadisticas(r: EstudioItem) -> Estadisticas:
    validas = [o for o in _validas(r.ofertas) if o.metodo in METODOS_CONFIABLES and o.precio_unitario]
    if not validas:
        return Estadisticas()
    unitarios = [o.precio_unitario for o in validas]
    rec = r.oferta(r.recomendada_id)
    mediana = statistics.median(unitarios)
    total_med = mediana * max(r.item.cantidad, 1)
    return Estadisticas(
        ofertas_validas=len(validas),
        tiendas=len({o.tienda for o in validas}),
        precio_unitario_min=min(unitarios),
        precio_unitario_max=max(unitarios),
        precio_unitario_mediana=round(mediana, 2),
        costo_total_min=min(o.costo_total for o in validas if o.costo_total),
        costo_total_recomendado=rec.costo_total if rec else None,
        ahorro_vs_mediana=round(total_med - rec.costo_total, 2) if rec and rec.costo_total else None,
    )


def _alertas_automaticas(r: EstudioItem) -> list[str]:
    alertas = []
    e = r.estadisticas
    if r.recomendada_id is None:
        alertas.append("No hay ninguna opcion verificable que cumpla lo pedido: se sugiere "
                       "cotizacion directa a proveedores.")
    else:
        rec = r.oferta(r.recomendada_id)
        if rec and not rec.verificada:
            alertas.append("La opcion recomendada no se pudo verificar en la tienda: confirmar "
                           "precio antes de comprar.")
        if rec and rec.stock is not None and rec.paquetes_necesarios and rec.stock < rec.paquetes_necesarios:
            alertas.append(f"La tienda recomendada reporta solo {rec.stock} unidades en stock y se "
                           f"necesitan {int(rec.paquetes_necesarios)}.")
    if e.ofertas_validas and e.tiendas < 2:
        alertas.append("Solo una tienda tiene el producto: poca base de comparacion.")
    if e.precio_unitario_min and e.precio_unitario_max and e.precio_unitario_max > 3 * e.precio_unitario_min:
        alertas.append("Hay mucha dispersion de precios: revisar que las presentaciones sean comparables.")
    return alertas


def _resumir(r: EstudioItem, llm: CadenaLLM, progreso: Progreso) -> None:
    e = r.estadisticas
    rec = r.oferta(r.recomendada_id)
    barata = r.oferta(r.mas_barata_id)
    fmt = lambda v: f"${v:,.0f}".replace(",", ".") if v is not None else "n/d"  # noqa: E731

    def linea(o: Oferta | None) -> str:
        if not o:
            return "ninguna"
        return (f"{o.tienda} - {o.titulo[:90]} | precio {fmt(o.precio)} por "
                f"{o.unidades_paquete:g} und | {fmt(o.precio_unitario)} por unidad | total "
                f"{fmt(o.costo_total)} | calificacion {o.calificacion or 'sin datos'} "
                f"({o.resenas or 0} resenas) | relevancia {o.relevancia} | "
                f"verificado: {'si' if o.verificada else 'no'}")

    otras = [o for o in r.ofertas if o.relevancia in ("exacto", "equivalente")
             and o.id not in (r.recomendada_id,)][:6]
    relacionadas = [o for o in r.ofertas if o.relevancia == "relacionado"][:3]
    datos = f"""\
PEDIDO: {r.item.cantidad:g} {r.item.unidad} de "{r.item.descripcion}" {r.item.especificaciones}
OFERTAS VALIDAS: {e.ofertas_validas} en {e.tiendas} tiendas
PRECIO POR UNIDAD: minimo {fmt(e.precio_unitario_min)}, mediana {fmt(e.precio_unitario_mediana)}, maximo {fmt(e.precio_unitario_max)}
RECOMENDADA: {linea(rec)}
MAS BARATA: {linea(barata)}
AHORRO DE LA RECOMENDADA FRENTE A LA MEDIANA: {fmt(e.ahorro_vs_mediana)}
OTRAS OPCIONES:
""" + "\n".join("  - " + linea(o) for o in otras) + """
RELACIONADAS (no cumplen todo lo pedido):
""" + ("\n".join("  - " + linea(o) for o in relacionadas) or "  ninguna") + """
ALERTAS DEL SISTEMA:
""" + ("\n".join("  - " + a for a in r.alertas) or "  ninguna") + (
        f"\nNOTAS DEL PLAN: {r.plan.notas}" if r.plan and r.plan.notas else "")

    if llm.hay_modelo and e.ofertas_validas:
        try:
            res = llm.json(sistema=SISTEMA_RESUMEN, usuario=datos, esquema=Resumen, progreso=progreso)
            r.resumen, r.justificacion = res.resumen, res.justificacion
            for a in res.alertas:
                if a not in r.alertas:
                    r.alertas.append(a)
            return
        except SinModeloDisponible:
            pass
    # Respaldo sin IA
    if e.ofertas_validas:
        r.resumen = (f"Se encontraron {e.ofertas_validas} opciones validas en {e.tiendas} tiendas. "
                     f"El precio por unidad va de {fmt(e.precio_unitario_min)} a "
                     f"{fmt(e.precio_unitario_max)} (mediana {fmt(e.precio_unitario_mediana)}).")
        if rec:
            r.justificacion = (f"Se recomienda {rec.tienda} por su relacion precio-calidad: "
                               f"{fmt(rec.precio_unitario)} por unidad, total {fmt(rec.costo_total)}.")
    else:
        r.resumen = "No se encontraron opciones que cumplan lo pedido."
