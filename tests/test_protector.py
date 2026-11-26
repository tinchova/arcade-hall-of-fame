"""Imágenes del protector de pantalla y plantilla del LaunchAgent."""

import contextlib
import io
import plistlib
import shutil
import subprocess
import unittest
from pathlib import Path

from arcade_hall_of_fame import cli
from arcade_hall_of_fame.protector import MANIFEST, PENDING_FILE, file_names, generate

from .test_historial import HistoryTestCase, demo_file

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "contrib" / "macos" / "com.arcade-hall-of-fame.protector.plist.in"
INSTALLER = REPO / "contrib" / "macos" / "instalar_protector.sh"


class ProtectorTest(HistoryTestCase):
    def run_protector(self) -> str:
        self.db.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--base", str(self.db_path), "--definiciones", str(self.db_dir),
                             "--jugadores", str(self.players_path), "protector", "--salida", str(self.out),
                             "--carpeta", str(self.saves), "--tamano", "320x180",
                             "--dat", str(self.out.parent / "sin-dat")])
        self.assertEqual(code, 0)
        from arcade_hall_of_fame.storage import Database
        self.db = Database(self.db_path)
        return out.getvalue()

    def setUp(self):
        super().setUp()
        self.out = Path(self.db_path).parent / "protector"

    def pngs(self):
        return sorted(p.name for p in self.out.glob("*.png"))

    def test_genera_y_no_reescribe_sin_cambios(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.assertIn("3 imágenes nuevas", self.run_protector())
        self.assertEqual(self.pngs(), ["hof-001-ranking.png", "hof-002-records.png", "hof-003-juego-demo.png"])
        self.assertTrue((self.out / MANIFEST).is_file())
        stamps = {p.name: p.stat().st_mtime_ns for p in self.out.glob("*.png")}
        self.assertIn("sin cambios en los datos", self.run_protector())
        self.assertEqual(stamps, {p.name: p.stat().st_mtime_ns for p in self.out.glob("*.png")})

    def test_con_cambios_solo_reescribe_lo_necesario_y_borra_lo_viejo(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.run_protector()
        (self.out / "ajeno.png").write_bytes(b"no es nuestro")
        (self.out / "hof-099-viejo.png").write_bytes(b"x")
        (self.out / "hof-001-ranking.png.part").write_bytes(b"x")
        self.write("demo", demo_file([(950, "QZ"), (900, "XY"), (500, "AA")]))
        text = self.run_protector()
        self.assertIn("borradas", text)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         [MANIFEST, "ajeno.png", "hof-001-ranking.png", "hof-002-records.png",
                          "hof-003-juego-demo.png", PENDING_FILE])

    def test_imagen_borrada_se_regenera(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.run_protector()
        (self.out / "hof-003-juego-demo.png").unlink()
        self.assertIn("1 imágenes nuevas", self.run_protector())
        self.assertIn("hof-003-juego-demo.png", self.pngs())

    def test_generate_no_arma_pantallas_si_el_estado_no_cambio(self):
        self.out.mkdir(parents=True)
        calls = []

        def build():
            calls.append(1)
            return []

        generate(build, self.out, 64, 36, "estado-1")
        (self.out / "hof-001-x.png").write_bytes(b"")  # para que el manifiesto no esté vacío
        manifest = (self.out / MANIFEST).read_text(encoding="utf-8").replace('"archivos": {}', '"archivos": {"hof-001-x.png": "h"}')
        (self.out / MANIFEST).write_text(manifest, encoding="utf-8")
        report = generate(build, self.out, 64, 36, "estado-1")
        self.assertTrue(report.skipped)
        self.assertEqual(len(calls), 1)

    def test_lista_de_records_sin_leer(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.assertIn("lista de récords sin leer actualizada", self.run_protector())
        self.assertIn("No hay récords sin leer", (self.out / PENDING_FILE).read_text(encoding="utf-8"))
        self.write("sinlectura", b"\x01\x02\x03")
        self.assertIn("lista de récords sin leer actualizada", self.run_protector())
        text = (self.out / PENDING_FILE).read_text(encoding="utf-8")
        self.assertIn("sinlectura", text)
        self.assertIn("sin definición", text)
        self.assertNotIn("demo ", text)
        self.assertNotIn("lista de récords", self.run_protector())  # sin cambios, no se reescribe
        self.assertNotIn(PENDING_FILE, self.pngs())

    def test_nombres_de_archivo(self):
        from arcade_hall_of_fame.ui.screens import Screen

        screens = [Screen("ranking", "", "", (), []), Screen("juego:Bubl_Bobl", "", "", (), [])]
        self.assertEqual(file_names(screens), ["hof-001-ranking.png", "hof-002-juego-bubl-bobl.png"])


class LaunchAgentTest(unittest.TestCase):
    def render(self) -> dict:
        values = {
            "@PYTHON@": "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13",
            "@REPO@": "/Users/ejemplo/arcade-hall-of-fame",
            "@PARTIDAS@": "/Users/ejemplo/Documents/RetroArch/saves/FinalBurn Neo/fbneo",
            "@HISCORE_DAT@": "/Users/ejemplo/Documents/RetroArch/system/fbneo/hiscore.dat",
            "@GAMELIST@": "/Users/ejemplo/ES-DE/gamelists/fbneo/gamelist.xml",
            "@SALIDA@": "/Users/ejemplo/Library/Application Support/arcade-hall-of-fame/protector",
            "@LOG@": "/Users/ejemplo/Library/Logs/arcade-hall-of-fame-protector.log",
        }
        text = TEMPLATE.read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace(key, value)
        self.assertNotIn("@", text.split("-->", 1)[1])
        return plistlib.loads(text.encode("utf-8"))

    def test_plantilla_valida_con_watchpaths(self):
        plist = self.render()
        self.assertEqual(plist["Label"], "com.arcade-hall-of-fame.protector")
        self.assertEqual(plist["WatchPaths"], ["/Users/ejemplo/Documents/RetroArch/saves/FinalBurn Neo/fbneo"])
        self.assertNotIn("StartInterval", plist)  # solo cuando cambian las partidas
        self.assertTrue(plist["RunAtLoad"])
        self.assertEqual(plist["ProgramArguments"][1:4], ["-m", "arcade_hall_of_fame", "protector"])
        self.assertEqual(plist["EnvironmentVariables"]["PYTHONPATH"], "/Users/ejemplo/arcade-hall-of-fame/src")

    @unittest.skipUnless(shutil.which("sh"), "sin sh")
    def test_script_de_instalacion_es_sintacticamente_valido(self):
        result = subprocess.run(["sh", "-n", str(INSTALLER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
