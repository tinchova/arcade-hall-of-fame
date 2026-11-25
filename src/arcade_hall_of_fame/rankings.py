"""Consultas de clasificación sobre la base SQLite.

Reglas (docs/REQUISITOS.md):

* El primer puesto de un juego es la puntuación máxima de su tabla vigente.
* Si varias iniciales empatan en ese máximo, cada una recibe el juego.
* Entradas de fábrica, iniciales vacías y juegos sin iniciales no dan crédito.
* La clasificación general cuenta juegos, no suma puntos.
* ``jugadores.json`` puede agrupar varias iniciales de una persona; cada
  persona cuenta como máximo una vez por juego.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .players import Players
from .storage import Database


@dataclass(frozen=True)
class GameLeader:
    game: str
    top_score: Optional[str]
    holders: Tuple[str, ...]
    reason: str  # "" si hay titular; si no, por qué no cuenta


@dataclass(frozen=True)
class PlayerRank:
    position: int
    initials: str
    count: int
    games: Tuple[str, ...]


def leaders(db: Database, players: Optional[Players] = None) -> List[GameLeader]:
    players = players or Players()
    result = []
    for source in db.sources():
        if not source["current_observation_id"]:
            continue
        observation = db.observation(source["current_observation_id"])
        rows = db.entries(observation["id"])
        top = observation["top_score_num"]
        top_rows = [r for r in rows if top is not None and r["score_num"] == top]
        holders = tuple(players.names(
            r["initials"] for r in top_rows
            if r["initials"] and r["initials"].strip() and not r["factory"]
        ))
        reason = ""
        if not holders:
            if top is None:
                reason = "puntuación no numérica"
            elif all(r["initials"] is None for r in rows):
                reason = "el juego no guarda iniciales"
            elif any(r["factory"] for r in top_rows):
                reason = "el máximo es una entrada de fábrica"
            else:
                reason = "el máximo no tiene iniciales"
        result.append(GameLeader(source["game"], observation["top_score_text"], holders, reason))
    return result


def player_ranking(db: Database, players: Optional[Players] = None) -> List[PlayerRank]:
    games: Dict[str, List[str]] = {}
    for leader in leaders(db, players):
        for initials in leader.holders:
            games.setdefault(initials, []).append(leader.game)
    ordered = sorted(games.items(), key=lambda item: (-len(item[1]), item[0]))
    ranking = []
    previous_count, position = None, 0
    for index, (initials, owned) in enumerate(ordered, start=1):
        if len(owned) != previous_count:
            position, previous_count = index, len(owned)
        ranking.append(PlayerRank(position, initials, len(owned), tuple(sorted(owned))))
    return ranking


def recent_records(db: Database, limit: int = 10, players: Optional[Players] = None) -> List[Dict]:
    players = players or Players()
    return [
        {
            "game": e["game"],
            "detected_utc": e["detected_utc"],
            "previous_top": e["previous_top_text"],
            "new_top": e["new_top_text"],
            "previous_holders": players.names(json.loads(e["previous_holders"])),
            "new_holders": players.names(json.loads(e["new_holders"])),
        }
        for e in db.events(limit)
    ]
