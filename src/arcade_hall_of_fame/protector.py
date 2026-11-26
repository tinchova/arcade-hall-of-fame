"""Imágenes para el protector de pantalla (slideshow de ES-DE con imágenes propias).

Genera un PNG por pantalla en una carpeta. Para no trabajar de más:

* si el estado de los datos (última tabla registrada, juegos, opciones) es el
  mismo que en la generación anterior, no se arma ni se escribe nada;
* si cambió, solo se reescriben las pantallas cuyo contenido cambió, según un
  manifiesto con el hash de cada una.

Cada archivo se escribe con un nombre temporal y se renombra al terminar, para
que ES-DE nunca lea una imagen a medio escribir. Se borran las imágenes propias
(``hof-*.png``) que ya no corresponden; los archivos ajenos no se tocan.

Junto a las imágenes queda ``hof-pendientes.txt``, con los juegos que tienen un
récord guardado que todavía no se puede leer (ver el comando ``pendientes``), y
los récords sin iniciales a los que falta ponerles nombre (``sin-nombre``).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Sequence

from .storage import Database
from .ui.layout import layout
from .ui.raster import Raster
from .ui.screens import Screen

PREFIX = "hof-"
MANIFEST = ".hof-protector.json"
TEMP_SUFFIX = ".part"
FORMAT_VERSION = 2  # 2: fondo negro, sin fábrica, nombres puestos a mano
PENDING_FILE = PREFIX + "pendientes.txt"


@dataclass
class ProtectorReport:
    skipped: bool = False
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)


def data_state(db: Database, options) -> str:
    """Resumen de todo lo que puede cambiar las imágenes, salvo el paso del tiempo."""
    row = db.conn.execute(
        "SELECT COALESCE(MAX(id), 0), COUNT(*) FROM observations"
    ).fetchone()
    accepted = db.conn.execute(
        "SELECT GROUP_CONCAT(game || ':' || COALESCE(current_observation_id, ''), ',') FROM "
        "(SELECT game, current_observation_id FROM sources ORDER BY game)"
    ).fetchone()[0]
    named = db.conn.execute(
        "SELECT GROUP_CONCAT(game || ':' || score_text || ':' || initials, ',') FROM "
        "(SELECT game, score_text, initials FROM record_names ORDER BY game, score_text)"
    ).fetchone()[0]
    events = db.conn.execute("SELECT COALESCE(MAX(id), 0), COUNT(*) FROM record_events").fetchone()
    flat = []
    for item in options:
        flat.extend(item if isinstance(item, (list, tuple)) else [item])
    # Para archivos (por ejemplo, el gamelist de ES-DE) cuenta también su fecha:
    # si ES-DE agrega nombres, las imágenes se actualizan.
    files = [(item, Path(item).stat().st_size, Path(item).stat().st_mtime_ns)
             for item in flat if isinstance(item, str) and Path(item).is_file()]
    text = repr((FORMAT_VERSION, tuple(row), accepted, named, tuple(events), flat, files))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-") or "pantalla"


def file_names(screens: Sequence[Screen]) -> List[str]:
    return [f"{PREFIX}{i:03d}-{_slug(s.key)}.png" for i, s in enumerate(screens, start=1)]


def _write_atomic(path: Path, data: bytes) -> None:
    temp = path.with_name(path.name + TEMP_SUFFIX)
    with open(temp, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def write_text_if_changed(path: Path, text: str) -> bool:
    """Escribe ``text`` (UTF-8) solo si difiere del contenido actual. Devuelve True si escribió."""
    data = text.encode("utf-8")
    try:
        if path.read_bytes() == data:
            return False
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, data)
    return True


def _read_manifest(path: Path) -> Dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def generate(build: Callable[[], Sequence[Screen]], out_dir: Path, width: int, height: int,
             state: str) -> ProtectorReport:
    """Actualiza la carpeta; ``build`` solo se llama si cambió ``state``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / MANIFEST
    manifest = _read_manifest(manifest_path)
    previous: Dict[str, str] = manifest.get("archivos", {}) if isinstance(manifest.get("archivos"), dict) else {}
    report = ProtectorReport()
    if manifest.get("estado") == state and previous and all((out_dir / n).is_file() for n in previous):
        report.skipped = True
        return report

    screens = build()
    current: Dict[str, str] = {}
    for name, screen in zip(file_names(screens), screens):
        ops = layout(screen, width, height, "", "")
        digest = hashlib.sha256(repr((width, height, ops)).encode("utf-8")).hexdigest()
        current[name] = digest
        target = out_dir / name
        if previous.get(name) == digest and target.is_file():
            report.unchanged.append(name)
            continue
        _write_atomic(target, Raster(width, height).draw(ops).png())
        report.written.append(name)

    for path in out_dir.iterdir():
        own_png = path.name.startswith(PREFIX) and path.name.endswith(".png")
        leftover = path.name.startswith(PREFIX) and path.name.endswith(TEMP_SUFFIX)
        if (own_png and path.name not in current) or leftover:
            path.unlink()
            report.removed.append(path.name)
    _write_atomic(manifest_path, json.dumps({"estado": state, "archivos": current}, indent=1,
                                            sort_keys=True).encode("utf-8"))
    return report
