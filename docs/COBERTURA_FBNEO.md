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
