import { KeyRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { api } from '../api'
import { useSesion } from '../auth'
import { Aviso, Boton, Campo, EncabezadoPagina, Tarjeta } from '../componentes/ui'
import { NOMBRE_ROL } from '../util'

export function Cuenta({ obligatoria = false }: { obligatoria?: boolean }) {
  const { usuario, refrescar, salir } = useSesion()
  const [actual, setActual] = useState('')
  const [nueva, setNueva] = useState('')
  const [repetir, setRepetir] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)

  const cambiar = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    if (nueva !== repetir) return setError('Las claves nuevas no coinciden')
    setCargando(true)
    try {
      await api('/auth/cambiar-clave', { cuerpo: { actual, nueva } })
      toast.success('Clave actualizada')
      setActual(''); setNueva(''); setRepetir('')
      await refrescar()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setCargando(false)
    }
  }

  const correo = async (v: boolean) => {
    await api('/auth/preferencias', { metodo: 'PUT', cuerpo: { notificar_correo: v } })
    await refrescar()
    toast.success(v ? 'Recibirá avisos por correo' : 'Avisos por correo desactivados')
  }

  const formulario = (
    <form onSubmit={cambiar} className="space-y-3">
      <Campo etiqueta="Clave actual"><input className="entrada" type="password" required value={actual} onChange={(e) => setActual(e.target.value)} autoComplete="current-password" /></Campo>
      <Campo etiqueta="Clave nueva" ayuda="Mínimo 8 caracteres, combinando letras con números o símbolos">
        <input className="entrada" type="password" required value={nueva} onChange={(e) => setNueva(e.target.value)} autoComplete="new-password" />
      </Campo>
      <Campo etiqueta="Repita la clave nueva"><input className="entrada" type="password" required value={repetir} onChange={(e) => setRepetir(e.target.value)} autoComplete="new-password" /></Campo>
      {error && <Aviso tipo="error">{error}</Aviso>}
      <Boton type="submit" cargando={cargando} icono={<KeyRound className="size-4" />}>Cambiar clave</Boton>
    </form>
  )

  if (obligatoria) {
    return (
      <div className="flex min-h-full items-center justify-center bg-slate-50 p-4">
        <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-lg font-semibold">Bienvenido, {usuario?.nombre}</h1>
          <p className="mb-4 mt-1 text-sm text-slate-500">Por seguridad, cambie la clave inicial antes de continuar.</p>
          {formulario}
          <button onClick={salir} className="mt-4 text-xs text-slate-500 hover:underline">Cerrar sesión</button>
        </div>
      </div>
    )
  }

  return (
    <>
      <EncabezadoPagina titulo="Mi cuenta" subtitulo={usuario?.email} />
      <div className="grid gap-4 md:grid-cols-2">
        <Tarjeta titulo="Datos">
          <dl className="space-y-2 text-sm">
            <div><dt className="etiqueta">Nombre</dt><dd>{usuario?.nombre}</dd></div>
            <div><dt className="etiqueta">Cargo / área</dt><dd>{usuario?.cargo} · {usuario?.area}</dd></div>
            <div><dt className="etiqueta">Roles</dt><dd>{usuario?.roles.map((r) => NOMBRE_ROL[r]).join(', ')}</dd></div>
          </dl>
          <label className="mt-4 flex items-center gap-2 text-sm">
            <input type="checkbox" checked={usuario?.notificar_correo ?? false} onChange={(e) => correo(e.target.checked)} className="size-4 accent-marca-600" />
            Recibir también las notificaciones por correo
          </label>
        </Tarjeta>
        <Tarjeta titulo="Cambiar clave">{formulario}</Tarjeta>
      </div>
    </>
  )
}
