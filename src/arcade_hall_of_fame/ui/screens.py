"""Contenido de las pantallas, independiente de Tk (se puede probar sin ventana)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional, Sequence, Tuple

from . import pixelfont as pf
from ..names import GameNames
from ..naming import UNNAMED, entry_name
from ..players import Players, name_key
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
    qr: Optional[List[List[bool]]] = None  # código QR en lugar de la tabla (pantalla de la página web)
    marquee: Any = None  # media.Picture: logo del juego en lugar del título en texto
    shot: Any = None  # media.Picture: captura al costado de la tabla
    tiles: Optional[List["Tile"]] = None  # pantalla mosaico: una celda por juego en lugar de la tabla


@dataclass
class Tile:
    """Celda de la pantalla mosaico: logo (o nombre) del juego, el 1º y sus puntos."""

    game: str
    title: str
    marquee: Any = None
    holder: Cell = ("", DIM)
    score: Cell = ("", PUNTOS)


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


def local_day(utc_text: str) -> str:
    """Día y mes locales (``26/11``), para la columna FECHA de últimos récords."""
    try:
        return datetime.fromisoformat(utc_text).astimezone().strftime("%d/%m")
    except ValueError:
        return utc_text[:5]


GAMES_WIDTH = 17  # ancho de la columna JUEGOS del ranking (JUGADOR tiene 12, el máximo de un alias)
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
    columns = (Column("POS", 3), Column("JUGADOR", 12), Column("RECORDS", 7, "right"),
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
            (local_day(e["detected_utc"]), FECHA),
            (names.name(e["game"]), JUEGO),
            (e["new_top"], PUNTOS),
            (holders, DIM if e["unnamed"] else RESTO),
        ])
        if len(rows) == limit:
            break
    # JUGADOR de 12: entra un alias completo (players.MAX_ALIAS); por eso la fecha va sin hora.
    columns = (Column("FECHA", 5), Column("JUEGO", 14), Column("PUNTOS", 8, "right"), Column("JUGADOR", 12))
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


class ScreenList(list):
    """Lista de pantallas que además sabe cuántos juegos tienen tabla (``games``)."""

    games = 0


@dataclass
class GameCard:
    """Datos de un juego para elegir los destacados."""

    game: str
    screen: Screen
    players: int  # jugadores distintos de la tabla, con su nombre final
    last_record: str  # hora UTC del récord vigente más reciente ("" si no se sabe)
    recent: bool  # tiene un récord nuevo dentro de los días de destacado


@dataclass(frozen=True)
class RotationOptions:
    """Cuántos juegos destacar y cómo armar los mosaicos (todo configurable desde el comando)."""

    featured: int = 8  # máximo de juegos destacados, con su pantalla
    featured_days: int = 7  # un récord nuevo deja al juego destacado durante estos días
    per_mosaic: int = 6  # juegos por pantalla mosaico (grilla de 3 x 2)
    mosaics: int = 3  # tope de pantallas mosaico por vuelta (rotan entre generaciones)


def distinct_players(db: Database, game: str, players: Players) -> int:
    """Jugadores distintos en la tabla vigente, con el nombre final (alias o nombre puesto)."""
    source = db.source(game)
    if source is None or not source["current_observation_id"]:
        return 0
    found = set()
    for e in db.entries(source["current_observation_id"]):
        name = entry_name(db, game, e)
        if name:
            found.add(name_key(players.name(name)))
    return len(found)


def _last_event_utc(db: Database, game: str) -> str:
    row = db.conn.execute("SELECT MAX(detected_utc) FROM record_events WHERE game = ?", (game,)).fetchone()
    return row[0] if row and row[0] else ""


def last_record_utc(db: Database, game: str) -> str:
    """Hora del último récord del juego (batido o de juego nuevo) o, si no hay, la primera
    vez que se vio su récord vigente; "" si no se sabe."""
    last = _last_event_utc(db, game)
    if last:
        return last
    source = db.source(game)
    if source is None or not source["current_observation_id"]:
        return ""
    observation = db.observation(source["current_observation_id"])
    return db.first_seen_top(game, observation["top_score_text"] or "") or ""


def _parse_utc(text: str) -> datetime:
    try:
        value = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def choose_featured(cards: Sequence[GameCard], limit: int) -> Tuple[List[GameCard], List[GameCard]]:
    """(destacados, resto).

    Primero los juegos con un récord nuevo (el más reciente primero); después,
    hasta completar ``limit``, los de más jugadores distintos y, para desempatar,
    el récord más reciente. El resto queda por orden alfabético, para los mosaicos.
    """
    limit = max(0, limit)
    by_recency = sorted(cards, key=lambda c: (-_parse_utc(c.last_record).timestamp(), c.screen.title.lower()))
    featured = [c for c in by_recency if c.recent][:limit]
    chosen = {c.game for c in featured}
    others = sorted((c for c in cards if c.game not in chosen),
                    key=lambda c: (-c.players, -_parse_utc(c.last_record).timestamp(), c.screen.title.lower()))
    featured += others[:limit - len(featured)]
    chosen = {c.game for c in featured}
    rest = sorted((c for c in cards if c.game not in chosen), key=lambda c: (c.screen.title.lower(), c.game))
    return featured, rest


def mosaic_pages(rest: Sequence[GameCard], per_page: int, max_pages: int,
                 rotation: int = 0) -> List[Tuple[int, int, List[GameCard]]]:
    """Páginas de mosaico de esta vuelta: (número, total, juegos).

    Si hay más páginas que ``max_pages``, se muestran ``max_pages`` seguidas a
    partir de una que avanza con ``rotation`` (una vez por generación), así que
    en vueltas sucesivas aparecen todas.
    """
    per_page = max(1, per_page)
    pages = [list(rest[i:i + per_page]) for i in range(0, len(rest), per_page)]
    total = len(pages)
    if total == 0 or max_pages <= 0:
        return []
    if total <= max_pages:
        return [(i + 1, total, page) for i, page in enumerate(pages)]
    start = (rotation * max_pages) % total
    return [((start + k) % total + 1, total, pages[(start + k) % total]) for k in range(max_pages)]


def _tile(card: GameCard, media) -> Tile:
    """Celda con el 1º de la tabla (la primera fila que se muestra) y sus puntos."""
    tile = Tile(card.game, card.screen.title, media.marquee(card.game) if media is not None else None)
    if card.screen.rows:
        first = card.screen.rows[0]
        name, color = first[2]
        tile.holder = (name, DIM if color == DIM else ORO)
        tile.score = (first[1][0], PUNTOS)
    return tile


def mosaic_screen(number: int, total: int, cards: Sequence[GameCard], media=None) -> Screen:
    return Screen(f"mosaico:{number}", "MÁS RÉCORDS", f"{number} / {total}", (), [], [], "",
                  tiles=[_tile(c, media) for c in cards])


def build_screens(db: Database, players: Players, names: Optional[GameNames] = None,
                  show_no_initials: bool = False, options: Optional[RotationOptions] = None,
                  media=None, rotation: int = 0, now: Optional[datetime] = None) -> List[Screen]:
    """Secuencia de rotación: TOP GLOBAL, ÚLTIMOS RÉCORDS, los juegos destacados (cada
    uno con su pantalla) y las pantallas mosaico con el resto de los juegos.

    No se muestran las entradas de fábrica (un juego que solo tiene esas no
    aparece) ni los récords sin iniciales que todavía no tienen nombre, salvo
    que se pida ``show_no_initials``. Todo queda guardado en la base igual.
    ``media`` (``media.Media``) da los marquees y capturas; sin él, todo en texto.
    """
    names = names or GameNames()
    options = options or RotationOptions()
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(days=options.featured_days)
    names.set_games(s["game"] for s in db.sources())
    ranking = ranking_screens(db, players, names, show_no_initials)
    sequence = ScreenList(ranking)
    sequence.append(records_screen(db, players, names, show_no_initials=show_no_initials))
    cards = []
    for source in db.sources():
        game = source["game"]
        screen = game_screen(db, game, players, names, show_no_initials)
        if screen is None:
            continue
        event = _last_event_utc(db, game)
        recent = options.featured_days > 0 and bool(event) and _parse_utc(event) >= since
        cards.append(GameCard(game, screen, distinct_players(db, game, players), last_record_utc(db, game), recent))
    featured, rest = choose_featured(cards, options.featured)
    for card in featured:
        if media is not None:
            card.screen.marquee = media.marquee(card.game)
            card.screen.shot = media.shot(card.game)
        sequence.append(card.screen)
    for number, total, page in mosaic_pages(rest, options.per_mosaic, options.mosaics, rotation):
        sequence.append(mosaic_screen(number, total, page, media))
    sequence.games = len(cards)
    status = status_line(db, len(cards))
    for screen in sequence:
        screen.status = status
    return sequence
