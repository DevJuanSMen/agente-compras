import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Ban, CheckCircle2, Copy, Download, FileSpreadsheet, FileText, Mail, Pencil, RefreshCw, Send, ShoppingCart,
  Sparkles, Upload, XCircle,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api, ErrorApi, urlDescarga } from '../api'
import { LineaEstudioTarjeta, ProgresoEstudio } from '../componentes/Estudio'
import {
  Aviso, Boton, Campo, Cargando, EncabezadoPagina, Insignia, Modal, Pestanas, Tarjeta, Vacio,
} from '../componentes/ui'
import type { Proveedor, Requerimiento, VistaEstudio } from '../tipos'
import { fecha, pesos, TEXTO_ACCION } from '../util'

type Pestana = 'estudio' | 'elementos' | 'ordenes' | 'historial'

export function DetalleRequerimiento() {
  const { id } = useParams()
  const qc = useQueryClient()
  const [pestana, setPestana] = useState<Pestana>('estudio')
  const [modal, setModal] = useState<'' | 'verificar' | 'cancelar' | 'reestudiar' | 'cotizacion' | 'ordenes' | 'solicitud'>('')

  const { data: req, isLoading } = useQuery({
    queryKey: ['requerimiento', id], queryFn: () => api<Requerimiento>(`/requerimientos/${id}`),
    refetchInterval: (q) => (q.state.data?.estado === 'en_estudio' ? 4_000 : false),
  })
  const enCurso = req?.estudios.some((e) => e.estado === 'en_cola' || e.estado === 'en_proceso')
  const { data: vista } = useQuery({
    queryKey: ['estudio', id], queryFn: () => api<VistaEstudio>(`/requerimientos/${id}/estudio`),
    enabled: !!req && req.estudios.length > 0, refetchInterval: enCurso ? 3_000 : false,
  })

  useEffect(() => {
    if (req && !req.estudios.length) setPestana('elementos')
  }, [req])

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['requerimiento', id] })
    qc.invalidateQueries({ queryKey: ['estudio', id] })
    qc.invalidateQueries({ queryKey: ['requerimientos'] })
    qc.invalidateQueries({ queryKey: ['tablero'] })
  }

  const resumenSeleccion = useMemo(() => {
    if (!req) return { elegidos: 0, total: 0, activos: 0 }
    const activos = req.items.filter((i) => !i.excluido)
    const elegidos = activos.filter((i) => i.seleccion)
    return { activos: activos.length, elegidos: elegidos.length, total: elegidos.reduce((s, i) => s + (i.seleccion?.costo_total ?? 0), 0) }
  }, [req])

  if (isLoading || !req) return <Cargando />
  const a = new Set(req.acciones)
  const puedeElegir = a.has('seleccionar')

  const accion = async (ruta: string, cuerpo?: unknown, mensaje?: string) => {
    try {
      await api(`/requerimientos/${id}${ruta}`, { metodo: 'POST', cuerpo })
      if (mensaje) toast.success(mensaje)
      refrescar()
      return true
    } catch (e) {
      toast.error((e as Error).message)
      return false
    }
  }

  return (
    <>
      <EncabezadoPagina
        titulo={<span className="flex flex-wrap items-center gap-2">{req.consecutivo} <Insignia estado={req.estado} texto={req.estado_texto} /></span>}
        subtitulo={`${req.destino} · ${req.nombre_cargo} · ${req.area || 'sin área'} · solicitado ${fecha(req.fecha_solicitud)}${req.fecha_requerida ? ` · requerido para ${fecha(req.fecha_requerida)}` : ''}`}
        acciones={<>
          {a.has('editar') && <Link to={`/requerimientos/${id}/editar`}><Boton variante="secundario" icono={<Pencil className="size-4" />}>Editar</Boton></Link>}
          {a.has('enviar') && <Boton icono={<Send className="size-4" />} onClick={() => accion('/enviar', undefined, 'Requerimiento enviado')}>Enviar</Boton>}
          {a.has('verificar') && <Boton icono={<CheckCircle2 className="size-4" />} onClick={() => setModal('verificar')}>Verificar solicitud</Boton>}
          <Descargas req={req} />
          {a.has('cancelar') && <Boton variante="fantasma" icono={<Ban className="size-4" />} onClick={() => setModal('cancelar')}>Cancelar</Boton>}
        </>}
      />

      {req.estado === 'rechazado' && req.motivo_rechazo && <Aviso tipo="error" className="mb-4"><b>Rechazado:</b> {req.motivo_rechazo}</Aviso>}
      {req.estado === 'cancelado' && <Aviso tipo="alerta" className="mb-4"><b>Cancelado.</b> {req.motivo_rechazo}</Aviso>}
      {req.estado === 'pendiente_verificacion' && <Aviso tipo="alerta" className="mb-4">Esperando verificación y aprobación de la solicitud por el área responsable.</Aviso>}

      {puedeElegir && (
        <div className="sticky top-14 z-20 -mx-4 mb-4 border-y border-marca-200 bg-marca-50/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-xl sm:border">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="text-sm">
              <b>Revisión de compras:</b> {resumenSeleccion.elegidos} de {resumenSeleccion.activos} ítems elegidos
              {resumenSeleccion.total > 0 && <> · total estimado <b>{pesos(resumenSeleccion.total)}</b></>}
            </div>
            <div className="flex flex-wrap gap-2">
              <Boton variante="secundario" tamano="sm" icono={<Sparkles className="size-3.5" />}
                onClick={() => accion('/usar-recomendadas', undefined, 'Se eligieron las recomendaciones del agente')}>Usar recomendaciones</Boton>
              <Boton variante="secundario" tamano="sm" icono={<RefreshCw className="size-3.5" />} onClick={() => setModal('reestudiar')}>Re-cotizar</Boton>
              <Boton variante="secundario" tamano="sm" icono={<Upload className="size-3.5" />} onClick={() => setModal('cotizacion')}>Cotización de proveedor</Boton>
              <Boton variante="secundario" tamano="sm" icono={<Mail className="size-3.5" />} onClick={() => setModal('solicitud')}>Pedir cotización</Boton>
              <Boton tamano="sm" icono={<ShoppingCart className="size-3.5" />} disabled={resumenSeleccion.elegidos < resumenSeleccion.activos || !resumenSeleccion.activos}
                onClick={() => setModal('ordenes')}>Generar órdenes de compra</Boton>
            </div>
          </div>
        </div>
      )}

      <Pestanas<Pestana> valor={pestana} alCambiar={setPestana} opciones={[
        { valor: 'estudio', texto: 'Estudio de mercado' },
        { valor: 'elementos', texto: `Elementos (${req.items.length})` },
        { valor: 'ordenes', texto: `Órdenes (${req.ordenes.length})` },
        { valor: 'historial', texto: 'Historial' },
      ]} />

      <div className="mt-4 space-y-4">
        {pestana === 'estudio' && (
          !req.estudios.length ? (
            <Tarjeta><Vacio titulo="Aún no hay estudio de mercado">
              {req.estado === 'borrador' ? 'Envíe el requerimiento para que el agente comience a cotizar.' : 'El estudio comenzará cuando la solicitud sea aprobada.'}
            </Vacio></Tarjeta>
          ) : !vista ? <Cargando /> : (
            <>
              <ProgresoEstudio vista={vista} />
              {vista.estudio?.estado === 'error' && (
                <Aviso tipo="error">
                  El estudio terminó con errores: {vista.estudio.error.split('\n')[0]}
                  {puedeElegir && <> — puede <button className="font-semibold underline" onClick={() => setModal('reestudiar')}>reintentarlo</button>.</>}
                </Aviso>
              )}
              {vista.estudio?.estado === 'listo' && (
                <p className="text-xs text-slate-500">
                  Estudio versión {vista.estudio.version} · terminado {fecha(vista.estudio.terminado_en, true)}.
                  Los precios de tienda incluyen IVA y se leyeron directamente del catálogo de cada tienda; los marcados como
                  confirmados se verificaron en la tienda en ese momento y se vuelven a verificar al generar la orden.
                </p>
              )}
              {vista.lineas.map((l, n) => (
                <LineaEstudioTarjeta key={l.item.id} linea={l} n={n + 1} rid={req.id} puedeElegir={puedeElegir} puedeCotizar={a.has('cotizacion_manual')} />
              ))}
            </>
          )
        )}

        {pestana === 'elementos' && <Elementos req={req} />}
        {pestana === 'ordenes' && (
          <Tarjeta sinPadding>
            {!req.ordenes.length ? <Vacio titulo="Sin órdenes de compra">Compras genera las órdenes después de revisar el estudio de mercado.</Vacio> : (
              <table className="tabla">
                <thead><tr><th>Número</th><th>Proveedor</th><th>Estado</th><th>Fecha</th><th className="text-right">Total a pagar</th></tr></thead>
                <tbody>{req.ordenes.map((o) => (
                  <tr key={o.id}>
                    <td><Link className="font-medium text-marca-800 hover:underline" to={`/ordenes/${o.id}`}>{o.numero}</Link></td>
                    <td>{o.proveedor_nombre}</td><td><Insignia estado={o.estado} texto={o.estado_texto} /></td>
                    <td>{fecha(o.fecha)}</td><td className="text-right font-medium">{pesos(o.total_pagar)}</td>
                  </tr>))}
                </tbody>
              </table>
            )}
          </Tarjeta>
        )}
        {pestana === 'historial' && (
          <Tarjeta>
            <ol className="relative space-y-4 border-l border-slate-200 pl-5">
              {req.eventos.map((e, i) => (
                <li key={i}>
                  <span className="absolute -left-1.5 mt-1.5 size-3 rounded-full border-2 border-white bg-marca-500" />
                  <p className="text-sm"><b>{e.usuario}</b> · {TEXTO_ACCION[e.accion] ?? e.accion}</p>
                  {e.detalle && <p className="text-xs text-slate-600">{e.detalle}</p>}
                  <p className="text-[11px] text-slate-400">{fecha(e.fecha, true)}</p>
                </li>
              ))}
            </ol>
          </Tarjeta>
        )}
      </div>

      <ModalDecision abierto={modal === 'verificar'} alCerrar={() => setModal('')} titulo="Verificación de la solicitud"
        texto="Revise que la solicitud corresponda a una necesidad real del área antes de pasarla al agente de compras."
        alAprobar={(m) => accion('/verificar', { aprobado: true, motivo: m }, 'Solicitud aprobada: el agente comenzó a cotizar')}
        alRechazar={(m) => accion('/verificar', { aprobado: false, motivo: m }, 'Solicitud rechazada')} />
      <ModalMotivo abierto={modal === 'cancelar'} alCerrar={() => setModal('')} titulo="Cancelar requerimiento" boton="Cancelar requerimiento"
        alConfirmar={(m) => accion('/cancelar', { motivo: m }, 'Requerimiento cancelado')} />
      <ModalReestudio abierto={modal === 'reestudiar'} alCerrar={() => setModal('')} req={req} alHecho={refrescar} />
      <ModalCotizacion abierto={modal === 'cotizacion'} alCerrar={() => setModal('')} req={req} alHecho={refrescar} />
      <ModalSolicitud abierto={modal === 'solicitud'} alCerrar={() => setModal('')} req={req} />
      <ModalOrdenes abierto={modal === 'ordenes'} alCerrar={() => setModal('')} req={req} alHecho={refrescar} />
    </>
  )
}

function Descargas({ req }: { req: Requerimiento }) {
  const hayEstudio = req.estudios.some((e) => e.estado === 'listo' || e.estado === 'error')
  return (
    <div className="relative">
      <details className="group">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 shadow-xs hover:bg-slate-50">
          <Download className="size-4" /> Documentos
        </summary>
        <div className="absolute right-0 z-30 mt-1 w-64 rounded-lg border border-slate-200 bg-white p-1 shadow-lg">
          <a className="flex items-center gap-2 rounded px-3 py-2 text-sm hover:bg-slate-50" target="_blank" rel="noreferrer"
             href={urlDescarga(`/requerimientos/${req.id}/documentos/requerimiento.xlsx`)}><FileSpreadsheet className="size-4 text-emerald-600" /> Formato de requerimiento</a>
          {hayEstudio && <>
            <a className="flex items-center gap-2 rounded px-3 py-2 text-sm hover:bg-slate-50" target="_blank" rel="noreferrer"
               href={urlDescarga(`/requerimientos/${req.id}/documentos/estudio.pdf`)}><FileText className="size-4 text-red-600" /> Estudio de mercado (PDF)</a>
            <a className="flex items-center gap-2 rounded px-3 py-2 text-sm hover:bg-slate-50" target="_blank" rel="noreferrer"
               href={urlDescarga(`/requerimientos/${req.id}/documentos/cuadro.xlsx`)}><FileSpreadsheet className="size-4 text-emerald-600" /> Cuadro comparativo de cotizaciones</a>
          </>}
        </div>
      </details>
    </div>
  )
}

function Elementos({ req }: { req: Requerimiento }) {
  return (
    <Tarjeta sinPadding>
      <div className="overflow-x-auto">
        <table className="tabla">
          <thead><tr><th>#</th><th>Cant.</th><th>Programa / proceso / laboratorio</th><th>Descripción</th><th>Observaciones</th><th>Imagen</th></tr></thead>
          <tbody>
            {req.items.map((i) => (
              <tr key={i.id} className={i.excluido ? 'text-slate-400 line-through' : ''}>
                <td>{i.orden + 1}</td>
                <td className="whitespace-nowrap">{i.cantidad.toLocaleString('es-CO')} {i.unidad}</td>
                <td>{i.programa || '—'}</td>
                <td><div className="font-medium">{i.descripcion}</div>
                  {i.especificaciones && <div className="text-xs text-slate-500">{i.especificaciones}</div>}
                  {i.marca_preferida && <div className="text-xs text-slate-500">Marca: {i.marca_preferida}{i.acepta_equivalentes ? ' o equivalente' : ' (sin equivalentes)'}</div>}
                </td>
                <td className="text-slate-600">{i.observaciones || '—'}</td>
                <td>{i.imagen ? <a href={urlDescarga(`/archivos/${i.imagen}`)} target="_blank" rel="noreferrer">
                  <img src={urlDescarga(`/archivos/${i.imagen}`)} alt="" className="h-12 w-12 rounded border object-cover" /></a> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(req.fuentes.length > 0 || req.sitios_extra.length > 0 || req.justificacion) && (
        <div className="space-y-1 border-t border-slate-100 p-4 text-sm text-slate-600">
          {req.justificacion && <p><b>Justificación:</b> {req.justificacion}</p>}
          {req.fuentes.length > 0 && <p><b>Tiendas indicadas:</b> {req.fuentes.join(', ')}</p>}
          {req.sitios_extra.length > 0 && <p><b>Otros sitios:</b> {req.sitios_extra.join(', ')}</p>}
        </div>
      )}
    </Tarjeta>
  )
}

// ---------------------------------------------------------------------------
function ModalDecision({ abierto, alCerrar, titulo, texto, alAprobar, alRechazar }: {
  abierto: boolean; alCerrar: () => void; titulo: string; texto: string
  alAprobar: (m: string) => Promise<boolean>; alRechazar: (m: string) => Promise<boolean>
}) {
  const [motivo, setMotivo] = useState('')
  const [c, setC] = useState('')
  const hacer = async (aprobar: boolean) => {
    setC(aprobar ? 'a' : 'r')
    const ok = aprobar ? await alAprobar(motivo) : await alRechazar(motivo)
    setC('')
    if (ok) { setMotivo(''); alCerrar() }
  }
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo={titulo} pie={<>
      <Boton variante="peligro" icono={<XCircle className="size-4" />} cargando={c === 'r'} onClick={() => hacer(false)}>Rechazar</Boton>
      <Boton variante="exito" icono={<CheckCircle2 className="size-4" />} cargando={c === 'a'} onClick={() => hacer(true)}>Aprobar</Boton>
    </>}>
      <p className="mb-3 text-sm text-slate-600">{texto}</p>
      <Campo etiqueta="Observaciones (obligatorias si rechaza)"><textarea className="entrada" rows={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} /></Campo>
    </Modal>
  )
}

export function ModalMotivo({ abierto, alCerrar, titulo, boton, alConfirmar, texto }: {
  abierto: boolean; alCerrar: () => void; titulo: string; boton: string; texto?: string; alConfirmar: (m: string) => Promise<boolean>
}) {
  const [motivo, setMotivo] = useState('')
  const [cargando, setCargando] = useState(false)
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo={titulo} pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Volver</Boton>
      <Boton variante="peligro" cargando={cargando} disabled={!motivo.trim()} onClick={async () => {
        setCargando(true)
        const ok = await alConfirmar(motivo)
        setCargando(false)
        if (ok) { setMotivo(''); alCerrar() }
      }}>{boton}</Boton>
    </>}>
      {texto && <p className="mb-3 text-sm text-slate-600">{texto}</p>}
      <Campo etiqueta="Motivo"><textarea className="entrada" rows={3} value={motivo} onChange={(e) => setMotivo(e.target.value)} autoFocus /></Campo>
    </Modal>
  )
}

function ModalReestudio({ abierto, alCerrar, req, alHecho }: { abierto: boolean; alCerrar: () => void; req: Requerimiento; alHecho: () => void }) {
  const [instrucciones, setInstrucciones] = useState('')
  const [items, setItems] = useState<number[]>([])
  const [cargando, setCargando] = useState(false)
  const enviar = async () => {
    setCargando(true)
    try {
      await api(`/requerimientos/${req.id}/estudio`, { cuerpo: { instrucciones, items_ids: items } })
      toast.success('El agente comenzó una nueva cotización')
      alHecho()
      alCerrar()
      setInstrucciones(''); setItems([])
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setCargando(false)
    }
  }
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo="Generar otra cotización" ancho="max-w-xl" pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Cancelar</Boton>
      <Boton icono={<RefreshCw className="size-4" />} cargando={cargando} onClick={enviar}>Re-cotizar</Boton>
    </>}>
      <p className="mb-3 text-sm text-slate-600">Indique al agente qué ajustar. Las líneas no marcadas conservan su estudio actual.</p>
      <Campo etiqueta="Instrucciones para el agente" ayuda='Ej: "buscar presentación por caja de 12", "solo marca Norma", "debe ser de 220V", "buscar también en ferreterías"'>
        <textarea className="entrada" rows={3} value={instrucciones} onChange={(e) => setInstrucciones(e.target.value)} />
      </Campo>
      <div className="mt-3">
        <span className="etiqueta">Líneas a re-cotizar (ninguna marcada = todas)</span>
        <div className="max-h-48 space-y-1 overflow-y-auto">
          {req.items.map((i) => (
            <label key={i.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="size-4 accent-marca-600" checked={items.includes(i.id)}
                onChange={(e) => setItems(e.target.checked ? [...items, i.id] : items.filter((x) => x !== i.id))} />
              {i.orden + 1}. {i.descripcion}
            </label>
          ))}
        </div>
      </div>
    </Modal>
  )
}

function BuscadorProveedor({ valor, alCambiar }: { valor: Proveedor | null; alCambiar: (p: Proveedor | null) => void }) {
  const [q, setQ] = useState('')
  const { data } = useQuery({
    queryKey: ['proveedores', 'buscar', q], queryFn: () => api<Proveedor[]>(`/proveedores?q=${encodeURIComponent(q)}&limite=12`),
    enabled: q.length >= 2,
  })
  if (valor) return (
    <div className="flex items-center justify-between rounded-lg border border-marca-300 bg-marca-50 px-3 py-2 text-sm">
      <span><b>{valor.nombre}</b> · NIT {valor.nit} · {valor.ciudad}</span>
      <button className="text-xs text-slate-500 hover:underline" onClick={() => alCambiar(null)}>Cambiar</button>
    </div>
  )
  return (
    <div className="relative">
      <input className="entrada" placeholder="Buscar en el listado de proveedores (nombre o NIT)…" value={q} onChange={(e) => setQ(e.target.value)} />
      {q.length >= 2 && data && (
        <ul className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {data.map((p) => (
            <li key={p.id}><button className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => { alCambiar(p); setQ('') }}>
              <b>{p.nombre}</b> <span className="text-xs text-slate-500">· {p.nit} · {p.ciudad}</span></button></li>
          ))}
          {!data.length && <li className="px-3 py-2 text-sm text-slate-500">Sin coincidencias</li>}
        </ul>
      )}
    </div>
  )
}

function ModalCotizacion({ abierto, alCerrar, req, alHecho }: { abierto: boolean; alCerrar: () => void; req: Requerimiento; alHecho: () => void }) {
  const [prov, setProv] = useState<Proveedor | null>(null)
  const [nombreLibre, setNombreLibre] = useState('')
  const [f, setF] = useState({ item_id: '', precio_unitario: '', unidades_paquete: '1', descripcion: '', vigencia: '', plazo_entrega: '', forma_pago: '', garantia: '', observaciones: '', incluye_iva: true, elegir: true })
  const [archivo, setArchivo] = useState<File | null>(null)
  const [cargando, setCargando] = useState(false)
  const guardar = async () => {
    if (!f.item_id || !f.precio_unitario) return toast.error('Elija el ítem e indique el precio')
    setCargando(true)
    try {
      const fd = new FormData()
      fd.append('item_id', f.item_id)
      if (prov) fd.append('proveedor_id', String(prov.id))
      fd.append('proveedor_nombre', nombreLibre)
      for (const k of ['precio_unitario', 'unidades_paquete', 'descripcion', 'vigencia', 'plazo_entrega', 'forma_pago', 'garantia', 'observaciones'] as const) fd.append(k, f[k])
      fd.append('incluye_iva', String(f.incluye_iva))
      if (archivo) fd.append('archivo', archivo)
      const r = await api<{ oferta_id: string }>(`/requerimientos/${req.id}/cotizaciones`, { formulario: fd })
      if (f.elegir) await api(`/requerimientos/${req.id}/items/${f.item_id}/seleccion`, { cuerpo: { oferta_id: r.oferta_id } })
      toast.success('Cotización registrada')
      alHecho()
      alCerrar()
      setProv(null); setArchivo(null); setF({ ...f, precio_unitario: '', descripcion: '', observaciones: '' })
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setCargando(false)
    }
  }
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo="Cotización formal de un proveedor" ancho="max-w-2xl" pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Cancelar</Boton>
      <Boton cargando={cargando} onClick={guardar}>Guardar cotización</Boton>
    </>}>
      <p className="mb-3 text-sm text-slate-600">Para proveedores locales o recurrentes sin tienda en línea. La cotización entra a la comparativa como opción formal.</p>
      <div className="grid gap-3 md:grid-cols-2">
        <Campo etiqueta="Ítem *" className="md:col-span-2">
          <select className="entrada" value={f.item_id} onChange={(e) => setF({ ...f, item_id: e.target.value })}>
            <option value="">Seleccione…</option>
            {req.items.filter((i) => !i.excluido).map((i) => <option key={i.id} value={i.id}>{i.orden + 1}. {i.descripcion} ({i.cantidad} {i.unidad})</option>)}
          </select>
        </Campo>
        <div className="md:col-span-2">
          <span className="etiqueta">Proveedor *</span>
          <BuscadorProveedor valor={prov} alCambiar={setProv} />
          {!prov && <input className="entrada mt-2" placeholder="…o escriba el nombre si no está en el listado" value={nombreLibre} onChange={(e) => setNombreLibre(e.target.value)} />}
        </div>
        <Campo etiqueta="Valor unitario *"><input type="number" min={0} className="entrada" value={f.precio_unitario} onChange={(e) => setF({ ...f, precio_unitario: e.target.value })} /></Campo>
        <Campo etiqueta="Unidades por presentación" ayuda="1 si el precio es por unidad"><input type="number" min={1} className="entrada" value={f.unidades_paquete} onChange={(e) => setF({ ...f, unidades_paquete: e.target.value })} /></Campo>
        <Campo etiqueta="Descripción ofrecida" className="md:col-span-2"><input className="entrada" value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} /></Campo>
        <Campo etiqueta="Vigencia"><input className="entrada" placeholder="30 días" value={f.vigencia} onChange={(e) => setF({ ...f, vigencia: e.target.value })} /></Campo>
        <Campo etiqueta="Plazo de entrega"><input className="entrada" value={f.plazo_entrega} onChange={(e) => setF({ ...f, plazo_entrega: e.target.value })} /></Campo>
        <Campo etiqueta="Forma de pago"><input className="entrada" value={f.forma_pago} onChange={(e) => setF({ ...f, forma_pago: e.target.value })} /></Campo>
        <Campo etiqueta="Garantía"><input className="entrada" value={f.garantia} onChange={(e) => setF({ ...f, garantia: e.target.value })} /></Campo>
        <Campo etiqueta="Archivo de la cotización (PDF, imagen)"><input type="file" className="entrada" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} /></Campo>
        <div className="space-y-2 pt-5 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-marca-600" checked={f.incluye_iva} onChange={(e) => setF({ ...f, incluye_iva: e.target.checked })} /> El valor incluye IVA</label>
          <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-marca-600" checked={f.elegir} onChange={(e) => setF({ ...f, elegir: e.target.checked })} /> Elegirla para este ítem</label>
        </div>
      </div>
    </Modal>
  )
}

function ModalSolicitud({ abierto, alCerrar, req }: { abierto: boolean; alCerrar: () => void; req: Requerimiento }) {
  const [prov, setProv] = useState<Proveedor | null>(null)
  const { data } = useQuery({
    queryKey: ['solicitud', req.id, prov?.id], enabled: abierto,
    queryFn: () => api<{ asunto: string; cuerpo: string; para: string }>(`/requerimientos/${req.id}/solicitud-cotizacion${prov ? `?proveedor_id=${prov.id}` : ''}`),
  })
  const mailto = data ? `mailto:${data.para}?subject=${encodeURIComponent(data.asunto)}&body=${encodeURIComponent(data.cuerpo)}` : '#'
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo="Solicitud de cotización a proveedor" ancho="max-w-2xl" pie={<>
      <Boton variante="secundario" icono={<Copy className="size-4" />} onClick={() => data && navigator.clipboard.writeText(data.cuerpo).then(() => toast.success('Texto copiado'))}>Copiar texto</Boton>
      <a href={mailto}><Boton icono={<Mail className="size-4" />} disabled={!data?.para}>Abrir en el correo</Boton></a>
    </>}>
      <p className="mb-3 text-sm text-slate-600">Paso del flujograma "enviar solicitud de cotización al proveedor". Elija un proveedor del listado para dirigirla.</p>
      <BuscadorProveedor valor={prov} alCambiar={setProv} />
      {prov && !prov.email && <Aviso tipo="alerta" className="mt-2">Este proveedor no tiene correo registrado; copie el texto y envíelo por otro medio ({prov.telefono || 'sin teléfono'}).</Aviso>}
      <pre className="mt-3 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs text-slate-700">{data?.cuerpo}</pre>
    </Modal>
  )
}

interface Cambio { item_id: number; precio_antes?: number; precio_ahora?: number; detalle: string; agotado: boolean }

function ModalOrdenes({ abierto, alCerrar, req, alHecho }: { abierto: boolean; alCerrar: () => void; req: Requerimiento; alHecho: () => void }) {
  const [forma, setForma] = useState('contado')
  const [obs, setObs] = useState('')
  const [cargando, setCargando] = useState(false)
  const [cambios, setCambios] = useState<Cambio[] | null>(null)
  const nombreItem = (id: number) => req.items.find((i) => i.id === id)?.descripcion ?? `ítem ${id}`
  const grupos = useMemo(() => {
    const g = new Map<string, number>()
    for (const i of req.items) if (!i.excluido && i.seleccion) g.set(i.seleccion.tienda, (g.get(i.seleccion.tienda) ?? 0) + (i.seleccion.costo_total ?? 0))
    return [...g.entries()]
  }, [req])

  const generar = async (confirmar: boolean) => {
    setCargando(true)
    try {
      const r = await api<{ ordenes: number[] }>(`/requerimientos/${req.id}/ordenes`, { cuerpo: { forma_pago: forma, observaciones: obs, confirmar_cambios: confirmar } })
      toast.success(`${r.ordenes.length} orden(es) de compra generada(s) y enviada(s) a aprobación`)
      setCambios(null)
      alHecho()
      alCerrar()
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === 409 && typeof e.detalle === 'object' && e.detalle && 'cambios' in e.detalle) {
        setCambios((e.detalle as { cambios: Cambio[] }).cambios)
        alHecho()
      } else toast.error((e as Error).message)
    } finally {
      setCargando(false)
    }
  }
  const hayAgotados = cambios?.some((c) => c.agotado)

  return (
    <Modal abierto={abierto} alCerrar={() => { setCambios(null); alCerrar() }} titulo="Generar órdenes de compra" ancho="max-w-xl" pie={<>
      <Boton variante="secundario" onClick={() => { setCambios(null); alCerrar() }}>Cancelar</Boton>
      {cambios ? (!hayAgotados && <Boton cargando={cargando} onClick={() => generar(true)}>Generar con precios actualizados</Boton>)
        : <Boton icono={<ShoppingCart className="size-4" />} cargando={cargando} onClick={() => generar(false)}>Verificar precios y generar</Boton>}
    </>}>
      {cambios ? (
        <div className="space-y-3">
          <Aviso tipo={hayAgotados ? 'error' : 'alerta'}>
            {hayAgotados ? 'Hay opciones agotadas en la tienda. Cierre y elija otra opción para esos ítems.'
              : 'Al re-verificar en las tiendas, algunos precios cambiaron. Las selecciones ya se actualizaron con el precio vigente.'}
          </Aviso>
          <ul className="space-y-2 text-sm">
            {cambios.map((c) => (
              <li key={c.item_id} className="rounded-lg border border-slate-200 p-2">
                <b>{nombreItem(c.item_id)}</b>
                <div className="text-xs text-slate-600">
                  {c.precio_antes != null && c.precio_ahora != null && <>{pesos(c.precio_antes)} → <b>{pesos(c.precio_ahora)}</b> · </>}{c.detalle}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            Se generará una orden por proveedor, en el formato de UPARSISTEM. Antes de crearlas, el agente vuelve a confirmar cada
            precio en la tienda; si alguno cambió, se lo mostrará antes de continuar.
          </p>
          <ul className="rounded-lg bg-slate-50 p-3 text-sm">
            {grupos.map(([t, total]) => <li key={t} className="flex justify-between"><span>{t}</span><b>{pesos(total)}</b></li>)}
          </ul>
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo etiqueta="Forma de pago">
              <select className="entrada" value={forma} onChange={(e) => setForma(e.target.value)}>
                <option value="contado">Contado</option><option value="credito">Crédito</option>
              </select>
            </Campo>
          </div>
          <Campo etiqueta="Observaciones de la orden" ayuda="Aparece en el campo Observaciones del formato (ej: ELEMENTOS PARA LABORATORIO DE ELECTRÓNICA)">
            <textarea className="entrada" rows={2} value={obs} placeholder={req.destino} onChange={(e) => setObs(e.target.value)} />
          </Campo>
        </div>
      )}
    </Modal>
  )
}
