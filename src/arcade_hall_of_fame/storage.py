"""Base SQLite local con observaciones, tablas y récords batidos.

Una observación es una tabla leída de un ``.hi`` con contenido distinto al
anterior de esa fuente. Releer un archivo sin cambios no agrega filas.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SCHEMA_VERSION = 1
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
        if version == 0:
            with self.conn:
                self.conn.executescript(SCHEMA)
                self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        elif version != SCHEMA_VERSION:
            raise RuntimeError(f"versión de base {version} no admitida (se espera {SCHEMA_VERSION})")

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

    def last_scan(self) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM scans ORDER BY id DESC LIMIT 1").fetchone()

    def events(self, limit: int) -> List[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM record_events ORDER BY detected_utc DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()

    # --- Escrituras (cada una en su propia transacción) --------------------------

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
