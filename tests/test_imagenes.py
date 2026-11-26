"""Lector de PNG, escalado, medios de ES-DE, destacados y mosaicos."""

import os
import struct
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

from arcade_hall_of_fame.players import Players
from arcade_hall_of_fame.ui import png
from arcade_hall_of_fame.ui import screens as sc
from arcade_hall_of_fame.ui.layout import GRID_COLS, layout, scale_for
from arcade_hall_of_fame.ui.media import Media, Picture, esde_media_dir
from arcade_hall_of_fame.ui.raster import Raster
from arcade_hall_of_fame.ui.screens import GameCard, RotationOptions, Screen, build_screens, choose_featured, mosaic_pages

from .test_historial import HistoryTestCase, demo_file


# --- PNG sintéticos ------------------------------------------------------------------

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def _filter_line(kind, line, prev, bpp):
    out = bytearray()
    for i, x in enumerate(line):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        pred = (0, a, b, (a + b) // 2, _paeth(a, b, c))[kind]
        out.append((x - pred) & 255)
    return bytes([kind]) + bytes(out)


def make_png(width, height, color, raw_pixels, filters=(0,), palette=b"", trns=b"", depth=8, interlace=0):
    """PNG con los filtros dados (uno por fila, en ciclo), escrito a mano para las pruebas."""
    bpp = png.CHANNELS[color]
    stride = width * bpp

    def filtered(w, h, pixels):
        prev = bytes(w * bpp)
        out = b""
        for y in range(h):
            line = pixels[y * w * bpp:(y + 1) * w * bpp]
            out += _filter_line(filters[y % len(filters)], line, prev, bpp)
            prev = line
        return out

    if interlace == 1:  # Adam7: cada pasada es una subimagen con sus propios filtros
        data = b""
        for x0, y0, dx, dy in png.ADAM7:
            xs, ys = range(x0, width, dx), range(y0, height, dy)
            if not xs or not ys:
                continue
            sub = b"".join(raw_pixels[y * stride + x * bpp:y * stride + (x + 1) * bpp] for y in ys for x in xs)
            data += filtered(len(xs), len(ys), sub)
    else:
        data = filtered(width, height, raw_pixels)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    out = png.SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace))
    if palette:
        out += chunk(b"PLTE", palette)
    if trns:
        out += chunk(b"tRNS", trns)
    return out + chunk(b"IDAT", zlib.compress(data)) + chunk(b"IEND", b"")


def pattern(width, height, channels, seed=1):
    """Bytes con variación suficiente para que cada filtro haga algo distinto."""
    return bytes((x * 37 + y * 91 + c * 53 + seed * 17 + (x * y) % 7) & 255
                 for y in range(height) for x in range(width) for c in range(channels))


def over_black(value, alpha):
    return (value * alpha + 127) // 255


class PNGReaderTest(unittest.TestCase):
    W, H = 7, 6  # tamaño impar: los filtros cruzan bordes de píxel

    def check_all_filters(self, color, raw, expected, **extra):
        for filters in ((0,), (1,), (2,), (3,), (4,), (0, 1, 2, 3, 4)):
            data = make_png(self.W, self.H, color, raw, filters, **extra)
            width, height, rgb = png.decode(data)
            self.assertEqual((width, height), (self.W, self.H))
            self.assertEqual(rgb, expected, f"tipo {color}, filtros {filters}")

    def test_gris(self):
        raw = pattern(self.W, self.H, 1)
        self.check_all_filters(0, raw, bytes(v for v in raw for _ in range(3)))

    def test_rgb(self):
        raw = pattern(self.W, self.H, 3)
        self.check_all_filters(2, raw, raw)

    def test_paleta_con_transparencia(self):
        palette = bytes(range(0, 48))  # 16 colores
        trns = bytes([255, 0, 128])  # índice 1 transparente, 2 a medias, el resto opaco
        raw = bytes(v % 16 for v in pattern(self.W, self.H, 1))
        expected = bytearray()
        for index in raw:
            alpha = trns[index] if index < len(trns) else 255
            expected += bytes(over_black(palette[index * 3 + c], alpha) for c in range(3))
        self.check_all_filters(3, raw, bytes(expected), palette=palette, trns=trns)

    def test_gris_con_alfa(self):
        raw = bytearray(pattern(self.W, self.H, 2))
        raw[1::2] = bytes(([0, 255, 128, 255, 7] * 100)[:self.W * self.H])
        expected = bytearray()
        for g, a in zip(raw[0::2], raw[1::2]):
            expected += bytes([over_black(g, a)] * 3)
        self.check_all_filters(4, bytes(raw), bytes(expected))

    def test_rgba(self):
        raw = bytearray(pattern(self.W, self.H, 4))
        raw[3::4] = bytes(([255, 0, 0, 200, 255, 1] * 100)[:self.W * self.H])
        expected = bytearray()
        for i in range(self.W * self.H):
            alpha = raw[i * 4 + 3]
            expected += bytes(over_black(raw[i * 4 + c], alpha) for c in range(3))
        self.check_all_filters(6, bytes(raw), bytes(expected))

    def test_rgba_opaco_queda_igual(self):
        raw = bytearray(pattern(self.W, self.H, 4))
        raw[3::4] = b"\xff" * (self.W * self.H)
        rgb = bytearray(self.W * self.H * 3)
        for c in range(3):
            rgb[c::3] = raw[c::4]
        self.check_all_filters(6, bytes(raw), bytes(rgb))

    def test_color_transparente_en_rgb_y_gris(self):
        raw = bytes([10, 20, 30, 40, 50, 60] * 21)  # 7 x 6 píxeles de dos colores
        _w, _h, rgb = png.decode(make_png(self.W, self.H, 2, raw, trns=struct.pack(">HHH", 40, 50, 60)))
        self.assertEqual(rgb, bytes([10, 20, 30, 0, 0, 0] * 21))
        gray = bytes([5, 9] * 21)
        _w, _h, rgb = png.decode(make_png(self.W, self.H, 0, gray, trns=struct.pack(">H", 9)))
        self.assertEqual(rgb, bytes([5, 5, 5, 0, 0, 0] * 21))

    def test_entrelazado_adam7(self):
        # Tamaños chicos y raros: algunas pasadas quedan vacías.
        for width, height in ((1, 1), (2, 3), (5, 1), (9, 10), (17, 9)):
            for color, channels, extra in ((0, 1, {}), (2, 3, {}), (3, 1, {"palette": bytes(range(48))}),
                                            (4, 2, {}), (6, 4, {})):
                raw = pattern(width, height, channels)
                if color == 3:
                    raw = bytes(v % 16 for v in raw)
                for filters in ((0,), (1,), (2,), (3,), (4,), (0, 1, 2, 3, 4)):
                    plain = png.decode(make_png(width, height, color, raw, filters, **extra))
                    laced = png.decode(make_png(width, height, color, raw, filters, interlace=1, **extra))
                    self.assertEqual(laced, plain, (width, height, color, filters))

    def test_no_soportados(self):
        raw = pattern(self.W, self.H, 3)
        interlaced = make_png(self.W, self.H, 2, raw, interlace=2)  # método de entrelazado inexistente
        sixteen = make_png(2, 2, 2, bytes(24), depth=16)
        jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(40)
        for data in (interlaced, sixteen, jpg, b"", png.SIGNATURE + b"cortado"):
            with self.assertRaises(png.PNGError):
                png.decode(data)
            self.assertIsNone(png.size_of(data))
        broken = make_png(self.W, self.H, 2, raw)
        with self.assertRaises(png.PNGError):  # datos comprimidos dañados
            png.decode(broken[:60] + b"\x00" * 10 + broken[70:])

    def test_codificar_y_volver_a_leer(self):
        raw = pattern(5, 3, 3)
        self.assertEqual(png.decode(png.encode(5, 3, raw)), (5, 3, raw))


class ResampleTest(unittest.TestCase):
    def test_proporcion(self):
        self.assertEqual(png.fit(600, 300, 288, 120), (240, 120))
        self.assertEqual(png.fit(224, 288, 288, 540), (288, 370))
        self.assertEqual(png.fit(10, 1000, 50, 50), (1, 50))
        self.assertEqual(png.fit(0, 10, 50, 50), (0, 0))

    def test_color_uniforme_se_mantiene(self):
        rgb = bytes([200, 100, 50]) * (13 * 7)
        for size in ((5, 3), (26, 14), (13, 7), (40, 9)):
            out = png.resample(rgb, 13, 7, *size)
            self.assertEqual(out, bytes([200, 100, 50]) * (size[0] * size[1]), size)

    def test_achicar_promedia_por_area(self):
        # 4 x 2 con bloques de 2 x 2 → 2 x 1 con el promedio exacto de cada bloque.
        rgb = bytes([0, 0, 0, 100, 100, 100, 10, 20, 30, 30, 40, 50,
                     200, 200, 200, 100, 100, 100, 50, 60, 70, 70, 80, 90])
        self.assertEqual(png.resample(rgb, 4, 2, 2, 1), bytes([100, 100, 100, 40, 50, 60]))

    def test_agrandar_bilineal(self):
        rgb = bytes([0, 0, 0, 255, 255, 255])  # 2 x 1: negro y blanco
        out = png.resample(rgb, 2, 1, 4, 1)
        values = list(out[0::3])
        self.assertEqual(values[0], 0)
        self.assertEqual(values[-1], 255)
        self.assertEqual(values, sorted(values))  # degradé sin saltos raros
        self.assertTrue(0 < values[1] < 128 < values[2] < 255)


# --- Medios de ES-DE -----------------------------------------------------------------

class MediaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "downloaded_media"
        self.cache = Path(self.tmp.name) / "cache"

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def red(self, w=8, h=4):
        return png.encode(w, h, bytes([255, 0, 0]) * (w * h))

    def test_busca_en_subcarpetas_y_cae_a_titlescreen(self):
        self.put("fbneo/marquees/cps1/ffight.png", self.red())
        self.put("fbneo/titlescreens/fbneo/galaga.png", self.red(4, 8))
        media = Media(self.root, "fbneo", self.cache)
        self.assertEqual((media.marquee("ffight").width, media.marquee("ffight").height), (8, 4))
        self.assertIsNone(media.shot("ffight"))
        self.assertEqual(Path(media.shot("galaga").path).parent.parent.name, "titlescreens")
        self.assertIsNone(media.marquee("nada"))
        self.assertIsNone(Media(None).marquee("ffight"))

    def test_no_soportado_o_jpg_usa_texto(self):
        self.put("fbneo/marquees/fbneo/a.png", b"\xff\xd8\xff\xe0 un jpg con nombre .png")
        self.put("fbneo/marquees/fbneo/b.png", make_png(2, 2, 2, bytes(24), depth=16))
        self.put("fbneo/screenshots/fbneo/a.png", self.red())
        media = Media(self.root, "fbneo")
        self.assertIsNone(media.marquee("a"))
        self.assertIsNone(media.marquee("b"))
        self.assertIsNotNone(media.shot("a"))

    def test_cache_en_disco(self):
        path = self.put("fbneo/marquees/fbneo/x.png", self.red(8, 4))
        picture = Media(self.root, "fbneo", self.cache).marquee("x")
        self.assertEqual(picture.pixels(4, 2), bytes([255, 0, 0]) * 8)
        files = list(self.cache.glob("*.rgb"))
        self.assertEqual(len(files), 1)
        # Otra instancia (otra ejecución) lee la caché sin decodificar el PNG.
        path.write_bytes(b"ya no es un png")
        os.utime(path, ns=(picture.mtime_ns, picture.mtime_ns))
        same = Picture(picture.path, picture.size, picture.mtime_ns, 8, 4, str(self.cache))
        from arcade_hall_of_fame.ui import media as media_module
        media_module._MEMORY.clear()
        self.assertEqual(same.pixels(4, 2), bytes([255, 0, 0]) * 8)
        # Si el archivo cambia (otra fecha o tamaño), no sirve la caché: aquí ya no es PNG.
        changed = Picture(picture.path, path.stat().st_size, path.stat().st_mtime_ns + 1, 8, 4, str(self.cache))
        self.assertIsNone(changed.pixels(4, 2))

    def test_carpeta_de_medios_de_es_de(self):
        home = Path(self.tmp.name) / "ES-DE"
        self.assertEqual(esde_media_dir(home), home / "downloaded_media")
        (home / "settings").mkdir(parents=True)
        settings = home / "settings" / "es_settings.xml"
        settings.write_text('<?xml version="1.0"?>\n<string name="MediaDirectory" value="" />\n', encoding="utf-8")
        self.assertEqual(esde_media_dir(home), home / "downloaded_media")
        settings.write_text('<?xml version="1.0"?>\n<bool name="X" value="true" />\n'
                            '<string name="MediaDirectory" value="/Volumes/Medios" />\n', encoding="utf-8")
        self.assertEqual(esde_media_dir(home), Path("/Volumes/Medios"))


# --- Destacados y mosaicos ------------------------------------------------------------

def card(game, players, last, recent=False):
    screen = Screen(f"juego:{game}", game.upper(), "", (), [])
    return GameCard(game, screen, players, last, recent)


class SelectionTest(unittest.TestCase):
    def test_mas_jugadores_y_desempate_por_record_mas_reciente(self):
        cards = [card("a", 3, "2026-01-01T00:00:00+00:00"), card("b", 5, "2026-01-01T00:00:00+00:00"),
                 card("c", 3, "2026-06-01T00:00:00+00:00"), card("d", 1, "2026-11-01T00:00:00+00:00"),
                 card("e", 2, "")]
        featured, rest = choose_featured(cards, 3)
        self.assertEqual([c.game for c in featured], ["b", "c", "a"])
        self.assertEqual([c.game for c in rest], ["d", "e"])  # alfabético

    def test_record_nuevo_entra_primero(self):
        cards = [card(g, 9 - i, "2026-01-01T00:00:00+00:00") for i, g in enumerate("abcdef")]
        cards.append(card("z", 0, "2026-11-20T00:00:00+00:00", recent=True))
        cards.append(card("y", 0, "2026-11-25T00:00:00+00:00", recent=True))
        featured, rest = choose_featured(cards, 4)
        self.assertEqual([c.game for c in featured], ["y", "z", "a", "b"])
        self.assertEqual([c.game for c in rest], ["c", "d", "e", "f"])
        featured, _rest = choose_featured(cards, 1)  # el tope vale también para los nuevos
        self.assertEqual([c.game for c in featured], ["y"])
        self.assertEqual(choose_featured(cards, 0)[0], [])

    def test_paginas_de_mosaico_y_rotacion(self):
        rest = [card(f"g{i:02d}", 0, "") for i in range(20)]  # 4 páginas de 6 (la última con 2)
        pages = mosaic_pages(rest, 6, 10)
        self.assertEqual([(n, t, len(p)) for n, t, p in pages], [(1, 4, 6), (2, 4, 6), (3, 4, 6), (4, 4, 2)])
        seen = []
        for rotation in range(4):
            shown = mosaic_pages(rest, 6, 3, rotation)
            self.assertEqual(len(shown), 3)
            seen.append([n for n, _t, _p in shown])
        self.assertEqual(seen, [[1, 2, 3], [4, 1, 2], [3, 4, 1], [2, 3, 4]])
        self.assertEqual(mosaic_pages([], 6, 3), [])
        self.assertEqual(mosaic_pages(rest, 6, 0), [])


class RotationScreensTest(HistoryTestCase):
    def setUp(self):
        super().setUp()
        for i in range(1, 11):
            name = f"juego{i:02d}"
            (self.db_dir / f"{name}.xml").write_bytes((self.db_dir / "demo.xml").read_bytes())
            # juego01 con 1 jugador, ..., juego03 con 3 (el resto, 1 o 2).
            initials = [["AB", "AB", "AB"], ["AB", "CD", "AB"], ["AB", "CD", "EF"]][min(i, 3) - 1] if i <= 3 \
                else (["XY", "XY", "XY"] if i % 2 else ["XY", "QZ", "XY"])
            self.write(name, demo_file([(900, initials[0]), (500, initials[1]), (100, initials[2])]))
        self.scan()  # línea base: sin récords nuevos

    def keys(self, screens):
        return [s.key for s in screens]

    def test_orden_de_la_vuelta(self):
        screens = build_screens(self.db, Players(), options=RotationOptions(featured=3, per_mosaic=3, mosaics=2))
        keys = self.keys(screens)
        self.assertEqual(keys[:2], ["ranking", "records"])
        self.assertEqual(keys[2], "juego:juego03")  # 3 jugadores distintos
        self.assertEqual(len([k for k in keys if k.startswith("juego:")]), 3)
        self.assertEqual([k for k in keys if k.startswith("mosaico:")], ["mosaico:1", "mosaico:2"])
        self.assertEqual(screens.games, 10)
        mosaic = screens[-1]
        self.assertEqual((mosaic.title, mosaic.subtitle), ("MÁS RÉCORDS", "2 / 3"))
        tile = mosaic.tiles[0]
        self.assertEqual(tile.holder[1], sc.ORO)
        self.assertEqual(tile.score, ("900", sc.PUNTOS))
        # La rotación muestra la página que faltaba.
        rotated = build_screens(self.db, Players(), options=RotationOptions(featured=3, per_mosaic=3, mosaics=2),
                                rotation=1)
        self.assertIn("mosaico:3", self.keys(rotated))

    def test_record_nuevo_destacado_por_n_dias(self):
        options = RotationOptions(featured=2, featured_days=7, per_mosaic=6, mosaics=3)
        self.assertNotIn("juego:juego09", self.keys(build_screens(self.db, Players(), options=options)))
        self.write("juego09", demo_file([(950, "XY"), (900, "XY"), (500, "XY")]))  # sigue con 1 jugador
        self.scan()  # récord batido
        keys = self.keys(build_screens(self.db, Players(), options=options))
        self.assertEqual(keys[2], "juego:juego09")
        later = datetime.now(timezone.utc) + timedelta(days=8)
        self.assertNotIn("juego:juego09", self.keys(build_screens(self.db, Players(), options=options, now=later)))
        no_days = RotationOptions(featured=2, featured_days=0)
        self.assertNotIn("juego:juego09", self.keys(build_screens(self.db, Players(), options=no_days)))

    def test_jugadores_distintos_con_alias(self):
        self.assertEqual(sc.distinct_players(self.db, "juego03", Players()), 3)
        same = Players.from_data({"jugadores": {"ANA": ["AB", "CD"]}})
        self.assertEqual(sc.distinct_players(self.db, "juego03", same), 2)


# --- Composición y dibujo con imágenes --------------------------------------------------

class ImageLayoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "m.png").write_bytes(png.encode(60, 30, bytes([255, 0, 0]) * 1800))
        (root / "s.png").write_bytes(png.encode(22, 28, bytes([0, 255, 0]) * (22 * 28)))
        self.marquee = Picture(str(root / "m.png"), 1, 1, 60, 30)
        self.shot = Picture(str(root / "s.png"), 1, 2, 22, 28)

    def tearDown(self):
        self.tmp.cleanup()

    def game(self, **extra):
        columns = (sc.Column("POS", 4), sc.Column("PUNTOS", 10, "right"), sc.Column("JUGADOR", 13), sc.Column("", 10))
        rows = [[(f"{i}.", sc.ORO), (str(1000 - i), sc.PUNTOS), ("AB", sc.RESTO), ("", sc.DIM)] for i in range(1, 11)]
        return Screen("juego:x", "TITULO DEL JUEGO", "1986 / TAITO", columns, rows, [("NOTA", sc.DIM)], **extra)

    def test_marquee_en_lugar_del_titulo_y_captura_al_costado(self):
        width, height = 1920, 1080
        plain = layout(self.game(), width, height)
        ops = layout(self.game(marquee=self.marquee, shot=self.shot), width, height)
        texts = [op[3] for op in ops if op[0] == "text"]
        self.assertIn("TITULO DEL JUEGO", [op[3] for op in plain if op[0] == "text"])
        self.assertNotIn("TITULO DEL JUEGO", texts)
        self.assertIn("1986 / TAITO", texts)
        images = [op for op in ops if op[0] == "image"]
        self.assertEqual([op[5] for op in images], [self.marquee, self.shot])
        s = scale_for(width, height)
        x0 = (width - GRID_COLS * 6 * s) // 2
        table_right = max(op[1] + len(op[3]) * 6 * s for op in ops if op[0] == "text" and op[3] in ("AB", "JUGADOR"))
        _, mx, my, mw, mh, _ = images[0]
        self.assertEqual(mw / mh, 2.0)  # respeta la proporción
        _, ix, iy, iw, ih, _ = images[1]
        self.assertGreater(ix, table_right)  # a la derecha de la tabla
        self.assertLessEqual(ix + iw, x0 + GRID_COLS * 6 * s)
        self.assertAlmostEqual(iw / ih, 22 / 28, places=1)
        status_y = max(op[2] for op in ops if op[0] == "text")
        self.assertLess(iy + ih, status_y)
        raster = Raster(width, height).draw(ops)
        self.assertEqual(raster.pixel(mx + mw // 2, my + mh // 2), "#ff0000")
        self.assertEqual(raster.pixel(ix + iw // 2, iy + ih // 2), "#00ff00")

    def test_sin_imagen_legible_no_dibuja_nada(self):
        broken = Picture(str(Path(self.tmp.name) / "no-existe.png"), 1, 1, 60, 30)
        ops = layout(self.game(marquee=broken), 640, 360)
        raster = Raster(640, 360).draw(ops)  # no falla
        self.assertEqual(raster.pixel(320, 40), "#000000")

    def test_mosaico_3_por_2(self):
        tiles = [sc.Tile(f"g{i}", f"JUEGO NUMERO {i}", self.marquee if i % 2 else None, ("TINCHOVA", sc.ORO),
                         ("123456", sc.PUNTOS)) for i in range(6)]
        screen = Screen("mosaico:1", "MÁS RÉCORDS", "1 / 3", (), [], tiles=tiles, status="20 JUEGOS")
        for size in ((1920, 1080), (1280, 720), (640, 360)):
            ops = layout(screen, *size, "PIE", "1/9")
            self.assertEqual([op[1] for op in ops if op[0] == "row"], list(range(6)))
            self.assertEqual(len([op for op in ops if op[0] == "image"]), 3)
            texts = [op for op in ops if op[0] == "text"]
            self.assertEqual(len([op for op in texts if op[3] == "TINCHOVA" and op[4] == sc.ORO]), 6)
            self.assertEqual(len([op for op in texts if op[3] == "123456" and op[4] == sc.PUNTOS]), 6)
            self.assertIn("MAS RECORDS", [op[3] for op in texts])
            self.assertIn("1 / 3", [op[3] for op in texts])
            for op in texts:
                self.assertLessEqual(op[1] + len(op[3]) * 6 * op[5], size[0], (size, op[3]))
                self.assertLessEqual(op[2] + 7 * op[5], size[1])
            # Sin marquee, el nombre del juego en celeste.
            self.assertTrue(any(op[3].startswith("JUEGO NUMERO") and op[4] == sc.JUEGO for op in texts))


if __name__ == "__main__":
    unittest.main()
