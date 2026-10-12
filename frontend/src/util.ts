export const pesos = (v: number | null | undefined, decimales = 0) =>
  v === null || v === undefined || Number.isNaN(v)
    ? '—'
    : '$' + v.toLocaleString('es-CO', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })

export const numero = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v.toLocaleString('es-CO', { maximumFractionDigits: 2 })

export function fecha(iso: string | null | undefined, conHora = false): string {
  if (!iso) return '—'
  const d = new Date(iso.length === 10 ? iso + 'T12:00:00' : iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('es-CO', {
    day: '2-digit', month: 'short', year: 'numeric',
    ...(conHora ? { hour: '2-digit', minute: '2-digit' } : {}),
  })
}

export function hace(iso: string | null | undefined): string {
  if (!iso) return ''
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'hace un momento'
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`
  return `hace ${Math.floor(s / 86400)} d`
}

export function duracion(seg: number | null | undefined): string {
  if (!seg && seg !== 0) return '—'
  if (seg < 90) return `${Math.round(seg)} s`
  return `${Math.round(seg / 60)} min`
}

// Color de cada estado, compartido por requerimientos y ordenes.
export const COLOR_ESTADO: Record<string, string> = {
  borrador: 'bg-slate-100 text-slate-700 ring-slate-200',
  pendiente_verificacion: 'bg-amber-50 text-amber-800 ring-amber-200',
  rechazado: 'bg-red-50 text-red-700 ring-red-200',
  en_estudio: 'bg-sky-50 text-sky-800 ring-sky-200',
  estudio_listo: 'bg-violet-50 text-violet-800 ring-violet-200',
  en_aprobacion: 'bg-amber-50 text-amber-800 ring-amber-200',
  aprobado: 'bg-marca-50 text-marca-800 ring-marca-200',
  cerrado: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  cancelado: 'bg-slate-100 text-slate-500 ring-slate-200',
  pendiente_aprobacion: 'bg-amber-50 text-amber-800 ring-amber-200',
  aprobada: 'bg-marca-50 text-marca-800 ring-marca-200',
  rechazada: 'bg-red-50 text-red-700 ring-red-200',
  pagada: 'bg-sky-50 text-sky-800 ring-sky-200',
  recibida: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  devolucion: 'bg-orange-50 text-orange-800 ring-orange-200',
  anulada: 'bg-slate-100 text-slate-500 ring-slate-200',
  pendiente_pago: 'bg-amber-50 text-amber-800 ring-amber-200',
}

export const TEXTO_ACCION: Record<string, string> = {
  creado: 'Creó el requerimiento',
  editado: 'Editó el requerimiento',
  enviado: 'Envió el requerimiento',
  verificado: 'Verificó y aprobó la solicitud',
  rechazado: 'Rechazó la solicitud',
  estudio_solicitado: 'Solicitó estudio de mercado',
  estudio_listo: 'Estudio de mercado listo',
  estudio_error: 'Falló el estudio de mercado',
  opcion_seleccionada: 'Eligió una opción',
  item_excluido: 'Excluyó un ítem',
  item_incluido: 'Volvió a incluir un ítem',
  cotizacion_manual: 'Cargó cotización de proveedor',
  cotizacion_eliminada: 'Eliminó cotización',
  ordenes_generadas: 'Generó órdenes de compra',
  orden_aprobada: 'Orden aprobada',
  orden_rechazada: 'Orden rechazada',
  cancelado: 'Canceló',
  cerrado: 'Requerimiento cerrado',
  creada: 'Orden creada',
  editada: 'Orden editada',
  aprobada: 'Aprobó el pago',
  rechazada: 'Rechazó la orden',
  anulada: 'Anuló la orden',
  pagada: 'Registró el pago',
  recibida: 'Recibido a satisfacción',
  devolucion: 'Inició devolución',
  precios_reverificados: 'Re-verificó precios en tienda',
  factura_proveedor: 'Asoció factura del proveedor',
}

export const NOMBRE_ROL: Record<string, string> = {
  solicitante: 'Solicitante',
  verificador: 'Verificador',
  compras: 'Compras',
  aprobador: 'Aprobador',
  tesoreria: 'Tesorería',
  admin: 'Administrador',
}

export const TEXTO_METODO: Record<string, string> = {
  manual: 'Cotización formal',
  api_tienda: 'Catálogo de la tienda',
  marcado_estructurado: 'Ficha de producto',
  navegador: 'Navegador',
  buscador: 'Solo buscador (no verificable)',
}
