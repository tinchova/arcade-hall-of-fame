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
# Variable opcional: JUEGOS (procesos que cuentan como juego abierto,
# separados por espacios; por defecto "RetroArch").
# Mientras haya un juego abierto no apaga la pantalla (el joystick puede no
# contar como uso); al cerrarlo, el tiempo sin uso se cuenta desde el cierre.
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
JUEGO="$ESTADO.juego"          # última vez que se vio un juego abierto
AVISO="$ESTADO.aviso"          # período ya anotado como "juego abierto"
JUEGOS="${JUEGOS:-RetroArch}"

leer() {   # número guardado en un archivo, o 0
    v="$(cat "$1" 2>/dev/null || true)"
    case "$v" in ''|*[!0-9]*) v=0 ;; esac
    echo "$v"
}

# HIDIdleTime: nanosegundos desde el último evento de teclado, mouse o similar.
NS="$(ioreg -c IOHIDSystem | awk '/"HIDIdleTime" =/ { print $NF; exit }')"
case "$NS" in
    ''|*[!0-9]*) echo "No se pudo leer HIDIdleTime" >&2; exit 1 ;;
esac
SIN_USO=$((NS / 1000000000))
AHORA="$(date +%s)"
INICIO=$((AHORA - SIN_USO))   # cuándo empezó este período sin uso

ABIERTO=""
for nombre in $JUEGOS; do
    if pgrep -x "$nombre" >/dev/null 2>&1; then
        ABIERTO="$nombre"
        break
    fi
done

# Si hubo un juego abierto después del último uso, el período empieza al cerrarlo.
VISTO="$(leer "$JUEGO")"
if [ -z "$ABIERTO" ] && [ "$VISTO" -gt "$INICIO" ]; then
    INICIO="$VISTO"
    SIN_USO=$((AHORA - INICIO))
fi

# Último apagado hecho por este script (segundos desde 1970), si hubo.
ULTIMO="$(leer "$ESTADO")"

if [ -n "$ABIERTO" ]; then
    ACCION="nada: juego abierto ($ABIERTO), no se apaga (${SIN_USO}s sin uso, umbral ${SEGUNDOS}s)"
    APAGAR=0
elif [ "$SIN_USO" -lt "$SEGUNDOS" ]; then
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
mkdir -p "$(dirname "$ESTADO")"
if [ -n "$ABIERTO" ]; then
    echo "$AHORA" > "$JUEGO"
    # Anotarlo una vez por período, cuando ya habría apagado.
    if [ "$SIN_USO" -ge "$SEGUNDOS" ] && [ "$(leer "$AVISO")" != "$INICIO" ]; then
        echo "$INICIO" > "$AVISO"
        echo "$(date '+%Y-%m-%d %H:%M:%S') juego abierto ($ABIERTO), no se apaga: ${SIN_USO}s sin uso"
    fi
fi
if [ "$APAGAR" = 1 ]; then
    echo "$AHORA" > "$ESTADO"
    echo "$(date '+%Y-%m-%d %H:%M:%S') $ACCION"
    pmset displaysleepnow
fi
