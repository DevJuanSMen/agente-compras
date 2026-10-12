"""Motor de estudio de mercado (v1.0).

Diferencia de fondo con la demo: **el precio nunca lo escribe la IA**.

Cada precio sale de una fuente estructurada -- la API de catalogo de la tienda,
su indice de busqueda o el marcado `schema.org` de la pagina de producto -- y
se contrasta contra la pagina que ve el cliente antes de recomendarlo. La IA
solo hace lo que no se puede hacer con reglas: entender que se esta pidiendo,
decidir si un producto encontrado corresponde a lo pedido y redactar el
resumen. Los numeros los calcula el codigo.

    planificar (IA)  ->  buscar en fuentes (sin IA)  ->  clasificar (IA)
        ->  normalizar por unidad (codigo)  ->  verificar en la pagina (sin IA)
        ->  puntuar y recomendar (codigo)  ->  resumir (IA, con cifras dadas)
"""
from .modelos import EstudioItem, ItemSolicitud, Oferta, OpcionesEstudio  # noqa: F401
