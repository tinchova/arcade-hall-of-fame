"""Intérprete propio del formato de definiciones de hi2txt.

Las definiciones por juego provienen del proyecto hi2txt-xml (GreatStoneEx,
GPL v2) y se descargan por separado en una carpeta local; no se distribuyen con
este código. Ver README.md, sección Créditos.
"""

from __future__ import annotations

import os

from ..reader import read_source
from .decoder import decode
from .definition import Definition, DefinitionLibrary, parse_definition
from .output import DecodedField, DecodedTable, Result, ScoreRow

MAX_FILE_SIZE = 1 << 20  # 1 MiB: muy por encima de cualquier .hi conocido

__all__ = [
    "DecodedField", "DecodedTable", "Definition", "DefinitionLibrary", "Result",
    "ScoreRow", "decode", "parse_definition", "read_file",
]


def read_file(definition: Definition, path: str | os.PathLike[str]) -> Result:
    """Lee un archivo de puntuaciones en modo ``rb`` y lo interpreta."""
    data = read_source(path, max_size=MAX_FILE_SIZE)
    return decode(definition, data, file_name=os.path.basename(os.fspath(path)))
