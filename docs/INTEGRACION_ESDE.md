# Integración con ES-DE como protector de pantalla

**Estado:** camino A instalado en la iMac el 2026-11-25: LaunchAgent cargado e imágenes generadas en `~/Library/Application Support/arcade-hall-of-fame/protector`. La configuración de ES-DE se cambia desde su menú (ES-DE estaba abierto y pisa `es_settings.xml` al salir); hay una copia previa en `~/ES-DE/settings/es_settings.xml.bak-20261125-214536`.

**Actualización del 2026-11-26:** destacados con marquee y captura, pantallas OTROS RÉCORDS y QR al final; LaunchAgent reinstalado con `WEB_PUERTO=47474` (ahora también corre a diario a las 6) y el de la página web reiniciado para que regenere con el código nuevo. Las imágenes escaladas quedan en `~/Library/Application Support/arcade-hall-of-fame/cache-medios` (se pueden borrar: se rehacen solas).

## Salón de la Fama como sistema de ES-DE

`contrib/macos/instalar_esde.sh` agrega un sistema propio para abrir la página web (alias y nombres, ver el README) desde ES-DE, como un juego más. Cómo lo resuelve ES-DE 3.0.2 en macOS:

- Los sistemas propios van en `~/ES-DE/custom_systems/es_systems.xml`, con el mismo formato que el `es_systems.xml` incluido (`<systemList><system>...`). ES-DE los lee al arrancar, junto con los suyos; un sistema solo aparece si su carpeta tiene al menos una entrada con la extensión indicada.
- El sistema: `name` `salondelafama`, `fullname` "Salón de la Fama", `path` `%ROMPATH%/salondelafama` (`ROMDirectory` vacío en `es_settings.xml`, así que `~/ROMs/salondelafama`), `extension` `.sh` y `command` `%EMULATOR_OS-SHELL% %ROM%`, igual que el sistema `ports` incluido (`OS-SHELL` es `zsh` o `bash`). `theme` `salondelafama` no existe en Linear: ES-DE muestra el nombre del sistema como texto.
- La entrada `Poner nombres.sh` abre Firefox en modo kiosco (`--kiosk`, pantalla completa sin barras) con un perfil propio (`~/Library/Application Support/arcade-hall-of-fame/firefox`, `--no-remote`), para no mezclarse con un Firefox ya abierto ni mostrar las pantallas de bienvenida. Sin `%RUNINBACKGROUND%`, ES-DE espera a que el comando termine y después vuelve a su pantalla: al cerrar Firefox con Cmd+Q se vuelve a ES-DE.
- ES-DE 3.0.2 en macOS lanza el comando con `popen` (agregando `2>&1`) y lee su salida hasta que se cierra; recién entonces vuelve. Si algún proceso que deja Firefox al salir (el `pingsender` de la telemetría, el `crashhelper`) hereda esa salida, ES-DE queda esperando y parece trancado (pasó el 2026-11-26: el registro muestra el lanzamiento y nunca la vuelta). Por eso la entrada ejecuta Firefox con la entrada y las salidas en `/dev/null`, apaga la telemetría y el `pingsender` en el `user.js` del perfil propio y, al terminar, le devuelve el foco a ES-DE con `open -a ES-DE` (si había otro Firefox abierto, macOS podía activar ese al cerrar el kiosco). `--no-remote` con `--profile` abre una instancia aparte aunque el Firefox normal esté abierto.
- Segunda trabada (2026-11-26, 18:23): había un Firefox normal reabierto por macOS al iniciar sesión ("Volver a abrir ventanas al iniciar sesión", `TALAppsToRelaunchAtLogin` en `~/Library/Preferences/ByHost/com.apple.loginwindow.*.plist`), que además quedó **detenido** (estado `T` en `ps`, sin tiempo de CPU, "Application is stopped" en `lsappinfo`). El Firefox del kiosco sí arrancó (el perfil propio muestra el arranque a las 18:23:12 y un cierre normal a las 18:25:32), pero no pasó al frente: quedó detrás de ES-DE y ES-DE, esperando, parecía colgado. Por eso la entrada ahora:
  - Lanza Firefox con `open -n -W -a Firefox --args --foreground --kiosk --no-remote --profile <perfil> <url>`: `-n` abre una instancia nueva por LaunchServices (que la trae al frente aunque haya otro Firefox, incluso uno detenido; sin `-n`, `open` le hablaría a ese), `-W` espera a que se cierre y `--foreground` hace que Firefox se active solo. Probado en la iMac con `--headless`: `open` vuelve cuando se cierra esa instancia.
  - Tiene un corte de seguridad: si en 30 segundos (`ESPERA=segundos` para cambiarlo) el Firefox del salón no arrancó o no es la aplicación al frente (`lsappinfo front`), lo cierra y vuelve a ES-DE.
  - Si quedó abierto un Firefox con el perfil del salón (perfil tomado: el nuevo mostraría "Firefox ya está abierto" detrás de ES-DE), lo cierra antes de lanzar.
  - Al final sigue con `open -a ES-DE`. Cada paso queda en `~/Library/Logs/arcade-hall-of-fame-esde.log` (lanzamiento, al frente a los N segundos, cerrado, o el corte).
  - El Firefox normal no se toca. Para que no se reabra al iniciar sesión: al apagar o cerrar sesión, desmarcar "Volver a abrir ventanas al iniciar sesión" (macOS recuerda la elección), o cerrar Firefox con Cmd+Q antes de apagar. Lo de Firefox mismo (Ajustes → General → "Abrir ventanas y pestañas anteriores") no influye en que se abra: solo en qué muestra.
- Se eligió Firefox en lugar de una ventana Tk propia: la página ya existe para el celular, se escribe con el teclado y Firefox maneja su pantalla completa sin crear un espacio aparte en el modo kiosco.

## Imagen con el QR de la página

Si la página web está instalada (`instalar_web.sh` reinstala el protector con `WEB_PUERTO=47474`), el protector agrega una imagen con el QR de la dirección actual (`http://<IP>:47474/`), solo mientras haya récords sin nombre (los de `sin-nombre`, por ejemplo un récord nuevo de Ms. Pac-Man, que no guarda iniciales): título "RECORD SIN NOMBRE" (o "RECORDS"), los primeros tres récords con su puntuación y `+N`, y abajo "ESCANEA PARA PONER TU NOMBRE" con la dirección. Los récords con iniciales no cuentan. Si todos tienen nombre, `hof-web.png` no se genera y se trata como sobrante (regla de abajo). En la página el QR está siempre. La IP se detecta en cada generación: si la Mac cambia de red, la imagen se regenera en el siguiente escaneo.

## Apagar la pantalla sin uso

Con ES-DE abierto, macOS nunca apaga la pantalla: ES-DE tiene la aserción `PreventUserIdleDisplaySleep` ("ES-DE using SDL_DisableScreenSaver", visible con `pmset -g assertions`), `coreaudiod` impide el reposo y en la iMac `pmset sleep` es 0. La pantalla queda encendida día y noche y la Mac se calienta.

`contrib/macos/apagar_pantalla.sh` apaga **solo la pantalla** con `pmset displaysleepnow` (no necesita sudo) cuando pasan 30 minutos sin teclado ni mouse. La Mac no se suspende: la página web y Tailscale siguen respondiendo. Cualquier tecla o movimiento del mouse la vuelve a encender.

- Lee el tiempo sin uso de `HIDIdleTime` (`ioreg -c IOHIDSystem`, en nanosegundos). Las aserciones de ES-DE no lo reinician; solo lo reinicia el uso real.
- Apaga una vez por período sin uso: guarda la hora del apagado en `~/Library/Application Support/arcade-hall-of-fame/apagar_pantalla.estado` y no vuelve a apagar hasta que haya uso y pase otro período completo. Así, si la pantalla se enciende sin tocar nada, no se apaga cada minuto.
- Con un juego abierto no apaga la pantalla, aunque pasen los 30 minutos: mientras corra RetroArch (`pgrep -x RetroArch`; otros procesos con `JUEGOS="RetroArch otro"`), no hace nada y el registro lo anota una vez ("juego abierto (RetroArch), no se apaga"). Al cerrar el juego, el tiempo sin uso se cuenta desde el cierre, así que no se apaga enseguida. Sirve sobre todo por los joysticks (ver abajo).
- `--prueba` solo informa qué haría, sin apagar ni guardar nada: sirve para probar la lógica con un umbral corto (`contrib/macos/apagar_pantalla.sh --prueba 5`).
- Joysticks: `HIDIdleTime` cuenta los eventos que macOS trata como teclado y mouse. Un encoder arcade que se presenta como teclado cuenta como uso. Un joystick USB genérico (página HID 1, uso 4 o 5, sin controlador) probablemente **no** lo reinicia, porque macOS no lo trata como actividad del usuario. En la iMac todavía no se comprobó con los dos joysticks "Lion King" que se conectaron el 2026-11-26 (ver la sección Joysticks). Si se conecta uno, probar `--prueba 5` mientras se lo mueve: si los segundos sin uso no vuelven a cero, el joystick no cuenta. Dentro de un juego no importa (con RetroArch abierto no se apaga); en el menú de ES-DE, usarlo solo con el joystick más de 30 minutos apagaría la pantalla, que se enciende con una tecla o el mouse.

Instalación (LaunchAgent `com.arcade-hall-of-fame.pantalla`, que corre el script cada 60 segundos):

```sh
~/arcade-hall-of-fame/contrib/macos/instalar_apagar_pantalla.sh
# otro tiempo, en segundos:
APAGAR_TRAS=3600 ~/arcade-hall-of-fame/contrib/macos/instalar_apagar_pantalla.sh
# para quitarlo:
~/arcade-hall-of-fame/contrib/macos/instalar_apagar_pantalla.sh --desinstalar
```

El registro (`~/Library/Logs/arcade-hall-of-fame-pantalla.log`) anota solo los apagados y los períodos en que no apagó por un juego abierto.

## Joysticks

En la iMac hay dos joysticks USB genéricos "Lion King" (Microntek "USB Joystick", DragonRise, VID `0x0079`, PID `0x0006`, página HID 1, uso 4). SDL los ve como 4 ejes, 12 botones y 1 hat, GUID `0300be79790000000600000007010000`. Arreglado el 2026-11-26.

**Problema 1: ES-DE se caía.** Con los joysticks conectados, ES-DE (SDL 2.30.2) se caía al arrancar o al llegar datos del joystick, con EXC_BAD_ACCESS o SIGILL en `hid_report_callback`, dentro de libSDL2. Causa: SDL trata el vendor DragonRise como posible mando de PlayStation (`HIDAPI_SupportsPlaystationDetection` en `SDL_hidapijoystick.c`). Para averiguarlo abre el dispositivo con su hidapi (`src/hidapi/mac/hid.c`), le manda reportes de prueba y lo cierra. Al cerrarlo, `hid_close` vuelve a programar el dispositivo en el run loop principal, y macOS sigue llamando al callback de reportes con el `hid_device` ya liberado: es un use-after-free. Los registros de los crashes muestran basura en la lista de reportes (`rax = "perclass"` en ASCII) y un heap corrompido en `calloc`. SDL 2.32.x tiene el mismo código: sigue haciendo la sonda para DragonRise y `hid_close` solo cambió en un detalle. No encontré un arreglo publicado, así que **no** se cambió la libSDL2 (la original 2.30.2 sigue en uso).

Arreglo: el hint `SDL_HIDAPI_IGNORE_DEVICES=0x0079/0x0006` hace que el hidapi de SDL no enumere ni abra esos joysticks. Igual funcionan por el driver IOKit de SDL. Los demás mandos siguen usando HIDAPI. El hint se pasa con `LSEnvironment` en `/Applications/ES-DE.app/Contents/Info.plist`, que llega al abrir ES-DE desde Finder, el Dock, `open -a` o los ítems de inicio de sesión. La app no está firmada, así que editar el plist no rompe ninguna firma. Después se registra de nuevo con `lsregister -f /Applications/ES-DE.app`. `launchctl setenv` no sirvió (crash 204944). Abrir ES-DE desde una sesión SSH tampoco sirve para probar: usar `open -a` desde SSH, que lo abre en la sesión gráfica. Para comprobar que la variable le llegó: `ps eww -p $(pgrep -x ES-DE) | tr ' ' '\n' | grep SDL_`.

**Si se recompila o reinstala ES-DE, el `Info.plist` se pisa y hay que volver a agregarlo:**

```sh
P=/Applications/ES-DE.app/Contents/Info.plist
/usr/libexec/PlistBuddy -c "Add :LSEnvironment dict" -c "Add :LSEnvironment:SDL_HIDAPI_IGNORE_DEVICES string 0x0079/0x0006" "$P"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f /Applications/ES-DE.app
```

**Problema 2: ES-DE no los reconocía.** ES-DE usa solo la API GameController de SDL y no tiene en cuenta los joysticks sin mapeo (`SDL_IsGameController`). SDL 2.30.2 no trae un mapeo para este GUID en macOS. Se creó `~/ES-DE/controllers/es_controller_mappings.cfg`, una copia del archivo de ejemplo de la app más la línea de la entrada "Marvo GT-004" de SDL_GameControllerDB (mismo GUID sin CRC, `03000000790000000600000007010000`, misma cantidad de botones y ejes), con el nombre "Lion King USB Joystick". El stick está mapeado como hat (dpad) y como ejes 0/1, porque no se sabe cuál de los dos usa. Con eso el log dice `Loaded 1 controller mapping` y `Added controller with default configuration: "Lion King USB Joystick"` dos veces (instance ID 0 y 1).

Falta la configuración de botones, que hace Nico frente a la Mac: en ES-DE, menú → INPUT DEVICE SETTINGS → CONFIGURE KEYBOARD AND CONTROLLERS, apretando los botones de cada joystick. Si un botón queda mal en el mapeo de SDL (por ejemplo, si el stick no mueve el cursor), se corrige en la línea del `.cfg`.

Para diagnosticar: en `~/joytest/` de la iMac hay dos programas chicos (`joytest`, `gc`) que cargan la misma libSDL2 de ES-DE y muestran los joysticks que ve SDL, su GUID y si tienen mapeo. Usarlos con `SDL_HIDAPI_IGNORE_DEVICES=0x0079/0x0006` delante.

**RetroArch** (1.22.2) no usa SDL para los mandos: `input_joypad_driver = "hid"` (IOHIDManager), así que no le afecta el crash. El registro (`--verbose`) muestra los dos joysticks: `[IOHID] Port 0/1: USB Joystick`, `0079:0006`, slots 0 y 1. Al no coincidir el nombre, la autoconfiguración eligió por VID/PID `autoconfig/hid/Retrolink_N64_USB_Controller.cfg` en los dos puertos, que es para otro mando con el mismo VID/PID; también existe `DragonRise_ZeroDelay.cfg`. Los botones de RetroArch todavía no se configuraron. Lo correcto es hacer un autoconfig propio para "USB Joystick" (Ajustes → Entrada → Controles del puerto 1 → Guardar autoconfiguración) apretando los botones.

Copias y cómo volver atrás: `~/backups/esde-joystick-20261126/` tiene el `Info.plist` y la `libSDL2-2.0.0.dylib` originales y el `es_log.txt` de antes. Para deshacer: copiar ese `Info.plist` sobre el de la app y correr `lsregister -f`; borrar `~/ES-DE/controllers/es_controller_mappings.cfg`.

## Volver atrás en la iMac

**Página web y sistema "Salón de la Fama"**, instalados en la iMac el 2026-11-26: LaunchAgent `com.arcade-hall-of-fame.web` (puerto 47474, `http://Arcade.local:47474/` o `http://192.168.1.10:47474/`), protector reinstalado con `WEB_PUERTO=47474` (imagen del QR) y el sistema en `~/ES-DE/custom_systems/es_systems.xml` con la entrada `~/ROMs/salondelafama/Poner nombres.sh`. Antes no existía ningún `es_systems.xml` propio (la carpeta `custom_systems` estaba vacía), así que no hubo nada que copiar; `es_settings.xml` no se tocó. Para que aparezca el sistema hay que reiniciar ES-DE.

Para quitarlo: `contrib/macos/instalar_esde.sh --desinstalar` (deja una copia del `es_systems.xml` antes de editarlo; o borrar el archivo, que solo tiene este sistema), `contrib/macos/instalar_web.sh --desinstalar` y, para sacar el QR de las imágenes, `contrib/macos/instalar_protector.sh`.


1. Quitar el LaunchAgent: `~/arcade-hall-of-fame/contrib/macos/instalar_protector.sh --desinstalar`.
2. Restaurar la configuración de ES-DE **con ES-DE cerrado** (si está abierto, la pisa al salir): `cp -p ~/ES-DE/settings/es_settings.xml.bak-20261125-214536 ~/ES-DE/settings/es_settings.xml`. Alternativa sin cerrar ES-DE: en el menú, SCREENSAVER TYPE → VIDEO y USE CUSTOM IMAGES desactivado.
3. Opcional: borrar la carpeta de imágenes `~/Library/Application Support/arcade-hall-of-fame/protector` y el registro `~/Library/Logs/arcade-hall-of-fame-protector.log`.

## Instalación (cuando el usuario lo confirme)

1. Generar y probar las imágenes, e instalar el LaunchAgent (desde la carpeta del repositorio clonado):

   ```sh
   contrib/macos/instalar_protector.sh
   ```

   El script verifica las rutas, corre una generación de prueba, completa la plantilla `contrib/macos/com.arcade-hall-of-fame.protector.plist.in`, la valida con `plutil` y la carga con `launchctl`. Las rutas se pueden cambiar con las variables `PYTHON`, `PARTIDAS`, `HISCORE_DAT`, `GAMELIST` y `SALIDA`. Las imágenes quedan por defecto en `~/Library/Application Support/arcade-hall-of-fame/protector` y el registro en `~/Library/Logs/arcade-hall-of-fame-protector.log`.

2. En ES-DE, en la configuración del protector de pantalla: tipo SLIDESHOW, USE CUSTOM IMAGES activado y CUSTOM IMAGE DIRECTORY apuntando a la carpeta de imágenes.

Para quitarlo: `contrib/macos/instalar_protector.sh --desinstalar` y volver a elegir el protector de video en ES-DE.

### Cuándo se regeneran las imágenes

- launchd ejecuta el comando al iniciar sesión, cada vez que cambia algo en la carpeta de partidas de FBNeo (`WatchPaths`), es decir, cuando FBNeo guarda un `.hi`, y una vez por día a las 6 (`StartCalendarInterval`; si la Mac está dormida, al despertar). La ejecución diaria es para que venzan los destacados por récord nuevo y roten los mosaicos (ver "Rotación de pantallas" en el README): el día forma parte del estado, y aun así solo se reescriben las imágenes que cambian.
- El comando escanea y compara el estado de los datos con el de la generación anterior (última tabla registrada, tabla vigente de cada juego, opciones y fecha del `gamelist.xml`). Si no cambió nada, termina sin armar ni escribir imágenes.
- Los marquees y capturas se leen de los medios de ES-DE (`~/ES-DE/downloaded_media/fbneo/...`) y entran en la huella de cada pantalla por ruta, tamaño y fecha: si ES-DE baja otra imagen, esa pantalla se reescribe en la siguiente generación que arme las pantallas (a más tardar, la del día siguiente).
- Si algo cambió, solo reescribe las pantallas cuyo contenido cambió. Escribe con un nombre temporal (`.part`) y renombra al terminar, y no toca otros archivos de la carpeta. Cada pantalla tiene un nombre fijo, sin número de orden (`hof-ranking.png`, `hof-ranking-2.png` si el ranking ocupa dos páginas, `hof-records.png`, `hof-juego-<zip>.png`, `hof-mosaico-<n>.png`, `hof-web.png`): el slideshow de ES-DE elige al azar (ver abajo), así que el orden no importa y un cambio de orden no deja archivos de más. Sobra una imagen cuando una pantalla deja de mostrarse (por ejemplo, un juego que deja de ser destacado). Si ES-DE no está abierto (`pgrep -x ES-DE`), se borra enseguida. Si está abierto, no se puede saber si su protector está en pantalla con esa imagen en la lista (borrarla mostraría negro en su turno): queda como está, sin reescribirla (no repite el ranking), anotada como relleno en el manifiesto con la hora, y se borra en la primera generación que ocurra más de 10 minutos después, aunque los datos no hayan cambiado. Así queda a lo sumo un archivo por pantalla que sobra. `protector --compactar` las borra ya (usarlo con el protector de ES-DE cerrado). Los archivos del formato anterior, numerados (`hof-003-juego-x.png`), se tratan como relleno con la misma regla.
- Poner nombre a un récord (`nombrar`) no toca la carpeta de partidas, así que launchd no se entera: por eso `nombrar` regenera las imágenes al terminar, con las opciones que el comando `protector` guarda en su manifiesto (`.hof-protector.json`).
- ES-DE 3.0.2 arma la lista de imágenes cada vez que se activa el protector (`Screensaver::startScreensaver(true)` llama a `generateCustomImageList`) y, mientras el protector sigue activo, rota sobre esa lista. Elige al azar sin repetir hasta completar la vuelta (`pickRandomCustomImage`: `std::mt19937` sobre lo que queda de la lista, y saca la elegida); al terminar, recarga la lista entera. Por eso cada copia de más de una pantalla multiplica sus apariciones. Si una imagen de la lista se borra en ese rato, `ImageComponent::setImage` no encuentra el archivo, deja la imagen sin textura y se ve la pantalla negra en su turno, sin aviso en `es_log.txt`, hasta que el protector se cierra y vuelve a activarse. Una imagen nueva no aparece hasta la siguiente activación; una reescrita se ve bien. Pasa solo si se borra una imagen con el protector de ES-DE en pantalla (por ejemplo, un juego que deja de mostrarse); de ahí la regla del relleno de arriba.
- La línea de estado de las imágenes muestra la fecha del último cambio, no la del último escaneo, para que las imágenes no cambien solo porque pasó el tiempo.

Evaluación del 2026-11-25, hecha en modo lectura sobre la iMac: ES-DE 3.0.2, `es_settings.xml`, carpeta `~/ES-DE` y la aplicación. No se cambió nada.

## Lo que hay hoy

- Protector activo: `ScreensaverType = video`, se activa a los 5 minutos (`ScreensaverTimer = 300000`).
- Opciones del slideshow presentes en 3.0.2: `ScreensaverSlideshowCustomImages` (hoy `false`), `ScreensaverSlideshowCustomDir` (vacío: usa `~/ES-DE/screensavers/custom_slideshow`, que existe y está vacía), `ScreensaverSlideshowRecurse`, `ScreensaverSwapImageTimeout` (10 s), `ScreensaverSlideshowScanlines` y `ScreensaverStretchImages`. En el menú aparecen como USE CUSTOM IMAGES, CUSTOM IMAGE DIRECTORY y CUSTOM IMAGE DIRECTORY RECURSIVE SEARCH.
- Scripts de eventos: `CustomEventScripts = false`; `~/ES-DE/scripts` está vacía. El binario incluye los eventos `startup`, `game-start`, `screensaver-start`, `screensaver-end`, `settings-changed`, `theme-changed`, `controls-changed`, `config-changed` y `reboot`. `game-end` figura en la documentación de ES-DE, pero no aparece como texto en el binario; hay que confirmarlo antes de depender de él.
- Pantalla: 1920 x 1080.

## Camino A (recomendado): slideshow de ES-DE con imágenes propias

La aplicación genera un PNG por pantalla (ranking, últimos récords y cada juego) a 1920 x 1080 en una carpeta, y el slideshow de ES-DE las muestra. ES-DE sigue manejando la pantalla, el teclado y la salida del protector: no hay ventanas compitiendo por el foco ni por el modo de pantalla completa de macOS. La generación de PNG no usa Tk; ya existe (`pantalla --capturas`) y tarda alrededor de un segundo.

Cambios en la configuración del usuario (desde el menú de ES-DE, Configuración de interfaz → Protector de pantalla):

1. Tipo de protector: SLIDESHOW (hoy es VIDEO; se dejaría de ver el protector de videos).
2. USE CUSTOM IMAGES: activado.
3. CUSTOM IMAGE DIRECTORY: una carpeta propia, por ejemplo `~/Library/Application Support/arcade-hall-of-fame/protector`, o la de ES-DE por defecto.
4. Cambio de imagen: 8 a 10 segundos (hoy, 10).
5. Líneas de barrido del slideshow: desactivadas (la imagen ya las trae) y estirar imágenes: desactivado.

Para mantener las imágenes al día se eligió un `LaunchAgent` con `WatchPaths` sobre la carpeta de partidas: no activa `CustomEventScripts` ni toca ES-DE (ver "Cuándo se regeneran las imágenes").

La generación escribe en archivos temporales y los renombra al terminar, para que ES-DE nunca lea una imagen a medio escribir, y borra las imágenes de juegos que ya no estén. Pendiente de comprobar en la iMac: que ES-DE relea la carpeta cada vez que arranca el protector, y en qué orden muestra las imágenes (si es aleatorio, el ranking puede aparecer en cualquier momento).

## Camino B: abrir la aplicación desde `screensaver-start`

Con `CustomEventScripts` activado, un script en `screensaver-start/` abriría la ventana Tk a pantalla completa y uno en `screensaver-end/` la cerraría. Problemas:

- En macOS, la pantalla completa de Tk crea su propio espacio, con la animación de cambio; queda por encima o por debajo de la ventana SDL de ES-DE según el foco.
- La tecla que despierta al usuario la recibe nuestra ventana, no ES-DE: el protector de ES-DE no termina y `screensaver-end` no se dispara. La aplicación tendría que cerrarse sola ante cualquier tecla, y ES-DE seguiría en su protector hasta otra pulsación.
- ES-DE espera a que terminen los scripts; habría que lanzar la aplicación en segundo plano.

Es más frágil y no aporta nada visible que A no tenga, salvo la animación de filas.

## Combinar con el tema de ES-DE

Pospuesto: Linear es el tema por defecto de ES-DE y el usuario todavía no eligió el suyo. Por ahora queda solo el estilo arcade. Lo que sigue documenta lo evaluado.

Tema activo: **Linear** (`linear-es-de`), incluido en ES-DE, en modo oscuro (`ThemeColorScheme = dark`) y variante con lista de texto y videos. Licencia MIT (Leon Styhre, Weestuarty); se basa en ESonline. Paleta del esquema oscuro: fondo `#373737`, texto principal `#FAFAFA`, secundario `#C2C2C2`, panel de datos `#303030`, etiquetas `#ABABAB` y barra de ayuda negra. Fuentes: Gilroy Light (títulos) y Oxygen Regular (texto).

- La licencia MIT cubre los archivos del tema; las fuentes tienen la suya. Oxygen es SIL OFL. Para Gilroy Light no hay licencia en el tema ni en `licenses/` de ES-DE, y Gilroy es una familia comercial: no conviene usarla.
- Tk no carga fuentes desde un archivo, y el generador de PNG del camino A está escrito en Python puro: usar Oxygen exigiría Pillow (una dependencia nueva) o instalar la fuente en el sistema.
- Propuesta sin dependencias: un estilo "linear" propio con su paleta, títulos alineados a la izquierda con subtítulo del tipo "Bubble Bobble / 1986 / Taito", líneas blancas finas, la barra negra de ayuda abajo, la fila destacada marcada con una barra blanca a la izquierda y un panel lateral con récord, titular y fecha. La tipografía seguiría siendo pixel propia, más fina; o, si se acepta Pillow solo para el generador, Oxygen leída en tiempo de ejecución desde la carpeta del tema, sin copiarla al repositorio.
