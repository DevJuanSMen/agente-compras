"""Logica de investigacion compartida por todos los proveedores de texto.

Aqui vive el agente completo. Un proveedor concreto (Gemini, Groq, NVIDIA)
solo tiene que implementar `_completar()`: mandar mensajes y devolver texto.
Todo lo demas -- busqueda por tienda, lectura de paginas, map-reduce, modo
JSON con reparacion, control de tasa -- es igual para todos.

Forma de la fase 2 (map-reduce, no bucle agentico)
--------------------------------------------------
    buscar por tienda (sin LLM) -> leer paginas (sin LLM)
      -> MAP:    resumir las paginas, en lotes de `paginas_por_llamada`
      -> REDUCE: una sola llamada que arma el dossier

Ninguna llamada acumula historial: eso evita que el contexto crezca al cuadrado.
El tamano del lote se ajusta al cuello de botella del proveedor -- ver
`AgenteTexto.paginas_por_llamada`.
"""
from __future__ import annotations

import json
import re
from abc import abstractmethod
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from . import busqueda, config, tiendas
from .core import AgenteBase, Progreso, Uso, _formatear_precio, _nada, fijar_precio_cotizado
from .limitador import LimitadorTPM, estimar_tokens_mensajes
from .models import AnalisisItem, Cotizacion, LineaCotizacion
from .prompts import (
    SISTEMA_DOSSIER,
    SISTEMA_EXTRACCION,
    SISTEMA_FICHA_TIENDA,
    SISTEMA_NOTA,
    SISTEMA_SINTESIS,
    prompt_ficha_tienda,
    prompt_nota_pagina,
    prompt_redactar_dossier,
    prompt_sintesis,
)

MAX_INTENTOS_JSON = 3
CARACTERES_POR_PAGINA = 5_000
RESULTADOS_POR_CONSULTA = 4
MAX_COMPETIDORES = 4

_FALLO_LECTURA = (
    "El sitio respondio", "No se pudo leer", "No es una pagina",
    "La pagina no expuso", "URL invalida",
)


@dataclass
class Respuesta:
    texto: str
    entrada: int = 0
    salida: int = 0
    motivo_fin: str = ""


@dataclass
class AgenteTexto(AgenteBase):
    """Agente completo sobre un `_completar()` que implementa cada proveedor."""

    uso: Uso = field(default_factory=Uso)
    limitador: LimitadorTPM | None = None
    # Cuantas paginas entran en una misma llamada. Adapta la forma del trabajo
    # al cuello de botella del proveedor, que no es el mismo en todos:
    #   Groq free tier:   8.000 tokens/min pero 1.000 peticiones/min.
    #                     Le sobran peticiones y le faltan tokens -> 1 pagina.
    #   Gemini free tier: contexto enorme pero pocas peticiones por dia.
    #                     Le sobran tokens y le faltan peticiones -> todas.
    paginas_por_llamada: int = 1

    # ------------------------------------------------------------------
    # Lo unico que debe implementar un proveedor
    # ------------------------------------------------------------------
    @abstractmethod
    def _completar(
        self,
        mensajes: list[dict],
        *,
        max_tokens: int,
        esfuerzo: str,
        formato_json: bool,
        progreso: Progreso,
    ) -> Respuesta:
        """Manda `mensajes` al modelo y devuelve su texto.

        `mensajes` sigue la forma de OpenAI: [{"role": "system"|"user", "content": str}].
        """

    @property
    def nombre_modelo(self) -> str:
        return config.modelo_actual()

    # ------------------------------------------------------------------
    # Fase 1 - lectura de la solicitud
    # ------------------------------------------------------------------
    def extraer(
        self,
        *,
        texto: str | None = None,
        pdf_bytes: bytes | None = None,
        nombre_pdf: str = "cotizacion.pdf",
        progreso: Progreso = _nada,
    ) -> Cotizacion:
        if not texto and not pdf_bytes:
            raise ValueError("Se necesita un PDF o un texto de entrada.")

        partes: list[str] = []
        if pdf_bytes:
            progreso(f"Leyendo {nombre_pdf} ({len(pdf_bytes) / 1024:.0f} KB)...")
            contenido = self._texto_de_pdf(pdf_bytes)
            if not contenido.strip():
                raise RuntimeError(
                    "El PDF no tiene capa de texto (parece escaneado). Transcribe la "
                    "cotizacion a texto, o usa AGENTE_PROVEEDOR=anthropic, que lee "
                    "PDF nativo incluso escaneado."
                )
            partes.append(f"=== TEXTO DEL PDF ===\n{contenido[:12_000]}")
        if texto:
            partes.append(f"=== TEXTO DEL USUARIO ===\n{texto}")

        cot = self._pedir_json(
            sistema=SISTEMA_EXTRACCION,
            usuario="Estructura la siguiente solicitud de compra.\n\n" + "\n\n".join(partes),
            esquema=Cotizacion,
            progreso=progreso,
        )
        progreso(f"Detectados {len(cot.items)} item(s).")
        return cot

    # ------------------------------------------------------------------
    # Fase 2 - investigacion
    # ------------------------------------------------------------------
    def investigar(
        self,
        item: LineaCotizacion,
        *,
        pais: str,
        moneda: str,
        competidores: list[str],
        progreso: Progreso = _nada,
        dominios: list[str] | None = None,
    ) -> str:
        etiqueta = _etiqueta(item)
        dominios = dominios or []
        rivales = competidores[:MAX_COMPETIDORES]

        # --- A. Donde comprarlo: una busqueda por tienda ------------------
        fichas: list[str] = []
        if dominios:
            progreso(f"Buscando el producto en {len(dominios)} tienda(s)...")
            por_tienda = busqueda.buscar_en_tiendas(
                etiqueta, dominios, por_tienda=2, region=_region(pais)
            )
            progreso(f"Encontrado en {len(por_tienda)} de {len(dominios)} tiendas.")
            leidas_tienda: list[tuple[str, busqueda.Resultado, str]] = []
            for dominio, resultados in por_tienda.items():
                nombre = tiendas.nombre_de_dominio(dominio)
                r = resultados[0]  # la mejor coincidencia por tienda
                progreso(f"Leyendo {nombre}: {r.url[:70]}")
                pagina = busqueda.leer(r.url, max_caracteres=CARACTERES_POR_PAGINA)
                if pagina.startswith(_FALLO_LECTURA):
                    progreso(f"  (sin acceso: {pagina[:90]})")
                    # El extracto del buscador suele traer el precio igual.
                    fichas.append(
                        f"### {nombre} | {r.url}\n"
                        f"(no se pudo leer la pagina; extracto del buscador)\n"
                        f"{r.titulo}\n{r.resumen}"
                    )
                    continue
                leidas_tienda.append((nombre, r, pagina))

            for lote in _en_lotes(leidas_tienda, self.paginas_por_llamada):
                fichas += self._fichas_de_tiendas(item, lote, progreso)

        # --- B. Precio de mercado, opiniones y problemas ------------------
        vistas: set[str] = set(re.findall(r"https?://\S+", "\n".join(fichas)))
        generales: list[busqueda.Resultado] = []
        for consulta in _consultas_generales(item, pais)[: config.MAX_BUSQUEDAS]:
            progreso(f"Buscando: {consulta}")
            for r in busqueda.buscar(consulta, max_resultados=RESULTADOS_POR_CONSULTA,
                                     region=_region(pais)):
                if r.url and r.url not in vistas:
                    vistas.add(r.url)
                    generales.append(r)

        notas, leidas = self._notas_de(_priorizar(generales), item, config.MAX_FETCHS, progreso)
        progreso(f"{len(notas)} fuentes con datos utiles de {leidas} leidas.")

        # --- C. Alternativas de otras marcas ------------------------------
        notas_rivales: list[str] = []
        cupo = min(len(rivales), max(1, config.MAX_FETCHS // 3)) if rivales else 0
        for marca, consultas in _consultas_rivales(item, rivales).items():
            candidatos: list[busqueda.Resultado] = []
            for c in consultas:
                progreso(f"Buscando: {c}")
                candidatos += [
                    r for r in busqueda.buscar(c, max_resultados=3, region=_region(pais))
                    if r.url and r.url not in vistas
                ]
            bloque = [f"## {marca}"]
            if cupo > 0 and candidatos:
                nrs, _ = self._notas_de(_priorizar(candidatos), item, 1, progreso, etiqueta=marca)
                cupo -= 1
                bloque += nrs
            indicios = "\n".join(
                f"  - {r.titulo} | {r.url}\n    {r.resumen[:180]}" for r in candidatos[:3]
            )
            if indicios:
                bloque.append(f"Indicios del buscador:\n{indicios}")
            if len(bloque) > 1:
                notas_rivales.append("\n".join(bloque))

        extractos = "\n".join(
            f"- {r.titulo} | {r.url}\n  {r.resumen[:200]}" for r in generales[:10]
        )
        if not fichas and not notas and not extractos.strip():
            raise RuntimeError(
                "No se consiguio ninguna evidencia. Si el buscador esta limitando, "
                "espera un minuto o configura AGENTE_BUSCADOR=tavily con TAVILY_API_KEY."
            )

        # --- D. REDUCE ----------------------------------------------------
        progreso("Redactando el dossier...")
        mensajes = [
            {"role": "system", "content": SISTEMA_DOSSIER},
            {
                "role": "user",
                "content": prompt_redactar_dossier(
                    producto=item.descripcion,
                    marca=item.marca,
                    modelo=item.modelo,
                    especificaciones=item.especificaciones,
                    precio=_formatear_precio(item),
                    pais=pais,
                    moneda=moneda,
                    competidores=rivales,
                    fichas="\n\n".join(fichas) or "(no se consulto ninguna tienda)",
                    notas="\n\n".join(notas) or "(ninguna fuente permitio lectura directa)",
                    notas_rivales="\n\n".join(notas_rivales) or "(sin datos de rivales)",
                    extractos=extractos,
                ),
            },
        ]
        dossier = self._pedir_texto(mensajes, max_tokens=4_000, esfuerzo="medium",
                                    progreso=progreso)
        if not dossier:
            raise RuntimeError(
                f"El modelo '{self.nombre_modelo}' no devolvio dossier. "
                "Prueba otro modelo o sube el limite de tokens de salida."
            )
        return dossier

    # ------------------------------------------------------------------
    # Fase 3 - veredicto estructurado
    # ------------------------------------------------------------------
    def sintetizar(
        self,
        dossier: str,
        item: LineaCotizacion,
        *,
        pais: str,
        moneda: str,
        progreso: Progreso = _nada,
    ) -> AnalisisItem:
        progreso("Consolidando el veredicto...")
        analisis = self._pedir_json(
            sistema=SISTEMA_SINTESIS,
            usuario=prompt_sintesis(
                dossier[:18_000],
                precio_cotizado=_formatear_precio(item),
                moneda=moneda,
                pais=pais,
            ),
            esquema=AnalisisItem,
            progreso=progreso,
        )
        return fijar_precio_cotizado(analisis, item, moneda)

    # ------------------------------------------------------------------
    # Pasos del map
    # ------------------------------------------------------------------
    def _fichas_de_tiendas(
        self,
        item: LineaCotizacion,
        lote: list[tuple[str, busqueda.Resultado, str]],
        progreso: Progreso,
    ) -> list[str]:
        """Extrae los datos de compra de una o varias paginas de tienda."""
        bloques = "\n\n".join(
            prompt_ficha_tienda(producto=_etiqueta(item), tienda=nombre, url=r.url, texto=pag)
            for nombre, r, pag in lote
        )
        mensajes = [
            {"role": "system", "content": SISTEMA_FICHA_TIENDA},
            {"role": "user", "content": bloques},
        ]
        try:
            salida = self._pedir_texto(
                mensajes, max_tokens=800 * len(lote), esfuerzo="low", progreso=progreso
            )
        except Exception as exc:
            progreso(f"  (no se pudieron leer las fichas: {str(exc)[:90]})")
            return []
        if not salida:
            return []
        cabecera = "\n".join(f"{nombre} | {r.url}" for nombre, r, _ in lote)
        return [f"### Tiendas leidas:\n{cabecera}\n\n{salida}"]

    def _notas_de(
        self,
        candidatos: list[busqueda.Resultado],
        item: LineaCotizacion,
        cupo: int,
        progreso: Progreso,
        etiqueta: str = "",
    ) -> tuple[list[str], int]:
        """Lee hasta `cupo` paginas y las resume, agrupandolas en lotes."""
        leidas: list[tuple[busqueda.Resultado, str]] = []
        for r in candidatos:
            if len(leidas) >= cupo:
                break
            marca = f" [{etiqueta}]" if etiqueta else ""
            progreso(f"Leyendo{marca}: {r.url[:72]}")
            texto = busqueda.leer(r.url, max_caracteres=CARACTERES_POR_PAGINA)
            if texto.startswith(_FALLO_LECTURA):
                progreso(f"  (sin acceso: {texto[:90]})")
                continue
            leidas.append((r, texto))

        notas: list[str] = []
        for lote in _en_lotes(leidas, self.paginas_por_llamada):
            bloques = "\n\n".join(
                prompt_nota_pagina(producto=_etiqueta(item), url=r.url, texto=t)
                for r, t in lote
            )
            mensajes = [
                {"role": "system", "content": SISTEMA_NOTA},
                {"role": "user", "content": bloques},
            ]
            try:
                salida = self._pedir_texto(
                    mensajes, max_tokens=700 * len(lote), esfuerzo="low", progreso=progreso
                )
            except Exception as exc:
                progreso(f"  (no se pudo resumir: {str(exc)[:90]})")
                continue
            if salida and "SIN DATOS" not in salida.upper()[:40]:
                cabecera = "\n".join(f"URL: {r.url}" for r, _ in lote)
                notas.append(f"### Fuentes:\n{cabecera}\n{salida}")
        return notas, len(leidas)

    # ------------------------------------------------------------------
    # Plomeria
    # ------------------------------------------------------------------
    def _pedir_texto(
        self, mensajes: list[dict], *, max_tokens: int, esfuerzo: str, progreso: Progreso
    ) -> str:
        """Pide texto y se asegura de recibirlo.

        Los modelos de razonamiento gastan el presupuesto pensando y pueden
        devolver contenido vacio sin lanzar error. Cuando pasa, se reintenta
        con menos razonamiento y mas espacio de salida.
        """
        r = self._llamar(mensajes, max_tokens=max_tokens, esfuerzo=esfuerzo,
                         formato_json=False, progreso=progreso)
        if r.texto.strip():
            return r.texto.strip()
        progreso(f"Respuesta vacia (fin={r.motivo_fin}); reintentando con menos razonamiento...")
        r = self._llamar(mensajes, max_tokens=int(max_tokens * 1.6), esfuerzo="low",
                         formato_json=False, progreso=progreso)
        return r.texto.strip()

    def _pedir_json(
        self, *, sistema: str, usuario: str, esquema: type[BaseModel], progreso: Progreso
    ):
        instruccion = (
            f"{sistema}\n\n"
            "Responde UNICAMENTE con un objeto json valido que cumpla este JSON Schema. "
            "Sin markdown, sin cercado de codigo, sin texto antes ni despues. "
            "Todos los campos son obligatorios; usa null o [] cuando no haya dato.\n\n"
            f"{json.dumps(esquema.model_json_schema(), ensure_ascii=False)}"
        )
        base = [
            {"role": "system", "content": instruccion},
            {"role": "user", "content": usuario},
        ]
        mensajes = list(base)
        ultimo_error = ""

        for intento in range(1, MAX_INTENTOS_JSON + 1):
            r = self._llamar(mensajes, max_tokens=config.MAX_TOKENS_JSON, esfuerzo="low",
                             formato_json=True, progreso=progreso)
            try:
                return esquema.model_validate_json(_limpiar_json(r.texto))
            except (ValidationError, ValueError) as exc:
                ultimo_error = str(exc)[:900]
                if intento == MAX_INTENTOS_JSON:
                    break
                progreso(f"El json no cumplio el esquema, reparando "
                         f"({intento}/{MAX_INTENTOS_JSON - 1})...")
                # Se reemplaza el intento anterior en vez de acumularlo: con
                # free tiers ajustados no hay espacio para arrastrar historial.
                mensajes = base + [
                    {"role": "assistant", "content": r.texto[:3_000]},
                    {"role": "user", "content":
                     "Ese json no valido contra el esquema. Corrige exactamente estos "
                     f"errores y devuelve SOLO el json completo:\n{ultimo_error}"},
                ]

        raise RuntimeError(
            f"El modelo '{self.nombre_modelo}' no produjo un json valido para "
            f"{esquema.__name__} en {MAX_INTENTOS_JSON} intentos. Ultimo error:\n{ultimo_error}"
        )

    def _llamar(
        self, mensajes: list[dict], *, max_tokens: int, esfuerzo: str,
        formato_json: bool, progreso: Progreso,
    ) -> Respuesta:
        if self.limitador is not None:
            self.limitador.esperar_cupo(
                estimar_tokens_mensajes(mensajes) + max_tokens, avisar=progreso
            )
        r = self._completar(mensajes, max_tokens=max_tokens, esfuerzo=esfuerzo,
                            formato_json=formato_json, progreso=progreso)
        self.uso.entrada += r.entrada
        self.uso.salida += r.salida
        if self.limitador is not None:
            self.limitador.registrar(r.entrada + r.salida)
        return r

    @staticmethod
    def _texto_de_pdf(datos: bytes) -> str:
        import fitz  # PyMuPDF

        with fitz.open(stream=datos, filetype="pdf") as doc:
            return "\n\n".join(pagina.get_text() for pagina in doc)


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
def _etiqueta(item: LineaCotizacion) -> str:
    """Termino de busqueda que identifica al producto.

    Con modelo, "marca + modelo" basta y es preciso. Sin modelo, la marca sola
    es inservible: buscar "Samsung" devuelve celulares, no la nevera. En ese
    caso manda la descripcion, que es la que trae la categoria y el tamano.
    """
    if item.modelo:
        return f"{item.marca or ''} {item.modelo}".strip()

    base = (item.descripcion or "").strip()
    if not base:
        base = item.categoria or ""
    # Las comparaciones van por palabra, no por subcadena: "pulgadas" contiene
    # "lg" y haria creer que la marca LG ya esta en el texto.
    def palabras(txt: str) -> set[str]:
        return set(re.findall(r"\w+", txt.lower()))

    if item.marca and not palabras(item.marca) <= palabras(base):
        base = f"{item.marca} {base}".strip()
    # La categoria solo se agrega si aporta algo: "nevera no frost" ya esta
    # contenida, palabra por palabra, en "nevera Samsung no frost 300 litros".
    if item.categoria and not palabras(item.categoria) <= palabras(base):
        base = f"{base} {item.categoria}".strip()
    return base[:90] or (item.marca or "producto")


def _region(pais: str) -> str:
    return {
        "Colombia": "co-es", "México": "mx-es", "Mexico": "mx-es", "Chile": "cl-es",
        "Perú": "pe-es", "Peru": "pe-es", "Argentina": "ar-es", "España": "es-es",
    }.get(pais, "co-es")


def _consultas_generales(item: LineaCotizacion, pais: str) -> list[str]:
    etiqueta = _etiqueta(item)
    consultas = [
        f"{etiqueta} precio {pais}",
        f"{etiqueta} opiniones review",
        f"{etiqueta} problemas fallas quejas",
        f"{etiqueta} ficha tecnica especificaciones",
    ]
    if item.precio_unitario is None:
        consultas.insert(0, f"{etiqueta} comprar precio")
    else:
        consultas.insert(0, f"{etiqueta} precio usado")
    return consultas


def _consultas_rivales(item: LineaCotizacion, rivales: list[str]) -> dict[str, list[str]]:
    """Consultas por marca rival, acotadas por el porte o la capacidad del item.

    El calificador se toma de una spec de tamano, nunca de la potencia: pegarle
    "Motor C4.4 121 HP" a la consulta devuelve catalogos de motores.
    """
    categoria = item.categoria or item.descripcion[:40]
    clase = _clase_tamano(item.especificaciones)

    def q(*partes: str) -> str:
        return " ".join(p for p in partes if p)

    return {
        rival: [q(rival, categoria, clase), q(rival, categoria, clase, "precio")]
        for rival in rivales
    }


def _clase_tamano(especificaciones: list[str]) -> str:
    """Porte o capacidad del producto, para acotar la comparativa.

    Acepta toneladas, kilos, litros y pulgadas: sirve igual para una excavadora
    que para una nevera o un televisor.
    """
    for spec in especificaciones:
        texto = spec.lower()
        kg = re.search(r"(\d{1,3}(?:[.,]\d{3})+|\d{4,6})\s*kg", texto)
        if kg:
            return f"{round(int(kg.group(1).replace('.', '').replace(',', '')) / 1000)} toneladas"
        ton = re.search(r"(\d{1,3}(?:[.,]\d{1,2})?)\s*(?:toneladas?|tons?|t)\b", texto)
        if ton:
            return f"{round(float(ton.group(1).replace(',', '.')))} toneladas"
        litros = re.search(r"(\d{2,4})\s*(?:litros?|lt|l)\b", texto)
        if litros:
            return f"{litros.group(1)} litros"
        pulgadas = re.search(r'(\d{2,3})\s*(?:pulgadas?|")', texto)
        if pulgadas:
            return f"{pulgadas.group(1)} pulgadas"
    return ""


# ---------------------------------------------------------------------------
# Priorizacion de fuentes
# ---------------------------------------------------------------------------
_PREFERIDOS = (
    "mercadolibre", "machineryline", "mascus", "machineryzone", "tucarro",
    "reddit", "forum", "foro", "olx", "agriaffaires", "truck1", "autoline",
    "wikipedia", "ritchiespecs", "amazon", "falabella", "homecenter", "alkosto",
)
# Rutas que casi siempre traen opiniones de usuarios. Sin este empujon, las
# paginas de listados se comen el cupo y el informe sale sin comentarios.
_RUTAS_OPINION = ("review", "reviews", "opinion", "opiniones", "comentarios",
                  "forum", "foro", "/r/", "comments")
_EVITAR = (
    "facebook.com", "instagram.com", "tiktok.com", "pinterest.", "x.com", "twitter.com",
    # Redirects publicitarios de buscadores: no son fuentes, son anuncios.
    "bing.com/aclick", "google.com/aclick", "duckduckgo.com/y.js", "/aclk?",
)


def _familia(url: str) -> str:
    """machineryline.mx, .es, .uk y .info son el mismo sitio: misma familia."""
    host = re.sub(r"^https?://", "", url.lower()).split("/")[0]
    host = re.sub(r"^www\.", "", host)
    partes = host.split(".")
    return partes[-2] if len(partes) >= 2 else host


def _priorizar(
    hallazgos: list[busqueda.Resultado], max_por_familia: int = 2
) -> list[busqueda.Resultado]:
    def puntaje(r: busqueda.Resultado) -> int:
        url = r.url.lower()
        if any(d in url for d in _EVITAR):
            return -1
        return (1
                + sum(2 for d in _PREFERIDOS if d in url)
                + sum(3 for d in _RUTAS_OPINION if d in url))

    ordenados = sorted((r for r in hallazgos if puntaje(r) >= 0), key=puntaje, reverse=True)
    vistos: dict[str, int] = {}
    salida = []
    for r in ordenados:
        fam = _familia(r.url)
        if vistos.get(fam, 0) >= max_por_familia:
            continue
        vistos[fam] = vistos.get(fam, 0) + 1
        salida.append(r)
    return salida


def _en_lotes(elementos: list, tamano: int) -> list[list]:
    """Parte una lista en grupos de `tamano`. Con tamano<=0, un solo grupo."""
    if not elementos:
        return []
    if tamano <= 0 or tamano >= len(elementos):
        return [list(elementos)]
    return [elementos[i : i + tamano] for i in range(0, len(elementos), tamano)]


def _limpiar_json(texto: str) -> str:
    """Quita el cercado markdown y el texto sobrante alrededor del objeto."""
    t = texto.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    t = t.strip()
    inicio, fin = t.find("{"), t.rfind("}")
    if inicio != -1 and fin > inicio:
        return t[inicio : fin + 1]
    return t
