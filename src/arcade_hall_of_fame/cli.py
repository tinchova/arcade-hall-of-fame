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
    python -m arcade_hall_of_fame web          # página para el celular (red local): alias y nombres

En la Mac, el script ``hof`` de la raíz del repositorio hace lo mismo desde
cualquier carpeta: ``~/arcade-hall-of-fame/hof nombrar mspacman ANA``.

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
from .naming import UNNAMED, NamingError, assign_name, entry_name, remove_name, select_row, unnamed_records
from .rankings import leaders, player_ranking, recent_records
from .scanner import scan, utc_now
from .players import load_players
from .storage import PENDING_SEEN_KEY, Database, visible_positions, default_data_dir, default_database, default_players_file

REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DB_DIR = REPO_DIR / "local" / "hi2txt-xml" / REVISION / "src" / "main" / "db"
# Comando que se muestra en los mensajes de ayuda (el script hof de la raíz del repositorio).
def _hof_command() -> str:
    if os.environ.get("ARCADE_HOF_COMANDO"):
        return os.environ["ARCADE_HOF_COMANDO"]
    script = REPO_DIR / "hof"
    if not script.is_file():
        return "python -m arcade_hall_of_fame"
    try:
        return "~/" + script.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(script)


HOF = _hof_command()


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
        new = len(report.new_unreadable)
        news = f", {new} {'nuevo' if new == 1 else 'nuevos'}" if new else ""
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
             f"Para ponerles nombre: {HOF} nombrar <juego> <iniciales>",
             "  (o desde el celular, con la página web: ver README)", ""]
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
    chosen = args.puesto is not None or args.de is not None
    if args.quitar:
        if args.iniciales:
            print("Con --quitar no se indican iniciales.", file=sys.stderr)
            return 2
        score, original = remove_name(db, args.juego, args.puntos, args.puesto, args.de)
        what = f"la fila de {score}" if chosen else f"el récord {score}"
        if original:
            print(f"{args.juego}: {what} vuelve a las iniciales originales del juego: {original}.")
        else:
            print(f"{args.juego}: {what} quedó otra vez sin nombre ({UNNAMED}).")
        refresh_protector_after_naming(args, db)
        return 0
    if not args.iniciales:
        print(f"Faltan las iniciales: {HOF} nombrar <juego> <iniciales> [--de <nombre actual> | --puesto N]",
              file=sys.stderr)
        return 2
    previous = select_row(db, args.juego, args.puesto, args.de, args.puntos).name
    record = assign_name(db, args.juego, args.iniciales, utc_now(), "comando", args.puntos, args.puesto, args.de)
    name = db.record_name(record.game, record.score_text)["initials"]
    change = f" (antes: {previous})" if previous and previous != name else ""
    if not record.position:
        what = f"el récord anterior {record.score_text} (no suma al ranking)"
    elif chosen:
        what = f"la fila del puesto {record.position} ({record.score_text})"
    else:
        what = f"el récord {record.score_text}"
    print(f"{record.game}: {what} queda a nombre de {name}{change}.")
    refresh_protector_after_naming(args, db)
    return 0


def refresh_protector_after_naming(args, db: Database) -> None:
    """Regenera las imágenes del protector, si su carpeta existe, con las opciones de la última vez.

    Poner un nombre no cambia la carpeta de partidas, así que el LaunchAgent no se
    dispara solo. Las opciones (tamaño, gamelist, DAT...) salen del manifiesto que
    deja el comando ``protector``; no se escanea.
    """
    from .protector import read_options

    out = Path(args.protector) if args.protector else default_data_dir() / "protector"
    if not out.is_dir():
        return
    options = read_options(out)
    if options is None:
        print("Las imágenes del protector se actualizan en el próximo escaneo (o con el comando protector).")
        return
    defaults = build_parser().parse_args(["protector", "--salida", str(out)])
    protector_args = argparse.Namespace(
        salida=str(out), carpeta=None, tamano=tuple(options["tamano"]),
        mostrar_sin_iniciales=options["mostrar_sin_iniciales"], gamelist=options["gamelist"],
        dat=options["dat"], definiciones=options["definiciones"], jugadores=options["jugadores"],
        web_puerto=options.get("web_puerto"), base=args.base,
        **{key: options.get(key, getattr(defaults, key)) for key in ROTATION_OPTIONS})
    update_protector(protector_args, db)


def names_loader(args):
    """Función juegos -> GameNames, con caché (el DAT de FBNeo pesa varios MB)."""
    import threading

    from .fetch_names import DEFAULT_DIR as DEFAULT_DATS
    from .names import from_files

    dats = [Path(d) for d in (args.dat or [])] or [DEFAULT_DATS]
    cache = {}
    lock = threading.Lock()

    def load(games):
        with lock:
            if "names" not in cache or not set(games) <= cache["games"]:
                cache["games"] = set(games) | cache.get("games", set())
                cache["names"] = from_files(args.gamelist, dats, Path(args.definiciones), sorted(cache["games"]))
            return cache["names"]

    return load


def cmd_web(args, db: Database) -> int:
    """Página para el celular, solo en la red local: alias de jugadores y nombres de récords."""
    from .direccion import page_urls, qr_svg, tailscale_urls
    from .players import Players
    from .web import WebConfig, make_server

    names = names_loader(args)
    server_names = lambda d, games: {g: names(games).name(g) for g in games}  # noqa: E731
    server = make_server(WebConfig(Path(args.base), server_names), args.direccion, args.puerto)
    port = server.server_address[1]
    urls = page_urls(port) if args.direccion in ("0.0.0.0", "") else [f"http://{args.direccion}:{port}/"]
    config = server.RequestHandlerClass.config
    config.file_players = lambda: Players.load(Path(args.jugadores))
    config.after_change = lambda d: refresh_protector_after_naming(args, d)
    config.addresses = urls
    config.qr_svg = qr_svg(urls[0]) if urls else ""
    for url in urls or [f"http://<IP de este equipo>:{port}/"]:
        print(f"Página del Salón de la Fama: {url}  (solo red local)", flush=True)
    config.tailscale = tailscale_urls(port) if args.direccion in ("0.0.0.0", "") else []
    for url in config.tailscale:
        print(f"Página del Salón de la Fama por Tailscale: {url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
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
    players = load_players(Path(args.jugadores), db)
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
            score = f" ({g.top_score})" if g.top_score is not None else ""
            print(f"  {g.game}{score}: {g.reason}")
    return 0


def cmd_game(args, db: Database) -> int:
    source = db.source(args.nombre)
    if source is None or not source["current_observation_id"]:
        error = f": {source['last_error']}" if source is not None and source["last_error"] else ""
        print(f"No hay una tabla registrada para {args.nombre}{error}", file=sys.stderr)
        return 1
    observation = db.observation(source["current_observation_id"])
    entries = db.entries(observation["id"])
    shown = visible_positions(entries)
    rows = []
    for e in entries:
        notes = []
        name = entry_name(db, args.nombre, e)
        if e["factory"]:
            # La fábrica se muestra solo como referencia: no tiene puesto ni cuenta para el récord.
            notes.append(f"fábrica, no cuenta (puesto {e['position']} en el juego)")
        elif name is None:
            notes.append("sin nombre")
        elif name != e["initials"]:
            original = (e["initials"] or "").strip()
            notes.append("nombre puesto con 'nombrar'" + (f" (original: {original})" if original else ""))
        position = "-" if e["factory"] else str(shown[e["position"]])
        rows.append([position, e["score_text"], name or (e["initials"] or ""), ", ".join(notes)])
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
    events = recent_records(db, args.n, load_players(Path(args.jugadores), db))
    if not events:
        print("Todavía no hay récords con titular.")
        return 0
    print_table(["Detectado", "Juego", "Anterior", "Nuevo", "Titular"], [
        [local_time(e["detected_utc"]), e["game"],
         "línea base" if e["baseline"] else "juego nuevo" if e["previous_top"] is None
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


# Opciones de la rotación (destacados, mosaicos e imágenes), comunes a pantalla y protector.
ROTATION_OPTIONS = ("destacados", "dias_destacado", "mosaico", "mosaicos", "medios", "sin_imagenes")


def add_rotation_options(p) -> None:
    p.add_argument("--destacados", type=int, default=8,
                   help="máximo de juegos destacados, cada uno con su pantalla (8)")
    p.add_argument("--dias-destacado", type=int, default=7,
                   help="días que un juego con récord nuevo queda destacado (7; 0: ninguno por récord nuevo)")
    p.add_argument("--mosaico", type=int, default=6, help="juegos por pantalla mosaico (6, grilla de 3 x 2)")
    p.add_argument("--mosaicos", type=int, default=3,
                   help="tope de pantallas mosaico por vuelta; si hay más, rotan entre generaciones (3)")
    p.add_argument("--medios", default=os.environ.get("ARCADE_HOF_MEDIOS"),
                   help="carpeta de medios de ES-DE (por defecto, la de es_settings.xml o "
                        "~/ES-DE/downloaded_media); se leen marquees, screenshots y titlescreens")
    p.add_argument("--sin-imagenes", action="store_true", help="no mostrar marquees ni capturas (todo en texto)")


def rotation_options(args):
    from .ui.screens import RotationOptions

    return RotationOptions(featured=args.destacados, featured_days=args.dias_destacado,
                           per_mosaic=args.mosaico, mosaics=args.mosaicos)


def media_for(args):
    """Medios de ES-DE para las pantallas, o None si se pidió todo en texto.

    El sistema es la carpeta del gamelist (``gamelists/fbneo/gamelist.xml`` → ``fbneo``) si
    existe entre los medios; si no, ``fbneo``.
    El resultado escalado se guarda en ``cache-medios`` junto a la base.
    """
    if args.sin_imagenes:
        return None
    from .ui.media import Media, esde_media_dir

    root = Path(os.path.expanduser(args.medios)) if args.medios else esde_media_dir()
    candidates = ([Path(args.gamelist).parent.name] if args.gamelist else []) + ["fbneo"]
    system = next((c for c in candidates if c and (root / c).is_dir()), "fbneo")
    return Media(root, system, Path(args.base).parent / "cache-medios")


def screen_builder(args, db: Database, rotation=None):
    """Devuelve una función que arma las pantallas con los nombres de los juegos.

    ``rotation`` da el número de generación para rotar los mosaicos; por defecto,
    cada llamada es una generación nueva (la ventana Tk rearma las pantallas en
    cada escaneo).
    """
    from .fetch_names import DEFAULT_DIR as DEFAULT_DATS
    from .names import from_files
    from .ui.screens import build_screens

    dats = [Path(d) for d in (args.dat or [])] or [DEFAULT_DATS]
    cache = {"calls": 0}

    def build():
        # Los nombres se leen una vez (el DAT de FBNeo pesa varios MB); solo se
        # vuelven a leer si aparece un juego que no estaba.
        games = [s["game"] for s in db.sources()]
        if "names" not in cache or not all(g in cache["games"] for g in games):
            cache["names"] = from_files(args.gamelist, dats, Path(args.definiciones), games)
            cache["games"] = set(games)
        # Los alias se releen cada vez: se pueden cambiar desde la página web.
        players = load_players(Path(args.jugadores), db)
        generation = rotation() if rotation is not None else cache["calls"]
        cache["calls"] += 1
        return build_screens(db, players, cache["names"], show_no_initials=args.mostrar_sin_iniciales,
                             options=rotation_options(args), media=media_for(args), rotation=generation)

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
        print(f"{len(seen)} {'captura' if len(seen) == 1 else 'capturas'} en {out}")
        return 0

    from .ui.tkapp import run

    run(build, refresh, args.segundos, args.escaneo if refresh else 0, not args.sin_animacion,
        args.ventana, args.salir_en)
    return 0


def cmd_protector(args, db: Database) -> int:
    """Escanea y, solo si cambiaron los datos, actualiza los PNG del protector de pantalla."""
    if args.carpeta:
        make_scanner(args, db)()
    update_protector(args, db)
    return 0


def update_protector(args, db: Database) -> None:
    """Imágenes y lista de pendientes del protector (sin escanear)."""
    from .protector import PENDING_FILE, data_state, generate, write_text_if_changed
    from .ui.screens import plural

    width, height = args.tamano
    web_port = getattr(args, "web_puerto", None)
    urls = []
    if web_port:
        from .direccion import page_urls

        urls = page_urls(web_port)  # si cambia la IP (otra red), cambia el QR
    rotation = {key: getattr(args, key) for key in ROTATION_OPTIONS}
    # El día cuenta en el estado: los destacados por récord nuevo vencen y los mosaicos
    # rotan de un día para otro (solo se reescriben las imágenes que cambian).
    media = media_for(args)
    media_root = str(media.root) if media is not None and media.root is not None else None
    state = data_state(db, (width, height, args.mostrar_sin_iniciales, args.gamelist, args.dat,
                            str(Path(args.jugadores).resolve()), urls, sorted(rotation.items()), media_root,
                            today().isoformat()))
    options = {"tamano": [width, height], "mostrar_sin_iniciales": bool(args.mostrar_sin_iniciales),
               "gamelist": args.gamelist, "dat": args.dat,
               "definiciones": str(Path(args.definiciones).resolve()), "jugadores": str(Path(args.jugadores).resolve()),
               "web_puerto": web_port, **rotation}
    from .protector import esde_running

    report = generate(lambda: build_screens_for_protector(args, db), Path(args.salida), width, height, state, options,
                      esde_running(), getattr(args, "compactar", False))
    pending_text = "\n".join(pending_lines(db, mark_new=False) + [""] + unnamed_lines(db)) + "\n"
    if write_text_if_changed(Path(args.salida) / PENDING_FILE, pending_text):
        print(f"Protector: lista de récords sin leer y sin nombre actualizada ({PENDING_FILE})")
    if report.skipped:
        print(f"Protector: sin cambios en los datos; no se reescribió nada en {args.salida}")
    else:
        print(f"Protector: {plural(len(report.written), 'imagen nueva o cambiada', 'imágenes nuevas o cambiadas')}, "
              f"{plural(len(report.unchanged), 'igual', 'iguales')}, "
              f"{plural(len(report.removed), 'borrada', 'borradas')}, en {args.salida}")
        if report.filled:
            print(f"Protector: {plural(len(report.filled), 'sobrante queda', 'sobrantes quedan')} como relleno "
                  "(ES-DE está abierto y puede estar mostrándolas); se borran en la primera generación "
                  "pasados 10 minutos, o con --compactar")


def today():
    from datetime import date

    return date.today()


def build_screens_for_protector(args, db: Database):
    from .ui.screens import local_stamp, plural

    # Una generación por día: los mosaicos que no entran en una vuelta rotan a diario.
    screens = screen_builder(args, db, rotation=lambda: today().toordinal())()
    # La línea de estado muestra el último cambio (no el último escaneo), para que
    # las imágenes solo cambien cuando cambian los datos.
    last = db.last_change()
    games = plural(screens.games, "JUEGO", "JUEGOS")
    status = f"{games}  ACTUALIZADO {local_stamp(last)}" if last else games
    for screen in screens:
        screen.status = status
    web = web_screen(getattr(args, "web_puerto", None), db, getattr(screens, "names", None))
    if web is not None:
        web.status = status
        screens.append(web)  # al final de la vuelta
    return screens


def web_screen(port: Optional[int], db: Database, names=None):
    """Pantalla con el QR de la página web, solo si hay récords sin nombre (los de ``sin-nombre``).

    Nombra los primeros récords que faltan y ``+N``. Devuelve None si no se pidió,
    no hay red o todos los récords tienen nombre: la imagen deja de mostrarse y
    se trata como cualquier pantalla que sobra.
    """
    if not port:
        return None
    from .direccion import page_urls, qr_matrix
    from .names import GameNames
    from .ui.layout import GRID_COLS
    from .ui.screens import HEADER, SUBTITLE, Screen, games_summary

    missing = unnamed_records(db)
    if not missing:
        return None
    urls = page_urls(port)
    if not urls:
        return None
    names = names or GameNames()
    records = [f"{names.name(r.game)} {r.score_text}" for r in missing]
    title = "RECORD SIN NOMBRE" if len(missing) == 1 else "RECORDS SIN NOMBRE"
    notes = [("ESCANEA PARA PONER TU NOMBRE", HEADER), (urls[0].replace("http://", ""), SUBTITLE)]
    return Screen("web", title, games_summary(records, GRID_COLS, 3), (), [], notes, qr=qr_matrix(urls[0]))


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
    add_rotation_options(p)
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
    p.add_argument("--web-puerto", type=int, default=None,
                   help="agregar una imagen con el QR de la página web en este puerto (por ejemplo 47474), "
                        "solo si hay récords sin nombre")
    p.add_argument("--compactar", action="store_true",
                   help="borrar ya las imágenes sobrantes (si ES-DE está abierto, por defecto quedan como relleno "
                        "hasta la primera generación pasados 10 minutos; usar con el protector de ES-DE cerrado)")
    add_rotation_options(p)
    p.set_defaults(func=cmd_protector)
    p = sub.add_parser("pendientes", help="juegos con un récord guardado que todavía no se puede leer")
    p.add_argument("--sin-marcar", action="store_true",
                   help="no dar por vistos los nuevos (la próxima vez se vuelven a destacar)")
    p.set_defaults(func=cmd_pending)
    p = sub.add_parser("sin-nombre", help="récords vigentes sin iniciales a los que falta ponerles nombre")
    p.set_defaults(func=cmd_unnamed)
    p = sub.add_parser("nombrar", help="poner o cambiar las iniciales del récord vigente de un juego")
    p.add_argument("juego")
    p.add_argument("iniciales", nargs="?")
    p.add_argument("--puntos", help="puntuación esperada: falla si el récord vigente es otro "
                                    "(con --de, también sirve para elegir entre filas con el mismo nombre; "
                                    "en los juegos que guardan solo el máximo, elige un récord anterior)")
    p.add_argument("--de", metavar="NOMBRE",
                   help="cambiar la fila que hoy está a este nombre (iniciales del juego o nombre puesto)")
    p.add_argument("--puesto", type=int, metavar="N", help="cambiar la fila de este puesto de la tabla vigente")
    p.add_argument("--quitar", action="store_true", help="quitar el nombre puesto (al récord, o a la fila elegida)")
    p.add_argument("--protector", default=os.environ.get("ARCADE_HOF_PROTECTOR"),
                   help="carpeta de imágenes del protector a regenerar si existe "
                        "(por defecto, protector/ en la carpeta de datos)")
    p.set_defaults(func=cmd_name)
    p = sub.add_parser("web", help="página para el celular (solo red local): alias de jugadores y nombres de récords")
    p.add_argument("--direccion", default=os.environ.get("ARCADE_HOF_WEB_DIRECCION", "0.0.0.0"),
                   help="dirección donde escuchar (0.0.0.0: todas; igual responde solo a la red local)")
    p.add_argument("--puerto", type=int, default=int(os.environ.get("ARCADE_HOF_WEB_PUERTO", "47474")),
                   help="puerto (47474)")
    p.add_argument("--gamelist", default=os.environ.get("ARCADE_HOF_GAMELIST"),
                   help="gamelist.xml de ES-DE para los nombres de los juegos (solo lectura)")
    p.add_argument("--dat", action="append", help="DAT de FBNeo o carpeta con DAT")
    p.add_argument("--protector", default=os.environ.get("ARCADE_HOF_PROTECTOR"),
                   help="carpeta de imágenes del protector a regenerar al guardar "
                        "(por defecto, protector/ en la carpeta de datos)")
    p.set_defaults(func=cmd_web)
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
