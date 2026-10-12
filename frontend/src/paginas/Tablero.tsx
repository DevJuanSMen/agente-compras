import { useQuery } from '@tanstack/react-query'
import { Activity, ClipboardList, Loader2, PiggyBank, Plus, ShoppingCart, Timer } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useSesion } from '../auth'
import { BarraProgreso, Boton, Cargando, EncabezadoPagina, Insignia, Tarjeta, Vacio } from '../componentes/ui'
import type { OrdenResumen, RequerimientoResumen } from '../tipos'
import { duracion, hace, pesos, TEXTO_ACCION } from '../util'

interface DatosTablero {
  por_estado: Record<string, number>
  total_requerimientos: number
  tareas: { titulo: string; tipo: 'req' | 'oc'; elementos: (RequerimientoResumen | OrdenResumen)[]; total: number }[]
  comprometido_mes: number
  ordenes_mes: number
  duracion_media_estudio_s: number | null
  ahorro_estimado: number
  en_estudio: RequerimientoResumen[]
  actividad: { accion: string; detalle: string; fecha: string; usuario: string; entidad: string; entidad_id: number }[]
}

export function Tablero() {
  const { usuario, tiene } = useSesion()
  const { data, isLoading } = useQuery({
    queryKey: ['tablero'], queryFn: () => api<DatosTablero>('/tablero'), refetchInterval: 20_000,
  })
  if (isLoading || !data) return <Cargando />
  const primerNombre = usuario?.nombre.split(' ')[0]

  return (
    <>
      <EncabezadoPagina titulo={`Hola, ${primerNombre}`} subtitulo="Esto es lo que necesita su atención hoy"
        acciones={tiene('solicitante', 'compras') && (
          <Link to="/requerimientos/nuevo"><Boton icono={<Plus className="size-4" />}>Nuevo requerimiento</Boton></Link>
        )} />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Indicador icono={<ClipboardList />} titulo="Requerimientos" valor={String(data.total_requerimientos)}
          detalle={`${data.por_estado.en_estudio ?? 0} en estudio · ${data.por_estado.estudio_listo ?? 0} por revisar`} />
        <Indicador icono={<ShoppingCart />} titulo="Comprometido este mes" valor={pesos(data.comprometido_mes)}
          detalle={`${data.ordenes_mes} orden(es) aprobada(s)`} />
        <Indicador icono={<PiggyBank />} titulo="Ahorro estimado" valor={pesos(data.ahorro_estimado)}
          detalle="Recomendado vs. mediana del mercado" />
        <Indicador icono={<Timer />} titulo="Tiempo medio de estudio" valor={duracion(data.duracion_media_estudio_s)}
          detalle="Últimos 30 estudios" />
      </div>

      {data.en_estudio.length > 0 && (
        <Tarjeta titulo={<span className="flex items-center gap-2"><Loader2 className="size-4 animate-spin text-marca-600" /> El agente está cotizando</span>} className="mb-5">
          <ul className="space-y-3">
            {data.en_estudio.map((r) => (
              <li key={r.id}>
                <Link to={`/requerimientos/${r.id}`} className="block rounded-lg p-2 hover:bg-slate-50">
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="font-medium">{r.consecutivo} · {r.destino}</span>
                    <span className="text-slate-500">{Math.round(r.estudio?.progreso ?? 0)}%</span>
                  </div>
                  <BarraProgreso valor={r.estudio?.progreso ?? 0} />
                  <p className="latido mt-1 truncate text-xs text-slate-500">{r.estudio?.paso}</p>
                </Link>
              </li>
            ))}
          </ul>
        </Tarjeta>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          {data.tareas.length === 0 && (
            <Tarjeta><Vacio titulo="No tiene tareas pendientes" icono={<Activity className="size-10" />}>
              Cuando haya requerimientos, estudios u órdenes que requieran su acción aparecerán aquí.
            </Vacio></Tarjeta>
          )}
          {data.tareas.map((t) => (
            <Tarjeta key={t.titulo} titulo={`${t.titulo} (${t.total})`} sinPadding
              acciones={<Link className="text-xs text-marca-700 hover:underline" to={t.tipo === 'oc' ? '/ordenes' : '/requerimientos'}>Ver todo</Link>}>
              <ul className="divide-y divide-slate-100">
                {t.elementos.map((e) => t.tipo === 'req' ? <FilaReq key={e.id} r={e as RequerimientoResumen} /> : <FilaOc key={e.id} o={e as OrdenResumen} />)}
              </ul>
            </Tarjeta>
          ))}
        </div>
        <Tarjeta titulo="Actividad reciente">
          <ol className="space-y-3">
            {data.actividad.map((a, i) => (
              <li key={i} className="text-sm">
                <Link to={a.entidad === 'orden' ? `/ordenes/${a.entidad_id}` : `/requerimientos/${a.entidad_id}`} className="hover:underline">
                  <span className="font-medium">{a.usuario}</span> · {TEXTO_ACCION[a.accion] ?? a.accion}
                </Link>
                {a.detalle && <p className="truncate text-xs text-slate-500">{a.detalle}</p>}
                <p className="text-[11px] text-slate-400">{hace(a.fecha)}</p>
              </li>
            ))}
            {!data.actividad.length && <li className="text-sm text-slate-500">Sin actividad todavía</li>}
          </ol>
        </Tarjeta>
      </div>
    </>
  )
}

function Indicador({ icono, titulo, valor, detalle }: { icono: ReactNode; titulo: string; valor: string; detalle: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xs">
      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
        <span className="text-marca-600 [&>svg]:size-4">{icono}</span>{titulo}
      </div>
      <div className="mt-1 truncate text-xl font-semibold text-slate-900">{valor}</div>
      <div className="truncate text-xs text-slate-500">{detalle}</div>
    </div>
  )
}

function FilaReq({ r }: { r: RequerimientoResumen }) {
  return (
    <li>
      <Link to={`/requerimientos/${r.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-slate-50">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{r.consecutivo} · {r.destino}</p>
          <p className="truncate text-xs text-slate-500">{r.nombre_cargo} · {r.n_items} ítem(s) · {hace(r.creado_en)}</p>
        </div>
        <Insignia estado={r.estado} texto={r.estado_texto} />
      </Link>
    </li>
  )
}

function FilaOc({ o }: { o: OrdenResumen }) {
  return (
    <li>
      <Link to={`/ordenes/${o.id}`} className="flex items-center justify-between gap-3 px-4 py-3 hover:bg-slate-50">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{o.numero} · {o.proveedor_nombre}</p>
          <p className="truncate text-xs text-slate-500">{o.requerimiento} · {o.n_lineas} línea(s)</p>
        </div>
        <span className="text-sm font-semibold">{pesos(o.total_pagar)}</span>
      </Link>
    </li>
  )
}
