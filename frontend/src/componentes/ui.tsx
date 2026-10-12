import { Loader2, X } from 'lucide-react'
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { COLOR_ESTADO } from '../util'

type Variante = 'primario' | 'secundario' | 'peligro' | 'fantasma' | 'exito'

const VARIANTES: Record<Variante, string> = {
  primario: 'bg-marca-700 text-white hover:bg-marca-800 shadow-sm',
  secundario: 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 shadow-xs',
  peligro: 'bg-red-600 text-white hover:bg-red-700 shadow-sm',
  fantasma: 'text-slate-600 hover:bg-slate-100',
  exito: 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm',
}

export function Boton({
  variante = 'primario', cargando, icono, children, className = '', tamano = 'md', ...resto
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variante?: Variante; cargando?: boolean; icono?: ReactNode; tamano?: 'sm' | 'md'
}) {
  const t = tamano === 'sm' ? 'px-2.5 py-1.5 text-xs' : 'px-3.5 py-2 text-sm'
  return (
    <button
      {...resto}
      disabled={resto.disabled || cargando}
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition
        disabled:opacity-50 disabled:cursor-not-allowed ${t} ${VARIANTES[variante]} ${className}`}
    >
      {cargando ? <Loader2 className="size-4 animate-spin" /> : icono}
      {children}
    </button>
  )
}

export function Tarjeta({ titulo, acciones, children, className = '', sinPadding }: {
  titulo?: ReactNode; acciones?: ReactNode; children: ReactNode; className?: string; sinPadding?: boolean
}) {
  return (
    <section className={`rounded-xl border border-slate-200 bg-white shadow-xs ${className}`}>
      {(titulo || acciones) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">{titulo}</h2>
          <div className="flex flex-wrap items-center gap-2">{acciones}</div>
        </header>
      )}
      <div className={sinPadding ? '' : 'p-4'}>{children}</div>
    </section>
  )
}

export function Insignia({ estado, texto }: { estado: string; texto?: string }) {
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset
      ${COLOR_ESTADO[estado] ?? 'bg-slate-100 text-slate-700 ring-slate-200'}`}>
      {texto ?? estado}
    </span>
  )
}

export function Etiqueta({ children, color = 'slate' }: { children: ReactNode; color?: 'slate' | 'verde' | 'ambar' | 'rojo' | 'azul' | 'violeta' }) {
  const c = {
    slate: 'bg-slate-100 text-slate-700', verde: 'bg-marca-100 text-marca-800', ambar: 'bg-amber-100 text-amber-800',
    rojo: 'bg-red-100 text-red-700', azul: 'bg-sky-100 text-sky-800', violeta: 'bg-violet-100 text-violet-800',
  }[color]
  return <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ${c}`}>{children}</span>
}

export function Campo({ etiqueta, children, ayuda, className = '' }: {
  etiqueta: string; children: ReactNode; ayuda?: string; className?: string
}) {
  return (
    <label className={`block ${className}`}>
      <span className="etiqueta">{etiqueta}</span>
      {children}
      {ayuda && <span className="mt-1 block text-xs text-slate-500">{ayuda}</span>}
    </label>
  )
}

export function Cargando({ texto = 'Cargando…' }: { texto?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
      <Loader2 className="size-5 animate-spin" /> {texto}
    </div>
  )
}

export function Vacio({ titulo, children, icono }: { titulo: string; children?: ReactNode; icono?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      {icono && <div className="text-slate-300">{icono}</div>}
      <p className="font-medium text-slate-700">{titulo}</p>
      {children && <div className="max-w-md text-sm text-slate-500">{children}</div>}
    </div>
  )
}

export function Modal({ abierto, alCerrar, titulo, children, pie, ancho = 'max-w-lg' }: {
  abierto: boolean; alCerrar: () => void; titulo: string; children: ReactNode; pie?: ReactNode; ancho?: string
}) {
  useEffect(() => {
    if (!abierto) return
    const f = (e: KeyboardEvent) => e.key === 'Escape' && alCerrar()
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  }, [abierto, alCerrar])
  if (!abierto) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 sm:items-center"
         onMouseDown={(e) => e.target === e.currentTarget && alCerrar()}>
      <div className={`w-full ${ancho} rounded-xl bg-white shadow-xl`}>
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h3 className="font-semibold text-slate-800">{titulo}</h3>
          <button onClick={alCerrar} className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600" aria-label="Cerrar">
            <X className="size-5" />
          </button>
        </header>
        <div className="px-5 py-4">{children}</div>
        {pie && <footer className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-5 py-3">{pie}</footer>}
      </div>
    </div>
  )
}

export function Pestanas<T extends string>({ valor, opciones, alCambiar }: {
  valor: T; opciones: { valor: T; texto: ReactNode }[]; alCambiar: (v: T) => void
}) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200">
      {opciones.map((o) => (
        <button key={o.valor} onClick={() => alCambiar(o.valor)}
          className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition
            ${valor === o.valor ? 'border-marca-600 text-marca-800' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>
          {o.texto}
        </button>
      ))}
    </div>
  )
}

export function Aviso({ tipo = 'info', children, className = '' }: {
  tipo?: 'info' | 'alerta' | 'error' | 'exito'; children: ReactNode; className?: string
}) {
  const c = {
    info: 'bg-sky-50 border-sky-200 text-sky-900', alerta: 'bg-amber-50 border-amber-200 text-amber-900',
    error: 'bg-red-50 border-red-200 text-red-800', exito: 'bg-emerald-50 border-emerald-200 text-emerald-900',
  }[tipo]
  return <div className={`rounded-lg border px-3 py-2 text-sm ${c} ${className}`}>{children}</div>
}

export function BarraProgreso({ valor }: { valor: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
      <div className="h-full rounded-full bg-marca-500 transition-all duration-700" style={{ width: `${Math.max(3, Math.min(100, valor))}%` }} />
    </div>
  )
}

export function EncabezadoPagina({ titulo, subtitulo, acciones }: { titulo: ReactNode; subtitulo?: ReactNode; acciones?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{titulo}</h1>
        {subtitulo && <p className="mt-0.5 text-sm text-slate-500">{subtitulo}</p>}
      </div>
      {acciones && <div className="flex flex-wrap gap-2">{acciones}</div>}
    </div>
  )
}
