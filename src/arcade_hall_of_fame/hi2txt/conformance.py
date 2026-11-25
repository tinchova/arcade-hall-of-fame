"""Medición local de cobertura y exactitud del intérprete.

Uso (desde la raíz, con las definiciones descargadas por ``fetch``)::

    python -m arcade_hall_of_fame.hi2txt.conformance local/hi2txt-xml/<revisión> \
        [--hiscore-dat ruta/a/hiscore.dat] [--juegos lista.txt] [--detalle]

Informa:

* cobertura estática: cuántas definiciones (y alias ``sameas``) carga el
  intérprete sin operaciones pendientes, y qué operaciones faltan más;
* exactitud: si la descarga incluye los casos de prueba de hi2txt-xml
  (``src/test``), compara la salida con la esperada (``oracle``);
* con ``--hiscore-dat``, cuántos juegos de ese ``hiscore.dat`` (por ejemplo, el
  de FBNeo) tienen definición, cuántas se pueden leer y si las regiones de
  memoria coinciden;
* con ``--hiscore-dat`` y ``--juegos`` (un archivo con un nombre de set o una
  ruta a un ``.zip`` por línea), qué juegos de esa colección se pueden leer y,
  si no, por qué.

No modifica ningún archivo.
"""

from __future__ import annotations

import argparse
import collections
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from ..models import DefinitionError, HighScoreError, UnsupportedDefinition
from .decoder import decode
from .definition import DefinitionLibrary
from .formats import render
from .hiscore_dat import expected_size, load_hiscore_dat


def static_coverage(library: DefinitionLibrary):
    status: dict[str, str] = {}
    features: collections.Counter[str] = collections.Counter()
    base_status: dict[str, str] = {}
    base_features: dict[str, tuple[str, ...]] = {}
    game_base: dict[str, str] = {}
    for game in library.games():
        try:
            base, _ = library.resolve(game)
        except DefinitionError:
            status[game] = "error"
            continue
        game_base[game] = base
        if base not in base_status:
            try:
                library.load(base)
                base_status[base] = "ok"
            except UnsupportedDefinition as exc:
                base_status[base] = "unsupported"
                base_features[base] = exc.features
                features.update(exc.features)
            except DefinitionError:
                base_status[base] = "error"
        status[game] = base_status[base]
    static_coverage.base_features = base_features  # type: ignore[attr-defined]
    static_coverage.game_base = game_base  # type: ignore[attr-defined]
    return status, base_status, features


def _oracle_tables(path: Path):
    root = ET.parse(path).getroot()
    tables, fields = [], {}
    for child in root:
        if child.tag == "table":
            columns = [c.text or "" for c in child.findall("col")]
            rows = [[cell.text or "" for cell in row.findall("cell")] for row in child.findall("row")]
            tables.append((child.get("id"), columns, rows))
        elif child.tag == "field":
            fields[child.get("id")] = child.text or ""
    return tables, fields


def _inputs_for(test_dir: Path, run: str, game: str) -> list[Path]:
    found = []
    hi = test_dir / "input" / run / "hi" / f"{game}.hi"
    if hi.is_file():
        found.append(hi)
    nv = test_dir / "input" / run / "nvram" / game
    if nv.is_dir():
        found.extend(sorted(p for p in nv.iterdir() if p.is_file()))
    return found


def oracle_check(library: DefinitionLibrary, test_dir: Path, supported: dict[str, str], detail: bool):
    outcome: collections.Counter[str] = collections.Counter()
    by_game: dict[str, str] = {}
    oracle_root = test_dir / "oracle"
    for run_dir in sorted(p for p in oracle_root.iterdir() if p.is_dir()):
        run = run_dir.name
        for oracle in sorted(run_dir.glob("*.xml")):
            game = oracle.stem
            key = f"{run}/{game}"
            if supported.get(game) != "ok":
                outcome["sin soporte"] += 1
                continue
            inputs = _inputs_for(test_dir, run, game)
            if len(inputs) != 1:
                outcome["varios archivos o ninguno"] += 1
                continue
            try:
                definition = library.load(game)
                result = decode(definition, inputs[0].read_bytes(), file_name=inputs[0].name)
            except HighScoreError as exc:
                outcome["error de lectura"] += 1
                by_game[key] = f"error: {exc}"
                continue
            try:
                tables, fields = _oracle_tables(oracle)
            except ET.ParseError:
                outcome["salida esperada ilegible"] += 1
                continue
            mine = [(t.id, list(t.columns), [[render(v) for v in row] for row in t.rows]) for t in result.tables]
            mine_fields = {f.id: render(f.value) for f in result.fields}
            ok_main = bool(tables) and bool(mine) and tables[0] == mine[0]
            if mine == tables and mine_fields == fields:
                outcome["coincide"] += 1
                by_game[key] = "ok"
            elif ok_main:
                outcome["tabla principal coincide"] += 1
                by_game[key] = "principal"
            else:
                outcome["difiere"] += 1
                diff = ""
                if tables and mine:
                    for a, b in zip(tables[0][2], mine[0][2]):
                        if a != b:
                            diff = f"esperado {a} / obtenido {b}"
                            break
                    if not diff:
                        diff = f"columnas {tables[0][1]} / {mine[0][1]}, filas {len(tables[0][2])} / {len(mine[0][2])}"
                by_game[key] = f"difiere: {diff}"
    return outcome, by_game


def hiscore_dat_coverage(library: DefinitionLibrary, path: Path, supported: dict[str, str]):
    entries = load_hiscore_dat(path)
    known = set(library.games())
    counts: collections.Counter[str] = collections.Counter()
    for game, regions in entries.items():
        counts["juegos en hiscore.dat"] += 1
        if game not in known:
            continue
        counts["con definición"] += 1
        if supported.get(game) != "ok":
            continue
        counts["con definición soportada"] += 1
        definition = library.load(game)
        size = expected_size(regions)
        structures = [s for s in definition.structures if s.matches_file(f"{game}.hi")]
        if not any(not s.sizes or size in s.sizes for s in structures):
            counts["  tamaño distinto"] += 1
            continue
        with_regions = [s for s in structures if s.regions]
        if with_regions and not any(regions in s.regions for s in with_regions):
            counts["  mismo tamaño, regiones distintas"] += 1
            continue
        counts["soportada y compatible con este hiscore.dat"] += 1
    return counts


READABLE = "se puede leer"
CATEGORIES = (
    READABLE,
    "FBNeo no guarda récords (no está en hiscore.dat)",
    "sin definición en hi2txt-xml",
    "definición con operaciones no soportadas",
    "definición con errores",
    "la definición describe otro archivo (nvram, eeprom...), no el .hi",
    "tamaño distinto al de hiscore.dat",
    "mismo tamaño, regiones de memoria distintas",
)


def classify(game: str, library: DefinitionLibrary, entries, status: dict[str, str]) -> tuple[str, str]:
    """Clasifica un juego: (categoría, detalle)."""
    regions = entries.get(game)
    if not regions:
        return CATEGORIES[1], ""
    if game not in status:
        siblings = sorted(g for g, r in entries.items() if r == regions and status.get(g) == "ok")
        hint = f"mismo bloque de hiscore.dat que {', '.join(siblings[:3])}" if siblings else ""
        return CATEGORIES[2], hint
    if status[game] == "unsupported":
        base = static_coverage.game_base.get(game, game)  # type: ignore[attr-defined]
        return CATEGORIES[3], ", ".join(static_coverage.base_features.get(base, ()))  # type: ignore[attr-defined]
    if status[game] != "ok":
        return CATEGORIES[4], ""
    definition = library.load(game)
    size = expected_size(regions)
    structures = [s for s in definition.structures if s.matches_file(f"{game}.hi")]
    if not structures:
        return CATEGORIES[5], ", ".join(sorted({s.file for s in definition.structures}))
    if not any(not s.sizes or size in s.sizes for s in structures):
        sizes = sorted({n for s in structures for n in s.sizes})
        return CATEGORIES[6], f"FBNeo {size} bytes, definición {sizes}"
    with_regions = [s for s in structures if s.regions]
    if with_regions and not any(regions in s.regions for s in with_regions):
        return CATEGORIES[7], ""
    return READABLE, ""


def read_game_list(path: Path) -> list[str]:
    names = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        name = line.strip().replace("\\", "/").rsplit("/", 1)[-1]
        if name.lower().endswith(".zip"):
            names.append(name[:-4])
    return sorted(set(names))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("carpeta", help="carpeta de la descarga (contiene src/main/db)")
    parser.add_argument("--hiscore-dat", help="hiscore.dat del emulador, para medir compatibilidad")
    parser.add_argument("--juegos", help="lista de sets o de rutas a .zip, uno por línea (requiere --hiscore-dat)")
    parser.add_argument("--detalle", action="store_true", help="listar resultados por juego")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(args.carpeta)
    library = DefinitionLibrary(root / "src" / "main" / "db")

    status, base_status, features = static_coverage(library)
    total = collections.Counter(status.values())
    base_total = collections.Counter(base_status.values())
    print(f"Definiciones: {len(status)} juegos ({len(base_status)} definiciones base, el resto alias sameas)")
    print(f"  soportadas: {total['ok']} juegos / {base_total['ok']} definiciones base")
    print(f"  con operaciones pendientes: {total['unsupported']} juegos / {base_total['unsupported']} base")
    print(f"  con errores en la definición: {total['error']} juegos / {base_total['error']} base")
    print("Operaciones pendientes más frecuentes (definiciones base que las usan):")
    for feature, count in features.most_common(25):
        print(f"  {count:4d}  {feature}")

    test_dir = root / "src" / "test"
    if (test_dir / "oracle").is_dir():
        outcome, by_game = oracle_check(library, test_dir, status, args.detalle)
        print("Comparación con las salidas esperadas de hi2txt-xml (src/test):")
        for name, count in outcome.most_common():
            print(f"  {count:4d}  {name}")
        if args.detalle:
            for key, text in sorted(by_game.items()):
                if text != "ok":
                    print(f"    {key}: {text}")

    if args.hiscore_dat:
        print(f"Compatibilidad con {Path(args.hiscore_dat).name}:")
        for name, count in hiscore_dat_coverage(library, Path(args.hiscore_dat), status).items():
            print(f"  {count:5d}  {name}")

    if args.hiscore_dat and args.juegos:
        entries = load_hiscore_dat(args.hiscore_dat)
        games = read_game_list(Path(args.juegos))
        results = {game: classify(game, library, entries, status) for game in games}
        counts = collections.Counter(category for category, _ in results.values())
        print(f"Colección: {len(games)} juegos")
        for category in CATEGORIES:
            if counts[category]:
                print(f"  {counts[category]:5d}  {category}")
        reasons = collections.Counter(
            feature.strip()
            for category, detail in results.values()
            if category == CATEGORIES[3]
            for feature in detail.split(",")
        )
        if reasons:
            print("  Operaciones que faltan en esa colección (juegos que las usan):")
            for feature, count in reasons.most_common():
                print(f"    {count:4d}  {feature}")
        hinted = sum(1 for c, d in results.values() if c == CATEGORIES[2] and d)
        if hinted:
            print(f"  Sin definición pero con un juego soportado en su mismo bloque de hiscore.dat: {hinted}")
        if args.detalle:
            for game, (category, detail) in sorted(results.items()):
                if category != READABLE:
                    print(f"    {game}: {category}{': ' + detail if detail else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
