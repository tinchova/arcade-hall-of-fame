#!/bin/sh
# Instala el LaunchAgent de la página web (alias de jugadores y nombres de récords,
# para usar desde el celular en la red de casa). Puerto fijo: 47474.
#
# Uso: contrib/macos/instalar_web.sh            (instala y carga)
#      contrib/macos/instalar_web.sh --desinstalar
# Variables opcionales: PYTHON, PUERTO, GAMELIST.
#
# Si el LaunchAgent del protector está instalado, lo reinstala con
# WEB_PUERTO para que las imágenes incluyan el QR de la página.
set -eu

LABEL="com.arcade-hall-of-fame.web"
DESTINO="$HOME/Library/LaunchAgents/$LABEL.plist"
PROTECTOR="$HOME/Library/LaunchAgents/com.arcade-hall-of-fame.protector.plist"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"

if [ "${1:-}" = "--desinstalar" ]; then
    launchctl unload "$DESTINO" 2>/dev/null || true
    rm -f "$DESTINO"
    echo "Página web desinstalada."
    if [ -f "$PROTECTOR" ]; then
        echo "Para sacar el QR de las imágenes del protector: contrib/macos/instalar_protector.sh"
    fi
    exit 0
fi

PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13}"
PUERTO="${PUERTO:-47474}"
GAMELIST="${GAMELIST:-$HOME/ES-DE/gamelists/fbneo/gamelist.xml}"
LOG="$HOME/Library/Logs/arcade-hall-of-fame-web.log"

if [ ! -x "$PYTHON" ]; then
    echo "No existe: $PYTHON" >&2
    exit 1
fi
case "$PUERTO" in
    ''|*[!0-9]*) echo "Puerto no válido: $PUERTO" >&2; exit 1 ;;
esac

mkdir -p "$(dirname "$DESTINO")"
"$PYTHON" - "$REPO/contrib/macos/$LABEL.plist.in" "$DESTINO" \
    "@PYTHON@=$PYTHON" "@REPO@=$REPO" "@PUERTO@=$PUERTO" "@GAMELIST@=$GAMELIST" "@LOG@=$LOG" <<'PY'
import sys
from xml.sax.saxutils import escape

source, target, *pairs = sys.argv[1:]
text = open(source, encoding="utf-8").read()
for pair in pairs:
    key, value = pair.split("=", 1)
    text = text.replace(key, escape(value))
open(target, "w", encoding="utf-8").write(text)
PY
plutil -lint "$DESTINO"
launchctl unload "$DESTINO" 2>/dev/null || true
launchctl load -w "$DESTINO"

# Esperar a que responda.
i=0
until curl -fsS -o /dev/null "http://localhost:$PUERTO/" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 20 ]; then
        echo "La página no responde; ver $LOG" >&2
        exit 1
    fi
    sleep 1
done

if [ -f "$PROTECTOR" ]; then
    echo "Reinstalando el protector para agregar el QR de la página..."
    WEB_PUERTO="$PUERTO" "$REPO/contrib/macos/instalar_protector.sh"
fi

NOMBRE="$(scutil --get LocalHostName 2>/dev/null || true)"
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
echo "Página web instalada: $DESTINO"
[ -n "$NOMBRE" ] && echo "Desde el celular (misma red): http://$NOMBRE.local:$PUERTO/"
[ -n "$IP" ] && echo "                          o: http://$IP:$PUERTO/"
echo "Registro: $LOG"
