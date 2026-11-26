"""Nombres puestos a mano a récords sin iniciales.

Algunos juegos no guardan iniciales (por ejemplo, Ms. Pac-Man) y en otros el
jugador puede no haberlas cargado. Ese récord no se puede atribuir desde el
archivo: no suma al ranking y no se muestra (salvo ``--mostrar-sin-iniciales``,
que lo presenta como ``???``) hasta que alguien le pone nombre.

El nombre queda en la base (tabla ``record_names``), asociado al juego y a esa
puntuación exacta. Si después el récord cambia, el nuevo queda sin nombre.

También sirve para reemplazar las iniciales de un récord que sí las tiene (por
ejemplo, las que el juego propone por defecto). Se guardan las originales
(``original_initials``) y el nombre solo se aplica a la fila de esa puntuación
con esas iniciales; ``remove_name`` las devuelve.

Este módulo no imprime ni lee argumentos: lo usa el comando ``nombrar`` y podrá
usarlo otra interfaz (por ejemplo, una página para el celular) sin cambios.
``unnamed_records`` da la lista para elegir, y ``assign_name`` recibe la
puntuación que vio quien eligió (``expected_score``) para no nombrar por error
un récord que cambió mientras tanto; ``origin`` registra desde dónde se puso.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import HighScoreError
from .storage import Database

UNNAMED = "???"
MAX_INITIALS = 10


class NamingError(HighScoreError):
    """No se puede poner (o quitar) el nombre pedido."""


@dataclass(frozen=True)
class UnnamedRecord:
    game: str
    score_text: str
    observation_id: int
    detected_utc: str  # desde cuándo es la tabla vigente


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


def _current_top(db: Database, game: str):
    source = db.source(game)
    if source is None or not source["current_observation_id"]:
        raise NamingError(f"no hay una tabla registrada para {game}")
    observation = db.observation(source["current_observation_id"])
    top = observation["top_score_num"]
    rows = [e for e in db.entries(observation["id"]) if top is not None and e["score_num"] == top]
    if not rows:
        raise NamingError(f"{game}: el récord no tiene una puntuación numérica")
    return observation, rows


def unnamed_records(db: Database) -> List[UnnamedRecord]:
    """Juegos cuyo récord vigente no tiene titular atribuible ni nombre puesto a mano."""
    result = []
    for source in db.sources():
        try:
            observation, rows = _current_top(db, source["game"])
        except NamingError:
            continue
        if any(not e["factory"] and has_initials(e) for e in rows) or any(e["factory"] for e in rows):
            continue
        if db.record_name(source["game"], observation["top_score_text"]) is None:
            result.append(UnnamedRecord(source["game"], observation["top_score_text"], observation["id"],
                                        observation["detected_utc"]))
    return result


def assign_name(db: Database, game: str, initials: str, now: str, origin: str = "comando",
                expected_score: Optional[str] = None) -> UnnamedRecord:
    """Pone nombre al récord vigente de ``game``. Si ya tenía uno, lo reemplaza.

    Si el récord tiene iniciales guardadas por el juego, el nombre las reemplaza
    (para esa puntuación y esas iniciales) y las originales quedan guardadas.
    """
    value = clean_initials(initials)
    observation, rows = _current_top(db, game)
    score = observation["top_score_text"]
    if expected_score is not None and expected_score.strip() != score:
        raise NamingError(f"{game}: el récord vigente es {score}, no {expected_score.strip()}")
    if any(e["factory"] for e in rows):
        raise NamingError(f"{game}: el récord vigente ({score}) es una entrada de fábrica")
    originals = sorted({_original(e) or "" for e in rows})
    if len(originals) > 1:
        raise NamingError(f"{game}: el récord vigente ({score}) está empatado entre varias iniciales "
                          f"({', '.join(o or UNNAMED for o in originals)})")
    db.set_record_name(game, score, value, observation["id"], now, origin, originals[0] or None)
    return UnnamedRecord(game, score, observation["id"], observation["detected_utc"])


def remove_name(db: Database, game: str) -> Tuple[str, Optional[str]]:
    """Quita el nombre del récord vigente de ``game``.

    Devuelve la puntuación y las iniciales originales (None si no tenía).
    """
    observation, _rows = _current_top(db, game)
    score = observation["top_score_text"]
    row = db.record_name(game, score)
    if row is None or not db.delete_record_name(game, score):
        raise NamingError(f"{game}: el récord vigente ({score}) no tiene nombre puesto")
    return score, row["original_initials"]
