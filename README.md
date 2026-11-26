# Arcade Hall of Fame

Proyecto para clasificar jugadores de máquinas arcade por la cantidad de juegos en los que poseen el récord número uno. Python, SQLite y funcionamiento local, independiente del frontend de emulación.

**Estado: prueba de concepto del lector (experimental).** Existe un intérprete propio, en Python y sin dependencias, del formato de definiciones de [hi2txt](https://greatstoneex.github.io/hi2txt-doc/doc/index.html). Con las definiciones publicadas por hi2txt-xml lee los `.hi` de cada juego y devuelve sus tablas (posición, puntuación, iniciales). Galaga es la prueba de concepto y Bubble Bobble el segundo caso: ambos reproducen las tablas de las fotos de la iMac. Un escaneo guarda en SQLite el historial de cada tabla y detecta récords batidos. Un comando de línea muestra el ranking de jugadores, la tabla de un juego y los últimos récords, y una pantalla arcade a pantalla completa (Tkinter) los rota sola. La compatibilidad con MAME y las integraciones con Attract-Mode y ES-DE son posteriores.

## Documentación

- [Trabajo existente: hi2txt y definiciones publicadas](docs/TRABAJO_EXISTENTE.md), con la decisión de usar sus definiciones.
- [Requisitos y reglas de clasificación](docs/REQUISITOS.md).
- [Investigación inicial de FinalBurn Neo y Galaga](docs/INVESTIGACION_GALAGA.md), con fuentes fijadas a una revisión.
- [Evidencia de Bubble Bobble](docs/INVESTIGACION_BUBBLE_BOBBLE.md): segunda tabla contrastada con archivo real.
- [Arquitectura y plan de implementación](docs/PLAN.md), con el estado de cada etapa.
- [Protocolo de validación con archivos reales](docs/VALIDACION.md) y resultados de cobertura.
- [Cobertura sobre la colección de FBNeo de la iMac](docs/COBERTURA_FBNEO.md): qué juegos se pueden leer y por qué no el resto.
- [Integración con ES-DE como protector de pantalla](docs/INTEGRACION_ESDE.md): evaluación y propuesta, sin aplicar.
- [Contribución y preparación para GitHub](CONTRIBUTING.md).

## Primer entorno objetivo

iMac Late 2013, Intel, macOS Catalina 10.15. Versiones comunicadas por el usuario: RetroArch **1.22.2 nightly** y FinalBurn Neo **1.0.0.03**. Linux será el segundo entorno de validación. La fecha/revisión de las compilaciones, el set exacto y las rutas efectivas siguen pendientes; los [pasos para localizarlos](docs/VALIDACION.md#localizar-los-archivos-en-la-imac) no requieren modificar los guardados.

El repositorio no incluye ROMs, BIOS, archivos del emulador, definiciones de terceros, bases de datos ni capturas de partidas.

## Instalación en una iMac con macOS (Catalina o posterior)

Requisitos: Git (en macOS viene con las herramientas de línea de comandos: `xcode-select --install`) y Python 3.13 del instalador oficial de [python.org](https://www.python.org/downloads/macos/), que incluye Tk 8.6. El Python que trae Catalina tiene un Tk 8.5 con fallas conocidas y no sirve para la pantalla. No hace falta instalar paquetes de Python para el proyecto, pero después de instalar Python hay que ejecutar una vez `Install Certificates.command` (en `/Applications/Python 3.13/`, doble clic o `sh "/Applications/Python 3.13/Install Certificates.command"`): sin eso las descargas del paso 3 fallan con `CERTIFICATE_VERIFY_FAILED`.

```sh
# 1. Descargar el proyecto
cd ~
git clone https://github.com/tinchova/arcade-hall-of-fame.git
cd arcade-hall-of-fame

# 2. Python 3.13 de python.org, por ruta completa
PY=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13
export PYTHONPATH=src

# 3. Descargar las definiciones de hi2txt-xml y los nombres de los juegos (a local/, fuera de Git)
$PY -m arcade_hall_of_fame.hi2txt.fetch
$PY -m arcade_hall_of_fame.fetch_names

# 4. Comprobar que todo funciona (pruebas automáticas, con datos sintéticos)
$PY -m unittest

# 5. Abrir la pantalla (escanea las partidas de FBNeo de RetroArch; Esc para salir)
$PY -m arcade_hall_of_fame pantalla \
    --carpeta "$HOME/Documents/RetroArch/saves/FinalBurn Neo/fbneo" \
    --hiscore-dat "$HOME/Documents/RetroArch/system/fbneo/hiscore.dat"
```

Si se usa ES-DE, agregar `--gamelist "$HOME/ES-DE/gamelists/fbneo/gamelist.xml"` para tomar los nombres de los juegos de ahí. Las rutas de RetroArch pueden variar según su configuración (ver [VALIDACION.md](docs/VALIDACION.md#localizar-los-archivos-en-la-imac)). El programa solo lee las partidas; su base de datos queda en `~/Library/Application Support/arcade-hall-of-fame/`.

Para actualizar:

```sh
cd ~/arcade-hall-of-fame
git pull
```

Si después de actualizar el README indica una revisión nueva de las definiciones o de los DAT, repetir el paso 3.

## Uso actual

Objetivo: Python 3.11 o posterior. El núcleo también funciona con el Python 3.8 que trae macOS Catalina, pero la pantalla necesita Tk 8.6: en la iMac se usa el Python 3.13 de python.org (`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13`). No tiene dependencias externas. Todos los comandos se ejecutan desde la raíz del repositorio.

1. Descargar las definiciones de hi2txt-xml (revisión fijada y verificada con SHA-256) a `local/`, carpeta excluida de Git:

   ```sh
   PYTHONPATH=src python -m arcade_hall_of_fame.hi2txt.fetch
   ```

   En Windows (PowerShell): `$env:PYTHONPATH="src"` antes del comando.

2. Mostrar la tabla de una copia de un `.hi` (se abre en solo lectura):

   ```sh
   PYTHONPATH=src python -m arcade_hall_of_fame.hi2txt galaga ruta/a/una/copia/galaga.hi
   ```

3. Escanear la carpeta de partidas de FBNeo y consultar (bash; la carpeta de partidas se lee en modo `rb`):

   ```sh
   export PYTHONPATH=src
   python -m arcade_hall_of_fame escanear "$HOME/Documents/RetroArch/saves/FinalBurn Neo/fbneo" \
       --hiscore-dat "$HOME/Documents/RetroArch/system/fbneo/hiscore.dat"
   python -m arcade_hall_of_fame ranking      # jugadores por cantidad de primeros puestos
   python -m arcade_hall_of_fame juego galaga # tabla vigente de un juego
   python -m arcade_hall_of_fame records      # últimos récords batidos
   python -m arcade_hall_of_fame aceptar <juego>  # aceptar un estado pendiente (máximo que bajó)
   python -m arcade_hall_of_fame pendientes   # récords que todavía no se pueden leer y récords sin nombre
   python -m arcade_hall_of_fame sin-nombre   # récords sin iniciales a los que falta ponerles nombre
   python -m arcade_hall_of_fame nombrar mspacman ANA  # poner iniciales al récord vigente de un juego
   ```

   La base SQLite va en la carpeta de datos del usuario: `~/Library/Application Support/arcade-hall-of-fame/` en macOS, `~/.local/share/arcade-hall-of-fame/` en Linux y `%LOCALAPPDATA%\arcade-hall-of-fame\` en Windows. Se puede cambiar con `--base` o con `ARCADE_HOF_BASE`; la carpeta de definiciones, con `--definiciones` o `ARCADE_HOF_DEFINICIONES`. Repetir el escaneo sobre archivos sin cambios no agrega nada.

4. Nombres de los juegos ("Bubble Bobble", no "bublbobl"): descargar los DAT de FinalBurn Neo, en una revisión fija y verificados con SHA-256, a `local/`:

   ```sh
   PYTHONPATH=src python -m arcade_hall_of_fame.fetch_names
   ```

   Si se indica el `gamelist.xml` de ES-DE (`--gamelist`), sus nombres tienen prioridad. Sin DAT ni gamelist se usa el nombre de la definición de hi2txt y, como último recurso, el del zip.

5. Pantalla arcade (Esc para salir; flechas o Enter para cambiar; Espacio para pausar):

   ```sh
   python -m arcade_hall_of_fame pantalla --carpeta "$HOME/Documents/RetroArch/saves/FinalBurn Neo/fbneo" \
       --hiscore-dat "$HOME/Documents/RetroArch/system/fbneo/hiscore.dat" \
       --gamelist "$HOME/ES-DE/gamelists/fbneo/gamelist.xml"
   ```

   Escanea al abrir y cada 60 segundos (`--escaneo`) y cambia de pantalla cada 8 (`--segundos`). Otras opciones: `--ventana 1280x720` para no usar pantalla completa, `--sin-animacion`, `--capturas <carpeta>` para guardar un PNG de cada pantalla sin abrir ventana y `--prueba` para comprobar Tk y generar las pantallas sin mostrarlas.

6. Imágenes para el protector de pantalla de ES-DE (slideshow con imágenes propias):

   ```sh
   python -m arcade_hall_of_fame protector --salida "<carpeta de imágenes>" \
       --carpeta "$HOME/Documents/RetroArch/saves/FinalBurn Neo/fbneo"
   ```

   Si los datos no cambiaron desde la vez anterior, no reescribe nada. Junto a las imágenes deja `hof-pendientes.txt`, con los juegos cuyo récord todavía no se puede leer y los récords sin nombre. En macOS, `contrib/macos/instalar_protector.sh` lo deja funcionando con un LaunchAgent que se dispara cuando cambia la carpeta de partidas; ver [INTEGRACION_ESDE.md](docs/INTEGRACION_ESDE.md).

7. Pruebas automáticas, con datos sintéticos:

   ```sh
   python -m unittest
   ```

Las iniciales son las guardadas por el juego, y el ranking las usa tal cual. Para agrupar varias iniciales de una misma persona, crear un `jugadores.json` opcional en la carpeta de datos (o indicarlo con `--jugadores`):

```json
{"jugadores": {"Ana": ["ANA", "A.N"]}}
```

Las entradas de fábrica (según las tablas `db_defaults` de hi2txt-xml) no dan crédito y no se muestran en la pantalla ni en las imágenes; un juego que solo tiene entradas de fábrica no aparece. Siguen guardadas en la base y se ven con `juego <nombre>`.

### Récords sin iniciales

Algunos juegos no guardan iniciales (Pac-Man, Ms. Pac-Man) y en otros el jugador puede no cargarlas. Ese récord se guarda, pero no suma al ranking y no se muestra hasta que alguien le pone nombre:

```sh
python -m arcade_hall_of_fame sin-nombre            # cuáles faltan (también en `pendientes` y en hof-pendientes.txt)
python -m arcade_hall_of_fame nombrar mspacman ANA  # el récord vigente de Ms. Pac-Man queda a nombre de ANA
python -m arcade_hall_of_fame nombrar mspacman ANA --puntos 25000  # igual, pero falla si el récord ya es otro
python -m arcade_hall_of_fame nombrar mspacman --quitar           # deshacer
```

El nombre queda en la base, asociado a esa puntuación exacta: desde ahí el juego aparece en su tabla con ese nombre y suma al ranking (también se agrupa con `jugadores.json`). Si después el récord cambia, el nuevo vuelve a quedar sin nombre. Las iniciales se pasan a mayúsculas y pueden tener hasta 10 caracteres. Al terminar, `nombrar` regenera las imágenes del protector si su carpeta existe (`--protector`, `ARCADE_HOF_PROTECTOR` o, por defecto, `protector/` en la carpeta de datos), con las mismas opciones que usó el comando `protector` la última vez; no hace falta esperar a otra partida.

Con `--mostrar-sin-iniciales` (o `ARCADE_HOF_MOSTRAR_SIN_INICIALES=1`), la pantalla y las imágenes muestran también los récords sin nombre, con el jugador como `???`. Está desactivada por defecto.

El primer escaneo de todo es la línea base y no anuncia récords. Un juego que aparece después (un `.hi` nuevo, como la primera partida a un juego) sí cuenta su primer récord en "últimos récords", salvo que sea una entrada de fábrica; si no tiene nombre, se muestra solo con la opción anterior.

La pantalla y las imágenes usan fondo negro puro (`#000000`), para que se confundan con los bordes negros de la pantalla.

### Juegos que no se pueden leer

Si un juego no se puede leer (no hay definición o usa una operación que el intérprete todavía no implementa), no se muestran datos: el escaneo lo anota y `pendientes` lo lista, para escribir su definición cuando haga falta ([cómo agregar un juego nuevo](docs/COBERTURA_FBNEO.md#agregar-un-juego-nuevo)). La comprobación opcional con muestras reales y la medición de cobertura se describen en [VALIDACION.md](docs/VALIDACION.md).

## Créditos

Las definiciones de juegos que usa este proyecto son obra de **GreatStoneEx (GreatStone)** y colaboradores del proyecto **hi2txt**:

- [hi2txt-xml](https://github.com/GreatStoneEx/hi2txt-xml): definiciones XML por juego. Licencia [GNU GPL versión 2](https://github.com/GreatStoneEx/hi2txt-xml/blob/990fca26edb8cd9e37ab0b569d5d59b06e31f0e0/LICENSE).
- [Documentación de hi2txt y referencia del formato XML](https://greatstoneex.github.io/hi2txt-doc/doc/xml.html), a partir de la cual se escribió el intérprete.

Los nombres de los juegos salen de los DAT de **FinalBurn Neo** ([libretro/FBNeo](https://github.com/libretro/FBNeo), revisión `d25b21e733fd4ee07980a65268abb5706fc3549d`, versión 1.0.0.03). Tampoco se redistribuyen: se descargan con `fetch_names` y conservan la licencia de FinalBurn Neo.

La tipografía pixel de la pantalla es propia del proyecto (glifos de 5 x 7 dibujados en código). La paleta parte de las recomendaciones del skill de diseño ui-ux-pro-max.

hi2txt-xml, a su vez, reconoce el trabajo de HiToText y de los mantenedores de `hiscore.dat` (Leezer y otros). Este repositorio no contiene ni redistribuye esas definiciones ni el motor de hi2txt: cada usuario las descarga con el comando anterior, y conservan su licencia original. El intérprete de este proyecto es código propio.

## Qué falta

Ver [el estado de las etapas](docs/PLAN.md#estado-de-las-etapas). En resumen: probar en Python 3.11 sobre Catalina y Linux; confirmar con un segundo estado real cuando aparezca (iniciales distintas a las de fábrica); después, el núcleo con SQLite, la clasificación general, el historial de récords y la interfaz. Un caso sintético no acredita compatibilidad real.

## Licencia

El código de este repositorio se publica con licencia [MIT](LICENSE) (Copyright (c) 2026 tinchova). Las definiciones de hi2txt-xml (GPL v2) y los DAT de FinalBurn Neo no forman parte del repositorio y conservan sus propias licencias.
