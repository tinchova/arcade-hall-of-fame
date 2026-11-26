"""Nombres puestos a mano a las filas de las tablas.

Algunos juegos no guardan iniciales (por ejemplo, Ms. Pac-Man) y en otros el
jugador puede no haberlas cargado. Ese récord no se puede atribuir desde el
archivo: no suma al ranking y no se muestra (salvo ``--mostrar-sin-iniciales``,
que lo presenta como ``???``) hasta que alguien le pone nombre.

El nombre queda en la base (tabla ``record_names``), asociado al juego, a esa
puntuación exacta y a las iniciales originales de la fila. Si después el récord
cambia, el nuevo queda sin nombre; si la fila baja de puesto (otro la supera),
conserva su nombre.

También sirve para reemplazar las iniciales de una fila que sí las tiene (por
ejemplo, las que el juego propone por defecto). Se guardan las originales
(``original_initials``) y el nombre solo se aplica a la fila de esa puntuación
con esas iniciales; ``remove_name`` las devuelve.

Las entradas de fábrica no se muestran ni se pueden nombrar, y los puestos se
renumeran sin ellas (``storage.visible_positions``): el récord (1º) es la mejor
fila de jugador aunque la fábrica tenga más puntos.

Por defecto se nombra el récord (1º) del juego; ``select_row`` permite elegir
otra fila por puesto (``position``, el que se muestra, sin la fábrica) o por el nombre que se ve hoy
(``current_name``). Límite: dos filas empatadas en puntos con iniciales
originales distintas no se pueden renombrar (la clave es juego y puntuación).

Este módulo no imprime ni lee argumentos: lo usan el comando ``nombrar``, la
página web (``web.py``).
``player_rows`` da la lista para elegir, y ``assign_name`` recibe la
puntuación que vio quien eligió (``expected_score``) para no nombrar por error
una fila que cambió mientras tanto; ``origin`` registra desde dónde se puso.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import HighScoreError
from .storage import Database, player_rows_of, player_top, visible_positions

UNNAMED = "???"
MAX_INITIALS = 12  # igual que un alias (players.MAX_ALIAS): entra en las columnas JUGADOR


class NamingError(HighScoreError):
    """No se puede poner (o quitar) el nombre pedido."""


@dataclass(frozen=True)
class UnnamedRecord:
    game: str
    score_text: str
    observation_id: int
    detected_utc: str  # desde cuándo es la tabla vigente


@dataclass(frozen=True)
class NamedRecord:
    game: str
    score_text: str
    initials: str  # el nombre puesto
    original_initials: Optional[str]  # las que traía el juego, si tenía
    named_utc: str
    origin: str


@dataclass(frozen=True)
class TableRow:
    """Fila de un jugador (no de fábrica) en la tabla vigente de un juego."""
    game: str
    position: int  # puesto que se muestra, renumerado sin las entradas de fábrica
    score_text: str
    name: Optional[str]  # el que se muestra: el puesto a mano o las iniciales del juego
    original: Optional[str]  # iniciales guardadas por el juego
    assigned: bool  # tiene un nombre puesto a mano
    top: bool  # es el récord del juego
    original_position: int = 0  # puesto en la tabla del juego, contando la fábrica


def has_initials(entry) -> bool:
    return bool(entry["initials"] and entry["initials"].strip())


def needs_name(entry) -> bool:
    """Fila de un jugador (no de fábrica) sin iniciales atribuibles."""
    return not entry["factory"] and not has_initials(entry)


def clean_initials(text: str) -> str:
    """Normaliza las iniciales: sin espacios de más y en mayúsculas, como en el arcade."""
    value = " ".join(str(text).split()).upper()
    if not value:
        raise NamingError("las iniciales no pueden estar vacías")
    if len(value) > MAX_INITIALS:
        raise NamingError(f"las iniciales pueden tener hasta {MAX_INITIALS} caracteres")
    if value == UNNAMED or any(unicodedata.category(c).startswith("C") for c in value):
        raise NamingError(f"iniciales no válidas: {value!r}")
    return value


def _original(entry) -> Optional[str]:
    return entry["initials"].strip() if has_initials(entry) else None


def name_applies(row, original: Optional[str]) -> bool:
    """El nombre guardado corresponde a una fila con esas iniciales originales."""
    return row is not None and row["original_initials"] == original


def entry_name(db: Database, game: str, entry) -> Optional[str]:
    """Nombre de la fila: el puesto a mano si lo hay; si no, las iniciales del juego."""
    if entry["factory"]:
        return None
    row = db.record_name(game, entry["score_text"])
    if name_applies(row, _original(entry)):
        return row["initials"]
    return entry["initials"] if has_initials(entry) else None


def _current(db: Database, game: str):
    source = db.source(game)
    if source is None or not source["current_observation_id"]:
        raise NamingError(f"no hay una tabla registrada para {game}")
    observation = db.observation(source["current_observation_id"])
    return observation, db.entries(observation["id"])


def _current_top(db: Database, game: str):
    """Tabla vigente y filas del récord (la mejor fila que no es de fábrica, con empates)."""
    observation, entries = _current(db, game)
    best = player_top(entries)
    if best is None:
        if entries and all(e["factory"] for e in entries):
            raise NamingError(f"{game}: la tabla vigente solo tiene entradas de fábrica")
        raise NamingError(f"{game}: el récord no tiene una puntuación numérica")
    rows = [e for e in player_rows_of(entries) if e["score_num"] == best["score_num"]]
    return observation, entries, rows


def _table_row(db: Database, game: str, entries, entry) -> TableRow:
    original = _original(entry)
    assigned = name_applies(db.record_name(game, entry["score_text"]), original)
    best = player_top(entries)
    top = best is not None and entry["score_num"] == best["score_num"]
    shown = visible_positions(entries).get(entry["position"], entry["position"])
    return TableRow(game, shown, entry["score_text"], entry_name(db, game, entry), original,
                    assigned, top, entry["position"])


def unnamed_records(db: Database) -> List[UnnamedRecord]:
    """Juegos cuyo récord vigente no tiene titular atribuible ni nombre puesto a mano."""
    result = []
    for source in db.sources():
        try:
            observation, _, rows = _current_top(db, source["game"])
        except NamingError:
            continue
        if any(has_initials(e) for e in rows):
            continue
        score = rows[0]["score_text"]
        if db.record_name(source["game"], score) is None:
            result.append(UnnamedRecord(source["game"], score, observation["id"], observation["detected_utc"]))
    return result


def player_rows(db: Database, game: Optional[str] = None) -> List[TableRow]:
    """Todas las filas de jugadores (sin las de fábrica) de las tablas vigentes."""
    result = []
    for source in db.sources():
        if game is not None and source["game"] != game:
            continue
        try:
            observation, entries = _current(db, source["game"])
        except NamingError:
            continue
        for entry in entries:
            if not entry["factory"] and (entry["score_text"] or "").strip():
                result.append(_table_row(db, source["game"], entries, entry))
    return result


def named_records(db: Database) -> List[NamedRecord]:
    """Filas de las tablas vigentes con un nombre puesto a mano."""
    result = []
    for row in player_rows(db):
        if row.assigned:
            stored = db.record_name(row.game, row.score_text)
            result.append(NamedRecord(row.game, row.score_text, row.name or "", row.original,
                                      stored["named_utc"], stored["origin"]))
    return result


def select_row(db: Database, game: str, position: Optional[int] = None, current_name: Optional[str] = None,
               expected_score: Optional[str] = None) -> TableRow:
    """Elige la fila: por puesto, por nombre actual o, sin opciones, el récord (1º).

    El puesto es el que se muestra, renumerado sin las entradas de fábrica.

    ``current_name`` es el nombre que se ve hoy (las iniciales del juego o el
    puesto a mano). Si varias filas lo tienen, hay que indicar el puesto o los
    puntos. ``expected_score`` es la puntuación que vio quien eligió: si no
    coincide, falla.
    """
    expected = expected_score.strip() if expected_score is not None else None
    if position is None and current_name is None:
        observation, entries, rows = _current_top(db, game)
        score = rows[0]["score_text"]
        if expected is not None and expected != score:
            raise NamingError(f"{game}: el récord vigente es {score}, no {expected}")
        originals = sorted({_original(e) or "" for e in rows})
        if len(originals) > 1:
            raise NamingError(f"{game}: el récord vigente ({score}) está empatado entre varias iniciales "
                              f"({', '.join(o or UNNAMED for o in originals)})")
        return _table_row(db, game, entries, rows[0])

    observation, entries = _current(db, game)
    if position is not None:
        shown = visible_positions(entries)
        found = [e for e in player_rows_of(entries) if shown[e["position"]] == position]
        if not found:
            raise NamingError(f"{game}: la tabla vigente no tiene puesto {position}")
        entry = found[0]
        if expected is not None and expected != entry["score_text"]:
            raise NamingError(f"{game}: el puesto {position} tiene {entry['score_text']}, no {expected}")
        if current_name is not None:
            wanted = " ".join(str(current_name).split()).upper()
            if (entry_name(db, game, entry) or "").upper() != wanted:
                raise NamingError(f"{game}: el puesto {position} no está a nombre de {wanted}")
    else:
        wanted = " ".join(str(current_name).split()).upper()
        found = [e for e in entries if not e["factory"] and (entry_name(db, game, e) or "").upper() == wanted
                 and (expected is None or e["score_text"] == expected)]
        if not found:
            extra = f" con {expected} puntos" if expected is not None else ""
            raise NamingError(f"{game}: ninguna fila de la tabla vigente está a nombre de {wanted}{extra}")
        if len(found) > 1:
            places = ", ".join(str(e["position"]) for e in found)
            raise NamingError(f"{game}: hay {len(found)} filas a nombre de {wanted} (puestos {places}); "
                              "indicar --puesto o --puntos")
        entry = found[0]
    if entry["factory"]:
        raise NamingError(f"{game}: la fila {entry['score_text']} es una entrada de fábrica")
    tied = {_original(e) or "" for e in entries if not e["factory"] and e["score_text"] == entry["score_text"]}
    if len(tied) > 1:
        raise NamingError(f"{game}: el puesto {visible_positions(entries)[entry['position']]} ({entry['score_text']}) está empatado con otra "
                          f"fila de iniciales distintas ({', '.join(sorted(o or UNNAMED for o in tied))}); "
                          "no se puede cambiar")
    return _table_row(db, game, entries, entry)


def assign_name(db: Database, game: str, initials: str, now: str, origin: str = "comando",
                expected_score: Optional[str] = None, position: Optional[int] = None,
                current_name: Optional[str] = None) -> TableRow:
    """Pone nombre a una fila de la tabla vigente (por defecto, el récord). Si ya tenía uno, lo reemplaza.

    Si la fila tiene iniciales guardadas por el juego, el nombre las reemplaza
    (para esa puntuación y esas iniciales) y las originales quedan guardadas.
    """
    value = clean_initials(initials)
    row = select_row(db, game, position, current_name, expected_score)
    observation_id = db.source(game)["current_observation_id"]
    db.set_record_name(game, row.score_text, value, observation_id, now, origin, row.original)
    return row


def remove_name(db: Database, game: str, expected_score: Optional[str] = None, position: Optional[int] = None,
                current_name: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """Quita el nombre puesto a una fila de la tabla vigente (por defecto, el récord).

    Devuelve la puntuación y las iniciales originales (None si no tenía).
    """
    row = select_row(db, game, position, current_name, expected_score)
    which = "el récord vigente" if position is None and current_name is None else f"el puesto {row.position}"
    stored = db.record_name(game, row.score_text)
    if stored is None or not db.delete_record_name(game, row.score_text):
        raise NamingError(f"{game}: {which} ({row.score_text}) no tiene nombre puesto")
    return row.score_text, stored["original_initials"]
