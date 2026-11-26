# Cobertura sobre la colección de FBNeo de la iMac

Medición del 2026-11-25, repetida el 2026-11-26 después de ampliar el intérprete. Se cruzaron tres fuentes:

- la lista de ROMs de la iMac: 586 juegos, todos de FinalBurn Neo (fbneo, neogeo, cps1/2/3 y toaplan_cave_stg);
- el `hiscore.dat` que usa FBNeo en la iMac, que define qué juegos guardan récords en un `.hi`;
- las definiciones de hi2txt-xml, revisión `990fca26edb8cd9e37ab0b569d5d59b06e31f0e0`, con el intérprete del proyecto.

La lista de ROMs, el `hiscore.dat` y los `.hi` quedan fuera del repositorio. Este documento solo recoge cantidades y motivos.

Para repetir la medición con otra colección:

```sh
PYTHONPATH=src python -m arcade_hall_of_fame.hi2txt.conformance local/hi2txt-xml/<revisión> \
    --hiscore-dat <hiscore.dat de FBNeo> --juegos <lista de .zip, uno por línea> [--detalle]
```

## Resultado

| Situación | Juegos |
| --- | --- |
| Total de la colección | 586 |
| **(a) FBNeo guarda récords** (tienen entrada en `hiscore.dat`) | **437** |
| **(b) El intérprete puede leerlos hoy** | **256** (59 % de los que guardan récords; 244 el 2026-11-25) |
| **(c) Guardan récords pero no se pueden leer** | **181** |
| FBNeo no guarda récords en `.hi` (sin entrada en `hiscore.dat`) | 149 |

"Se puede leer" significa que la definición carga sin operaciones pendientes y que su tamaño y sus regiones de memoria coinciden con lo que guarda FBNeo. Galaga, Bubble Bobble, Pac-Man y Out Run están confirmados con un archivo real; para el resto, la confirmación llegará con el primer `.hi` de cada juego.

## Motivos de (c)

| Motivo | Juegos | Qué haría falta |
| --- | --- | --- |
| hi2txt-xml no tiene definición para el juego | 172 | Escribir definiciones nuevas (idealmente, aportarlas a hi2txt-xml) o aceptar que esos juegos no entren al ranking |
| La definición describe otro archivo (`nvram`, `saveram`, `eeprom`...), no el `.hi` que guarda FBNeo | 5 | Una definición para el `.hi` de FBNeo |
| El tamaño del `.hi` de FBNeo no coincide con la definición | 2 | Revisar si FBNeo guarda más datos que MAME y adaptar la definición |
| Mismo tamaño, pero otras regiones de memoria | 1 | Comparar con una muestra real antes de usarla |
| La definición tiene un error propio | 1 | Corregir la definición |

Ya no queda ningún juego de la colección frenado por operaciones del intérprete. El 2026-11-25 eran 13; el 2026-11-26 se implementaron las seis operaciones que usaban, siguiendo la documentación oficial del formato y comprobándolas con los casos de prueba de hi2txt-xml:

| Operación | Juegos | Ejemplo |
| --- | --- | --- |
| Charset predefinido `CS_NUMBER[desplazamiento,delta]` | 5 (aerofgt, armwar, dimahoo, exedexes, gnbarich) | cifras 0 a 9 desde el código ASCII 0x30, más el desplazamiento; el delta separa cifras consecutivas |
| `format@formatter` (formato estilo Java, de un solo valor) | 3 (goldnaxe, mrdo, outrun) | `%02d`, `%.1f` (redondea la mitad hacia arriba, como Java) |
| `char@src` hexadecimal sin `0x` | 2 (futaribl, solrwarr) | `src="2D"` |
| `base="256"`: un byte por cifra decimal | 1 (galaga88) | `00 02 07 00 06 03` → 27063 |
| Formato implícito `>N`: desplazamiento de N bits a la derecha | 1 (tgm2p) | `>2;%4` |
| `line-ignore` sin `:valor`: omite las filas con esa columna vacía | 1 (tmnt2pj) | `line-ignore="NAME"` |

De esos 13, 12 se leen ahora. tgm2p no: con las operaciones resueltas se ve que su definición describe la `eeprom`, no el `.hi`, y pasa a la fila "otro archivo". En toda la biblioteca de hi2txt-xml quedan 14 juegos (3 definiciones base) con operaciones pendientes, ninguno en esta colección: columnas dentro de `divide` y un `case` con `operator="="`.

El mayor obstáculo son los 172 juegos sin definición, no el intérprete.

Los 149 juegos sin entrada en `hiscore.dat` incluyen muchos de Neo Geo, que guardan sus récords en otro tipo de archivo, o no los guardan. Habría que investigarlos aparte.

## Out Run (muestra real, 2026-11-26)

`outrun.hi` (280 bytes) se copió de la iMac sin modificarla. Guarda 20 puestos con puntuación, iniciales, tiempo y ruta; la definición oculta los puestos sin iniciales. El archivo tiene **solo la tabla de fábrica**: siete puestos con iniciales (5.000.000 YU., 4.800.000 BIN, 4.600.000 KAG, 4.400.000 MIY, 4.200.000 MAT, 4.000.000 IKA, 3.800.000 A.O, todos con tiempo 0'00''00) y trece sin iniciales, de 3.600.000 a 1.000.000. No hay ninguna entrada de una partida: la de Nico no llegó a la tabla (seguramente con menos de 1.000.000, el puesto 20) o FBNeo guardó la tabla sin cambios. El caso de prueba de hi2txt-xml para Out Run, que sí incluye partidas con tiempo, coincide exactamente.

## Pac-Man (nueva muestra real)

`pacman.hi` (11 bytes) usa la definición de `puckman` (alias `sameas`), con las mismas regiones de memoria que el `hiscore.dat` de FBNeo. Resultado: **un único récord, 1400 puntos, sin iniciales**. El juego solo guarda la puntuación máxima. Para el ranking habrá que decidir cómo tratar juegos sin iniciales: no pueden atribuirse a una persona desde el archivo.

## Python en la iMac

La iMac tiene **Python 3.8.2**, el de las herramientas de línea de comandos de Apple. Las pruebas se ejecutaron desde una copia temporal en `/tmp`, borrada al terminar, sin instalar nada:

- las 52 pruebas pasan (2 opcionales salteadas);
- las pruebas con muestras reales, leyendo los `galaga.hi` y `bublbobl.hi` originales en modo lectura, pasan y confirman que hash y fecha de modificación no cambian;
- `pacman.hi` da la misma tabla que en Windows.

Para esto hubo que cambiar un alias de tipo, que usaba una sintaxis exclusiva de Python 3.9 o posterior. El objetivo sigue siendo Python 3.11: 3.8 ya no recibe actualizaciones de seguridad, y `pyproject.toml` declara 3.11. Que funcione con el Python del sistema sirve para diagnosticar sin instalar nada.

## Récords que todavía no se pueden leer

Cuando el escaneo encuentra el `.hi` de un juego que no se puede leer (sin definición, con operaciones no soportadas, de otro tamaño o con otras regiones de memoria, o sin entrada en `hiscore.dat`), ya no lo ignora: lo anota en la base con el motivo, la fecha en que apareció y la última modificación del archivo. No se inventa nada: solo se sabe que alguien jugó y que FBNeo guardó una tabla.

```sh
python -m arcade_hall_of_fame pendientes             # lista; destaca NUEVO y CAMBIÓ desde la consulta anterior
python -m arcade_hall_of_fame pendientes --sin-marcar # igual, sin darlos por vistos
```

`NUEVO` es un juego que apareció desde la última consulta; `CAMBIÓ`, uno cuyo archivo se modificó desde entonces (probablemente otra partida). El comando `protector` deja la misma lista en `hof-pendientes.txt`, junto a los PNG, para verla sin abrir la base; solo lo reescribe si cambió. Cuando un juego pasa a leerse (por ejemplo, porque se agregó su definición), sale de la lista en el siguiente escaneo.

## Agregar un juego nuevo

Hace falta, del juego en cuestión:

1. **Una partida con iniciales y la foto de la tabla.** Jugar hasta entrar en la tabla, poner iniciales reconocibles (por ejemplo `ABC`) y sacar una foto de la pantalla de récords completa, con todas las posiciones. La foto es la verdad contra la que se comprueba la definición: posiciones, puntuaciones e iniciales. Mejor dos partidas con resultados distintos, para distinguir qué bytes cambian.
2. **El `.hi` que guardó FBNeo**, copiado (nunca movido ni editado) de la carpeta de partidas, por ejemplo `saves/FinalBurn Neo/fbneo/<juego>.hi`, después de salir del juego, que es cuando FBNeo lo escribe.
3. **La entrada del juego en el `hiscore.dat` de FBNeo**, que dice qué regiones de memoria se guardaron y en qué orden: cada línea `@:maincpu,program,<dirección>,<largo>,<inicio>,<fin>` es un bloque del `.hi`, uno detrás del otro. La suma de los largos es el tamaño del archivo.

Con eso se escribe la definición en el formato de hi2txt ([referencia del XML](https://greatstoneex.github.io/hi2txt-doc/doc/xml.html)): una `<structure file=".hi">` con el tamaño (`<check><size>`) y las regiones (`<check><definition>`), los elementos en orden (`<elt>` o `<loop>` para puntuaciones, iniciales y separadores) y una `<output>` con la tabla. Conviene partir de la definición de un juego del mismo fabricante y la misma época, que suele usar la misma codificación de puntuaciones (BCD o binario) y el mismo juego de caracteres, y confirmarlo byte a byte contra la foto. Se prueba con:

```sh
PYTHONPATH=src python -m arcade_hall_of_fame.hi2txt <juego> ruta/a/una/copia/<juego>.hi
```

y se agrega una prueba con el `.hi` como muestra real local (ver [VALIDACION.md](VALIDACION.md)). Las definiciones de hi2txt-xml no se versionan en este repositorio; la definición nueva queda local, junto a las descargadas, y conviene **proponerla también a [hi2txt-xml](https://github.com/GreatStoneEx/hi2txt-xml)** (un pull request con el XML nuevo, en `src/main/db/`, o un issue con el XML adjunto), que acepta contribuciones de definiciones y es GPL v2. Así le sirve a todos y vuelve en la próxima revisión fijada.

### Primer candidato: Sunset Riders

`ssriders` y sus versiones (`ssridersubc` incluida) tienen entrada en el `hiscore.dat` de FBNeo, así que FBNeo guarda su `.hi`, pero hi2txt-xml no tiene definición para ninguna. La entrada de FBNeo guarda dos bloques: `104400` (0x50 bytes) y `104120` (4 bytes), es decir un `.hi` de 84 bytes. Probablemente el primero sea la tabla y el segundo el máximo que se muestra en pantalla, pero eso hay que confirmarlo con la partida, la foto y el `.hi`. Un punto de partida razonable es la definición de `tmnt2` (Konami, 1991, hardware parecido), con puntuaciones en BCD y su propio juego de caracteres; no hay que suponer que coincide. Una vez escrita, la misma definición, con `<sameas>`, sirve para los demás sets de `ssriders` del mismo bloque de `hiscore.dat`.
