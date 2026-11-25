"""Tipografía pixel propia de 5 x 7, diseñada para este proyecto.

Cada glifo son siete filas de cinco columnas; ``#`` es un píxel encendido.
No proviene de ninguna fuente existente, así que no requiere licencia aparte.
El texto se normaliza a mayúsculas sin tildes; un carácter sin glifo se dibuja
como ``?``.
"""

from __future__ import annotations

import unicodedata
from typing import Dict, List, Tuple

GLYPH_W = 5
GLYPH_H = 7
ADVANCE = 6  # ancho de glifo + separación, en píxeles de la fuente
LINE = 10  # alto de línea, en píxeles de la fuente

_RAW: Dict[str, Tuple[str, ...]] = {
    "A": (" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "B": ("#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "),
    "C": (" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "),
    "D": ("#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "),
    "E": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"),
    "F": ("#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "),
    "G": (" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ####"),
    "H": ("#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"),
    "I": (" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "),
    "J": ("  ###", "   # ", "   # ", "   # ", "#  # ", "#  # ", " ##  "),
    "K": ("#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"),
    "L": ("#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"),
    "M": ("#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"),
    "N": ("#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"),
    "O": (" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "P": ("#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "),
    "Q": (" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"),
    "R": ("#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"),
    "S": (" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "),
    "T": ("#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "),
    "U": ("#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "),
    "V": ("#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "),
    "W": ("#   #", "#   #", "#   #", "# # #", "# # #", "# # #", " # # "),
    "X": ("#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"),
    "Y": ("#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "),
    "Z": ("#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"),
    "0": (" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "),
    "1": ("  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "),
    "2": (" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"),
    "3": ("#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "),
    "4": ("   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "),
    "5": ("#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "),
    "6": ("  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "),
    "7": ("#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "),
    "8": (" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "),
    "9": (" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "),
    " ": ("     ",) * 7,
    ".": ("     ",) * 5 + (" ##  ", " ##  "),
    ",": ("     ",) * 5 + ("  #  ", " #   "),
    ":": ("     ", " ##  ", " ##  ", "     ", " ##  ", " ##  ", "     "),
    ";": ("     ", " ##  ", " ##  ", "     ", " ##  ", "  #  ", " #   "),
    "-": ("     ", "     ", "     ", " ### ", "     ", "     ", "     "),
    "+": ("     ", "  #  ", "  #  ", "#####", "  #  ", "  #  ", "     "),
    "/": ("    #", "    #", "   # ", "  #  ", " #   ", "#    ", "#    "),
    "!": ("  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "     ", "  #  "),
    "?": (" ### ", "#   #", "    #", "   # ", "  #  ", "     ", "  #  "),
    "'": ("  #  ", "  #  ", " #   ", "     ", "     ", "     ", "     "),
    '"': (" # # ", " # # ", "     ", "     ", "     ", "     ", "     "),
    "(": ("   # ", "  #  ", " #   ", " #   ", " #   ", "  #  ", "   # "),
    ")": (" #   ", "  #  ", "   # ", "   # ", "   # ", "  #  ", " #   "),
    "[": (" ### ", " #   ", " #   ", " #   ", " #   ", " #   ", " ### "),
    "]": (" ### ", "   # ", "   # ", "   # ", "   # ", "   # ", " ### "),
    "#": (" # # ", " # # ", "#####", " # # ", "#####", " # # ", " # # "),
    "*": ("     ", "  #  ", "# # #", " ### ", "# # #", "  #  ", "     "),
    "=": ("     ", "     ", "#####", "     ", "#####", "     ", "     "),
    "<": ("   # ", "  #  ", " #   ", "#    ", " #   ", "  #  ", "   # "),
    ">": (" #   ", "  #  ", "   # ", "    #", "   # ", "  #  ", " #   "),
    "_": ("     ",) * 6 + ("#####",),
    "%": ("##   ", "##  #", "   # ", "  #  ", " #   ", "#  ##", "   ##"),
    "&": (" ##  ", "#  # ", "# #  ", " #   ", "# # #", "#  # ", " ## #"),
    "@": (" ### ", "#   #", "# ###", "# # #", "# ###", "#    ", " ### "),
}


def _parse(rows: Tuple[str, ...]) -> Tuple[Tuple[int, int], ...]:
    assert len(rows) == GLYPH_H and all(len(r) == GLYPH_W for r in rows)
    return tuple((x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c == "#")


GLYPHS: Dict[str, Tuple[Tuple[int, int], ...]] = {ch: _parse(rows) for ch, rows in _RAW.items()}


def normalize(text: str) -> str:
    """Mayúsculas sin tildes; los caracteres sin glifo pasan a ``?``."""
    decomposed = unicodedata.normalize("NFD", str(text).upper())
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c if c in GLYPHS else ("" if c in "\r\n" else "?") for c in plain)


def glyph(ch: str) -> Tuple[Tuple[int, int], ...]:
    return GLYPHS.get(ch, GLYPHS["?"])


def runs(ch: str) -> List[Tuple[int, int, int]]:
    """Tramos horizontales (x, y, largo) del glifo, para dibujar menos rectángulos."""
    rows = _RAW.get(ch, _RAW["?"])
    out = []
    for y, row in enumerate(rows):
        x = 0
        while x < GLYPH_W:
            if row[x] == "#":
                start = x
                while x < GLYPH_W and row[x] == "#":
                    x += 1
                out.append((start, y, x - start))
            else:
                x += 1
    return out


def text_width(text: str, scale: int) -> int:
    n = len(normalize(text))
    return 0 if n == 0 else (n * ADVANCE - 1) * scale


def fit(text: str, chars: int) -> str:
    """Recorta a ``chars`` caracteres (normalizados)."""
    t = normalize(text)
    return t if len(t) <= chars else t[: max(0, chars - 1)] + "."
