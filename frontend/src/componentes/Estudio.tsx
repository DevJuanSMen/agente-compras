import { useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, BadgeCheck, CheckCircle2, ChevronDown, ChevronRight, CircleSlash, ExternalLink, Info, Loader2,
  Star, Trash2, TrendingDown, XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api } from '../api'
import type { LineaEstudio, Oferta, VistaEstudio } from '../tipos'
import { fecha, hace, pesos, TEXTO_METODO } from '../util'
import { Aviso, BarraProgreso, Boton, Etiqueta, Tarjeta } from './ui'

type Filtro = 'validas' | 'relacionadas' | 'descartadas' | 'todas'

export function ProgresoEstudio({ vista }: { vista: VistaEstudio }) {
  const e = vista.estudio
  const [verBitacora, setVerBitacora] = useState(false)
  if (!e || (e.estado !== 'en_cola' && e.estado !== 'en_proceso')) return null
  return (
    <Tarjeta className="border-sky-200 bg-sky-50/40">
      <div className="flex items-start gap-3">
        <Loader2 className="mt-0.5 size-5 shrink-0 animate-spin text-sky-600" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="font-semibold text-slate-800">
              {e.estado === 'en_cola' ? 'Estudio de mercado en cola' : 'El agente está haciendo el estudio de mercado'}
              {e.version > 1 && <span className="ml-1 text-sm font-normal text-slate-500">(versión {e.version})</span>}
            </h3>
            <span className="text-sm font-medium text-sky-800">{Math.round(e.progreso)}%</span>
          </div>
          <div className="my-2"><BarraProgreso valor={e.progreso} /></div>
          <p className="latido truncate text-sm text-slate-600">{e.paso}</p>
          <p className="mt-1 text-xs text-slate-500">
            Busca en las tiendas, revisa qué productos corresponden a lo pedido y confirma cada precio directamente en la
            tienda. Puede tardar unos minutos; le avisaremos cuando termine (puede cerrar esta página).
          </p>
          {e.instrucciones && <p className="mt-1 text-xs text-slate-600"><b>Instrucciones:</b> {e.instrucciones}</p>}
          <button onClick={() => setVerBitacora(!verBitacora)} className="mt-2 flex items-center gap-1 text-xs font-medium text-sky-800 hover:underline">
            {verBitacora ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />} Ver qué está haciendo
          </button>
          {verBitacora && (
            <ol className="mt-2 max-h-64 overflow-y-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-200">
              {e.bitacora.map((b, i) => (
                <li key={i}><span className="text-slate-500">{new Date(b.t).toLocaleTimeString('es-CO')}</span> {b.m}</li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </Tarjeta>
  )
}

export function LineaEstudioTarjeta({ linea, n, rid, puedeElegir, puedeCotizar }: {
  linea: LineaEstudio; n: number; rid: number; puedeElegir: boolean; puedeCotizar: boolean
}) {
  const qc = useQueryClient()
  const [filtro, setFiltro] = useState<Filtro>('validas')
  const [eligiendo, setEligiendo] = useState<string | null>(null)
  const it = linea.item
  const seleccion = it.seleccion?.id
  const rec = linea.ofertas.find((o) => o.id === linea.recomendada_id)
  const est = linea.estadisticas

  const visibles = linea.ofertas.filter((o) => {
    if (filtro === 'validas') return o.relevancia === 'exacto' || o.relevancia === 'equivalente'
    if (filtro === 'relacionadas') return o.relevancia === 'relacionado'
    if (filtro === 'descartadas') return o.relevancia === 'descartado' || o.relevancia === 'sin_clasificar'
    return true
  })
  const conteo = (f: Filtro) => linea.ofertas.filter((o) =>
    f === 'validas' ? ['exacto', 'equivalente'].includes(o.relevancia)
      : f === 'relacionadas' ? o.relevancia === 'relacionado'
        : f === 'descartadas' ? ['descartado', 'sin_clasificar'].includes(o.relevancia) : true).length

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['estudio', String(rid)] })
    qc.invalidateQueries({ queryKey: ['requerimiento', String(rid)] })
  }

  const elegir = async (oferta_id: string | null) => {
    setEligiendo(oferta_id ?? 'ninguna')
    try {
      await api(`/requerimientos/${rid}/items/${it.id}/seleccion`, { cuerpo: { oferta_id } })
      refrescar()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setEligiendo(null)
    }
  }

  const excluir = async (excluido: boolean) => {
    try {
      await api(`/requerimientos/${rid}/items/${it.id}/excluir`, { cuerpo: { excluido } })
      refrescar()
    } catch (e) {
      toast.error((e as Error).message)
    }
  }

  const borrarCotizacion = async (cid: number) => {
    if (!confirm('¿Eliminar esta cotización?')) return
    await api(`/requerimientos/${rid}/cotizaciones/${cid}`, { metodo: 'DELETE' })
    refrescar()
  }

  return (
    <Tarjeta sinPadding className={it.excluido ? 'opacity-60' : ''}>
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-4 py-3">
        <div className="min-w-0">
          <div className="text-xs font-semibold text-slate-400">ÍTEM {n}{it.programa && ` · ${it.programa}`}</div>
          <h3 className="font-semibold text-slate-800">{it.descripcion}</h3>
          <p className="text-sm text-slate-500">
            {it.cantidad.toLocaleString('es-CO')} {it.unidad}{it.especificaciones && ` · ${it.especificaciones}`}
            {it.marca_preferida && ` · Marca: ${it.marca_preferida}${it.acepta_equivalentes ? ' o equivalente' : ''}`}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {it.excluido ? <Etiqueta color="rojo">Excluido de la compra</Etiqueta>
            : seleccion ? <Etiqueta color="verde"><CheckCircle2 className="size-3" /> Opción elegida</Etiqueta>
              : puedeElegir ? <Etiqueta color="ambar">Pendiente de elegir</Etiqueta> : null}
          {puedeElegir && (
            <Boton variante="fantasma" tamano="sm" onClick={() => excluir(!it.excluido)}>
              {it.excluido ? 'Volver a incluir' : 'Excluir de la compra'}
            </Boton>
          )}
        </div>
      </header>

      {linea.error ? (
        <div className="p-4"><Aviso tipo="error">No se pudo estudiar esta línea: {linea.error}</Aviso></div>
      ) : !linea.ofertas.length && !linea.resumen ? (
        <div className="p-4 text-sm text-slate-500">Esperando resultados de esta línea…</div>
      ) : (
        <div className="space-y-4 p-4">
          {rec && (
            <div className="rounded-lg border border-marca-300 bg-marca-50 p-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-marca-800">
                <Star className="size-3.5 fill-marca-500 text-marca-500" /> Recomendación del agente · mejor precio en relación a la calidad
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{rec.tienda} — {rec.titulo}</p>
                  <p className="text-sm text-slate-600">
                    {pesos(rec.precio)}{rec.unidades_paquete !== 1 && ` por paquete de ${rec.unidades_paquete}`} ·{' '}
                    <b>{pesos(rec.precio_unitario)} por unidad</b> · {rec.paquetes_necesarios} × = <b>{pesos(rec.costo_total)}</b> para el pedido
                  </p>
                  <SelloVerificacion o={rec} />
                </div>
                <div className="flex gap-2">
                  {rec.url && <a href={rec.url} target="_blank" rel="noreferrer"><Boton variante="secundario" tamano="sm" icono={<ExternalLink className="size-3.5" />}>Ver en tienda</Boton></a>}
                  {puedeElegir && !it.excluido && (seleccion === rec.id
                    ? <Boton tamano="sm" variante="exito" icono={<CheckCircle2 className="size-3.5" />} onClick={() => elegir(null)}>Elegida</Boton>
                    : <Boton tamano="sm" cargando={eligiendo === rec.id} onClick={() => elegir(rec.id)}>Elegir esta</Boton>)}
                </div>
              </div>
            </div>
          )}

          <div className="grid gap-3 text-sm md:grid-cols-4">
            <Dato titulo="Opciones válidas" valor={`${est.ofertas_validas ?? 0} en ${est.tiendas ?? 0} tiendas`} />
            <Dato titulo="Precio por unidad" valor={est.precio_unitario_min ? `${pesos(est.precio_unitario_min)} – ${pesos(est.precio_unitario_max)}` : '—'} />
            <Dato titulo="Mediana del mercado" valor={pesos(est.precio_unitario_mediana)} />
            <Dato titulo="Ahorro vs. mediana" valor={est.ahorro_vs_mediana && est.ahorro_vs_mediana > 0 ? pesos(est.ahorro_vs_mediana) : '—'} resaltar />
          </div>

          {(linea.resumen || linea.justificacion) && (
            <div className="space-y-1 text-sm text-slate-700">
              {linea.resumen && <p>{linea.resumen}</p>}
              {linea.justificacion && <p className="text-slate-600"><b>Por qué la recomendada:</b> {linea.justificacion}</p>}
            </div>
          )}
          {linea.alertas.length > 0 && (
            <ul className="space-y-1">
              {linea.alertas.map((a, i) => (
                <li key={i} className="flex gap-2 rounded-md bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">
                  <AlertTriangle className="mt-px size-3.5 shrink-0" />{a}
                </li>
              ))}
            </ul>
          )}

          <div>
            <div className="mb-2 flex flex-wrap gap-1">
              {(['validas', 'relacionadas', 'descartadas', 'todas'] as Filtro[]).map((f) => (
                <button key={f} onClick={() => setFiltro(f)}
                  className={`rounded-full px-2.5 py-1 text-xs font-medium ${filtro === f ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>
                  {{ validas: 'Cumplen lo pedido', relacionadas: 'Relacionados / sustitutos', descartadas: 'Descartados', todas: 'Todos' }[f]} ({conteo(f)})
                </button>
              ))}
            </div>
            <div className="overflow-x-auto rounded-lg border border-slate-200">
              <table className="tabla">
                <thead>
                  <tr><th>Tienda</th><th>Producto</th><th className="text-right">Precio</th><th className="text-right">$/unidad</th>
                    <th className="text-right">Total pedido</th><th>Calif.</th><th>Verificación</th>{puedeElegir && <th />}</tr>
                </thead>
                <tbody>
                  {visibles.map((o) => (
                    <FilaOferta key={o.id} o={o} linea={linea} elegida={seleccion === o.id}
                      accion={puedeElegir && !it.excluido ? (
                        seleccion === o.id
                          ? <Boton tamano="sm" variante="exito" onClick={() => elegir(null)} title="Quitar selección">Elegida</Boton>
                          : o.relevancia === 'descartado' || o.metodo === 'buscador'
                            ? <span className="text-[11px] text-slate-400" title={o.metodo === 'buscador' ? 'Precio no verificable' : 'No corresponde a lo pedido'}>No elegible</span>
                            : <Boton tamano="sm" variante="secundario" cargando={eligiendo === o.id} onClick={() => elegir(o.id)}>Elegir</Boton>
                      ) : null} />
                  ))}
                  {!visibles.length && <tr><td colSpan={8} className="py-6 text-center text-slate-500">Sin productos en esta categoría</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          {linea.cotizaciones.length > 0 && puedeCotizar && (
            <div className="text-xs text-slate-600">
              <b>Cotizaciones formales cargadas:</b>{' '}
              {linea.cotizaciones.map((c) => (
                <span key={c.id} className="mr-2 inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5">
                  {c.proveedor_nombre} {pesos(c.precio_unitario)}
                  <button onClick={() => borrarCotizacion(c.id)} className="text-slate-400 hover:text-red-600"><Trash2 className="size-3" /></button>
                </span>
              ))}
            </div>
          )}

          {linea.fuentes.length > 0 && (
            <details className="text-xs text-slate-500">
              <summary className="cursor-pointer select-none">Fuentes consultadas ({linea.fuentes.length}) {linea.plan && `· búsquedas: ${linea.plan.consultas.join(' | ')}`}</summary>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {linea.fuentes.map((f) => (
                  <span key={f.fuente} title={f.detalle}
                    className={`rounded px-1.5 py-0.5 ${f.estado === 'ok' ? 'bg-marca-50 text-marca-800' : f.estado === 'error' ? 'bg-red-50 text-red-700' : 'bg-slate-100'}`}>
                    {f.nombre}: {f.estado === 'ok' ? `${f.resultados} productos` : f.estado === 'error' ? 'no respondió' : 'sin resultados'}
                  </span>
                ))}
              </div>
              {linea.plan?.atributos_clave?.length ? <p className="mt-1">Atributos exigidos: {linea.plan.atributos_clave.join(', ')}</p> : null}
              {linea.plan?.notas && <p className="mt-1">Nota del agente: {linea.plan.notas}</p>}
              {linea.generado_en && <p className="mt-1">Generado {fecha(linea.generado_en, true)} en {Math.round(linea.duracion_s ?? 0)} s</p>}
            </details>
          )}
        </div>
      )}
    </Tarjeta>
  )
}

function Dato({ titulo, valor, resaltar }: { titulo: string; valor: string; resaltar?: boolean }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{titulo}</div>
      <div className={`font-semibold ${resaltar ? 'text-marca-700' : 'text-slate-800'}`}>{valor}</div>
    </div>
  )
}

function SelloVerificacion({ o }: { o: Oferta }) {
  const v = o.verificacion
  if (o.metodo === 'manual') return <span className="mt-1 inline-flex items-center gap-1 text-xs text-marca-700"><BadgeCheck className="size-3.5" /> Cotización formal del proveedor</span>
  if (v?.ok) return (
    <span className="mt-1 inline-flex items-center gap-1 text-xs text-marca-700" title={v.detalle}>
      <BadgeCheck className="size-3.5" /> Precio confirmado en la tienda {hace(v.momento)} ({v.metodo})
    </span>
  )
  if (v) return <span className="mt-1 inline-flex items-center gap-1 text-xs text-amber-700"><AlertTriangle className="size-3.5" /> {v.detalle}</span>
  return <span className="mt-1 inline-flex items-center gap-1 text-xs text-slate-500"><Info className="size-3.5" /> {TEXTO_METODO[o.metodo]} · sin verificación individual</span>
}

function FilaOferta({ o, linea, elegida, accion }: { o: Oferta; linea: LineaEstudio; elegida: boolean; accion: React.ReactNode }) {
  const v = o.verificacion
  return (
    <tr className={elegida ? 'bg-marca-50/70' : o.relevancia === 'descartado' ? 'text-slate-400' : ''}>
      <td className="whitespace-nowrap">
        <div className="font-medium">{o.tienda}</div>
        {o.vendedor && o.vendedor !== o.tienda && <div className="text-[11px] text-slate-500">Vende: {o.vendedor}</div>}
      </td>
      <td className="min-w-64">
        <div className="flex flex-wrap gap-1">
          {o.id === linea.recomendada_id && <Etiqueta color="verde"><Star className="size-3" />Recomendada</Etiqueta>}
          {o.id === linea.mas_barata_id && <Etiqueta color="azul"><TrendingDown className="size-3" />Más barata</Etiqueta>}
          {o.id === linea.mejor_calificada_id && <Etiqueta color="violeta">Mejor calificada</Etiqueta>}
          {o.relevancia === 'equivalente' && <Etiqueta>Equivalente</Etiqueta>}
          {o.metodo === 'manual' && <Etiqueta color="verde">Cotización formal</Etiqueta>}
          {o.disponible === false && <Etiqueta color="rojo">Agotado</Etiqueta>}
        </div>
        {o.url ? <a href={o.url} target="_blank" rel="noreferrer" className="text-slate-800 hover:text-marca-700 hover:underline">{o.titulo}</a> : o.titulo}
        {o.marca && <span className="ml-1 text-xs text-slate-400">· {o.marca}</span>}
        {o.motivo && <div className="text-[11px] text-slate-500">{o.motivo}</div>}
        {o.notas.map((nota, i) => <div key={i} className="text-[11px] text-amber-700">{nota}</div>)}
      </td>
      <td className="whitespace-nowrap text-right">
        {pesos(o.precio)}
        {o.precio_antes && <div className="text-[11px] text-slate-400 line-through">{pesos(o.precio_antes)}</div>}
        {o.unidades_paquete !== 1 && <div className="text-[11px] text-slate-500">paquete x{o.unidades_paquete}</div>}
      </td>
      <td className="whitespace-nowrap text-right font-medium">{pesos(o.precio_unitario)}</td>
      <td className="whitespace-nowrap text-right">{pesos(o.costo_total)}{o.paquetes_necesarios && o.unidades_paquete !== 1 ? <div className="text-[11px] text-slate-500">{o.paquetes_necesarios} paq.</div> : null}</td>
      <td className="whitespace-nowrap text-xs">{o.calificacion ? <>★ {o.calificacion.toFixed(1)} <span className="text-slate-400">({o.resenas ?? 0})</span></> : '—'}</td>
      <td className="text-xs">
        {o.metodo === 'manual' ? <span className="text-marca-700">Formal</span>
          : v?.ok ? <span className="inline-flex items-center gap-1 text-marca-700" title={`${v.metodo}: ${v.detalle}`}><BadgeCheck className="size-3.5" />Confirmado</span>
            : v ? <span className="inline-flex items-center gap-1 text-amber-700" title={v.detalle}><XCircle className="size-3.5" />No confirmado</span>
              : o.metodo === 'buscador' ? <span className="inline-flex items-center gap-1 text-red-600" title="El precio sale del extracto del buscador"><CircleSlash className="size-3.5" />No verificable</span>
                : <span className="text-slate-400" title={TEXTO_METODO[o.metodo]}>Catálogo</span>}
      </td>
      {accion !== null && <td className="whitespace-nowrap">{accion}</td>}
    </tr>
  )
}
