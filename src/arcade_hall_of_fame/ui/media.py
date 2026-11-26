"""Marquees y capturas de los juegos, leídos de los medios que bajó ES-DE.

ES-DE guarda los medios en ``<carpeta de medios>/<sistema>/<tipo>/<subcarpeta>/<zip>.png``
(por ejemplo ``~/ES-DE/downloaded_media/fbneo/marquees/fbneo/bublbobl.png``; la
subcarpeta es la de la ROM: ``cps1``, ``neogeo``...). La carpeta de medios es la de
``MediaDirectory`` en ``es_settings.xml`` o, si está vacía, ``~/ES-DE/downloaded_media``.
Todo se lee en modo lectura y nada se copia al repositorio.

Si un juego no tiene la imagen, o el PNG no está soportado (ver ``png.py``), se
devuelve None y la pantalla muestra el texto en su lugar.

Escalar en Python puro tarda unas décimas de segundo por imagen, así que el
resultado escalado se guarda en una caché en disco (y en memoria), con una clave
que incluye la ruta, el tamaño y la fecha del archivo: si ES-DE baja otra imagen,
se vuelve a escalar.
"""

from __future__ import annotations

import hashlib
import os
import struct
import xml.etree.ElementTree as ET
import zlib
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from . import png

MARQUEE_KINDS = ("marquees",)
SHOT_KINDS = ("screenshots", "titlescreens")  # captura; si no hay, pantalla de título
CACHE_MAGIC = b"HOFRGB1\n"
CACHE_VERSION = 1
_MEMORY: "OrderedDict[Tuple, bytes]" = OrderedDict()
_MEMORY_MAX = 96


def esde_media_dir(esde_home: Optional[Path] = None) -> Path:
    """Carpeta de medios de ES-DE: ``MediaDirectory`` de su configuración o la de por defecto."""
    home = Path(esde_home) if esde_home else Path.home() / "ES-DE"
    value = ""
    try:
        text = (home / "settings" / "es_settings.xml").read_text(encoding="utf-8")
        root = ET.fromstring("<r>" + text.split("?>", 1)[-1] + "</r>")
        value = next((e.get("value", "") for e in root.iter("string") if e.get("name") == "MediaDirectory"), "")
    except (OSError, ET.ParseError):
        pass
    value = value.strip()
    if value:
        return Path(os.path.expanduser(value))
    return home / "downloaded_media"


@dataclass(frozen=True)
class Picture:
    """Una imagen en disco. Su ``repr`` (ruta, tamaño y fecha) sirve de huella para el protector."""

    path: str
    size: int
    mtime_ns: int
    width: int
    height: int
    cache_dir: Optional[str] = field(default=None, compare=False, repr=False)

    def pixels(self, width: int, height: int) -> Optional[bytes]:
        """RGB escalado a ``width`` x ``height``; None si no se pudo leer."""
        key = (self.path, self.size, self.mtime_ns, width, height)
        if key in _MEMORY:
            _MEMORY.move_to_end(key)
            return _MEMORY[key]
        data = self._from_disk(key)
        if data is None:
            try:
                w, h, rgb = png.decode(Path(self.path).read_bytes())
                data = png.resample(rgb, w, h, width, height)
            except (OSError, png.PNGError):
                return None
            self._to_disk(key, data)
        _MEMORY[key] = data
        while len(_MEMORY) > _MEMORY_MAX:
            _MEMORY.popitem(last=False)
        return data

    def _cache_file(self, key) -> Optional[Path]:
        if not self.cache_dir:
            return None
        digest = hashlib.sha1(repr((CACHE_VERSION,) + key).encode("utf-8")).hexdigest()
        return Path(self.cache_dir) / f"{digest}.rgb"

    def _from_disk(self, key) -> Optional[bytes]:
        path = self._cache_file(key)
        if path is None:
            return None
        try:
            blob = path.read_bytes()
            if blob[:8] != CACHE_MAGIC:
                return None
            w, h = struct.unpack(">II", blob[8:16])
            data = zlib.decompress(blob[16:])
            return data if (w, h) == key[3:] and len(data) == w * h * 3 else None
        except (OSError, zlib.error, struct.error):
            return None

    def _to_disk(self, key, data: bytes) -> None:
        path = self._cache_file(key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_name(path.name + ".part")
            temp.write_bytes(CACHE_MAGIC + struct.pack(">II", *key[3:]) + zlib.compress(data, 1))
            os.replace(temp, path)
        except OSError:
            pass  # sin caché igual funciona, solo más lento


class Media:
    """Busca el marquee y la captura de cada juego en la carpeta de medios de ES-DE."""

    def __init__(self, root: Optional[Path], system: str = "fbneo", cache_dir: Optional[Path] = None):
        self.root = Path(root) / system if root else None
        self.cache_dir = str(cache_dir) if cache_dir else None
        self._subdirs: Dict[str, List[Path]] = {}
        self._found: Dict[Tuple[str, Tuple[str, ...]], Optional[Picture]] = {}

    def _dirs(self, kind: str, system: str) -> List[Path]:
        if kind not in self._subdirs:
            base = self.root / kind
            dirs = [base]
            try:
                subs = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: (p.name != system, p.name))
                dirs += subs
            except OSError:
                pass
            self._subdirs[kind] = dirs
        return self._subdirs[kind]

    def find(self, game: str, kinds: Iterable[str]) -> Optional[Picture]:
        kinds = tuple(kinds)
        if self.root is None:
            return None
        key = (game, kinds)
        if key not in self._found:
            self._found[key] = self._search(game, kinds)
        return self._found[key]

    def _search(self, game: str, kinds: Tuple[str, ...]) -> Optional[Picture]:
        for kind in kinds:
            for folder in self._dirs(kind, self.root.name):
                path = folder / f"{game}.png"
                try:
                    stat = path.stat()
                    with open(path, "rb") as handle:
                        head = handle.read(33)
                except OSError:
                    continue
                size = png.size_of(head)
                if size is None:
                    break  # existe pero no está soportado: se prueba el tipo siguiente (o el texto)
                return Picture(str(path), stat.st_size, stat.st_mtime_ns, size[0], size[1], self.cache_dir)
        return None

    def marquee(self, game: str) -> Optional[Picture]:
        return self.find(game, MARQUEE_KINDS)

    def shot(self, game: str) -> Optional[Picture]:
        return self.find(game, SHOT_KINDS)
