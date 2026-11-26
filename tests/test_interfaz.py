"""Partes no gráficas de la interfaz: fuente, pantallas, composición y PNG."""

import contextlib
import io
import struct
import unittest
import zlib
from pathlib import Path

from arcade_hall_of_fame import cli
from arcade_hall_of_fame.players import Players
from arcade_hall_of_fame.ui import pixelfont as pf
from arcade_hall_of_fame.ui.layout import GRID_COLS, GRID_LINES, layout, scale_for
from arcade_hall_of_fame.ui.raster import Raster
from arcade_hall_of_fame.ui.screens import BG, DIM, Column, Screen, build_screens

from .test_historial import FACTORY, HistoryTestCase, demo_file


class PixelFontTest(unittest.TestCase):
    def test_glifos_de_5x7_y_caracteres_basicos(self):
        for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,:-/!?()<>#%":
            self.assertIn(ch, pf.GLYPHS)
        for ch, pixels in pf.GLYPHS.items():
            self.assertTrue(all(0 <= x < pf.GLYPH_W and 0 <= y < pf.GLYPH_H for x, y in pixels), ch)

    def test_normalizar_tildes_y_desconocidos(self):
        self.assertEqual(pf.normalize("Salón ñandú"), "SALON NANDU")
        self.assertEqual(pf.normalize("A♥B"), "A?B")

    def test_recortar_y_medir(self):
        self.assertEqual(pf.fit("abcdef", 4), "ABC.")
        self.assertEqual(pf.fit("abc", 4), "ABC")
        self.assertEqual(pf.text_width("AB", 3), (2 * pf.ADVANCE - 1) * 3)

    def test_tramos_reconstruyen_el_glifo(self):
        for ch in pf.GLYPHS:
            pixels = {(x + i, y) for x, y, n in pf.runs(ch) for i in range(n)}
            self.assertEqual(pixels, set(pf.GLYPHS[ch]), ch)


class LayoutTest(unittest.TestCase):
    def screen(self, rows=2):
        columns = (Column("POS", 4), Column("PUNTOS", 8, "right"))
        data = [[(f"{i}.", DIM), (str(1000 * i), DIM)] for i in range(1, rows + 1)]
        return Screen("prueba", "Título largo de prueba", "SUB", columns, data, [("NOTA", DIM)], "VACIO", "1/2")

    def test_escala_y_limites(self):
        self.assertEqual(scale_for(1920, 1080), 4)
        self.assertEqual(scale_for(100, 100), 1)
        for size in ((1920, 1080), (1280, 720), (1024, 768), (640, 480)):
            ops = layout(self.screen(10), *size, "PIE", "9/9")
            s = scale_for(*size)
            for op in ops:
                if op[0] == "text":
                    _, x, y, text, _color, scale = op
                    self.assertGreaterEqual(x, 0)
                    self.assertLessEqual(x + pf.text_width(text, scale), size[0], (size, text))
                    self.assertLessEqual(y + pf.GLYPH_H * scale, size[1])
            self.assertLessEqual(GRID_LINES * pf.LINE * s, size[1])
            self.assertLessEqual(GRID_COLS * pf.ADVANCE * s, size[0])

    def test_filas_marcadas_para_la_animacion(self):
        ops = layout(self.screen(3), 1280, 720)
        self.assertEqual([op[1] for op in ops if op[0] == "row"], [0, 1, 2])
        self.assertEqual([op[1] for op in ops if op[0] == "endrow"], [0, 1, 2])
        texts = [op[3] for op in ops if op[0] == "text"]
        self.assertIn("TITULO LARGO DE", texts)  # el título largo ocupa dos líneas
        self.assertIn("PRUEBA", texts)
        self.assertIn("3000", texts)

    def test_pantalla_vacia_muestra_mensaje(self):
        texts = [op[3] for op in layout(self.screen(0), 1280, 720) if op[0] == "text"]
        self.assertIn("VACIO", texts)

    def test_fondo_negro_puro_y_contraste(self):
        from arcade_hall_of_fame.ui import screens as sc

        def luminance(color):
            channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
            return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

        def contrast(a, b):
            la, lb = sorted((luminance(a), luminance(b)), reverse=True)
            return (la + 0.05) / (lb + 0.05)

        self.assertEqual(BG, "#000000")
        for name in ("TITLE", "SUBTITLE", "HEADER", "HEADER_DIM", "TEXT", "DIM", "ALERT", "GOOD"):
            self.assertGreaterEqual(contrast(getattr(sc, name), BG), 4.5, name)
        for color in (sc.TEXT, sc.DIM, sc.GOOD) + sc.RANK_COLORS:  # filas sobre la banda del primer puesto
            self.assertGreaterEqual(contrast(color, sc.CARD), 4.5, color)
        raster = Raster(1280, 720).draw(layout(self.screen(), 1280, 720))
        border = {raster.pixel(x, y) for x in range(1280) for y in (0, 1, 2, 3, 719)}
        border |= {raster.pixel(x, y) for x in (0, 1, 2, 1279) for y in range(720)}
        self.assertEqual(border, {"#000000"})  # sin líneas de barrido ni otro color en los bordes

    def test_png_valido_y_pixeles(self):
        raster = Raster(320, 200).draw(layout(self.screen(), 320, 200))
        self.assertEqual(raster.pixel(0, 1), BG)
        png = raster.png()
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        width, height = struct.unpack(">II", png[16:24])
        self.assertEqual((width, height), (320, 200))
        start = png.index(b"IDAT") + 4
        length = struct.unpack(">I", png[start - 8:start - 4])[0]
        self.assertEqual(len(zlib.decompress(png[start:start + length])), (320 * 3 + 1) * 200)


class ScreensTest(HistoryTestCase):
    def test_secuencia_y_contenido(self):
        for i in range(1, 7):
            (self.db_dir / f"juego{i}.xml").write_bytes((self.db_dir / "demo.xml").read_bytes())
            self.write(f"juego{i}", demo_file([(100 * i, "AB"), (50, "CD"), (10, "EF")]))
        self.write("demo", demo_file(FACTORY))
        self.write("solotop", bytes([0x14, 0x00]))
        self.scan()
        screens = build_screens(self.db, Players())
        keys = [s.key for s in screens]
        self.assertEqual(keys[:2], ["ranking", "records"])
        self.assertEqual(keys.count("ranking"), 2)  # vuelve al ranking cada 4 juegos
        # demo (solo fábrica) y solotop (sin iniciales ni nombre) no aparecen
        self.assertEqual(len([k for k in keys if k.startswith("juego:")]), 6)
        ranking = screens[0]
        self.assertEqual(ranking.rows[0][1][0], "AB")
        self.assertEqual(ranking.rows[0][2][0], "6")
        self.assertEqual(ranking.notes, [])
        by_key = {s.key: s for s in screens}
        self.assertNotIn("juego:demo", by_key)
        self.assertNotIn("juego:solotop", by_key)
        self.assertEqual(by_key["records"].rows, [])
        self.assertEqual(by_key["records"].columns[3].label, "JUGADOR")
        shown = {s.key: s for s in build_screens(self.db, Players(), show_no_initials=True)}
        self.assertNotIn("juego:demo", shown)  # la fábrica no se muestra nunca
        self.assertEqual([c[0] for c in shown["juego:solotop"].rows[0][:3]], ["1.", "1400", "???"])
        self.assertFalse(shown["juego:solotop"].highlight_first)
        self.assertEqual(shown["juego:solotop"].notes[0][0], "??? SIN NOMBRE: NO SUMA AL RANKING")
        self.assertEqual(shown["ranking"].notes[0][0], "1 RECORD SIN NOMBRE (???): NO SUMAN")
        for screen in shown.values():  # ninguna nota ni encabezado se recorta
            self.assertTrue(all(len(text) <= 42 for text, _ in screen.notes))
            self.assertTrue(all(len(c.label) <= c.width for c in screen.columns))
        self.assertTrue(screens[0].status.startswith("6 JUEGOS  ULTIMO ESCANEO "))

    def test_singular_con_un_juego(self):
        from arcade_hall_of_fame.ui.screens import plural

        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.scan()
        self.assertTrue(build_screens(self.db, Players())[0].status.startswith("1 JUEGO  ULTIMO ESCANEO "))
        self.assertEqual([plural(n, "JUEGO", "JUEGOS") for n in (0, 1, 2)], ["0 JUEGOS", "1 JUEGO", "2 JUEGOS"])

    def test_fabrica_oculta_y_records_con_nombre(self):
        from arcade_hall_of_fame.naming import assign_name

        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        self.scan()  # línea base
        self.write("solotop", bytes([0x14, 0x00]))
        self.scan()  # juego nuevo: su primer récord cuenta, pero no tiene nombre
        screens = {s.key: s for s in build_screens(self.db, Players())}
        demo = screens["juego:demo"]
        self.assertEqual([[c[0] for c in row[:3]] for row in demo.rows], [["1.", "900", "XY"]])  # sin fábrica
        self.assertTrue(demo.highlight_first)
        self.assertNotIn("juego:solotop", screens)
        self.assertEqual(screens["records"].rows, [])
        shown = {s.key: s for s in build_screens(self.db, Players(), show_no_initials=True)}
        self.assertEqual([c[0] for c in shown["records"].rows[0][1:]], ["solotop", "1400", "???"])
        assign_name(self.db, "solotop", "NC", "2026-11-25T12:00:00+00:00")
        screens = {s.key: s for s in build_screens(self.db, Players.from_data({"jugadores": {"Ana": ["NC"]}}))}
        self.assertEqual([c[0] for c in screens["juego:solotop"].rows[0][:3]], ["1.", "1400", "Ana"])
        self.assertTrue(screens["juego:solotop"].highlight_first)
        self.assertEqual([c[0] for c in screens["records"].rows[0][1:]], ["solotop", "1400", "Ana"])
        self.assertIn(["Ana", "1"], [[r[1][0], r[2][0]] for r in screens["ranking"].rows])

    def test_jugador_debajo_de_la_fabrica_conserva_su_posicion(self):
        self.write("demo", demo_file([(500, "AA"), (450, "QZ"), (300, "CC")]))
        self.scan()
        screen = {s.key: s for s in build_screens(self.db, Players())}["juego:demo"]
        self.assertEqual([[c[0] for c in row[:3]] for row in screen.rows], [["2.", "450", "QZ"]])
        self.assertFalse(screen.highlight_first)  # no es el récord del juego

    def test_ranking_paginado(self):
        for i in range(12):
            name = f"j{i:02d}"
            (self.db_dir / f"{name}.xml").write_bytes((self.db_dir / "demo.xml").read_bytes())
            initials = "ABCDEFGHIJKL"[i] * 2
            self.write(name, demo_file([(900, initials), (50, "CD"), (10, "EF")]))
        self.scan()
        screens = [s for s in build_screens(self.db, Players()) if s.key == "ranking"]
        self.assertEqual([s.page for s in screens[:2]], ["1/2", "2/2"])


class ScreenCommandTest(HistoryTestCase):
    def run_cli(self, *args) -> str:
        self.db.close()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["--base", str(self.db_path), "--definiciones", str(self.db_dir),
                             "--jugadores", str(self.players_path), *args,
                             "--dat", str(Path(self.db_path).parent / "sin-dat")])
        self.assertEqual(code, 0)
        from arcade_hall_of_fame.storage import Database
        self.db = Database(self.db_path)
        return out.getvalue()

    def test_capturas_y_modo_prueba(self):
        self.write("demo", demo_file([(900, "XY"), (500, "AA"), (400, "BB")]))
        out_dir = Path(self.db_path).parent / "capturas"
        text = self.run_cli("pantalla", "--carpeta", str(self.saves), "--capturas", str(out_dir), "--tamano", "640x360")
        self.assertIn("3 capturas", text)
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), ["juego-demo.png", "ranking.png", "records.png"])
        self.assertIn("Modo de prueba", self.run_cli("pantalla", "--prueba", "--tamano", "640x360"))


class NamesTest(unittest.TestCase):
    def test_limpieza_y_desambiguacion(self):
        from arcade_hall_of_fame.names import GameNames, clean

        self.assertEqual(clean("Bubble Bobble (Japan, Ver 0.1)"), "Bubble Bobble")
        self.assertEqual(clean("Splatterhouse (World, new version (SH3))"), "Splatterhouse")
        self.assertEqual(clean("Strikers 1945 III (World) / Strikers 1999"), "Strikers 1945 III / Strikers 1999")
        self.assertEqual(clean("(Hack)"), "(Hack)")
        dat = {"dd": "Double Dragon (World set 1)", "ddn": "Double Dragon (Neo-Geo)",
               "x1": "Juego X (set 1)", "x2": "Juego X (set 1)", "bb": "Bubble Bobble (Japan)"}
        gamelist = {"bb": "Bubble Bobble"}
        names = GameNames(gamelist, dat, {"solo": "Solo Label"})
        names.set_games(["dd", "ddn", "x1", "x2", "bb", "solo", "zip"])
        self.assertEqual(names.name("bb"), "Bubble Bobble")
        self.assertEqual(names.name("dd"), "Double Dragon (World set 1)")
        self.assertEqual(names.name("ddn"), "Double Dragon (Neo-Geo)")
        self.assertEqual({names.name("x1"), names.name("x2")}, {"Juego X (set 1) [x1]", "Juego X (set 1) [x2]"})
        self.assertEqual(names.name("solo"), "Solo Label")
        self.assertEqual(names.name("zip"), "zip")  # sin otra opción, el nombre del zip

    def test_lectura_de_archivos(self):
        import tempfile
        from arcade_hall_of_fame.names import from_files

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "gamelist.xml").write_text(
                "<gameList><game><path>./bb.zip</path><name>Bubble Bobble</name></game></gameList>", encoding="utf-8")
            dats = root / "dats"
            dats.mkdir()
            (dats / "a.dat").write_text(
                '<?xml version="1.0"?><datafile><game name="gg"><description>Gee Gee (US)</description></game>'
                '<game name="bb"><description>Otro nombre</description></game></datafile>', encoding="utf-8")
            defs = root / "db"
            defs.mkdir()
            (defs / "lab.xml").write_text('<hi2txt label="Con Label &amp; Algo"><structure/></hi2txt>', encoding="utf-8")
            (defs / "alias.xml").write_text('<hi2txt><sameas id="lab"/></hi2txt>', encoding="utf-8")
            names = from_files(str(root / "gamelist.xml"), [dats], defs, ["bb", "gg", "lab", "alias"])
            self.assertEqual([names.name(g) for g in ("bb", "gg", "lab", "alias")],
                             ["Bubble Bobble", "Gee Gee", "Con Label & Algo", "alias"])
            self.assertEqual(from_files(None, [root / "no-existe"], None, ["bb"]).name("bb"), "bb")
