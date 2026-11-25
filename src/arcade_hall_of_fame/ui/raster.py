"""Dibuja operaciones de ``layout`` en una imagen PNG, en Python puro.

Sirve para capturas reproducibles y para probar el dibujo sin pantalla.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Iterable

from . import pixelfont as pf


def _rgb(color: str) -> bytes:
    return bytes(int(color[i:i + 2], 16) for i in (1, 3, 5))


class Raster:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 3)

    def rect(self, x: int, y: int, w: int, h: int, color: str) -> None:
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(self.width, x + w), min(self.height, y + h)
        if x2 <= x1 or y2 <= y1:
            return
        row = _rgb(color) * (x2 - x1)
        for yy in range(y1, y2):
            start = (yy * self.width + x1) * 3
            self.pixels[start:start + len(row)] = row

    def text(self, x: int, y: int, text: str, color: str, scale: int) -> None:
        for i, ch in enumerate(text):
            gx = x + i * pf.ADVANCE * scale
            for rx, ry, length in pf.runs(ch):
                self.rect(gx + rx * scale, y + ry * scale, length * scale, scale, color)

    def draw(self, ops: Iterable[tuple]) -> "Raster":
        for op in ops:
            if op[0] == "rect":
                self.rect(*op[1:])
            elif op[0] == "text":
                self.text(*op[1:])
            # "row" solo marca el comienzo de una fila (animación en Tk)
        return self

    def pixel(self, x: int, y: int) -> str:
        i = (y * self.width + x) * 3
        return "#%02x%02x%02x" % tuple(self.pixels[i:i + 3])

    def png(self) -> bytes:
        stride = self.width * 3
        raw = b"".join(b"\x00" + bytes(self.pixels[y * stride:(y + 1) * stride]) for y in range(self.height))

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        header = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")

    def save(self, path: Path) -> None:
        Path(path).write_bytes(self.png())
