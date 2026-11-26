"""Convierte una pantalla en operaciones de dibujo simples (sin Tk).

Operaciones:

* ``("rect", x, y, ancho, alto, color)``
* ``("text", x, y, texto, color, escala)``: texto ya normalizado, esquina superior izquierda.
* ``("row", i)`` / ``("endrow", i)``: delimitan cada fila de la tabla, para mostrarlas
  escalonadas; quien no anima las ignora.
"""

from __future__ import annotations

from typing import List, Tuple

from . import pixelfont as pf
from .screens import BG, CARD, DIM, FRAME, HEADER, HEADER_DIM, SCANLINE, SUBTITLE, TITLE, Screen

GRID_COLS = 42  # caracteres de ancho del área de contenido
GRID_LINES = 22  # líneas de alto

Op = Tuple


def scale_for(width: int, height: int) -> int:
    return max(1, min(width // (GRID_COLS * pf.ADVANCE), height // (GRID_LINES * pf.LINE)))


def _text(ops: List[Op], x: int, y: int, text: str, color: str, scale: int) -> None:
    t = pf.normalize(text)
    if t.strip():
        ops.append(("text", x, y, t, color, scale))


def layout(screen: Screen, width: int, height: int, footer_left: str = "", footer_right: str = "",
           scanlines: bool = True) -> List[Op]:
    s = scale_for(width, height)
    char = pf.ADVANCE * s
    line = pf.LINE * s
    content_w = GRID_COLS * char
    x0 = (width - content_w) // 2
    y0 = (height - GRID_LINES * line) // 2
    ops: List[Op] = [("rect", 0, 0, width, height, BG)]
    if scanlines and SCANLINE != BG:
        step = max(3, 3 * s)
        for y in range(0, height, step):
            ops.append(("rect", 0, y, width, max(1, s // 2), SCANLINE))
    border = max(2, s)
    ops.append(("rect", x0 - 2 * s, y0, content_w + 4 * s, border, FRAME))
    ops.append(("rect", x0 - 2 * s, y0 + GRID_LINES * line - border, content_w + 4 * s, border, FRAME))

    # Bloque de título, tabla y notas, fijo arriba: si hay más filas, crece hacia abajo.
    big = 2 * s
    title_lines = wrap(screen.title, GRID_COLS // 2)
    if len(title_lines) > 2:
        title_lines, title_scale = [pf.fit(screen.title, GRID_COLS)], s
    else:
        title_scale = big
    title_h = len(title_lines) * (2 * line if title_scale == big else line)
    rows_h = max(len(screen.rows), 3) * line
    notes = screen.notes[:2]
    top = y0 + line
    y = top
    for text in title_lines:
        tx = (width - pf.text_width(text, title_scale)) // 2
        shadow = max(1, title_scale // 2)
        _text(ops, tx + shadow, y + shadow, text, FRAME, title_scale)  # sombra
        _text(ops, tx, y, text, TITLE, title_scale)
        y += 2 * line if title_scale == big else line
    y += line // 2
    subtitle = pf.fit(screen.subtitle, GRID_COLS)
    _text(ops, (width - pf.text_width(subtitle, s)) // 2, y, subtitle, SUBTITLE, s)
    y += 2 * line

    # Encabezado de columnas y separador.
    x = x0
    positions = []
    for col in screen.columns:
        positions.append((x, col))
        label = pf.fit(col.label, col.width)
        lx = x + (col.width * char - pf.text_width(label, s) if col.align == "right" else 0)
        _text(ops, lx, y, label, HEADER, s)
        x += (col.width + 1) * char
    ops.append(("rect", x0, y + line - 2 * s, content_w, s, HEADER))

    # Filas.
    y += line + line // 2
    rows_top = y
    if not screen.rows and screen.empty_message:
        msg = pf.fit(screen.empty_message, GRID_COLS)
        _text(ops, (width - pf.text_width(msg, s)) // 2, y + line, msg, DIM, s)
    for index, row in enumerate(screen.rows):
        ops.append(("row", index))  # inicio de fila: Tk las muestra de a una
        if index == 0 and screen.highlight_first:
            ops.append(("rect", x0 - s, y - 2 * s, content_w + 2 * s, line, CARD))
        for (cx, col), (text, color) in zip(positions, row):
            t = pf.fit(text, col.width)
            tx = cx + (col.width * char - pf.text_width(t, s) if col.align == "right" else 0)
            _text(ops, tx, y, t, color, s)
        ops.append(("endrow", index))
        y += line

    # Notas, estado y pie.
    note_y = rows_top + rows_h + line
    for text, color in notes:
        t = pf.fit(text, GRID_COLS)
        _text(ops, (width - pf.text_width(t, s)) // 2, note_y, t, color, s)
        note_y += line
    # Pie pegado a la línea inferior: la ayuda (si hay) en la última línea y el
    # estado justo arriba; sin ayuda (imágenes del protector), el estado va abajo de todo.
    foot_y = y0 + GRID_LINES * line - line - border
    left = pf.fit(footer_left, GRID_COLS - 8)
    right = pf.fit(" ".join(p for p in (screen.page, footer_right) if p), 7)
    if screen.status:
        status = pf.fit(screen.status, GRID_COLS)
        status_y = foot_y - line if left.strip() or right.strip() else foot_y
        _text(ops, (width - pf.text_width(status, s)) // 2, status_y, status, HEADER_DIM, s)
    _text(ops, x0, foot_y, left, DIM, s)
    _text(ops, x0 + content_w - pf.text_width(right, s), foot_y, right, DIM, s)
    return ops


def wrap(text: str, width: int) -> List[str]:
    """Reparte el texto en líneas de hasta ``width`` caracteres, por palabras."""
    lines: List[str] = []
    current = ""
    for word in pf.normalize(text).split():
        while len(word) > width:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:width])
            word = word[width:]
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [""]
