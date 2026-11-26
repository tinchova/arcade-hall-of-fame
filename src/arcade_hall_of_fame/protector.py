"""Imágenes para el protector de pantalla (slideshow de ES-DE con imágenes propias).

Genera un PNG por pantalla en una carpeta. Para no trabajar de más:

* si el estado de los datos (última tabla registrada, juegos, opciones) es el
  mismo que en la generación anterior, no se arma ni se escribe nada;
* si cambió, solo se reescriben las pantallas cuyo contenido cambió, según un
  manifiesto con el hash de cada una.

Cada archivo se escribe con un nombre temporal y se renombra al terminar, para
que ES-DE nunca lea una imagen a medio escribir. Cada pantalla tiene un nombre
fijo (``hof-ranking.png``, ``hof-juego-<zip>.png``...); las imágenes propias
(``hof-*.png``) que ya no corresponden se borran (ver ``generate``) y los
archivos ajenos no se tocan.

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
import time
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
FILLER_SECONDS = 10 * 60  # un sobrante se borra en la primera generación pasado este tiempo
FORMAT_VERSION = 15  # 2: fondo negro, sin fábrica, nombres puestos a mano; 3: singular y opciones;
# 4: columna RECORDS, JUEGOS con +N, bloque arriba y estado abajo, línea base en últimos récords
# 5: regla única de colores (podio, resto gris, puntos blancos, juego celeste), sin banda en la fila 1; 6: plata acerada; 7: subtítulo TOP GLOBAL
# 8: filas del podio enteras en oro, plata y bronce; 9: alias de jugadores y columnas JUGADOR de 12
# 10: destacados con marquee y captura, pantallas mosaico y QR al final
# 11: la fábrica se ignora del todo: puestos renumerados y récord = mejor fila de jugador
# 12: nombres de archivo fijos por pantalla, sin número de orden
# 13: la pantalla del QR solo si hay récords sin nombre, y los nombra
# 14: juegos que guardan solo el máximo: los récords anteriores en la tabla del juego
# 15: las filas ocultas sin nombre no dejan hueco: puestos renumerados
PENDING_FILE = PREFIX + "pendientes.txt"


@dataclass
class ProtectorReport:
    skipped: bool = False
    written: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    filled: List[str] = field(default_factory=list)  # sobrantes nuevos que quedan como relleno


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
    aliases = sorted(db.aliases().items())
    flat = []
    for item in options:
        flat.extend(item if isinstance(item, (list, tuple)) else [item])
    # Para archivos (por ejemplo, el gamelist de ES-DE) cuenta también su fecha:
    # si ES-DE agrega nombres, las imágenes se actualizan.
    files = [(item, Path(item).stat().st_size, Path(item).stat().st_mtime_ns)
             for item in flat if isinstance(item, str) and Path(item).is_file()]
    text = repr((FORMAT_VERSION, tuple(row), accepted, named, tuple(events), aliases, flat, files))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-") or "pantalla"


def file_names(screens: Sequence[Screen]) -> List[str]:
    """Un nombre fijo por pantalla, sin número de orden: ES-DE elige las imágenes al azar."""
    names: List[str] = []
    for screen in screens:
        base = name = f"{PREFIX}{_slug(screen.key)}"
        n = 1
        while f"{name}.png" in names:  # páginas del ranking: hof-ranking, hof-ranking-2...
            n += 1
            name = f"{base}-{n}"
        names.append(f"{name}.png")
    return names


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


def esde_running() -> Optional[bool]:
    """True si ES-DE está abierto, False si no, None si no se puede saber."""
    if sys.platform == "win32":
        return None
    try:
        code = subprocess.run(["pgrep", "-x", "ES-DE" if sys.platform == "darwin" else "es-de"],
                              capture_output=True, timeout=5).returncode
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(code)


def generate(build: Callable[[], Sequence[Screen]], out_dir: Path, width: int, height: int,
             state: str, options: Optional[Dict] = None, esde_running: Optional[bool] = None,
             compact: bool = False, now: Optional[float] = None) -> ProtectorReport:
    """Actualiza la carpeta; ``build`` solo se llama si cambió ``state``.

    ``options`` se guarda en el manifiesto, para que otro comando (por ejemplo,
    ``nombrar``) pueda regenerar las imágenes con las mismas opciones.

    Cada pantalla tiene un nombre fijo (sin número de orden), así que un cambio de
    orden no deja archivos de más. Sobra un archivo cuando una pantalla deja de
    mostrarse (por ejemplo, un juego que deja de ser destacado) y en la migración
    desde los nombres numerados.

    ES-DE arma la lista de imágenes al activar su protector y rota sobre ella
    mientras sigue activo; si una se borra, en su turno muestra negro. Por eso un
    sobrante se borra enseguida solo si ES-DE no está abierto (``esde_running``
    False) o con ``compact``; si no, queda como está (relleno, anotado en el
    manifiesto con la hora) y se borra en la primera generación que ocurra más de
    ``FILLER_SECONDS`` después. El relleno no se reescribe: no repite el ranking.
    """
    now = time.time() if now is None else now
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / MANIFEST
    manifest = _read_manifest(manifest_path)
    previous: Dict[str, str] = manifest.get("archivos", {}) if isinstance(manifest.get("archivos"), dict) else {}
    relleno = manifest.get("relleno") if isinstance(manifest.get("relleno"), dict) else {}
    # Hora en que cada sobrante pasó a ser relleno (en el formato viejo era otra cosa: cuenta desde ahora).
    fillers_before: Dict[str, float] = {n: t for n, t in relleno.items() if isinstance(t, (int, float))}

    def expired(name: str) -> bool:
        return compact or esde_running is False or (name in fillers_before
                                                     and now - fillers_before[name] > FILLER_SECONDS)

    report = ProtectorReport()
    own = [p.name for p in out_dir.iterdir() if p.name.startswith(PREFIX)
           and (p.name.endswith(".png") or p.name.endswith(TEMP_SUFFIX))]
    extra = [n for n in own if n not in previous]
    if (manifest.get("estado") == state and manifest.get("opciones") == options and previous
            and all((out_dir / n).is_file() for n in previous)
            and all(n in fillers_before and not expired(n) for n in extra)):
        report.skipped = True
        return report

    screens = build()
    current: Dict[str, str] = {}
    for name, screen in zip(file_names(screens), screens):
        ops = layout(screen, width, height, "", "")
        digest = hashlib.sha256(repr((width, height, ops)).encode("utf-8")).hexdigest()
        current[name] = digest
        target = out_dir / name
        if previous.get(name) != digest or not target.is_file():
            _write_atomic(target, Raster(width, height).draw(ops).png())
            report.written.append(name)
        else:
            report.unchanged.append(name)

    fillers: Dict[str, float] = {}
    for path in sorted(out_dir.iterdir()):
        own_png = path.name.startswith(PREFIX) and path.name.endswith(".png")
        leftover = path.name.startswith(PREFIX) and path.name.endswith(TEMP_SUFFIX)
        if leftover or (own_png and path.name not in current and expired(path.name)):
            path.unlink()
            report.removed.append(path.name)
        elif own_png and path.name not in current:
            fillers[path.name] = fillers_before.get(path.name, now)
            if path.name not in fillers_before:
                report.filled.append(path.name)
    _write_manifest(manifest_path, {"estado": state, "archivos": current, "opciones": options,
                                    "relleno": fillers})
    return report


def _write_manifest(path: Path, manifest: Dict) -> None:
    _write_atomic(path, json.dumps(manifest, indent=1, sort_keys=True).encode("utf-8"))
