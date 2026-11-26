"""Imágenes del protector de pantalla y plantilla del LaunchAgent."""

import contextlib
import io
import json
import plistlib
import shutil
import subprocess
import unittest
from pathlib import Path

from arcade_hall_of_fame import cli
from arcade_hall_of_fame.protector import MANIFEST, PENDING_FILE, file_names, generate
from arcade_hall_of_fame.ui.screens import Screen

from .test_historial import HistoryTestCase, demo_file

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "contrib" / "macos" / "com.arcade-hall-of-fame.protector.plist.in"
INSTALLER = REPO / "contrib" / "macos" / "instalar_protector.sh"


class ProtectorTest(HistoryTestCase):
    def run_protector(self, *extra) -> str:
        self.db.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--base", str(self.db_path), "--definiciones", str(self.db_dir),
                             "--jugadores", str(self.players_path), "protector", "--salida", str(self.out),
                             "--carpeta", str(self.saves), "--tamano", "320x180",
                             "--dat", str(self.out.parent / "sin-dat"), *extra])
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
        # El sobrante no se borra (ES-DE puede tenerlo en su lista): queda como copia del ranking.
        self.assertIn("0 borradas,", text)
        self.assertIn("1 sobrante reescrita", text)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         [MANIFEST, "ajeno.png", "hof-001-ranking.png", "hof-002-records.png",
                          "hof-003-juego-demo.png", "hof-099-viejo.png", PENDING_FILE])
        ranking = (self.out / "hof-001-ranking.png").read_bytes()
        self.assertEqual((self.out / "hof-099-viejo.png").read_bytes(), ranking)
        self.assertIn("hof-099-viejo.png", json.loads((self.out / MANIFEST).read_text(encoding="utf-8"))["relleno"])
        self.assertIn("sin cambios en los datos", self.run_protector())
        self.assertIn("1 borrada,", self.run_protector("--compactar"))
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         [MANIFEST, "ajeno.png", "hof-001-ranking.png", "hof-002-records.png",
                          "hof-003-juego-demo.png", PENDING_FILE])
        self.assertEqual(json.loads((self.out / MANIFEST).read_text(encoding="utf-8"))["relleno"], {})

    def test_relleno_hasta_el_proximo_arranque(self):
        self.out.mkdir(parents=True)
        screens = [Screen("ranking", "A", "", (), []), Screen("records", "B", "", (), []),
                   Screen("juego:x", "C", "", (), [])]
        generate(lambda: screens, self.out, 64, 36, "e1", boot="arranque-1")
        report = generate(lambda: screens[:2], self.out, 64, 36, "e2", boot="arranque-1")
        self.assertEqual((report.removed, report.filled), ([], ["hof-003-juego-x.png"]))
        ranking = (self.out / "hof-001-ranking.png").read_bytes()
        self.assertEqual((self.out / "hof-003-juego-x.png").read_bytes(), ranking)
        # El ranking cambia: el relleno se actualiza con él.
        screens[0] = Screen("ranking", "Z", "", (), [])
        report = generate(lambda: screens[:2], self.out, 64, 36, "e3", boot="arranque-1")
        self.assertEqual(report.filled, ["hof-003-juego-x.png"])
        self.assertEqual((self.out / "hof-003-juego-x.png").read_bytes(), (self.out / "hof-001-ranking.png").read_bytes())
        # Arranque nuevo: aunque los datos no cambiaron, se borra el relleno.
        report = generate(lambda: screens[:2], self.out, 64, 36, "e3", boot="arranque-2")
        self.assertEqual((report.skipped, report.removed), (False, ["hof-003-juego-x.png"]))
        self.assertFalse((self.out / "hof-003-juego-x.png").exists())
        # Sin relleno, un arranque nuevo sin cambios no reescribe nada, pero anota el arranque.
        self.assertTrue(generate(lambda: screens[:2], self.out, 64, 36, "e3", boot="arranque-3").skipped)
        self.assertEqual(json.loads((self.out / MANIFEST).read_text(encoding="utf-8"))["arranque"], "arranque-3")
        report = generate(lambda: screens[1:2], self.out, 64, 36, "e4", boot="arranque-3")
        self.assertEqual((report.removed, report.filled), ([], ["hof-001-ranking.png", "hof-002-records.png"]))  # renumeradas

    def test_imagen_borrada_se_regenera(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.run_protector()
        (self.out / "hof-003-juego-demo.png").unlink()
        self.assertIn("1 imagen nueva o cambiada, 2 iguales, 0 borradas", self.run_protector())
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
        self.assertIn("lista de récords sin leer y sin nombre actualizada", self.run_protector())
        text = (self.out / PENDING_FILE).read_text(encoding="utf-8")
        self.assertIn("No hay récords sin leer", text)
        self.assertIn("No hay récords sin nombre", text)
        self.write("sinlectura", b"\x01\x02\x03")
        self.write("solotop", bytes([0x14, 0x00]))
        self.assertIn("lista de récords sin leer y sin nombre actualizada", self.run_protector())
        text = (self.out / PENDING_FILE).read_text(encoding="utf-8")
        self.assertIn("sinlectura", text)
        self.assertIn("sin definición", text)
        self.assertIn("Récords sin nombre: 1", text)
        self.assertIn("solotop  1400", text)
        self.assertNotIn("demo ", text)
        self.assertNotIn("hof-004-juego-solotop.png", self.pngs())  # sin nombre: no se muestra
        self.assertNotIn("lista de récords", self.run_protector())  # sin cambios, no se reescribe
        self.assertNotIn(PENDING_FILE, self.pngs())

    def test_nombrar_regenera_las_imagenes(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.write("solotop", bytes([0x14, 0x00]))
        self.run_protector()
        self.assertEqual(len(self.pngs()), 3)
        self.assertIn("Récords sin nombre: 1", (self.out / PENDING_FILE).read_text(encoding="utf-8"))
        text = self.run_cli("nombrar", "solotop", "NC", "--protector", str(self.out))
        self.assertIn("queda a nombre de NC", text)
        self.assertIn("4 imágenes nuevas o cambiadas", text)  # cambia la cantidad de juegos
        self.assertIn("hof-004-juego-solotop.png", self.pngs())
        self.assertIn("No hay récords sin nombre", (self.out / PENDING_FILE).read_text(encoding="utf-8"))
        self.assertIn("sin cambios en los datos", self.run_protector())  # mismas opciones que el protector
        text = self.run_cli("nombrar", "solotop", "--quitar", "--protector", str(self.out))
        self.assertIn("1 sobrante reescrita", text)  # sale de la rotación en el próximo arranque
        self.assertEqual((self.out / "hof-004-juego-solotop.png").read_bytes(),
                         (self.out / "hof-001-ranking.png").read_bytes())
        # Sin carpeta del protector, nombrar no crea nada.
        missing = self.out.parent / "no-existe"
        self.run_cli("nombrar", "solotop", "NC", "--protector", str(missing))
        self.assertFalse(missing.exists())

    def run_cli(self, *args) -> str:
        self.db.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--base", str(self.db_path), "--definiciones", str(self.db_dir),
                             "--jugadores", str(self.players_path), *args])
        self.assertEqual(code, 0)
        from arcade_hall_of_fame.storage import Database
        self.db = Database(self.db_path)
        return out.getvalue()

    def test_nombres_de_archivo(self):
        from arcade_hall_of_fame.ui.screens import Screen

        screens = [Screen("ranking", "", "", (), []), Screen("juego:Bubl_Bobl", "", "", (), [])]
        self.assertEqual(file_names(screens), ["hof-001-ranking.png", "hof-002-juego-bubl-bobl.png"])


class LaunchAgentTest(unittest.TestCase):
    def render(self, web: str = "") -> dict:
        values = {
            "@WEB@": web,
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
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 6, "Minute": 0})  # vencen destacados, rotan mosaicos
        self.assertEqual(plist["ProgramArguments"][1:4], ["-m", "arcade_hall_of_fame", "protector"])
        self.assertEqual(plist["EnvironmentVariables"]["PYTHONPATH"], "/Users/ejemplo/arcade-hall-of-fame/src")

    def test_plantilla_con_el_qr_de_la_pagina(self):
        plist = self.render("<string>--web-puerto</string><string>47474</string>")
        self.assertEqual(plist["ProgramArguments"][-2:], ["--web-puerto", "47474"])

    def test_plantilla_de_la_pagina_web(self):
        text = (TEMPLATE.parent / "com.arcade-hall-of-fame.web.plist.in").read_text(encoding="utf-8")
        for key, value in {"@PYTHON@": "/usr/bin/python3", "@REPO@": "/Users/ejemplo/r", "@PUERTO@": "47474",
                           "@GAMELIST@": "/Users/ejemplo/g.xml", "@LOG@": "/Users/ejemplo/web.log"}.items():
            text = text.replace(key, value)
        self.assertNotIn("@", text.split("-->", 1)[1])
        plist = plistlib.loads(text.encode("utf-8"))
        self.assertEqual(plist["Label"], "com.arcade-hall-of-fame.web")
        self.assertEqual(plist["ProgramArguments"][3:6], ["web", "--puerto", "47474"])
        self.assertTrue(plist["KeepAlive"])

    @unittest.skipUnless(shutil.which("sh"), "sin sh")
    def test_script_de_instalacion_es_sintacticamente_valido(self):
        for script in (INSTALLER, INSTALLER.parent / "instalar_web.sh", INSTALLER.parent / "instalar_esde.sh",
                       INSTALLER.parents[2] / "hof"):
            result = subprocess.run(["sh", "-n", str(script)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
