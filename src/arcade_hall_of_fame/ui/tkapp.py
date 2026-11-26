"""Ventana Tk a pantalla completa: rota pantallas y escanea cada tanto.

Controles: flechas o Enter para cambiar de pantalla, Espacio para pausar la
rotación, Esc para salir. Un joystick mapeado a esas teclas funciona igual.

Para mantenerla liviana, solo se redibuja al cambiar de pantalla. La única
animación es la aparición escalonada de las filas (40 ms entre una y otra),
que se puede desactivar.
"""

from __future__ import annotations

import base64
import sys
from typing import Callable, Dict, List, Optional, Tuple

from . import pixelfont as pf
from . import png
from .layout import GRID_COLS, GRID_LINES, layout, scale_for
from .screens import BG, FRAME, SUBTITLE, Screen

STAGGER_MS = 40
PROGRESS_MS = 500
FOOTER = "<> CAMBIAR ESPACIO PAUSA ESC SALIR"


class ArcadeApp:
    def __init__(self, root, build: Callable[[], List[Screen]], refresh: Optional[Callable[[], None]],
                 seconds: float = 8.0, scan_seconds: float = 60.0, animate: bool = True,
                 fullscreen: bool = True, quit_after: Optional[float] = None):
        import tkinter as tk

        self.tk = tk
        self.root = root
        self.build = build
        self.refresh = refresh
        self.seconds = seconds
        self.scan_seconds = scan_seconds
        self.animate = animate
        self.screens: List[Screen] = []
        self.index = 0
        self.paused = False
        self.images: Dict[Tuple[str, str, int], object] = {}
        self.pictures: Dict[Tuple, object] = {}  # marquees y capturas ya convertidos para Tk
        self.pending: List[str] = []
        self.rotate_job: Optional[str] = None
        self.elapsed_ms = 0
        self.progress_item = None

        root.title("Arcade Hall of Fame")
        root.configure(bg=BG)
        if fullscreen:
            root.attributes("-fullscreen", True)
        self.canvas = tk.Canvas(root, bg=BG, highlightthickness=0, cursor="none" if fullscreen else "")
        self.canvas.pack(fill="both", expand=True)
        for key in ("<Escape>", "q", "Q"):
            root.bind(key, lambda _e: self.close())
        for key in ("<Right>", "<Down>", "<Return>", "<KP_Enter>"):
            root.bind(key, lambda _e: self.step(1))
        for key in ("<Left>", "<Up>"):
            root.bind(key, lambda _e: self.step(-1))
        root.bind("<space>", lambda _e: self.toggle_pause())
        self.canvas.bind("<Configure>", lambda _e: self.root.after_idle(self.show))
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.reload(scan=True)
        if scan_seconds > 0:
            root.after(int(scan_seconds * 1000), self.periodic_scan)
        root.after(PROGRESS_MS, self.tick)
        if quit_after:
            root.after(int(quit_after * 1000), self.close)

    # --- Datos ---------------------------------------------------------------

    def reload(self, scan: bool) -> None:
        if scan and self.refresh is not None:
            try:
                self.refresh()
            except Exception as exc:  # un error de escaneo no debe cerrar la pantalla
                print(f"Error al escanear: {exc}", file=sys.stderr)
        key = self.screens[self.index].key if self.screens else None
        self.screens = self.build()
        keys = [s.key for s in self.screens]
        self.index = keys.index(key) if key in keys else 0

    def periodic_scan(self) -> None:
        self.reload(scan=True)
        self.root.after(int(self.scan_seconds * 1000), self.periodic_scan)

    # --- Navegación ---------------------------------------------------------------

    def step(self, delta: int) -> None:
        if self.screens:
            self.index = (self.index + delta) % len(self.screens)
        self.show()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.show()

    def close(self) -> None:
        self.root.destroy()

    def tick(self) -> None:
        if not self.paused:
            self.elapsed_ms += PROGRESS_MS
            if self.elapsed_ms >= self.seconds * 1000:
                self.step(1)
        self.update_progress()
        self.root.after(PROGRESS_MS, self.tick)

    # --- Dibujo -----------------------------------------------------------------

    def glyph_image(self, ch: str, color: str, scale: int):
        key = (ch, color, scale)
        image = self.images.get(key)
        if image is None:
            image = self.tk.PhotoImage(width=pf.GLYPH_W * scale, height=pf.GLYPH_H * scale)
            for x, y, length in pf.runs(ch):
                image.put(color, to=(x * scale, y * scale, (x + length) * scale, (y + 1) * scale))
            self.images[key] = image
        return image

    def picture_image(self, picture, w: int, h: int):
        """PhotoImage de una imagen escalada, o None si Tk no la acepta.

        Se prueba PPM binario (lo más rápido) y, si esa versión de Tk no lo lee,
        PNG en base64 (Tk 8.6 y posteriores lo traen incorporado)."""
        key = (repr(picture), w, h)
        if key not in self.pictures:
            data = picture.pixels(w, h)
            image = None
            if data is not None:
                for fmt, blob in (("ppm", lambda: b"P6 %d %d 255\n" % (w, h) + data),
                                  ("png", lambda: base64.b64encode(png.encode(w, h, data)))):
                    try:
                        image = self.tk.PhotoImage(data=blob(), format=fmt)
                        break
                    except self.tk.TclError:
                        image = None
            if len(self.pictures) > 64:
                self.pictures.clear()
            self.pictures[key] = image
        return self.pictures[key]

    def draw_op(self, op) -> None:
        if op[0] == "image":
            _, x, y, w, h, picture = op
            image = self.picture_image(picture, w, h)
            if image is not None:
                self.canvas.create_image(x, y, image=image, anchor="nw")
        elif op[0] == "rect":
            _, x, y, w, h, color = op
            self.canvas.create_rectangle(x, y, x + w, y + h, fill=color, width=0)
        elif op[0] == "text":
            _, x, y, text, color, scale = op
            advance = pf.ADVANCE * scale
            for i, ch in enumerate(text):
                if ch != " ":
                    self.canvas.create_image(x + i * advance, y, image=self.glyph_image(ch, color, scale), anchor="nw")

    def show(self) -> None:
        for job in self.pending:
            self.root.after_cancel(job)
        self.pending = []
        self.elapsed_ms = 0
        width, height = self.canvas.winfo_width(), self.canvas.winfo_height()
        if width < 50 or height < 50 or not self.screens:
            return
        screen = self.screens[self.index]
        status = "PAUSA" if self.paused else f"{self.index + 1}/{len(self.screens)}"
        ops = layout(screen, width, height, FOOTER, status)
        self.canvas.delete("all")
        rows: List[List[tuple]] = []
        current: Optional[List[tuple]] = None
        for op in ops:
            if op[0] == "row":
                current = []
            elif op[0] == "endrow":
                rows.append(current or [])
                current = None
            elif current is not None:
                current.append(op)
            else:
                self.draw_op(op)
        for i, row_ops in enumerate(rows):
            if self.animate:
                self.pending.append(self.root.after(STAGGER_MS * (i + 1), self.draw_row, row_ops))
            else:
                self.draw_row(row_ops)
        s = scale_for(width, height)
        content_w = GRID_COLS * pf.ADVANCE * s
        x0 = (width - content_w) // 2
        y_bar = (height - GRID_LINES * pf.LINE * s) // 2 + GRID_LINES * pf.LINE * s - max(2, s)
        self.bar = (x0 - 2 * s, y_bar, content_w + 4 * s, max(2, s))
        self.progress_item = self.canvas.create_rectangle(0, 0, 0, 0, fill=SUBTITLE, width=0)
        self.update_progress()

    def draw_row(self, ops) -> None:
        for op in ops:
            self.draw_op(op)

    def update_progress(self) -> None:
        """Barra de tiempo hasta la próxima pantalla, sobre el borde inferior."""
        if self.progress_item is None:
            return
        x, y, w, h = self.bar
        fraction = 1.0 if self.paused else min(1.0, self.elapsed_ms / (self.seconds * 1000))
        color = FRAME if self.paused else SUBTITLE
        self.canvas.coords(self.progress_item, x, y, x + int(w * fraction), y + h)
        self.canvas.itemconfigure(self.progress_item, fill=color)


def run(build, refresh, seconds: float, scan_seconds: float, animate: bool, window: Optional[Tuple[int, int]],
        quit_after: Optional[float] = None) -> None:
    import tkinter as tk

    root = tk.Tk()
    if window:
        root.geometry(f"{window[0]}x{window[1]}+0+0")
    ArcadeApp(root, build, refresh, seconds, scan_seconds, animate, fullscreen=window is None, quit_after=quit_after)
    root.mainloop()
