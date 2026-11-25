"""Contenido de las pantallas, independiente de Tk (se puede probar sin ventana)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from ..names import GameNames
from ..players import Players
from ..rankings import leaders, player_ranking, recent_records
from ..storage import Database

# Paleta (tokens semánticos). Base tomada de las paletas "Gaming" y
# "Arcade & Retro Game" del skill ui-ux-pro-max; contraste del texto sobre el
# fondo de 4.5:1 o más.
BG = "#0f0f23"        # fondo
SCANLINE = "#13132c"  # líneas de barrido, apenas visibles
CARD = "#1e1c35"      # banda detrás del primer puesto
FRAME = "#4c1d95"     # bordes y sombra del título
TITLE = "#f43f5e"     # título (rosa neón)
SUBTITLE = "#a78bfa"  # subtítulo (violeta)
HEADER = "#3de8ff"    # encabezados de columna (cian)
HEADER_DIM = "#5b9fb0"  # línea de estado (cian apagado, contraste 5:1)
TEXT = "#e2e8f0"      # texto normal
DIM = "#94a3b8"       # texto secundario y entradas de fábrica
ALERT = "#f43f5e"
GOOD = "#22c55e"      # puntajes y titulares
RANK_COLORS = ("#facc15", "#cbd5e1", "#fb923c")  # oro, plata, bronce

ROWS_PER_PAGE = 10

Cell = Tuple[str, str]  # (texto, color)


@dataclass(frozen=True)
class Column:
    label: str
    width: int  # en caracteres
    align: str = "left"  # "left" o "right"


@dataclass
class Screen:
    key: str
    title: str
    subtitle: str
    columns: Sequence[Column]
    rows: List[List[Cell]]
    notes: List[Cell] = field(default_factory=list)
    empty_message: str = ""
    page: str = ""
    highlight_first: bool = True
    status: str = ""
    no_initials: bool = False  # juego que no guarda iniciales  # línea de estado: juegos registrados y último escaneo


def rank_color(position: int) -> str:
    return RANK_COLORS[position - 1] if 1 <= position <= len(RANK_COLORS) else GOOD


def ordinal(position: int) -> str:
    return f"{position}."


def _pages(rows: List[List[Cell]]) -> List[List[List[Cell]]]:
    if not rows:
        return [[]]
    return [rows[i:i + ROWS_PER_PAGE] for i in range(0, len(rows), ROWS_PER_PAGE)]


def local_stamp(utc_text: str) -> str:
    try:
        return datetime.fromisoformat(utc_text).astimezone().strftime("%d/%m %H:%M")
    except ValueError:
        return utc_text


def ranking_screens(db: Database, players: Players, names: GameNames,
                    show_no_initials: bool = False) -> List[Screen]:
    ranking = player_ranking(db, players)
    rows = [
        [(ordinal(r.position), rank_color(r.position)), (r.initials, rank_color(r.position)),
         (str(r.count), TEXT), (", ".join(names.name(g) for g in r.games), DIM)]
        for r in ranking
    ]
    without = [g for g in leaders(db, players) if not g.holders
               and (show_no_initials or g.reason != "el juego no guarda iniciales")]
    notes: List[Cell] = []
    if without:
        if show_no_initials:
            text = f"{len(without)} SIN TITULAR: FABRICA O SIN INICIALES"
        else:
            text = f"{len(without)} {'JUEGO' if len(without) == 1 else 'JUEGOS'} SIN TITULAR: TABLA DE FABRICA"
        notes.append((text, DIM))
    columns = (Column("POS", 4), Column("JUGADOR", 10), Column("PRIMEROS", 8, "right"), Column("JUEGOS", 16))
    pages = _pages(rows)
    return [
        Screen("ranking", "SALON DE LA FAMA", "JUGADORES POR PRIMEROS PUESTOS", columns, page_rows, notes,
               "TODAVIA NADIE TIENE UN PRIMER PUESTO", f"{i}/{len(pages)}" if len(pages) > 1 else "")
        for i, page_rows in enumerate(pages, start=1)
    ]


def records_screen(db: Database, players: Players, names: GameNames, limit: int = ROWS_PER_PAGE) -> Screen:
    rows = []
    for e in recent_records(db, limit, players):
        rows.append([
            (local_stamp(e["detected_utc"]), DIM),
            (names.name(e["game"]), HEADER),
            (e["new_top"], SUBTITLE),
            (", ".join(e["new_holders"]) or "-", GOOD),
        ])
    columns = (Column("FECHA", 11), Column("JUEGO", 13), Column("PUNTOS", 8, "right"), Column("JUGADOR", 7))
    return Screen("records", "ULTIMOS RECORDS", "RECORDS BATIDOS DETECTADOS", columns, rows, [],
                  "TODAVIA NO HAY RECORDS BATIDOS", highlight_first=False)


def game_screen(db: Database, game: str, players: Players, names: GameNames) -> Optional[Screen]:
    source = db.source(game)
    if source is None or not source["current_observation_id"]:
        return None
    entries = db.entries(source["current_observation_id"])
    no_initials = all(e["initials"] is None for e in entries)
    rows = []
    for e in entries[:ROWS_PER_PAGE]:
        position = e["position"]
        if e["factory"]:
            color = DIM
        else:
            color = rank_color(position)
        name = "" if e["initials"] is None else players.name(e["initials"]) if e["initials"].strip() else ""
        rows.append([(ordinal(position), color), (e["score_text"], color), (name, color),
                     ("FABRICA" if e["factory"] else "", DIM)])
    notes: List[Cell] = []
    if no_initials:
        notes.append(("SIN INICIALES: NO SUMA AL RANKING", DIM))
    elif any(e["factory"] for e in entries):
        notes.append(("LA FABRICA NO SUMA AL RANKING", DIM))
    columns = (Column("POS", 4), Column("PUNTOS", 10, "right"), Column("JUGADOR", 13), Column("", 10))
    first_counts = bool(entries) and not entries[0]["factory"] and not no_initials
    return Screen(f"juego:{game}", names.name(game), "TABLA DEL JUEGO", columns, rows, notes, "TABLA VACIA",
                  highlight_first=first_counts, no_initials=no_initials)


def status_line(db: Database, count: int) -> str:
    scan = db.last_scan()
    when = local_stamp(scan["finished_utc"]) if scan is not None else "-"
    return f"{count} JUEGOS  ULTIMO ESCANEO {when}"


def build_screens(db: Database, players: Players, names: Optional[GameNames] = None,
                  games_between_ranking: int = 4, show_no_initials: bool = False) -> List[Screen]:
    """Secuencia de rotación: ranking, récords y juegos, volviendo al ranking cada tanto.

    Los juegos que no guardan iniciales (por ejemplo, Pac-Man) se escanean y se
    guardan igual, pero no se muestran salvo que se pida ``show_no_initials``.
    """
    names = names or GameNames()
    names.set_games(s["game"] for s in db.sources())
    ranking = ranking_screens(db, players, names, show_no_initials)
    sequence: List[Screen] = list(ranking) + [records_screen(db, players, names)]
    games = [g for g in (game_screen(db, s["game"], players, names) for s in db.sources())
             if g is not None and (show_no_initials or not g.no_initials)]
    games.sort(key=lambda screen: screen.title.lower())
    for i, screen in enumerate(games):
        if i and i % games_between_ranking == 0:
            sequence.append(ranking[0])
        sequence.append(screen)
    status = status_line(db, len(games))
    for screen in sequence:
        screen.status = status
    return sequence
