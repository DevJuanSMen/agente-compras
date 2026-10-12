import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, guardarToken, obtenerToken } from './api'
import type { Rol, Usuario } from './tipos'

interface Sesion {
  usuario: Usuario | null
  cargando: boolean
  entrar: (email: string, clave: string) => Promise<Usuario>
  salir: () => void
  refrescar: () => Promise<void>
  tiene: (...roles: Rol[]) => boolean
}

const Contexto = createContext<Sesion | null>(null)

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<Usuario | null>(null)
  const [cargando, setCargando] = useState(true)

  const refrescar = useCallback(async () => {
    if (!obtenerToken()) {
      setUsuario(null)
      setCargando(false)
      return
    }
    try {
      setUsuario(await api<Usuario>('/auth/yo'))
    } catch {
      setUsuario(null)
    } finally {
      setCargando(false)
    }
  }, [])

  useEffect(() => {
    refrescar()
    const alVencer = () => setUsuario(null)
    window.addEventListener('sesion-vencida', alVencer)
    return () => window.removeEventListener('sesion-vencida', alVencer)
  }, [refrescar])

  const entrar = async (email: string, clave: string) => {
    const r = await api<{ token: string; usuario: Usuario }>('/auth/login', { cuerpo: { email, clave } })
    guardarToken(r.token)
    setUsuario(r.usuario)
    return r.usuario
  }

  const salir = () => {
    guardarToken(null)
    setUsuario(null)
  }

  const tiene = (...roles: Rol[]) =>
    !!usuario && (usuario.roles.includes('admin') || roles.some((r) => usuario.roles.includes(r)))

  return (
    <Contexto.Provider value={{ usuario, cargando, entrar, salir, refrescar, tiene }}>
      {children}
    </Contexto.Provider>
  )
}

export function useSesion(): Sesion {
  const c = useContext(Contexto)
  if (!c) throw new Error('useSesion fuera de ProveedorSesion')
  return c
}
