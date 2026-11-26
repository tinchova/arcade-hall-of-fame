"""Escaneo de la carpeta de partidas de FBNeo y registro en SQLite.

Los archivos se abren solo en modo ``rb``. Cada ``.hi`` se lee dos veces y se
comprueban tamaño y fecha de modificación antes y después, para descartar
lecturas a medio escribir.

Si el juego no se puede leer (no hay definición, usa operaciones no soportadas o
el archivo no coincide con ella), no es un error pasajero: se anota en la base
como récord sin leer, con el motivo y la fecha de modificación del archivo, y se
lista con el comando ``pendientes``.

El primer escaneo (base sin tablas) es la línea base y no anuncia récords. Un
juego que aparece después (un ``.hi`` nuevo) sí cuenta su primer récord en
"últimos récords", salvo que solo tenga entradas de fábrica.

Las entradas de fábrica no cuentan para los récords: el récord de un juego es
su mejor fila de jugador (``storage.player_top``). Un récord real que no supera
a la fábrica igual es récord si supera al real anterior. El máximo de la tabla
entera (con fábrica) solo se usa para detectar tablas que bajaron (pendientes).
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from . import __version__
from .hi2txt import MAX_FILE_SIZE, DefinitionLibrary, decode
from .hi2txt.defaults import FactoryTables
from .hi2txt.formats import render, to_number
from .models import (DefinitionError, FormatError, HighScoreError, IncompatibleFile, MissingDefinition,
                     SourceReadError, UnsupportedDefinition)
from .reader import read_source
from .storage import BASELINE_NOTE, NEW_GAME_NOTE, Database, player_top

LOWER_TOP_NOTE = "el máximo bajó: posible reinicio o restauración; no reemplaza la tabla vigente"

REASON_NO_DEFINITION = "sin definición en hi2txt-xml"
REASON_UNSUPPORTED = "definición con operaciones no soportadas"
REASON_DEFINITION_ERROR = "definición con errores"
REASON_INCOMPATIBLE = "el archivo no coincide con la definición"
REASON_NOT_IN_HISCORE_DAT = "no figura en hiscore.dat"


class NotInHiscoreDat(IncompatibleFile):
    """El juego no tiene entrada en el hiscore.dat indicado."""


def unreadable_reason(exc: HighScoreError) -> Optional[Tuple[str, str]]:
    """(motivo, detalle) si el error indica que el juego no se puede leer; si no, None.

    Los errores de acceso o de datos (archivo a medio escribir, tabla vacía...)
    no cuentan: pueden resolverse solos en el próximo escaneo.
    """
    if isinstance(exc, MissingDefinition):
        return REASON_NO_DEFINITION, ""
    if isinstance(exc, UnsupportedDefinition):
        return REASON_UNSUPPORTED, ", ".join(exc.features)
    if isinstance(exc, NotInHiscoreDat):
        return REASON_NOT_IN_HISCORE_DAT, ""
    if isinstance(exc, IncompatibleFile):
        return REASON_INCOMPATIBLE, str(exc)
    if isinstance(exc, DefinitionError):
        return REASON_DEFINITION_ERROR, str(exc)
    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class ScanReport:
    files: int = 0
    new_observations: List[str] = field(default_factory=list)
    unchanged: List[str] = field(default_factory=list)
    pending: List[str] = field(default_factory=list)
    records: List[Tuple[str, str, str, List[str]]] = field(default_factory=list)
    errors: List[Tuple[str, str]] = field(default_factory=list)
    # Juegos con récord guardado que no se puede leer: (juego, motivo).
    unreadable: List[Tuple[str, str]] = field(default_factory=list)
    new_unreadable: List[str] = field(default_factory=list)


def read_stable(path: Path) -> bytes:
    """Lee el archivo dos veces; falla si cambia mientras se lee."""
    before = os.stat(path)
    first = read_source(path, MAX_FILE_SIZE)
    second = read_source(path, MAX_FILE_SIZE)
    after = os.stat(path)
    if first != second or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise SourceReadError(f"{path.name!r} cambió durante la lectura; se reintentará en el próximo escaneo")
    return first


def _number(value) -> Optional[float]:
    try:
        return float(to_number(value))
    except FormatError:
        return None


def _holders(rows: List[Dict], best) -> List[str]:
    """Iniciales atribuibles que tienen el récord ``best`` (sin fábrica, sin vacías)."""
    if best is None:
        return []
    top = best["score_num"]
    return sorted({
        r["initials"].strip() for r in rows
        if r["score_num"] == top and r["initials"] and r["initials"].strip() and not r["factory"]
    })


def normalize_rows(result, factory) -> List[Dict]:
    rows = []
    for row in result.score_rows():
        score_text = render(row.score).strip()
        initials = None if row.initials is None else render(row.initials)
        rows.append({
            "position": row.position,
            "score_text": score_text,
            "score_num": _number(row.score),
            "initials": initials,
            "factory": (score_text, initials or "") in factory,
        })
    return rows


def scan(
    folder: Path,
    db: Database,
    library: DefinitionLibrary,
    factory: FactoryTables,
    definitions_revision: str,
    regions: Optional[Dict[str, tuple]] = None,
    now: Callable[[], str] = utc_now,
) -> ScanReport:
    folder = Path(folder)
    if not folder.is_dir():
        raise SourceReadError(f"no existe la carpeta de partidas {folder.name!r}")
    try:
        Path(db.path).resolve().relative_to(folder.resolve())
    except ValueError:
        pass
    else:
        raise SourceReadError("la base de datos no puede estar dentro de la carpeta de partidas")

    report = ScanReport()
    started = now()
    baseline = not db.has_observations()
    for path in sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".hi"):
        report.files += 1
        game = path.stem
        stamp = now()
        mtime_utc = None
        try:
            mtime_utc = datetime.fromtimestamp(os.stat(path).st_mtime, timezone.utc).isoformat(timespec="seconds")
            data = read_stable(path)
            file_hash = hashlib.sha256(data).hexdigest()
            source = db.source(game)
            if source is not None and source["last_hash"] == file_hash and source["last_error"] is None:
                db.touch_source(game, path.name, stamp, None)
                report.unchanged.append(game)
                continue
            definition = library.load(game)
            game_regions = (regions or {}).get(game)
            if regions is not None and game_regions is None:
                raise NotInHiscoreDat(f"{game}: no figura en hiscore.dat")
            result = decode(definition, data, file_name=path.name, regions=game_regions)
            rows = normalize_rows(result, factory.rows(game))
            if not rows:
                raise FormatError(f"{game}: la tabla está vacía")
        except HighScoreError as exc:
            db.touch_source(game, path.name, stamp, str(exc))
            reason = unreadable_reason(exc)
            if reason is None or mtime_utc is None:
                report.errors.append((game, str(exc)))
            else:
                if db.mark_unreadable(game, path.name, reason[0], reason[1], mtime_utc, stamp):
                    report.new_unreadable.append(game)
                report.unreadable.append((game, reason[0]))
            continue
        _record(db, game, path.name, file_hash, rows, stamp, definitions_revision, report, baseline)
    db.add_scan(started, now(), report.files, len(report.new_observations), len(report.unchanged), len(report.errors))
    return report


def _record(db: Database, game, file_name, file_hash, rows, stamp, revision, report: ScanReport,
            baseline: bool = False) -> None:
    numbers = [r["score_num"] for r in rows if r["score_num"] is not None]
    top_num = max(numbers) if numbers else None
    top_text = next((r["score_text"] for r in rows if r["score_num"] == top_num), None) if numbers else None

    source = db.source(game)
    current = db.observation(source["current_observation_id"]) if source and source["current_observation_id"] else None
    status, note, make_current, event = "aceptada", None, True, None
    best = player_top(rows)
    if current is None:
        note = BASELINE_NOTE if baseline else NEW_GAME_NOTE
        if not baseline and best is not None:
            event = {"previous_top": None, "new_top": best["score_text"], "previous_holders": [],
                     "new_holders": _holders(rows, best)}
    else:
        previous_rows = [dict(r) for r in db.entries(current["id"])]
        previous = player_top(previous_rows)
        lower_table = top_num is not None and current["top_score_num"] is not None and top_num < current["top_score_num"]
        # También baja si se pierde el récord de un jugador aunque la fábrica siga arriba.
        lower_player = previous is not None and (best is None or best["score_num"] < previous["score_num"])
        if lower_table or lower_player:
            status, note, make_current = "pendiente", LOWER_TOP_NOTE, False
        elif best is not None and (previous is None or best["score_num"] > previous["score_num"]):
            event = {
                "previous_top": previous["score_text"] if previous is not None else None,
                "new_top": best["score_text"],
                "previous_holders": _holders(previous_rows, previous),
                "new_holders": _holders(rows, best),
            }
    db.add_observation(game, file_name, file_hash, stamp, rows, top_text, top_num, status, note,
                       make_current, event, __version__, revision)
    db.clear_unreadable(game)
    report.new_observations.append(game)
    if status == "pendiente":
        report.pending.append(game)
    if event is not None:
        report.records.append((game, event["previous_top"], event["new_top"], event["new_holders"]))
