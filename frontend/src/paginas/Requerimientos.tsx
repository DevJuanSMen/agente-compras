import { useQuery } from '@tanstack/react-query'
import { ClipboardList, Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useSesion } from '../auth'
import { BarraProgreso, Boton, Cargando, EncabezadoPagina, Insignia, Tarjeta, Vacio } from '../componentes/ui'
import type { Catalogos, RequerimientoResumen } from '../tipos'
import { fecha, pesos } from '../util'

export function Requerimientos() {
  const { tiene } = useSesion()
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const estado = params.get('estado') ?? ''
  const mios = params.get('mios') === '1'
  const navegar = useNavigate()
  const ve_todo = tiene('verificador', 'compras', 'aprobador', 'tesoreria')

  const { data: cat } = useQuery({ queryKey: ['catalogos'], queryFn: () => api<Catalogos>('/catalogos'), staleTime: 300_000 })
  const { data, isLoading } = useQuery({
    queryKey: ['requerimientos', estado, params.get('q'), mios],
    queryFn: () => api<RequerimientoResumen[]>(`/requerimientos?estado=${estado}&q=${encodeURIComponent(params.get('q') ?? '')}&mios=${mios}`),
    refetchInterval: (consulta) => (consulta.state.data?.some((r) => r.estado === 'en_estudio') ? 5_000 : 30_000),
  })

  const cambiar = (clave: string, valor: string) => {
    const p = new URLSearchParams(params)
    if (valor) p.set(clave, valor)
    else p.delete(clave)
    setParams(p, { replace: true })
  }

  return (
    <>
      <EncabezadoPagina titulo="Requerimientos" subtitulo="Solicitudes de compra en el formato de UPARSISTEM"
        acciones={tiene('solicitante', 'compras') && (
          <Link to="/requerimientos/nuevo"><Boton icono={<Plus className="size-4" />}>Nuevo requerimiento</Boton></Link>
        )} />
      <Tarjeta sinPadding>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-3">
          <form className="relative min-w-56 flex-1" onSubmit={(e) => { e.preventDefault(); cambiar('q', q) }}>
            <Search className="absolute left-2.5 top-2.5 size-4 text-slate-400" />
            <input className="entrada pl-8" placeholder="Buscar por consecutivo, destino, solicitante o área…" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <select className="entrada w-auto" value={estado} onChange={(e) => cambiar('estado', e.target.value)}>
            <option value="">Todos los estados</option>
            {cat && Object.entries(cat.estados_req).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          {ve_todo && (
            <label className="flex items-center gap-1.5 text-sm text-slate-600">
              <input type="checkbox" className="size-4 accent-marca-600" checked={mios} onChange={(e) => cambiar('mios', e.target.checked ? '1' : '')} />
              Solo los míos
            </label>
          )}
        </div>
        {isLoading ? <Cargando /> : !data?.length ? (
          <Vacio titulo="No hay requerimientos" icono={<ClipboardList className="size-10" />}>
            {tiene('solicitante') ? 'Cree el primero con el botón "Nuevo requerimiento".' : 'Aún no hay solicitudes con este filtro.'}
          </Vacio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabla">
              <thead><tr><th>Consecutivo</th><th>Destino / área</th><th>Solicitante</th><th>Ítems</th><th>Fecha</th><th>Estado</th><th className="text-right">Órdenes</th></tr></thead>
              <tbody>
                {data.map((r) => (
                  <tr key={r.id} className="cursor-pointer" onClick={() => navegar(`/requerimientos/${r.id}`)}>
                    <td className="font-medium text-marca-800">
                      {r.consecutivo}
                      {r.prioridad !== 'normal' && <span className="ml-1.5 rounded bg-red-100 px-1 text-[10px] font-semibold uppercase text-red-700">{r.prioridad}</span>}
                    </td>
                    <td><div className="max-w-72 truncate">{r.destino}</div><div className="text-xs text-slate-500">{r.area}</div></td>
                    <td className="text-slate-600">{r.solicitante}</td>
                    <td>{r.n_items}</td>
                    <td className="whitespace-nowrap text-slate-600">{fecha(r.fecha_solicitud)}</td>
                    <td className="min-w-44">
                      <Insignia estado={r.estado} texto={r.estado_texto} />
                      {r.estado === 'en_estudio' && r.estudio && (
                        <div className="mt-1.5"><BarraProgreso valor={r.estudio.progreso} /></div>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-right">{r.total_ordenes ? pesos(r.total_ordenes) : '—'}</td>
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
