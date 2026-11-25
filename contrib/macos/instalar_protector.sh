#!/bin/sh
# Instala el LaunchAgent que mantiene al día las imágenes del protector de ES-DE.
# No toca ES-DE: después hay que elegir el protector "slideshow" con imágenes
# propias desde su menú (ver docs/INTEGRACION_ESDE.md).
#
# Uso: contrib/macos/instalar_protector.sh            (instala y carga)
#      contrib/macos/instalar_protector.sh --desinstalar
# Variables opcionales para cambiar rutas: PYTHON, PARTIDAS, HISCORE_DAT,
# GAMELIST, SALIDA.
set -eu

LABEL="com.arcade-hall-of-fame.protector"
DESTINO="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ "${1:-}" = "--desinstalar" ]; then
    launchctl unload "$DESTINO" 2>/dev/null || true
    rm -f "$DESTINO"
    echo "LaunchAgent desinstalado. Las imágenes ya generadas quedan en su carpeta."
    exit 0
fi

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13}"
PARTIDAS="${PARTIDAS:-$HOME/Documents/RetroArch/saves/FinalBurn Neo/fbneo}"
HISCORE_DAT="${HISCORE_DAT:-$HOME/Documents/RetroArch/system/fbneo/hiscore.dat}"
GAMELIST="${GAMELIST:-$HOME/ES-DE/gamelists/fbneo/gamelist.xml}"
SALIDA="${SALIDA:-$HOME/Library/Application Support/arcade-hall-of-fame/protector}"
LOG="$HOME/Library/Logs/arcade-hall-of-fame-protector.log"

for ruta in "$PYTHON" "$PARTIDAS" "$HISCORE_DAT"; do
    if [ ! -e "$ruta" ]; then
        echo "No existe: $ruta" >&2
        exit 1
    fi
done

# Prueba manual antes de instalar: debe terminar sin errores.
(cd "$REPO" && PYTHONPATH="$REPO/src" "$PYTHON" -m arcade_hall_of_fame protector \
    --salida "$SALIDA" --carpeta "$PARTIDAS" --hiscore-dat "$HISCORE_DAT" --gamelist "$GAMELIST")

mkdir -p "$(dirname "$DESTINO")"
# Completa la plantilla con Python (escapa los valores para XML).
"$PYTHON" - "$REPO/contrib/macos/$LABEL.plist.in" "$DESTINO" \
    "@PYTHON@=$PYTHON" "@REPO@=$REPO" "@PARTIDAS@=$PARTIDAS" "@HISCORE_DAT@=$HISCORE_DAT" \
    "@GAMELIST@=$GAMELIST" "@SALIDA@=$SALIDA" "@LOG@=$LOG" <<'PY'
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
echo "LaunchAgent instalado: $DESTINO"
echo "Imágenes en: $SALIDA"
