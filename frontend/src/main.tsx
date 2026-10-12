import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Toaster } from 'sonner'
import { ProveedorSesion, useSesion } from './auth'
import { Layout } from './componentes/Layout'
import { Cargando } from './componentes/ui'
import './index.css'
import { Configuracion } from './paginas/Configuracion'
import { Cuenta } from './paginas/Cuenta'
import { DetalleOrden } from './paginas/DetalleOrden'
import { DetalleRequerimiento } from './paginas/DetalleRequerimiento'
import { Entrar } from './paginas/Entrar'
import { Facturas } from './paginas/Facturas'
import { FormRequerimiento } from './paginas/FormRequerimiento'
import { Ordenes } from './paginas/Ordenes'
import { Proveedores } from './paginas/Proveedores'
import { Requerimientos } from './paginas/Requerimientos'
import { Tablero } from './paginas/Tablero'
import { Usuarios } from './paginas/Usuarios'

const clienteConsultas = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true, staleTime: 5_000 } },
})

function Protegida({ children }: { children: ReactNode }) {
  const { usuario, cargando } = useSesion()
  const ubicacion = useLocation()
  if (cargando) return <Cargando />
  if (!usuario) return <Navigate to="/entrar" replace state={{ desde: ubicacion.pathname + ubicacion.search }} />
  if (usuario.debe_cambiar_clave) return <Cuenta obligatoria />
  return <>{children}</>
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={clienteConsultas}>
      <BrowserRouter>
        <ProveedorSesion>
          <Routes>
            <Route path="/entrar" element={<Entrar />} />
            <Route element={<Protegida><Layout /></Protegida>}>
              <Route index element={<Tablero />} />
              <Route path="requerimientos" element={<Requerimientos />} />
              <Route path="requerimientos/nuevo" element={<FormRequerimiento />} />
              <Route path="requerimientos/:id" element={<DetalleRequerimiento />} />
              <Route path="requerimientos/:id/editar" element={<FormRequerimiento />} />
              <Route path="ordenes" element={<Ordenes />} />
              <Route path="ordenes/:id" element={<DetalleOrden />} />
              <Route path="facturas" element={<Facturas />} />
              <Route path="proveedores" element={<Proveedores />} />
              <Route path="usuarios" element={<Usuarios />} />
              <Route path="configuracion" element={<Configuracion />} />
              <Route path="cuenta" element={<Cuenta />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Route>
          </Routes>
          <Toaster position="top-right" richColors closeButton />
        </ProveedorSesion>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
