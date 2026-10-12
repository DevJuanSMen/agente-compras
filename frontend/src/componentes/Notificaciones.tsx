import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, BellRing, CheckCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { api } from '../api'
import type { Notificacion } from '../tipos'
import { hace } from '../util'

const PUNTO: Record<string, string> = {
  exito: 'bg-emerald-500', error: 'bg-red-500', info: 'bg-sky-500',
}

/** Campana con sondeo cada 15 s. Cuando llega una notificacion nueva muestra
 *  un aviso en la app y, si el usuario lo permitio, una notificacion del
 *  navegador: asi se entera de que el estudio termino aunque este en otra pestana. */
export function Notificaciones() {
  const [abierto, setAbierto] = useState(false)
  const vistas = useRef<Set<number> | null>(null)
  const navegar = useNavigate()
  const qc = useQueryClient()
  const caja = useRef<HTMLDivElement>(null)

  const { data } = useQuery({
    queryKey: ['notificaciones'],
    queryFn: () => api<{ no_leidas: number; items: Notificacion[] }>('/notificaciones'),
    refetchInterval: 15_000,
    refetchIntervalInBackground: true,
  })

  useEffect(() => {
    if (!data) return
    const ids = new Set(data.items.map((n) => n.id))
    if (vistas.current) {
      const nuevas = data.items.filter((n) => !vistas.current!.has(n.id) && !n.leida)
      for (const n of nuevas.slice(0, 3)) {
        const metodo = n.tipo === 'error' ? toast.error : n.tipo === 'exito' ? toast.success : toast
        metodo(n.titulo, { description: n.mensaje, action: n.enlace ? { label: 'Ver', onClick: () => navegar(n.enlace) } : undefined })
        if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
          const aviso = new Notification(n.titulo, { body: n.mensaje, icon: '/logo.png', tag: `n${n.id}` })
          aviso.onclick = () => { window.focus(); if (n.enlace) navegar(n.enlace) }
        }
      }
      if (nuevas.length) qc.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'notificaciones' })
    }
    vistas.current = ids
  }, [data, navegar, qc])

  useEffect(() => {
    const cerrar = (e: MouseEvent) => caja.current && !caja.current.contains(e.target as Node) && setAbierto(false)
    document.addEventListener('mousedown', cerrar)
    return () => document.removeEventListener('mousedown', cerrar)
  }, [])

  const abrir = async (n: Notificacion) => {
    setAbierto(false)
    if (!n.leida) {
      await api(`/notificaciones/${n.id}/leer`, { metodo: 'POST' })
      qc.invalidateQueries({ queryKey: ['notificaciones'] })
    }
    if (n.enlace) navegar(n.enlace)
  }

  const leerTodas = async () => {
    await api('/notificaciones/leer-todas', { metodo: 'POST' })
    qc.invalidateQueries({ queryKey: ['notificaciones'] })
  }

  const permitir = () => Notification.requestPermission().then((p) =>
    p === 'granted' ? toast.success('Recibirá avisos del navegador cuando termine un estudio') : null)

  const sinLeer = data?.no_leidas ?? 0
  return (
    <div className="relative" ref={caja}>
      <button onClick={() => setAbierto(!abierto)} aria-label="Notificaciones"
        className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100">
        {sinLeer ? <BellRing className="size-5" /> : <Bell className="size-5" />}
        {sinLeer > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex min-w-4.5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {sinLeer > 99 ? '99+' : sinLeer}
          </span>
        )}
      </button>
      {abierto && (
        <div className="absolute right-0 z-40 mt-2 w-[min(92vw,380px)] overflow-hidden rounded-xl border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
            <span className="text-sm font-semibold">Notificaciones</span>
            {sinLeer > 0 && (
              <button onClick={leerTodas} className="flex items-center gap-1 text-xs text-marca-700 hover:underline">
                <CheckCheck className="size-3.5" /> Marcar todas
              </button>
            )}
          </div>
          {'Notification' in window && Notification.permission === 'default' && (
            <button onClick={permitir} className="w-full bg-marca-50 px-4 py-2 text-left text-xs text-marca-800 hover:bg-marca-100">
              Activar avisos del navegador para enterarse cuando termine un estudio de mercado
            </button>
          )}
          <ul className="max-h-[60vh] overflow-y-auto">
            {data?.items.length ? data.items.map((n) => (
              <li key={n.id}>
                <button onClick={() => abrir(n)} className={`flex w-full gap-3 px-4 py-3 text-left hover:bg-slate-50 ${n.leida ? 'opacity-60' : ''}`}>
                  <span className={`mt-1.5 size-2 shrink-0 rounded-full ${n.leida ? 'bg-slate-300' : PUNTO[n.tipo] ?? 'bg-sky-500'}`} />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-slate-800">{n.titulo}</span>
                    {n.mensaje && <span className="line-clamp-2 block text-xs text-slate-500">{n.mensaje}</span>}
                    <span className="block text-[11px] text-slate-400">{hace(n.creada_en)}</span>
                  </span>
                </button>
              </li>
            )) : <li className="px-4 py-8 text-center text-sm text-slate-500">Sin notificaciones</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
