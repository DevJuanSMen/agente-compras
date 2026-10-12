"""Genera cotizaciones PDF de ejemplo para probar la carga de documentos.

    python scripts/generar_cotizacion_ejemplo.py

Crea dos, para cubrir los dos escenarios distintos del agente:
  - `cotizacion_oficina.pdf`  productos de consumo que se consiguen en tiendas
                              con precio publicado -> comparativa de tiendas
  - `cotizacion_maquinaria.pdf`  equipo industrial usado, sin precio de lista
                              -> tasacion contra el mercado de usados
"""
from __future__ import annotations

import pathlib

import fitz  # PyMuPDF

SALIDA = pathlib.Path(__file__).resolve().parents[1] / "ejemplos"

OFICINA = [
    ("Helvetica-Bold", 17, "SUMINISTROS TECNICOS ANDINOS S.A.S."),
    ("Helvetica", 9, "NIT 901.226.445-1  |  Av. El Dorado 68C-61, Bogota  |  ventas@sta.test"),
    ("", 0, ""),
    ("Helvetica-Bold", 13, "COTIZACION No. STA-2026-0418"),
    ("Helvetica", 10, "Fecha: 24 de septiembre de 2026        Validez: 10 dias"),
    ("Helvetica", 10, "Cliente: Uparsistem S.A.S."),
    ("", 0, ""),
    ("Helvetica-Bold", 11, "ITEM 1"),
    ("Helvetica", 10, "Portatil Lenovo ThinkPad E14 Gen 5"),
    ("Helvetica", 9, "  Procesador: AMD Ryzen 5 7530U"),
    ("Helvetica", 9, "  Memoria: 16 GB DDR4   |   Almacenamiento: 512 GB SSD NVMe"),
    ("Helvetica", 9, "  Pantalla: 14 pulgadas Full HD   |   Sistema: Windows 11 Pro"),
    ("Helvetica", 9, "  Garantia: 1 ano del fabricante"),
    ("Helvetica", 10, "  Cantidad: 5        Valor unitario: $ 3.450.000"),
    ("", 0, ""),
    ("Helvetica-Bold", 11, "ITEM 2"),
    ("Helvetica", 10, "Monitor Samsung 27 pulgadas LS27C360EALXZS"),
    ("Helvetica", 9, "  Resolucion: 1920x1080   |   Frecuencia: 75 Hz   |   Panel IPS"),
    ("Helvetica", 10, "  Cantidad: 5        Valor unitario: $ 689.000"),
    ("", 0, ""),
    ("Helvetica-Bold", 11, "ITEM 3"),
    ("Helvetica", 10, "Silla ergonomica de oficina con soporte lumbar y apoyabrazos 3D"),
    ("Helvetica", 9, "  Malla transpirable, base metalica, capacidad 120 kg"),
    ("Helvetica", 10, "  Cantidad: 5        Valor unitario: $ 890.000"),
    ("", 0, ""),
    ("Helvetica-Bold", 11, "TOTAL COTIZADO: $ 25.145.000"),
    ("", 0, ""),
    ("Helvetica-Bold", 10, "CONDICIONES COMERCIALES"),
    ("Helvetica", 9, "  - Forma de pago: 50% anticipo, 50% contra entrega"),
    ("Helvetica", 9, "  - Tiempo de entrega: 15 dias habiles"),
    ("Helvetica", 9, "  - Precios no incluyen IVA"),
    ("Helvetica", 9, "  - Envio incluido dentro de Bogota"),
    ("", 0, ""),
    ("Helvetica-Oblique", 8,
     "Documento de ejemplo generado para pruebas. Empresa y precios ficticios."),
]

MAQUINARIA = [
    ("Helvetica-Bold", 18, "MAQUINARIAS DEL NORTE S.A.S."),
    ("Helvetica", 9, "NIT 900.451.772-3  |  Calle 13 # 68-45, Bogota D.C.  |  ventas@maqnorte.test"),
    ("", 0, ""),
    ("Helvetica-Bold", 14, "COTIZACION No. MN-2026-0918"),
    ("Helvetica", 10, "Fecha: 18 de septiembre de 2026        Validez: 15 dias calendario"),
    ("Helvetica", 10, "Cliente: Constructora Uparsistem S.A.S."),
    ("", 0, ""),
    ("Helvetica-Bold", 11, "ITEM 1"),
    ("Helvetica", 10, "Excavadora hidraulica sobre orugas CATERPILLAR 320 GC"),
    ("Helvetica", 9, "  Ano de fabricacion: 2021"),
    ("Helvetica", 9, "  Horometro: 3.050 horas"),
    ("Helvetica", 9, "  Motor: Cat C4.4 ACERT, 121 HP"),
    ("Helvetica", 9, "  Peso operativo: 22.200 kg   |   Capacidad cucharon: 1,19 m3"),
    ("Helvetica", 9, "  Estado: usado, importado de Estados Unidos, tren de rodaje 70%"),
    ("Helvetica", 10, "  Cantidad: 1        Valor unitario: USD 165.000,00"),
    ("", 0, ""),
    ("Helvetica-Bold", 11, "ITEM 2"),
    ("Helvetica", 10, "Martillo hidraulico CAT H120 GC para excavadora 20-24 t"),
    ("Helvetica", 9, "  Nuevo, con kit de instalacion y dos cinceles"),
    ("Helvetica", 10, "  Cantidad: 1        Valor unitario: USD 18.500,00"),
    ("", 0, ""),
    ("Helvetica-Bold", 11, "TOTAL COTIZADO: USD 183.500,00"),
    ("", 0, ""),
    ("Helvetica-Bold", 10, "CONDICIONES COMERCIALES"),
    ("Helvetica", 9, "  - Forma de pago: 50% anticipo, 50% contra entrega"),
    ("Helvetica", 9, "  - Tiempo de entrega: 45 dias habiles desde el anticipo"),
    ("Helvetica", 9, "  - Garantia: 6 meses o 500 horas, lo que ocurra primero (solo tren motriz)"),
    ("Helvetica", 9, "  - Precios no incluyen IVA ni nacionalizacion"),
    ("Helvetica", 9, "  - Flete hasta obra en Bogota incluido"),
    ("", 0, ""),
    ("Helvetica-Oblique", 8,
     "Documento de ejemplo generado para pruebas. Empresa y precios ficticios."),
]


def escribir(lineas, destino: pathlib.Path) -> None:
    doc = fitz.open()
    pagina = doc.new_page()
    y = 58.0
    for fuente, tam, texto in lineas:
        if not texto:
            y += 10
            continue
        if y > 740:                      # no dejar que se salga de la hoja
            pagina = doc.new_page()
            y = 58.0
        pagina.insert_text((56, y), texto, fontname=fuente, fontsize=tam)
        y += tam + 6
    doc.save(str(destino))
    doc.close()
    print(f"Escrito: {destino.name}  ({destino.stat().st_size / 1024:.1f} KB)")


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    escribir(OFICINA, SALIDA / "cotizacion_oficina.pdf")
    escribir(MAQUINARIA, SALIDA / "cotizacion_maquinaria.pdf")
    # Se conserva el nombre viejo para no romper comandos ya escritos.
    escribir(MAQUINARIA, SALIDA / "cotizacion_ejemplo.pdf")


if __name__ == "__main__":
    main()
