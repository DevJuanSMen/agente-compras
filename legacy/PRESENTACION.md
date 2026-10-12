# Guía para la presentación

Lo mínimo para que salga bien, en orden.

## Antes de entrar a la sala

```bash
python scripts/verificar.py          # 30 segundos, confirma que todo responde
streamlit run app.py                 # http://localhost:8501
```

**Generá los informes con anticipación.** Es la decisión más importante:

```bash
python cli.py "nevera Samsung No Frost RB30N4160 307 litros" \
  --tiendas "exito.com,alkosto.com,mercadolibre.com.co,falabella.com.co,homecenter.com.co" \
  --json demo_nevera.json
```

Una corrida tarda 3–5 minutos. Esperar eso frente a una audiencia se siente eterno, y
te deja expuesto a que DuckDuckGo limite o a que se agote la cuota diaria del modelo.
En la presentación los cargás con **"Abrir informe (.json)"** en Configuración técnica.

Tené 2 o 3 informes generados: uno de electrodoméstico, uno de herramienta y uno de la
cotización en PDF. Cubren los tres casos de uso sin correr nada en vivo.

## Usá el modelo exacto, no una descripción genérica

Esto cambia radicalmente el resultado:

| Consulta | Qué devuelve el buscador | Resultado |
|---|---|---|
| `nevera Samsung RB30N4160 307 litros` | Fichas de producto | Precios reales de varias tiendas |
| `una nevera de 300 litros` | Páginas de categoría | Tiendas sin precio |

Una página de categoría no tiene un precio único que reportar. Si vas a mostrar una
búsqueda genérica, aclará que el agente responde con el rango del mercado y no con
precios puntuales — o mejor, mostrá una con referencia exacta.

## El orden que recomiendo para mostrarlo

1. **Dónde comprarlo** — tabla de tiendas con precio y link clickeable. Es el corazón:
   abrí un link en vivo para que vean que el precio coincide con la tienda real.
2. **Veredicto** — calificaciones, precio típico de mercado y desviación.
3. **Pestaña "Qué dicen los compradores"** — citas con su fuente.
4. **Expander "Evidencia cruda"** al pie — el dossier completo. Es el argumento de
   credibilidad: cada dato del informe se puede rastrear hasta la página de donde salió.

## Si algo falla en vivo

| Síntoma | Qué hacer |
|---|---|
| Tarda mucho / no avanza | Es normal: buscar, leer páginas y esperar cupo. La bitácora muestra cada paso |
| "Cuota del día agotada" | Configuración técnica → cambiá de proveedor (`groq`, `nvidia`). Cada uno tiene cuota propia |
| Tiendas sin precio | La página se arma con JS y no publica JSON-LD. Mostrá las que sí y explicá el caso |
| El buscador no responde | DuckDuckGo limitando. Esperá un minuto, o pasá a Tavily |
| Todo se cae | Cargá un informe `.json` de respaldo. Por eso los generaste antes |

## Lo que conviene decir sobre el sistema

- **Nada inventado.** Cada precio y cada comentario lleva su URL. El campo es obligatorio
  en el esquema de datos: si el modelo no tiene el link, la fila no pasa la validación.
  No es una instrucción que el modelo pueda ignorar, es el contrato.
- **Sin scrapers frágiles.** El precio sale del marcado estructurado que las tiendas
  publican para Google. Está en el HTML servido aunque la página lo pinte con JavaScript.
- **Proveedor intercambiable.** Gemini, Groq, NVIDIA o Anthropic con una variable.
  Hoy corre en free tier; con presupuesto se cambia a Claude sin tocar código.

## Lo que conviene NO prometer

- Que funciona con cualquier tienda: las que no publican JSON-LD quedan sin precio.
- Que las opiniones aparecen siempre: dependen de que haya reseñas indexadas.
- Tiempos de respuesta rápidos en free tier.
