"""Página web local para el celular: alias de jugadores y nombres de récords.

Solo biblioteca estándar. A la izquierda (en el celular, un selector arriba),
**GLOBAL** y debajo los juegos que tienen récords de jugadores:

* **GLOBAL**: alias de iniciales que valen para todos los juegos
  (``TCH`` -> ``TINCHOVA``, hasta 12 caracteres): agregar, cambiar y borrar. Se
  guardan en la base (``player_aliases``); los de ``jugadores.json`` se
  muestran, pero se editan en el archivo (un alias de la base con las mismas
  iniciales gana). También muestra el QR con la dirección para el celular.
* **SIN LEER**: juegos con un ``.hi`` guardado que todavía no se puede leer
  (lo que muestra ``pendientes``), con el motivo y desde cuándo. Solo informa.
* **Cada juego**: su tabla con todas las filas de jugadores (no las de fábrica),
  para ponerle nombre a cada una (lo mismo que ``nombrar --puesto``) o quitárselo.

La página no escanea: lee lo que registra el LaunchAgent del protector, que
escanea cada vez que FBNeo guarda un ``.hi``. Marca como NUEVO los juegos y las
filas que aparecieron desde la visita anterior de ese navegador (una cookie con
la fecha de la visita; una visita termina tras 30 minutos sin cargar la página).

Lo que se muestra en cada fila: nombre puesto al récord > alias de las
iniciales (las del juego o las puestas) > iniciales del juego. Ver
``players.py`` y ``naming.py``.

Límite de seguridad (ver README): no tiene cuentas ni contraseñas. Está pensada
para la red de casa y se protege así:

* responde solo a clientes con dirección privada, de enlace local o del propio
  equipo (``192.168.x.x``, ``10.x.x.x``, ``172.16-31.x.x``, ``fe80::``,
  ``127.0.0.1``...) o de Tailscale (``100.64.0.0/10``, ``fd7a:115c:a1e0::/48``:
  quién entra por ahí lo decide la política del tailnet); a cualquier otro le
  devuelve 403;
* acepta solo un nombre de host que sea una dirección IP, ``localhost``, un
  nombre ``.local``, un nombre MagicDNS de Tailscale (``*.ts.net``) o el nombre
  del equipo (contra el "DNS rebinding");
* en los envíos exige que ``Origin`` (o, si falta, ``Referer``) sea esta misma
  página: otra página abierta en el celular no puede enviar el formulario;
* atiende solo ``GET /`` y los envíos ``POST /nombrar``, ``/quitar``, ``/alias``
  y ``/alias/borrar``; el resto es 404. No sirve archivos ni muestra nada más;
* valida todo lo recibido: tamaño y formato del cuerpo, juego existente, puesto
  y puntuación iguales a los de la tabla vigente, y textos de largo acotado sin
  caracteres de control.

Cualquiera conectado a la misma red puede usarla. No exponerla a Internet (no
abrir ni redirigir el puerto en el router).
"""

from __future__ import annotations

import html
import ipaddress
import re
import socket
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, urlencode, urlsplit

from .models import HighScoreError
from .naming import (MAX_INITIALS, NamingError, assign_name, clean_initials, keeps_only_top, player_rows,
                     remove_name)
from .players import (MAX_ALIAS, MAX_ALIAS_INITIALS, AliasError, Players, check_printable, clean_alias_initials,
                      clean_alias_name)
from .scanner import utc_now
from .storage import Database

DEFAULT_PORT = 47474
MAX_BODY = 2048
ORIGIN = "celular"
GLOBAL = "global"
UNREADABLE = "sin-leer"
COOKIE = "hof_visita"
VISIT_GAP = timedelta(minutes=30)  # sin cargar la página por este tiempo, empieza otra visita
_STAMP = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?\+00:00")
_WRITE_LOCK = threading.Lock()  # un cambio (y su regeneración del protector) por vez

DONE = {
    "nombrado": "Nombre guardado.",
    "quitado": "Nombre quitado.",
    "alias": "Alias guardado: ya vale en todos los juegos.",
    "alias-borrado": "Alias borrado.",
}


@dataclass
class WebConfig:
    db_path: Path
    names: Callable[[Database, List[str]], Dict[str, str]]  # juego -> nombre legible
    file_players: Callable[[], Players] = Players  # alias de jugadores.json (solo lectura)
    after_change: Callable[[Database], None] = lambda db: None  # p. ej., regenerar el protector
    qr_svg: str = ""  # QR con la dirección para el celular (se muestra en GLOBAL)
    addresses: Sequence[str] = ()  # direcciones para abrir la página
    tailscale: Sequence[str] = ()  # direcciones por Tailscale (solo texto, no van en el QR)


# --- Límites de acceso -----------------------------------------------------------

TAILSCALE_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


def is_tailscale(ip) -> bool:
    """Dirección del rango que usa Tailscale (CGNAT en IPv4, ULA propia en IPv6)."""
    return any(ip in net for net in TAILSCALE_NETWORKS if net.version == ip.version)


def allowed_client(address: str) -> bool:
    """Solo la red local (privadas, de enlace local o del propio equipo) o Tailscale."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_link_local or (ip.is_private and not ip.is_unspecified) or is_tailscale(ip)


def _host_name(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else ""
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def allowed_host(host_header: Optional[str]) -> bool:
    """Nombre de host aceptable: IP, localhost, ``*.local``, ``*.ts.net`` (MagicDNS) o el nombre del equipo."""
    if not host_header:
        return False
    name = _host_name(host_header)
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    own = socket.gethostname().lower()
    return name in ("localhost", own, own.split(".")[0]) or name.endswith((".local", ".ts.net"))


def same_origin(headers, host_header: str) -> bool:
    """El envío viene de esta misma página (Origin, o Referer si el navegador no manda Origin)."""
    source = headers.get("Origin") or headers.get("Referer")
    if not source or source == "null":
        return False
    parts = urlsplit(source)
    return parts.scheme == "http" and parts.netloc.lower() == host_header.strip().lower()


# --- Novedades desde la visita anterior ------------------------------------------

def visit_window(cookie_header: Optional[str], now: str) -> Tuple[Optional[str], str]:
    """(desde cuándo marcar NUEVO, valor nuevo de la cookie).

    La cookie guarda "última carga|inicio de la referencia". Si la última carga
    fue hace más de ``VISIT_GAP``, empieza otra visita y la referencia pasa a ser
    esa última carga. Sin cookie válida (primera visita), no se marca nada.
    """
    last = since = None
    for part in (cookie_header or "").split(";"):
        key, _, value = part.strip().partition("=")
        if key == COOKIE:
            pieces = value.split("|")
            if len(pieces) == 2 and all(_STAMP.fullmatch(p) for p in pieces):
                last, since = pieces
    if last is None:
        return None, f"{now}|{now}"
    if datetime.fromisoformat(now) - datetime.fromisoformat(last) > VISIT_GAP:
        since = last
    return since, f"{now}|{since}"


def new_marks(db: Database, since: Optional[str]) -> Tuple[Set[str], Set[Tuple[str, str, str]]]:
    """Juegos que aparecieron y filas (juego, puntos, iniciales) nuevas en su tabla, desde ``since``."""
    games: Set[str] = set()
    rows: Set[Tuple[str, str, str]] = set()
    if since is None:
        return games, rows
    for source in db.sources():
        if not source["current_observation_id"]:
            continue
        current = db.observation(source["current_observation_id"])
        if source["first_seen_utc"] > since:
            games.add(source["game"])
        if current["detected_utc"] <= since:
            continue
        previous = db.conn.execute(
            "SELECT id FROM observations WHERE game = ? AND id < ? AND detected_utc <= ? ORDER BY id DESC LIMIT 1",
            (source["game"], current["id"], since)).fetchone()
        before = {(e["score_text"], (e["initials"] or "").strip())
                  for e in (db.entries(previous["id"]) if previous else [])}
        for e in db.entries(current["id"]):
            key = (e["score_text"], (e["initials"] or "").strip())
            if not e["factory"] and key not in before:
                rows.add((source["game"],) + key)
    return games, rows


# --- Página -------------------------------------------------------------------
# Colores de la paleta del proyecto (ui/screens.py): fondo negro, título rosa,
# subtítulo violeta, juegos celestes, puntos blancos, nombres en oro.

CSS = """
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:#000;color:#fff;font:600 18px/1.35 ui-monospace,Menlo,Consolas,monospace;
  text-transform:uppercase;letter-spacing:.04em}
header{padding:16px 16px 0;text-align:center}
h1{color:#f43f5e;font-size:30px;margin:0;text-shadow:3px 3px #4c1d95}
.wrap{display:flex;gap:18px;padding:16px;max-width:1100px;margin:0 auto}
nav{flex:0 0 270px;border:3px solid #4c1d95;padding:6px 0;align-self:flex-start}
nav a{display:block;padding:9px 14px;color:#3de8ff;text-decoration:none;border-left:6px solid transparent}
nav a.global{color:#a78bfa;border-bottom:2px solid #2a1257}
nav a.on{background:#1a0b33;border-left-color:#f43f5e;color:#fff}
nav .cuenta{color:#f43f5e;float:right}
nav a.sinleer{color:#9e9e9e;border-bottom:2px solid #2a1257}
.nuevo-tag{background:#4ade80;color:#000;font-size:12px;padding:1px 5px;margin-left:6px;vertical-align:middle}
main{flex:1;min-width:0}
.selector{display:none}
h2{color:#3de8ff;font-size:24px;border-bottom:3px solid #3de8ff;padding-bottom:4px;margin:0 0 6px}
.sub{color:#a78bfa;font-size:15px;margin:0 0 10px}
.aviso{background:#3a2a00;border:1px solid #ffb300;color:#ffe082;padding:10px 12px;border-radius:6px;font-size:15px;margin:0 0 12px;text-transform:none;letter-spacing:0}
.ayuda{color:#9e9e9e;font-size:14px;margin:0 0 12px;text-transform:none;letter-spacing:0}
.fila{border-bottom:2px solid #2a1257;padding:10px 0}
.pos{color:#9e9e9e;display:inline-block;min-width:2.4em}
.pts{color:#fff;font-size:21px}
.nom{color:#facc15}
.nada{color:#787878}
.det{color:#787878;font-size:13px;text-transform:none;letter-spacing:0}
form{display:flex;gap:8px;margin-top:8px;flex-wrap:wrap}
input[type=text],select{flex:1 1 140px;min-width:0;font:inherit;font-size:22px;text-transform:uppercase;
  background:#000;color:#facc15;border:3px solid #a78bfa;padding:6px 8px;letter-spacing:.08em}
input.ini{flex:0 1 110px}
button{font:inherit;font-size:17px;padding:8px 14px;border:3px solid #f43f5e;background:#f43f5e;color:#000;
  cursor:pointer}
button.sec{background:#000;color:#f43f5e}
.msg{padding:10px 12px;margin:0 0 14px;border:3px solid}
.ok{color:#4ade80;border-color:#4ade80}
.err{color:#f43f5e;border-color:#f43f5e}
.nuevo{border:3px dashed #4c1d95;padding:10px 12px;margin-top:18px}
.qr{margin-top:24px;border:3px solid #4c1d95;padding:12px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.qr svg{width:170px;height:170px}
.qr .dir,.tailscale .dir{color:#3de8ff;word-break:break-all;text-transform:none;letter-spacing:0}
.tailscale{margin-top:12px;border:3px solid #4c1d95;padding:12px}
footer{color:#787878;font-size:13px;padding:0 16px 20px;text-align:center}
@media (max-width:720px){
  .wrap{display:block;padding:12px}
  nav{display:none}
  .selector{display:flex;margin:0 0 16px}
  h1{font-size:24px}
}
"""


def _e(text: object) -> str:
    return html.escape(str(text), quote=True)


def _input(name: str, value: str, maxlength: int, label: str, css: str = "", placeholder: str = "",
           datalist: str = "") -> str:
    extra = (f' list="{datalist}"' if datalist else "") + (f' class="{css}"' if css else "")
    return (f'<input type="text" name="{name}" value="{_e(value)}" maxlength="{maxlength}" required '
            f'autocomplete="off" autocapitalize="characters" spellcheck="false" aria-label="{_e(label)}" '
            f'placeholder="{_e(placeholder or label)}"{extra}>')


def _hidden(**fields) -> str:
    return "".join(f'<input type="hidden" name="{k}" value="{_e(v)}">' for k, v in fields.items())


def render_page(db: Database, names: Dict[str, str], file_players: Players, view: str = GLOBAL,
                message: Optional[Tuple[str, str]] = None, qr_svg: str = "", addresses: Sequence[str] = (),
                since: Optional[str] = None, tailscale: Sequence[str] = ()) -> str:
    """Página completa. ``view`` es ``GLOBAL`` (alias), ``UNREADABLE`` o el juego elegido.

    ``since``: lo detectado después se marca como NUEVO. ``tailscale``: direcciones
    por Tailscale, que se muestran en texto debajo del QR (el QR es la de la red local).
    """
    new_games, new_rows = new_marks(db, since)
    unreadable = db.unreadable()
    tag = '<span class="nuevo-tag">NUEVO</span>'
    db_aliases = db.aliases()
    players = file_players.with_aliases(db_aliases)
    rows = player_rows(db)
    games: Dict[str, list] = {}
    for r in rows:
        games.setdefault(r.game, []).append(r)
    order = sorted(games, key=lambda g: (names.get(g, g).lower(), g))
    if view not in games and view != UNREADABLE:
        view = GLOBAL

    out = ['<!doctype html><html lang="es"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>Salón de la Fama</title>', f"<style>{CSS}</style></head><body>",
           "<header><h1>Salón de la Fama</h1></header>", '<div class="wrap">']

    # Lista de la izquierda (en el celular, un selector arriba). Los juegos con
    # filas sin nombre llevan la cantidad ("2?").
    links = [f'<a href="/" class="global{" on" if view == GLOBAL else ""}">Global</a>']
    options = [f'<option value="{GLOBAL}"{" selected" if view == GLOBAL else ""}>Global: alias</option>']
    if unreadable:
        on = " on" if view == UNREADABLE else ""
        links.append(f'<a href="/?ver={UNREADABLE}" class="sinleer{on}">Sin leer ({len(unreadable)})</a>')
        options.append(f'<option value="{UNREADABLE}"{" selected" if view == UNREADABLE else ""}>'
                       f"Sin leer ({len(unreadable)})</option>")
    for game in order:
        missing = sum(1 for r in games[game] if not r.name)
        title = names.get(game, game)
        fresh = game in new_games or any(k[0] == game for k in new_rows)
        badge = f'<span class="cuenta" title="filas sin nombre">{missing}?</span>' if missing else ""
        on = ' class="on"' if view == game else ""
        links.append(f'<a href="/?{urlencode({"ver": game})}"{on}>{badge}{_e(title)}{tag if fresh else ""}</a>')
        options.append(f'<option value="{_e(game)}"{" selected" if view == game else ""}>{_e(title)}'
                       f'{f" ({missing}?)" if missing else ""}{" - NUEVO" if fresh else ""}</option>')
    out.append("<nav>" + "".join(links) + "</nav><main>")
    out.append('<form class="selector" method="get" action="/"><select name="ver" aria-label="Elegir">'
               + "".join(options) + '</select><button type="submit">Ver</button></form>')
    if message:
        kind, text = message
        out.append(f'<p class="msg {_e(kind)}" role="status">{_e(text)}</p>')
    if view == GLOBAL:
        out.append(_global_html(db_aliases, file_players, players, rows, qr_svg, addresses, tailscale))
    elif view == UNREADABLE:
        out.append(_unreadable_html(unreadable, names))
    else:
        fresh = {(score, initials) for game, score, initials in new_rows if game == view}
        out.append(_game_html(view, names.get(view, view), games[view], players, fresh,
                              view in new_games, keeps_only_top(db, view)))
    out.append("</main></div><footer>Solo funciona dentro de la red de casa (o por Tailscale).</footer></body></html>")
    return "".join(out)


def _global_html(db_aliases: Dict[str, str], file_players: Players, players: Players, rows, qr_svg: str,
                 addresses: Sequence[str], tailscale: Sequence[str] = ()) -> str:
    in_db = {a.upper() for a in db_aliases}
    file_only = {k: v for k, v in file_players.mapping.items() if k.upper() not in in_db}
    out = ["<h2>Global</h2>",
           f'<p class="sub">Alias de iniciales para todos los juegos ({len(db_aliases) + len(file_only)})</p>',
           f'<p class="ayuda">Unas iniciales y el nombre que se muestra en su lugar (hasta {MAX_ALIAS} caracteres), '
           "en todas las tablas, el ranking y las imágenes del protector. Un nombre puesto a una fila "
           "de un juego pasa por arriba del alias.</p>"]
    for initials, name in db_aliases.items():
        out.append(f'<div class="fila"><span class="pts">{_e(initials)}</span> → <span class="nom">{_e(name)}</span>'
                   f'<form method="post" action="/alias">{_hidden(iniciales=initials)}'
                   f'{_input("nombre", name, MAX_ALIAS, "Nombre para mostrar")}'
                   '<button type="submit">Cambiar</button></form>'
                   f'<form method="post" action="/alias/borrar">{_hidden(iniciales=initials)}'
                   '<button type="submit" class="sec">Borrar</button></form></div>')
    for initials, name in sorted(file_only.items()):
        out.append(f'<div class="fila"><span class="pts">{_e(initials)}</span> → <span class="nom">{_e(name)}</span>'
                   '<div class="det">Viene de jugadores.json: se cambia en ese archivo, o agregando acá un alias '
                   "con las mismas iniciales.</div></div>")
    if not db_aliases and not file_only:
        out.append('<p class="nada">Todavía no hay alias.</p>')
    aliased = {k.upper() for k in players.mapping}
    known = sorted({r.original for r in rows if r.original and r.original.upper() not in aliased})
    out.append('<datalist id="iniciales">' + "".join(f'<option value="{_e(k)}">' for k in known) + "</datalist>")
    out.append('<div class="nuevo"><div class="sub">Agregar alias</div><form method="post" action="/alias">'
               f'{_input("iniciales", "", MAX_ALIAS_INITIALS, "Iniciales", "ini", "TCH", "iniciales")}'
               f'{_input("nombre", "", MAX_ALIAS, "Nombre para mostrar", "", "NOMBRE")}'
               '<button type="submit">Agregar</button></form></div>')
    if qr_svg:
        out.append(f'<div class="qr">{qr_svg}<div><div class="sub">Escaneá para abrir en el celular</div>'
                   + "".join(f'<div class="dir">{_e(a)}</div>' for a in addresses) + "</div></div>")
    if tailscale:
        out.append('<div class="tailscale"><div class="sub">Desde fuera de casa, por Tailscale</div>'
                   + "".join(f'<div class="dir">{_e(a)}</div>' for a in tailscale) + "</div>")
    return "".join(out)


def _local(utc_text: str) -> str:
    try:
        return datetime.fromisoformat(utc_text).astimezone().strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return utc_text


def _unreadable_html(unreadable, names: Dict[str, str]) -> str:
    out = ["<h2>Sin leer</h2>",
           f'<p class="sub">Juegos con un récord guardado que todavía no se puede leer ({len(unreadable)})</p>',
           '<p class="ayuda">Se sabe que alguien jugó y FBNeo guardó la tabla, pero no qué dice. Para leerlos hay '
           "que escribir su definición (ver docs/COBERTURA_FBNEO.md, \"Agregar un juego nuevo\").</p>"]
    for r in unreadable:
        reason = r["reason"] + (f" ({r['detail']})" if r["detail"] else "")
        out.append(f'<div class="fila"><div class="pts">{_e(names.get(r["game"], r["game"]))}</div>'
                   f'<div class="det">{_e(r["game"])}: {_e(reason)}</div>'
                   f'<div class="det">Desde {_e(_local(r["first_seen_utc"]))}; última partida '
                   f'{_e(_local(r["file_mtime_utc"]))}</div></div>')
    if not unreadable:
        out.append('<p class="nada">Todos los juegos guardados se pueden leer.</p>')
    return "".join(out)


def _game_html(game: str, title: str, rows, players: Players, fresh: Set[Tuple[str, str]] = frozenset(),
               new_game: bool = False, only_top: bool = False) -> str:
    tag = '<span class="nuevo-tag">NUEVO</span>'
    out = [f"<h2>{_e(title)}{tag if new_game else ''}</h2>"]
    if only_top:
        out.append('<p class="aviso" role="note">Este juego guarda solo el récord máximo, sin iniciales. '
                   "Solo se registra una partida cuando supera el récord; las que no lo superan no quedan "
                   "guardadas.</p>")
    out += [
           '<p class="ayuda">Todas las filas de jugadores. Un nombre puesto a una fila pasa por arriba del alias '
           f"de sus iniciales (hasta {MAX_INITIALS} caracteres; si coincide con un alias, se muestra el alias). "
           "Las filas sin nombre (???) no se muestran ni suman.</p>"]
    for r in sorted(rows, key=lambda r: r.position):
        shown = players.name(r.name) if r.name else "???"
        details = []
        if r.assigned:
            details.append("nombre puesto" + (f"; el juego tenía {r.original}" if r.original else ""))
        if r.name and shown != r.name:
            details.append(f"alias de {r.name}")
        fields = _hidden(juego=game, puesto=r.position, puntos=r.score_text)
        remove = (f'<form method="post" action="/quitar">{fields}'
                  '<button type="submit" class="sec">Quitar nombre</button></form>') if r.assigned else ""
        is_new = (r.score_text, r.original or "") in fresh
        out.append(f'<div class="fila"><div class="pts"><span class="pos">{r.position}.</span>{_e(r.score_text)} '
                   f'<span class="{"nom" if r.name else "nada"}">{_e(shown)}</span>{tag if is_new else ""}</div>'
                   + (f'<div class="det">{_e("; ".join(details))}</div>' if details else "")
                   + f'<form method="post" action="/nombrar">{fields}'
                   f'{_input("nombre", r.name if r.assigned else "", MAX_INITIALS, "Nombre", "", "NOMBRE")}'
                   f'<button type="submit">{"Cambiar" if r.assigned else "Poner"}</button></form>{remove}</div>')
    return "".join(out)


# --- Servidor -------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "arcade-hall-of-fame"
    sys_version = ""
    config: WebConfig  # se asigna en make_server

    def log_message(self, format: str, *args) -> None:  # noqa: A002 (firma de la clase base)
        sys.stderr.write(f"{self.client_address[0]} {format % args}\n")

    def _send(self, status: int, body: str = "", content_type: str = "text/html; charset=utf-8",
              location: Optional[str] = None, cookie: Optional[str] = None) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", f"{COOKIE}={cookie}; Max-Age=31536000; Path=/; HttpOnly; SameSite=Strict")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                         "frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _text(self, status: int, text: str) -> None:
        self._send(status, text + "\n", "text/plain; charset=utf-8")

    def _check(self) -> bool:
        if not allowed_client(self.client_address[0]):
            self._text(403, "Solo desde la red local.")
            return False
        if not allowed_host(self.headers.get("Host")):
            self._text(400, "Nombre de host no admitido.")
            return False
        return True

    def _page(self, db: Database, status: int, message: Optional[Tuple[str, str]], view: str = GLOBAL) -> None:
        since, cookie = visit_window(self.headers.get("Cookie"), utc_now())
        games = sorted({s["game"] for s in db.sources()} | {r["game"] for r in db.unreadable()})
        self._send(status, render_page(db, self.config.names(db, games), self.config.file_players(), view, message,
                                       self.config.qr_svg, self.config.addresses, since,
                                       self.config.tailscale), cookie=cookie)

    def do_GET(self) -> None:  # noqa: N802
        if not self._check():
            return
        parts = urlsplit(self.path)
        if parts.path != "/":
            self._text(404, "No existe.")
            return
        query = parse_qs(parts.query, max_num_fields=4)
        done = (query.get("hecho") or [""])[0]
        view = (query.get("ver") or [GLOBAL])[0][:64]
        db = Database(self.config.db_path)
        try:
            self._page(db, 200, ("ok", DONE[done]) if done in DONE else None, view)
        finally:
            db.close()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self._check():
            return
        path = urlsplit(self.path).path
        if path not in ("/nombrar", "/quitar", "/alias", "/alias/borrar"):
            self._text(404, "No existe.")
            return
        if not same_origin(self.headers, self.headers.get("Host", "")):
            self._text(403, "El envío tiene que salir de esta misma página.")
            return
        content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if content_type != "application/x-www-form-urlencoded":
            self._text(415, "Formato no admitido.")
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._text(411, "Falta el largo del envío.")
            return
        if length < 0 or length > MAX_BODY:
            self._text(413, "Envío demasiado grande.")
            return
        try:
            fields = parse_qs(self.rfile.read(length).decode("utf-8"), max_num_fields=8)
        except (UnicodeDecodeError, ValueError):
            self._text(400, "Envío no válido.")
            return
        if any(len(v) != 1 for v in fields.values()):
            self._text(400, "Envío no válido.")
            return
        values = {k: v[0] for k, v in fields.items()}
        with _WRITE_LOCK:
            db = Database(self.config.db_path)
            try:
                self._apply(db, path, values)
            finally:
                db.close()

    def _apply(self, db: Database, path: str, values: Dict[str, str]) -> None:
        view = GLOBAL
        try:
            if path in ("/alias", "/alias/borrar"):
                initials = clean_alias_initials(values.get("iniciales", ""))
                if path == "/alias":
                    db.set_alias(initials, clean_alias_name(values.get("nombre", "")), utc_now())
                    done = "alias"
                else:
                    if not db.delete_alias(initials):
                        raise AliasError(f"{initials} no tiene un alias guardado acá (si viene de "
                                         "jugadores.json, se borra en ese archivo)")
                    done = "alias-borrado"
            else:
                game, score = values.get("juego", ""), values.get("puntos", "")
                if not game or len(game) > 64 or db.source(game) is None:
                    raise NamingError("ese juego no está registrado")
                view = game
                try:
                    position = int(values.get("puesto", ""))
                except ValueError:
                    raise NamingError("falta el puesto de la fila") from None
                if not score or len(score) > 32 or not 1 <= position <= 999:
                    raise NamingError("faltan datos de la fila")
                if path == "/nombrar":
                    name = clean_initials(values.get("nombre", ""))
                    check_printable(name, "el nombre")
                    assign_name(db, game, name, utc_now(), ORIGIN, score, position)
                    done = "nombrado"
                else:
                    remove_name(db, game, score, position)
                    done = "quitado"
        except HighScoreError as exc:
            self._page(db, 400, ("err", f"No se guardó: {exc}."), view)
            return
        try:
            self.config.after_change(db)
        except Exception as exc:  # el cambio ya quedó guardado; las imágenes se actualizan en el próximo escaneo
            sys.stderr.write(f"No se pudo regenerar el protector: {exc}\n")
        self._send(303, "", location="/?" + urlencode({"ver": view, "hecho": done}))


def make_server(config: WebConfig, address: str = "0.0.0.0", port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    handler = type("ConfiguredHandler", (Handler,), {"config": config})
    server = ThreadingHTTPServer((address, port), handler)
    server.daemon_threads = True
    return server
