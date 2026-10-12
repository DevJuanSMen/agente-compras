import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  BadgeCheck, Ban, CheckCircle2, CreditCard, ExternalLink, FileText, PackageCheck, Pencil, RefreshCw, XCircle,
} from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api, ErrorApi, urlDescarga } from '../api'
import logo from '../assets/logo.png'
import { Aviso, Boton, Campo, Cargando, EncabezadoPagina, Insignia, Modal, Tarjeta } from '../componentes/ui'
import type { InformeVerificacion, Orden, Proveedor } from '../tipos'
import { fecha, hace, pesos, TEXTO_ACCION } from '../util'
import { ModalMotivo } from './DetalleRequerimiento'

const n2 = (v: number) => v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export function DetalleOrden() {
  const { id } = useParams()
  const qc = useQueryClient()
  const [modal, setModal] = useState<'' | 'rechazar' | 'anular' | 'pagar' | 'recibir' | 'editar'>('')
  const [informes, setInformes] = useState<InformeVerificacion[] | null>(null)
  const [ocupado, setOcupado] = useState('')
  const { data: o, isLoading } = useQuery({ queryKey: ['orden', id], queryFn: () => api<Orden>(`/ordenes/${id}`) })
  const { data: emp } = useQuery({
    queryKey: ['empresa'], staleTime: 600_000,
    queryFn: () => api<{ nombre: string; nit: string; direccion: string; telefono: string; ciudad: string }>('/empresa'),
  })
  if (isLoading || !o) return <Cargando />
  const a = new Set(o.acciones)

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['orden', id] })
    qc.invalidateQueries({ queryKey: ['ordenes'] })
    qc.invalidateQueries({ queryKey: ['tablero'] })
    qc.invalidateQueries({ queryKey: ['requerimiento', String(o.requerimiento_id)] })
  }

  const hacer = async (ruta: string, cuerpo?: unknown, mensaje?: string) => {
    setOcupado(ruta)
    try {
      const r = await api<{ informes?: InformeVerificacion[]; precios_cambiaron?: boolean }>(`/ordenes/${id}${ruta}`, { metodo: 'POST', cuerpo })
      if (ruta === '/reverificar') {
        setInformes(r.informes ?? [])
        toast[r.precios_cambiaron ? 'warning' : 'success'](r.precios_cambiaron ? 'Hay cambios de precio frente a la orden' : 'Precios confirmados en las tiendas')
      } else if (mensaje) toast.success(mensaje)
      refrescar()
      return true
    } catch (e) {
      if (e instanceof ErrorApi && e.estado === 409 && e.detalle && typeof e.detalle === 'object' && 'informes' in e.detalle) {
        setInformes((e.detalle as { informes: InformeVerificacion[] }).informes)
        refrescar()
      }
      toast.error((e as Error).message)
      return false
    } finally {
      setOcupado('')
    }
  }

  const verif = o.verificacion?.informes ?? []
  const listaInformes = informes ?? (verif.length ? verif : null)

  return (
    <>
      <EncabezadoPagina
        titulo={<span className="flex flex-wrap items-center gap-2">{o.numero} <Insignia estado={o.estado} texto={o.estado_texto} /></span>}
        subtitulo={<>Requerimiento <Link className="text-marca-700 hover:underline" to={`/requerimientos/${o.requerimiento_id}`}>{o.requerimiento}</Link> · elaborada por {o.creada_por} {hace(o.creada_en)}</>}
        acciones={<>
          <a href={urlDescarga(`/ordenes/${o.id}/pdf`)} target="_blank" rel="noreferrer"><Boton variante="secundario" icono={<FileText className="size-4" />}>PDF</Boton></a>
          {a.has('reverificar') && <Boton variante="secundario" icono={<RefreshCw className="size-4" />} cargando={ocupado === '/reverificar'} onClick={() => hacer('/reverificar')}>Re-verificar precios</Boton>}
          {a.has('editar') && <Boton variante="secundario" icono={<Pencil className="size-4" />} onClick={() => setModal('editar')}>Ajustar</Boton>}
          {a.has('anular') && <Boton variante="fantasma" icono={<Ban className="size-4" />} onClick={() => setModal('anular')}>Anular</Boton>}
          {a.has('rechazar') && <Boton variante="peligro" icono={<XCircle className="size-4" />} onClick={() => setModal('rechazar')}>Rechazar</Boton>}
          {a.has('aprobar') && <Boton variante="exito" icono={<CheckCircle2 className="size-4" />} cargando={ocupado === '/aprobar'}
            onClick={() => confirm(`¿Aprobar el pago de ${pesos(o.total_pagar)} a ${o.proveedor_nombre}?`) && hacer('/aprobar', undefined, 'Pago aprobado: factura generada')}>Aprobar pago</Boton>}
          {a.has('pagar') && <Boton icono={<CreditCard className="size-4" />} onClick={() => setModal('pagar')}>Registrar pago</Boton>}
          {a.has('recibir') && <Boton variante="secundario" icono={<PackageCheck className="size-4" />} onClick={() => setModal('recibir')}>Registrar recepción</Boton>}
        </>}
      />

      {o.estado === 'rechazada' && <Aviso tipo="error" className="mb-4"><b>Rechazada:</b> {o.motivo_rechazo}</Aviso>}
      {o.estado === 'anulada' && <Aviso tipo="alerta" className="mb-4"><b>Anulada:</b> {o.motivo_rechazo}</Aviso>}
      {o.estado === 'devolucion' && <Aviso tipo="error" className="mb-4"><b>Devolución en curso:</b> {o.notas_recepcion}</Aviso>}
      {!o.proveedor_nit && o.estado === 'pendiente_aprobacion' && (
        <Aviso tipo="alerta" className="mb-4">El proveedor no tiene NIT registrado en el listado. Compras debe completarlo con <b>Ajustar</b> antes de la aprobación.</Aviso>
      )}
      {o.precios_cambiaron && o.estado === 'pendiente_aprobacion' && (
        <Aviso tipo="alerta" className="mb-4">La última verificación encontró precios distintos a los de la orden. Se recomienda rechazarla para que compras la ajuste.</Aviso>
      )}

      <div className="grid gap-5 xl:grid-cols-3">
        <div className="space-y-5 xl:col-span-2">
          {/* Vista en el formato de orden de compra de UPARSISTEM */}
          <Tarjeta sinPadding>
            <div className="overflow-x-auto p-5">
              <div className="min-w-[640px]">
                <div className="flex justify-between gap-4 border border-slate-200 p-3">
                  <div className="text-center text-xs leading-snug">
                    <img src={logo} alt="" className="mx-auto h-14" />
                    <div className="font-bold">{emp?.nombre}</div><div>Nit {emp?.nit}</div>
                    <div className="mt-2">{emp?.direccion}</div><div>Tel: {emp?.telefono}</div><div>{emp?.ciudad}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold">Orden de compra</div>
                    <div className="mb-2">No. {o.numero}</div>
                    <table className="ml-auto text-xs">
                      <tbody>
                        <tr><th className="bg-slate-200 px-2 py-1 text-right">Para</th><td className="bg-slate-100 px-2 py-1 text-right">{o.proveedor_nombre}</td></tr>
                        <tr><th className="bg-slate-200 px-2 py-1 text-right">Nit</th><td className="bg-slate-100 px-2 py-1 text-right">{o.proveedor_nit || <span className="text-red-600">POR COMPLETAR</span>}</td></tr>
                        <tr><th className="bg-slate-200 px-2 py-1 text-right">Fecha</th><td className="bg-slate-100 px-2 py-1 text-right">{o.fecha}</td></tr>
                      </tbody>
                    </table>
                  </div>
                </div>
                <table className="mt-4 w-full border-collapse text-xs">
                  <thead>
                    <tr className="bg-slate-200">{['Ítem', 'Descripción', 'Cantidad', 'Vr. Unitario', 'Valor desc.', 'Impto. Cargo', 'Impto. Rete.', 'Vr. Total'].map((h) => <th key={h} className="border border-slate-300 px-2 py-1.5">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {o.lineas.map((l, n) => (
                      <tr key={l.id} className="odd:bg-white even:bg-slate-50">
                        <td className="border border-slate-200 px-2 py-1 text-center">{n + 1}</td>
                        <td className="border border-slate-200 px-2 py-1">{l.descripcion}</td>
                        <td className="border border-slate-200 px-2 py-1 text-right">{n2(l.cantidad)}</td>
                        <td className="border border-slate-200 px-2 py-1 text-right">{n2(l.vr_unitario)}</td>
                        <td className="border border-slate-200 px-2 py-1 text-right">{n2(l.descuento)}</td>
                        <td className="border border-slate-200 px-2 py-1 text-right">{l.iva_pct} %</td>
                        <td className="border border-slate-200 px-2 py-1 text-right">{String(l.rete_pct).replace('.', ',')} %</td>
                        <td className="border border-slate-200 px-2 py-1 text-right">{n2(l.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="mt-3 flex justify-between gap-4 text-xs">
                  <div className="self-center"><b>Observaciones:</b><p>{o.observaciones}</p></div>
                  <table className="min-w-60">
                    <tbody>
                      {([['Total Bruto', o.total_bruto], ['Descuentos', o.descuentos], ['Subtotal', o.subtotal],
                        ...(o.iva_total ? [['IVA', o.iva_total]] : []),
                        [`Retefuente ${String(o.retefuente_pct).replace('.', ',')}%`, o.retefuente], [`ReteICA ${o.reteica_x_mil}`, o.reteica]] as [string, number][]).map(([k, v]) => (
                        <tr key={k}><th className="px-2 py-1 text-right">{k}</th><td className="px-2 py-1 text-right">{n2(v)}</td></tr>
                      ))}
                      <tr className="bg-slate-200 font-bold"><th className="px-2 py-1.5 text-right">Total a Pagar COP</th><td className="px-2 py-1.5 text-right">{n2(o.total_pagar)}</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </Tarjeta>

          <Tarjeta titulo="Soporte de cada precio" sinPadding>
            <div className="overflow-x-auto">
              <table className="tabla">
                <thead><tr><th>#</th><th>Tienda / proveedor</th><th>Producto publicado</th><th>Verificación al generar</th></tr></thead>
                <tbody>
                  {o.lineas.map((l, n) => (
                    <tr key={l.id}>
                      <td>{n + 1}</td><td>{l.tienda}</td>
                      <td>{l.url_fuente ? <a className="inline-flex items-center gap-1 text-marca-700 hover:underline" href={l.url_fuente} target="_blank" rel="noreferrer">{l.titulo} <ExternalLink className="size-3" /></a> : l.titulo}</td>
                      <td className="text-xs">{l.verificacion?.ok ? <span className="inline-flex items-center gap-1 text-marca-700"><BadgeCheck className="size-3.5" /> {fecha(l.verificacion.momento, true)} · {l.verificacion.metodo}</span>
                        : <span className="text-amber-700">{l.verificacion?.detalle ?? 'Sin verificación'}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Tarjeta>

          {listaInformes && (
            <Tarjeta titulo={`Última verificación en tienda ${o.verificada_en ? `(${hace(o.verificada_en)})` : ''}`}>
              <ul className="space-y-1.5 text-sm">
                {listaInformes.map((inf, i) => {
                  const malo = inf.agotado || (inf.precio_orden != null && inf.precio_ahora != null && Math.abs(inf.precio_ahora - inf.precio_orden) > 1)
                  return (
                    <li key={i} className={`flex flex-wrap justify-between gap-2 rounded-md px-2.5 py-1.5 ${malo ? 'bg-amber-50 text-amber-900' : 'bg-marca-50 text-marca-900'}`}>
                      <span>Línea {inf.linea ?? i + 1}: {inf.detalle}</span>
                      {inf.precio_ahora != null && <span>Tienda: <b>{pesos(inf.precio_ahora)}</b>{inf.precio_orden != null && <> · Orden: {pesos(inf.precio_orden)}</>}</span>}
                    </li>
                  )
                })}
              </ul>
            </Tarjeta>
          )}
        </div>

        <div className="space-y-5">
          <Tarjeta titulo="Proveedor">
            <p className="font-medium">{o.proveedor_nombre}</p>
            <p className="text-sm text-slate-600">NIT {o.proveedor_nit || '—'}</p>
            {o.proveedor_contacto && <p className="mt-1 text-xs text-slate-500">{o.proveedor_contacto}</p>}
            <p className="mt-2 text-xs text-slate-500">Canal: {o.canal === 'tienda_en_linea' ? 'Tienda en línea' : 'Proveedor directo (cotización formal)'} · Pago {o.forma_pago}</p>
          </Tarjeta>
          {o.facturas.length > 0 && (
            <Tarjeta titulo="Factura">
              {o.facturas.map((f) => (
                <div key={f.id} className="flex items-center justify-between text-sm">
                  <span><b>{f.numero}</b> · <Insignia estado={f.estado} texto={f.estado === 'pagada' ? 'Pagada' : f.estado === 'anulada' ? 'Anulada' : 'Pendiente de pago'} /></span>
                  <a href={urlDescarga(`/facturas/${f.id}/pdf`)} target="_blank" rel="noreferrer" className="text-marca-700 hover:underline">PDF</a>
                </div>
              ))}
              {o.referencia_pago && <p className="mt-2 text-xs text-slate-500">Pago: {o.referencia_pago} · {fecha(o.pagada_en, true)}
                {o.soporte_pago && <> · <a className="text-marca-700 hover:underline" target="_blank" rel="noreferrer" href={urlDescarga(`/archivos/${o.soporte_pago}`)}>soporte</a></>}</p>}
            </Tarjeta>
          )}
          <Tarjeta titulo="Historial">
            <ol className="space-y-2.5">
              {o.eventos.map((e, i) => (
                <li key={i} className="text-sm">
                  <b>{e.usuario}</b> · {TEXTO_ACCION[e.accion] ?? e.accion}
                  {e.detalle && <div className="text-xs text-slate-600">{e.detalle}</div>}
                  <div className="text-[11px] text-slate-400">{fecha(e.fecha, true)}</div>
                </li>
              ))}
            </ol>
          </Tarjeta>
        </div>
      </div>

      <ModalMotivo abierto={modal === 'rechazar'} alCerrar={() => setModal('')} titulo="Rechazar orden" boton="Rechazar"
        texto="La orden vuelve a compras para que genere otra cotización que se ajuste a lo indicado."
        alConfirmar={(m) => hacer('/rechazar', { motivo: m }, 'Orden rechazada')} />
      <ModalMotivo abierto={modal === 'anular'} alCerrar={() => setModal('')} titulo="Anular orden" boton="Anular"
        alConfirmar={(m) => hacer('/anular', { motivo: m }, 'Orden anulada')} />
      <ModalPago abierto={modal === 'pagar'} alCerrar={() => setModal('')} orden={o} alHecho={refrescar} />
      <ModalRecepcion abierto={modal === 'recibir'} alCerrar={() => setModal('')} hacer={hacer} />
      <ModalEditar abierto={modal === 'editar'} alCerrar={() => setModal('')} orden={o} alHecho={refrescar} />
    </>
  )
}

function ModalPago({ abierto, alCerrar, orden, alHecho }: { abierto: boolean; alCerrar: () => void; orden: Orden; alHecho: () => void }) {
  const [ref, setRef] = useState('')
  const [archivo, setArchivo] = useState<File | null>(null)
  const [cargando, setCargando] = useState(false)
  const guardar = async () => {
    setCargando(true)
    try {
      const fd = new FormData()
      fd.append('referencia', ref)
      if (archivo) fd.append('soporte', archivo)
      await api(`/ordenes/${orden.id}/pago`, { formulario: fd })
      toast.success('Pago registrado')
      alHecho(); alCerrar()
    } catch (e) { toast.error((e as Error).message) } finally { setCargando(false) }
  }
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo={`Registrar pago · ${pesos(orden.total_pagar)}`} pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Cancelar</Boton>
      <Boton cargando={cargando} disabled={ref.trim().length < 2} onClick={guardar}>Registrar pago</Boton>
    </>}>
      <div className="space-y-3">
        <Campo etiqueta="Referencia del pago *" ayuda="Número de transferencia, comprobante de egreso o voucher">
          <input className="entrada" value={ref} onChange={(e) => setRef(e.target.value)} />
        </Campo>
        <Campo etiqueta="Soporte de pago (opcional)"><input type="file" className="entrada" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} /></Campo>
      </div>
    </Modal>
  )
}

function ModalRecepcion({ abierto, alCerrar, hacer }: { abierto: boolean; alCerrar: () => void; hacer: (r: string, c?: unknown, m?: string) => Promise<boolean> }) {
  const [cumple, setCumple] = useState(true)
  const [notas, setNotas] = useState('')
  const [cargando, setCargando] = useState(false)
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo="Recepción del pedido" pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Cancelar</Boton>
      <Boton variante={cumple ? 'exito' : 'peligro'} cargando={cargando} onClick={async () => {
        setCargando(true)
        const ok = await hacer('/recepcion', { cumple, notas }, cumple ? 'Recibido a satisfacción' : 'Devolución iniciada')
        setCargando(false)
        if (ok) alCerrar()
      }}>{cumple ? 'Confirmar recepción' : 'Iniciar devolución'}</Boton>
    </>}>
      <p className="mb-3 text-sm text-slate-600">Compare el elemento recibido con la factura y con el requerimiento.</p>
      <div className="mb-3 flex gap-2">
        <button onClick={() => setCumple(true)} className={`flex-1 rounded-lg border p-3 text-sm ${cumple ? 'border-emerald-400 bg-emerald-50' : 'border-slate-200'}`}>Cumple</button>
        <button onClick={() => setCumple(false)} className={`flex-1 rounded-lg border p-3 text-sm ${!cumple ? 'border-red-400 bg-red-50' : 'border-slate-200'}`}>No cumple</button>
      </div>
      <Campo etiqueta={cumple ? 'Notas (opcional)' : 'Qué no cumple *'}><textarea className="entrada" rows={3} value={notas} onChange={(e) => setNotas(e.target.value)} /></Campo>
    </Modal>
  )
}

function ModalEditar({ abierto, alCerrar, orden, alHecho }: { abierto: boolean; alCerrar: () => void; orden: Orden; alHecho: () => void }) {
  const [f, setF] = useState({
    proveedor_id: orden.proveedor_id as number | null, proveedor_nombre: orden.proveedor_nombre, proveedor_nit: orden.proveedor_nit,
    forma_pago: orden.forma_pago, observaciones: orden.observaciones, retefuente_pct: orden.retefuente_pct, reteica_x_mil: orden.reteica_x_mil,
  })
  const [lineas, setLineas] = useState(orden.lineas.map((l) => ({ id: l.id, descuento: l.descuento, iva_pct: l.iva_pct, rete_pct: l.rete_pct })))
  const [q, setQ] = useState('')
  const [cargando, setCargando] = useState(false)
  const { data: provs } = useQuery({
    queryKey: ['proveedores', 'buscar', q], enabled: q.length >= 2,
    queryFn: () => api<Proveedor[]>(`/proveedores?q=${encodeURIComponent(q)}&limite=10`),
  })
  const guardar = async () => {
    setCargando(true)
    try {
      await api(`/ordenes/${orden.id}`, { metodo: 'PUT', cuerpo: { ...f, lineas } })
      toast.success('Orden actualizada')
      alHecho(); alCerrar()
    } catch (e) { toast.error((e as Error).message) } finally { setCargando(false) }
  }
  return (
    <Modal abierto={abierto} alCerrar={alCerrar} titulo="Ajustar orden" ancho="max-w-3xl" pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Cancelar</Boton>
      <Boton cargando={cargando} onClick={guardar}>Guardar y recalcular</Boton>
    </>}>
      <div className="space-y-4">
        <div>
          <span className="etiqueta">Proveedor del listado</span>
          <input className="entrada" placeholder="Buscar para reemplazar (nombre o NIT)…" value={q} onChange={(e) => setQ(e.target.value)} />
          {q.length >= 2 && provs && (
            <ul className="mt-1 max-h-40 overflow-y-auto rounded-lg border border-slate-200">
              {provs.map((p) => <li key={p.id}><button className="w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50"
                onClick={() => { setF({ ...f, proveedor_id: p.id, proveedor_nombre: p.nombre, proveedor_nit: p.nit }); setQ('') }}>{p.nombre} · {p.nit}</button></li>)}
            </ul>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Campo etiqueta="Nombre / razón social"><input className="entrada" value={f.proveedor_nombre} onChange={(e) => setF({ ...f, proveedor_nombre: e.target.value, proveedor_id: null })} /></Campo>
          <Campo etiqueta="NIT"><input className="entrada" value={f.proveedor_nit} onChange={(e) => setF({ ...f, proveedor_nit: e.target.value, proveedor_id: null })} /></Campo>
          <Campo etiqueta="Forma de pago"><select className="entrada" value={f.forma_pago} onChange={(e) => setF({ ...f, forma_pago: e.target.value })}><option value="contado">Contado</option><option value="credito">Crédito</option></select></Campo>
          <div className="grid grid-cols-2 gap-3">
            <Campo etiqueta="Retefuente %"><input type="number" step="0.1" className="entrada" value={f.retefuente_pct} onChange={(e) => {
              const v = Number(e.target.value); setF({ ...f, retefuente_pct: v }); setLineas(lineas.map((l) => ({ ...l, rete_pct: v })))
            }} /></Campo>
            <Campo etiqueta="ReteICA (por mil)"><input type="number" step="0.1" className="entrada" value={f.reteica_x_mil} onChange={(e) => setF({ ...f, reteica_x_mil: Number(e.target.value) })} /></Campo>
          </div>
          <Campo etiqueta="Observaciones" className="sm:col-span-2"><textarea className="entrada" rows={2} value={f.observaciones} onChange={(e) => setF({ ...f, observaciones: e.target.value })} /></Campo>
        </div>
        <div className="overflow-x-auto">
          <table className="tabla">
            <thead><tr><th>Línea</th><th className="text-right">Vr. unitario</th><th>Descuento $</th><th>IVA %</th><th>Rete %</th></tr></thead>
            <tbody>{orden.lineas.map((l, i) => (
              <tr key={l.id}>
                <td className="max-w-64 truncate">{i + 1}. {l.descripcion}</td>
                <td className="text-right">{pesos(l.vr_unitario)}</td>
                {(['descuento', 'iva_pct', 'rete_pct'] as const).map((k) => (
                  <td key={k}><input type="number" step="any" min={0} className="entrada w-24" value={lineas[i][k]}
                    onChange={(e) => setLineas(lineas.map((x, j) => (j === i ? { ...x, [k]: Number(e.target.value) } : x)))} /></td>
                ))}
              </tr>))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-slate-500">El valor unitario no se edita: proviene del precio verificado en la tienda o de la cotización formal.</p>
        </div>
      </div>
    </Modal>
  )
}
