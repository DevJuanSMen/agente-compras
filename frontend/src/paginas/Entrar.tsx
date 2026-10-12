import { LogIn } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'
import { useSesion } from '../auth'
import { Aviso, Boton, Campo } from '../componentes/ui'

export function Entrar() {
  const { usuario, entrar } = useSesion()
  const [email, setEmail] = useState('')
  const [clave, setClave] = useState('')
  const [error, setError] = useState('')
  const [cargando, setCargando] = useState(false)
  const navegar = useNavigate()
  const desde = (useLocation().state as { desde?: string } | null)?.desde ?? '/'

  if (usuario) return <Navigate to={desde} replace />

  const enviar = async (e: FormEvent) => {
    e.preventDefault()
    setError('')
    setCargando(true)
    try {
      await entrar(email, clave)
      navegar(desde, { replace: true })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-marca-50 via-white to-slate-100 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <img src={logo} alt="UPARSISTEM" className="h-20 w-auto" />
          <h1 className="mt-4 text-lg font-semibold text-slate-800">Agente de Compras</h1>
          <p className="text-sm text-slate-500">Requerimientos, estudios de mercado y órdenes de compra</p>
        </div>
        <form onSubmit={enviar} className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <Campo etiqueta="Correo institucional">
            <input className="entrada" type="email" autoComplete="username" required value={email}
                   onChange={(e) => setEmail(e.target.value)} placeholder="usuario@uparsistem.edu.co" autoFocus />
          </Campo>
          <Campo etiqueta="Clave">
            <input className="entrada" type="password" autoComplete="current-password" required value={clave}
                   onChange={(e) => setClave(e.target.value)} />
          </Campo>
          {error && <Aviso tipo="error">{error}</Aviso>}
          <Boton type="submit" className="w-full" cargando={cargando} icono={<LogIn className="size-4" />}>Ingresar</Boton>
        </form>
        <p className="mt-4 text-center text-xs text-slate-400">¿Olvidó su clave? Pídale al administrador que la restablezca.</p>
      </div>
    </div>
  )
}
