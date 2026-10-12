import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, Save } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { api } from '../api'
import { Aviso, Boton, Campo, Cargando, EncabezadoPagina, Tarjeta } from '../componentes/ui'
import type { Catalogos } from '../tipos'

type Config = {
  empresa: Record<string, string>
  flujo: { verificacion_area: boolean; horas_validez_precio: number; tolerancia_precio_pct: number }
  impuestos: { iva_pct: number; retefuente_pct: number; reteica_x_mil: number; base_minima_retencion: number }
  consecutivos: Record<string, string | number>
  estudio: { fuentes_por_defecto: string[]; auto_fuentes: boolean; peso_precio: number; verificar_top: number; usar_navegador: boolean }
  firmas: Record<string, string>
  areas: string[]
  laboratorios: string[]
  tipos: string[]
  unidades: string[]
}

interface Salud { version: string; trabajador_activo: boolean; en_cola: number; ia: string[]; navegador: boolean; correo: boolean }

export function Configuracion() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['configuracion'], queryFn: () => api<Config>('/configuracion') })
  const { data: salud } = useQuery({ queryKey: ['salud'], queryFn: () => api<Salud>('/salud'), refetchInterval: 15_000 })
  const { data: cat } = useQuery({ queryKey: ['catalogos'], queryFn: () => api<Catalogos>('/catalogos'), staleTime: 300_000 })
  const [c, setC] = useState<Config | null>(null)
  useEffect(() => { if (data) setC(structuredClone(data)) }, [data])
  if (isLoading || !c) return <Cargando />

  const guardar = async (clave: keyof Config) => {
    try {
      await api(`/configuracion/${clave}`, { metodo: 'PUT', cuerpo: c[clave] })
      toast.success('Configuración guardada')
      qc.invalidateQueries({ queryKey: ['configuracion'] })
      qc.invalidateQueries({ queryKey: ['catalogos'] })
    } catch (e) { toast.error((e as Error).message) }
  }
  const set = <K extends keyof Config>(clave: K, valor: Config[K]) => setC({ ...c, [clave]: valor })
  const pie = (clave: keyof Config) => <div className="mt-4 flex justify-end"><Boton tamano="sm" icono={<Save className="size-3.5" />} onClick={() => guardar(clave)}>Guardar</Boton></div>

  return (
    <>
      <EncabezadoPagina titulo="Configuración" subtitulo="Parámetros del proceso de compras" />
      {salud && (
        <Tarjeta className="mb-5" titulo={<span className="flex items-center gap-2"><Activity className="size-4" /> Estado del sistema · v{salud.version}</span>}>
          <div className="grid gap-2 text-sm sm:grid-cols-2 lg:grid-cols-5">
            <Estado ok={salud.trabajador_activo}>Agente en segundo plano {salud.en_cola ? `(${salud.en_cola} en cola)` : ''}</Estado>
            <Estado ok={salud.ia.length > 0}>IA: {salud.ia.join(', ') || 'sin clave configurada'}</Estado>
            <Estado ok={salud.navegador}>Navegador para verificar precios</Estado>
            <Estado ok={salud.correo}>Correo {salud.correo ? 'configurado' : 'no configurado (solo avisos en la app)'}</Estado>
          </div>
        </Tarjeta>
      )}
      <div className="grid gap-5 lg:grid-cols-2">
        <Tarjeta titulo="Flujo de aprobación">
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-marca-600" checked={c.flujo.verificacion_area}
              onChange={(e) => set('flujo', { ...c.flujo, verificacion_area: e.target.checked })} />
            <span><b>Exigir verificación del área</b> antes del estudio de mercado (paso "Verificación y aprobación de la solicitud" del flujograma).
              Si está apagado, el requerimiento entra directo al agente al enviarlo.</span>
          </label>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Campo etiqueta="Validez de un precio verificado (horas)" ayuda="Al aprobar el pago, si el precio es más viejo se re-verifica en la tienda">
              <input type="number" className="entrada" value={c.flujo.horas_validez_precio} onChange={(e) => set('flujo', { ...c.flujo, horas_validez_precio: Number(e.target.value) })} />
            </Campo>
            <Campo etiqueta="Tolerancia de cambio de precio (%)">
              <input type="number" step="0.1" className="entrada" value={c.flujo.tolerancia_precio_pct} onChange={(e) => set('flujo', { ...c.flujo, tolerancia_precio_pct: Number(e.target.value) })} />
            </Campo>
          </div>
          {pie('flujo')}
        </Tarjeta>

        <Tarjeta titulo="Impuestos por defecto de la orden">
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo etiqueta="Impto. cargo / IVA (%)" ayuda="Los precios de tienda ya incluyen IVA"><input type="number" step="0.1" className="entrada" value={c.impuestos.iva_pct} onChange={(e) => set('impuestos', { ...c.impuestos, iva_pct: Number(e.target.value) })} /></Campo>
            <Campo etiqueta="Retefuente (%)"><input type="number" step="0.1" className="entrada" value={c.impuestos.retefuente_pct} onChange={(e) => set('impuestos', { ...c.impuestos, retefuente_pct: Number(e.target.value) })} /></Campo>
            <Campo etiqueta="ReteICA (por mil)"><input type="number" step="0.1" className="entrada" value={c.impuestos.reteica_x_mil} onChange={(e) => set('impuestos', { ...c.impuestos, reteica_x_mil: Number(e.target.value) })} /></Campo>
            <Campo etiqueta="Base mínima para retener ($)" ayuda="0 = siempre (como en el formato entregado)"><input type="number" className="entrada" value={c.impuestos.base_minima_retencion} onChange={(e) => set('impuestos', { ...c.impuestos, base_minima_retencion: Number(e.target.value) })} /></Campo>
          </div>
          <Aviso tipo="info" className="mt-3">Confirme estas tarifas con contabilidad; compras puede ajustarlas por orden antes de enviarla a aprobación.</Aviso>
          {pie('impuestos')}
        </Tarjeta>

        <Tarjeta titulo="Agente de estudio de mercado">
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo etiqueta={`Peso del precio vs. calidad: ${Math.round(c.estudio.peso_precio * 100)}% / ${Math.round((1 - c.estudio.peso_precio) * 100)}%`}
              ayuda="Cuánto pesa el precio por unidad frente a la calidad (relevancia, calificaciones, confiabilidad)">
              <input type="range" min={0.3} max={0.9} step={0.05} className="w-full accent-marca-600" value={c.estudio.peso_precio} onChange={(e) => set('estudio', { ...c.estudio, peso_precio: Number(e.target.value) })} />
            </Campo>
            <Campo etiqueta="Precios a verificar por ítem" ayuda="Se confirman en la tienda las mejor puntuadas y las más baratas">
              <input type="number" min={2} max={15} className="entrada" value={c.estudio.verificar_top} onChange={(e) => set('estudio', { ...c.estudio, verificar_top: Number(e.target.value) })} />
            </Campo>
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-marca-600" checked={c.estudio.auto_fuentes} onChange={(e) => set('estudio', { ...c.estudio, auto_fuentes: e.target.checked })} /> Agregar automáticamente las tiendas que mejor cubren cada rubro</label>
          <label className="mt-2 flex items-center gap-2 text-sm"><input type="checkbox" className="size-4 accent-marca-600" checked={c.estudio.usar_navegador} onChange={(e) => set('estudio', { ...c.estudio, usar_navegador: e.target.checked })} /> Usar navegador real para páginas que arman el precio con JavaScript</label>
          <div className="mt-3">
            <span className="etiqueta">Tiendas que siempre se consultan</span>
            <div className="flex flex-wrap gap-1.5">
              {cat?.fuentes.filter((f) => f.tipo !== 'web').map((f) => {
                const on = c.estudio.fuentes_por_defecto.includes(f.clave)
                return <button key={f.clave} onClick={() => set('estudio', { ...c.estudio, fuentes_por_defecto: on ? c.estudio.fuentes_por_defecto.filter((x) => x !== f.clave) : [...c.estudio.fuentes_por_defecto, f.clave] })}
                  className={`rounded-full px-2.5 py-1 text-xs ${on ? 'bg-marca-600 text-white' : 'bg-slate-100 text-slate-700'}`}>{f.nombre}</button>
              })}
            </div>
          </div>
          {pie('estudio')}
        </Tarjeta>

        <Tarjeta titulo="Datos de la empresa (encabezado de documentos)">
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(c.empresa).map(([k, v]) => (
              <Campo key={k} etiqueta={k.replace('_', ' ')}><input className="entrada" value={v} onChange={(e) => set('empresa', { ...c.empresa, [k]: e.target.value })} /></Campo>
            ))}
          </div>
          {pie('empresa')}
        </Tarjeta>

        <Tarjeta titulo="Consecutivos">
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(c.consecutivos).map(([k, v]) => (
              <Campo key={k} etiqueta={k.replace(/_/g, ' ')}>
                <input className="entrada" value={v} onChange={(e) => set('consecutivos', { ...c.consecutivos, [k]: k.endsWith('siguiente') ? Number(e.target.value) : e.target.value })} />
              </Campo>
            ))}
          </div>
          {pie('consecutivos')}
        </Tarjeta>

        <Tarjeta titulo="Firmas del cuadro comparativo">
          <div className="grid gap-3">
            {Object.entries(c.firmas).map(([k, v]) => (
              <Campo key={k} etiqueta={k.replace('_', ' ')}><input className="entrada" value={v} onChange={(e) => set('firmas', { ...c.firmas, [k]: e.target.value })} /></Campo>
            ))}
          </div>
          {pie('firmas')}
        </Tarjeta>

        {(['areas', 'laboratorios', 'tipos', 'unidades'] as const).map((k) => (
          <Tarjeta key={k} titulo={{ areas: 'Áreas / sedes', laboratorios: 'Programas y laboratorios', tipos: 'Tipos de necesidad', unidades: 'Unidades' }[k]}>
            <textarea className="entrada font-mono text-xs" rows={8} value={c[k].join('\n')} onChange={(e) => set(k, e.target.value.split('\n'))} />
            <p className="mt-1 text-xs text-slate-500">Uno por línea.</p>
            <div className="mt-4 flex justify-end"><Boton tamano="sm" icono={<Save className="size-3.5" />} onClick={async () => {
              const limpio = c[k].map((x) => x.trim()).filter(Boolean)
              setC({ ...c, [k]: limpio })
              try { await api(`/configuracion/${k}`, { metodo: 'PUT', cuerpo: limpio }); toast.success('Guardado'); qc.invalidateQueries({ queryKey: ['catalogos'] }) }
              catch (e) { toast.error((e as Error).message) }
            }}>Guardar</Boton></div>
          </Tarjeta>
        ))}
      </div>
    </>
  )
}

function Estado({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2">
      <span className={`size-2.5 shrink-0 rounded-full ${ok ? 'bg-emerald-500' : 'bg-amber-500'}`} />{children}
    </div>
  )
}
