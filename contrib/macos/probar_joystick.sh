#!/bin/sh
# Prueba de los joysticks, frente a la Mac (ver docs/JOYSTICK.md). Muestra cada
# botón, la cruz y los ejes de cada joystick, con su número en el orden del
# driver "hid" de RetroArch (#1 = puerto 1) y su locationID (el puerto USB), y
# una vez por segundo los segundos sin uso (HIDIdleTime, lo que mira
# apagar_pantalla.sh). Necesita clang (Command Line Tools).
#
# Uso: contrib/macos/probar_joystick.sh [SEGUNDOS]   (por defecto 60)
set -eu
SEGUNDOS="${1:-60}"
case "$SEGUNDOS" in
    ''|*[!0-9]*) echo "Segundos no válidos: $SEGUNDOS" >&2; exit 2 ;;
esac
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BIN="${TMPDIR:-/tmp}/joyeventos.$$"
clang -O2 -o "$BIN" "$REPO/contrib/macos/joyeventos.c" -framework IOKit -framework CoreFoundation
"$BIN" &
PID=$!
trap 'kill "$PID" 2>/dev/null; rm -f "$BIN"' EXIT INT TERM
i=0
while [ "$i" -lt "$SEGUNDOS" ]; do
    NS="$(ioreg -c IOHIDSystem | awk '/"HIDIdleTime" =/ { print $NF; exit }')"
    echo "$(date +%H:%M:%S) sin uso: $((NS / 1000000000))s"
    sleep 1
    i=$((i + 1))
done
