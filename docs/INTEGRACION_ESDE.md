# Integración con ES-DE como protector de pantalla

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

Para mantener las imágenes al día hay dos opciones; la elección es del usuario:

- **Scripts de eventos.** Activar `CustomEventScripts` y agregar un script en `~/ES-DE/scripts/screensaver-start/` (y en `startup/`) que, en segundo plano, escanee y regenere los PNG. Si se confirma `game-end`, regenerar al terminar cada partida es lo más preciso.
- **Agente de launchd.** Un `LaunchAgent` del usuario que regenere cada 5 minutos, sin tocar ES-DE.

La generación escribe en archivos temporales y los renombra al terminar, para que ES-DE nunca lea una imagen a medio escribir, y borra las imágenes de juegos que ya no estén. Pendiente de comprobar en la iMac: que ES-DE relea la carpeta cada vez que arranca el protector, y en qué orden muestra las imágenes (si es aleatorio, el ranking puede aparecer en cualquier momento).

## Camino B: abrir la aplicación desde `screensaver-start`

Con `CustomEventScripts` activado, un script en `screensaver-start/` abriría la ventana Tk a pantalla completa y uno en `screensaver-end/` la cerraría. Problemas:

- En macOS, la pantalla completa de Tk crea su propio espacio, con la animación de cambio; queda por encima o por debajo de la ventana SDL de ES-DE según el foco.
- La tecla que despierta al usuario la recibe nuestra ventana, no ES-DE: el protector de ES-DE no termina y `screensaver-end` no se dispara. La aplicación tendría que cerrarse sola ante cualquier tecla, y ES-DE seguiría en su protector hasta otra pulsación.
- ES-DE espera a que terminen los scripts; habría que lanzar la aplicación en segundo plano.

Es más frágil y no aporta nada visible que A no tenga, salvo la animación de filas.

## Combinar con el tema de ES-DE

Tema activo: **Linear** (`linear-es-de`), incluido en ES-DE, en modo oscuro (`ThemeColorScheme = dark`) y variante con lista de texto y videos. Licencia MIT (Leon Styhre, Weestuarty); se basa en ESonline. Paleta del esquema oscuro: fondo `#373737`, texto principal `#FAFAFA`, secundario `#C2C2C2`, panel de datos `#303030`, etiquetas `#ABABAB` y barra de ayuda negra. Fuentes: Gilroy Light (títulos) y Oxygen Regular (texto).

- La licencia MIT cubre los archivos del tema; las fuentes tienen la suya. Oxygen es SIL OFL. Para Gilroy Light no hay licencia en el tema ni en `licenses/` de ES-DE, y Gilroy es una familia comercial: no conviene usarla.
- Tk no carga fuentes desde un archivo, y el generador de PNG del camino A está escrito en Python puro: usar Oxygen exigiría Pillow (una dependencia nueva) o instalar la fuente en el sistema.
- Propuesta sin dependencias: un estilo "linear" propio con su paleta, títulos alineados a la izquierda con subtítulo del tipo "Bubble Bobble / 1986 / Taito", líneas blancas finas, la barra negra de ayuda abajo, la fila destacada marcada con una barra blanca a la izquierda y un panel lateral con récord, titular y fecha. La tipografía seguiría siendo pixel propia, más fina; o, si se acepta Pillow solo para el generador, Oxygen leída en tiempo de ejecución desde la carpeta del tema, sin copiarla al repositorio.
