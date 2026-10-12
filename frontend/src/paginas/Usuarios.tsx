import { useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, Plus } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { api } from '../api'
import { Boton, Campo, Cargando, EncabezadoPagina, Etiqueta, Modal, Tarjeta } from '../componentes/ui'
import type { Catalogos, Rol, Usuario } from '../tipos'
import { NOMBRE_ROL } from '../util'

export function Usuarios() {
  const qc = useQueryClient()
  const [editando, setEditando] = useState<Partial<Usuario> | null>(null)
  const { data, isLoading } = useQuery({ queryKey: ['usuarios'], queryFn: () => api<Usuario[]>('/usuarios') })
  const { data: cat } = useQuery({ queryKey: ['catalogos'], queryFn: () => api<Catalogos>('/catalogos'), staleTime: 300_000 })

  const restablecer = async (u: Usuario) => {
    if (!confirm(`¿Restablecer la clave de ${u.nombre}?`)) return
    const r = await api<{ clave_inicial: string }>(`/usuarios/${u.id}/restablecer-clave`, { metodo: 'POST' })
    toast.success(`Clave restablecida a "${r.clave_inicial}". Deberá cambiarla al ingresar.`, { duration: 10_000 })
  }

  return (
    <>
      <EncabezadoPagina titulo="Usuarios y roles" subtitulo="Cada persona puede tener varios roles. Los roles siguen el flujograma de compras."
        acciones={<Boton icono={<Plus className="size-4" />} onClick={() => setEditando({ roles: ['solicitante'], activo: true, notificar_correo: true })}>Nuevo usuario</Boton>} />
      {cat && (
        <div className="mb-4 grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
          {Object.entries(cat.roles).map(([k, v]) => <div key={k} className="rounded-lg border border-slate-200 bg-white px-3 py-2"><b>{NOMBRE_ROL[k]}</b>: <span className="text-slate-600">{v}</span></div>)}
        </div>
      )}
      <Tarjeta sinPadding>
        {isLoading ? <Cargando /> : (
          <div className="overflow-x-auto">
            <table className="tabla">
              <thead><tr><th>Nombre</th><th>Correo</th><th>Cargo / área</th><th>Roles</th><th>Estado</th><th /></tr></thead>
              <tbody>
                {data?.map((u) => (
                  <tr key={u.id} className={u.activo ? '' : 'opacity-50'}>
                    <td className="font-medium"><button className="hover:text-marca-700 hover:underline" onClick={() => setEditando(u)}>{u.nombre}</button></td>
                    <td>{u.email}</td><td className="text-slate-600">{u.cargo}<div className="text-xs">{u.area}</div></td>
                    <td><div className="flex flex-wrap gap-1">{u.roles.map((r) => <Etiqueta key={r} color={r === 'admin' ? 'violeta' : 'verde'}>{NOMBRE_ROL[r]}</Etiqueta>)}</div></td>
                    <td>{u.activo ? (u.debe_cambiar_clave ? <span className="text-xs text-amber-700">Pendiente primer ingreso</span> : 'Activo') : 'Inactivo'}</td>
                    <td className="text-right"><button onClick={() => restablecer(u)} title="Restablecer clave" className="text-slate-400 hover:text-marca-700"><KeyRound className="size-4" /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Tarjeta>
      {editando && <ModalUsuario u={editando} areas={cat?.areas ?? []} alCerrar={() => setEditando(null)} alHecho={() => qc.invalidateQueries({ queryKey: ['usuarios'] })} />}
    </>
  )
}

function ModalUsuario({ u, areas, alCerrar, alHecho }: { u: Partial<Usuario>; areas: string[]; alCerrar: () => void; alHecho: () => void }) {
  const [f, setF] = useState({ nombre: u.nombre ?? '', email: u.email ?? '', cargo: u.cargo ?? '', area: u.area ?? '', roles: u.roles ?? [], activo: u.activo ?? true, notificar_correo: u.notificar_correo ?? true })
  const [cargando, setCargando] = useState(false)
  const alternar = (r: Rol) => setF({ ...f, roles: f.roles.includes(r) ? f.roles.filter((x) => x !== r) : [...f.roles, r] })
  const guardar = async () => {
    setCargando(true)
    try {
      const r = await api<Usuario & { clave_inicial?: string }>(u.id ? `/usuarios/${u.id}` : '/usuarios', { metodo: u.id ? 'PUT' : 'POST', cuerpo: f })
      toast.success(r.clave_inicial ? `Usuario creado. Clave inicial: "${r.clave_inicial}"` : 'Usuario actualizado', { duration: r.clave_inicial ? 12_000 : 4_000 })
      alHecho(); alCerrar()
    } catch (e) { toast.error((e as Error).message) } finally { setCargando(false) }
  }
  return (
    <Modal abierto alCerrar={alCerrar} titulo={u.id ? 'Editar usuario' : 'Nuevo usuario'} ancho="max-w-xl" pie={<>
      <Boton variante="secundario" onClick={alCerrar}>Cancelar</Boton><Boton cargando={cargando} onClick={guardar}>Guardar</Boton>
    </>}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Campo etiqueta="Nombre completo *"><input className="entrada" value={f.nombre} onChange={(e) => setF({ ...f, nombre: e.target.value })} /></Campo>
        <Campo etiqueta="Correo institucional *"><input className="entrada" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Campo>
        <Campo etiqueta="Cargo"><input className="entrada" value={f.cargo} onChange={(e) => setF({ ...f, cargo: e.target.value })} /></Campo>
        <Campo etiqueta="Área"><input className="entrada" list="areas-u" value={f.area} onChange={(e) => setF({ ...f, area: e.target.value })} />
          <datalist id="areas-u">{areas.map((a) => <option key={a} value={a} />)}</datalist></Campo>
      </div>
      <div className="mt-4">
        <span className="etiqueta">Roles</span>
        <div className="grid gap-2 sm:grid-cols-2">
          {(Object.keys(NOMBRE_ROL) as Rol[]).map((r) => (
            <label key={r} className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${f.roles.includes(r) ? 'border-marca-400 bg-marca-50' : 'border-slate-200'}`}>
              <input type="checkbox" className="size-4 accent-marca-600" checked={f.roles.includes(r)} onChange={() => alternar(r)} /> {NOMBRE_ROL[r]}
            </label>
          ))}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-4 text-sm">
        <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-marca-600" checked={f.activo} onChange={(e) => setF({ ...f, activo: e.target.checked })} /> Activo</label>
        <label className="flex items-center gap-2"><input type="checkbox" className="size-4 accent-marca-600" checked={f.notificar_correo} onChange={(e) => setF({ ...f, notificar_correo: e.target.checked })} /> Notificar por correo</label>
      </div>
    </Modal>
  )
}
