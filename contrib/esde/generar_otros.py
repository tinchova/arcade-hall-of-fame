"""Genera las imágenes del sistema "Otros" de ES-DE (tema linear-arcade).

Uso (necesita Pillow):

    python contrib/esde/generar_otros.py BASE.webp SALIDA/

BASE.webp es el arte del carrusel que hizo el generador original del tema para el
sistema (system/systemart/salondelafama.webp, 800x800): se conserva su marco
(borde rosa con brillo y línea violeta) y se redibuja el interior. Escribe:

- logo-otros.svg      -> system/logos/salondelafama.svg (texto "OTROS")
- arte-otros.webp     -> system/systemart/salondelafama.webp (engranaje + "OTROS")
- Salón de la Fama.png y Apagar la Mac.png -> imágenes de las dos entradas
  (contrib/esde/medios/, que instalar_esde.sh copia a downloaded_media).

Todo con la tipografía pixel 5x7 del proyecto (src/arcade_hall_of_fame/ui/pixelfont.py)
y los colores del tema: rosa #F43F5E, sombra violeta #4C1D95.
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageDraw

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(AQUI, "..", "..", "src"))
from arcade_hall_of_fame.ui.pixelfont import ADVANCE, GLYPH_H, LINE, _RAW  # noqa: E402

ROSA = (244, 63, 94, 255)
VIOLETA = (76, 29, 149, 255)
FONDO = (11, 6, 21, 235)  # interior de la tarjeta, como el arte original
ESCALA = 9  # tamaño de un píxel de la fuente en el arte de 800x800
SOMBRA = 3  # desplazamiento de la sombra violeta, en píxeles de imagen
INTERIOR = (158, 158, 643, 493)  # dentro de la línea violeta del marco
RECORTE = (128, 128, 673, 523)  # la tarjeta con su brillo, para las imágenes de las entradas

ENGRANAJE = (
    "....####....",
    ".##.####.##.",
    ".##########.",
    "..########..",
    "####....####",
    "###......###",
    "###......###",
    "####....####",
    "..########..",
    ".##########.",
    ".##.####.##.",
    "....####....",
)

APAGADO = (
    ".....#.....",
    "..#..#..#..",
    ".#...#...#.",
    "#....#....#",
    "#....#....#",
    "#.........#",
    "#.........#",
    "#.........#",
    ".#.......#.",
    "..#.....#..",
    "...#####...",
)


def pixeles_texto(texto: str) -> list[tuple[int, int]]:
    """Píxeles encendidos de una línea de texto (x, y), en unidades de la fuente."""
    puntos = []
    for i, letra in enumerate(texto):
        filas = _RAW.get(letra, ("     ",) * GLYPH_H)
        for y, fila in enumerate(filas):
            for x, c in enumerate(fila):
                if c == "#":
                    puntos.append((i * ADVANCE + x, y))
    return puntos


def pixeles_sprite(sprite: tuple[str, ...]) -> list[tuple[int, int]]:
    return [(x, y) for y, fila in enumerate(sprite) for x, c in enumerate(fila) if c == "#"]


def ancho_texto(texto: str) -> int:
    return len(texto) * ADVANCE - 1


def logo_svg(lineas: list[str]) -> str:
    """SVG pixel como los demás logos del tema: viewBox en unidades, 20 px por unidad."""
    ancho = max(ancho_texto(t) for t in lineas) + 1
    alto = (len(lineas) - 1) * LINE + GLYPH_H + 1
    puntos = []
    for n, texto in enumerate(lineas):
        dx = (ancho - 1 - ancho_texto(texto)) // 2
        puntos += [(x + dx, y + n * LINE) for x, y in pixeles_texto(texto)]

    def grupo(color: str, d: int) -> str:
        rects = "".join(f'<rect x="{x + d}" y="{y + d}" width="1" height="1"/>' for x, y in puntos)
        return f'<g fill="{color}">{rects}</g>'

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="{ancho * 20}" '
        f'height="{alto * 20}" shape-rendering="crispEdges">\n'
        f"{grupo('#4C1D95', 1)}\n{grupo('#F43F5E', 0)}\n</svg>\n"
    )


def dibujar(d: ImageDraw.ImageDraw, puntos, x0: int, y0: int) -> None:
    for color, off in ((VIOLETA, SOMBRA), (ROSA, 0)):
        for x, y in puntos:
            px, py = x0 + x * ESCALA + off, y0 + y * ESCALA + off
            d.rectangle((px, py, px + ESCALA - 1, py + ESCALA - 1), fill=color)


def tarjeta(base: Image.Image, sprite: tuple[str, ...], texto: str) -> Image.Image:
    """El marco de la base con un ícono arriba y una línea de texto abajo, centrados."""
    im = base.copy()
    d = ImageDraw.Draw(im)
    d.rectangle(INTERIOR, fill=FONDO)
    cx = (INTERIOR[0] + INTERIOR[2] + 1) // 2
    alto_sprite = len(sprite)
    alto_total = (alto_sprite + 4 + GLYPH_H) * ESCALA
    y0 = (INTERIOR[1] + INTERIOR[3] + 1 - alto_total) // 2
    dibujar(d, pixeles_sprite(sprite), cx - len(sprite[0]) * ESCALA // 2, y0)
    dibujar(d, pixeles_texto(texto), cx - ancho_texto(texto) * ESCALA // 2, y0 + (alto_sprite + 4) * ESCALA)
    return im


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    base = Image.open(sys.argv[1]).convert("RGBA")
    salida = sys.argv[2]
    os.makedirs(salida, exist_ok=True)
    with open(os.path.join(salida, "logo-otros.svg"), "w", encoding="utf-8") as f:
        f.write(logo_svg(["OTROS"]))
    tarjeta(base, ENGRANAJE, "OTROS").save(os.path.join(salida, "arte-otros.webp"), lossless=True)
    # Entradas: el arte original del salón (corona) y una tarjeta con el botón de apagado.
    base.crop(RECORTE).save(os.path.join(salida, "Salón de la Fama.png"), optimize=True)
    tarjeta(base, APAGADO, "APAGAR").crop(RECORTE).save(os.path.join(salida, "Apagar la Mac.png"), optimize=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
