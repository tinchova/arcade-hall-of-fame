# Cobertura sobre la colección de FBNeo de la iMac

Medición del 2026-11-25. Se cruzaron tres fuentes:

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
| **(b) El intérprete puede leerlos hoy** | **244** (56 % de los que guardan récords) |
| **(c) Guardan récords pero no se pueden leer** | **193** |
| FBNeo no guarda récords en `.hi` (sin entrada en `hiscore.dat`) | 149 |

"Se puede leer" significa que la definición carga sin operaciones pendientes y que su tamaño y sus regiones de memoria coinciden con lo que guarda FBNeo. Solo Galaga, Bubble Bobble y Pac-Man están confirmados con un archivo real; para el resto, la confirmación llegará con el primer `.hi` de cada juego.

## Motivos de (c)

| Motivo | Juegos | Qué haría falta |
| --- | --- | --- |
| hi2txt-xml no tiene definición para el juego | 172 | Escribir definiciones nuevas (idealmente, aportarlas a hi2txt-xml) o aceptar que esos juegos no entren al ranking |
| La definición usa operaciones que el intérprete no implementa | 13 | Ampliar el intérprete (ver abajo) |
| La definición describe otro archivo (`nvram`, `saveram`...), no el `.hi` que guarda FBNeo | 4 | Una definición para el `.hi` de FBNeo |
| El tamaño del `.hi` de FBNeo no coincide con la definición | 2 | Revisar si FBNeo guarda más datos que MAME y adaptar la definición |
| Mismo tamaño, pero otras regiones de memoria | 1 | Comparar con una muestra real antes de usarla |
| La definición tiene un error propio | 1 | Corregir la definición |

Operaciones pendientes en esos 13 juegos:

| Operación | Juegos |
| --- | --- |
| Charsets predefinidos `CS_*` (`CS_NUMBER`) | 5 |
| `format@formatter` (formato estilo Java, p. ej. `%.2f`) | 3 |
| `char@src` en hexadecimal sin prefijo `0x` | 2 |
| `base="256"` | 1 |
| Operación `shift` (formatos `>N`) | 1 |
| `line-ignore` sin `:valor` | 1 |

Con las tres primeras se recuperarían hasta 10 juegos. El mayor obstáculo son los 172 juegos sin definición, no el intérprete.

Los 149 juegos sin entrada en `hiscore.dat` incluyen muchos de Neo Geo, que guardan sus récords en otro tipo de archivo, o no los guardan. Habría que investigarlos aparte.

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
