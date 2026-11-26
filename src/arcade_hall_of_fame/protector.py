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
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from .storage import Database
from .ui.layout import layout
from .ui.raster import Raster
from .ui.screens import Screen

PREFIX = "hof-"
MANIFEST = ".hof-protector.json"
TEMP_SUFFIX = ".part"
FORMAT_VERSION = 7  # 2: fondo negro, sin fábrica, nombres puestos a mano; 3: singular y opciones;
# 4: columna RECORDS, JUEGOS con +N, bloque arriba y estado abajo, línea base en últimos récords
# 5: regla única de colores (podio, resto gris, puntos blancos, juego celeste), sin banda en la fila 1; 6: plata acerada; 7: subtítulo TOP GLOBAL
PENDING_FILE = PREFIX + "pendientes.txt"


@dataclass
class ProtectorReport:
    skipped: bool = False
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    filled: List[str] = field(default_factory=list)  # sobrantes reescritos como relleno


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


def read_options(out_dir: Path) -> Optional[Dict]:
    """Opciones con que se generó la carpeta la última vez (para regenerarla igual), o None."""
    options = _read_manifest(Path(out_dir) / MANIFEST).get("opciones")
    return options if isinstance(options, dict) else None


def boot_id() -> Optional[str]:
    """Identifica el arranque actual del sistema (macOS y Linux); None si no se sabe."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True,
                                 timeout=5, check=True).stdout
            match = re.search(r"sec = (\d+)", out)
            return match.group(1) if match else None
        if sys.platform.startswith("linux"):
            return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip() or None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def generate(build: Callable[[], Sequence[Screen]], out_dir: Path, width: int, height: int,
             state: str, options: Optional[Dict] = None, boot: Optional[str] = None,
             compact: bool = False) -> ProtectorReport:
    """Actualiza la carpeta; ``build`` solo se llama si cambió ``state``.

    ``options`` se guarda en el manifiesto, para que otro comando (por ejemplo,
    ``nombrar``) pueda regenerar las imágenes con las mismas opciones.

    ES-DE arma la lista de imágenes al activar su protector y rota sobre ella
    mientras sigue activo; si una se borra, en su turno muestra negro. Por eso
    las imágenes propias que sobran (menos pantallas o pantallas renumeradas)
    no se borran: se reescriben como copia de la primera pantalla (el ranking)
    y quedan anotadas como relleno en el manifiesto. Se borran solo al compactar:
    con ``compact`` o en la primera generación después de un arranque del sistema
    (``boot`` distinto del anotado), cuando ES-DE todavía no armó su lista.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / MANIFEST
    manifest = _read_manifest(manifest_path)
    previous: Dict[str, str] = manifest.get("archivos", {}) if isinstance(manifest.get("archivos"), dict) else {}
    fillers_before: Dict[str, str] = manifest.get("relleno", {}) if isinstance(manifest.get("relleno"), dict) else {}
    compact = compact or (boot is not None and manifest.get("arranque") != boot)
    report = ProtectorReport()
    if (manifest.get("estado") == state and manifest.get("opciones") == options and previous
            and all((out_dir / n).is_file() for n in list(previous) + list(fillers_before))
            and not (compact and fillers_before)):
        report.skipped = True
        if boot is not None and manifest.get("arranque") != boot:
            manifest["arranque"] = boot
            _write_manifest(manifest_path, manifest)
        return report

    screens = build()
    current: Dict[str, str] = {}
    first_png: Optional[bytes] = None
    first_digest = ""
    for index, (name, screen) in enumerate(zip(file_names(screens), screens)):
        ops = layout(screen, width, height, "", "")
        digest = hashlib.sha256(repr((width, height, ops)).encode("utf-8")).hexdigest()
        current[name] = digest
        target = out_dir / name
        png = None
        if previous.get(name) != digest or not target.is_file():
            png = Raster(width, height).draw(ops).png()
            _write_atomic(target, png)
            report.written.append(name)
        else:
            report.unchanged.append(name)
        if index == 0:
            first_digest = digest
            first_png = png if png is not None else target.read_bytes()

    fillers: Dict[str, str] = {}
    for path in sorted(out_dir.iterdir()):
        own_png = path.name.startswith(PREFIX) and path.name.endswith(".png")
        leftover = path.name.startswith(PREFIX) and path.name.endswith(TEMP_SUFFIX)
        if leftover or (own_png and path.name not in current and (compact or first_png is None)):
            path.unlink()
            report.removed.append(path.name)
        elif own_png and path.name not in current:
            fillers[path.name] = first_digest
            if fillers_before.get(path.name) != first_digest:
                _write_atomic(path, first_png)
                report.filled.append(path.name)
    _write_manifest(manifest_path, {"estado": state, "archivos": current, "opciones": options,
                                    "relleno": fillers, "arranque": boot})
    return report


def _write_manifest(path: Path, manifest: Dict) -> None:
    _write_atomic(path, json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"))
