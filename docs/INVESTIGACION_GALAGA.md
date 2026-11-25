# Investigación inicial: FinalBurn Neo y Galaga

Consulta: 2026-11-25. Investigación de código público y primera inspección de una copia real de `galaga.hi` aportada por el usuario.

> Actualización: Galaga es la prueba de concepto del intérprete de definiciones hi2txt, que reproduce las cinco filas de la foto. Las dudas de este documento sobre codificación de puntuaciones y caracteres quedan resueltas por la definición publicada (`galaga.xml` de hi2txt-xml). La tabla observada es la tabla de fábrica del juego. Resultados en [VALIDACION.md](VALIDACION.md#resultados-con-las-muestras-reales).

La primera muestra tiene **51 bytes**, coincidentes con la longitud esperada para la definición consultada. La lectura mantuvo iguales el hash y la fecha de modificación del archivo. El usuario aportó después una fotografía de la tabla visible, que permite una primera comparación. Faltan capturas con cambios controlados para confirmar el formato. El binario, la fotografía, su hash y sus rutas privadas no se incorporan al repositorio.

## Fuentes primarias

Se consultó `libretro/FBNeo` en la revisión `d25b21e733fd4ee07980a65268abb5706fc3549d`. El usuario informa RetroArch **1.22.2 nightly** y core FinalBurn Neo **1.0.0.03**. La revisión concreta del core instalado y la fecha de la nightly aún se desconocen; no se ha establecido que correspondan al código consultado.

- [S1: documentación oficial de Libretro, Hiscores](https://docs.libretro.com/library/fbneo/#hiscores).
- [S2: persistencia, HiscoreInit y HiscoreExit](https://github.com/libretro/FBNeo/blob/d25b21e733fd4ee07980a65268abb5706fc3549d/src/burn/hiscore.cpp).
- [S3: rutas de la integración libretro, retro_load_game_common](https://github.com/libretro/FBNeo/blob/d25b21e733fd4ee07980a65268abb5706fc3549d/src/burner/libretro/libretro.cpp).
- [S4: definición de Galaga en hiscore.dat](https://github.com/libretro/FBNeo/blob/d25b21e733fd4ee07980a65268abb5706fc3549d/metadata/hiscore.dat).
- [S5: driver de Galaga](https://github.com/libretro/FBNeo/blob/d25b21e733fd4ee07980a65268abb5706fc3549d/src/burn/drv/pre90s/d_galaga.cpp).
- [S6: cierre del driver, BurnDrvExit](https://github.com/libretro/FBNeo/blob/d25b21e733fd4ee07980a65268abb5706fc3549d/src/burn/burn.cpp).
- [S7: distribución oficial de Python 3.11.9](https://www.python.org/downloads/release/python-3119/).

## Hechos observados

`hiscore.dat` describe rangos de memoria, no resultados ni nombres. El código concatena sus bytes en `<set>.hi`, sin cabecera ni esquema de jugadores. `HiscoreExit` escribe sujeto a comprobaciones; `BurnDrvExit` lo invoca al cerrar el driver. Una partida abierta no garantiza un archivo actualizado. [S2, S6]

En libretro, la definición se busca en `<system_directory>/fbneo/hiscore.dat`; los `.hi`, en `<save_directory>/fbneo/`. RetroArch proporciona esos directorios y puede ordenarlos por contenido o core. Se debe verificar la ruta efectiva; no fijar una ruta de macOS por suposición. [S3]

La documentación requiere activar Hiscores y disponer de `hiscore.dat`. Advierte que el soporte puede faltar o fallar para un set. [S1]

El driver identifica `galaga` como Galaga (Namco rev. B) y lo marca con soporte de hiscores. Otros nombres representan variantes; no se habilitan por compartir familia. [S5]

Para `galaga`, la definición consultada indica estos bloques, en este orden: [S4]

| Bloque | Dirección RAM | Longitud | Offset derivado dentro del .hi |
| --- | --- | --- | --- |
| 1 | `0x8A20` | `0x2D` = 45 bytes | `0x00` a `0x2C` |
| 2 | `0x83ED` | `0x06` = 6 bytes | `0x2D` a `0x32` |

**Inferencia:** para esa definición y ese escritor se esperan 51 bytes. Los offsets son del archivo concatenado, no direcciones RAM. Si la muestra difiere, investigar versión y definición antes de interpretar.

## Primera comparación entre archivo y pantalla

La fotografía muestra cinco puntuaciones de **20.000**, en orden con los nombres `N.N`, `A.A`, `M.M`, `C.C` y `O.O`. El máximo superior también es 20.000. Se trata de la línea base observada; no se atribuyen estas entradas a jugadores reales.

La distribución candidata dentro del archivo es:

| Offsets, inclusivos | Interpretación provisional | Evidencia y límite |
| --- | --- | --- |
| `0x00`–`0x1D` | Cinco puntuaciones de seis bytes cada una | Los cinco campos candidatos son idénticos, como los valores en pantalla; su orden entre filas aún no se puede distinguir |
| `0x1E`–`0x2C` | Cinco nombres de tres códigos cada uno | Los patrones repetidos coinciden con las letras y el punto de los cinco nombres, en ese orden |
| `0x2D`–`0x32` | Posible copia del máximo mostrado arriba | Coincide con el primer campo candidato de puntuación; la función requiere otro estado |

La correspondencia candidata de caracteres observados es `0x0A` → `A`, `0x0C` → `C`, `0x16` → `M`, `0x17` → `N`, `0x18` → `O` y `0x2A` → punto. Es consistente con letras consecutivas a partir de `0x0A`, pero no demuestra el resto del alfabeto ni otros símbolos.

Los campos de puntuación son compatibles con dígitos de menor a mayor peso y `0x24` como blanco inicial: bajo esa hipótesis representan 20.000. Una única puntuación repetida no demuestra la codificación, la posición de todos los dígitos ni el significado general del blanco. No implementar aún esa hipótesis como formato validado.

## Lo que todavía no está demostrado

- La distribución candidata de cinco puntuaciones y cinco nombres frente a estados con filas diferentes.
- Si las puntuaciones usan dígitos por byte, BCD, otro orden o alguna codificación distinta.
- La tabla de caracteres de las iniciales, los espacios y otros símbolos. No asumir ASCII.
- Qué función cumple cada bloque y si contiene copias de datos o información de presentación.
- Cómo se representan empates, entradas iniciales, límites de puntuación y reinicios.
- Cuándo cambia efectivamente el archivo en las versiones instaladas.

Los valores de espera de los extremos en `hiscore.dat` son comprobaciones de inicialización de memoria; no deben convertirse sin evidencia en una firma obligatoria para toda captura guardada. [S2]

La primera comparación respalda una distribución y un mapa parcial de caracteres; todavía no valida un decodificador general de Galaga. La especificación requiere las capturas adicionales descritas en [VALIDACION.md](VALIDACION.md).

## Compatibilidad del entorno

Python publica un instalador universal2 de 3.11.9 para macOS 10.9 o posterior. Esto respalda investigar la rama 3.11 en Catalina; no certifica nuestra aplicación ni convierte esa versión antigua en recomendación de mantenimiento. Elegir una distribución mantenida compatible y verificar `sqlite3`, `tkinter`, pantalla completa y salida en el equipo real. [S7]

## Pendientes para cerrar la investigación

Completar fecha/revisión de las compilaciones comunicadas, set, DIP switches, opciones de persistencia, rutas efectivas y hash del `hiscore.dat` local. Después completar un mapa de campos con offsets, codificación, ejemplos observados, reglas de error y evidencia de varias capturas independientes. No redistribuir archivos de terceros para completar esta documentación.
