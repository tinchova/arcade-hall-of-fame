#!/bin/sh
# Instala el LaunchAgent que apaga solo la pantalla (sin suspender la Mac) tras
# un rato sin teclado ni mouse. Ver apagar_pantalla.sh.
#
# Uso: contrib/macos/instalar_apagar_pantalla.sh            (instala y carga)
#      contrib/macos/instalar_apagar_pantalla.sh --desinstalar
# Variable opcional: APAGAR_TRAS (segundos sin uso, 1800 por defecto).
set -eu

LABEL="com.arcade-hall-of-fame.pantalla"
DESTINO="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SCRIPT="$REPO/contrib/macos/apagar_pantalla.sh"

if [ "${1:-}" = "--desinstalar" ]; then
    launchctl unload "$DESTINO" 2>/dev/null || true
    rm -f "$DESTINO"
    echo "Apagado de pantalla desinstalado."
    exit 0
fi

SEGUNDOS="${APAGAR_TRAS:-1800}"
case "$SEGUNDOS" in
    ''|*[!0-9]*) echo "Segundos no válidos: $SEGUNDOS" >&2; exit 1 ;;
esac
LOG="$HOME/Library/Logs/arcade-hall-of-fame-pantalla.log"

# Prueba: lee el tiempo sin uso sin apagar nada.
/bin/sh "$SCRIPT" --prueba "$SEGUNDOS"

mkdir -p "$(dirname "$DESTINO")"
sed -e "s|@SCRIPT@|$SCRIPT|g" -e "s|@SEGUNDOS@|$SEGUNDOS|g" -e "s|@LOG@|$LOG|g" \
    "$REPO/contrib/macos/$LABEL.plist.in" > "$DESTINO"
plutil -lint "$DESTINO"
launchctl unload "$DESTINO" 2>/dev/null || true
launchctl load -w "$DESTINO"
echo "Apagado de pantalla instalado: $DESTINO (tras ${SEGUNDOS}s sin uso)"
echo "Registro: $LOG"
