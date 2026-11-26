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
- [Integración con ES-DE](docs/INTEGRACION_ESDE.md): protector de pantalla con imágenes propias y sistema "Salón de la Fama" que abre la página web.
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

## Uso en la Mac: el comando `hof`

`python3.13 -m arcade_hall_of_fame` solo funciona desde la carpeta del repositorio y con `PYTHONPATH=src`. Para no depender de eso, el repositorio trae el script `hof`: usa el Python 3.13 de python.org (si no está, `python3`), arma solo el `PYTHONPATH` y se puede llamar desde cualquier carpeta. Para copiar y pegar en la Terminal de la Mac:

```sh
# Qué récords no tienen nombre (sin iniciales: no se muestran ni suman al ranking)
~/arcade-hall-of-fame/hof sin-nombre

# Ponerle nombre al récord (1º) de un juego: hasta 12 caracteres, se pasa a mayúsculas
~/arcade-hall-of-fame/hof nombrar mspacman CAMILA

# Cambiar otra fila de la tabla: la que hoy dice TCH, o la del puesto 3
~/arcade-hall-of-fame/hof nombrar bublbobl CAMILA --de TCH
~/arcade-hall-of-fame/hof nombrar bublbobl CAMILA --puesto 3

# Si dos filas dicen lo mismo, pide el puesto o los puntos
~/arcade-hall-of-fame/hof nombrar bublbobl CAMILA --de TCH --puntos 30000

# Quitar un nombre puesto (vuelven las iniciales del juego, o queda sin nombre)
~/arcade-hall-of-fame/hof nombrar mspacman --quitar
~/arcade-hall-of-fame/hof nombrar bublbobl --quitar --de CAMILA

# Ranking, tabla de un juego y últimos récords
~/arcade-hall-of-fame/hof ranking
~/arcade-hall-of-fame/hof juego bublbobl
~/arcade-hall-of-fame/hof records

# Regenerar ya las imágenes del protector de ES-DE (el LaunchAgent lo hace solo)
~/arcade-hall-of-fame/hof protector \
    --salida "$HOME/Library/Application Support/arcade-hall-of-fame/protector" \
    --carpeta "$HOME/Documents/RetroArch/saves/FinalBurn Neo/fbneo" \
    --hiscore-dat "$HOME/Documents/RetroArch/system/fbneo/hiscore.dat" \
    --gamelist "$HOME/ES-DE/gamelists/fbneo/gamelist.xml" --web-puerto 47474
```

`nombrar` y la página web regeneran las imágenes del protector al guardar. Para nombres de una misma persona en todos los juegos (por ejemplo, que TCH se muestre como TINCHOVA), conviene un alias: se cargan en la página web (sección GLOBAL).

## Página web para el celular

Una página muy simple, para usar desde el celular en la red de casa:

- **GLOBAL**: alias de iniciales que valen para todos los juegos (TCH → TINCHOVA, hasta 12 caracteres): agregar, cambiar y borrar. Se aplican a todas las filas con esas iniciales, en el ranking, las tablas y las imágenes del protector. Muestra también el QR con la dirección de la página.
- **SIN LEER**: juegos con un `.hi` guardado que todavía no se puede leer, con el motivo y desde cuándo (solo informa: hay que escribir su definición).
- **Cada juego** con récords: su tabla con todas las filas de jugadores, para ponerle nombre a cada una (como `nombrar --puesto`) o quitárselo. Los juegos con filas sin nombre llevan la cantidad (`2?`), y lo que apareció desde la visita anterior se marca NUEVO. Si el juego guarda solo el récord máximo, sin tabla ni iniciales (Pac-Man, Ms. Pac-Man: se deduce de la tabla que devuelve la definición, una sola fila sin iniciales), la página lo avisa: solo queda registrada una partida cuando supera el récord. En esos juegos la tabla muestra a los que fueron rompiendo el récord (ver [Récords sin iniciales](#récords-sin-iniciales-y-nombres-puestos-a-mano)), cada uno con su campo para el nombre.

Lo que se muestra en cada fila: **nombre puesto a esa fila > alias de sus iniciales > iniciales del juego**. El alias también se aplica a un nombre puesto: si a un récord sin iniciales se le pone TCH, se muestra TINCHOVA. El ranking agrupa por ese nombre final, sin distinguir mayúsculas ni espacios. Los alias se guardan en la base; los de `jugadores.json` siguen valiendo y se muestran, pero se cambian en el archivo (un alias de la base con las mismas iniciales gana).

La página no escanea por su cuenta: lee lo que registra el LaunchAgent del protector, que escanea cada vez que FBNeo guarda un `.hi`.

Instalación en la Mac (LaunchAgent que la deja andando, también después de reiniciar):

```sh
~/arcade-hall-of-fame/contrib/macos/instalar_web.sh
# para quitarla:
~/arcade-hall-of-fame/contrib/macos/instalar_web.sh --desinstalar
```

Puerto fijo: **47474** (se cambia con `PUERTO=...`). Direcciones para abrirla desde el celular, conectado al mismo wifi:

- `http://<nombre de la Mac>.local:47474/`: no depende de la IP, así que sigue sirviendo si la Mac se lleva a otra casa. El nombre es el de `scutil --get LocalHostName` (Preferencias del Sistema → Compartir; en la iMac, `Arcade`, o sea `http://Arcade.local:47474/`). iPhone lo resuelve siempre; algunos Android, no.
- `http://<IP de la Mac>:47474/`: la IP actual, que es la que va en el QR. El QR se muestra siempre en la página (GLOBAL). En el protector de ES-DE va como una imagen más solo mientras haya récords sin nombre (los mismos que lista `sin-nombre`): "RECORD SIN NOMBRE" (o "RECORDS"), los primeros tres con su puntuación y `+N` si hay más (por ejemplo, `MS. PAC-MAN 18310`), el QR y "ESCANEA PARA PONER TU NOMBRE". Cuando todos tienen nombre, la imagen deja de generarse y se borra como cualquier pantalla que sobra. Si la IP cambia, la imagen se regenera.

Para probarla sin instalar: `~/arcade-hall-of-fame/hof web` (Ctrl+C para cerrarla).

### Desde fuera de casa, por Tailscale

Si la Mac está en un tailnet de [Tailscale](https://tailscale.com/), la página también responde a los equipos del tailnet, sin abrir ningún puerto en el router:

- `http://<IP de Tailscale de la Mac>:47474/` (la que da `tailscale ip -4`, del rango `100.x.y.z`), o
- `http://<nombre de la Mac>.<tailnet>.ts.net:47474/`, con MagicDNS activado.

Al arrancar, la página busca la IP de Tailscale (`/usr/local/bin/tailscale ip -4`, o la aplicación de Tailscale) y, si la hay, la muestra en texto debajo del QR. El QR sigue siendo la dirección de la red local, para el celular conectado al wifi. Si Tailscale se conecta después de arrancar la página, la dirección aparece al reiniciar el LaunchAgent (`launchctl kickstart -k gui/$(id -u)/com.arcade-hall-of-fame.web`).

Quién del tailnet puede entrar lo decide la política de acceso del tailnet (ACL): la página no agrega cuentas propias. Para limitarla, permitir en la política solo el puerto 47474 de la Mac a los usuarios o equipos que corresponda.

### Límite de seguridad

La página **no tiene cuentas ni contraseñas**: cualquiera conectado a la misma red (el wifi de casa) puede cambiar nombres y alias. Está pensada solo para eso, y se protege así:

- escucha en el puerto 47474 y responde solo a direcciones de la red local (`192.168.x.x`, `10.x.x.x`, `172.16-31.x.x`, enlace local y el propio equipo) y a las de Tailscale (`100.64.0.0/10` y `fd7a:115c:a1e0::/48`); a cualquier otra le devuelve 403;
- acepta solo pedidos dirigidos a una IP, a `localhost`, a un nombre `.local` o a un nombre MagicDNS de Tailscale (`.ts.net`) (contra el "DNS rebinding": una página de Internet no puede usar el navegador del celular para hablarle);
- los envíos tienen que salir de la misma página (`Origin`/`Referer`): otra página abierta en el celular no puede mandar el formulario;
- solo atiende la página y cuatro envíos (`/nombrar`, `/quitar`, `/alias`, `/alias/borrar`); no sirve archivos ni muestra otra cosa, y valida todo lo que recibe (tamaño, formato, juego, puesto y puntos de la fila, largo y caracteres del texto);
- no usa JavaScript, y la página prohíbe cargar cualquier recurso externo (Content-Security-Policy).

**No abrir ni redirigir el puerto 47474 en el router**: expuesta a Internet, cualquiera podría cambiar los nombres.

### Abrirla desde ES-DE

`contrib/macos/instalar_esde.sh` agrega a ES-DE un sistema propio, **Salón de la Fama**, con una entrada, **Poner nombres**, que abre la página en Firefox a pantalla completa (modo kiosco, con un perfil propio). Al cerrar Firefox con **Cmd+Q** se vuelve a ES-DE. Si la página no está instalada como LaunchAgent, la entrada la levanta mientras Firefox está abierto.

```sh
~/arcade-hall-of-fame/contrib/macos/instalar_esde.sh
# para quitarlo:
~/arcade-hall-of-fame/contrib/macos/instalar_esde.sh --desinstalar
```

Toca solo `~/ES-DE/custom_systems/es_systems.xml` (antes deja una copia con la fecha, `es_systems.xml.bak-AAAAMMDD-HHMMSS`) y crea `~/ROMs/salondelafama/Poner nombres.sh`. No toca `es_settings.xml`. ES-DE lee los sistemas al arrancar: hay que cerrarlo y volver a abrirlo para que aparezca. Ver [INTEGRACION_ESDE.md](docs/INTEGRACION_ESDE.md#salón-de-la-fama-como-sistema-de-es-de).

### Apagar la pantalla sin uso

ES-DE no deja que macOS apague la pantalla. `contrib/macos/instalar_apagar_pantalla.sh` instala un LaunchAgent que, tras 30 minutos sin teclado ni mouse (`APAGAR_TRAS=segundos` para cambiarlo), apaga solo la pantalla con `pmset displaysleepnow`, sin suspender la Mac: la página y Tailscale siguen andando. Con un juego abierto (RetroArch) no la apaga. Detalles y límites (joysticks) en [INTEGRACION_ESDE.md](docs/INTEGRACION_ESDE.md#apagar-la-pantalla-sin-uso).

## Uso actual

Objetivo: Python 3.11 o posterior. El núcleo también funciona con el Python 3.8 que trae macOS Catalina, pero la pantalla necesita Tk 8.6: en la iMac se usa el Python 3.13 de python.org (`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13`). No tiene dependencias externas. Los comandos de esta sección se ejecutan desde la raíz del repositorio con `PYTHONPATH=src`; en la Mac es más simple el script `hof` (sección anterior), que funciona desde cualquier carpeta.

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
   python -m arcade_hall_of_fame records      # últimos récords
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

   Escanea al abrir y cada 60 segundos (`--escaneo`) y cambia de pantalla cada 8 (`--segundos`). Otras opciones: `--ventana 1280x720` para no usar pantalla completa, `--sin-animacion`, `--capturas <carpeta>` para guardar un PNG de cada pantalla sin abrir ventana y `--prueba` para comprobar Tk y generar las pantallas sin mostrarlas. La rotación y las imágenes de los juegos se describen en [Rotación de pantallas](#rotación-de-pantallas).

6. Imágenes para el protector de pantalla de ES-DE (slideshow con imágenes propias):

   ```sh
   python -m arcade_hall_of_fame protector --salida "<carpeta de imágenes>" \
       --carpeta "$HOME/Documents/RetroArch/saves/FinalBurn Neo/fbneo"
   ```

   Si los datos no cambiaron desde la vez anterior, no reescribe nada. Cada pantalla tiene un nombre fijo (`hof-ranking.png`, `hof-records.png`, `hof-juego-<zip>.png`, `hof-mosaico-<n>.png`, `hof-web.png` solo si hay récords sin nombre), sin número de orden: ES-DE las elige al azar. La imagen de una pantalla que deja de mostrarse se borra enseguida si ES-DE está cerrado; si está abierto (podría tenerla en la lista de su protector y mostraría negro en su lugar) queda como está y se borra en la primera generación pasados 10 minutos, o con `protector --compactar`. Junto a las imágenes deja `hof-pendientes.txt`, con los juegos cuyo récord todavía no se puede leer y los récords sin nombre. Acepta las opciones de la rotación (`--destacados`, `--dias-destacado`, `--mosaico`, `--mosaicos`, `--medios`, `--sin-imagenes`; ver [Rotación de pantallas](#rotación-de-pantallas)). En macOS, `contrib/macos/instalar_protector.sh` lo deja funcionando con un LaunchAgent que se dispara cuando cambia la carpeta de partidas y una vez por día; ver [INTEGRACION_ESDE.md](docs/INTEGRACION_ESDE.md).

7. Pruebas automáticas, con datos sintéticos:

   ```sh
   python -m unittest
   ```

Las iniciales son las guardadas por el juego, y el ranking las usa tal cual. Para agrupar varias iniciales de una misma persona, crear un `jugadores.json` opcional en la carpeta de datos (o indicarlo con `--jugadores`):

```json
{"jugadores": {"Ana": ["ANA", "A.N"]}}
```

Las entradas de fábrica (según las tablas `db_defaults` de hi2txt-xml) se ignoran del todo para el ranking, los récords y las tablas que se muestran: el primer puesto de un juego es su mejor entrada que no es de fábrica (si tiene nombre), aunque la fábrica tenga más puntos, y los puestos que se muestran se renumeran sin ellas. Por ejemplo, si 1942 tiene la fábrica en los tres primeros lugares y TCH en el cuarto, TCH es el 1º. Un juego que solo tiene entradas de fábrica no aparece. Siguen guardadas en la base y `juego <nombre>` las lista como referencia, sin puesto y con su posición original en el juego. El puesto de `nombrar --puesto` es el que se muestra, sin la fábrica.

### Récords sin iniciales y nombres puestos a mano

Algunos juegos no guardan iniciales (Pac-Man, Ms. Pac-Man) y en otros el jugador puede no cargarlas. Ese récord se guarda, pero no suma al ranking y no se muestra hasta que alguien le pone nombre, con `nombrar` o desde la página web:

```sh
python -m arcade_hall_of_fame sin-nombre            # cuáles faltan (también en `pendientes` y en hof-pendientes.txt)
python -m arcade_hall_of_fame nombrar mspacman ANA  # el récord vigente de Ms. Pac-Man queda a nombre de ANA
python -m arcade_hall_of_fame nombrar mspacman ANA --puntos 25000  # igual, pero falla si el récord ya es otro
python -m arcade_hall_of_fame nombrar bublbobl CAMILA --de TCH     # la fila que hoy dice TCH
python -m arcade_hall_of_fame nombrar bublbobl CAMILA --puesto 3   # la fila del puesto 3
python -m arcade_hall_of_fame nombrar mspacman --quitar           # deshacer
```

Sin opciones, `nombrar` actúa sobre el récord (1º). `--de` elige la fila por el nombre que se ve hoy (las iniciales del juego o un nombre ya puesto) y `--puesto` por su posición en la tabla vigente; si dos filas tienen el mismo nombre, pide `--puesto` o `--puntos`. `--quitar` acepta las mismas opciones.

**Juegos que guardan solo el máximo** (Pac-Man, Ms. Pac-Man y cualquier otro cuya tabla vigente sea una sola fila sin iniciales): cada partida que supera el récord deja una tabla nueva en el historial, así que los récords anteriores se conocen. La tabla del juego (en el protector, la ventana y la página web) los muestra debajo del vigente, como una tabla normal, del mayor al menor y con los mismos colores del podio; los que no tienen nombre se ocultan como siempre (salvo con `--mostrar-sin-iniciales`). Se nombran eligiéndolos por la puntuación: `nombrar mspacman ANA --puntos 12000` (y `--quitar --puntos 12000`), o desde la página, con el campo de cada fila. El nombre se ve en la tabla y en últimos récords, pero en el TOP GLOBAL ese juego da un primer puesto solo al récord vigente, y un récord anterior sin nombre no hace aparecer la imagen del QR.

`nombrar` también cambia las iniciales de una fila que sí las tiene, por ejemplo las que el juego propone por defecto: `nombrar bublbobl ANA` reemplaza las del récord vigente de Bubble Bobble para esa puntuación. Las originales quedan guardadas: `juego bublbobl` las muestra y `nombrar bublbobl --quitar` las devuelve. Dos filas empatadas en puntos con iniciales distintas no se pueden cambiar.

El nombre queda en la base, atado a esa fila exacta (juego, puntuación e iniciales originales): desde ahí aparece en su tabla con ese nombre y suma al ranking. Si la fila baja de puesto porque otro la supera, conserva el nombre; si el récord cambia, el nuevo vuelve a quedar sin nombre. Los nombres y los alias se pasan a mayúsculas y pueden tener hasta 12 caracteres, que es lo que entra en la columna JUGADOR de todas las pantallas (por eso la fecha de últimos récords va sin hora). Al terminar, `nombrar` regenera las imágenes del protector si su carpeta existe (`--protector`, `ARCADE_HOF_PROTECTOR` o, por defecto, `protector/` en la carpeta de datos), con las mismas opciones que usó el comando `protector` la última vez; no hace falta esperar a otra partida.

Lo que se muestra en cada fila es: nombre puesto a la fila > alias de sus iniciales (de la página web o de `jugadores.json`) > iniciales del juego. El ranking agrupa por ese nombre final, sin distinguir mayúsculas ni espacios.

Con `--mostrar-sin-iniciales` (o `ARCADE_HOF_MOSTRAR_SIN_INICIALES=1`), la pantalla y las imágenes muestran también los récords sin nombre, con el jugador como `???`. Está desactivada por defecto.

El primer escaneo de todo es la línea base y no anuncia récords batidos. Un juego que aparece después (un `.hi` nuevo, como la primera partida a un juego) sí cuenta su primer récord en "últimos récords", salvo que solo tenga entradas de fábrica; si no tiene nombre, se muestra solo con la opción anterior.

"Últimos récords" también incluye los récords vigentes de la línea base que tienen titular (iniciales del juego o un nombre puesto con `nombrar`), con la fecha en que se detectó esa puntuación por primera vez y el nombre puesto, si lo hay, en lugar de las iniciales originales. Los juegos que solo tienen fábrica y los récords sin nombre no aparecen. Un récord de jugador que supera al récord de jugador anterior cuenta aunque no supere a la fábrica; si el récord de un jugador desaparece (aunque la fábrica siga arriba), la tabla queda pendiente como cualquier máximo que baja. Cuando uno de esos récords se bate, queda el récord batido en su lugar. En `records` figuran como "línea base".

### Rotación de pantallas

La ventana y las imágenes del protector siguen el mismo orden en cada vuelta:

1. **TOP GLOBAL** (el ranking, en varias páginas si hace falta) y **ÚLTIMOS RÉCORDS**.
2. Los juegos **destacados**, cada uno con su pantalla: hasta 8 (`--destacados`). Primero los que tienen un récord nuevo (batido, o el primero de un juego nuevo) de los últimos 7 días (`--dias-destacado`; 0 para no usarlo), del más reciente al más viejo; después, los de más jugadores distintos en su tabla (con el nombre final: alias o nombre puesto) y, para desempatar, los de récord más reciente.
3. Las pantallas **OTROS RÉCORDS** (mosaico) con el resto de los juegos, por orden alfabético: 6 por pantalla (`--mosaico`) en una grilla de 3 x 2, con el logo de cada juego (o su nombre), el 1º con su nombre final en oro y los puntos en blanco, y un contador "1 / 3". Hay un tope de 3 mosaicos por vuelta (`--mosaicos`): si hay más, cada generación empieza por otros, así que van apareciendo todos (la ventana Tk cambia en cada escaneo; el protector, una vez por día).
4. La del QR de la página web, si está instalada y hay récords sin nombre.

La pantalla de un destacado muestra arriba el marquee (logo) del juego en lugar del título en texto, debajo el año y el fabricante, y al costado de la tabla una captura del juego (o, si no hay, su pantalla de título). Las imágenes se leen en el momento de los medios que bajó ES-DE: `<medios>/fbneo/{marquees,screenshots,titlescreens}/<subcarpeta>/<zip>.png`, donde `<medios>` es la carpeta `MediaDirectory` de `es_settings.xml` o, si está vacía, `~/ES-DE/downloaded_media` (se cambia con `--medios` o `ARCADE_HOF_MEDIOS`; `--sin-imagenes` deja todo en texto). No se copian al repositorio. El lector de PNG es propio, en Python puro (`ui/png.py`): 8 bits por canal, con o sin entrelazado (Adam7), en gris, RGB, paleta, gris con alfa y RGBA; si falta la imagen o el PNG no está soportado (por ejemplo, uno de 2 o 4 bits, o un JPG), se usa la pantalla de título en lugar de la captura, o el texto en lugar del logo. De los medios de la iMac se leen todos los marquees; solo 3 capturas no (berzerk, joust y seawolft, de 2 o 4 bits). El resultado escalado (promedio por área al achicar, bilineal al agrandar, siempre con la proporción original) se guarda en `cache-medios/` junto a la base, así que solo la primera vez cuesta: en la iMac, 1,5 segundos para la primera generación y medio segundo las siguientes.

La pantalla y las imágenes usan fondo negro puro (`#000000`), para que se confundan con los bordes negros de la pantalla. El título, el subtítulo y la tabla van fijos bajo la línea superior (si hay más filas, la tabla crece hacia abajo) y la línea de estado, pegada a la línea inferior: en las imágenes del protector va justo encima de esa línea y en la ventana, justo encima de la línea de ayuda. En el ranking, la columna RECORDS cuenta los primeros puestos y JUEGOS nombra hasta dos y agrega `+N` con los demás (por ejemplo, `GALAGA, PENGO +3`); si los nombres no entran en el ancho, se nombra uno solo, recortado con un punto si hace falta.

### Juegos que no se pueden leer

Si un juego no se puede leer (no hay definición o usa una operación que el intérprete todavía no implementa), no se muestran datos: el escaneo lo anota y `pendientes` lo lista, para escribir su definición cuando haga falta ([cómo agregar un juego nuevo](docs/COBERTURA_FBNEO.md#agregar-un-juego-nuevo)). La comprobación opcional con muestras reales y la medición de cobertura se describen en [VALIDACION.md](docs/VALIDACION.md).

## Créditos

Las definiciones de juegos que usa este proyecto son obra de **GreatStoneEx (GreatStone)** y colaboradores del proyecto **hi2txt**:

- [hi2txt-xml](https://github.com/GreatStoneEx/hi2txt-xml): definiciones XML por juego. Licencia [GNU GPL versión 2](https://github.com/GreatStoneEx/hi2txt-xml/blob/990fca26edb8cd9e37ab0b569d5d59b06e31f0e0/LICENSE).
- [Documentación de hi2txt y referencia del formato XML](https://greatstoneex.github.io/hi2txt-doc/doc/xml.html), a partir de la cual se escribió el intérprete.

Los nombres de los juegos salen de los DAT de **FinalBurn Neo** ([libretro/FBNeo](https://github.com/libretro/FBNeo), revisión `d25b21e733fd4ee07980a65268abb5706fc3549d`, versión 1.0.0.03). Tampoco se redistribuyen: se descargan con `fetch_names` y conservan la licencia de FinalBurn Neo.

El código QR se genera con [QR Code generator library](https://www.nayuki.io/page/qr-code-generator-library) de **Project Nayuki** (licencia MIT), versión 1.8.0, copiada sin cambios en `src/arcade_hall_of_fame/vendor/qrcodegen.py` con su aviso de licencia.

La tipografía pixel de la pantalla es propia del proyecto (glifos de 5 x 7 dibujados en código). La paleta parte de las recomendaciones del skill de diseño ui-ux-pro-max. Los colores siguen una regla única, igual en la ventana y en las imágenes del protector: en las tablas con posiciones, las filas del 1º, 2º y 3º van enteras en oro, plata y bronce (posición, jugador, puntos o récords y juegos); del 4º en adelante, posición y jugador en gris claro, puntos en blanco y juego en celeste; en últimos récords, sin podio, el jugador en gris claro y la fecha en un gris más apagado. La paleta está definida en un solo lugar, `src/arcade_hall_of_fame/ui/screens.py`.

hi2txt-xml, a su vez, reconoce el trabajo de HiToText y de los mantenedores de `hiscore.dat` (Leezer y otros). Este repositorio no contiene ni redistribuye esas definiciones ni el motor de hi2txt: cada usuario las descarga con el comando anterior, y conservan su licencia original. El intérprete de este proyecto es código propio.

## Qué falta

Ver [el estado de las etapas](docs/PLAN.md#estado-de-las-etapas). En resumen: probar en Python 3.11 sobre Catalina y Linux; confirmar con un segundo estado real cuando aparezca (iniciales distintas a las de fábrica); después, el núcleo con SQLite, la clasificación general, el historial de récords y la interfaz. Un caso sintético no acredita compatibilidad real.

## Licencia

El código de este repositorio se publica con licencia [MIT](LICENSE) (Copyright (c) 2026 tinchova), salvo `src/arcade_hall_of_fame/vendor/qrcodegen.py`, de Project Nayuki, también MIT. Las definiciones de hi2txt-xml (GPL v2) y los DAT de FinalBurn Neo no forman parte del repositorio y conservan sus propias licencias.
