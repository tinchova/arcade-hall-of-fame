"""Imágenes del protector de pantalla y plantilla del LaunchAgent."""

import contextlib
import io
import json
import plistlib
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from arcade_hall_of_fame import cli, protector
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
        # ES-DE abierto: los sobrantes quedan como relleno (igual en cualquier sistema).
        patcher = mock.patch.object(protector, "esde_running", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def pngs(self):
        return sorted(p.name for p in self.out.glob("*.png"))

    def test_genera_y_no_reescribe_sin_cambios(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.assertIn("3 imágenes nuevas", self.run_protector())
        self.assertEqual(self.pngs(), ["hof-juego-demo.png", "hof-ranking.png", "hof-records.png"])
        self.assertTrue((self.out / MANIFEST).is_file())
        stamps = {p.name: p.stat().st_mtime_ns for p in self.out.glob("*.png")}
        self.assertIn("sin cambios en los datos", self.run_protector())
        self.assertEqual(stamps, {p.name: p.stat().st_mtime_ns for p in self.out.glob("*.png")})

    def test_con_cambios_solo_reescribe_lo_necesario_y_borra_lo_viejo(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.run_protector()
        (self.out / "ajeno.png").write_bytes(b"no es nuestro")
        (self.out / "hof-viejo.png").write_bytes(b"x")
        (self.out / "hof-ranking.png.part").write_bytes(b"x")
        self.write("demo", demo_file([(950, "QZ"), (900, "XY"), (500, "AA")]))
        text = self.run_protector()
        # El sobrante no se borra (ES-DE está abierto y puede tenerlo en su lista): queda como está.
        self.assertIn("0 borradas,", text)
        self.assertIn("1 sobrante queda como relleno", text)
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         sorted([MANIFEST, "ajeno.png", "hof-juego-demo.png", "hof-ranking.png", "hof-records.png",
                                 "hof-viejo.png", PENDING_FILE]))
        self.assertEqual((self.out / "hof-viejo.png").read_bytes(), b"x")  # no repite el ranking
        self.assertIn("hof-viejo.png", json.loads((self.out / MANIFEST).read_text(encoding="utf-8"))["relleno"])
        self.assertIn("sin cambios en los datos", self.run_protector())
        self.assertIn("1 borrada,", self.run_protector("--compactar"))
        self.assertEqual(sorted(p.name for p in self.out.iterdir()),
                         sorted([MANIFEST, "ajeno.png", "hof-juego-demo.png", "hof-ranking.png", "hof-records.png",
                                 PENDING_FILE]))
        self.assertEqual(json.loads((self.out / MANIFEST).read_text(encoding="utf-8"))["relleno"], {})

    def test_relleno_se_borra_pasados_10_minutos(self):
        self.out.mkdir(parents=True)
        screens = [Screen("ranking", "A", "", (), []), Screen("records", "B", "", (), []),
                   Screen("juego:x", "C", "", (), [])]
        generate(lambda: screens, self.out, 64, 36, "e1", esde_running=True, now=1000)
        old = (self.out / "hof-juego-x.png").read_bytes()
        # Un cambio de orden no deja sobrantes ni reescribe nada.
        report = generate(lambda: [screens[2], screens[0], screens[1]], self.out, 64, 36, "e2",
                          esde_running=True, now=1000)
        self.assertEqual((report.written, report.removed, report.filled), ([], [], []))
        # El juego deja de mostrarse: queda como está (no se reescribe con el ranking).
        report = generate(lambda: screens[:2], self.out, 64, 36, "e3", esde_running=True, now=1000)
        self.assertEqual((report.removed, report.filled), ([], ["hof-juego-x.png"]))
        self.assertEqual((self.out / "hof-juego-x.png").read_bytes(), old)
        # Sin cambios y antes de los 10 minutos: no se hace nada.
        self.assertTrue(generate(lambda: screens[:2], self.out, 64, 36, "e3", esde_running=True, now=1500).skipped)
        report = generate(lambda: screens[:1], self.out, 64, 36, "e4", esde_running=True, now=1500)
        self.assertEqual((report.removed, report.filled), ([], ["hof-records.png"]))
        # Pasados 10 minutos, aunque los datos no cambiaron, se borra el relleno vencido; el más nuevo queda.
        report = generate(lambda: screens[:1], self.out, 64, 36, "e4", esde_running=True, now=1700)
        self.assertEqual((report.skipped, report.removed, report.filled), (False, ["hof-juego-x.png"], []))
        self.assertTrue((self.out / "hof-records.png").exists())
        self.assertEqual(json.loads((self.out / MANIFEST).read_text(encoding="utf-8"))["relleno"],
                         {"hof-records.png": 1500})
        # Vuelve a mostrarse: deja de ser relleno.
        generate(lambda: screens[:2], self.out, 64, 36, "e5", esde_running=True, now=1700)
        self.assertEqual(json.loads((self.out / MANIFEST).read_text(encoding="utf-8"))["relleno"], {})

    def test_sin_es_de_abierto_los_sobrantes_se_borran_enseguida(self):
        self.out.mkdir(parents=True)
        screens = [Screen("ranking", "A", "", (), []), Screen("juego:x", "C", "", (), [])]
        generate(lambda: screens, self.out, 64, 36, "e1", esde_running=True)
        report = generate(lambda: screens[:1], self.out, 64, 36, "e2", esde_running=True)
        self.assertEqual(report.filled, ["hof-juego-x.png"])
        # ES-DE se cerró: aunque los datos no cambiaron, el relleno se borra.
        report = generate(lambda: screens[:1], self.out, 64, 36, "e2", esde_running=False)
        self.assertEqual((report.skipped, report.removed), (False, ["hof-juego-x.png"]))
        self.assertTrue(generate(lambda: screens[:1], self.out, 64, 36, "e2", esde_running=False).skipped)

    def test_migracion_desde_nombres_numerados(self):
        self.out.mkdir(parents=True)
        old = {"hof-001-ranking.png": "a", "hof-002-records.png": "b", "hof-003-juego-x.png": "c"}
        for name in list(old) + ["hof-004-ranking.png"]:
            (self.out / name).write_bytes(b"viejo")
        (self.out / MANIFEST).write_text(json.dumps({"estado": "viejo", "archivos": old, "arranque": "1",
                                                     "relleno": {"hof-004-ranking.png": "a"}}), encoding="utf-8")
        screens = [Screen("ranking", "A", "", (), []), Screen("records", "B", "", (), []),
                   Screen("juego:x", "C", "", (), [])]
        # Con ES-DE abierto, los numerados quedan como relleno (a lo sumo hasta pasados 10 minutos).
        report = generate(lambda: screens, self.out, 64, 36, "e1", esde_running=True, now=0)
        self.assertEqual(report.filled, sorted(old) + ["hof-004-ranking.png"])
        report = generate(lambda: screens, self.out, 64, 36, "e1", esde_running=True, now=601)
        self.assertEqual(len(report.removed), 4)
        self.assertEqual(sorted(p.name for p in self.out.glob("*.png")),
                         ["hof-juego-x.png", "hof-ranking.png", "hof-records.png"])
        self.assertNotIn("arranque", json.loads((self.out / MANIFEST).read_text(encoding="utf-8")))

    def test_imagen_borrada_se_regenera(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.run_protector()
        (self.out / "hof-juego-demo.png").unlink()
        self.assertIn("1 imagen nueva o cambiada, 2 iguales, 0 borradas", self.run_protector())
        self.assertIn("hof-juego-demo.png", self.pngs())

    def test_generate_no_arma_pantallas_si_el_estado_no_cambio(self):
        self.out.mkdir(parents=True)
        calls = []

        def build():
            calls.append(1)
            return []

        generate(build, self.out, 64, 36, "estado-1")
        (self.out / "hof-x.png").write_bytes(b"")  # para que el manifiesto no esté vacío
        manifest = (self.out / MANIFEST).read_text(encoding="utf-8").replace('"archivos": {}', '"archivos": {"hof-x.png": "h"}')
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
        self.assertNotIn("hof-juego-solotop.png", self.pngs())  # sin nombre: no se muestra
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
        self.assertIn("hof-juego-solotop.png", self.pngs())
        self.assertIn("No hay récords sin nombre", (self.out / PENDING_FILE).read_text(encoding="utf-8"))
        self.assertIn("sin cambios en los datos", self.run_protector())  # mismas opciones que el protector
        text = self.run_cli("nombrar", "solotop", "--quitar", "--protector", str(self.out))
        self.assertIn("1 sobrante queda como relleno", text)  # ES-DE abierto: se borra más tarde
        # Sin carpeta del protector, nombrar no crea nada.
        missing = self.out.parent / "no-existe"
        self.run_cli("nombrar", "solotop", "NC", "--protector", str(missing))
        self.assertFalse(missing.exists())

    def test_qr_solo_con_records_sin_nombre(self):
        urls = ["http://192.168.1.5:47474", "http://arcade.local:47474"]
        patcher = mock.patch("arcade_hall_of_fame.direccion.page_urls", return_value=urls)
        patcher.start()
        self.addCleanup(patcher.stop)
        protector.esde_running.return_value = False  # los sobrantes se borran enseguida
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.run_protector("--web-puerto", "47474")
        self.assertNotIn("hof-web.png", self.pngs())  # todos con iniciales: sin QR
        self.write("solotop", bytes([0x14, 0x00]))
        self.run_protector("--web-puerto", "47474")
        self.assertIn("hof-web.png", self.pngs())
        screens = cli.build_screens_for_protector(cli.build_parser().parse_args(
            ["--base", str(self.db_path), "--definiciones", str(self.db_dir), "--jugadores", str(self.players_path),
             "protector", "--salida", str(self.out), "--dat", str(self.out.parent / "sin-dat"),
             "--web-puerto", "47474"]), self.db)
        web = screens[-1]
        self.assertEqual((web.key, web.title, web.subtitle), ("web", "RECORD SIN NOMBRE", "SOLOTOP 1400"))
        self.assertEqual(web.notes[0][0], "ESCANEA PARA PONER TU NOMBRE")
        self.assertEqual(web.notes[1][0], "192.168.1.5:47474")
        self.assertTrue(web.qr)
        # Con nombre, la pantalla deja de generarse y la imagen se borra como cualquier sobrante.
        text = self.run_cli("nombrar", "solotop", "NC", "--protector", str(self.out))
        self.assertIn("1 borrada", text)
        self.assertNotIn("hof-web.png", self.pngs())

    def test_qr_nombra_hasta_tres_records_y_el_resto(self):
        from arcade_hall_of_fame.naming import UnnamedRecord
        from arcade_hall_of_fame.names import GameNames

        missing = [UnnamedRecord(g, s, 1, "") for g, s in
                   [("mspacman", "18310"), ("puckman", "9000"), ("galaga", "50"), ("dkong", "7"), ("frogger", "1")]]
        with mock.patch("arcade_hall_of_fame.direccion.page_urls", return_value=["http://10.0.0.2:1"]),                 mock.patch.object(cli, "unnamed_records", return_value=missing):
            web = cli.web_screen(1, self.db, GameNames())
            self.assertEqual(web.title, "RECORDS SIN NOMBRE")
            self.assertEqual(web.subtitle, "MSPACMAN 18310, PUCKMAN 9000, GALAGA 50 +2")
            self.assertIsNone(cli.web_screen(None, self.db))
        with mock.patch.object(cli, "unnamed_records", return_value=[]):
            self.assertIsNone(cli.web_screen(1, self.db))

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

        screens = [Screen("ranking", "", "", (), []), Screen("ranking", "", "", (), []),
                   Screen("juego:Bubl_Bobl", "", "", (), []), Screen("mosaico:2", "", "", (), []),
                   Screen("web", "", "", (), [])]
        self.assertEqual(file_names(screens), ["hof-ranking.png", "hof-ranking-2.png", "hof-juego-bubl-bobl.png",
                                               "hof-mosaico-2.png", "hof-web.png"])


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
