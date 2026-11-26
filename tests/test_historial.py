"""Escaneo, historial SQLite, clasificación y comando de línea con datos sintéticos."""

import contextlib
import hashlib
import io
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from arcade_hall_of_fame import cli
from arcade_hall_of_fame.hi2txt import DefinitionLibrary
from arcade_hall_of_fame.hi2txt.defaults import FactoryTables
from arcade_hall_of_fame.models import ConfigError, FormatError, SourceReadError
from arcade_hall_of_fame.players import Players
from arcade_hall_of_fame.rankings import leaders, player_ranking, recent_records
from arcade_hall_of_fame.scanner import (REASON_INCOMPATIBLE, REASON_NO_DEFINITION, REASON_NOT_IN_HISCORE_DAT,
                                         REASON_UNSUPPORTED, scan, unreadable_reason)
from arcade_hall_of_fame.storage import SCHEMA, Database

from .synthetic import DEMO_BCD, xml

LETTERS = {c: 0x0A + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
LETTERS.update({" ": 0x24, ".": 0x2A})


def bcd(value: int) -> bytes:
    """Puntuación de 3 bytes del formato sintético DEMO_BCD (menor peso primero)."""
    digits = [int(d) for d in reversed(str(value))]
    return bytes(digits + [0x24] * (3 - len(digits)))


def demo_file(rows, top=None) -> bytes:
    """Construye el archivo sintético de DEMO_BCD a partir de 3 filas (puntos, iniciales)."""
    scores = b"".join(bcd(s) for s, _ in rows)
    names = b"".join(bytes(LETTERS[c] for c in n) for _, n in rows)
    return scores + names + bcd(top if top is not None else max(s for s, _ in rows))


# Juego sintético sin iniciales: solo guarda el máximo.
DEMO_TOP_ONLY = xml("""
  <structure file=".hi"><check><size>2</size></check>
    <elt size="2" type="int" id="SCORE" base="16"/></structure>
  <output><table><column id="RANK" src="index" format="+1"/><column id="SCORE"/></table></output>
""")

# Tabla de fábrica sintética de "demo", en el formato de db_defaults.
DEMO_FACTORY = b"""<hi2txt><table><col>RANK</col><col>SCORE</col><col>NAME</col>
<row><cell>1</cell><cell>500</cell><cell>AA</cell></row>
<row><cell>2</cell><cell>400</cell><cell>BB</cell></row>
<row><cell>3</cell><cell>300</cell><cell>CC</cell></row></table></hi2txt>"""

FACTORY = [(500, "AA"), (400, "BB"), (300, "CC")]


class HistoryTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.saves = root / "saves"
        self.saves.mkdir()
        db_dir = root / "defs" / "db"
        db_dir.mkdir(parents=True)
        (db_dir / "demo.xml").write_bytes(DEMO_BCD)
        (db_dir / "democlon.xml").write_bytes(xml('<sameas id="demo"/>'))
        (db_dir / "solotop.xml").write_bytes(DEMO_TOP_ONLY)
        defaults = root / "defs" / "db_defaults"
        defaults.mkdir()
        (defaults / "demo.xml").write_bytes(DEMO_FACTORY)
        (defaults / "democlon.xml").write_bytes(xml('<sameas id="demo"/>'))
        self.db_dir = db_dir
        self.db_path = root / "datos" / "historial.sqlite3"
        self.players_path = root / "datos" / "jugadores.json"
        self.db = Database(self.db_path)
        self.addCleanup(lambda: self.db.close())
        self.library = DefinitionLibrary(db_dir)
        self.factory = FactoryTables(defaults)
        self.clock = iter(f"2026-11-25T10:{m:02d}:00+00:00" for m in range(60))

    def write(self, game: str, data: bytes) -> None:
        (self.saves / f"{game}.hi").write_bytes(data)

    def scan(self, regions=None):
        return scan(self.saves, self.db, self.library, self.factory, "rev-prueba", regions, now=lambda: next(self.clock))

    def count(self, table: str) -> int:
        return self.db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class ScanTest(HistoryTestCase):
    def test_primer_escaneo_es_linea_base_y_repetir_no_duplica(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        report = self.scan()
        self.assertEqual((report.new_observations, report.records), (["demo"], []))
        for _ in range(3):
            report = self.scan()
            self.assertEqual(report.unchanged, ["demo"])
        self.assertEqual((self.count("observations"), self.count("entries"), self.count("record_events")), (1, 3, 0))
        self.assertEqual(self.count("scans"), 4)

    def test_record_batido_por_otra_persona(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.scan()
        self.write("demo", demo_file([(950, "QZ"), (900, "XY"), (500, "AA")]))
        report = self.scan()
        self.assertEqual(report.records, [("demo", "900", "950", ["QZ"])])
        events = recent_records(self.db)
        self.assertEqual(events[0]["previous_holders"], ["XY"])
        self.assertEqual(events[0]["new_holders"], ["QZ"])
        self.assertEqual(events[0]["detected_utc"], "2026-11-25T10:04:00+00:00")  # 3 marcas por escaneo
        self.assertEqual([(r.initials, r.count) for r in player_ranking(self.db)], [("QZ", 1)])

    def test_mejora_propia_genera_evento(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.scan()
        self.write("demo", demo_file([(990, "XY"), (900, "XY"), (500, "AA")]))
        self.assertEqual(self.scan().records, [("demo", "900", "990", ["XY"])])

    def test_empate_sin_subir_no_es_record_y_ambos_suman(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.scan()
        self.write("demo", demo_file([(900, "XY"), (900, "QZ"), (500, "AA")]))
        report = self.scan()
        self.assertEqual((report.new_observations, report.records), (["demo"], []))
        self.assertEqual(leaders(self.db)[0].holders, ("QZ", "XY"))

    def test_maximo_menor_queda_pendiente_hasta_aceptar(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.scan()
        self.write("demo", demo_file(FACTORY))  # p. ej., se borró la memoria
        report = self.scan()
        self.assertEqual(report.pending, ["demo"])
        self.assertEqual(leaders(self.db)[0].holders, ("XY",))  # la tabla vigente no cambia
        self.assertEqual(self.scan().unchanged, ["demo"])  # el pendiente no se duplica
        pending = self.db.pending("demo")
        self.db.accept("demo", pending["id"])
        self.assertIsNone(self.db.pending("demo"))
        self.assertEqual(leaders(self.db)[0].reason, "el máximo es una entrada de fábrica")

    def test_restauracion_a_b_a(self):
        a = demo_file([(900, "XY"), (500, "AA"), (400, "BB")])
        b = demo_file([(950, "QZ"), (900, "XY"), (500, "AA")])
        for data in (a, b, a):
            self.write("demo", data)
            self.scan()
        self.assertEqual(self.count("observations"), 3)
        self.assertIsNotNone(self.db.pending("demo"))
        self.assertEqual(leaders(self.db)[0].holders, ("QZ",))

    def test_entradas_de_fabrica_y_alias(self):
        self.write("democlon", demo_file(FACTORY))
        self.scan()
        entries = self.db.entries(self.db.source("democlon")["current_observation_id"])
        self.assertTrue(all(e["factory"] for e in entries))
        self.assertEqual(player_ranking(self.db), [])

    def test_juego_sin_iniciales_no_suma(self):
        self.write("solotop", bytes([0x14, 0x00]))
        self.scan()
        leader = leaders(self.db)[0]
        self.assertEqual((leader.top_score, leader.holders, leader.reason), ("1400", (), "el juego no guarda iniciales"))

    def test_no_legibles_sin_duplicar_y_sin_tabla(self):
        self.write("desconocido", b"\x00\x01")
        self.write("demo", b"\x00" * 5)  # tamaño incorrecto
        report = self.scan()
        self.assertEqual(report.errors, [])
        self.assertEqual(sorted(report.unreadable),
                         [("demo", REASON_INCOMPATIBLE), ("desconocido", REASON_NO_DEFINITION)])
        self.assertEqual(report.new_unreadable, ["demo", "desconocido"])
        report = self.scan()
        self.assertEqual(report.new_unreadable, [])
        self.assertEqual(len(report.unreadable), 2)
        self.assertEqual(self.count("observations"), 0)
        self.assertEqual(self.count("unreadable"), 2)
        self.assertIn("no hay definición", self.db.source("desconocido")["last_error"])
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.assertEqual(self.scan().new_observations, ["demo"])
        self.assertIsNone(self.db.source("demo")["last_error"])
        self.assertEqual([r["game"] for r in self.db.unreadable()], ["desconocido"])

    def test_no_legible_registra_aparicion_y_modificacion(self):
        path = self.saves / "sinlectura.hi"
        self.write("sinlectura", b"\x01\x02\x03")
        os.utime(path, (1_790_000_000, 1_790_000_000))
        self.scan()
        row = self.db.unreadable()[0]
        self.assertEqual((row["game"], row["reason"], row["detail"]), ("sinlectura", REASON_NO_DEFINITION, ""))
        first_seen = row["first_seen_utc"]
        self.assertEqual(row["file_mtime_utc"], "2026-09-21T14:13:20+00:00")
        self.assertIsNone(row["file_changed_utc"])
        self.scan()
        self.assertIsNone(self.db.unreadable()[0]["file_changed_utc"])
        os.utime(path, (1_790_000_600, 1_790_000_600))
        self.scan()
        row = self.db.unreadable()[0]
        self.assertEqual(row["first_seen_utc"], first_seen)
        self.assertEqual(row["file_mtime_utc"], "2026-09-21T14:23:20+00:00")
        self.assertGreater(row["file_changed_utc"], first_seen)
        self.assertEqual(path.read_bytes(), b"\x01\x02\x03")

    def test_motivos_de_no_lectura(self):
        (self.db_dir / "pendiente.xml").write_bytes(xml("""
  <structure file=".hi"><elt size="2" type="int" id="SCORE" base="256"/></structure>
  <output><table><column id="SCORE"/></table></output>"""))
        (self.db_dir / "otroarchivo.xml").write_bytes(xml("""
  <structure file="nvram"><elt size="2" type="int" id="SCORE"/></structure>
  <output><table><column id="SCORE"/></table></output>"""))
        self.write("pendiente", b"\x00\x01")
        self.write("otroarchivo", b"\x00\x01")
        self.scan()
        reasons = {r["game"]: (r["reason"], r["detail"]) for r in self.db.unreadable()}
        self.assertEqual(reasons["pendiente"][0], REASON_UNSUPPORTED)
        self.assertIn("base", reasons["pendiente"][1])
        self.assertEqual(reasons["otroarchivo"][0], REASON_INCOMPATIBLE)
        self.assertIn("otro archivo", reasons["otroarchivo"][1])
        # Un error de lectura o de datos no es "no legible": puede resolverse solo.
        self.assertIsNone(unreadable_reason(FormatError("demo: la tabla está vacía")))
        self.assertIsNone(unreadable_reason(SourceReadError("cambió durante la lectura")))

    def test_regiones_de_hiscore_dat(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        report = self.scan(regions={})
        self.assertEqual(report.unreadable, [("demo", REASON_NOT_IN_HISCORE_DAT)])
        self.assertIn("no figura en hiscore.dat", self.db.source("demo")["last_error"])

    def test_base_de_la_version_1_se_actualiza(self):
        path = Path(self.db_path).with_name("v1.sqlite3")
        conn = sqlite3.connect(str(path))
        conn.executescript(SCHEMA)
        conn.execute("PRAGMA user_version = 1")
        conn.commit()
        conn.close()
        db = Database(path)
        self.addCleanup(db.close)
        self.assertEqual(db.unreadable(), [])
        self.assertEqual(db.conn.execute("PRAGMA user_version").fetchone()[0], 2)

    def test_originales_intactos(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        path = self.saves / "demo.hi"
        before = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        self.scan()
        self.scan()
        after = (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(before, after)
        self.assertEqual(sorted(p.name for p in self.saves.iterdir()), ["demo.hi"])

    def test_base_dentro_de_la_carpeta_de_partidas(self):
        db = Database(self.saves / "historial.sqlite3")
        self.addCleanup(db.close)
        with self.assertRaises(SourceReadError):
            scan(self.saves, db, self.library, self.factory, "rev")


class RankingTest(HistoryTestCase):
    def test_cuenta_juegos_no_puntos_y_empates_comparten_posicion(self):
        defs = {f"juego{i}": DEMO_BCD for i in range(1, 5)}
        for name, data in defs.items():
            (self.db_dir / f"{name}.xml").write_bytes(data)
        self.write("juego1", demo_file([(100, "AB"), (50, "CD"), (10, "EF")]))
        self.write("juego2", demo_file([(200, "AB"), (150, "CD"), (10, "EF")]))
        self.write("juego3", demo_file([(999, "CD"), (50, "AB"), (10, "EF")]))
        self.write("juego4", demo_file([(300, "EF"), (300, "GH"), (10, "AB")]))
        self.scan()
        ranking = [(r.position, r.initials, r.count) for r in player_ranking(self.db)]
        self.assertEqual(ranking, [(1, "AB", 2), (2, "CD", 1), (2, "EF", 1), (2, "GH", 1)])


class PlayersTest(HistoryTestCase):
    def test_iniciales_de_una_persona_cuentan_una_vez_por_juego(self):
        for name in ("juego1", "juego2"):
            (self.db_dir / f"{name}.xml").write_bytes(DEMO_BCD)
        self.write("juego1", demo_file([(100, "NC"), (100, "N."), (10, "EF")]))
        self.write("juego2", demo_file([(200, "N."), (150, "CD"), (10, "EF")]))
        self.scan()
        players = Players.from_data({"jugadores": {"Ana": ["NC", "N."]}})
        self.assertEqual(leaders(self.db, players)[0].holders, ("Ana",))
        ranking = [(r.initials, r.count) for r in player_ranking(self.db, players)]
        self.assertEqual(ranking, [("Ana", 2)])
        self.assertEqual([(r.initials, r.count) for r in player_ranking(self.db)], [("N.", 2), ("NC", 1)])

    def test_archivo_opcional_y_errores(self):
        self.assertEqual(Players.load(self.players_path).mapping, {})
        self.players_path.write_text('{"jugadores": {"Ana": ["ANA"], "Otra": ["ANA"]}}', encoding="utf-8")
        with self.assertRaisesRegex(ConfigError, "ANA"):
            Players.load(self.players_path)
        self.players_path.write_text("{no es json", encoding="utf-8")
        with self.assertRaises(ConfigError):
            Players.load(self.players_path)
        with self.assertRaises(ConfigError):
            Players.from_data({"jugadores": {"Ana": "ANA"}})


class CliTest(HistoryTestCase):
    def run_cli(self, *args) -> str:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(["--base", str(self.db_path), "--definiciones", str(self.db_dir),
                             "--jugadores", str(self.players_path), *args])
        self.assertIn(code, (0, 1))
        return out.getvalue()

    def test_comandos(self):
        self.db.close()
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.write("solotop", bytes([0x14, 0x00]))
        self.assertIn("nuevos estados: 2", self.run_cli("escanear", str(self.saves)))
        self.assertIn("primer escaneo es la línea base", self.run_cli("records"))
        self.write("demo", demo_file([(950, "QZ"), (900, "XY"), (500, "AA")]))
        self.assertIn("Récord batido en demo: 900 -> 950 (QZ)", self.run_cli("escanear", str(self.saves)))
        ranking = self.run_cli("ranking")
        self.assertIn("QZ", ranking)
        self.assertIn("solotop (1400): el juego no guarda iniciales", ranking)
        table = self.run_cli("juego", "demo")
        self.assertIn("950", table)
        self.assertIn("fábrica", table)
        self.assertIn("XY", self.run_cli("records"))
        self.assertIn("No hay una tabla", self.run_cli("juego", "otro"))
        self.assertIn("no tiene estados pendientes", self.run_cli("aceptar", "demo"))
        self.players_path.write_text('{"jugadores": {"Quique": ["QZ"]}}', encoding="utf-8")
        self.assertIn("Quique", self.run_cli("ranking"))
        self.assertIn("Quique", self.run_cli("records"))
        self.db = Database(self.db_path)

    def test_pendientes(self):
        self.db.close()
        self.assertIn("No hay récords sin leer", self.run_cli("pendientes"))
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.write("sinlectura", b"\x01\x02\x03")
        self.assertIn("Récords que no se pueden leer: 1, 1 nuevos", self.run_cli("escanear", str(self.saves)))
        text = self.run_cli("pendientes", "--sin-marcar")
        self.assertIn("NUEVO  sinlectura", text)
        self.assertIn(REASON_NO_DEFINITION, text)
        self.assertNotIn("demo", text)
        self.assertIn("NUEVO  sinlectura", self.run_cli("pendientes"))  # el anterior no marcó
        self.assertNotIn("NUEVO  sinlectura", self.run_cli("pendientes"))
        path = self.saves / "sinlectura.hi"
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 60_000_000_000))
        self.run_cli("escanear", str(self.saves))
        self.assertIn("CAMBIÓ  sinlectura", self.run_cli("pendientes"))
        self.db = Database(self.db_path)


if __name__ == "__main__":
    unittest.main()
