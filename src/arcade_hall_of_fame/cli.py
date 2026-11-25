"""Comando de línea: escanear partidas y consultar clasificaciones.

Uso, desde la raíz del repositorio::

    python -m arcade_hall_of_fame escanear "<carpeta de partidas>/fbneo" [--hiscore-dat <ruta>]
    python -m arcade_hall_of_fame ranking
    python -m arcade_hall_of_fame juego galaga
    python -m arcade_hall_of_fame records [-n 10]
    python -m arcade_hall_of_fame aceptar <juego>
    python -m arcade_hall_of_fame pantalla --carpeta "<carpeta de partidas>/fbneo"

Opciones comunes: ``--base`` (archivo SQLite; por defecto en la carpeta de
datos del usuario) y ``--definiciones`` (carpeta ``src/main/db`` descargada con
``python -m arcade_hall_of_fame.hi2txt.fetch``) y ``--jugadores``
(``jugadores.json`` opcional; ver ``players.py``).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .hi2txt import DefinitionLibrary
from .hi2txt.defaults import FactoryTables
from .hi2txt.fetch import REVISION
from .hi2txt.hiscore_dat import load_hiscore_dat
from .models import HighScoreError
from .rankings import leaders, player_ranking, recent_records
from .scanner import scan
from .players import Players
from .storage import Database, default_database, default_players_file

DEFAULT_DB_DIR = Path("local") / "hi2txt-xml" / REVISION / "src" / "main" / "db"


def local_time(utc_text: str) -> str:
    try:
        return datetime.fromisoformat(utc_text).astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return utc_text


def print_table(headers: List[str], rows: List[List[str]]) -> None:
    widths = [max(len(str(x)) for x in [h] + [r[i] for r in rows]) for i, h in enumerate(headers)]
    print("  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip())
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(row, widths)).rstrip())


def make_scanner(args, db: Database):
    """Devuelve una función que escanea args.carpeta con la configuración dada."""
    library = DefinitionLibrary(args.definiciones)
    factory = FactoryTables(Path(args.definiciones).parent / "db_defaults")
    regions = load_hiscore_dat(args.hiscore_dat) if args.hiscore_dat else None
    revision = REVISION if REVISION in str(Path(args.definiciones).resolve()) else "desconocida"
    return lambda: scan(Path(args.carpeta), db, library, factory, revision, regions)


def cmd_scan(args, db: Database) -> int:
    report = make_scanner(args, db)()
    print(f"Archivos .hi: {report.files}; nuevos estados: {len(report.new_observations)}; "
          f"sin cambios: {len(report.unchanged)}; con error: {len(report.errors)}")
    for game, previous, new, holders in report.records:
        print(f"  Récord batido en {game}: {previous} -> {new} ({', '.join(holders) or 'sin titular atribuible'})")
    for game in report.pending:
        print(f"  {game}: el máximo bajó; queda pendiente (ver 'aceptar')")
    for game, error in report.errors:
        print(f"  {game}: {error}")
    return 0


def cmd_ranking(args, db: Database) -> int:
    players = Players.load(Path(args.jugadores))
    ranking = player_ranking(db, players)
    if ranking:
        print_table(["Pos", "Jugador", "Primeros puestos", "Juegos"],
                    [[str(r.position), r.initials, str(r.count), ", ".join(r.games)] for r in ranking])
    else:
        print("Todavía nadie tiene un primer puesto atribuible.")
    without = [g for g in leaders(db, players) if not g.holders]
    if without:
        print("\nJuegos sin primer puesto atribuible:")
        for g in without:
            print(f"  {g.game} ({g.top_score}): {g.reason}")
    return 0


def cmd_game(args, db: Database) -> int:
    source = db.source(args.nombre)
    if source is None or not source["current_observation_id"]:
        error = f": {source['last_error']}" if source is not None and source["last_error"] else ""
        print(f"No hay una tabla registrada para {args.nombre}{error}", file=sys.stderr)
        return 1
    observation = db.observation(source["current_observation_id"])
    rows = []
    for e in db.entries(observation["id"]):
        notes = []
        if e["factory"]:
            notes.append("fábrica")
        if e["initials"] is None:
            notes.append("sin iniciales")
        rows.append([str(e["position"]), e["score_text"], e["initials"] or "", ", ".join(notes)])
    print(f"{args.nombre}: tabla vigente desde {local_time(observation['detected_utc'])}, "
          f"última lectura {local_time(source['last_seen_utc'])}")
    print_table(["Pos", "Puntuación", "Iniciales", "Notas"], rows)
    pending = db.pending(args.nombre)
    if pending is not None:
        print(f"\nAviso: hay un estado pendiente del {local_time(pending['detected_utc'])}: {pending['note']}")
    if source["last_error"]:
        print(f"\nÚltimo error de lectura: {source['last_error']}")
    return 0


def cmd_records(args, db: Database) -> int:
    events = recent_records(db, args.n, Players.load(Path(args.jugadores)))
    if not events:
        print("Todavía no se registraron récords batidos (el primer escaneo es la línea base).")
        return 0
    print_table(["Detectado", "Juego", "Anterior", "Nuevo", "Titular"], [
        [local_time(e["detected_utc"]), e["game"], f"{e['previous_top']} ({', '.join(e['previous_holders']) or '-'})",
         e["new_top"], ", ".join(e["new_holders"]) or "-"]
        for e in events
    ])
    return 0


def cmd_accept(args, db: Database) -> int:
    pending = db.pending(args.nombre)
    if pending is None:
        print(f"{args.nombre} no tiene estados pendientes.", file=sys.stderr)
        return 1
    db.accept(args.nombre, pending["id"])
    print(f"{args.nombre}: el estado del {local_time(pending['detected_utc'])} es la nueva línea base.")
    return 0


def parse_size(text: str):
    try:
        width, height = (int(v) for v in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("usar ANCHOxALTO, por ejemplo 1280x720") from None
    return width, height


def cmd_screen(args, db: Database) -> int:
    from .ui.layout import layout
    from .ui.raster import Raster
    from .ui.screens import build_screens
    from .ui.tkapp import FOOTER

    from .fetch_names import DEFAULT_DIR as DEFAULT_DATS
    from .names import from_files

    players = Players.load(Path(args.jugadores))
    dats = [Path(d) for d in (args.dat or [])] or [DEFAULT_DATS]
    refresh = None
    if args.carpeta:
        scanner = make_scanner(args, db)
        refresh = lambda: scanner()  # noqa: E731

    cache = {}

    def build():
        # Los nombres se leen una vez (el DAT de FBNeo pesa varios MB); los juegos
        # nuevos que aparezcan después se agregan sin releer el DAT.
        games = [s["game"] for s in db.sources()]
        if "names" not in cache or not all(g in cache["games"] for g in games):
            cache["names"] = from_files(args.gamelist, dats, Path(args.definiciones), games)
            cache["games"] = set(games)
        return build_screens(db, players, cache["names"])

    if args.capturas or args.prueba:
        if refresh is not None:
            refresh()
        screens = build()
        width, height = args.tamano
        if args.prueba:
            import tkinter

            version = tkinter.Tcl().eval("info patchlevel")
            for screen in screens:
                Raster(width, height).draw(layout(screen, width, height, FOOTER, "1/1"))
            print(f"Modo de prueba: Tk {version}; {len(screens)} pantallas generadas a {width}x{height} sin abrir ventana.")
            return 0
        out = Path(args.capturas)
        out.mkdir(parents=True, exist_ok=True)
        seen = set()
        for i, screen in enumerate(screens, start=1):
            if screen.key in seen:
                continue
            seen.add(screen.key)
            name = screen.key.replace(":", "-") + (f"-{screen.page.replace('/', 'de')}" if screen.page else "")
            Raster(width, height).draw(layout(screen, width, height, FOOTER, f"{i}/{len(screens)}")).save(out / f"{name}.png")
        print(f"{len(seen)} capturas en {out}")
        return 0

    from .ui.tkapp import run

    run(build, refresh, args.segundos, args.escaneo if refresh else 0, not args.sin_animacion,
        args.ventana, args.salir_en)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arcade_hall_of_fame", description="Salón de la fama arcade local.")
    parser.add_argument("--base", default=os.environ.get("ARCADE_HOF_BASE") or str(default_database()),
                        help="archivo SQLite (por defecto, en la carpeta de datos del usuario)")
    parser.add_argument("--definiciones", default=os.environ.get("ARCADE_HOF_DEFINICIONES") or str(DEFAULT_DB_DIR),
                        help="carpeta src/main/db de hi2txt-xml")
    parser.add_argument("--jugadores", default=os.environ.get("ARCADE_HOF_JUGADORES") or str(default_players_file()),
                        help="jugadores.json opcional que agrupa iniciales por persona")
    sub = parser.add_subparsers(dest="comando")
    p = sub.add_parser("escanear", help="leer los .hi de una carpeta y registrar cambios")
    p.add_argument("carpeta")
    p.add_argument("--hiscore-dat", help="hiscore.dat de FBNeo, para comprobar regiones de memoria")
    p.set_defaults(func=cmd_scan)
    p = sub.add_parser("ranking", help="jugadores por cantidad de primeros puestos")
    p.set_defaults(func=cmd_ranking)
    p = sub.add_parser("juego", help="tabla vigente de un juego")
    p.add_argument("nombre")
    p.set_defaults(func=cmd_game)
    p = sub.add_parser("records", help="últimos récords batidos")
    p.add_argument("-n", type=int, default=10)
    p.set_defaults(func=cmd_records)
    p = sub.add_parser("pantalla", help="interfaz a pantalla completa (Esc para salir)")
    p.add_argument("--carpeta", default=os.environ.get("ARCADE_HOF_PARTIDAS"),
                   help="carpeta de partidas a escanear al abrir y cada tanto")
    p.add_argument("--hiscore-dat", help="hiscore.dat de FBNeo, para comprobar regiones de memoria")
    p.add_argument("--segundos", type=float, default=8.0, help="segundos por pantalla (8)")
    p.add_argument("--escaneo", type=float, default=60.0, help="segundos entre escaneos (60)")
    p.add_argument("--sin-animacion", action="store_true", help="mostrar las filas sin aparición escalonada")
    p.add_argument("--gamelist", default=os.environ.get("ARCADE_HOF_GAMELIST"),
                   help="gamelist.xml de ES-DE para los nombres de los juegos (solo lectura)")
    p.add_argument("--dat", action="append",
                   help="DAT de FBNeo o carpeta con DAT (por defecto, los bajados con fetch_names)")
    p.add_argument("--ventana", type=parse_size, help="ventana de ANCHOxALTO en lugar de pantalla completa")
    p.add_argument("--salir-en", type=float, help="cerrar sola después de N segundos (pruebas)")
    p.add_argument("--prueba", action="store_true", help="comprobar Tk y generar las pantallas sin abrir ventana")
    p.add_argument("--capturas", help="guardar PNG de cada pantalla en esta carpeta, sin abrir ventana")
    p.add_argument("--tamano", type=parse_size, default=(1920, 1080), help="tamaño de capturas y prueba (1920x1080)")
    p.set_defaults(func=cmd_screen)
    p = sub.add_parser("aceptar", help="aceptar un estado pendiente como nueva línea base")
    p.add_argument("nombre")
    p.set_defaults(func=cmd_accept)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    db = Database(Path(args.base))
    try:
        return args.func(args, db)
    except HighScoreError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()
