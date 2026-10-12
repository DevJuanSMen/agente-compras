import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, Plus, Search } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api } from '../api'
import { useSesion } from '../auth'
import { Boton, Campo, Cargando, EncabezadoPagina, Modal, Tarjeta, Vacio } from '../componentes/ui'
import type { Proveedor } from '../tipos'

const VACIO: Omit<Proveedor, 'id' | 'nit'> = {
  nombre: '', tipo_identificacion: 'NIT', identificacion: '', dv: '', direccion: '', ciudad: 'Valledupar', telefono: '',
  email: '', sitio_web: '', rubros: [], recurrente: true, activo: true, notas: '',
}

export function Proveedores() {
  const { tiene } = useSesion()
  const qc = useQueryClient()
  const [q, setQ] = useState('')
  const [buscar, setBuscar] = useState('')
  const [inactivos, setInactivos] = useState(false)
  const [editando, setEditando] = useState<Partial<Proveedor> | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ['proveedores', buscar, inactivos],
    queryFn: () => api<Proveedor[]>(`/proveedores?q=${encodeURIComponent(buscar)}&solo_activos=${!inactivos}&limite=1000`),
  })

  return (
    <>
      <EncabezadoPagina titulo="Proveedores" subtitulo="Listado de proveedores recurrentes de UPARSISTEM (importado del Excel) y nuevos registros"
        acciones={tiene('compras') && <Boton icono={<Plus className="size-4" />} onClick={() => setEditando({ ...VACIO })}>Nuevo proveedor</Boton>} />
      <Tarjeta sinPadding>
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 p-3">
          <form className="relative min-w-56 flex-1" onSubmit={(e) => { e.preventDefault(); setBuscar(q) }}>
            <Search className="absolute left-2.5 top-2.5 size-4 text-slate-400" />
            <input className="entrada pl-8" placeholder="Buscar por nombre, NIT, correo o notas…" value={q} onChange={(e) => setQ(e.target.value)} />
          </form>
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <input type="checkbox" className="size-4 accent-marca-600" checked={inactivos} onChange={(e) => setInactivos(e.target.checked)} /> Incluir inactivos
          </label>
          <span className="text-xs text-slate-500">{data?.length ?? 0} proveedores</span>
        </div>
        {isLoading ? <Cargando /> : !data?.length ? <Vacio titulo="Sin proveedores" icono={<Building2 className="size-10" />} /> : (
          <div className="max-h-[70vh] overflow-auto">
            <table className="tabla">
              <thead className="sticky top-0"><tr><th>Nombre</th><th>Identificación</th><th>Ciudad</th><th>Contacto</th><th>Recurrente</th></tr></thead>
              <tbody>
                {data.map((p) => (
                  <tr key={p.id} className={`${tiene('compras') ? 'cursor-pointer' : ''} ${p.activo ? '' : 'opacity-50'}`} onClick={() => tiene('compras') && setEditando(p)}>
                    <td className="font-medium">{p.nombre}{p.notas && <div className="text-xs font-normal text-slate-500">{p.notas}</div>}</td>
                    <td className="whitespace-nowrap">{p.tipo_identificacion === 'NIT' ? 'NIT' : 'CC'} {p.nit}</td>
                    <td>{p.ciudad}</td>
                    <td className="text-xs">{p.telefono && <div>{p.telefono}</div>}{p.email && <div className="text-slate-500">{p.email}</div>}{p.sitio_web && <div className="text-marca-700">{p.sitio_web}</div>}</td>
                    <td>{p.recurrente ? 'Sí' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
      {editando && <ModalProveedor p={editando} alCerrar={() => setEditando(null)} alHecho={() => qc.invalidateQueries({ queryKey: ['proveedores'] })} />}
    </>
  )
}

function ModalProveedor({ p, alCerrar, alHecho }: { p: Partial<Proveedor>; alCerrar: () => void; alHecho: () => void }) {
  const [f, setF] = useState({ ...VACIO, ...p })
  const [cargando, setCargando] = useState(false)
  const campo = (k: keyof typeof VACIO, etiqueta: string, clase = '') => (
    <Campo etiqueta={etiqueta} className={clase}>
      <input className="entrada" value={String(f[k] ?? '')} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
    </Campo>
  )
  const guardar = async () => {
    setCargando(true)
    try {
      const { id: _id, nit: _nit, ...cuerpo } = f as Proveedor
      await api(p.id ? `/proveedores/${p.id}` : '/proveedores', { metodo: p.id ? 'PUT' : 'POST', cuerpo })
      toast.success('Proveedor guardado')
      alHecho(); alCerrar()
    } catch (e) { toast.error((e as Error).message) } finally { setCargando(false) }
  }
  return (
    <Modal abierto alCerrar={alCerrar} titulo={p.id ? 'Editar proveedor' : 'Nuevo proveedor'} ancho="max-w-2xl" pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Cancelar</Boton><Boton cargando={cargando} onClick={guardar}>Guardar</Boton>
    </>}>
      <div className="grid gap-3 sm:grid-cols-6">
        {campo('nombre', 'Nombre o razón social *', 'sm:col-span-6')}
        <Campo etiqueta="Tipo de identificación" className="sm:col-span-2">
          <select className="entrada" value={f.tipo_identificacion} onChange={(e) => setF({ ...f, tipo_identificacion: e.target.value })}>
            <option>NIT</option><option>Cédula de ciudadanía</option><option>Cédula de extranjería</option>
          </select>
        </Campo>
        {campo('identificacion', 'Número', 'sm:col-span-3')}
        {campo('dv', 'DV', 'sm:col-span-1')}
        {campo('direccion', 'Dirección', 'sm:col-span-4')}
        {campo('ciudad', 'Ciudad', 'sm:col-span-2')}
        {campo('telefono', 'Teléfono', 'sm:col-span-2')}
        {campo('email', 'Correo', 'sm:col-span-2')}
        {campo('sitio_web', 'Sitio web', 'sm:col-span-2')}
        {campo('notas', 'Notas (qué vende, condiciones)', 'sm:col-span-6')}
        <label className="flex items-center gap-2 text-sm sm:col-span-3"><input type="checkbox" className="size-4 accent-marca-600" checked={f.recurrente} onChange={(e) => setF({ ...f, recurrente: e.target.checked })} /> Proveedor recurrente</label>
        <label className="flex items-center gap-2 text-sm sm:col-span-3"><input type="checkbox" className="size-4 accent-marca-600" checked={f.activo} onChange={(e) => setF({ ...f, activo: e.target.checked })} /> Activo</label>
      </div>
    </Modal>
  )
}
