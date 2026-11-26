"""Lector de PNG y escalado, en Python puro (sin dependencias).

Se usa para mostrar los marquees y capturas que bajó ES-DE. Soporta lo que
ES-DE suele bajar: 8 bits por canal, sin entrelazado, tipos de color 0 (gris),
2 (RGB), 3 (paleta), 4 (gris con alfa) y 6 (RGBA), con los cinco filtros y la
transparencia de ``tRNS``. Cualquier otra cosa (16 bits, entrelazado, un JPG con
extensión .png) da ``PNGError`` y quien llama muestra el texto en su lugar.

El resultado es RGB de 3 bytes por píxel, compuesto sobre negro (el fondo de
las pantallas), así que la transparencia de los logos se ve como fondo.

Para que sea rápido sin numpy, lo que se puede se hace con operaciones de
``bytes`` (rebanadas, ``translate``) y enteros grandes; lo demás, en bucles
cortos. El escalado es separable, con pesos enteros: promedio por área al
achicar y bilineal al agrandar.
"""

from __future__ import annotations

import math
import re
import struct
import zlib
from typing import List, Optional, Tuple

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_SHIFT = 16
_ONE = 1 << _SHIFT
_HALF = _ONE >> 1


class PNGError(ValueError):
    """PNG no soportado o dañado."""


def read_header(data: bytes) -> Tuple[int, int, int, int, int]:
    """(ancho, alto, bits, tipo de color, entrelazado) del IHDR; ``PNGError`` si no es PNG."""
    if data[:8] != SIGNATURE or data[12:16] != b"IHDR" or len(data) < 33:
        raise PNGError("no es un PNG")
    width, height, depth, color, _comp, _filt, interlace = struct.unpack(">IIBBBBB", data[16:29])
    return width, height, depth, color, interlace


def check_supported(header: Tuple[int, int, int, int, int]) -> None:
    width, height, depth, color, interlace = header
    if color not in CHANNELS:
        raise PNGError(f"tipo de color {color} no soportado")
    if depth != 8:
        raise PNGError(f"{depth} bits por canal no soportado")
    if interlace:
        raise PNGError("PNG entrelazado no soportado")
    if not (0 < width <= 8192 and 0 < height <= 8192):
        raise PNGError("tamaño no válido")


def _chunks(data: bytes):
    pos = 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length:
            raise PNGError("PNG cortado")
        yield kind, body
        if kind == b"IEND":
            return
        pos += 12 + length


def _add_bytes(a: bytes, b: bytes, mask7: int, mask8: int) -> bytearray:
    """Suma byte a byte módulo 256, de una vez, con un entero grande (sin acarreo entre bytes)."""
    x, y = int.from_bytes(a, "big"), int.from_bytes(b, "big")
    return bytearray((((x & mask7) + (y & mask7)) ^ ((x ^ y) & mask8)).to_bytes(len(a), "big"))


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> bytearray:
    out = bytearray(height * stride)
    prev = bytearray(stride)
    mask7 = int.from_bytes(b"\x7f" * stride, "big")
    mask8 = int.from_bytes(b"\x80" * stride, "big")
    pos = 0
    for y in range(height):
        kind = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if len(line) != stride:
            raise PNGError("datos de imagen incompletos")
        if kind == 0:
            pass
        elif kind == 1:  # Sub
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif kind == 2:  # Up
            line = _add_bytes(line, prev, mask7, mask8)
        elif kind == 3:  # Average
            for i in range(bpp):
                line[i] = (line[i] + (prev[i] >> 1)) & 255
            for i in range(bpp, stride):
                line[i] = (line[i] + ((line[i - bpp] + prev[i]) >> 1)) & 255
        elif kind == 4:  # Paeth
            for i in range(bpp):
                line[i] = (line[i] + prev[i]) & 255
            for i in range(bpp, stride):
                a, b, c = line[i - bpp], prev[i], prev[i - bpp]
                pa, pb, pc = b - c, a - c, a + b - c - c
                if pa < 0:
                    pa = -pa
                if pb < 0:
                    pb = -pb
                if pc < 0:
                    pc = -pc
                if pa <= pb and pa <= pc:
                    line[i] = (line[i] + a) & 255
                elif pb <= pc:
                    line[i] = (line[i] + b) & 255
                else:
                    line[i] = (line[i] + c) & 255
        else:
            raise PNGError(f"filtro {kind} no válido")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


# Tablas de "valor * alfa / 255" (redondeado) para componer sobre negro, una por alfa.
_MUL: List[bytes] = [bytes((v * a + 127) // 255 for v in range(256)) for a in range(256)]
_NOT_OPAQUE = re.compile(rb"[^\xff]+")


def _composite(rgb: bytearray, alpha: bytes) -> None:
    """Compone sobre negro los píxeles no opacos (los opacos quedan como están).

    Los tramos de píxeles no opacos se buscan con una expresión regular (en C);
    los totalmente transparentes se ponen en negro de una vez.
    """
    for match in _NOT_OPAQUE.finditer(alpha):
        start, end = match.span()
        run = match.group()
        if run.count(0) == len(run):
            rgb[start * 3:end * 3] = bytes((end - start) * 3)
            continue
        for i in range(start, end):
            table = _MUL[alpha[i]]
            j = i * 3
            rgb[j] = table[rgb[j]]
            rgb[j + 1] = table[rgb[j + 1]]
            rgb[j + 2] = table[rgb[j + 2]]


def decode(data: bytes) -> Tuple[int, int, bytes]:
    """PNG → (ancho, alto, RGB compuesto sobre negro)."""
    header = read_header(data)
    check_supported(header)
    width, height, _depth, color, _interlace = header
    palette = b""
    trns = b""
    idat = []
    for kind, body in _chunks(data):
        if kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
    if not idat:
        raise PNGError("sin datos de imagen")
    try:
        raw = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise PNGError(f"datos comprimidos dañados: {exc}") from None
    bpp = CHANNELS[color]
    pixels = _unfilter(raw, height, width * bpp, bpp)
    count = width * height
    rgb = bytearray(count * 3)
    if color == 0:
        gray = bytes(pixels)
        if len(trns) >= 2:  # un valor de gris transparente
            table = bytearray(range(256))
            table[trns[1]] = 0
            gray = gray.translate(table)
        rgb[0::3] = rgb[1::3] = rgb[2::3] = gray
    elif color == 2:
        rgb[:] = pixels
        if len(trns) >= 6:  # un color transparente
            key = bytes((trns[1], trns[3], trns[5]))
            pos = rgb.find(key)
            while pos != -1:
                if pos % 3 == 0:
                    rgb[pos:pos + 3] = b"\0\0\0"
                pos = rgb.find(key, pos + 1)
    elif color == 3:
        if not palette or len(palette) % 3:
            raise PNGError("paleta ausente o dañada")
        entries = len(palette) // 3
        # Se compone la paleta sobre negro y se traduce cada canal con translate.
        tables = [bytearray(256) for _ in range(3)]
        for index in range(entries):
            alpha = trns[index] if index < len(trns) else 255
            for channel in range(3):
                tables[channel][index] = _MUL[alpha][palette[index * 3 + channel]]
        indices = bytes(pixels)
        for channel in range(3):
            rgb[channel::3] = indices.translate(tables[channel])
    elif color == 4:
        gray = bytes(pixels[0::2])
        rgb[0::3] = rgb[1::3] = rgb[2::3] = gray
        _composite(rgb, bytes(pixels[1::2]))
    else:  # 6
        for channel in range(3):
            rgb[channel::3] = pixels[channel::4]
        _composite(rgb, bytes(pixels[3::4]))
    return width, height, bytes(rgb)


def fit(width: int, height: int, box_w: int, box_h: int) -> Tuple[int, int]:
    """Tamaño que entra en la caja respetando la proporción (al menos 1 x 1)."""
    if width <= 0 or height <= 0 or box_w <= 0 or box_h <= 0:
        return 0, 0
    factor = min(box_w / width, box_h / height)
    return max(1, round(width * factor)), max(1, round(height * factor))


def _contributions(src: int, dst: int) -> List[Tuple[int, Tuple[int, ...]]]:
    """Para cada píxel de destino: (primer píxel de origen, pesos enteros que suman 1 << 16).

    Al achicar, promedio por área (cada píxel de origen pesa lo que cubre); al
    agrandar, bilineal (los dos vecinos más cercanos, según la distancia).
    """
    result = []
    scale = src / dst
    for i in range(dst):
        if scale >= 1:
            lo, hi = i * scale, (i + 1) * scale
            first, last = int(lo), min(src, math.ceil(hi - 1e-9))
            weights = [min(hi, j + 1) - max(lo, j) for j in range(first, last)]
        else:
            center = min(max((i + 0.5) * scale - 0.5, 0.0), src - 1.0)
            first = int(center)
            frac = center - first
            weights = [1.0 - frac, frac] if first + 1 < src and frac > 0 else [1.0]
        total = sum(weights)
        ints = [int(w / total * _ONE) for w in weights]
        ints[max(range(len(ints)), key=lambda k: weights[k])] += _ONE - sum(ints)
        while len(ints) > 1 and ints[-1] == 0:
            ints.pop()
        result.append((first, tuple(ints)))
    return result


def _resample_line(plane: bytes, contributions) -> bytes:
    out = bytearray(len(contributions))
    for x, (first, weights) in enumerate(contributions):
        if len(weights) == 1:
            out[x] = plane[first]
        elif len(weights) == 2:
            out[x] = (plane[first] * weights[0] + plane[first + 1] * weights[1] + _HALF) >> _SHIFT
        else:
            acc = _HALF
            for k, w in enumerate(weights):
                acc += plane[first + k] * w
            out[x] = acc >> _SHIFT
    return bytes(out)


def _blend_rows(rows: List[bytes], weights: Tuple[int, ...]) -> bytes:
    if len(weights) == 1:
        return rows[0]
    if len(weights) == 2:
        w0, w1 = weights
        return bytes([(a * w0 + b * w1 + _HALF) >> _SHIFT for a, b in zip(rows[0], rows[1])])
    if len(weights) == 3:
        w0, w1, w2 = weights
        return bytes([(a * w0 + b * w1 + c * w2 + _HALF) >> _SHIFT for a, b, c in zip(*rows)])
    acc = [_HALF] * len(rows[0])
    for row, w in zip(rows, weights):
        acc = [s + v * w for s, v in zip(acc, row)]
    return bytes([s >> _SHIFT for s in acc])


def resample(rgb: bytes, width: int, height: int, new_w: int, new_h: int) -> bytes:
    """Escala una imagen RGB (3 bytes por píxel) a ``new_w`` x ``new_h``."""
    if (new_w, new_h) == (width, height):
        return bytes(rgb)
    columns = _contributions(width, new_w)
    stride = width * 3
    # Primero en horizontal, canal por canal (cada canal es una rebanada de la fila).
    narrow: List[bytes] = []
    for y in range(height):
        row = rgb[y * stride:(y + 1) * stride]
        out = bytearray(new_w * 3)
        for channel in range(3):
            out[channel::3] = _resample_line(row[channel::3], columns)
        narrow.append(bytes(out))
    # Después en vertical, combinando filas enteras.
    result = bytearray()
    for first, weights in _contributions(height, new_h):
        result += _blend_rows(narrow[first:first + len(weights)], weights)
    return bytes(result)


def encode(width: int, height: int, rgb: bytes) -> bytes:
    """RGB → PNG (tipo de color 2, sin filtros); para pruebas y capturas."""
    stride = width * 3
    raw = b"".join(b"\x00" + rgb[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def size_of(data: bytes) -> Optional[Tuple[int, int]]:
    """(ancho, alto) si el PNG está soportado; None si no."""
    try:
        header = read_header(data)
        check_supported(header)
    except PNGError:
        return None
    return header[0], header[1]
