import {
  Building2, ClipboardList, FileText, LayoutDashboard, LogOut, Menu, Receipt, Settings, ShoppingCart, Users, X,
} from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import logo from '../assets/logo.png'
import { useSesion } from '../auth'
import type { Rol } from '../tipos'
import { NOMBRE_ROL } from '../util'
import { Notificaciones } from './Notificaciones'

interface Enlace { a: string; texto: string; icono: ReactNode; roles?: Rol[] }

const ENLACES: Enlace[] = [
  { a: '/', texto: 'Tablero', icono: <LayoutDashboard className="size-4.5" /> },
  { a: '/requerimientos', texto: 'Requerimientos', icono: <ClipboardList className="size-4.5" /> },
  { a: '/ordenes', texto: 'Órdenes de compra', icono: <ShoppingCart className="size-4.5" />, roles: ['compras', 'aprobador', 'tesoreria'] },
  { a: '/facturas', texto: 'Facturas', icono: <Receipt className="size-4.5" />, roles: ['compras', 'aprobador', 'tesoreria'] },
  { a: '/proveedores', texto: 'Proveedores', icono: <Building2 className="size-4.5" />, roles: ['compras', 'aprobador', 'tesoreria'] },
  { a: '/usuarios', texto: 'Usuarios', icono: <Users className="size-4.5" />, roles: ['admin'] },
  { a: '/configuracion', texto: 'Configuración', icono: <Settings className="size-4.5" />, roles: ['admin'] },
]

export function Layout() {
  const { usuario, salir, tiene } = useSesion()
  const [menu, setMenu] = useState(false)
  const navegar = useNavigate()
  const visibles = ENLACES.filter((e) => !e.roles || tiene(...e.roles))

  const nav = (
    <nav className="flex flex-col gap-0.5 p-3">
      {visibles.map((e) => (
        <NavLink key={e.a} to={e.a} end={e.a === '/'} onClick={() => setMenu(false)}
          className={({ isActive }) => `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition
            ${isActive ? 'bg-marca-50 text-marca-800' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'}`}>
          {e.icono} {e.texto}
        </NavLink>
      ))}
    </nav>
  )

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col overflow-y-auto border-r border-slate-200 bg-white lg:flex">
        <Marca />
        {nav}
        <PieUsuario />
      </aside>

      {menu && (
        <div className="fixed inset-0 z-40 bg-slate-900/40 lg:hidden" onClick={() => setMenu(false)}>
          <aside className="flex h-full w-64 flex-col bg-white" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pr-2"><Marca /><button onClick={() => setMenu(false)} className="p-2"><X className="size-5" /></button></div>
            {nav}
            <PieUsuario />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur">
          <button className="rounded-lg p-2 hover:bg-slate-100 lg:hidden" onClick={() => setMenu(true)} aria-label="Menú"><Menu className="size-5" /></button>
          <div className="flex-1 truncate text-sm text-slate-500">
            <span className="hidden sm:inline">Agente de Compras · </span>
            <span className="font-medium text-slate-700">{usuario?.nombre}</span>
            <span className="ml-2 hidden text-xs md:inline">({usuario?.roles.map((r) => NOMBRE_ROL[r]).join(', ')})</span>
          </div>
          <Notificaciones />
          <button onClick={() => { salir(); navegar('/entrar') }} title="Cerrar sesión"
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100"><LogOut className="size-5" /></button>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

function Marca() {
  return (
    <div className="flex items-center gap-2.5 px-4 py-4">
      <img src={logo} alt="UPARSISTEM" className="h-9 w-auto" />
      <div className="leading-tight">
        <div className="text-sm font-bold text-slate-800">Compras</div>
        <div className="text-[11px] text-slate-500">UPARSISTEM · v1.0</div>
      </div>
    </div>
  )
}

function PieUsuario() {
  const { usuario } = useSesion()
  return (
    <div className="mt-auto border-t border-slate-100 p-4 text-xs text-slate-500">
      <div className="flex items-center gap-2">
        <FileText className="size-3.5" />
        <NavLink to="/cuenta" className="hover:text-marca-700 hover:underline">Mi cuenta</NavLink>
      </div>
      <div className="mt-1 truncate">{usuario?.email}</div>
    </div>
  )
}
