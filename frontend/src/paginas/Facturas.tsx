import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Paperclip, Receipt } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { api, urlDescarga } from '../api'
import { useSesion } from '../auth'
import { Boton, Campo, Cargando, EncabezadoPagina, Insignia, Modal, Tarjeta, Vacio } from '../componentes/ui'
import type { Factura } from '../tipos'
import { fecha, pesos } from '../util'

const TEXTO: Record<string, string> = { pendiente_pago: 'Pendiente de pago', pagada: 'Pagada', anulada: 'Anulada' }

export function Facturas() {
  const { tiene } = useSesion()
  const qc = useQueryClient()
  const [editando, setEditando] = useState<Factura | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['facturas'], queryFn: () => api<Factura[]>('/facturas') })
  const pendiente = data?.filter((f) => f.estado === 'pendiente_pago').reduce((s, f) => s + f.total_pagar, 0) ?? 0

  return (
    <>
      <EncabezadoPagina titulo="Facturas" subtitulo={`Una por cada orden aprobada · ${pesos(pendiente)} pendientes de pago`} />
      <Tarjeta sinPadding>
        {isLoading ? <Cargando /> : !data?.length ? (
          <Vacio titulo="Aún no hay facturas" icono={<Receipt className="size-10" />}>Se generan automáticamente cuando se aprueba el pago de una orden de compra.</Vacio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabla">
              <thead><tr><th>Número</th><th>Orden</th><th>Proveedor</th><th>Requerimiento</th><th>Fecha</th><th>Estado</th><th>Factura del proveedor</th><th className="text-right">Total</th><th /></tr></thead>
              <tbody>
                {data.map((f) => (
                  <tr key={f.id}>
                    <td className="font-medium">{f.numero}</td>
                    <td><Link className="text-marca-700 hover:underline" to={`/ordenes/${f.orden_id}`}>{f.orden}</Link></td>
                    <td>{f.proveedor_nombre}</td><td>{f.requerimiento}</td>
                    <td className="whitespace-nowrap">{fecha(f.fecha)}</td>
                    <td><Insignia estado={f.estado} texto={TEXTO[f.estado] ?? f.estado} /></td>
                    <td className="text-xs">
                      {f.numero_proveedor || '—'}
                      {f.archivo_proveedor && <a className="ml-1 text-marca-700 hover:underline" target="_blank" rel="noreferrer" href={urlDescarga(`/archivos/${f.archivo_proveedor}`)}>archivo</a>}
                    </td>
                    <td className="whitespace-nowrap text-right font-semibold">{pesos(f.total_pagar)}</td>
                    <td className="whitespace-nowrap text-right">
                      <a href={urlDescarga(`/facturas/${f.id}/pdf`)} target="_blank" rel="noreferrer" className="mr-2 text-sm text-marca-700 hover:underline">PDF</a>
                      {tiene('tesoreria', 'compras') && <button onClick={() => setEditando(f)} className="text-slate-500 hover:text-marca-700" title="Asociar factura del proveedor"><Paperclip className="inline size-4" /></button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
      {editando && <ModalFacturaProveedor f={editando} alCerrar={() => setEditando(null)} alHecho={() => qc.invalidateQueries({ queryKey: ['facturas'] })} />}
    </>
  )
}

function ModalFacturaProveedor({ f, alCerrar, alHecho }: { f: Factura; alCerrar: () => void; alHecho: () => void }) {
  const [numero, setNumero] = useState(f.numero_proveedor)
  const [archivo, setArchivo] = useState<File | null>(null)
  const [cargando, setCargando] = useState(false)
  const guardar = async () => {
    setCargando(true)
    try {
      const fd = new FormData()
      fd.append('numero_proveedor', numero)
      if (archivo) fd.append('archivo', archivo)
      await api(`/facturas/${f.id}`, { formulario: fd })
      toast.success('Factura del proveedor asociada')
      alHecho(); alCerrar()
    } catch (e) { toast.error((e as Error).message) } finally { setCargando(false) }
  }
  return (
    <Modal abierto alCerrar={alCerrar} titulo={`Factura del proveedor · ${f.numero}`} pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Cancelar</Boton><Boton cargando={cargando} onClick={guardar}>Guardar</Boton>
    </>}>
      <p className="mb-3 text-sm text-slate-600">Asocie la factura electrónica que emitió el proveedor (recepción de la factura, flujograma de orden de compra).</p>
      <div className="space-y-3">
        <Campo etiqueta="Número de factura del proveedor"><input className="entrada" value={numero} onChange={(e) => setNumero(e.target.value)} /></Campo>
        <Campo etiqueta="Archivo (PDF o XML convertido)"><input type="file" className="entrada" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} /></Campo>
      </div>
    </Modal>
  )
}
