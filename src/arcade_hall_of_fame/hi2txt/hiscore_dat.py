"""Lectura de ``hiscore.dat`` (FBNeo o MAME) para comparar regiones de memoria.

Solo se usa para comprobar que la definición de hi2txt corresponde a lo que
guarda el emulador. El archivo no se incluye en el repositorio.
"""

from __future__ import annotations

import re
from pathlib import Path

from .definition import parse_region_line

Region = tuple[int, int, int, int]
_NAME_LINE = re.compile(r"^([A-Za-z0-9_]+):$")


def parse_hiscore_dat(text: str) -> dict[str, tuple[Region, ...]]:
    """Devuelve juego → regiones (dirección, largo, inicio, fin), en orden."""
    entries: dict[str, tuple[Region, ...]] = {}
    names: list[str] = []
    regions: list[Region] = []

    def flush():
        for name in names:
            entries.setdefault(name, tuple(regions))

    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        match = _NAME_LINE.match(line)
        if match or line.endswith(":"):  # también entradas con lista de software
            if regions:
                flush()
                names, regions = [], []
            if match:
                names.append(match.group(1))
            continue
        region = parse_region_line(line)
        if region is not None and names:
            regions.append(region)
    if regions:
        flush()
    return entries


def load_hiscore_dat(path: str | Path) -> dict[str, tuple[Region, ...]]:
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8", errors="replace")
    return parse_hiscore_dat(text)


def expected_size(regions: tuple[Region, ...]) -> int:
    return sum(length for _, length, _, _ in regions)
