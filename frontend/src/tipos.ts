export type Rol = 'solicitante' | 'verificador' | 'compras' | 'aprobador' | 'tesoreria' | 'admin'

export interface Usuario {
  id: number
  nombre: string
  email: string
  cargo: string
  area: string
  roles: Rol[]
  activo: boolean
  debe_cambiar_clave: boolean
  notificar_correo: boolean
}

export interface Fuente {
  clave: string
  nombre: string
  dominio: string
  tipo: string
  rubros: string[]
  verificable: boolean
}

export interface Catalogos {
  areas: string[]
  laboratorios: string[]
  tipos: string[]
  unidades: string[]
  fuentes: Fuente[]
  rubros: Record<string, string>
  estados_req: Record<string, string>
  estados_oc: Record<string, string>
  roles: Record<Rol, string>
  flujo: { verificacion_area: boolean; horas_validez_precio: number; tolerancia_precio_pct: number }
}

export interface Item {
  id: number
  orden: number
  cantidad: number
  unidad: string
  programa: string
  descripcion: string
  especificaciones: string
  marca_preferida: string
  acepta_equivalentes: boolean
  observaciones: string
  imagen: string
  seleccion: Oferta | null
  excluido: boolean
}

export interface EstudioResumen {
  estado: 'en_cola' | 'en_proceso' | 'listo' | 'error' | 'cancelado'
  progreso: number
  paso: string
  version: number
}

export interface RequerimientoResumen {
  id: number
  consecutivo: string
  estado: string
  estado_texto: string
  solicitante: string
  nombre_cargo: string
  area: string
  destino: string
  tipo: string
  prioridad: string
  fecha_solicitud: string
  fecha_requerida: string | null
  n_items: number
  creado_en: string
  estudio: EstudioResumen | null
  total_ordenes: number
}

export interface Evento {
  accion: string
  detalle: string
  fecha: string
  usuario: string
}

export interface Requerimiento extends RequerimientoResumen {
  justificacion: string
  fuentes: string[]
  sitios_extra: string[]
  proveedores_sugeridos: number[]
  motivo_rechazo: string
  solicitante_id: number
  items: Item[]
  estudios: (EstudioResumen & { id: number; instrucciones: string; creado_en: string; terminado_en: string | null; error: string })[]
  ordenes: OrdenResumen[]
  eventos: Evento[]
  acciones: string[]
}

export interface Verificacion {
  ok: boolean
  precio_pagina: number | null
  metodo: string
  momento: string
  detalle: string
}

export interface Oferta {
  id: string
  fuente: string
  tienda: string
  dominio: string
  url: string
  titulo: string
  marca: string
  vendedor: string
  imagen: string
  precio: number | null
  precio_antes: number | null
  moneda: string
  disponible: boolean | null
  stock: number | null
  calificacion: number | null
  resenas: number | null
  notas: string[]
  metodo: 'manual' | 'api_tienda' | 'marcado_estructurado' | 'navegador' | 'buscador'
  capturado_en: string
  verificacion: Verificacion | null
  relevancia: 'exacto' | 'equivalente' | 'relacionado' | 'descartado' | 'sin_clasificar'
  motivo: string
  unidades_paquete: number
  precio_unitario: number | null
  paquetes_necesarios: number | null
  costo_total: number | null
  puntaje_precio: number
  puntaje_calidad: number
  puntaje: number
}

export interface EstadoFuente {
  fuente: string
  nombre: string
  estado: 'ok' | 'sin_resultados' | 'error' | 'omitida'
  resultados: number
  detalle: string
}

export interface LineaEstudio {
  item: Item
  plan: { nombre_normalizado: string; rubro: string; consultas: string[]; atributos_clave: string[]; unidad_compra: string; notas: string } | null
  resumen: string
  justificacion: string
  alertas: string[]
  estadisticas: {
    ofertas_validas?: number
    tiendas?: number
    precio_unitario_min?: number | null
    precio_unitario_max?: number | null
    precio_unitario_mediana?: number | null
    costo_total_recomendado?: number | null
    ahorro_vs_mediana?: number | null
  }
  fuentes: EstadoFuente[]
  recomendada_id: string | null
  mas_barata_id: string | null
  mejor_calificada_id: string | null
  error: string | null
  generado_en: string | null
  duracion_s: number | null
  ofertas: Oferta[]
  cotizaciones: { id: number; proveedor_nombre: string; precio_unitario: number; archivo: string }[]
}

export interface VistaEstudio {
  estudio: {
    id: number
    version: number
    estado: EstudioResumen['estado']
    progreso: number
    paso: string
    bitacora: { t: string; m: string }[]
    error: string
    creado_en: string
    iniciado_en: string | null
    terminado_en: string | null
    instrucciones: string
  } | null
  vigente_version: number | null
  lineas: LineaEstudio[]
}

export interface OrdenResumen {
  id: number
  numero: string
  estado: string
  estado_texto: string
  proveedor_nombre: string
  proveedor_nit: string
  canal: string
  fecha: string
  total_pagar: number
  forma_pago: string
  requerimiento_id: number
  requerimiento: string
  n_lineas: number
  precios_cambiaron: boolean
  verificada_en: string | null
  creada_en: string
}

export interface LineaOrden {
  id: number
  posicion: number
  item_id: number | null
  descripcion: string
  cantidad: number
  vr_unitario: number
  descuento: number
  iva_pct: number
  rete_pct: number
  total: number
  url_fuente: string
  tienda: string
  titulo: string
  verificacion: Verificacion | null
}

export interface Factura {
  id: number
  numero: string
  orden_id: number
  orden: string
  proveedor_nombre: string
  fecha: string
  estado: string
  total_pagar: number
  numero_proveedor: string
  archivo_proveedor: string
  requerimiento: string
}

export interface InformeVerificacion {
  item_id: number
  linea?: number
  ok: boolean
  cambio: boolean
  agotado: boolean
  precio_antes: number | null
  precio_ahora: number | null
  precio_orden?: number
  detalle: string
}

export interface Orden extends OrdenResumen {
  proveedor_id: number | null
  proveedor_contacto: string
  observaciones: string
  retefuente_pct: number
  reteica_x_mil: number
  total_bruto: number
  descuentos: number
  subtotal: number
  iva_total: number
  retefuente: number
  reteica: number
  motivo_rechazo: string
  verificacion: { informes?: InformeVerificacion[]; momento?: string }
  referencia_pago: string
  soporte_pago: string
  notas_recepcion: string
  creada_por: string
  aprobada_por: string
  aprobada_en: string | null
  pagada_en: string | null
  recibida_en: string | null
  lineas: LineaOrden[]
  facturas: Factura[]
  eventos: Evento[]
  acciones: string[]
}

export interface Proveedor {
  id: number
  nombre: string
  tipo_identificacion: string
  identificacion: string
  dv: string
  nit: string
  direccion: string
  ciudad: string
  telefono: string
  email: string
  sitio_web: string
  rubros: string[]
  recurrente: boolean
  activo: boolean
  notas: string
}

export interface Notificacion {
  id: number
  titulo: string
  mensaje: string
  enlace: string
  tipo: string
  leida: boolean
  creada_en: string
}
