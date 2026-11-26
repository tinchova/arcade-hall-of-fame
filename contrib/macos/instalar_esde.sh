#!/bin/sh
# Agrega a ES-DE un sistema propio, "Salón de la Fama", con una sola entrada
# ("Poner nombres") que abre la página web en Firefox a pantalla completa
# (modo kiosco). Al cerrar Firefox (Cmd+Q) se vuelve a ES-DE.
#
# Uso: contrib/macos/instalar_esde.sh             (instala)
#      contrib/macos/instalar_esde.sh --desinstalar
# Variables opcionales: PUERTO (47474), FIREFOX, ROMS (carpeta de ROMs de ES-DE).
#
# Toca solo ~/ES-DE/custom_systems/es_systems.xml (antes hace una copia con la
# fecha, si existe) y crea la carpeta <ROMs>/salondelafama. No toca
# es_settings.xml. ES-DE lee los sistemas al arrancar: reiniciarlo para verlo.
set -eu

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON="${PYTHON:-/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13}"
PUERTO="${PUERTO:-47474}"
FIREFOX="${FIREFOX:-/Applications/Firefox.app/Contents/MacOS/firefox}"
ESDE="$HOME/ES-DE"
SISTEMAS="$ESDE/custom_systems/es_systems.xml"
SISTEMA="salondelafama"

# Carpeta de ROMs: la de es_settings.xml (solo lectura) o ~/ROMs, la de ES-DE por defecto.
if [ -z "${ROMS:-}" ]; then
    ROMS="$("$PYTHON" - "$ESDE/settings/es_settings.xml" <<'PY'
import sys
import xml.etree.ElementTree as ET
try:
    text = open(sys.argv[1], encoding="utf-8").read()
    root = ET.fromstring("<r>" + text.split("?>", 1)[-1] + "</r>")
    value = next((e.get("value", "") for e in root.iter("string") if e.get("name") == "ROMDirectory"), "")
except (OSError, ET.ParseError):
    value = ""
print(value)
PY
)"
    ROMS="${ROMS:-$HOME/ROMs}"
    case "$ROMS" in "~"/*) ROMS="$HOME/${ROMS#\~/}" ;; esac
fi
CARPETA="$ROMS/$SISTEMA"

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
    for tag, text in (("name", name), ("fullname", "Salón de la Fama"), ("path", f"%ROMPATH%/{name}"),
                      ("extension", ".sh"), ("command", "%EMULATOR_OS-SHELL% %ROM%"), ("platform", "pc"),
                      ("theme", name)):
        child = ET.SubElement(system, tag)
        child.text = text
        if tag == "command":
            child.set("label", "Firefox (modo kiosco)")
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
    rm -f "$CARPETA/Poner nombres.sh"
    rmdir "$CARPETA" 2>/dev/null || true
    echo "Sistema \"Salón de la Fama\" quitado de ES-DE (reiniciar ES-DE)."
    exit 0
fi

for ruta in "$PYTHON" "$FIREFOX"; do
    if [ ! -x "$ruta" ]; then
        echo "No existe: $ruta" >&2
        exit 1
    fi
done
case "$PUERTO" in
    ''|*[!0-9]*) echo "Puerto no válido: $PUERTO" >&2; exit 1 ;;
esac

copia
editar agregar
mkdir -p "$CARPETA"
ENTRADA="$CARPETA/Poner nombres.sh"
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
PREFS
TEMPORAL=""
if ! curl -fsS -o /dev/null "\$URL" 2>/dev/null; then
    "$REPO/hof" web --direccion 127.0.0.1 --puerto "$PUERTO" >/dev/null 2>&1 &
    TEMPORAL=\$!
    sleep 2
fi
"$FIREFOX" --kiosk --no-remote --profile "\$PERFIL" "\$URL"
if [ -n "\$TEMPORAL" ]; then
    kill "\$TEMPORAL" 2>/dev/null || true
fi
EOF
chmod +x "$ENTRADA"
echo "Sistema \"Salón de la Fama\" agregado: $SISTEMAS"
echo "Entrada: $ENTRADA"
echo "Reiniciar ES-DE para que aparezca. En Firefox, Cmd+Q vuelve a ES-DE."
