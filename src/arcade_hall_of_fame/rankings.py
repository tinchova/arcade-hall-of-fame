"""Consultas de clasificación sobre la base SQLite.

Reglas (docs/REQUISITOS.md):

* Las entradas de fábrica se ignoran del todo: el primer puesto de un juego es
  la mejor fila que no es de fábrica de su tabla vigente, aunque la fábrica
  tenga más puntos. Un juego que solo tiene entradas de fábrica no tiene récord.
* Si varias iniciales empatan en ese máximo, cada una recibe el juego.
* Un máximo sin iniciales (juegos que no las guardan o iniciales vacías) no da
  crédito hasta que se le pone nombre con ``nombrar`` (ver ``naming.py``).
* La clasificación general cuenta juegos, no suma puntos.
* ``jugadores.json`` puede agrupar varias iniciales de una persona; cada
  persona cuenta como máximo una vez por juego.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .naming import entry_name, needs_name
from .players import Players, name_key
from .storage import Database, player_rows_of, player_top


@dataclass(frozen=True)
class GameLeader:
    game: str
    top_score: Optional[str]
    holders: Tuple[str, ...]
    reason: str  # "" si hay titular; si no, por qué no cuenta
    unnamed: bool = False  # el máximo es de un jugador, pero no tiene iniciales ni nombre


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
        rows = db.entries(source["current_observation_id"])
        best = player_top(rows)
        top_rows = [r for r in player_rows_of(rows) if best is not None and r["score_num"] == best["score_num"]]
        names = [entry_name(db, source["game"], r) for r in top_rows]
        holders = tuple(players.names(n for n in names if n))
        unnamed = not holders and any(needs_name(r) for r in top_rows)
        reason = ""
        if not holders:
            if best is None and rows and all(r["factory"] for r in rows):
                reason = "solo tiene entradas de fábrica"
            elif best is None:
                reason = "puntuación no numérica"
            elif all(r["initials"] is None for r in rows):
                reason = "el juego no guarda iniciales; falta ponerle nombre"
            else:
                reason = "el máximo no tiene iniciales; falta ponerle nombre"
        result.append(GameLeader(source["game"], best["score_text"] if best is not None else None, holders,
                                 reason, unnamed))
    return result


def player_ranking(db: Database, players: Optional[Players] = None) -> List[PlayerRank]:
    # Se agrupa por el nombre final que se muestra (nombre puesto > alias > iniciales),
    # sin distinguir mayúsculas ni espacios de más: TINCHOVA puesto a mano en un juego
    # y TCH con alias TINCHOVA en otro son la misma fila del ranking.
    games: Dict[str, List[str]] = {}
    shown: Dict[str, str] = {}
    for leader in leaders(db, players):
        for initials in leader.holders:
            key = name_key(initials)
            shown.setdefault(key, initials)
            if leader.game not in games.setdefault(key, []):
                games[key].append(leader.game)
    games = {shown[k]: v for k, v in games.items()}
    ordered = sorted(games.items(), key=lambda item: (-len(item[1]), item[0]))
    ranking = []
    previous_count, position = None, 0
    for index, (initials, owned) in enumerate(ordered, start=1):
        if len(owned) != previous_count:
            position, previous_count = index, len(owned)
        ranking.append(PlayerRank(position, initials, len(owned), tuple(sorted(owned))))
    return ranking


def _with_name(named, holders: List[str]) -> List[str]:
    """Titulares de un evento con el nombre puesto a mano, si corresponde a esas iniciales."""
    if named is None:
        return holders
    original = named["original_initials"]
    if (original is None and not holders) or (original is not None and holders == [original]):
        return [named["initials"]]
    return holders


def recent_records(db: Database, limit: int = 10, players: Optional[Players] = None,
                   include_baseline: bool = True) -> List[Dict]:
    """Últimos récords: batidos, primeros récords de juegos nuevos y, con
    ``include_baseline``, los récords vigentes de la línea base que tienen titular.

    Si el récord no tenía iniciales (o se le cambiaron) y después se le puso
    nombre, se muestra ese nombre. ``unnamed`` indica que el nuevo récord sigue
    sin titular. Los de la línea base (``baseline``) llevan la fecha en que se
    detectó por primera vez esa puntuación; los juegos que solo tienen fábrica y
    los récords sin nombre no se incluyen.
    """
    players = players or Players()
    result = []
    for e in db.events(limit):
        previous = list(json.loads(e["previous_holders"]))
        new = list(json.loads(e["new_holders"]))
        if e["previous_top_text"] is not None:
            previous = _with_name(db.record_name(e["game"], e["previous_top_text"]), previous)
        new = _with_name(db.record_name(e["game"], e["new_top_text"]), new)
        result.append({
            "game": e["game"],
            "detected_utc": e["detected_utc"],
            "previous_top": e["previous_top_text"],
            "new_top": e["new_top_text"],
            "previous_holders": players.names(previous),
            "new_holders": players.names(new),
            "unnamed": not new,
            "baseline": False,
        })
    if include_baseline:
        result.extend(_baseline_records(db, players))
        result.sort(key=lambda r: r["detected_utc"], reverse=True)
    return result[:limit]


def _baseline_records(db: Database, players: Players) -> List[Dict]:
    """Récords vigentes con titular que no salieron de un récord batido (los de la línea base)."""
    result = []
    for leader in leaders(db, players):
        if not leader.holders or leader.top_score is None:
            continue
        if db.has_event(leader.game, leader.top_score):
            continue
        first = db.first_seen_top(leader.game, leader.top_score)
        if first is None:
            continue
        result.append({
            "game": leader.game,
            "detected_utc": first,
            "previous_top": None,
            "new_top": leader.top_score,
            "previous_holders": [],
            "new_holders": list(leader.holders),
            "unnamed": False,
            "baseline": True,
        })
    return result
