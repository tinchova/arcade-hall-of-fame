"""Muestra la tabla de puntuaciones de un archivo, para diagnóstico.

Uso, desde la raíz del repositorio::

    python -m arcade_hall_of_fame.hi2txt galaga ruta/a/una/copia/galaga.hi

El archivo se abre en modo ``rb``; no se escribe nada.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..models import HighScoreError
from . import DefinitionLibrary, read_file
from .fetch import REVISION
from .formats import render

DEFAULT_DB = Path(__file__).resolve().parents[3] / "local" / "hi2txt-xml" / REVISION / "src" / "main" / "db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Muestra la tabla de un archivo de puntuaciones.")
    parser.add_argument("juego", help="nombre del set, p. ej. galaga")
    parser.add_argument("archivo", help="archivo .hi (preferentemente una copia)")
    parser.add_argument("--definiciones", default=str(DEFAULT_DB), help=f"carpeta de definiciones (por defecto {DEFAULT_DB})")
    parser.add_argument("--todo", action="store_true", help="mostrar también tablas y campos extra/debug")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    try:
        result = read_file(DefinitionLibrary(args.definiciones).load(args.juego), args.archivo)
    except HighScoreError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    for table in result.tables:
        if table.display != "always" and not args.todo:
            continue
        visible = [k for k, d in enumerate(table.column_display) if args.todo or d == "always"]
        if not visible:
            continue
        if table.id:
            print(f"[{table.id}]")
        print(" | ".join(table.columns[k] for k in visible))
        for row in table.rows:
            print(" | ".join(render(row[k]) for k in visible))
        print()
    for field in result.fields:
        if args.todo or field.display == "always":
            print(f"{field.id}: {render(field.value)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
