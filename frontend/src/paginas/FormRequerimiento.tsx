import { useQuery } from '@tanstack/react-query'
import { ImagePlus, Plus, Send, Save, ShieldCheck, Trash2, X } from 'lucide-react'
import { useEffect, useState, type KeyboardEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { api } from '../api'
import { useSesion } from '../auth'
import { Aviso, Boton, Campo, Cargando, EncabezadoPagina, Tarjeta } from '../componentes/ui'
import type { Catalogos, Requerimiento } from '../tipos'

interface ItemForm {
  cantidad: number | ''
  unidad: string
  programa: string
  descripcion: string
  especificaciones: string
  marca_preferida: string
  acepta_equivalentes: boolean
  observaciones: string
  archivo?: File | null
  imagen?: string
}

const itemVacio = (): ItemForm => ({
  cantidad: 1, unidad: 'UND', programa: '', descripcion: '', especificaciones: '', marca_preferida: '',
  acepta_equivalentes: true, observaciones: '', archivo: null,
})

export function FormRequerimiento() {
  const { id } = useParams()
  const editando = !!id
  const { usuario } = useSesion()
  const navegar = useNavigate()
  const { data: cat } = useQuery({ queryKey: ['catalogos'], queryFn: () => api<Catalogos>('/catalogos'), staleTime: 300_000 })
  const { data: existente, isLoading } = useQuery({
    queryKey: ['requerimiento', id], queryFn: () => api<Requerimiento>(`/requerimientos/${id}`), enabled: editando,
  })

  const [cab, setCab] = useState({
    nombre_cargo: usuario ? `${usuario.nombre}${usuario.cargo ? ' - ' + usuario.cargo : ''}` : '',
    area: usuario?.area ?? '', destino: '', tipo: '', fecha_requerida: '', prioridad: 'normal', justificacion: '',
  })
  const [items, setItems] = useState<ItemForm[]>([itemVacio()])
  const [fuentes, setFuentes] = useState<string[]>([])
  const [sitios, setSitios] = useState<string[]>([])
  const [sitioNuevo, setSitioNuevo] = useState('')
  const [guardando, setGuardando] = useState<'' | 'borrador' | 'enviar'>('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!existente) return
    setCab({
      nombre_cargo: existente.nombre_cargo, area: existente.area, destino: existente.destino, tipo: existente.tipo,
      fecha_requerida: existente.fecha_requerida ?? '', prioridad: existente.prioridad, justificacion: existente.justificacion,
    })
    setItems(existente.items.map((i) => ({ ...i, archivo: null })))
    setFuentes(existente.fuentes)
    setSitios(existente.sitios_extra)
  }, [existente])

  if (editando && (isLoading || !existente)) return <Cargando />

  const cambiarItem = (n: number, campo: keyof ItemForm, valor: unknown) =>
    setItems((prev) => prev.map((it, i) => (i === n ? { ...it, [campo]: valor } : it)))

  const agregarSitio = () => {
    const s = sitioNuevo.trim()
    if (s && !sitios.includes(s) && sitios.length < 8) setSitios([...sitios, s])
    setSitioNuevo('')
  }
  const teclaSitio = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') { e.preventDefault(); agregarSitio() }
  }

  const guardar = async (enviar: boolean) => {
    setError('')
    const validos = items.filter((i) => i.descripcion.trim())
    if (!cab.destino.trim()) return setError('Indique el destino de la compra')
    if (!validos.length) return setError('Agregue al menos un elemento con descripción')
    if (validos.some((i) => !i.cantidad || Number(i.cantidad) <= 0)) return setError('Todas las cantidades deben ser mayores que cero')
    setGuardando(enviar ? 'enviar' : 'borrador')
    try {
      const cuerpo = {
        ...cab, fecha_requerida: cab.fecha_requerida || null, fuentes, sitios_extra: sitioNuevo.trim() ? [...sitios, sitioNuevo.trim()] : sitios,
        proveedores_sugeridos: [], enviar: false,
        items: validos.map(({ archivo: _a, imagen: _i, ...resto }) => ({ ...resto, cantidad: Number(resto.cantidad) })),
      }
      const req = await api<Requerimiento>(editando ? `/requerimientos/${id}` : '/requerimientos', {
        metodo: editando ? 'PUT' : 'POST', cuerpo,
      })
      // Las imagenes se suben una vez existe el item (necesitan su id).
      for (const [n, it] of validos.entries()) {
        if (it.archivo && req.items[n]) {
          const fd = new FormData()
          fd.append('archivo', it.archivo)
          await api(`/requerimientos/${req.id}/items/${req.items[n].id}/imagen`, { formulario: fd })
        }
      }
      if (enviar) await api(`/requerimientos/${req.id}/enviar`, { metodo: 'POST' })
      toast.success(enviar
        ? (cat?.flujo.verificacion_area ? 'Requerimiento enviado a verificación del área' : 'Requerimiento enviado: el agente comenzó el estudio de mercado')
        : 'Borrador guardado')
      navegar(`/requerimientos/${req.id}`)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setGuardando('')
    }
  }

  const verificables = cat?.fuentes.filter((f) => f.tipo !== 'web') ?? []

  return (
    <>
      <EncabezadoPagina titulo={editando ? `Editar ${existente?.consecutivo}` : 'Nuevo requerimiento'}
        subtitulo="Formato de requerimiento UPARSISTEM SAS — cualquier tipo de bien o insumo" />

      <div className="space-y-5">
        <Tarjeta titulo="1. Datos de la solicitud">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Campo etiqueta="Nombre y cargo del solicitante *">
              <input className="entrada" value={cab.nombre_cargo} onChange={(e) => setCab({ ...cab, nombre_cargo: e.target.value })} />
            </Campo>
            <Campo etiqueta="Área / sede">
              <input className="entrada" list="areas" value={cab.area} onChange={(e) => setCab({ ...cab, area: e.target.value })} />
              <datalist id="areas">{cat?.areas.map((a) => <option key={a} value={a} />)}</datalist>
            </Campo>
            <Campo etiqueta="Tipo de necesidad">
              <select className="entrada" value={cab.tipo} onChange={(e) => setCab({ ...cab, tipo: e.target.value })}>
                <option value="">Seleccione…</option>
                {cat?.tipos.map((t) => <option key={t}>{t}</option>)}
              </select>
            </Campo>
            <Campo etiqueta="Destino de la compra *" className="md:col-span-2">
              <input className="entrada" placeholder="Ej: Elementos para laboratorio de electrónica" value={cab.destino} onChange={(e) => setCab({ ...cab, destino: e.target.value })} />
            </Campo>
            <div className="grid grid-cols-2 gap-3">
              <Campo etiqueta="Fecha en que lo requiere">
                <input type="date" className="entrada" value={cab.fecha_requerida} onChange={(e) => setCab({ ...cab, fecha_requerida: e.target.value })} />
              </Campo>
              <Campo etiqueta="Prioridad">
                <select className="entrada" value={cab.prioridad} onChange={(e) => setCab({ ...cab, prioridad: e.target.value })}>
                  <option value="normal">Normal</option><option value="alta">Alta</option><option value="urgente">Urgente</option>
                </select>
              </Campo>
            </div>
            <Campo etiqueta="Justificación (opcional)" className="md:col-span-2 lg:col-span-3">
              <textarea className="entrada" rows={2} value={cab.justificacion} onChange={(e) => setCab({ ...cab, justificacion: e.target.value })} />
            </Campo>
          </div>
        </Tarjeta>

        <Tarjeta titulo="2. Elementos requeridos" acciones={
          <Boton variante="secundario" tamano="sm" icono={<Plus className="size-4" />} onClick={() => setItems([...items, itemVacio()])}>Agregar elemento</Boton>
        }>
          <p className="mb-3 text-xs text-slate-500">
            Describa cada elemento con el mayor detalle posible (medidas, capacidad, voltaje, gramaje, color). Entre más precisa la
            descripción, más preciso el estudio de mercado. La marca es opcional.
          </p>
          <datalist id="labs">{cat?.laboratorios.map((l) => <option key={l} value={l} />)}</datalist>
          <div className="space-y-3">
            {items.map((it, n) => (
              <div key={n} className="rounded-lg border border-slate-200 bg-slate-50/60 p-3">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-500">ÍTEM {n + 1}</span>
                  {items.length > 1 && (
                    <button onClick={() => setItems(items.filter((_, i) => i !== n))} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600" title="Quitar">
                      <Trash2 className="size-4" />
                    </button>
                  )}
                </div>
                <div className="grid gap-3 md:grid-cols-12">
                  <Campo etiqueta="Cantidad *" className="md:col-span-2">
                    <input type="number" min={0} step="any" className="entrada" value={it.cantidad}
                      onChange={(e) => cambiarItem(n, 'cantidad', e.target.value === '' ? '' : Number(e.target.value))} />
                  </Campo>
                  <Campo etiqueta="Unidad" className="md:col-span-2">
                    <input className="entrada" list="unidades" value={it.unidad} onChange={(e) => cambiarItem(n, 'unidad', e.target.value.toUpperCase())} />
                  </Campo>
                  <Campo etiqueta="Programa / proceso / laboratorio" className="md:col-span-8">
                    <input className="entrada" list="labs" value={it.programa} onChange={(e) => cambiarItem(n, 'programa', e.target.value)} />
                  </Campo>
                  <Campo etiqueta="Descripción del insumo / elemento *" className="md:col-span-6">
                    <input className="entrada" placeholder="Ej: Cautín tipo lápiz 40W" value={it.descripcion} onChange={(e) => cambiarItem(n, 'descripcion', e.target.value)} />
                  </Campo>
                  <Campo etiqueta="Especificaciones" className="md:col-span-6">
                    <input className="entrada" placeholder="Ej: 110V, punta fina, con base" value={it.especificaciones} onChange={(e) => cambiarItem(n, 'especificaciones', e.target.value)} />
                  </Campo>
                  <Campo etiqueta="Marca preferida (opcional)" className="md:col-span-3">
                    <input className="entrada" value={it.marca_preferida} onChange={(e) => cambiarItem(n, 'marca_preferida', e.target.value)} />
                  </Campo>
                  <label className="flex items-end gap-2 pb-2 text-sm text-slate-600 md:col-span-3">
                    <input type="checkbox" className="size-4 accent-marca-600" checked={it.acepta_equivalentes} onChange={(e) => cambiarItem(n, 'acepta_equivalentes', e.target.checked)} />
                    Acepta marcas equivalentes
                  </label>
                  <Campo etiqueta="Observaciones" className="md:col-span-4">
                    <input className="entrada" value={it.observaciones} onChange={(e) => cambiarItem(n, 'observaciones', e.target.value)} />
                  </Campo>
                  <div className="md:col-span-2">
                    <span className="etiqueta">Imagen de referencia</span>
                    <label className="flex cursor-pointer items-center gap-1.5 truncate rounded-lg border border-dashed border-slate-300 bg-white px-2 py-2 text-xs text-slate-600 hover:border-marca-400">
                      <ImagePlus className="size-4 shrink-0" />
                      <span className="truncate">{it.archivo?.name ?? (it.imagen ? 'Cambiar imagen' : 'Adjuntar')}</span>
                      <input type="file" accept="image/*" className="hidden" onChange={(e) => cambiarItem(n, 'archivo', e.target.files?.[0] ?? null)} />
                    </label>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <datalist id="unidades">{cat?.unidades.map((u) => <option key={u} value={u} />)}</datalist>
        </Tarjeta>

        <Tarjeta titulo="3. ¿Dónde cotizar?">
          <p className="mb-3 text-sm text-slate-600">
            Si no marca ninguna, el agente elige las tiendas que mejor cubren cada tipo de producto y además busca en
            internet. Las marcadas se consultan siempre.
          </p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {verificables.map((f) => (
              <label key={f.clave} className={`flex cursor-pointer items-start gap-2 rounded-lg border p-2.5 text-sm transition
                ${fuentes.includes(f.clave) ? 'border-marca-400 bg-marca-50' : 'border-slate-200 hover:border-slate-300'}`}>
                <input type="checkbox" className="mt-0.5 size-4 accent-marca-600" checked={fuentes.includes(f.clave)}
                  onChange={(e) => setFuentes(e.target.checked ? [...fuentes, f.clave] : fuentes.filter((x) => x !== f.clave))} />
                <span>
                  <span className="flex items-center gap-1 font-medium">{f.nombre}{f.verificable && <ShieldCheck className="size-3.5 text-marca-600" aria-label="Precio verificable" />}</span>
                  <span className="block text-[11px] text-slate-500">{f.rubros.slice(0, 3).map((r) => cat?.rubros[r] ?? r).join(' · ')}</span>
                </span>
              </label>
            ))}
          </div>
          <div className="mt-4">
            <span className="etiqueta">Otros almacenes o sitios web (escriba y presione Enter)</span>
            <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-slate-300 bg-white p-1.5">
              {sitios.map((s) => (
                <span key={s} className="flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs">
                  {s}<button onClick={() => setSitios(sitios.filter((x) => x !== s))}><X className="size-3" /></button>
                </span>
              ))}
              <input className="min-w-48 flex-1 px-1.5 py-1 text-sm outline-none" value={sitioNuevo} placeholder="ej: ferreteriaelpunto.com, Papelería Tauro"
                onChange={(e) => setSitioNuevo(e.target.value)} onKeyDown={teclaSitio} onBlur={agregarSitio} />
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Con dominio (ej. tienda.com) el agente detecta su plataforma y lee el precio de la propia tienda. Con solo el nombre, lo
              busca en internet. Los proveedores locales sin tienda en línea se cotizan desde compras con cotización formal.
            </p>
          </div>
        </Tarjeta>

        {error && <Aviso tipo="error">{error}</Aviso>}
        <div className="flex flex-wrap justify-end gap-2">
          <Boton variante="secundario" onClick={() => navegar(-1)}>Cancelar</Boton>
          <Boton variante="secundario" icono={<Save className="size-4" />} cargando={guardando === 'borrador'} disabled={!!guardando} onClick={() => guardar(false)}>
            Guardar borrador
          </Boton>
          <Boton icono={<Send className="size-4" />} cargando={guardando === 'enviar'} disabled={!!guardando} onClick={() => guardar(true)}>
            {cat?.flujo.verificacion_area ? 'Enviar a verificación' : 'Enviar al agente de compras'}
          </Boton>
        </div>
      </div>
    </>
  )
}
