# Integración con ES-DE como protector de pantalla

**Estado:** camino A instalado en la iMac el 2026-11-25: LaunchAgent cargado e imágenes generadas en `~/Library/Application Support/arcade-hall-of-fame/protector`. La configuración de ES-DE se cambia desde su menú (ES-DE estaba abierto y pisa `es_settings.xml` al salir); hay una copia previa en `~/ES-DE/settings/es_settings.xml.bak-20261125-214536`.

## Salón de la Fama como sistema de ES-DE

`contrib/macos/instalar_esde.sh` agrega un sistema propio para abrir la página web (alias y nombres, ver el README) desde ES-DE, como un juego más. Cómo lo resuelve ES-DE 3.0.2 en macOS:

- Los sistemas propios van en `~/ES-DE/custom_systems/es_systems.xml`, con el mismo formato que el `es_systems.xml` incluido (`<systemList><system>...`). ES-DE los lee al arrancar, junto con los suyos; un sistema solo aparece si su carpeta tiene al menos una entrada con la extensión indicada.
- El sistema: `name` `salondelafama`, `fullname` "Salón de la Fama", `path` `%ROMPATH%/salondelafama` (`ROMDirectory` vacío en `es_settings.xml`, así que `~/ROMs/salondelafama`), `extension` `.sh` y `command` `%EMULATOR_OS-SHELL% %ROM%`, igual que el sistema `ports` incluido (`OS-SHELL` es `zsh` o `bash`). `theme` `salondelafama` no existe en Linear: ES-DE muestra el nombre del sistema como texto.
- La entrada `Poner nombres.sh` abre Firefox en modo kiosco (`--kiosk`, pantalla completa sin barras) con un perfil propio (`~/Library/Application Support/arcade-hall-of-fame/firefox`, `--no-remote`), para no mezclarse con un Firefox ya abierto ni mostrar las pantallas de bienvenida. Sin `%RUNINBACKGROUND%`, ES-DE espera a que el comando termine y después vuelve a su pantalla: al cerrar Firefox con Cmd+Q se vuelve a ES-DE.
- Se eligió Firefox en lugar de una ventana Tk propia: la página ya existe para el celular, se escribe con el teclado y Firefox maneja su pantalla completa sin crear un espacio aparte en el modo kiosco.

## Imagen con el QR de la página

Si la página web está instalada (`instalar_web.sh` reinstala el protector con `WEB_PUERTO=47474`), el protector agrega una imagen "PONER NOMBRES / ESCANEA CON EL CELULAR" con el QR de la dirección actual (`http://<IP>:47474/`) y, abajo, la dirección `.local` de la Mac. La IP se detecta en cada generación: si la Mac cambia de red, la imagen se regenera en el siguiente escaneo.

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

- launchd ejecuta el comando al iniciar sesión y cada vez que cambia algo en la carpeta de partidas de FBNeo (`WatchPaths`), es decir, cuando FBNeo guarda un `.hi`. No hay ejecuciones a intervalos fijos.
- El comando escanea y compara el estado de los datos con el de la generación anterior (última tabla registrada, tabla vigente de cada juego, opciones y fecha del `gamelist.xml`). Si no cambió nada, termina sin armar ni escribir imágenes.
- Si algo cambió, solo reescribe las pantallas cuyo contenido cambió. Escribe con un nombre temporal (`.part`) y renombra al terminar, y no toca otros archivos de la carpeta. Las imágenes propias (`hof-*.png`) que sobran (menos pantallas, o pantallas renumeradas porque entró un juego en el medio) no se borran, porque ES-DE puede tenerlas en la lista del protector activo y mostraría negro en su turno (ver abajo): se reescriben como copia del ranking y quedan anotadas como relleno en el manifiesto. Se borran en la primera generación después de un arranque del sistema (el LaunchAgent corre al iniciar sesión, antes de que el protector de ES-DE arme su lista) o con `protector --compactar`, con el protector de ES-DE cerrado.
- Poner nombre a un récord (`nombrar`) no toca la carpeta de partidas, así que launchd no se entera: por eso `nombrar` regenera las imágenes al terminar, con las opciones que el comando `protector` guarda en su manifiesto (`.hof-protector.json`).
- ES-DE 3.0.2 arma la lista de imágenes cada vez que se activa el protector (`Screensaver::startScreensaver(true)` llama a `generateCustomImageList`) y, mientras el protector sigue activo, rota sobre esa lista. Si una imagen de la lista se borra en ese rato, `ImageComponent::setImage` no encuentra el archivo, deja la imagen sin textura y se ve la pantalla negra en su turno, sin aviso en `es_log.txt`, hasta que el protector se cierra y vuelve a activarse. Una imagen nueva no aparece hasta la siguiente activación; una reescrita se ve bien. Pasa solo si el protector se regenera con el protector de ES-DE en pantalla y cambia la cantidad de imágenes (por ejemplo, un juego que deja de mostrarse).
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
