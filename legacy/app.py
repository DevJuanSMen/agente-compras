"""Asistente de compras (Streamlit).

    streamlit run app.py

La pantalla esta pensada para quien compra, no para quien la programo: arriba
que se quiere comprar y donde buscarlo, abajo donde conviene comprarlo y por
que. Lo tecnico -- proveedor de IA, modelo, credenciales, tokens y costo --
vive en el panel "Configuracion tecnica" al final de la barra lateral.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import streamlit as st

from agente_compras import config, models, tiendas
from agente_compras.pipeline import analizar

st.set_page_config(page_title="Asistente de Compras", page_icon="🛒", layout="wide")

COLOR_VEREDICTO = {
    "muy_barato": ("#0f7b6c", "Muy por debajo del mercado"),
    "buen_precio": ("#1b7f4b", "Buen precio"),
    "precio_justo": ("#8a6d0b", "Precio de mercado"),
    "caro": ("#b45309", "Por encima del mercado"),
    "muy_caro": ("#b02a2a", "Muy por encima del mercado"),
    "sin_datos": ("#5a6472", "Sin precio que evaluar"),
}
COLOR_RECOMENDACION = {
    "comprar": ("✅", "#1b7f4b", "Comprar"),
    "negociar": ("🤝", "#8a6d0b", "Negociar antes de comprar"),
    "comparar_mas": ("🔍", "#b45309", "Comparar mas opciones"),
    "no_comprar": ("⛔", "#b02a2a", "No comprar"),
}
EMOJI_SENTIMIENTO = {"positivo": "🟢", "neutral": "⚪", "negativo": "🔴"}


def estrellas(valor: float) -> str:
    return "★" * int(round(valor)) + "☆" * (5 - int(round(valor)))


def barra_calificacion(etiqueta: str, valor: float) -> None:
    st.markdown(
        f"<div style='font-size:.8rem;opacity:.7'>{etiqueta}</div>"
        f"<div style='font-size:1.25rem;letter-spacing:2px;color:#d98f00'>{estrellas(valor)}"
        f"<span style='font-size:.9rem;color:inherit;opacity:.6'> {valor:.1f}</span></div>",
        unsafe_allow_html=True,
    )


def money(valor, moneda: str = "") -> str:
    return f"{moneda} {valor:,.0f}".strip() if valor is not None else "—"


# ===========================================================================
# Barra lateral: lo que le importa a quien compra
# ===========================================================================
with st.sidebar:
    st.header("Tu compra")
    pais = st.selectbox(
        "Pais", list(tiendas.CATALOGO),
        index=list(tiendas.CATALOGO).index(config.PAIS_DEFAULT)
        if config.PAIS_DEFAULT in tiendas.CATALOGO else 0,
    )
    moneda = st.text_input("Moneda", value=config.MONEDA_DEFAULT)

    st.divider()
    st.subheader("Donde buscar")
    sugeridas = tiendas.nombres_y_dominios(pais)
    elegidas = st.multiselect(
        "Tiendas", sugeridas, default=sugeridas[:4],
        help="El agente busca el producto dentro de cada tienda y trae precio, "
             "disponibilidad y link de cada una.",
    )
    extra = st.text_area(
        "Otras tiendas (un dominio por linea)", height=70,
        placeholder="miproveedor.com\ndistribuidora.com.co",
    )
    dominios = [tiendas.dominio_de(e) for e in elegidas]
    dominios += [tiendas.dominio_de(l) for l in extra.splitlines() if l.strip()]
    dominios = [d for d in dict.fromkeys(dominios) if d][: config.MAX_TIENDAS]
    if dominios:
        st.caption(f"Se consultaran {len(dominios)}: {', '.join(dominios)}")
    else:
        st.caption("Sin tiendas seleccionadas: solo se buscara precio de mercado general.")

    st.divider()
    st.subheader("Marcas a comparar")
    marcas_txt = st.text_area(
        "Una por linea. Vacio = el agente las deduce.", height=90,
        label_visibility="collapsed", placeholder="LG\nWhirlpool\nMabe",
    )
    competidores = [m.strip() for m in marcas_txt.splitlines() if m.strip()] or None
    max_items = st.slider("Items a analizar", 1, 8, 1)

    # -----------------------------------------------------------------
    # Todo lo tecnico, plegado y al final
    # -----------------------------------------------------------------
    st.divider()
    with st.expander("⚙️ Configuracion tecnica"):
        disponibles = config.proveedores_disponibles()
        opciones = list(config.PROVEEDORES)
        proveedor = st.selectbox(
            "Proveedor de IA", opciones,
            index=opciones.index(config.PROVEEDOR) if config.PROVEEDOR in opciones else 0,
            format_func=lambda p: f"{p}  ✓" if p in disponibles else f"{p}  (sin key)",
        )
        config.PROVEEDOR = proveedor
        nombre_clave = config.nombre_credencial(proveedor)

        if not config.hay_credenciales(proveedor):
            st.warning(f"Falta {nombre_clave}")
            st.caption(f"Se obtiene en {config.DONDE_CONSEGUIRLA.get(proveedor, '')}")
            clave = st.text_input(f"{nombre_clave} para esta sesion", type="password")
            if clave:
                os.environ[nombre_clave] = clave.strip()
                st.success("Clave cargada.")
        else:
            st.success(f"{nombre_clave} detectada")

        modelo = st.text_input("Modelo", value=config.modelo_actual(proveedor))
        if modelo != config.modelo_actual(proveedor):
            setattr(config, {"gemini": "MODELO_GEMINI", "groq": "MODELO_GROQ",
                             "nvidia": "MODELO_NVIDIA",
                             "anthropic": "MODELO_ANTHROPIC"}[proveedor], modelo)

        config.MAX_BUSQUEDAS = st.slider("Busquedas por item", 3, 20, config.MAX_BUSQUEDAS)
        config.MAX_FETCHS = st.slider("Paginas a leer por item", 2, 15, config.MAX_FETCHS)
        st.caption(f"Buscador: `{os.getenv('AGENTE_BUSCADOR', 'ddg')}`")

        st.divider()
        demo = st.button("Cargar informe de ejemplo", use_container_width=True)
        guardado = st.file_uploader("Abrir informe (.json)", type=["json"], key="cargar_json")


# ===========================================================================
# Entrada
# ===========================================================================
st.title("🛒 Asistente de Compras")
st.caption(
    "Decinos que queres comprar. Buscamos el producto en las tiendas que elijas, "
    "comparamos precios, revisamos que dicen los compradores y te decimos donde "
    "conviene comprarlo. Todo con el link para que lo compruebes."
)

col_a, col_b = st.columns([3, 2])
with col_a:
    texto = st.text_area(
        "¿Que queres comprar?", height=110,
        placeholder="Una nevera Samsung no frost de 300 litros\n"
                    "…o: me cotizaron un taladro Bosch GSB 13 RE en $ 320.000, ¿esta bien?",
    )
with col_b:
    pdf = st.file_uploader("¿Tenes una cotizacion? Subila (PDF)", type=["pdf"])

lanzar = st.button("Buscar", type="primary", use_container_width=True,
                   disabled=not (pdf or texto))

if "informe" not in st.session_state:
    st.session_state.informe = None

if demo:
    from agente_compras.ejemplo import informe_ejemplo

    st.session_state.informe = informe_ejemplo()

if guardado is not None and st.session_state.get("_ultimo_json") != guardado.file_id:
    try:
        st.session_state.informe = models.Informe.model_validate_json(
            guardado.getvalue().decode("utf-8")
        )
        st.session_state._ultimo_json = guardado.file_id
        st.success(f"Informe cargado desde {guardado.name}")
    except Exception as exc:
        st.error(f"Ese archivo no es un informe valido: {exc}")

if lanzar:
    if not config.hay_credenciales(proveedor):
        st.error(f"Configura {nombre_clave} en Configuracion tecnica antes de continuar.")
        st.stop()

    bitacora: list[str] = []
    with st.status("Buscando...", expanded=True) as estado:
        caja = st.empty()

        def progreso(linea: str) -> None:
            bitacora.append(linea)
            estado.update(label=linea)
            caja.code("\n".join(bitacora[-14:]), language=None)

        try:
            st.session_state.informe = analizar(
                texto=texto or None,
                pdf_bytes=pdf.getvalue() if pdf else None,
                nombre_pdf=pdf.name if pdf else "cotizacion.pdf",
                pais=pais, moneda=moneda,
                competidores=competidores, dominios=dominios,
                max_items=max_items, progreso=progreso,
            )
        except Exception as exc:
            estado.update(label="Fallo la busqueda", state="error")
            st.exception(exc)
            st.stop()
        estado.update(label="Listo", state="complete", expanded=False)


# ===========================================================================
# Resultados
# ===========================================================================
informe: models.Informe | None = st.session_state.informe
if informe is None:
    st.info("Escribi que queres comprar, o subi una cotizacion, y pulsa Buscar.")
    st.stop()

for nota in informe.notas_investigacion:
    st.warning(nota)

for a in informe.analisis:
    st.divider()
    emoji, color_rec, texto_rec = COLOR_RECOMENDACION[a.recomendacion]
    st.subheader(f"{a.marca} {a.modelo or ''} — {a.producto}")

    # ---- Donde comprar: lo primero que se ve ---------------------------
    st.markdown("### 🏬 Donde comprarlo")
    if not a.donde_comprar:
        st.info(
            "No se encontro el producto publicado en las tiendas consultadas. "
            "Proba agregando otras tiendas en la barra lateral."
        )
    else:
        mejor = a.donde_comprar[0]
        c1, c2, c3 = st.columns([2, 1, 1])
        c1.metric("Mejor opcion", mejor.tienda)
        c2.metric("Precio", money(mejor.precio, mejor.moneda))
        c3.metric("Ahorro", a.ahorro_posible or "—")
        st.markdown(f"**Por que:** {a.mejor_opcion}")

        st.dataframe(
            [
                {
                    "Tienda": o.tienda,
                    "Producto": o.producto,
                    "Precio": money(o.precio, o.moneda),
                    "Disponibilidad": o.disponibilidad,
                    "Envio": o.envio or "—",
                    "Garantia": o.garantia or "—",
                    "Link": o.url,
                }
                for o in a.donde_comprar
            ],
            use_container_width=True, hide_index=True,
            column_config={"Link": st.column_config.LinkColumn("Link", display_text="abrir")},
        )
        for o in a.donde_comprar:
            if o.observaciones:
                st.caption(f"**{o.tienda}:** {o.observaciones}")

    # ---- Veredicto -----------------------------------------------------
    st.markdown("### 📋 Veredicto")
    cab1, cab2 = st.columns([3, 2])
    with cab1:
        st.markdown(
            f"<div style='background:{color_rec}1a;border-left:4px solid {color_rec};"
            f"padding:.7rem 1rem;border-radius:4px'>"
            f"<strong style='color:{color_rec}'>{emoji} {texto_rec}</strong><br>{a.resumen}</div>",
            unsafe_allow_html=True,
        )
    with cab2:
        g1, g2 = st.columns(2)
        with g1:
            barra_calificacion("Producto", a.calificacion_producto)
            barra_calificacion("Marca", a.calificacion_marca)
        with g2:
            barra_calificacion("Precio", a.calificacion_precio)
            barra_calificacion("Global", a.calificacion_global)

    color_precio, leyenda = COLOR_VEREDICTO[a.veredicto_precio]
    rango = a.rango_mercado
    p1, p2, p3, p4 = st.columns(4)
    sin_consulta = a.precio_cotizado is None
    p1.metric(
        "Precio consultado",
        money(a.precio_cotizado, a.moneda_cotizada or "") if not sin_consulta else "—",
        help="No diste un precio a evaluar: el agente compara las tiendas entre si."
        if sin_consulta else None,
    )
    p2.metric("Tipico de mercado", money(rango.tipico, rango.moneda), help=rango.base)
    p3.metric("Rango observado",
              f"{rango.minimo:,.0f} – {rango.maximo:,.0f}" if rango.minimo and rango.maximo else "—",
              help=f"Confianza: {rango.confianza}")
    p4.metric("Desviacion",
              f"{a.desviacion_pct:+.1f}%" if a.desviacion_pct is not None else "—",
              delta=leyenda, delta_color="inverse")
    if sin_consulta and a.veredicto_precio == "sin_datos":
        leyenda = "No diste un precio a evaluar: se comparan las tiendas entre si"
    st.markdown(
        f"<span style='color:{color_precio};font-weight:600'>{leyenda}.</span> "
        f"{a.justificacion_precio}", unsafe_allow_html=True,
    )

    # ---- Detalle -------------------------------------------------------
    tabs = st.tabs(["Otras marcas", "Que dicen los compradores",
                    "Fortalezas y riesgos", "Preguntas al vendedor", "Fuentes"])

    with tabs[0]:
        if not a.alternativas:
            st.info("No se encontraron alternativas comparables con evidencia suficiente.")
        else:
            st.dataframe(
                [
                    {
                        "Marca": alt.marca, "Modelo": alt.modelo,
                        "Calif.": f"{alt.calificacion:.1f}  {estrellas(alt.calificacion)}",
                        "Precio ref.": alt.precio_estimado or "—",
                        "Por que compara": alt.equivalencia,
                        "Link": alt.url or "",
                    }
                    for alt in a.alternativas
                ],
                use_container_width=True, hide_index=True,
                column_config={"Link": st.column_config.LinkColumn("Link", display_text="ver")},
            )
            for alt in a.alternativas:
                with st.expander(f"{alt.marca} {alt.modelo} — detalle"):
                    d1, d2 = st.columns(2)
                    d1.write("**Ventajas**")
                    for v in alt.ventajas:
                        d1.write(f"- {v}")
                    d2.write("**Desventajas**")
                    for v in alt.desventajas:
                        d2.write(f"- {v}")
                    st.caption(f"Disponibilidad local: {alt.disponibilidad_local}")
                    for u in alt.fuentes:
                        st.caption(u)

    with tabs[1]:
        if not a.comentarios_clientes:
            st.info("No se encontraron comentarios de compradores con fuente verificable.")
        for c in a.comentarios_clientes:
            st.markdown(
                f"{EMOJI_SENTIMIENTO[c.sentimiento]} > *{c.texto}*\n\n"
                f"— **{c.autor or 'comprador anonimo'}**, {c.fuente} · [fuente]({c.url})"
            )
            st.write("")

    with tabs[2]:
        f1, f2 = st.columns(2)
        f1.write("**Fortalezas**")
        for x in a.fortalezas:
            f1.success(x, icon="✔️")
        f2.write("**Debilidades**")
        for x in a.debilidades:
            f2.warning(x, icon="⚠️")
        if a.banderas_rojas:
            st.write("**Banderas rojas**")
            for x in a.banderas_rojas:
                st.error(x, icon="🚩")
        if a.costo_total_propiedad:
            st.write("**Costo total de propiedad**")
            for x in a.costo_total_propiedad:
                st.write(f"- {x}")

    with tabs[3]:
        for q in a.preguntas_al_proveedor:
            st.write(f"- {q}")

    with tabs[4]:
        st.caption(f"Confianza del analisis: **{a.confianza_analisis}**")
        for f in a.fuentes:
            st.markdown(f"- [{f.titulo}]({f.url}) · `{f.tipo}`")

# ---- Pie: descarga para el usuario, metricas solo en el panel tecnico ----
st.divider()
sello = f"{datetime.now():%Y%m%d_%H%M}"
c1, c2, c3 = st.columns([1, 1, 3])
with c1:
    try:
        from agente_compras.exportar_pdf import a_bytes

        st.download_button(
            "📄 Descargar PDF", data=a_bytes(informe),
            file_name=f"informe_compras_{sello}.pdf", mime="application/pdf",
            type="primary", use_container_width=True,
        )
    except Exception as exc:
        st.caption(f"No se pudo generar el PDF: {exc}")
with c2:
    st.download_button(
        "Descargar JSON", data=json.dumps(informe.model_dump(), ensure_ascii=False, indent=2),
        file_name=f"informe_compras_{sello}.json", mime="application/json",
        use_container_width=True,
    )
with c3:
    with st.expander("⚙️ Detalle tecnico de esta corrida"):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Items", len(informe.analisis))
        m2.metric("Tokens entrada", f"{informe.tokens_entrada:,}")
        m3.metric("Tokens salida", f"{informe.tokens_salida:,}")
        m4.metric("Costo", f"US$ {informe.costo_usd:.2f}" if informe.costo_usd else "sin tarifa")
        if informe.proveedor:
            st.caption(f"Proveedor: `{informe.proveedor}` · Modelo: `{informe.modelo}`")
        if informe.dossieres:
            st.markdown("**Evidencia cruda que alimento el analisis**")
            st.caption("Sirve para auditar de donde salio cada precio y cada cita.")
            for d in informe.dossieres:
                st.markdown(d)
                st.divider()
