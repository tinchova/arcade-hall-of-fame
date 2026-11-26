"""Contenido de las pantallas, independiente de Tk (se puede probar sin ventana)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from . import pixelfont as pf
from ..names import GameNames
from ..naming import UNNAMED, entry_name
from ..players import Players
from ..rankings import leaders, player_ranking, recent_records
from ..storage import Database

# Paleta: el único lugar donde se definen colores. Base tomada de las paletas
# "Gaming" y "Arcade & Retro Game" del skill ui-ux-pro-max; todo el texto tiene
# contraste de 4.5:1 o más sobre el fondo (lo comprueba test_interfaz). El fondo
# es negro puro para que se confunda con los bordes negros de la pantalla; por
# eso las líneas de barrido son del mismo color (no se dibujan).
#
# Regla única, igual en la ventana y en las imágenes del protector:
# * tablas con posiciones: las filas del 1º, 2º y 3º van enteras en ORO, PLATA y
#   BRONCE (posición, jugador, puntos o récords, juegos y nota); del 4º en adelante
#   posición y jugador RESTO, puntos PUNTOS (blanco) y juego JUEGO (celeste);
# * últimos récords: jugador RESTO, fecha FECHA, juego JUEGO y puntos PUNTOS.
BG = "#000000"        # fondo
SCANLINE = BG         # líneas de barrido: desactivadas sobre negro puro
FRAME = "#4c1d95"     # bordes y sombra del título
TITLE = "#f43f5e"     # título (rosa neón)
SUBTITLE = "#a78bfa"  # subtítulo (violeta)
HEADER = "#3de8ff"    # encabezados de columna (celeste)
HEADER_DIM = "#5b9fb0"  # línea de estado (celeste apagado)
ORO = "#facc15"       # 1º puesto
PLATA = "#b8cce6"     # 2º puesto (plata acerada: azulada, se distingue del blanco y del resto)
BRONCE = "#fb923c"    # 3º puesto
RESTO = "#9e9e9e"     # del 4º en adelante y jugadores de últimos récords (gris claro)
PUNTOS = "#ffffff"    # puntos, en todas las pantallas
JUEGO = HEADER        # nombre de juego, en todas las pantallas (celeste)
FECHA = "#787878"     # fechas (gris más apagado que RESTO)
DIM = FECHA           # texto secundario: notas, pie, mensajes y filas ??? sin nombre
PODIUM = (ORO, PLATA, BRONCE)

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
    status: str = ""  # línea de estado: juegos registrados y último escaneo


def plural(count: int, singular: str, plural_form: str) -> str:
    """``1 JUEGO``, ``2 JUEGOS``: el número con la palabra en singular o plural."""
    return f"{count} {singular if count == 1 else plural_form}"


def rank_color(position: int) -> str:
    return PODIUM[position - 1] if 1 <= position <= len(PODIUM) else RESTO


def row_color(position: int, default: str) -> str:
    """Color de una celda que no es posición ni jugador: el del puesto en el podio
    (la fila va entera de ese color) o ``default`` del 4º en adelante."""
    return PODIUM[position - 1] if 1 <= position <= len(PODIUM) else default


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


GAMES_WIDTH = 19  # ancho de la columna JUEGOS del ranking
GAMES_SHOWN = 2  # juegos que se nombran antes del "+N"


def _shorten(name: str, width: int) -> str:
    """Recorta un nombre a ``width`` caracteres, de preferencia en un espacio, terminando en punto."""
    name = pf.normalize(name).strip()
    if len(name) <= width:
        return name
    cut = name[:max(0, width - 1)]
    space = cut.rfind(" ")
    if space >= width // 2:
        cut = cut[:space]
    return cut.rstrip(" ,.:;-/") + "."


def games_summary(games: Sequence[str], width: int = GAMES_WIDTH, shown: int = GAMES_SHOWN) -> str:
    """Hasta ``shown`` nombres de juego y luego ``+N``, sin pasarse de ``width`` caracteres.

    Si los nombres no entran completos se nombran menos juegos (sube el ``+N``);
    si ni uno entra, se recorta ese nombre con prolijidad.
    """
    names = [pf.normalize(g).strip() for g in games]
    if not names:
        return ""
    for count in range(min(shown, len(names)), 0, -1):
        rest = len(names) - count
        suffix = f" +{rest}" if rest else ""
        text = ", ".join(names[:count])
        if len(text) + len(suffix) <= width:
            return text + suffix
    rest = len(names) - 1
    suffix = f" +{rest}" if rest else ""
    return _shorten(names[0], width - len(suffix)) + suffix


def ranking_screens(db: Database, players: Players, names: GameNames,
                    show_no_initials: bool = False) -> List[Screen]:
    ranking = player_ranking(db, players)
    rows = [
        [(ordinal(r.position), rank_color(r.position)), (r.initials, rank_color(r.position)),
         (str(r.count), row_color(r.position, PUNTOS)),
         (games_summary(sorted((names.name(g) for g in r.games), key=str.lower)), row_color(r.position, JUEGO))]
        for r in ranking
    ]
    notes: List[Cell] = []
    unnamed = [g for g in leaders(db, players) if g.unnamed]
    if unnamed and show_no_initials:
        count = len(unnamed)
        notes.append((f"{plural(count, 'RECORD', 'RECORDS')} SIN NOMBRE ({UNNAMED}): NO SUMAN", DIM))
    columns = (Column("POS", 3), Column("JUGADOR", 10), Column("RECORDS", 7, "right"),
               Column("JUEGOS", GAMES_WIDTH))
    pages = _pages(rows)
    return [
        Screen("ranking", "SALON DE LA FAMA", "TOP GLOBAL", columns, page_rows, notes,
               "TODAVIA NADIE TIENE UN PRIMER PUESTO", f"{i}/{len(pages)}" if len(pages) > 1 else "")
        for i, page_rows in enumerate(pages, start=1)
    ]


def records_screen(db: Database, players: Players, names: GameNames, limit: int = ROWS_PER_PAGE,
                   show_no_initials: bool = False) -> Screen:
    """Últimos récords, incluidos los de la línea base con titular (con la fecha en que
    se detectaron). Los que no tienen nombre se ocultan (o se muestran como ???)."""
    rows = []
    # Se piden de más por si hay que saltear récords sin nombre.
    for e in recent_records(db, limit * 5, players):
        if e["unnamed"] and not show_no_initials:
            continue
        holders = UNNAMED if e["unnamed"] else ", ".join(e["new_holders"])
        rows.append([
            (local_stamp(e["detected_utc"]), FECHA),
            (names.name(e["game"]), JUEGO),
            (e["new_top"], PUNTOS),
            (holders, DIM if e["unnamed"] else RESTO),
        ])
        if len(rows) == limit:
            break
    columns = (Column("FECHA", 11), Column("JUEGO", 13), Column("PUNTOS", 8, "right"), Column("JUGADOR", 7))
    return Screen("records", "ULTIMOS RECORDS", "RECORDS DETECTADOS", columns, rows, [],
                  "TODAVIA NO HAY RECORDS")


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
    rows = []
    any_unnamed = False
    for e in db.entries(observation["id"]):
        if e["factory"]:
            continue
        name = entry_name(db, game, e)
        if name is None and not show_no_initials:
            continue
        position = e["position"]
        if name is None:
            any_unnamed = True
            color, shown = DIM, UNNAMED
        else:
            color, shown = rank_color(position), players.name(name)
        podium = name is not None
        rows.append([(ordinal(position), color),
                     (e["score_text"], row_color(position, PUNTOS) if podium else PUNTOS),
                     (shown, color), ("", row_color(position, DIM) if podium else DIM)])
        if len(rows) == ROWS_PER_PAGE:
            break
    if not rows:
        return None
    notes: List[Cell] = []
    if any_unnamed:
        notes.append((f"{UNNAMED} SIN NOMBRE: NO SUMA AL RANKING", DIM))
    columns = (Column("POS", 4), Column("PUNTOS", 10, "right"), Column("JUGADOR", 13), Column("", 10))
    subtitle = names.detail(game) or "TABLA DEL JUEGO"  # año y fabricante, del DAT de FBNeo
    return Screen(f"juego:{game}", names.name(game), subtitle, columns, rows, notes, "TABLA VACIA")


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
