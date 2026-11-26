"""Convierte una pantalla en operaciones de dibujo simples (sin Tk).

Operaciones:

* ``("rect", x, y, ancho, alto, color)``
* ``("text", x, y, texto, color, escala)``: texto ya normalizado, esquina superior izquierda.
* ``("image", x, y, ancho, alto, imagen)``: una ``media.Picture`` escalada a ese tamaño
  (su ``repr`` identifica el archivo, así que la huella de la pantalla cambia si cambia).
* ``("row", i)`` / ``("endrow", i)``: delimitan cada fila de la tabla, para mostrarlas
  escalonadas; quien no anima las ignora.
"""

from __future__ import annotations

from typing import List, Tuple

from . import pixelfont as pf
from .png import fit as fit_box
from .screens import BG, DIM, FRAME, HEADER, HEADER_DIM, JUEGO, SCANLINE, SUBTITLE, TITLE, Screen

GRID_COLS = 42  # caracteres de ancho del área de contenido
GRID_LINES = 22  # líneas de alto
MARQUEE_LINES = 3  # alto del marquee que reemplaza al título, en líneas
MARQUEE_COLS = 30  # ancho máximo del marquee, en caracteres
SHOT_GAP = 1  # caracteres entre la tabla y la captura
MOSAIC_COLS, MOSAIC_ROWS = 3, 2
TILE_LOGO_LINES = 3  # alto del marquee chico de cada celda del mosaico, en líneas

Op = Tuple


def scale_for(width: int, height: int) -> int:
    return max(1, min(width // (GRID_COLS * pf.ADVANCE), height // (GRID_LINES * pf.LINE)))


def _text(ops: List[Op], x: int, y: int, text: str, color: str, scale: int) -> None:
    t = pf.normalize(text)
    if t.strip():
        ops.append(("text", x, y, t, color, scale))


def _image(ops: List[Op], picture, x: int, y: int, box_w: int, box_h: int, center_y: bool = True) -> int:
    """Imagen centrada en la caja (sin pasarse); devuelve el alto que ocupó."""
    w, h = fit_box(picture.width, picture.height, box_w, box_h)
    if w and h:
        ops.append(("image", x + (box_w - w) // 2, y + ((box_h - h) // 2 if center_y else 0), w, h, picture))
    return h


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
    if screen.marquee is not None:
        title_lines = []
        box_w = min(content_w, MARQUEE_COLS * char)
        _image(ops, screen.marquee, (width - box_w) // 2, y, box_w, MARQUEE_LINES * line)
        y += MARQUEE_LINES * line
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

    if screen.qr:
        _qr(ops, screen, width, y, x0, y0, s, line, border)
        return ops
    foot_y = y0 + GRID_LINES * line - line - border
    left = pf.fit(footer_left, GRID_COLS - 8)
    right = pf.fit(" ".join(p for p in (screen.page, footer_right) if p), 7)
    status_y = foot_y - line if left.strip() or right.strip() else foot_y
    if screen.tiles is not None:
        _mosaic(ops, screen, y, x0, content_w, status_y - line // 2, s, line)
        _footer(ops, screen, width, x0, content_w, foot_y, status_y, left, right, s)
        return ops

    # Con captura, la tabla va sin la última columna (vacía) y la captura a su derecha.
    columns = list(screen.columns)
    if screen.shot is not None:
        while columns and not columns[-1].label and len(columns) > 1:
            columns.pop()
    table_chars = sum(c.width + 1 for c in columns) - 1
    table_w = content_w if screen.shot is None else table_chars * char

    # Encabezado de columnas y separador.
    x = x0
    positions = []
    header_y = y
    for col in columns:
        positions.append((x, col))
        label = pf.fit(col.label, col.width)
        lx = x + (col.width * char - pf.text_width(label, s) if col.align == "right" else 0)
        _text(ops, lx, y, label, HEADER, s)
        x += (col.width + 1) * char
    ops.append(("rect", x0, y + line - 2 * s, table_w, s, HEADER))

    # Filas.
    y += line + line // 2
    rows_top = y
    if not screen.rows and screen.empty_message:
        msg = pf.fit(screen.empty_message, GRID_COLS)
        _text(ops, (width - pf.text_width(msg, s)) // 2, y + line, msg, DIM, s)
    for index, row in enumerate(screen.rows):
        ops.append(("row", index))  # inicio de fila: Tk las muestra de a una
        for (cx, col), (text, color) in zip(positions, row):
            t = pf.fit(text, col.width)
            tx = cx + (col.width * char - pf.text_width(t, s) if col.align == "right" else 0)
            _text(ops, tx, y, t, color, s)
        ops.append(("endrow", index))
        y += line

    # Captura al costado de la tabla, desde el encabezado hasta antes del estado,
    # con un borde fino del color del marco.
    if screen.shot is not None:
        shot_x = x0 + (table_chars + SHOT_GAP) * char
        box_w = x0 + content_w - shot_x
        box_h = status_y - line // 2 - header_y
        w, h = fit_box(screen.shot.width, screen.shot.height, box_w - 2 * s, box_h - 2 * s)
        if w and h:
            ix = shot_x + (box_w - w) // 2
            ops.append(("rect", ix - s, header_y - s, w + 2 * s, h + 2 * s, FRAME))
            ops.append(("image", ix, header_y, w, h, screen.shot))

    # Notas, estado y pie.
    note_y = rows_top + rows_h + line
    for text, color in notes:
        t = pf.fit(text, GRID_COLS if screen.shot is None else table_chars)
        nx = (width - pf.text_width(t, s)) // 2 if screen.shot is None else x0
        _text(ops, nx, note_y, t, color, s)
        note_y += line
    _footer(ops, screen, width, x0, content_w, foot_y, status_y, left, right, s)
    return ops


def _footer(ops: List[Op], screen: Screen, width: int, x0: int, content_w: int, foot_y: int, status_y: int,
            left: str, right: str, s: int) -> None:
    """Pie pegado a la línea inferior: la ayuda (si hay) en la última línea y el
    estado justo arriba; sin ayuda (imágenes del protector), el estado va abajo de todo."""
    if screen.status:
        status = pf.fit(screen.status, GRID_COLS)
        _text(ops, (width - pf.text_width(status, s)) // 2, status_y, status, HEADER_DIM, s)
    _text(ops, x0, foot_y, left, DIM, s)
    _text(ops, x0 + content_w - pf.text_width(right, s), foot_y, right, DIM, s)


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


def _qr(ops: List[Op], screen: Screen, width: int, y: int, x0: int, y0: int, s: int, line: int, border: int) -> None:
    """Código QR centrado (negro sobre blanco, con margen de 4 módulos), y las notas abajo."""
    modules = len(screen.qr)
    notes = screen.notes[:2]
    bottom = y0 + GRID_LINES * line - border - line * (2 + len(notes))
    side = min(bottom - y, GRID_COLS * pf.ADVANCE * s // 2)
    module = max(1, side // (modules + 8))
    total = module * (modules + 8)
    qx = (width - total) // 2
    ops.append(("rect", qx, y, total, total, "#ffffff"))
    for row, cells in enumerate(screen.qr):
        x = 0
        while x < modules:  # tramos horizontales, para dibujar menos rectángulos
            if cells[x]:
                start = x
                while x < modules and cells[x]:
                    x += 1
                ops.append(("rect", qx + (4 + start) * module, y + (4 + row) * module, (x - start) * module,
                            module, "#000000"))
            else:
                x += 1
    note_y = y + total + line // 2
    for text, color in notes:
        t = pf.fit(text, GRID_COLS)
        _text(ops, (width - pf.text_width(t, s)) // 2, note_y, t, color, s)
        note_y += line
    if screen.status:
        status = pf.fit(screen.status, GRID_COLS)
        _text(ops, (width - pf.text_width(status, s)) // 2, y0 + GRID_LINES * line - line - border, status,
              HEADER_DIM, s)


def _mosaic(ops: List[Op], screen: Screen, top: int, x0: int, content_w: int, bottom: int,
            s: int, line: int) -> None:
    """Grilla de 3 x 2: en cada celda el marquee chico del juego (o su nombre), el 1º
    con su nombre final en oro y los puntos en blanco. Cada celda es una "fila" para
    la animación de la ventana."""
    char = pf.ADVANCE * s
    cell_w = content_w // MOSAIC_COLS
    cell_chars = cell_w // char - 1
    cell_h = (bottom - top) // MOSAIC_ROWS
    logo_h = TILE_LOGO_LINES * line
    block_h = logo_h + line // 2 + 2 * line  # logo, separación, jugador y puntos
    for index, tile in enumerate((screen.tiles or [])[:MOSAIC_COLS * MOSAIC_ROWS]):
        col, row = index % MOSAIC_COLS, index // MOSAIC_COLS
        cx = x0 + col * cell_w
        cy = top + row * cell_h + max(0, (cell_h - block_h) // 2)
        ops.append(("row", index))
        if tile.marquee is not None:
            _image(ops, tile.marquee, cx + char // 2, cy, cell_w - char, logo_h)
        else:
            lines = wrap(tile.title, cell_chars)[:TILE_LOGO_LINES]
            if len(wrap(tile.title, cell_chars)) > TILE_LOGO_LINES:
                lines[-1] = pf.fit(lines[-1] + " X", cell_chars)  # termina en punto: hay más
            ty = cy + (logo_h - len(lines) * line) // 2 + (line - pf.GLYPH_H * s) // 2
            for text in lines:
                _text(ops, cx + (cell_w - pf.text_width(text, s)) // 2, ty, text, JUEGO, s)
                ty += line
        y = cy + logo_h + line // 2
        for text, color in (tile.holder, tile.score):
            t = pf.fit(text, cell_chars)
            _text(ops, cx + (cell_w - pf.text_width(t, s)) // 2, y, t, color, s)
            y += line
        ops.append(("endrow", index))
