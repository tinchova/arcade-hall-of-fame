#!/bin/sh
# Apaga solo la pantalla (no suspende la Mac) cuando pasan SEGUNDOS sin usar el
# teclado ni el mouse (HIDIdleTime). ES-DE impide que macOS la apague
# solo (aserción PreventUserIdleDisplaySleep), así que esto lo hace a mano con
# "pmset displaysleepnow", que no necesita sudo. La Mac sigue despierta: la
# página web y Tailscale siguen respondiendo. Tocar una tecla o el mouse
# vuelve a encender la pantalla. Un joystick USB genérico probablemente no
# cuenta como uso (ver docs/INTEGRACION_ESDE.md).
#
# Uso: contrib/macos/apagar_pantalla.sh [--prueba] [SEGUNDOS]
#   SEGUNDOS  tiempo sin uso antes de apagar (por defecto $APAGAR_TRAS o 1800).
#   --prueba  solo informa qué haría; no apaga ni guarda nada.
# Pensado para correr cada minuto (LaunchAgent, ver instalar_apagar_pantalla.sh).
# Apaga una sola vez por período de inactividad: si alguien enciende la pantalla
# sin tocar nada (por ejemplo por la red), no la vuelve a apagar hasta que haya
# uso y otro período completo sin uso.
set -eu

PRUEBA=0
if [ "${1:-}" = "--prueba" ]; then
    PRUEBA=1
    shift
fi
SEGUNDOS="${1:-${APAGAR_TRAS:-1800}}"
case "$SEGUNDOS" in
    ''|*[!0-9]*) echo "Segundos no válidos: $SEGUNDOS" >&2; exit 2 ;;
esac
ESTADO="${ESTADO:-$HOME/Library/Application Support/arcade-hall-of-fame/apagar_pantalla.estado}"

# HIDIdleTime: nanosegundos desde el último evento de teclado, mouse o similar.
NS="$(ioreg -c IOHIDSystem | awk '/"HIDIdleTime" =/ { print $NF; exit }')"
case "$NS" in
    ''|*[!0-9]*) echo "No se pudo leer HIDIdleTime" >&2; exit 1 ;;
esac
SIN_USO=$((NS / 1000000000))
AHORA="$(date +%s)"
INICIO=$((AHORA - SIN_USO))   # cuándo empezó este período sin uso

# Último apagado hecho por este script (segundos desde 1970), si hubo.
ULTIMO=0
if [ -f "$ESTADO" ]; then
    ULTIMO="$(cat "$ESTADO" 2>/dev/null || echo 0)"
    case "$ULTIMO" in ''|*[!0-9]*) ULTIMO=0 ;; esac
fi

if [ "$SIN_USO" -lt "$SEGUNDOS" ]; then
    ACCION="nada: ${SIN_USO}s sin uso, umbral ${SEGUNDOS}s"
    APAGAR=0
elif [ "$ULTIMO" -ge "$INICIO" ]; then
    ACCION="nada: ya la apagó en este período sin uso ($(date -r "$ULTIMO" '+%Y-%m-%d %H:%M:%S'))"
    APAGAR=0
else
    ACCION="apagar la pantalla: ${SIN_USO}s sin uso, umbral ${SEGUNDOS}s"
    APAGAR=1
fi

if [ "$PRUEBA" = 1 ]; then
    echo "Prueba: $ACCION"
    exit 0
fi
if [ "$APAGAR" = 1 ]; then
    mkdir -p "$(dirname "$ESTADO")"
    echo "$AHORA" > "$ESTADO"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $ACCION"
    pmset displaysleepnow
fi
