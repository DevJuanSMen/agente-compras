// Cliente de la API. El token vive en localStorage y viaja como Bearer.
const CLAVE_TOKEN = 'compras_token'

export function obtenerToken(): string | null {
  try {
    return localStorage.getItem(CLAVE_TOKEN)
  } catch {
    return null
  }
}

export function guardarToken(token: string | null) {
  try {
    if (token) localStorage.setItem(CLAVE_TOKEN, token)
    else localStorage.removeItem(CLAVE_TOKEN)
  } catch {
    /* modo privado: la sesion dura lo que la pestana */
  }
}

export class ErrorApi extends Error {
  estado: number
  detalle: unknown
  constructor(estado: number, mensaje: string, detalle: unknown) {
    super(mensaje)
    this.estado = estado
    this.detalle = detalle
  }
}

type Opciones = { metodo?: string; cuerpo?: unknown; formulario?: FormData }

export async function api<T = unknown>(ruta: string, op: Opciones = {}): Promise<T> {
  const cabeceras: Record<string, string> = {}
  const token = obtenerToken()
  if (token) cabeceras.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (op.formulario) body = op.formulario
  else if (op.cuerpo !== undefined) {
    cabeceras['Content-Type'] = 'application/json'
    body = JSON.stringify(op.cuerpo)
  }
  const r = await fetch(`/api${ruta}`, {
    method: op.metodo ?? (body ? 'POST' : 'GET'),
    headers: cabeceras,
    body,
  })
  if (r.status === 401 && !ruta.startsWith('/auth/login')) {
    guardarToken(null)
    window.dispatchEvent(new Event('sesion-vencida'))
  }
  const tipo = r.headers.get('content-type') ?? ''
  const datos = tipo.includes('json') ? await r.json() : await r.text()
  if (!r.ok) {
    const detalle = (datos as { detail?: unknown })?.detail ?? datos
    let mensaje = 'Error inesperado'
    if (typeof detalle === 'string') mensaje = detalle
    else if (Array.isArray(detalle)) mensaje = detalle.map((d: { msg?: string; loc?: string[] }) => `${d.loc?.slice(-1)[0] ?? ''}: ${d.msg}`).join('; ')
    else if (detalle && typeof detalle === 'object' && 'mensaje' in detalle) mensaje = String((detalle as { mensaje: string }).mensaje)
    throw new ErrorApi(r.status, mensaje, detalle)
  }
  return datos as T
}

/** URL de descarga con token en la consulta (se abre en otra pestana). */
export function urlDescarga(ruta: string): string {
  const sep = ruta.includes('?') ? '&' : '?'
  return `/api${ruta}${sep}token=${encodeURIComponent(obtenerToken() ?? '')}`
}
