"""Comando de línea: escanear partidas y consultar clasificaciones.

Uso, desde la raíz del repositorio::

    python -m arcade_hall_of_fame escanear "<carpeta de partidas>/fbneo" [--hiscore-dat <ruta>]
    python -m arcade_hall_of_fame ranking
    python -m arcade_hall_of_fame juego galaga
    python -m arcade_hall_of_fame records [-n 10]
    python -m arcade_hall_of_fame aceptar <juego>

Opciones comunes: ``--base`` (archivo SQLite; por defecto en la carpeta de
datos del usuario) y ``--definiciones`` (carpeta ``src/main/db`` descargada con
``python -m arcade_hall_of_fame.hi2txt.fetch``).
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
from .storage import Database, default_database

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


def cmd_scan(args, db: Database) -> int:
    library = DefinitionLibrary(args.definiciones)
    factory = FactoryTables(Path(args.definiciones).parent / "db_defaults")
    regions = load_hiscore_dat(args.hiscore_dat) if args.hiscore_dat else None
    revision = REVISION if REVISION in str(Path(args.definiciones).resolve()) else "desconocida"
    report = scan(Path(args.carpeta), db, library, factory, revision, regions)
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
    ranking = player_ranking(db)
    if ranking:
        print_table(["Pos", "Iniciales", "Primeros puestos", "Juegos"],
                    [[str(r.position), r.initials, str(r.count), ", ".join(r.games)] for r in ranking])
    else:
        print("Todavía nadie tiene un primer puesto atribuible.")
    without = [g for g in leaders(db) if not g.holders]
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
    events = recent_records(db, args.n)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arcade_hall_of_fame", description="Salón de la fama arcade local.")
    parser.add_argument("--base", default=os.environ.get("ARCADE_HOF_BASE") or str(default_database()),
                        help="archivo SQLite (por defecto, en la carpeta de datos del usuario)")
    parser.add_argument("--definiciones", default=os.environ.get("ARCADE_HOF_DEFINICIONES") or str(DEFAULT_DB_DIR),
                        help="carpeta src/main/db de hi2txt-xml")
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
