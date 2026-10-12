import { useQuery } from '@tanstack/react-query'
import { ShoppingCart } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Cargando, EncabezadoPagina, Insignia, Tarjeta, Vacio } from '../componentes/ui'
import type { Catalogos, OrdenResumen } from '../tipos'
import { fecha, pesos } from '../util'

export function Ordenes() {
  const [params, setParams] = useSearchParams()
  const estado = params.get('estado') ?? ''
  const navegar = useNavigate()
  const { data: cat } = useQuery({ queryKey: ['catalogos'], queryFn: () => api<Catalogos>('/catalogos'), staleTime: 300_000 })
  const { data, isLoading } = useQuery({
    queryKey: ['ordenes', estado], queryFn: () => api<OrdenResumen[]>(`/ordenes?estado=${estado}`), refetchInterval: 30_000,
  })
  const total = data?.reduce((s, o) => s + (['anulada', 'rechazada'].includes(o.estado) ? 0 : o.total_pagar), 0) ?? 0

  return (
    <>
      <EncabezadoPagina titulo="Órdenes de compra" subtitulo={data ? `${data.length} orden(es) · ${pesos(total)} vigentes` : undefined} />
      <Tarjeta sinPadding>
        <div className="flex flex-wrap gap-1.5 border-b border-slate-100 p-3">
          {[['', 'Todas'], ...Object.entries(cat?.estados_oc ?? {})].map(([k, v]) => (
            <button key={k} onClick={() => setParams(k ? { estado: k } : {}, { replace: true })}
              className={`rounded-full px-3 py-1 text-xs font-medium ${estado === k ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'}`}>{v}</button>
          ))}
        </div>
        {isLoading ? <Cargando /> : !data?.length ? <Vacio titulo="No hay órdenes" icono={<ShoppingCart className="size-10" />} /> : (
          <div className="overflow-x-auto">
            <table className="tabla">
              <thead><tr><th>Número</th><th>Proveedor</th><th>Requerimiento</th><th>Fecha</th><th>Pago</th><th>Estado</th><th className="text-right">Total a pagar</th></tr></thead>
              <tbody>
                {data.map((o) => (
                  <tr key={o.id} className="cursor-pointer" onClick={() => navegar(`/ordenes/${o.id}`)}>
                    <td className="font-medium text-marca-800">{o.numero}</td>
                    <td><div>{o.proveedor_nombre}</div><div className="text-xs text-slate-500">{o.proveedor_nit ? `NIT ${o.proveedor_nit}` : <span className="text-red-600">NIT por completar</span>}</div></td>
                    <td>{o.requerimiento}</td>
                    <td className="whitespace-nowrap">{fecha(o.fecha)}</td>
                    <td className="capitalize">{o.forma_pago}</td>
                    <td><Insignia estado={o.estado} texto={o.estado_texto} />{o.precios_cambiaron && <div className="mt-1 text-[11px] text-amber-700">Precios cambiaron</div>}</td>
                    <td className="whitespace-nowrap text-right font-semibold">{pesos(o.total_pagar)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
    </>
  )
}
