"""Demo por consola, util para probar el pipeline sin levantar la UI.

    python cli.py "quiero comprar una excavadora CAT 320 GC, me la ofrecen en USD 165000"
    python cli.py --pdf cotizacion.pdf --items 1
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# La consola de Windows usa cp1252 por defecto: forzamos UTF-8 para los acentos.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agente_compras import config
from agente_compras.pipeline import analizar


def _dominios(texto: str, pais: str) -> list[str]:
    """Dominios donde buscar: los que pase el usuario, o los sugeridos del pais."""
    from agente_compras import tiendas

    if texto.strip():
        return [tiendas.dominio_de(t) for t in texto.split(",") if t.strip()]
    return [t.dominio for t in tiendas.por_defecto(pais)][: config.MAX_TIENDAS]


def main() -> int:
    ap = argparse.ArgumentParser(description="Agente de compras")
    ap.add_argument("texto", nargs="?", help="Descripcion libre de lo que se quiere comprar")
    ap.add_argument("--pdf", type=pathlib.Path, help="Cotizacion en PDF")
    ap.add_argument("--pais", default=config.PAIS_DEFAULT)
    ap.add_argument("--moneda", default=config.MONEDA_DEFAULT)
    ap.add_argument("--items", type=int, default=1, help="Cuantos items analizar")
    ap.add_argument("--marcas", default="", help="Marcas rivales separadas por coma")
    ap.add_argument("--tiendas", default="",
                    help="Dominios donde buscar, separados por coma. "
                         "Vacio = las sugeridas del pais")
    ap.add_argument("--proveedor", default=None, help="gemini | groq | nvidia | anthropic")
    ap.add_argument("--json", type=pathlib.Path, help="Guardar el informe en este archivo")
    ap.add_argument("--pdf-salida", type=pathlib.Path, dest="pdf_salida",
                    help="Guardar el informe como PDF, con los enlaces clicables")
    ap.add_argument("--dossier", type=pathlib.Path,
                    help="Guardar la evidencia cruda que alimento el analisis")
    args = ap.parse_args()

    if not args.texto and not args.pdf:
        ap.error("Pasa un texto o --pdf")
    if args.proveedor:
        config.PROVEEDOR = args.proveedor.lower()
    if not config.hay_credenciales():
        print(f"Falta {config.nombre_credencial()} en el entorno o en .env "
              f"(proveedor: {config.PROVEEDOR})", file=sys.stderr)
        return 1

    informe = analizar(
        texto=args.texto,
        pdf_bytes=args.pdf.read_bytes() if args.pdf else None,
        nombre_pdf=args.pdf.name if args.pdf else "cotizacion.pdf",
        pais=args.pais,
        moneda=args.moneda,
        competidores=[m.strip() for m in args.marcas.split(",") if m.strip()] or None,
        dominios=_dominios(args.tiendas, args.pais),
        max_items=args.items,
        progreso=lambda linea: print(f"  - {linea}", flush=True),
    )

    for a in informe.analisis:
        print("\n" + "=" * 78)
        print(f"{a.marca} {a.modelo or ''} — {a.producto}")
        print("=" * 78)
        print(f"Recomendacion   : {a.recomendacion.upper()}")
        print(f"Calificaciones  : producto {a.calificacion_producto}/5 | "
              f"marca {a.calificacion_marca}/5 | precio {a.calificacion_precio}/5 | "
              f"global {a.calificacion_global}/5")
        print(f"Veredicto precio: {a.veredicto_precio}"
              + (f" ({a.desviacion_pct:+.1f}%)" if a.desviacion_pct is not None else ""))
        r = a.rango_mercado
        print(f"Mercado         : {r.moneda} {r.minimo}–{r.maximo} (tipico {r.tipico}) "
              f"[{r.base}, confianza {r.confianza}]")
        print(f"\n{a.resumen}\n")

        if a.donde_comprar:
            print("-- Donde comprarlo --")
            for o in a.donde_comprar:
                precio = f"{o.moneda} {o.precio:,.0f}" if o.precio else "precio n/d"
                print(f"  {o.tienda:24} {precio:>18}   {o.disponibilidad}")
                print(f"      {o.url}")
            print(f"\n  MEJOR OPCION: {a.mejor_opcion}")
            if a.ahorro_posible:
                print(f"  AHORRO: {a.ahorro_posible}")
            print()
        else:
            print("-- No se encontro el producto publicado en las tiendas consultadas --\n")

        print(f"Justificacion   : {a.justificacion_precio}\n")

        if a.comentarios_clientes:
            print("-- Comentarios de usuarios --")
            for c in a.comentarios_clientes:
                print(f"  [{c.sentimiento}] {c.texto}")
                print(f"           {c.fuente} {c.url or ''}")
        if a.alternativas:
            print("\n-- Alternativas --")
            for alt in a.alternativas:
                print(f"  {alt.marca} {alt.modelo} — {alt.calificacion}/5 — "
                      f"{alt.precio_estimado or 'precio n/d'}")
                print(f"     + {'; '.join(alt.ventajas)}")
                print(f"     - {'; '.join(alt.desventajas)}")
        if a.banderas_rojas:
            print("\n-- Banderas rojas --")
            for x in a.banderas_rojas:
                print(f"  ! {x}")
        if a.preguntas_al_proveedor:
            print("\n-- Preguntas al proveedor --")
            for q in a.preguntas_al_proveedor:
                print(f"  ? {q}")
        print(f"\nFuentes ({len(a.fuentes)}):")
        for f in a.fuentes:
            print(f"  - {f.titulo}: {f.url}")

    for nota in informe.notas_investigacion:
        print(f"\n[nota] {nota}")
    print(
        f"\nTokens: {informe.tokens_entrada:,} in / {informe.tokens_salida:,} out"
        f"  |  Costo estimado: US$ {informe.costo_usd:.2f}"
    )

    if args.pdf_salida:
        from agente_compras.exportar_pdf import exportar

        exportar(informe, args.pdf_salida)
        print(f"PDF guardado en {args.pdf_salida}")
    if args.dossier:
        args.dossier.write_text("\n\n".join(informe.dossieres), encoding="utf-8")
        print(f"Dossier guardado en {args.dossier}")
    if args.json:
        args.json.write_text(
            json.dumps(informe.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Informe guardado en {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
