"""Base SQLite local con observaciones, tablas y récords batidos.

Una observación es una tabla leída de un ``.hi`` con contenido distinto al
anterior de esa fuente. Releer un archivo sin cambios no agrega filas.

Los ``.hi`` de juegos que el intérprete no puede leer (sin definición, con
operaciones no soportadas, de otro tamaño...) se anotan en ``unreadable``: se
sabe que hay un récord guardado, pero no cuál. No se guarda ningún dato de su
contenido.

Los récords sin iniciales (juegos que no las guardan, como Ms. Pac-Man, o
partidas en las que no se cargaron) pueden recibir un nombre con el comando
``nombrar``; se guarda en ``record_names``, asociado al juego y a esa puntuación
exacta (ver ``naming.py``).
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SCHEMA_VERSION = 5
APP_NAME = "arcade-hall-of-fame"

SCHEMA = """
CREATE TABLE sources (
    game TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    last_hash TEXT,
    first_seen_utc TEXT NOT NULL,
    last_seen_utc TEXT NOT NULL,
    last_error TEXT,
    current_observation_id INTEGER REFERENCES observations(id)
);
CREATE TABLE observations (
    id INTEGER PRIMARY KEY,
    game TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    detected_utc TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('aceptada', 'pendiente')),
    note TEXT,
    top_score_text TEXT,
    top_score_num REAL,
    interpreter_version TEXT NOT NULL,
    definitions_revision TEXT NOT NULL
);
CREATE TABLE entries (
    observation_id INTEGER NOT NULL REFERENCES observations(id),
    position INTEGER NOT NULL,
    score_text TEXT NOT NULL,
    score_num REAL,
    initials TEXT,
    factory INTEGER NOT NULL CHECK (factory IN (0, 1)),
    PRIMARY KEY (observation_id, position)
);
CREATE TABLE record_events (
    id INTEGER PRIMARY KEY,
    game TEXT NOT NULL,
    observation_id INTEGER NOT NULL REFERENCES observations(id),
    detected_utc TEXT NOT NULL,
    previous_top_text TEXT,
    new_top_text TEXT NOT NULL,
    previous_holders TEXT NOT NULL,
    new_holders TEXT NOT NULL
);
CREATE TABLE scans (
    id INTEGER PRIMARY KEY,
    started_utc TEXT NOT NULL,
    finished_utc TEXT NOT NULL,
    files INTEGER NOT NULL,
    new_observations INTEGER NOT NULL,
    unchanged INTEGER NOT NULL,
    errors INTEGER NOT NULL
);
CREATE INDEX observations_game ON observations(game, id);
CREATE INDEX record_events_time ON record_events(detected_utc, id);
"""

# Agregado en la versión 2 (las bases de la versión 1 se actualizan solas).
SCHEMA_V2 = """
CREATE TABLE unreadable (
    game TEXT PRIMARY KEY,
    file_name TEXT NOT NULL,
    reason TEXT NOT NULL,
    detail TEXT NOT NULL,
    first_seen_utc TEXT NOT NULL,
    last_seen_utc TEXT NOT NULL,
    file_mtime_utc TEXT NOT NULL,
    file_changed_utc TEXT,
    seen_mtime_utc TEXT
);
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Agregado en la versión 3: nombres puestos a mano a récords sin iniciales.
# La clave es (juego, puntuación): si el récord cambia, el nuevo queda sin nombre.
# ``origin`` dice desde dónde se puso ("comando"; más adelante, por ejemplo, "celular").
SCHEMA_V3 = """
CREATE TABLE record_names (
    game TEXT NOT NULL,
    score_text TEXT NOT NULL,
    initials TEXT NOT NULL,
    observation_id INTEGER REFERENCES observations(id),
    named_utc TEXT NOT NULL,
    origin TEXT NOT NULL,
    PRIMARY KEY (game, score_text)
);
"""

# Agregado en la versión 4: iniciales que traía el récord cuando se le cambió el
# nombre (NULL si no tenía). El nombre solo se aplica a filas con esas iniciales.
SCHEMA_V4 = """
ALTER TABLE record_names ADD COLUMN original_initials TEXT
"""

# Agregado en la versión 5: alias de jugadores (iniciales -> nombre para mostrar),
# editables desde la página web. Se suman a los de jugadores.json y, si una
# misma inicial está en los dos, gana el de la base (ver players.py).
SCHEMA_V5 = """
CREATE TABLE player_aliases (
    initials TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    updated_utc TEXT NOT NULL
)
"""

BASELINE_NOTE = "línea base"
NEW_GAME_NOTE = "primer récord de un juego nuevo"

PENDING_SEEN_KEY = "pendientes_vistos_utc"


def player_rows_of(rows: Sequence[Any]) -> List[Any]:
    """Filas de jugadores: sin las entradas de fábrica, que no cuentan para nada."""
    return [r for r in rows if not r["factory"]]


def player_top(rows: Sequence[Any]) -> Optional[Any]:
    """Mejor fila que no es de fábrica (la primera, si hay empate), o None.

    El récord de un juego es esta fila: las entradas de fábrica se ignoran del
    todo, aunque tengan más puntos que los jugadores.
    """
    numeric = [r for r in player_rows_of(rows) if r["score_num"] is not None]
    if not numeric:
        return None
    top = max(r["score_num"] for r in numeric)
    return next(r for r in numeric if r["score_num"] == top)


def visible_positions(rows: Sequence[Any]) -> Dict[int, int]:
    """Puesto original -> puesto que se muestra, renumerado sin las entradas de fábrica."""
    return {r["position"]: i for i, r in enumerate(player_rows_of(rows), start=1)}


def default_data_dir() -> Path:
    """Carpeta de datos del usuario según el sistema (fuera del repositorio)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else home / "AppData" / "Local") / APP_NAME
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else home / ".local" / "share") / APP_NAME


def default_database() -> Path:
    return default_data_dir() / "historial.sqlite3"


def default_players_file() -> Path:
    return default_data_dir() / "jugadores.json"


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION or version < 0:
            raise RuntimeError(f"versión de base {version} no admitida (se espera {SCHEMA_VERSION})")
        if version < SCHEMA_VERSION:
            self._migrate(version)

    def _migrate(self, version: int) -> None:
        """Crea o actualiza el esquema en una sola transacción (todo o nada)."""
        steps = [(1, SCHEMA), (2, SCHEMA_V2), (3, SCHEMA_V3), (4, SCHEMA_V4), (5, SCHEMA_V5)]
        self.conn.execute("BEGIN")
        try:
            for target, script in steps:
                if version < target:
                    for statement in script.split(";"):
                        if statement.strip():
                            self.conn.execute(statement)
            if 0 < version < 3:
                self._backfill_new_game_events()
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def _backfill_new_game_events(self) -> None:
        """Al pasar a la versión 3: el primer récord de un juego que apareció después
        del primer escaneo también cuenta como récord (antes quedaba como línea base)."""
        row = self.conn.execute("SELECT MIN(finished_utc) FROM scans WHERE new_observations > 0").fetchone()
        if not row or row[0] is None:
            return
        candidates = self.conn.execute(
            "SELECT o.* FROM observations o WHERE o.status = 'aceptada' AND o.note = ? AND o.detected_utc > ? "
            "AND o.top_score_num IS NOT NULL "
            "AND NOT EXISTS (SELECT 1 FROM record_events e WHERE e.observation_id = o.id) ORDER BY o.id",
            (BASELINE_NOTE, row[0]),
        ).fetchall()
        for obs in candidates:
            entries = self.entries(obs["id"])
            best = player_top(entries)
            if best is None:
                continue
            top = [e for e in player_rows_of(entries) if e["score_num"] == best["score_num"]]
            holders = sorted({e["initials"].strip() for e in top if e["initials"] and e["initials"].strip()})
            self.conn.execute(
                "INSERT INTO record_events (game, observation_id, detected_utc, previous_top_text, new_top_text, "
                "previous_holders, new_holders) VALUES (?, ?, ?, NULL, ?, '[]', ?)",
                (obs["game"], obs["id"], obs["detected_utc"], best["score_text"], json.dumps(holders)),
            )
            self.conn.execute("UPDATE observations SET note = ? WHERE id = ?", (NEW_GAME_NOTE, obs["id"]))

    def close(self) -> None:
        self.conn.close()

    # --- Consultas ------------------------------------------------------------

    def source(self, game: str) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM sources WHERE game = ?", (game,)).fetchone()

    def sources(self) -> List[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM sources ORDER BY game").fetchall()

    def observation(self, observation_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM observations WHERE id = ?", (observation_id,)).fetchone()

    def entries(self, observation_id: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM entries WHERE observation_id = ? ORDER BY position", (observation_id,)
        ).fetchall()

    def pending(self, game: str) -> Optional[sqlite3.Row]:
        """Última observación pendiente posterior a la tabla vigente, si la hay."""
        source = self.source(game)
        current = source["current_observation_id"] if source else None
        return self.conn.execute(
            "SELECT * FROM observations WHERE game = ? AND status = 'pendiente' AND id > ? "
            "ORDER BY id DESC LIMIT 1",
            (game, current or 0),
        ).fetchone()

    def last_change(self) -> Optional[str]:
        """Hora UTC de la última tabla nueva registrada, o None."""
        row = self.conn.execute("SELECT MAX(detected_utc) FROM observations").fetchone()
        return row[0] if row else None

    def last_scan(self) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()

    def events(self, limit: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM record_events ORDER BY detected_utc DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()

    def has_event(self, game: str, top_text: str) -> bool:
        """Hay un récord batido (o de juego nuevo) registrado con esa puntuación."""
        return self.conn.execute(
            "SELECT 1 FROM record_events WHERE game = ? AND new_top_text = ? LIMIT 1", (game, top_text)
        ).fetchone() is not None

    def first_seen_top(self, game: str, top_text: str) -> Optional[str]:
        """Hora UTC de la primera tabla aceptada del juego cuyo récord (sin contar
        las entradas de fábrica) es esa puntuación, o None."""
        candidates = self.conn.execute(
            "SELECT DISTINCT o.id, o.detected_utc FROM observations o JOIN entries e ON e.observation_id = o.id "
            "WHERE o.game = ? AND o.status = 'aceptada' AND e.score_text = ? AND e.factory = 0 "
            "ORDER BY o.detected_utc, o.id", (game, top_text)
        ).fetchall()
        for row in candidates:
            best = player_top(self.entries(row["id"]))
            if best is not None and best["score_text"] == top_text:
                return row["detected_utc"]
        return None

    def current_top(self, game: str) -> Optional[sqlite3.Row]:
        """Fila del récord de la tabla vigente (sin contar la fábrica), o None."""
        source = self.source(game)
        if source is None or not source["current_observation_id"]:
            return None
        return player_top(self.entries(source["current_observation_id"]))

    def unreadable(self) -> List[sqlite3.Row]:
        """Juegos con un ``.hi`` que no se puede leer, por nombre de juego."""
        return self.conn.execute("SELECT * FROM unreadable ORDER BY game").fetchall()

    def has_observations(self) -> bool:
        return self.conn.execute("SELECT 1 FROM observations LIMIT 1").fetchone() is not None

    def record_name(self, game: str, score_text: str) -> Optional[sqlite3.Row]:
        """Nombre puesto a mano a esa puntuación exacta del juego, si lo hay."""
        return self.conn.execute(
            "SELECT * FROM record_names WHERE game = ? AND score_text = ?", (game, score_text)
        ).fetchone()

    def record_names(self) -> List[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM record_names ORDER BY game, score_text").fetchall()

    def aliases(self) -> Dict[str, str]:
        """Alias de jugadores guardados en la base: iniciales -> nombre para mostrar."""
        rows = self.conn.execute("SELECT initials, display_name FROM player_aliases ORDER BY initials").fetchall()
        return {r["initials"]: r["display_name"] for r in rows}

    def set_alias(self, initials: str, display_name: str, now: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO player_aliases (initials, display_name, updated_utc) VALUES (?, ?, ?) "
                "ON CONFLICT(initials) DO UPDATE SET display_name = excluded.display_name, "
                "updated_utc = excluded.updated_utc", (initials, display_name, now))

    def delete_alias(self, initials: str) -> bool:
        with self.conn:
            cursor = self.conn.execute("DELETE FROM player_aliases WHERE initials = ?", (initials,))
        return cursor.rowcount > 0

    def setting(self, key: str) -> Optional[str]:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    # --- Escrituras (cada una en su propia transacción) --------------------------

    def mark_unreadable(self, game: str, file_name: str, reason: str, detail: str, mtime_utc: str,
                        now: str) -> bool:
        """Anota (o actualiza) un juego que no se puede leer. Devuelve True si es nuevo.

        Si la fecha de modificación del archivo cambió desde la vez anterior, se
        registra cuándo se notó (``file_changed_utc``): probablemente hubo otra partida.
        """
        with self.conn:
            previous = self.conn.execute(
                "SELECT file_mtime_utc FROM unreadable WHERE game = ?", (game,)
            ).fetchone()
            if previous is None:
                self.conn.execute(
                    "INSERT INTO unreadable (game, file_name, reason, detail, first_seen_utc, last_seen_utc, "
                    "file_mtime_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (game, file_name, reason, detail, now, now, mtime_utc),
                )
                return True
            changed = ", file_changed_utc = ?" if previous[0] != mtime_utc else ""
            params: list = [file_name, reason, detail, now, mtime_utc] + ([now] if changed else []) + [game]
            self.conn.execute(
                "UPDATE unreadable SET file_name = ?, reason = ?, detail = ?, last_seen_utc = ?, "
                f"file_mtime_utc = ?{changed} WHERE game = ?",
                params,
            )
            return False

    def mark_unreadable_seen(self, now: str) -> None:
        """Da por vista la lista actual: los nuevos y los modificados dejan de destacarse."""
        with self.conn:
            self.conn.execute("UPDATE unreadable SET seen_mtime_utc = file_mtime_utc")
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (PENDING_SEEN_KEY, now),
            )

    def clear_unreadable(self, game: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM unreadable WHERE game = ?", (game,))

    def set_record_name(self, game: str, score_text: str, initials: str, observation_id: Optional[int],
                        now: str, origin: str, original_initials: Optional[str] = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO record_names (game, score_text, initials, observation_id, named_utc, origin, "
                "original_initials) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(game, score_text) DO UPDATE SET "
                "initials = excluded.initials, observation_id = excluded.observation_id, "
                "named_utc = excluded.named_utc, origin = excluded.origin, "
                "original_initials = excluded.original_initials",
                (game, score_text, initials, observation_id, now, origin, original_initials),
            )

    def delete_record_name(self, game: str, score_text: str) -> bool:
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM record_names WHERE game = ? AND score_text = ?", (game, score_text))
        return cursor.rowcount > 0


    def touch_source(self, game: str, file_name: str, now: str, error: Optional[str]) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO sources (game, file_name, first_seen_utc, last_seen_utc, last_error) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(game) DO UPDATE SET file_name = excluded.file_name, "
                "last_seen_utc = excluded.last_seen_utc, last_error = excluded.last_error",
                (game, file_name, now, now, error),
            )

    def add_observation(
        self,
        game: str,
        file_name: str,
        file_hash: str,
        now: str,
        rows: Sequence[Dict[str, Any]],
        top_text: Optional[str],
        top_num: Optional[float],
        status: str,
        note: Optional[str],
        make_current: bool,
        event: Optional[Dict[str, Any]],
        interpreter_version: str,
        definitions_revision: str,
    ) -> int:
        with self.conn:
            self.conn.execute(
                "INSERT INTO sources (game, file_name, first_seen_utc, last_seen_utc) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(game) DO NOTHING",
                (game, file_name, now, now),
            )
            cursor = self.conn.execute(
                "INSERT INTO observations (game, file_hash, detected_utc, status, note, top_score_text, "
                "top_score_num, interpreter_version, definitions_revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (game, file_hash, now, status, note, top_text, top_num, interpreter_version, definitions_revision),
            )
            observation_id = cursor.lastrowid
            self.conn.executemany(
                "INSERT INTO entries (observation_id, position, score_text, score_num, initials, factory) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (observation_id, r["position"], r["score_text"], r["score_num"], r["initials"], int(r["factory"]))
                    for r in rows
                ],
            )
            if event is not None:
                self.conn.execute(
                    "INSERT INTO record_events (game, observation_id, detected_utc, previous_top_text, "
                    "new_top_text, previous_holders, new_holders) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        game, observation_id, now, event["previous_top"], event["new_top"],
                        json.dumps(event["previous_holders"]), json.dumps(event["new_holders"]),
                    ),
                )
            assignments = "file_name = ?, last_hash = ?, last_seen_utc = ?, last_error = NULL"
            params: list = [file_name, file_hash, now]
            if make_current:
                assignments += ", current_observation_id = ?"
                params.append(observation_id)
            self.conn.execute(f"UPDATE sources SET {assignments} WHERE game = ?", params + [game])
        return observation_id

    def accept(self, game: str, observation_id: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE observations SET status = 'aceptada', note = COALESCE(note || '; ', '') || "
                "'aceptada como nueva línea base' WHERE id = ?",
                (observation_id,),
            )
            self.conn.execute("UPDATE sources SET current_observation_id = ? WHERE game = ?", (observation_id, game))

    def add_scan(self, started: str, finished: str, files: int, new: int, unchanged: int, errors: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO scans (started_utc, finished_utc, files, new_observations, unchanged, errors) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (started, finished, files, new, unchanged, errors),
            )
