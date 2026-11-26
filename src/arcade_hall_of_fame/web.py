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
* atiende solo ``GET /`` y los envíos ``POST /nombrar``, ``/quitar``, ``/alias``,
  ``/alias/borrar`` y ``/secreto`` (con frecuencia limitada); el resto es 404. No
  sirve archivos ni muestra nada más;
* valida todo lo recibido: tamaño y formato del cuerpo, juego existente, puesto
  y puntuación iguales a los de la tabla vigente, y textos de largo acotado sin
  caracteres de control.

Cualquiera conectado a la misma red puede usarla. No exponerla a Internet (no
abrir ni redirigir el puerto en el router).
"""

from __future__ import annotations

import base64
import hashlib
import html
import ipaddress
import json
import re
import socket
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, urlencode, urlsplit

from .models import HighScoreError
from .naming import (MAX_INITIALS, NamingError, assign_name, clean_initials, keeps_only_top, player_rows,
                     previous_records, previous_rows, remove_name)
from .players import (MAX_ALIAS, MAX_ALIAS_INITIALS, AliasError, Players, check_printable, clean_alias_initials,
                      clean_alias_name)
from .scanner import utc_now
from .storage import EGG_DEVICES, Database

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
body{margin:0;background:#000;color:#fff;font:600 18px/1.35 ui-monospace,Menlo,Consolas,monospace;touch-action:manipulation;
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
#titulo{cursor:default;-webkit-user-select:none;user-select:none;touch-action:manipulation;
  -webkit-tap-highlight-color:transparent}
#egg{position:fixed;inset:0;z-index:99;background:#000;overflow:hidden;touch-action:none;
  -webkit-user-select:none;user-select:none;-webkit-tap-highlight-color:transparent}
#egg canvas{position:absolute;left:0;top:0;width:100%;height:100%;display:block;cursor:crosshair}
#egg .fin{position:absolute;inset:0;display:flex;padding:16px;overflow-y:auto;background:rgba(0,0,0,.8);
  touch-action:pan-y}
#egg .caja{margin:auto;display:flex;flex-direction:column;align-items:center;gap:14px;text-align:center;max-width:100%}
#egg .caja b{color:#f43f5e;font-size:clamp(30px,9vw,84px);text-shadow:4px 4px #4c1d95;letter-spacing:.06em}
#egg .caja>span{color:#facc15;font-size:24px}
#egg .caja i{color:#9e9e9e;font-size:14px;font-style:normal;min-height:1.2em}
#egg form{justify-content:center;margin:0}
#egg input.ini3{flex:0 0 auto;width:4.4em;font-size:36px;text-align:center;letter-spacing:.25em;padding:4px 0 4px .25em}
#egg .top{list-style:none;margin:0;padding:10px 14px;border:3px solid #4c1d95;width:min(340px,100%)}
#egg .top li{display:flex;gap:14px;padding:3px 6px;color:#3de8ff}
#egg .top .p{color:#9e9e9e;min-width:2.2em;text-align:right}
#egg .top .n{color:#facc15;flex:1;text-align:left}
#egg .top li.yo{background:#1a0b33;outline:2px solid #f43f5e;color:#4ade80}
#egg .top li.yo .n{color:#4ade80}
#egg .top li.mas{color:#787878;justify-content:center}
#egg .top li.tit{color:#a78bfa;justify-content:center;border-bottom:2px solid #2a1257;margin-bottom:4px}
#egg .primero{display:flex;flex-direction:column;gap:8px;border:3px solid #4ade80;padding:12px 16px;color:#4ade80;font-size:22px}
#egg .primero span+span{color:#facc15}
"""


# Easter egg: 7 toques seguidos en el título abren un minijuego (atrapar 20 lentes que
# caen, lo más rápido posible). Va inline y la CSP lo permite por su hash, no con
# 'unsafe-inline'. Dibuja todo en un solo <canvas>; el tiempo se guarda con POST /secreto.
EGG_JS = """(function(){
var h=document.getElementById('titulo');if(!h)return;
var TOTAL=20,EN_PANTALLA=4,CORTE=180000;
var taps=[],box=null,raf=0,medir=null;
var LENTE='M5 4L112 7Q120 8 119 16L117 30Q114 44 100 44L88 44Q77 44 73 35Q69 27 62 27Q55 27 51 35Q47 44 34 43L22 42Q10 41 8 30L5 17Q3 9 5 4Z';
h.addEventListener('click',function(){
  var t=Date.now();taps.push(t);taps=taps.filter(function(x){return t-x<3000;});
  if(taps.length>=7&&!box){taps=[];abrir();}
});
document.addEventListener('keydown',function(e){if(box&&e.key==='Escape'){e.preventDefault();cerrar();}});
function seg(ms){return (ms/1000).toFixed(3);}
function el(p,tag,txt,cls){var e=document.createElement(tag);e.textContent=txt;if(cls)e.className=cls;p.appendChild(e);return e;}
function sprite(px){
  var c=document.createElement('canvas'),k=px/120;c.width=px;c.height=Math.ceil(64*k);
  var g=c.getContext('2d');g.scale(k,k);g.fillStyle='#8b0016';g.fill(new Path2D(LENTE));
  g.strokeStyle='#fff';g.lineWidth=2;g.lineCap='round';g.beginPath();g.moveTo(36,54);g.lineTo(66,59);g.stroke();
  return c;
}
function abrir(){
  box=document.createElement('div');box.id='egg';box.setAttribute('role','dialog');box.setAttribute('aria-label','Minijuego');
  var cv=document.createElement('canvas');box.appendChild(cv);document.body.appendChild(box);
  document.documentElement.style.overflow='hidden';
  var g=cv.getContext('2d',{alpha:false}),W=1,H=1,dpr=1,base=90,img=null;
  medir=function(){
    dpr=Math.min(2,window.devicePixelRatio||1);W=innerWidth;H=innerHeight;
    cv.width=Math.round(W*dpr);cv.height=Math.round(H*dpr);base=Math.max(60,Math.min(120,W/6));
    img=sprite(Math.ceil(base*1.3*dpr));
  };
  medir();window.addEventListener('resize',medir);
  var lentes=[],chispas=[],atrapados=0,toques=0,lanzados=0,t0=performance.now(),prev=t0,ult=-1e9,fin=false;
  function lanzar(l){
    l=l||{};l.w=base*(0.8+Math.random()*0.45);l.h=l.w*64/120;
    l.x=l.w/2+Math.random()*Math.max(1,W-l.w);l.y=-l.w/2;l.v=H*(0.12+Math.random()*0.1);
    l.a=Math.random()*6.283;l.g=(Math.random()-0.5)*0.7;return l;
  }
  cv.addEventListener('pointerdown',function(e){
    e.preventDefault();if(fin)return;
    var r=cv.getBoundingClientRect(),px=e.clientX-r.left,py=e.clientY-r.top;
    for(var i=lentes.length-1;i>=0;i--){
      var l=lentes[i],dx=px-l.x,dy=py-l.y,c=Math.cos(l.a),s=Math.sin(l.a),u=dx*c+dy*s,v=dy*c-dx*s;
      if(Math.abs(u)<=l.w/2+8&&Math.abs(v)<=l.h/2+10){
        lentes.splice(i,1);pop(l);atrapados++;if(e.pointerType==='touch')toques++;
        if(atrapados>=TOTAL)terminar(Math.max(1,Math.round(performance.now()-t0)),false);
        return;
      }
    }
  });
  function pop(l){
    for(var i=0;i<10;i++){var a=i/10*6.283+Math.random()*0.3;
      chispas.push({x:l.x,y:l.y,vx:Math.cos(a)*120,vy:Math.sin(a)*120,t:0,c:i%4?'#8b0016':'#fff'});}
  }
  function dibujar(now,dt){
    g.setTransform(1,0,0,1,0,0);g.fillStyle='#000';g.fillRect(0,0,cv.width,cv.height);
    for(var i=0;i<lentes.length;i++){
      var l=lentes[i];l.y+=l.v*dt;l.a+=l.g*dt;
      if(l.y-l.w>H)lanzar(l);
      var c=Math.cos(l.a)*dpr,s=Math.sin(l.a)*dpr;
      g.setTransform(c,s,-s,c,l.x*dpr,l.y*dpr);g.drawImage(img,-l.w/2,-l.h/2,l.w,l.h);
    }
    g.setTransform(dpr,0,0,dpr,0,0);
    for(i=chispas.length-1;i>=0;i--){
      var p=chispas[i];p.t+=dt;if(p.t>0.45){chispas.splice(i,1);continue;}
      var q=Math.floor(p.t*12)/12;g.globalAlpha=1-q/0.45;g.fillStyle=p.c;
      g.fillRect(Math.round(p.x+p.vx*q)-5,Math.round(p.y+p.vy*q)-5,10,10);
    }
    g.globalAlpha=1;g.fillStyle='#3de8ff';g.font='600 18px ui-monospace,Menlo,Consolas,monospace';
    g.textAlign='center';g.textBaseline='top';
    g.fillText('LENTES '+atrapados+'/'+TOTAL+'   '+seg(now-t0),W/2,10);
  }
  function paso(now){
    if(!box||fin)return;
    var dt=Math.min(0.05,Math.max(0,(now-prev)/1000));prev=now;
    if(lentes.length<EN_PANTALLA&&lanzados<TOTAL&&now-ult>450){ult=now;lanzados++;lentes.push(lanzar(null));}
    dibujar(now,dt);
    if(now-t0>CORTE){terminar(0,true);return;}
    raf=requestAnimationFrame(paso);
  }
  function terminar(ms,corte){
    fin=true;cancelAnimationFrame(raf);
    var tipo=toques*2>=TOTAL?'celular':'pc',listo=false,f=document.createElement('div');f.className='fin';
    var w=el(f,'div','','caja');el(w,'b','BY TINCHOVA007');
    el(w,'span',corte?'TIEMPO AGOTADO':'TIEMPO '+seg(ms)+' s');
    var vol=document.createElement('button');vol.type='button';vol.className='sec';vol.textContent='Volver';
    vol.addEventListener('click',cerrar);
    if(corte){setTimeout(function(){listo=true;},800);}
    else{
      var fo=el(w,'form','');
      var inp=document.createElement('input');inp.type='text';inp.maxLength=3;inp.className='ini3';inp.placeholder='AAA';
      inp.autocomplete='off';inp.spellcheck=false;inp.setAttribute('autocapitalize','characters');
      inp.setAttribute('aria-label','Tus iniciales');fo.appendChild(inp);
      var bt=el(fo,'button','Guardar');bt.type='submit';
      inp.addEventListener('input',function(){
        var v=inp.value.toUpperCase().replace(/[^A-Z0-9]/g,'').slice(0,3);if(v!==inp.value)inp.value=v;
      });
      var msg=el(w,'i','Tus iniciales: hasta 3 letras o n\\u00fameros');
      fo.addEventListener('submit',function(e){
        e.preventDefault();var v=inp.value;
        if(!/^[A-Z0-9]{1,3}$/.test(v)){msg.textContent='Hasta 3 letras o n\\u00fameros';inp.focus();return;}
        bt.disabled=true;msg.textContent='Guardando...';
        fetch('/secreto',{method:'POST',credentials:'same-origin',
          headers:{'Content-Type':'application/x-www-form-urlencoded'},
          body:'iniciales='+encodeURIComponent(v)+'&tiempo='+ms+'&tipo='+tipo})
        .then(function(r){return r.json().then(function(d){if(!r.ok)throw new Error(d.error||'error');return d;});})
        .then(function(d){fo.remove();msg.remove();tabla(w,vol,d);setTimeout(function(){listo=true;},600);})
        .catch(function(err){bt.disabled=false;msg.textContent='No se guard\\u00f3: '+err.message;});
      });
      setTimeout(function(){inp.focus();},50);
    }
    w.appendChild(vol);
    f.addEventListener('click',function(e){if(listo&&e.target.tagName!=='BUTTON')cerrar();});
    box.appendChild(f);
  }
  function tabla(w,vol,d){
    var ol=document.createElement('ol');ol.className='top';
    function fila(pos,ini,ms,yo){var li=el(ol,'li','',yo?'yo':'');el(li,'span',pos+'.','p');el(li,'span',ini,'n');el(li,'span',seg(ms));}
    var donde=d.tipo==='celular'?'CELULAR':'PC';
    if(d.primero){var pr=document.createElement('div');pr.className='primero';
      el(pr,'span','\\u00a1PRIMER R\\u00c9CORD EN '+donde+'!');el(pr,'span',d.ini+'  '+seg(d.ms)+' s');w.insertBefore(pr,vol);}
    else{
      el(ol,'li','TOP 10 '+donde,'tit');
      for(var i=0;i<d.top.length;i++)fila(i+1,d.top[i].ini,d.top[i].ms,d.top[i].nuevo);
      if(d.puesto>d.top.length){el(ol,'li','...','mas');fila(d.puesto,d.ini,d.ms,true);}
      w.insertBefore(ol,vol);
    }el(w,'i','Toc\\u00e1 o Esc para volver');
  }
  raf=requestAnimationFrame(paso);
}
function cerrar(){
  cancelAnimationFrame(raf);if(medir)window.removeEventListener('resize',medir);
  if(box)box.remove();box=null;medir=null;document.documentElement.style.overflow='';
}
})();"""
EGG_INITIALS = re.compile(r"[A-Z0-9]{1,3}")
EGG_MIN_MS, EGG_MAX_MS = 2000, 180000  # un tiempo fuera de esto no se guarda


class RateLimit:
    """Frecuencia de envíos por cliente: uno cada ``gap`` segundos y hasta ``per_hour`` por hora."""

    def __init__(self, gap: float = 5.0, per_hour: int = 30):
        self.gap, self.per_hour = gap, per_hour
        self._seen: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def allow(self, client: str, now: Optional[float] = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            for key in [k for k, v in self._seen.items() if now - v[-1] > 3600]:
                del self._seen[key]  # olvida a los que no envían hace más de una hora
            times = [t for t in self._seen.get(client, []) if now - t < 3600]
            if (times and now - times[-1] < self.gap) or len(times) >= self.per_hour:
                self._seen[client] = times or [now]
                return False
            self._seen[client] = times + [now]
            return True


EGG_CSP = "'sha256-" + base64.b64encode(hashlib.sha256(EGG_JS.encode("utf-8")).digest()).decode("ascii") + "'"


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
           '<header><h1 id="titulo">Salón de la Fama</h1></header>', '<div class="wrap">']

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
        out.append(_game_html(view, names.get(view, view), games[view] + previous_rows(db, view), players, fresh,
                              view in new_games, keeps_only_top(db, view)))
    out.append("</main></div><footer>Solo funciona dentro de la red de casa (o por Tailscale).</footer>"
               f"<script>{EGG_JS}</script></body></html>")
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
        if r.previous:  # récord anterior (juegos que guardan solo el máximo): se elige por la puntuación
            fields = _hidden(juego=game, puntos=r.score_text, historial="1")
            details.append(f"récord anterior, detectado el {_local(r.detected_utc)}: no suma al ranking")
        else:
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
    limiter: "RateLimit"  # frecuencia de envíos del minijuego; se asigna en make_server

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
                         f"default-src 'none'; style-src 'unsafe-inline'; script-src {EGG_CSP}; "
                         "connect-src 'self'; form-action 'self'; "
                         "frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")

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
        if path not in ("/nombrar", "/quitar", "/alias", "/alias/borrar", "/secreto"):
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
        if path == "/secreto":
            self._egg(values)
            return
        with _WRITE_LOCK:
            db = Database(self.config.db_path)
            try:
                self._apply(db, path, values)
            finally:
                db.close()

    def _egg(self, values: Dict[str, str]) -> None:
        """Tiempo del minijuego secreto: lo guarda y devuelve el TOP 10 de su tipo (en JSON)."""
        if not self.limiter.allow(self.client_address[0]):
            self._json(429, {"error": "demasiados env\u00edos seguidos; prob\u00e1 en un rato"})
            return
        initials, device, raw = values.get("iniciales", ""), values.get("tipo", ""), values.get("tiempo", "")
        if not EGG_INITIALS.fullmatch(initials):
            self._json(400, {"error": "las iniciales son hasta 3 letras o n\u00fameros"})
            return
        if device not in EGG_DEVICES:
            self._json(400, {"error": "tipo de partida no v\u00e1lido"})
            return
        if not (raw.isascii() and raw.isdigit() and len(raw) <= 7 and EGG_MIN_MS <= int(raw) <= EGG_MAX_MS):
            self._json(400, {"error": "tiempo no v\u00e1lido"})
            return
        ms = int(raw)
        with _WRITE_LOCK:
            db = Database(self.config.db_path)
            try:
                new_id, rank, count = db.add_egg_time(device, initials, ms, utc_now())
                top = [{"ini": r["initials"], "ms": r["time_ms"], "nuevo": r["id"] == new_id}
                       for r in db.egg_top(device, 10)]
            finally:
                db.close()
        self._json(200, {"tipo": device, "ini": initials, "ms": ms, "puesto": rank, "primero": count == 1,
                         "top": top})

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
                if values.get("historial") == "1":  # récord anterior: se elige solo por la puntuación
                    position = None
                    if not any(r.score_text == score for r in previous_records(db, game)):
                        raise NamingError("ese récord anterior no está en el historial del juego")
                else:
                    try:
                        position = int(values.get("puesto", ""))
                    except ValueError:
                        raise NamingError("falta el puesto de la fila") from None
                    if not 1 <= position <= 999:
                        raise NamingError("faltan datos de la fila")
                if not score or len(score) > 32:
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
    handler = type("ConfiguredHandler", (Handler,), {"config": config, "limiter": RateLimit()})
    server = ThreadingHTTPServer((address, port), handler)
    server.daemon_threads = True
    return server
