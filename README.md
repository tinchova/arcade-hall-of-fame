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

6. Pruebas automáticas, con datos sintéticos:

   ```sh
   python -m unittest
   ```

Las iniciales son las guardadas por el juego, y el ranking las usa tal cual. Para agrupar varias iniciales de una misma persona, crear un `jugadores.json` opcional en la carpeta de datos (o indicarlo con `--jugadores`):

```json
{"jugadores": {"Ana": ["NIC", "N.C"]}}
```

 No dan crédito las entradas de fábrica (según las tablas `db_defaults` de hi2txt-xml) ni los juegos que no guardan iniciales, como Pac-Man; esos juegos sí aparecen en su tabla. Si una definición usa una operación que el intérprete todavía no implementa, el error lo dice y no se muestran datos. La comprobación opcional con muestras reales y la medición de cobertura se describen en [VALIDACION.md](docs/VALIDACION.md).

## Créditos

Las definiciones de juegos que usa este proyecto son obra de **GreatStoneEx (GreatStone)** y colaboradores del proyecto **hi2txt**:

- [hi2txt-xml](https://github.com/GreatStoneEx/hi2txt-xml): definiciones XML por juego. Licencia [GNU GPL versión 2](https://github.com/GreatStoneEx/hi2txt-xml/blob/990fca26edb8cd9e37ab0b569d5d59b06e31f0e0/LICENSE).
- [Documentación de hi2txt y referencia del formato XML](https://greatstoneex.github.io/hi2txt-doc/doc/xml.html), a partir de la cual se escribió el intérprete.

Los nombres de los juegos salen de los DAT de **FinalBurn Neo** ([libretro/FBNeo](https://github.com/libretro/FBNeo), revisión `d25b21e733fd4ee07980a65268abb5706fc3549d`, versión 1.0.0.03). Tampoco se redistribuyen: se descargan con `fetch_names` y conservan la licencia de FinalBurn Neo.

La tipografía pixel de la pantalla es propia del proyecto (glifos de 5 x 7 dibujados en código). La paleta parte de las recomendaciones del skill de diseño ui-ux-pro-max.

hi2txt-xml, a su vez, reconoce el trabajo de HiToText y de los mantenedores de `hiscore.dat` (Leezer y otros). Este repositorio no contiene ni redistribuye esas definiciones ni el motor de hi2txt: cada usuario las descarga con el comando anterior, y conservan su licencia original. El intérprete de este proyecto es código propio.

## Qué falta

Ver [el estado de las etapas](docs/PLAN.md#estado-de-las-etapas). En resumen: probar en Python 3.11 sobre Catalina y Linux; confirmar con un segundo estado real cuando aparezca (iniciales distintas a las de fábrica); después, el núcleo con SQLite, la clasificación general, el historial de récords y la interfaz. Un caso sintético no acredita compatibilidad real.

La licencia del código propio está pendiente de decisión. El código y los recursos de terceros conservan sus condiciones originales.
