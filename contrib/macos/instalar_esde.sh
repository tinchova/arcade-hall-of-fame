#!/bin/sh
# Agrega a ES-DE un sistema propio, "Otros" (nombre interno salondelafama), con
# dos entradas:
#   - "Salón de la Fama": abre la página web en Firefox a pantalla completa
#     (modo kiosco). Al cerrar Firefox (Cmd+Q) se vuelve a ES-DE.
#   - "Apagar la Mac": apaga la Mac en orden. Pide confirmación con el joystick:
#     hay que elegirla dos veces en 15 segundos (la primera vez avisa con una
#     notificación y con voz y vuelve enseguida a ES-DE).
#
# Uso: contrib/macos/instalar_esde.sh             (instala)
#      contrib/macos/instalar_esde.sh --desinstalar
# Variables opcionales: PUERTO (47474), FIREFOX, ROMS (carpeta de ROMs de ES-DE),
# MEDIOS (carpeta downloaded_media de ES-DE).
# Cada lanzamiento queda en ~/Library/Logs/arcade-hall-of-fame-esde.log.
#
# Toca solo ~/ES-DE/custom_systems/es_systems.xml (antes hace una copia con la
# fecha, si existe), crea la carpeta <ROMs>/salondelafama y copia las imágenes
# de las entradas (contrib/esde/medios) a <MEDIOS>/salondelafama. No toca
# es_settings.xml ni el tema. ES-DE lee los sistemas al arrancar: reiniciarlo.
set -eu

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13}"
PUERTO="${PUERTO:-47474}"
FIREFOX="${FIREFOX:-/Applications/Firefox.app/Contents/MacOS/firefox}"
APP="${FIREFOX%/Contents/MacOS/*}"
ESDE="$HOME/ES-DE"
SISTEMAS="$ESDE/custom_systems/es_systems.xml"
SISTEMA="salondelafama"

# Lee un valor de es_settings.xml (solo lectura); vacío si no está.
ajuste() {
    "$PYTHON" - "$ESDE/settings/es_settings.xml" "$1" <<'PY'
import sys
import xml.etree.ElementTree as ET
try:
    text = open(sys.argv[1], encoding="utf-8").read()
    root = ET.fromstring("<r>" + text.split("?>", 1)[-1] + "</r>")
    value = next((e.get("value", "") for e in root.iter("string") if e.get("name") == sys.argv[2]), "")
except (OSError, ET.ParseError):
    value = ""
print(value)
PY
}

# Carpeta de ROMs: la de es_settings.xml o ~/ROMs, la de ES-DE por defecto.
if [ -z "${ROMS:-}" ]; then
    ROMS="$(ajuste ROMDirectory)"
    ROMS="${ROMS:-$HOME/ROMs}"
    case "$ROMS" in "~"/*) ROMS="$HOME/${ROMS#\~/}" ;; esac
fi
# Carpeta de medios: la de es_settings.xml o ~/ES-DE/downloaded_media.
if [ -z "${MEDIOS:-}" ]; then
    MEDIOS="$(ajuste MediaDirectory)"
    MEDIOS="${MEDIOS:-$ESDE/downloaded_media}"
    case "$MEDIOS" in "~"/*) MEDIOS="$HOME/${MEDIOS#\~/}" ;; esac
fi
CARPETA="$ROMS/$SISTEMA"
SALON="Salón de la Fama"
APAGAR="Apagar la Mac"
# ES-DE busca la imagen de cada entrada por su nombre de archivo, según el tipo
# que pida el tema: miximages (lista), screenshots y covers (carrusel).
TIPOS_MEDIOS="miximages screenshots covers"

copia() {
    if [ -f "$SISTEMAS" ]; then
        COPIA="$SISTEMAS.bak-$(date +%Y%m%d-%H%M%S)"
        cp -p "$SISTEMAS" "$COPIA"
        echo "Copia de seguridad: $COPIA"
    fi
}

# Agrega (o quita, con "quitar") el sistema en es_systems.xml, conservando los demás.
editar() {
    mkdir -p "$(dirname "$SISTEMAS")"
    "$PYTHON" - "$SISTEMAS" "$1" "$SISTEMA" <<'PY'
import os
import sys
import xml.etree.ElementTree as ET

path, action, name = sys.argv[1:]
if os.path.isfile(path):
    root = ET.parse(path).getroot()
else:
    root = ET.Element("systemList")
for system in list(root.findall("system")):
    if (system.findtext("name") or "").strip() == name:
        root.remove(system)
if action == "agregar":
    system = ET.SubElement(root, "system")
    for tag, text in (("name", name), ("fullname", "Otros"), ("path", f"%ROMPATH%/{name}"),
                      ("extension", ".sh"), ("command", "%EMULATOR_OS-SHELL% %ROM%"), ("platform", "pc"),
                      ("theme", name)):
        child = ET.SubElement(system, tag)
        child.text = text
        if tag == "command":
            child.set("label", "Script")
ET.indent(root, space="    ")
data = '<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
tmp = path + ".part"
with open(tmp, "w", encoding="utf-8") as out:
    out.write(data)
os.replace(tmp, path)
PY
}

if [ "${1:-}" = "--desinstalar" ]; then
    if [ -f "$SISTEMAS" ]; then
        copia
        editar quitar
    fi
    rm -f "$CARPETA/Poner nombres.sh" "$CARPETA/$SALON.sh" "$CARPETA/$APAGAR.sh"
    rmdir "$CARPETA" 2>/dev/null || true
    for tipo in $TIPOS_MEDIOS; do
        rm -f "$MEDIOS/$SISTEMA/$tipo/$SALON.png" "$MEDIOS/$SISTEMA/$tipo/$APAGAR.png"
        rmdir "$MEDIOS/$SISTEMA/$tipo" 2>/dev/null || true
    done
    rmdir "$MEDIOS/$SISTEMA" 2>/dev/null || true
    echo "Sistema \"Otros\" quitado de ES-DE (reiniciar ES-DE)."
    exit 0
fi

for ruta in "$PYTHON" "$FIREFOX"; do
    if [ ! -x "$ruta" ]; then
        echo "No existe: $ruta" >&2
        exit 1
    fi
done
case "$APP" in
    *.app) ;;
    *) echo "FIREFOX tiene que estar dentro de una aplicación (.app): $FIREFOX" >&2; exit 1 ;;
esac
case "$PUERTO" in
    ''|*[!0-9]*) echo "Puerto no válido: $PUERTO" >&2; exit 1 ;;
esac

copia
editar agregar
mkdir -p "$CARPETA"
# Hasta el 2026-11-27 la entrada de la página se llamaba "Poner nombres".
rm -f "$CARPETA/Poner nombres.sh"
ENTRADA="$CARPETA/$SALON.sh"
# La entrada: abre la página en Firefox, con un perfil propio, y espera a que se
# cierre (ES-DE espera a que termine para volver). Si la página no está andando
# (LaunchAgent sin instalar), la levanta solo mientras Firefox está abierto.
cat > "$ENTRADA" <<EOF
#!/bin/sh
# Generado por arcade-hall-of-fame/contrib/macos/instalar_esde.sh.
# Abre la página del Salón de la Fama en Firefox (modo kiosco). Cmd+Q vuelve a ES-DE.
URL="http://localhost:$PUERTO/"
PERFIL="\$HOME/Library/Application Support/arcade-hall-of-fame/firefox"
mkdir -p "\$PERFIL"
cat > "\$PERFIL/user.js" <<'PREFS'
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("startup.homepage_welcome_url", "");
user_pref("startup.homepage_welcome_url.additional", "");
user_pref("datareporting.policy.dataSubmissionPolicyBypassNotification", true);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.tabs.warnOnClose", false);
user_pref("app.update.auto", false);
user_pref("toolkit.telemetry.shutdownPingSender.enabled", false);
user_pref("toolkit.telemetry.shutdownPingSender.enabledFirstSession", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("toolkit.telemetry.archive.enabled", false);
user_pref("toolkit.telemetry.unified", false);
user_pref("datareporting.healthreport.uploadEnabled", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
PREFS
TEMPORAL=""
if ! curl -fsS -m 3 -o /dev/null "\$URL" </dev/null >/dev/null 2>&1; then
    "$REPO/hof" web --direccion 127.0.0.1 --puerto "$PUERTO" </dev/null >/dev/null 2>&1 &
    TEMPORAL=\$!
    sleep 2
fi
# Registro de cada lanzamiento, para ver qué pasó si ES-DE no vuelve.
REGISTRO="\$HOME/Library/Logs/arcade-hall-of-fame-esde.log"
anotar() { echo "\$(date '+%Y-%m-%d %H:%M:%S') \$*" >>"\$REGISTRO" 2>/dev/null || true; }
# Segundos que tiene Firefox para arrancar y quedar al frente; si no, se vuelve a ES-DE.
ESPERA=\${ESPERA:-30}
# El Firefox del salón (el proceso principal, no el "open" que lo lanza).
firefox_salon() { pgrep -n -f "MacOS/firefox .*--profile \$PERFIL" 2>/dev/null; }
# PID de la aplicación que está al frente.
al_frente() { lsappinfo info -only pid "\$(lsappinfo front 2>/dev/null)" 2>/dev/null | sed -n 's/.*=//p'; }
cerrar_firefox() {
    kill "\$1" 2>/dev/null || return 0
    n=0
    while kill -0 "\$1" 2>/dev/null && [ \$n -lt 10 ]; do sleep 1; n=\$((n + 1)); done
    kill -9 "\$1" 2>/dev/null || true
}

# Un Firefox del salón que quedó de antes tiene el perfil tomado: el nuevo
# mostraría "Firefox ya está abierto" detrás de ES-DE. Se cierra primero.
VIEJO="\$(firefox_salon)"
if [ -n "\$VIEJO" ]; then
    anotar "quedaba un Firefox del salón abierto (pid \$VIEJO): se cierra"
    cerrar_firefox "\$VIEJO"
fi

# "open -n -W": una instancia nueva por LaunchServices, que macOS trae al frente
# aunque haya otro Firefox abierto (o detenido), y "open" espera a que se cierre.
# --foreground: Firefox se activa solo al arrancar. --no-remote con un perfil
# propio: no se mezcla con el Firefox normal. Entrada y salidas a /dev/null:
# ES-DE lee la salida del comando hasta que se cierra y un proceso que Firefox
# deja vivo al salir (pingsender, crashhelper) lo dejaría esperando.
anotar "lanzando Firefox (\$URL)"
open -n -W -a "$APP" --args --foreground --kiosk --no-remote --profile "\$PERFIL" "\$URL" </dev/null >/dev/null 2>&1 &
ABRIR=\$!
FIREFOX_PID=""
FRENTE=""
t=0
while [ \$t -lt "\$ESPERA" ]; do
    sleep 1
    t=\$((t + 1))
    kill -0 "\$ABRIR" 2>/dev/null || break
    [ -n "\$FIREFOX_PID" ] || FIREFOX_PID="\$(firefox_salon)"
    if [ -n "\$FIREFOX_PID" ] && [ "\$(al_frente)" = "\$FIREFOX_PID" ]; then
        FRENTE=1
        break
    fi
done
if [ -n "\$FRENTE" ]; then
    anotar "Firefox \$FIREFOX_PID al frente a los \${t}s"
    wait "\$ABRIR" 2>/dev/null || true
    anotar "Firefox cerrado"
elif kill -0 "\$ABRIR" 2>/dev/null; then
    # Corte de seguridad: no arrancó o quedó escondido detrás de ES-DE.
    anotar "Firefox (pid \${FIREFOX_PID:-ninguno}) no quedó al frente en \${ESPERA}s: se cierra y se vuelve a ES-DE (al frente: pid \$(al_frente))"
    [ -z "\$FIREFOX_PID" ] || cerrar_firefox "\$FIREFOX_PID"
    kill "\$ABRIR" 2>/dev/null || true
else
    anotar "Firefox terminó antes de quedar al frente (pid \${FIREFOX_PID:-ninguno})"
fi
if [ -n "\$TEMPORAL" ]; then
    kill "\$TEMPORAL" 2>/dev/null || true
fi
# Al cerrar Firefox, macOS puede pasarle el foco a otra aplicación (otro Firefox,
# el Finder): se lo devolvemos a ES-DE.
open -a ES-DE >/dev/null 2>&1 || true
EOF
chmod +x "$ENTRADA"

# "Apagar la Mac", con confirmación pensada para el joystick: la primera vez
# guarda la hora en una marca, avisa y vuelve enseguida a ES-DE; si se vuelve a
# elegir dentro del plazo, apaga. Si el aviso no se ve, no pasa nada: la marca vence.
APAGADO="$CARPETA/$APAGAR.sh"
cat > "$APAGADO" <<'EOF'
#!/bin/sh
# Generado por arcade-hall-of-fame/contrib/macos/instalar_esde.sh.
# Apaga la Mac en orden (como el menú Apple > Apagar: las aplicaciones, incluido
# ES-DE, se cierran bien). Sin sudo. Para confirmar con el joystick hay que
# elegir "Apagar la Mac" dos veces en PLAZO segundos: la primera vez solo avisa
# (notificación y voz) y vuelve enseguida a ES-DE.
# "sh 'Apagar la Mac.sh' --prueba" muestra qué haría, sin avisar ni apagar.
PLAZO=15
VOZ=  # voz de "say" (por ejemplo Diego, es_AR); vacía para no hablar (por defecto, sin voz)
DIR="$HOME/Library/Application Support/arcade-hall-of-fame"
MARCA="$DIR/apagar.marca"
REGISTRO="$HOME/Library/Logs/arcade-hall-of-fame-esde.log"
anotar() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >>"$REGISTRO" 2>/dev/null || true; }
PRUEBA=""
[ "${1:-}" = "--prueba" ] && PRUEBA=1

AHORA=$(date +%s)
ANTES=$(cat "$MARCA" 2>/dev/null)
case "$ANTES" in ''|*[!0-9]*) ANTES=0 ;; esac
rm -f "$MARCA"
PASO=$((AHORA - ANTES))
if [ "$PASO" -ge 0 ] && [ "$PASO" -le "$PLAZO" ]; then
    if [ -n "$PRUEBA" ]; then
        echo "prueba: confirmado a los ${PASO}s, apagaría la Mac"
        exit 0
    fi
    anotar "apagar: confirmado a los ${PASO}s, se apaga la Mac"
    /usr/bin/osascript -e 'tell application "loginwindow" to «event aevtrsdn»' </dev/null >/dev/null 2>&1 &
    exit 0
fi

mkdir -p "$DIR"
echo "$AHORA" >"$MARCA"
if [ -n "$PRUEBA" ]; then
    echo "prueba: primera vez, esperaría la confirmación ${PLAZO}s"
    exit 0
fi
anotar "apagar: primera vez, se espera la confirmación ${PLAZO}s"
# El aviso va en segundo plano y sin la salida de ES-DE (que lee la salida del
# comando hasta que se cierra): el script termina ya y ES-DE vuelve enseguida.
(
    /usr/bin/osascript -e "display notification \"Volvé a elegir Apagar la Mac en los próximos $PLAZO segundos para confirmar.\" with title \"¿Apagar la Mac?\" sound name \"Submarine\""
    [ -z "$VOZ" ] || /usr/bin/say -v "$VOZ" "Para apagar, elegí de nuevo Apagar la Mac." || /usr/bin/say "Para apagar, elegí de nuevo Apagar la Mac."
) </dev/null >/dev/null 2>&1 &
exit 0
EOF
chmod +x "$APAGADO"

# Imágenes de las entradas (las genera contrib/esde/generar_otros.py).
for tipo in $TIPOS_MEDIOS; do
    mkdir -p "$MEDIOS/$SISTEMA/$tipo"
    for nombre in "$SALON" "$APAGAR"; do
        cp "$REPO/contrib/esde/medios/$nombre.png" "$MEDIOS/$SISTEMA/$tipo/$nombre.png"
    done
done

echo "Sistema \"Otros\" agregado: $SISTEMAS"
echo "Entradas: $ENTRADA"
echo "          $APAGADO"
echo "Imágenes: $MEDIOS/$SISTEMA/{$(echo "$TIPOS_MEDIOS" | tr ' ' ',')}"
echo "Reiniciar ES-DE para que aparezca. En Firefox, Cmd+Q vuelve a ES-DE."
