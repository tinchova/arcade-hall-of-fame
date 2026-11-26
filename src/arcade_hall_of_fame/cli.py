"""Comando de línea: escanear partidas y consultar clasificaciones.

Uso, desde la raíz del repositorio::

    python -m arcade_hall_of_fame escanear "<carpeta de partidas>/fbneo" [--hiscore-dat <ruta>]
    python -m arcade_hall_of_fame ranking
    python -m arcade_hall_of_fame juego galaga
    python -m arcade_hall_of_fame records [-n 10]
    python -m arcade_hall_of_fame aceptar <juego>
    python -m arcade_hall_of_fame pendientes
    python -m arcade_hall_of_fame sin-nombre
    python -m arcade_hall_of_fame nombrar <juego> <iniciales>
    python -m arcade_hall_of_fame pantalla --carpeta "<carpeta de partidas>/fbneo"
    python -m arcade_hall_of_fame protector --salida <carpeta de imágenes> --carpeta "<partidas>/fbneo"

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
from .naming import UNNAMED, NamingError, assign_name, entry_name, remove_name, unnamed_records
from .rankings import leaders, player_ranking, recent_records
from .scanner import scan, utc_now
from .players import Players
from .storage import PENDING_SEEN_KEY, Database, default_database, default_players_file

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
        who = ", ".join(holders) or "sin iniciales: ver 'sin-nombre'"
        if previous is None:
            print(f"  Primer récord en {game} (juego nuevo): {new} ({who})")
        else:
            print(f"  Récord batido en {game}: {previous} -> {new} ({who})")
    for game in report.pending:
        print(f"  {game}: el máximo bajó; queda pendiente (ver 'aceptar')")
    for game, error in report.errors:
        print(f"  {game}: {error}")
    if report.unreadable:
        news = f", {len(report.new_unreadable)} nuevos" if report.new_unreadable else ""
        print(f"  Récords que no se pueden leer: {len(report.unreadable)}{news} (ver 'pendientes')")
    return 0


def pending_lines(db: Database, mark_new: bool) -> List[str]:
    """Texto de la lista de juegos con récords sin leer (también va al archivo del protector)."""
    rows = db.unreadable()
    if not rows:
        return ["No hay récords sin leer: todos los .hi encontrados se pueden leer."]
    lines = [f"Juegos con un récord guardado que todavía no se puede leer: {len(rows)}",
             "Se sabe que alguien jugó y FBNeo guardó la tabla, pero no qué dice.",
             "Para agregarlos, ver docs/COBERTURA_FBNEO.md, sección \"Agregar un juego nuevo\".", ""]
    table = []
    for r in rows:
        mark = ""
        if mark_new and r["seen_mtime_utc"] is None:
            mark = "NUEVO"
        elif mark_new and r["seen_mtime_utc"] != r["file_mtime_utc"]:
            mark = "CAMBIÓ"
        reason = r["reason"] + (f" ({r['detail']})" if r["detail"] else "")
        table.append([mark, r["game"], local_time(r["first_seen_utc"]), local_time(r["file_mtime_utc"]), reason])
    headers = ["", "Juego", "Apareció", "Última modificación", "Motivo"]
    if not mark_new:
        headers, table = headers[1:], [row[1:] for row in table]
    widths = [max(len(str(x)) for x in [h] + [row[i] for row in table]) for i, h in enumerate(headers)]
    lines.append("  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip())
    lines.append("  ".join("-" * w for w in widths))
    lines.extend("  ".join(str(c).ljust(w) for c, w in zip(row, widths)).rstrip() for row in table)
    return lines


def unnamed_lines(db: Database) -> List[str]:
    """Récords vigentes sin iniciales ni nombre (también van al archivo del protector)."""
    rows = unnamed_records(db)
    if not rows:
        return ["No hay récords sin nombre."]
    lines = [f"Récords sin nombre: {len(rows)}",
             f"No tienen iniciales: no se muestran (o salen como {UNNAMED}) ni suman al ranking.",
             "Para ponerles nombre: python -m arcade_hall_of_fame nombrar <juego> <iniciales>", ""]
    table = [[r.game, r.score_text, local_time(r.detected_utc)] for r in rows]
    headers = ["Juego", "Récord", "Desde"]
    widths = [max(len(str(x)) for x in [h] + [row[i] for row in table]) for i, h in enumerate(headers)]
    lines.append("  ".join(h.ljust(w) for h, w in zip(headers, widths)).rstrip())
    lines.append("  ".join("-" * w for w in widths))
    lines.extend("  ".join(str(c).ljust(w) for c, w in zip(row, widths)).rstrip() for row in table)
    return lines


def cmd_unnamed(args, db: Database) -> int:
    print("\n".join(unnamed_lines(db)))
    return 0


def cmd_name(args, db: Database) -> int:
    if args.quitar:
        if args.iniciales:
            print("Con --quitar no se indican iniciales.", file=sys.stderr)
            return 2
        score = remove_name(db, args.juego)
        print(f"{args.juego}: el récord {score} quedó otra vez sin nombre ({UNNAMED}).")
        return 0
    if not args.iniciales:
        print("Faltan las iniciales: nombrar <juego> <iniciales>", file=sys.stderr)
        return 2
    source = db.source(args.juego)
    previous = None
    if source is not None and source["current_observation_id"]:
        observation = db.observation(source["current_observation_id"])
        row = db.record_name(args.juego, observation["top_score_text"])
        previous = row["initials"] if row else None
    record = assign_name(db, args.juego, args.iniciales, utc_now(), "comando", args.puntos)
    name = db.record_name(record.game, record.score_text)["initials"]
    change = f" (antes: {previous})" if previous and previous != name else ""
    print(f"{record.game}: el récord {record.score_text} queda a nombre de {name}{change}.")
    print("Las imágenes del protector se actualizan en el próximo escaneo (o con el comando protector).")
    return 0


def cmd_pending(args, db: Database) -> int:
    seen = db.setting(PENDING_SEEN_KEY)
    lines = pending_lines(db, mark_new=True)
    print("\n".join(lines))
    if db.unreadable():
        since = f"desde la consulta del {local_time(seen)}" if seen else "(primera consulta)"
        print(f"\nNUEVO: apareció {since}; CAMBIÓ: el archivo se modificó desde entonces (otra partida).")
    if not args.sin_marcar:
        db.mark_unreadable_seen(utc_now())
    print()
    print("\n".join(unnamed_lines(db)))
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
        name = entry_name(db, args.nombre, e)
        if e["factory"]:
            notes.append("fábrica")
        elif name is None:
            notes.append("sin nombre")
        elif not (e["initials"] or "").strip():
            notes.append("nombre puesto con 'nombrar'")
        rows.append([str(e["position"]), e["score_text"], name or (e["initials"] or ""), ", ".join(notes)])
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
        [local_time(e["detected_utc"]), e["game"],
         "juego nuevo" if e["previous_top"] is None
         else f"{e['previous_top']} ({', '.join(e['previous_holders']) or '-'})",
         e["new_top"], UNNAMED if e["unnamed"] else ", ".join(e["new_holders"])]
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


def screen_builder(args, db: Database):
    """Devuelve una función que arma las pantallas con los nombres de los juegos."""
    from .fetch_names import DEFAULT_DIR as DEFAULT_DATS
    from .names import from_files
    from .ui.screens import build_screens

    players = Players.load(Path(args.jugadores))
    dats = [Path(d) for d in (args.dat or [])] or [DEFAULT_DATS]
    cache = {}

    def build():
        # Los nombres se leen una vez (el DAT de FBNeo pesa varios MB); solo se
        # vuelven a leer si aparece un juego que no estaba.
        games = [s["game"] for s in db.sources()]
        if "names" not in cache or not all(g in cache["games"] for g in games):
            cache["names"] = from_files(args.gamelist, dats, Path(args.definiciones), games)
            cache["games"] = set(games)
        return build_screens(db, players, cache["names"], show_no_initials=args.mostrar_sin_iniciales)

    return build


def cmd_screen(args, db: Database) -> int:
    from .ui.layout import layout
    from .ui.raster import Raster
    from .ui.tkapp import FOOTER

    refresh = None
    if args.carpeta:
        scanner = make_scanner(args, db)
        refresh = lambda: scanner()  # noqa: E731
    build = screen_builder(args, db)

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
            ops = layout(screen, width, height, FOOTER, f"{i}/{len(screens)}")
            Raster(width, height).draw(ops).save(out / f"{name}.png")
        print(f"{len(seen)} capturas en {out}")
        return 0

    from .ui.tkapp import run

    run(build, refresh, args.segundos, args.escaneo if refresh else 0, not args.sin_animacion,
        args.ventana, args.salir_en)
    return 0


def cmd_protector(args, db: Database) -> int:
    """Escanea y, solo si cambiaron los datos, actualiza los PNG del protector de pantalla."""
    from .protector import PENDING_FILE, data_state, generate, write_text_if_changed

    if args.carpeta:
        make_scanner(args, db)()
    width, height = args.tamano
    state = data_state(db, (width, height, args.mostrar_sin_iniciales, args.gamelist, args.dat))
    report = generate(lambda: build_screens_for_protector(args, db), Path(args.salida), width, height, state)
    pending_text = "\n".join(pending_lines(db, mark_new=False) + [""] + unnamed_lines(db)) + "\n"
    if write_text_if_changed(Path(args.salida) / PENDING_FILE, pending_text):
        print(f"Protector: lista de récords sin leer y sin nombre actualizada ({PENDING_FILE})")
    if report.skipped:
        print(f"Protector: sin cambios en los datos; no se reescribió nada en {args.salida}")
    else:
        print(f"Protector: {len(report.written)} imágenes nuevas o cambiadas, {len(report.unchanged)} iguales, "
              f"{len(report.removed)} borradas, en {args.salida}")
    return 0


def build_screens_for_protector(args, db: Database):
    from .ui.screens import local_stamp

    screens = screen_builder(args, db)()
    # La línea de estado muestra el último cambio (no el último escaneo), para que
    # las imágenes solo cambien cuando cambian los datos.
    last = db.last_change()
    count = sum(1 for s in screens if s.key.startswith("juego:"))
    status = f"{count} JUEGOS  ACTUALIZADO {local_stamp(last)}" if last else f"{count} JUEGOS"
    for screen in screens:
        screen.status = status
    return screens


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
    p.add_argument("--mostrar-sin-iniciales", action="store_true",
                   default=os.environ.get("ARCADE_HOF_MOSTRAR_SIN_INICIALES", "") in ("1", "si", "true"),
                   help="mostrar también los récords sin iniciales ni nombre, como ??? (ocultos por defecto)")
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
    p = sub.add_parser("protector", help="generar los PNG para el protector de pantalla de ES-DE")
    p.add_argument("--salida", required=not os.environ.get("ARCADE_HOF_PROTECTOR"),
                   default=os.environ.get("ARCADE_HOF_PROTECTOR"), help="carpeta de imágenes del slideshow")
    p.add_argument("--carpeta", default=os.environ.get("ARCADE_HOF_PARTIDAS"), help="carpeta de partidas a escanear")
    p.add_argument("--hiscore-dat", help="hiscore.dat de FBNeo, para comprobar regiones de memoria")
    p.add_argument("--gamelist", default=os.environ.get("ARCADE_HOF_GAMELIST"),
                   help="gamelist.xml de ES-DE para los nombres de los juegos (solo lectura)")
    p.add_argument("--dat", action="append", help="DAT de FBNeo o carpeta con DAT")
    p.add_argument("--mostrar-sin-iniciales", action="store_true",
                   default=os.environ.get("ARCADE_HOF_MOSTRAR_SIN_INICIALES", "") in ("1", "si", "true"),
                   help="mostrar también los récords sin iniciales ni nombre, como ??? (ocultos por defecto)")
    p.add_argument("--tamano", type=parse_size, default=(1920, 1080), help="tamaño de las imágenes (1920x1080)")
    p.set_defaults(func=cmd_protector)
    p = sub.add_parser("pendientes", help="juegos con un récord guardado que todavía no se puede leer")
    p.add_argument("--sin-marcar", action="store_true",
                   help="no dar por vistos los nuevos (la próxima vez se vuelven a destacar)")
    p.set_defaults(func=cmd_pending)
    p = sub.add_parser("sin-nombre", help="récords vigentes sin iniciales a los que falta ponerles nombre")
    p.set_defaults(func=cmd_unnamed)
    p = sub.add_parser("nombrar", help="poner iniciales al récord vigente de un juego que no las tiene")
    p.add_argument("juego")
    p.add_argument("iniciales", nargs="?")
    p.add_argument("--puntos", help="puntuación esperada: falla si el récord vigente es otro")
    p.add_argument("--quitar", action="store_true", help="quitar el nombre puesto al récord vigente")
    p.set_defaults(func=cmd_name)
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
