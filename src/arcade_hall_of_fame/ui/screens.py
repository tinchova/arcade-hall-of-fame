"""Contenido de las pantallas, independiente de Tk (se puede probar sin ventana)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from ..names import GameNames
from ..naming import UNNAMED, entry_name
from ..players import Players
from ..rankings import leaders, player_ranking, recent_records
from ..storage import Database

# Paleta (tokens semánticos). Base tomada de las paletas "Gaming" y
# "Arcade & Retro Game" del skill ui-ux-pro-max; contraste del texto sobre el
# fondo de 4.5:1 o más (lo comprueba test_interfaz). El fondo es negro puro
# para que se confunda con los bordes negros de la pantalla; por eso las
# líneas de barrido son del mismo color (no se dibujan).
BG = "#000000"        # fondo
SCANLINE = BG         # líneas de barrido: desactivadas sobre negro puro
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
    status: str = ""  # línea de estado: juegos registrados y último escaneo


def plural(count: int, singular: str, plural_form: str) -> str:
    """``1 JUEGO``, ``2 JUEGOS``: el número con la palabra en singular o plural."""
    return f"{count} {singular if count == 1 else plural_form}"


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
    notes: List[Cell] = []
    unnamed = [g for g in leaders(db, players) if g.unnamed]
    if unnamed and show_no_initials:
        count = len(unnamed)
        notes.append((f"{plural(count, 'RECORD', 'RECORDS')} SIN NOMBRE ({UNNAMED}): NO SUMAN", DIM))
    columns = (Column("POS", 4), Column("JUGADOR", 10), Column("PRIMEROS", 8, "right"), Column("JUEGOS", 16))
    pages = _pages(rows)
    return [
        Screen("ranking", "SALON DE LA FAMA", "JUGADORES POR PRIMEROS PUESTOS", columns, page_rows, notes,
               "TODAVIA NADIE TIENE UN PRIMER PUESTO", f"{i}/{len(pages)}" if len(pages) > 1 else "")
        for i, page_rows in enumerate(pages, start=1)
    ]


def records_screen(db: Database, players: Players, names: GameNames, limit: int = ROWS_PER_PAGE,
                   show_no_initials: bool = False) -> Screen:
    """Últimos récords. Los que no tienen nombre se ocultan (o se muestran como ???)."""
    rows = []
    # Se piden de más por si hay que saltear récords sin nombre.
    for e in recent_records(db, limit * 5, players):
        if e["unnamed"] and not show_no_initials:
            continue
        holders = UNNAMED if e["unnamed"] else ", ".join(e["new_holders"])
        rows.append([
            (local_stamp(e["detected_utc"]), DIM),
            (names.name(e["game"]), HEADER),
            (e["new_top"], SUBTITLE),
            (holders, DIM if e["unnamed"] else GOOD),
        ])
        if len(rows) == limit:
            break
    columns = (Column("FECHA", 11), Column("JUEGO", 13), Column("PUNTOS", 8, "right"), Column("JUGADOR", 7))
    return Screen("records", "ULTIMOS RECORDS", "RECORDS BATIDOS DETECTADOS", columns, rows, [],
                  "TODAVIA NO HAY RECORDS BATIDOS", highlight_first=False)


def game_screen(db: Database, game: str, players: Players, names: GameNames,
                show_no_initials: bool = False) -> Optional[Screen]:
    """Tabla de un juego, o None si no tiene nada para mostrar.

    Las entradas de fábrica no se muestran. Las filas sin iniciales se muestran
    con el nombre puesto a mano (``nombrar``); si no tienen, solo con
    ``show_no_initials`` y como ``???``. Se conserva la posición original.
    """
    source = db.source(game)
    if source is None or not source["current_observation_id"]:
        return None
    observation = db.observation(source["current_observation_id"])
    top = observation["top_score_num"]
    rows = []
    first_counts = False
    any_unnamed = False
    for e in db.entries(observation["id"]):
        if e["factory"]:
            continue
        name = entry_name(db, game, e)
        if name is None and not show_no_initials:
            continue
        if not rows:
            first_counts = name is not None and top is not None and e["score_num"] == top
        position = e["position"]
        if name is None:
            any_unnamed = True
            color, shown = DIM, UNNAMED
        else:
            color, shown = rank_color(position), players.name(name)
        rows.append([(ordinal(position), color), (e["score_text"], color), (shown, color), ("", DIM)])
        if len(rows) == ROWS_PER_PAGE:
            break
    if not rows:
        return None
    notes: List[Cell] = []
    if any_unnamed:
        notes.append((f"{UNNAMED} SIN NOMBRE: NO SUMA AL RANKING", DIM))
    columns = (Column("POS", 4), Column("PUNTOS", 10, "right"), Column("JUGADOR", 13), Column("", 10))
    subtitle = names.detail(game) or "TABLA DEL JUEGO"  # año y fabricante, del DAT de FBNeo
    return Screen(f"juego:{game}", names.name(game), subtitle, columns, rows, notes, "TABLA VACIA",
                  highlight_first=first_counts)


def status_line(db: Database, count: int) -> str:
    scan = db.last_scan()
    when = local_stamp(scan["finished_utc"]) if scan is not None else "-"
    return f"{plural(count, 'JUEGO', 'JUEGOS')}  ULTIMO ESCANEO {when}"


def build_screens(db: Database, players: Players, names: Optional[GameNames] = None,
                  games_between_ranking: int = 4, show_no_initials: bool = False) -> List[Screen]:
    """Secuencia de rotación: ranking, récords y juegos, volviendo al ranking cada tanto.

    No se muestran las entradas de fábrica (un juego que solo tiene esas no
    aparece) ni los récords sin iniciales que todavía no tienen nombre, salvo
    que se pida ``show_no_initials``. Todo queda guardado en la base igual.
    """
    names = names or GameNames()
    names.set_games(s["game"] for s in db.sources())
    ranking = ranking_screens(db, players, names, show_no_initials)
    sequence: List[Screen] = list(ranking) + [records_screen(db, players, names, show_no_initials=show_no_initials)]
    games = [g for g in (game_screen(db, s["game"], players, names, show_no_initials) for s in db.sources())
             if g is not None]
    games.sort(key=lambda screen: screen.title.lower())
    for i, screen in enumerate(games):
        if i and i % games_between_ranking == 0:
            sequence.append(ranking[0])
        sequence.append(screen)
    status = status_line(db, len(games))
    for screen in sequence:
        screen.status = status
    return sequence
