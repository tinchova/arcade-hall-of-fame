"""Página web, alias de jugadores y elección de fila en ``nombrar`` (sin red: servidor en 127.0.0.1)."""

import http.client
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

from arcade_hall_of_fame.naming import NamingError, assign_name, player_rows, select_row
from arcade_hall_of_fame.players import AliasError, Players, clean_alias_initials, clean_alias_name, load_players
from arcade_hall_of_fame.rankings import player_ranking
from arcade_hall_of_fame.storage import Database
from arcade_hall_of_fame.ui import screens as sc
from arcade_hall_of_fame.ui.layout import GRID_COLS
from arcade_hall_of_fame import web

from .test_historial import NamingTest, demo_file

NOW = "2026-11-26T12:00:00+00:00"


def add_table(db: Database, game: str, rows, now: str = NOW) -> None:
    """Tabla vigente sintética: [(puntos, iniciales)], sin pasar por el lector."""
    entries = [{"position": i, "score_text": str(s), "score_num": s, "initials": n or None, "factory": False}
               for i, (s, n) in enumerate(rows, start=1)]
    top = max(s for s, _ in rows)
    db.add_observation(game, f"{game}.hi", f"h-{game}-{now}-{rows}", now, entries, str(top), top, "aceptada",
                       "línea base", True, None, "prueba", "prueba")


class AliasTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Database(Path(tmp.name) / "h.sqlite3")
        self.addCleanup(self.db.close)

    def test_ranking_agrupa_por_nombre_final(self):
        # Pac-Man sin iniciales con el nombre TINCHOVA puesto a mano; Bubble Bobble con TCH.
        add_table(self.db, "pacman", [(1400, None)])
        add_table(self.db, "bublbobl", [(30000, "TCH"), (100, "ZZ")])
        assign_name(self.db, "pacman", "TINCHOVA", NOW)
        before = [(r.initials, r.count) for r in player_ranking(self.db, load_players(None, self.db))]
        self.assertEqual(before, [("TCH", 1), ("TINCHOVA", 1)])
        self.db.set_alias("TCH", "TINCHOVA", NOW)
        after = [(r.initials, r.count, r.games) for r in player_ranking(self.db, load_players(None, self.db))]
        self.assertEqual(after, [("TINCHOVA", 2, ("bublbobl", "pacman"))])
        # Sin distinguir mayúsculas ni espacios de más.
        players = Players({"TCH": "tinchova "})
        self.assertEqual([(r.count) for r in player_ranking(self.db, players)], [2])

    def test_orden_nombre_puesto_alias_iniciales(self):
        add_table(self.db, "galaga", [(500, "TCH"), (400, "TCH"), (300, None), (200, "ABC")])
        self.db.set_alias("tch", "TINCHOVA", NOW)  # el web guarda en mayúsculas; igual se compara sin distinguir
        players = load_players(None, self.db)
        assign_name(self.db, "galaga", "PEDRO", NOW, position=2)  # pasa por arriba del alias
        assign_name(self.db, "galaga", "TCH", NOW, position=3)  # sin iniciales: se le pone TCH -> alias
        shown = {r.position: players.name(r.name) for r in player_rows(self.db, "galaga")}
        self.assertEqual(shown, {1: "TINCHOVA", 2: "PEDRO", 3: "TINCHOVA", 4: "ABC"})

    def test_juegos_que_guardan_solo_el_maximo(self):
        from arcade_hall_of_fame.naming import keeps_only_top

        add_table(self.db, "pacman", [(1400, None)])
        add_table(self.db, "unafila", [(900, "TCH")])
        add_table(self.db, "galaga", [(500, None), (300, None)])
        self.assertEqual([keeps_only_top(self.db, g) for g in ("pacman", "unafila", "galaga", "nohay")],
                         [True, False, False, False])

    def test_records_anteriores_de_un_juego_que_guarda_solo_el_maximo(self):
        from arcade_hall_of_fame.naming import previous_records, remove_name, unnamed_records

        add_table(self.db, "pacman", [(1400, None)], "2026-11-01T10:00:00+00:00")
        add_table(self.db, "pacman", [(2000, None)], "2026-11-02T10:00:00+00:00")
        add_table(self.db, "pacman", [(3000, None)], "2026-11-03T10:00:00+00:00")
        add_table(self.db, "galaga", [(500, "TCH")])
        self.assertEqual([(r.score_text, r.detected_utc[:10], r.name) for r in previous_records(self.db, "pacman")],
                         [("2000", "2026-11-02", None), ("1400", "2026-11-01", None)])
        self.assertEqual(previous_records(self.db, "galaga"), [])
        self.assertEqual([r.game for r in unnamed_records(self.db)], ["pacman"])  # el vigente, 3000
        assign_name(self.db, "pacman", "ana", NOW, expected_score="1400")
        self.assertEqual(previous_records(self.db, "pacman")[1].name, "ANA")
        self.assertEqual([r.initials for r in player_ranking(self.db, load_players(None, self.db))], ["TCH"])
        assign_name(self.db, "pacman", "BETO", NOW, expected_score="3000")  # el vigente
        self.assertEqual(unnamed_records(self.db), [])  # el 2000 sin nombre no cuenta (no dispara el QR)
        self.assertEqual([r.initials for r in player_ranking(self.db, load_players(None, self.db))], ["BETO", "TCH"])
        self.assertEqual(remove_name(self.db, "pacman", "1400"), ("1400", None))
        with self.assertRaises(NamingError):
            assign_name(self.db, "galaga", "X", NOW, expected_score="400")

    def test_tabla_del_juego_con_los_que_rompieron_el_record(self):
        add_table(self.db, "pacman", [(1400, None)], "2026-11-01T10:00:00+00:00")
        add_table(self.db, "pacman", [(2000, None)], "2026-11-02T10:00:00+00:00")
        add_table(self.db, "pacman", [(3000, None)], "2026-11-03T10:00:00+00:00")
        assign_name(self.db, "pacman", "ANA", NOW, expected_score="3000")
        assign_name(self.db, "pacman", "TCH", NOW, expected_score="1400")
        self.db.set_alias("TCH", "TINCHOVA", NOW)
        players = load_players(None, self.db)

        def table(show=False):
            screen = sc.game_screen(self.db, "pacman", players, sc.GameNames(), show)
            return [[c[0] for c in row[:3]] for row in screen.rows], [row[2][1] for row in screen.rows]

        rows, colors = table()
        self.assertEqual(rows, [["1.", "3000", "ANA"], ["3.", "1400", "TINCHOVA"]])  # 2000 sin nombre: oculto
        self.assertEqual(colors, [sc.rank_color(1), sc.rank_color(3)])  # podio
        rows, _ = table(show=True)
        self.assertEqual([r[2] for r in rows], ["ANA", "???", "TINCHOVA"])
        # En el TOP GLOBAL suma solo el vigente.
        self.assertEqual([(r.initials, r.count) for r in player_ranking(self.db, players)], [("ANA", 1)])

    def test_validacion_de_alias(self):
        self.assertEqual(clean_alias_initials(" tch "), "TCH")
        self.assertEqual(clean_alias_name("  ana   maria "), "ANA MARIA")
        self.assertEqual(clean_alias_name("Peña"), "PEÑA")  # se muestra sin tilde en la fuente pixel
        for bad in ("", "A" * 13, "???", "A\x00B", "A♥B"):
            with self.assertRaises(AliasError):
                clean_alias_name(bad)
        with self.assertRaises(AliasError):
            clean_alias_initials("A" * 13)

    def test_nombres_de_12_entran_en_todas_las_pantallas(self):
        add_table(self.db, "galaga", [(500, "TCH"), (400, "QQ")])
        self.db.set_alias("TCH", "ABCDEFGHIJKL", NOW)
        self.db.conn.execute("INSERT INTO record_events (game, observation_id, detected_utc, previous_top_text, "
                             "new_top_text, previous_holders, new_holders) VALUES ('galaga', 1, ?, NULL, '500', "
                             "'[]', '[\"TCH\"]')", (NOW,))
        self.db.conn.commit()
        screens = sc.build_screens(self.db, load_players(None, self.db))
        seen = 0
        for screen in screens:
            self.assertLessEqual(sum(c.width for c in screen.columns) + len(screen.columns) - 1, GRID_COLS,
                                 screen.key)
            for row in screen.rows:
                for (text, _color), column in zip(row, screen.columns):
                    if text == "ABCDEFGHIJKL":
                        self.assertGreaterEqual(column.width, 12, screen.key)
                        seen += 1
        self.assertEqual(seen, 3)  # ranking, últimos récords y la tabla del juego
        records = next(s for s in screens if s.key == "records")
        self.assertRegex(records.rows[0][0][0], r"^\d\d/\d\d$")  # fecha sin hora


class ChooseRowTest(NamingTest):
    def test_nombrar_con_de_y_puesto(self):
        self.db.close()
        self.write("demo", demo_file([(900, "XY"), (600, "QQ"), (450, "QQ")]))
        self.run_cli("escanear", str(self.saves))
        self.assertIn("hay 2 filas a nombre de QQ (puestos 2, 3); indicar --puesto o --puntos",
                      self.run_cli("nombrar", "demo", "CAMILA", "--de", "qq"))
        self.assertIn("la fila del puesto 3 (450) queda a nombre de CAMILA (antes: QQ)",
                      self.run_cli("nombrar", "demo", "camila", "--de", "QQ", "--puntos", "450"))
        self.assertIn("la fila del puesto 2 (600) queda a nombre de BETO (antes: QQ)",
                      self.run_cli("nombrar", "demo", "BETO", "--puesto", "2"))
        self.assertIn("ninguna fila de la tabla vigente está a nombre de ZZ",
                      self.run_cli("nombrar", "demo", "X", "--de", "ZZ"))
        self.assertIn("no tiene puesto 9", self.run_cli("nombrar", "demo", "X", "--puesto", "9"))
        self.assertIn("el récord 900 queda a nombre de NC (antes: XY)", self.run_cli("nombrar", "demo", "NC"))
        table = self.run_cli("juego", "demo")
        self.assertRegex(table, r"2 +600 +BETO")
        self.assertRegex(table, r"3 +450 +CAMILA")
        self.assertIn("vuelve a las iniciales originales del juego: QQ",
                      self.run_cli("nombrar", "demo", "--quitar", "--de", "CAMILA"))
        self.assertRegex(self.run_cli("juego", "demo"), r"3 +450 +QQ")
        self.db = Database(self.db_path)
        with self.assertRaises(NamingError):
            select_row(self.db, "demo", position=2, expected_score="450")


class WebTest(unittest.TestCase):
    def setUp(self):
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "h.sqlite3"
        db = Database(self.path)
        add_table(db, "galaga", [(500, "TCH"), (300, None)])
        add_table(db, "pacman", [(1400, None)])
        db.conn.execute("INSERT INTO unreadable (game, file_name, reason, detail, first_seen_utc, last_seen_utc, "
                        "file_mtime_utc) VALUES ('raro', 'raro.hi', 'sin definición en hi2txt-xml', '', ?, ?, ?)",
                        (NOW, NOW, NOW))
        db.conn.commit()
        db.close()
        self.changes = []
        config = web.WebConfig(self.path, lambda d, games: {g: g.upper() + " TITULO" for g in games},
                               after_change=lambda d: self.changes.append(1), qr_svg="<svg>qr</svg>",
                               addresses=["http://192.168.1.10:47474/"],
                               tailscale=["http://100.101.102.103:47474/"])
        handler_log = web.Handler.log_message
        web.Handler.log_message = lambda *a: None  # sin registro en la salida de las pruebas
        self.addCleanup(setattr, web.Handler, "log_message", handler_log)
        self.server = web.make_server(config, "127.0.0.1", 0)
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": f"127.0.0.1:{self.port}"}
        if body is not None:
            h.update({"Content-Type": "application/x-www-form-urlencoded",
                      "Origin": f"http://127.0.0.1:{self.port}"})
        h.update(headers or {})
        conn.request(method, path, body=urlencode(body) if isinstance(body, dict) else body, headers=h)
        response = conn.getresponse()
        data = response.read().decode("utf-8")
        conn.close()
        return response, data

    def db(self):
        db = Database(self.path)
        self.addCleanup(db.close)
        return db

    def test_pagina_global_y_juego(self):
        response, page = self.request("GET", "/")
        self.assertEqual(response.status, 200)
        self.assertIn("default-src 'none'", response.getheader("Content-Security-Policy"))
        self.assertIn("GALAGA TITULO", page)
        self.assertIn("Sin leer (1)", page)
        self.assertIn("<svg>qr</svg>", page)
        self.assertIn("192.168.1.10:47474", page)
        self.assertIn("Tailscale", page)
        self.assertIn("100.101.102.103:47474", page)
        self.assertIn("hof_visita=", response.getheader("Set-Cookie"))
        _, page = self.request("GET", "/?ver=galaga")
        self.assertIn("500", page)
        self.assertIn('name="puesto" value="2"', page)
        self.assertNotIn("guarda solo el récord máximo", page)  # tabla con varias filas
        _, page = self.request("GET", "/?ver=pacman")
        self.assertIn('class="aviso"', page)  # una sola fila sin iniciales: solo guarda el máximo
        self.assertIn("las que no lo superan no quedan guardadas", page)
        self.assertNotIn('name="historial"', page)  # todavía no hay récords anteriores

    def test_records_anteriores_en_la_pagina(self):
        db = self.db()
        add_table(db, "pacman", [(2000, None)], "2026-11-20T10:00:00+00:00")  # supera al 1400
        db.close()
        _, page = self.request("GET", "/?ver=pacman")
        self.assertIn('name="historial" value="1"', page)  # el anterior, en la misma tabla
        self.assertIn("récord anterior, detectado el", page)
        self.assertLess(page.index("2000"), page.index("1400"))
        self.assertIn('name="puntos" value="1400"', page)
        response, _ = self.request("POST", "/nombrar", {"juego": "pacman", "puntos": "1400", "historial": "1",
                                                        "nombre": "ana"})
        self.assertEqual(response.status, 303)
        self.assertEqual(self.db().record_name("pacman", "1400")["initials"], "ANA")
        _, page = self.request("GET", "/?ver=pacman")
        self.assertIn("ANA", page)
        response, _ = self.request("POST", "/nombrar", {"juego": "pacman", "puntos": "999", "historial": "1",
                                                        "nombre": "ana"})
        self.assertEqual(response.status, 400)
        response, _ = self.request("POST", "/quitar", {"juego": "pacman", "puntos": "1400", "historial": "1"})
        self.assertEqual(response.status, 303)
        self.assertIsNone(self.db().record_name("pacman", "1400"))
        _, page = self.request("GET", "/?ver=sin-leer")
        self.assertIn("RARO TITULO", page)
        self.assertIn("sin definición en hi2txt-xml", page)
        _, page = self.request("GET", "/?ver=<script>")
        self.assertNotIn("<script>", page)

    def test_nombrar_quitar_y_alias(self):
        response, _ = self.request("POST", "/nombrar", {"juego": "galaga", "puesto": "2", "puntos": "300",
                                                        "nombre": "ana  maria"})
        self.assertEqual(response.status, 303)
        self.assertEqual(response.getheader("Location"), "/?ver=galaga&hecho=nombrado")
        self.assertEqual(self.db().record_name("galaga", "300")["initials"], "ANA MARIA")
        self.assertEqual(self.db().record_name("galaga", "300")["origin"], "celular")
        response, page = self.request("POST", "/nombrar", {"juego": "galaga", "puesto": "2", "puntos": "999",
                                                           "nombre": "X"})
        self.assertEqual(response.status, 400)
        self.assertIn("el puesto 2 tiene 300, no 999", page)
        response, page = self.request("POST", "/nombrar", {"juego": "galaga", "puesto": "1", "puntos": "500",
                                                           "nombre": "A" * 13})
        self.assertEqual(response.status, 400)
        response, _ = self.request("POST", "/quitar", {"juego": "galaga", "puesto": "2", "puntos": "300"})
        self.assertEqual(response.status, 303)
        self.assertIsNone(self.db().record_name("galaga", "300"))
        response, _ = self.request("POST", "/alias", {"iniciales": "tch", "nombre": "tinchova"})
        self.assertEqual(response.status, 303)
        self.assertEqual(self.db().aliases(), {"TCH": "TINCHOVA"})
        _, page = self.request("GET", "/?ver=galaga")
        self.assertIn("alias de TCH", page)
        response, _ = self.request("POST", "/alias/borrar", {"iniciales": "TCH"})
        self.assertEqual(response.status, 303)
        self.assertEqual(self.db().aliases(), {})
        response, page = self.request("POST", "/alias/borrar", {"iniciales": "TCH"})
        self.assertEqual(response.status, 400)
        self.assertEqual(len(self.changes), 4)  # se regeneró el protector en cada cambio guardado

    def test_limites(self):
        body = {"juego": "galaga", "puesto": "1", "puntos": "500", "nombre": "X"}
        response, _ = self.request("POST", "/nombrar", body, {"Origin": "http://otra.example"})
        self.assertEqual(response.status, 403)
        response, _ = self.request("POST", "/nombrar", body, {"Origin": ""})
        self.assertEqual(response.status, 403)
        response, _ = self.request("GET", "/", headers={"Host": "atacante.example"})
        self.assertEqual(response.status, 400)
        response, _ = self.request("GET", "/archivo.txt")
        self.assertEqual(response.status, 404)
        response, _ = self.request("POST", "/borrar-todo", body)
        self.assertEqual(response.status, 404)
        response, _ = self.request("POST", "/nombrar", "x" * 5000)
        self.assertEqual(response.status, 413)
        response, _ = self.request("POST", "/nombrar", body, {"Content-Type": "application/json"})
        self.assertEqual(response.status, 415)
        response, _ = self.request("POST", "/nombrar", {"juego": "noexiste", "puesto": "1", "puntos": "1",
                                                        "nombre": "X"})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.changes, [])

    def test_clientes_y_hosts(self):
        for ok in ("192.168.1.20", "10.0.0.5", "172.16.3.4", "127.0.0.1", "fe80::1", "::1", "::ffff:192.168.1.2",
                   "100.64.24.66", "100.108.85.112", "100.127.255.254", "fd7a:115c:a1e0::1"):
            self.assertTrue(web.allowed_client(ok), ok)
        for bad in ("8.8.8.8", "200.40.30.1", "0.0.0.0", "basura", "100.63.255.255", "100.128.0.1",
                    "2606:4700::1111"):
            self.assertFalse(web.allowed_client(bad), bad)
        for ok in ("192.168.1.10:47474", "localhost:47474", "mi-imac.local:47474", "[fe80::1]:47474",
                   "100.101.102.103:47474", "mi-imac.ejemplo.ts.net:47474", "[fd7a:115c:a1e0::1]:47474"):
            self.assertTrue(web.allowed_host(ok), ok)
        for bad in ("", "evil.com", "192.168.1.10.evil.com:47474", "ts.net.evil.com", "evilts.net"):
            self.assertFalse(web.allowed_host(bad), bad)

    def test_post_por_tailscale_exige_el_mismo_origen(self):
        body = {"juego": "galaga", "puesto": "1", "puntos": "500", "nombre": "X"}
        host = "mi-imac.ejemplo.ts.net:47474"
        response, _ = self.request("GET", "/", headers={"Host": host})
        self.assertEqual(response.status, 200)
        response, _ = self.request("POST", "/nombrar", body, {"Host": host, "Origin": "http://otra.example"})
        self.assertEqual(response.status, 403)
        self.assertEqual(self.changes, [])
        response, _ = self.request("POST", "/nombrar", body, {"Host": host, "Origin": f"http://{host}"})
        self.assertEqual(response.status, 303)

    def test_ip_de_tailscale(self):
        import sys
        import tempfile

        from arcade_hall_of_fame import direccion

        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "tailscale.py"
            fake.write_text("print('100.108.1.2')", encoding="utf-8")
            orig = direccion.subprocess.run
            direccion.subprocess.run = lambda cmd, **kw: orig([sys.executable, cmd[0]] + cmd[1:], **kw)
            self.addCleanup(setattr, direccion.subprocess, "run", orig)
            self.assertEqual(direccion.tailscale_ip([str(fake)]), "100.108.1.2")
            fake.write_text("print('192.168.1.2')", encoding="utf-8")
            self.assertIsNone(direccion.tailscale_ip([str(fake)]))

    def test_nuevo_desde_la_visita_anterior(self):
        first = "2026-11-26T10:00:00+00:00"
        since, cookie = web.visit_window(None, first)
        self.assertIsNone(since)  # primera visita: nada marcado
        since, cookie = web.visit_window(f"x=1; hof_visita={cookie}", "2026-11-26T10:10:00+00:00")
        self.assertEqual(since, first)  # misma visita: se mantiene la referencia
        since, _ = web.visit_window(f"hof_visita={cookie}", "2026-11-26T12:00:00+00:00")
        self.assertEqual(since, "2026-11-26T10:10:00+00:00")  # otra visita: desde la última carga
        self.assertEqual(web.visit_window("hof_visita=<b>|x", first)[0], None)
        db = self.db()
        add_table(db, "galaga", [(800, "NEW"), (500, "TCH"), (300, None)], now="2026-11-26T13:00:00+00:00")
        add_table(db, "digdug", [(100, "AB")], now="2026-11-26T13:00:00+00:00")
        games, rows = web.new_marks(db, "2026-11-26T12:30:00+00:00")
        self.assertEqual(games, {"digdug"})
        self.assertEqual(rows, {("galaga", "800", "NEW"), ("digdug", "100", "AB")})
        _, page = self.request("GET", "/?ver=galaga", headers={
            "Cookie": "hof_visita=2026-11-26T12:30:00+00:00|2026-11-26T12:30:00+00:00"})
        self.assertIn("NUEVO", page)


if __name__ == "__main__":
    unittest.main()
