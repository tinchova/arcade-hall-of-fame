#!/bin/sh
# Saca a los joysticks "Lion King" (0079:0006) del driver interno
# "DragonRise ZeroDelay Encoder" de RetroArch (ver docs/JOYSTICK.md).
#
# El driver de joypad "hid" de RetroArch para macOS trae una tabla fija de
# joysticks conocidos por VID/PID (input/connect/joypad_connection.c). La
# entrada "DragonRise ZeroDelay Encoder" (0079:0006) lee el reporte USB a su
# manera y solo da ejes si el byte de la palanca derecha vale 0x7F; los Lion
# King mandan 0x80, así que la palanca nunca se mueve en RetroArch. El parche
# cambia el PID de esa entrada (06 00 -> ff ff) para que no coincida con
# ningún joystick, y RetroArch use la lectura genérica de IOKit (palanca
# izquierda = ejes 0/1, derecha = ejes 4/5, cruz = h0, botones = número - 1).
#
# Busca la entrada (puntero al nombre + VID 0x0079 + PID 0x0006) en vez de
# usar un offset fijo, y no toca nada si no encuentra exactamente una. Hace
# copia del .app entero antes y re-firma ad hoc. Reaplicarlo después de cada
# actualización de RetroArch, con RetroArch cerrado.
#
# Uso: contrib/macos/parchear_retroarch.sh [--comprobar] [RUTA.app]
#      (por defecto /Applications/RetroArch.app; --comprobar solo informa)
set -eu
COMPROBAR=0
if [ "${1:-}" = "--comprobar" ]; then COMPROBAR=1; shift; fi
APP="${1:-/Applications/RetroArch.app}"
BIN="$APP/Contents/MacOS/RetroArch"
[ -f "$BIN" ] || { echo "No existe $BIN" >&2; exit 2; }

estado() {
    /usr/bin/python3 - "$BIN" <<'EOF'
import struct, sys
b = open(sys.argv[1], "rb").read()
nombre = b"DragonRise ZeroDelay Encoder\0"
pos = b.find(nombre)
if pos < 0 or b.find(nombre, pos + 1) >= 0:
    print("ERROR no encuentro una sola vez el nombre de la entrada"); sys.exit(0)
# Mach-O x86_64: __TEXT empieza en 0x100000000 con offset 0 en el archivo.
ptr = struct.pack("<Q", 0x100000000 + pos)
hits = [i for i in range(0, len(b) - 12, 8) if b[i:i + 8] == ptr]
if len(hits) != 1:
    print("ERROR entradas que apuntan al nombre: %d" % len(hits)); sys.exit(0)
o = hits[0] + 8
vidpid = b[o:o + 4]
if vidpid == b"\x79\x00\x06\x00":
    print("SIN_PARCHE %d" % (o + 2))
elif vidpid == b"\x79\x00\xff\xff":
    print("PARCHEADO %d" % (o + 2))
else:
    print("ERROR bytes inesperados en %#x: %s" % (o, vidpid.hex()))
EOF
}

E="$(estado)"
echo "$BIN: $E"
case "$E" in
    PARCHEADO*) exit 0 ;;
    SIN_PARCHE*) ;;
    *) exit 1 ;;
esac
[ "$COMPROBAR" = 1 ] && exit 0
if pgrep -x RetroArch >/dev/null; then
    echo "RetroArch está abierto: cerralo y volvé a correr esto." >&2; exit 1
fi
OFFSET="${E#SIN_PARCHE }"
COPIA="$HOME/backups/$(basename "$APP" .app)-original-$(date +%Y%m%d-%H%M%S).app"
mkdir -p "$HOME/backups"
cp -Rp "$APP" "$COPIA"
echo "Copia: $COPIA"
/usr/bin/python3 - "$BIN" "$OFFSET" <<'EOF'
import sys
f, o = sys.argv[1], int(sys.argv[2])
b = bytearray(open(f, "rb").read())
assert b[o - 2:o + 2] == b"\x79\x00\x06\x00"
b[o:o + 2] = b"\xff\xff"
open(f, "wb").write(b)
print("Parcheado el offset %#x" % o)
EOF
codesign -f -s - --deep "$APP"
codesign -v "$APP"
"$BIN" --version 2>&1 | head -2
echo "$BIN: $(estado)"
