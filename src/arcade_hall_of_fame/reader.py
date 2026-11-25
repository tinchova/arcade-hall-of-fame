"""Lectura de archivos originales del emulador, exclusivamente en modo ``rb``.

Este módulo nunca crea, modifica, renombra ni elimina archivos.
"""

from __future__ import annotations

import os
from pathlib import Path

from .models import SourceReadError


def read_source(path: str | os.PathLike[str], max_size: int) -> bytes:
    """Devuelve el contenido de ``path`` abierto en modo binario de solo lectura.

    Lee como máximo ``max_size + 1`` bytes, para detectar un archivo demasiado
    grande sin cargarlo entero. Cualquier problema de acceso o de tamaño se
    informa como ``SourceReadError``.
    """
    if max_size < 0:
        raise ValueError("max_size no puede ser negativo")
    source = Path(path)
    try:
        with open(source, "rb") as handle:
            data = handle.read(max_size + 1)
    except OSError as exc:
        raise SourceReadError(f"no se pudo leer {source.name!r}: {exc.strerror or exc}") from exc
    if len(data) > max_size:
        raise SourceReadError(
            f"{source.name!r} supera el tamaño máximo admitido de {max_size} bytes"
        )
    return data
