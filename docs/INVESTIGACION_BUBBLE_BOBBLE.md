# Evidencia alternativa: Bubble Bobble

Fecha: 2026-11-25. El usuario probó `bublbobl` como alternativa por la dificultad de conseguir una nueva entrada en Galaga. Se inspeccionaron una copia privada de `hiscore.dat`, una copia de `bublbobl.hi` y una fotografía de la tabla. No se ha implementado un adaptador adicional ni se declara validación completa.

## Persistencia observada

La definición local incluye `bublbobl` y 47 bloques que suman **86 bytes**. La muestra tiene exactamente esa longitud. Su lectura no alteró el contenido ni la fecha de modificación. La recepción del archivo se produjo después de indicar al usuario que cerrara el contenido; no se observó directamente el momento de escritura en la iMac.

El binario, la definición de terceros, la fotografía, sus hashes y sus rutas privadas permanecen fuera del repositorio. Las siguientes correspondencias documentan el análisis, sin redistribuir esos archivos.

## Comparación con la pantalla

| Posición | Puntuación | Ronda | Nombre |
| --- | --- | --- | --- |
| 1 | 40.080 | 5 | ABC |
| 2 | 30.000 | 32 | I.F |
| 3 | 30.000 | 28 | MTJ |
| 4 | 30.000 | 24 | NSO |
| 5 | 30.000 | 20 | KIM |

Una comprobación puntual en memoria reprodujo las cinco filas de la foto con la interpretación candidata siguiente. Esta comprobación no es un adaptador de producción ni una suite automatizada del proyecto.

## Distribución candidata

El primer bloque de la definición local comienza en RAM `0xE654`, tiene 35 bytes y corresponde a cinco filas contiguas de siete bytes.

| Campo de cada fila | Offset relativo | Interpretación contrastada en esta muestra |
| --- | --- | --- |
| Puntuación | 0–2 | Tres bytes BCD empaquetado, menor peso primero; multiplicar el entero resultante por diez |
| Ronda | 3 | Entero binario sin signo más uno |
| Nombre | 4–6 | Tres caracteres ASCII; letras y punto observados |

Para bytes de puntuación `b0`, `b1`, `b2`, definir `decimal(b) = 10 × (b >> 4) + (b & 15)`. La fórmula candidata es `10 × (decimal(b0) + 100 × decimal(b1) + 10000 × decimal(b2))`, con ambos nibbles entre cero y nueve.

El primer campo se interpreta como 4.008 unidades de diez puntos, dando **40.080**, mientras que las restantes filas representan 3.000 unidades, dando **30.000**. La ronda almacenada es una unidad menor que la mostrada en las cinco filas. Los nombres coinciden exactamente al interpretar sus bytes como ASCII.

El segundo bloque ocupa offsets `0x23`–`0x25`; no se ha determinado su función. El tercer bloque, en `0x26`–`0x28`, coincide con el campo candidato de puntuación de la primera fila y podría conservar el máximo. Los bloques restantes no están interpretados. No tratarlos como entradas de jugadores ni exigir que sean constantes.

## Límites y siguiente comprobación

La longitud coincidente y las cinco filas correctas respaldan esta interpretación para una instantánea. No demuestran todavía cambios de titular, persistencia entre sesiones, orden al insertar nuevas filas, límites de puntuación, espacios, caracteres no observados o compatibilidad con otras variantes y versiones.

El siguiente contraste útil es otra tabla con puntuación e iniciales diferentes, acompañada del `.hi` obtenido al cerrar contenido. Conservar ambas copias por separado. Para comprobar el lector no es necesario superar 40.080: una entrada por encima de 30.000 que permita registrar iniciales distintas también aportaría evidencia. Una superación del máximo sí será necesaria para validar posteriormente el evento de récord batido de extremo a extremo.

Esta investigación mantiene separado el formato de Bubble Bobble del de Galaga: la coincidencia de extensión `.hi` no implica igual codificación ni distribución. Sigue vigente el objetivo de implementar y validar un único adaptador inicial; Galaga queda pendiente y Bubble Bobble es el candidato alternativo investigado.
