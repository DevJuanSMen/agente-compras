# Agente de Compras UPARSISTEM — v1.0

Sistema de compras multiusuario: el solicitante diligencia el **requerimiento** (formato UPARSISTEM),
el agente hace el **estudio de mercado** en segundo plano y avisa, compras revisa y genera las
**órdenes de compra** (formato UPARSISTEM), el aprobador financiero aprueba el pago y se genera la
**factura**; tesorería registra pago y recepción.

```
Solicitante ──► [Verificador de área, opcional] ──► Agente: estudio de mercado ──► aviso
     ▲                                                                              │
     │ notificaciones                              Compras: elige / re-cotiza / cotización formal
     │                                                       │  (re-verifica precios en tienda)
     └──────── Tesorería: pago y recepción ◄── Factura ◄── Aprobador: aprueba el pago de cada OC
```

## Arranque

```bash
pip install -r requirements.txt
python -m playwright install chromium      # navegador real para verificar precios
copy .env.example .env                      # poner al menos GEMINI_API_KEY
iniciar.bat                                 # compila la interfaz (1a vez) y abre http://localhost:8000
```

Equivalente manual: `cd frontend && npm install && npm run build`, luego desde la raíz
`python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000`.
Para desarrollar la interfaz con recarga en caliente: uvicorn en :8000 y `npm run dev` en `frontend/` (:5173).

**Cuentas iniciales** (clave `Uparsistem2026*`, se exige cambiarla en el primer ingreso):
`admin@`, `solicitante@`, `verificador@`, `compras@`, `aprobador@`, `tesoreria@uparsistem.edu.co`.
El administrador crea los usuarios reales (Usuarios → Nuevo) y desactiva los de prueba.

## Roles

| Rol | Hace |
|---|---|
| Solicitante | Crea requerimientos (cualquier funcionario) |
| Verificador | Aprueba la solicitud antes del estudio — paso opcional, se activa en Configuración |
| Compras | Revisa el estudio, elige opciones, pide re-cotización con instrucciones, carga cotizaciones formales de proveedores locales, genera las órdenes, ajusta proveedor/NIT/retenciones |
| Aprobador | Aprueba o rechaza el pago de cada orden (al rechazar vuelve a compras) |
| Tesorería | Registra pago (referencia + soporte), factura del proveedor y recepción / devolución |
| Admin | Usuarios, configuración. Una persona puede tener varios roles |

## Precisión de precios — cómo se evita "en la tienda vale otra cosa"

1. **El precio nunca lo escribe la IA.** Sale del catálogo o índice de búsqueda de la propia tienda,
   o del marcado `schema.org` de la ficha de producto. La IA solo entiende el pedido, decide qué
   productos corresponden y redacta el resumen; los números los calcula el código.
2. **Verificación en la tienda** de las mejores opciones y las más baratas de cada ítem, por un camino
   distinto al de la búsqueda: el **simulador de carrito** en tiendas VTEX (lo que cobraría la caja, con
   promociones y límite de unidades por pedido) o la ficha de producto que ve el cliente.
3. **Re-verificación al generar la orden** (si un precio cambió, compras lo ve y confirma; si está
   agotado o la tienda no permite la cantidad pedida, se bloquea) y **otra vez al aprobar el pago** si
   el precio tiene más de 24 h (configurable).
4. **Precio por unidad normalizado**: "Lapiceros x10" se compara por lapicero y se calcula cuántos
   paquetes comprar. Precios atípicos, stock insuficiente, precios con tarjeta propia (CMR) y vendedores
   terceros de marketplace quedan marcados.
5. Las opciones que solo tienen el precio del buscador se muestran como referencia **no elegible**.

Fuentes comprobadas: Éxito, Carulla, Olímpica, Panamericana, Easy, Jumbo, Metro, Pepe Ganga (VTEX),
Alkosto, Ktronix, Alkomprar (índice de búsqueda), Falabella, Homecenter, más búsqueda abierta en
internet. Para un sitio que escriba el usuario se autodetecta VTEX / WooCommerce / Shopify y, si no,
se lee la página (con navegador real si arma el precio con JavaScript). **MercadoLibre** bloquea el
acceso automático: sus resultados son referencia hasta configurar `ML_ACCESS_TOKEN` de su API oficial.
Los proveedores locales sin tienda en línea entran por **cotización formal** (con el texto de solicitud
de cotización listo para enviar por correo).

La recomendación es la mejor relación precio/calidad: `peso × (precio unitario mínimo / precio
unitario) + (1 − peso) × calidad`, donde calidad combina corresponder exactamente a lo pedido,
calificación con promedio bayesiano (4,8 con 3 reseñas no le gana a 4,6 con 400) y confiabilidad de
la fuente. El peso (60 % precio por defecto) se ajusta en Configuración.

## Documentos

| Documento | Formato |
|---|---|
| Requerimiento | Excel con la estructura de `REQUERIMIENTOS UPARSISTEM SAS 2026.xlsx` |
| Estudio de mercado | PDF por ítem: recomendada, rango, mediana, opciones con enlace y verificación |
| Cuadro comparativo | Excel con la estructura de `Cuadro Comparativo de Cotizaciones.xlsx` (3 cotizaciones + elegido + firmas) |
| Orden de compra | PDF idéntico a `FORMATO ORDEN DE COMPRA.pdf` + anexo de soporte de cada precio |
| Factura | PDF por cada orden aprobada (y se asocia la factura electrónica real del proveedor) |

Aritmética de la orden comprobada contra la OC-1-3621 del formato: total bruto 2.627.200,
retefuente 2,5 % = 65.680, ReteICA 10 ‰ = 26.272, total a pagar 2.535.248.

## Pruebas

```bash
python scripts/prueba_api.py          # flujo completo con los 6 roles, estudio simulado (~10 s)
python scripts/prueba_api.py --real   # igual, contra las tiendas reales (unos minutos)
python scripts/prueba_tiendas.py      # pruebas sin red del módulo de búsqueda
```

## Estructura

```
agente_compras/          cerebro (Python)
  mercado/               motor v1.0: fuentes.py (adaptadores por tienda), estudio.py (orquestador),
                         precio_pagina.py, navegador.py (Playwright), prompts.py, modelos.py
  llm.py                 cadena de modelos con respaldo (Gemini → Groq → NVIDIA)
  proveedor_*.py         clientes de cada proveedor de IA
backend/app/             API FastAPI: modelos (SQLAlchemy), flujo.py (reglas del flujograma),
                         trabajador.py (cola de estudios en BD), documentos/ (PDF y Excel), routers/
backend/datos/           base de datos SQLite y archivos subidos (no versionar; respaldar)
frontend/                React + TypeScript + Tailwind (Vite)
recursos/                formatos entregados por UPARSISTEM (se importa el listado de proveedores)
legacy/                  demo anterior (Streamlit) y sus corridas
```

## Pendiente / fuera de alcance de esta versión

- Integración Q10 (requiere acceso a su API) y Siigo.
- Confirmar con contabilidad las tarifas por defecto (retefuente 2,5 %, ReteICA 10 ‰, IVA en 0 porque el
  precio de tienda ya lo incluye) y la base mínima de retención.
- Para producción: PostgreSQL (`COMPRAS_DATABASE_URL`), SMTP para correos, HTTPS detrás de un proxy y
  respaldo diario de `backend/datos/`.
