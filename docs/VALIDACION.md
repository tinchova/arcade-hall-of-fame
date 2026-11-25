# Validación de Galaga

Estado (2026-11-25): el intérprete de definiciones hi2txt reproduce las tablas de las dos muestras reales disponibles, contrastadas con sus fotos. Es una prueba de concepto: falta un segundo estado real con iniciales que no sean las de fábrica y la ejecución en Catalina y Linux.

## Resultados con las muestras reales

| Juego | Archivo | Filas obtenidas (puntuación, iniciales) | Coincide con la foto |
| --- | --- | --- | --- |
| Galaga (`galaga`) | 51 bytes | 20000 N.N · 20000 A.A · 20000 M.M · 20000 C.C · 20000 O.O; máximo 20000 | Sí |
| Bubble Bobble (`bublbobl`) | 86 bytes | 40080 ABC · 30000 I.F · 30000 MTJ · 30000 NSO · 30000 KIM; etapas 5, 32, 28, 24, 20 | Sí |

La lectura no cambió el contenido ni la fecha de modificación de ninguna de las dos copias. Las regiones del `hiscore.dat` de FBNeo para `galaga` coinciden con las que declara la definición.

**Hallazgo:** la tabla de Galaga de la foto es idéntica a la tabla de fábrica que publica hi2txt-xml (`src/main/db_defaults/galaga.xml`). Son entradas precargadas por el juego, no partidas de personas, y según la regla 5 de [REQUISITOS.md](REQUISITOS.md) no deben otorgar crédito. Por eso la muestra confirma la decodificación de puntuaciones e iniciales, pero no la de una tabla modificada por jugadores.

## Escaneo con las partidas reales de la iMac

Prueba del 2026-11-25, con copia temporal en `/tmp` (base incluida), borrada al terminar, y la carpeta de partidas leída en modo lectura; el listado de la carpeta fue idéntico antes y después. Python 3.8.2, SQLite 3.28.0. Pasaron todas las pruebas. El primer escaneo registró 3 tablas (galaga, bublbobl, pacman); el segundo, ninguna nueva. Ranking: `ABC` con 1 primer puesto (bublbobl). Galaga no cuenta porque su máximo es de fábrica, y Pac-Man porque no guarda iniciales. Todavía no hay récords batidos: el primer escaneo es la línea base.

## Comprobación local opcional

`tests/test_muestras_reales.py` lee copias privadas indicadas por variables de entorno y se saltea si faltan; saltearla no acredita compatibilidad. Ejemplo (bash):

```sh
export ARCADE_HOF_HI2TXT_DB=local/hi2txt-xml/<revisión>/src/main/db
export ARCADE_HOF_GALAGA_SAMPLE=/ruta/privada/galaga.hi
export ARCADE_HOF_GALAGA_EXPECTED="20000 N.N;20000 A.A;20000 M.M;20000 C.C;20000 O.O"
export ARCADE_HOF_BUBLBOBL_SAMPLE=/ruta/privada/bublbobl.hi
export ARCADE_HOF_BUBLBOBL_EXPECTED="40080 ABC;30000 I.F;30000 MTJ;30000 NSO;30000 KIM"
python -m unittest tests.test_muestras_reales -v
```

La prueba también comprueba que el hash y la fecha de modificación de la muestra no cambian.

## Cobertura del intérprete

Medida con `python -m arcade_hall_of_fame.hi2txt.conformance local/hi2txt-xml/<revisión> --hiscore-dat <hiscore.dat de FBNeo>`, sobre hi2txt-xml `990fca26edb8cd9e37ab0b569d5d59b06e31f0e0`. Para comparar con salidas esperadas, descargar con `fetch --pruebas`.

| Medida | Resultado |
| --- | --- |
| Juegos con definición en hi2txt-xml | 3102 (780 definiciones base; el resto son alias `sameas`) |
| Cargan sin operaciones pendientes | 2939 juegos (94,7 %), 743 definiciones base |
| Con operaciones pendientes | 146 juegos (34 base): `CS_*` 11, `base=256` 9, `formatter` 8, `shift`, columnas en `divide` y casos sueltos |
| Con errores propios de la definición | 17 juegos (3 base: sin `<structure>` o bucle sin `count`) |
| Casos de prueba de hi2txt-xml (`src/test`, 803) | 606 salidas idénticas y 15 con la tabla principal idéntica; 8 difieren, 11 dan error, 42 sin soporte, 117 son `nvram` de varios archivos (no aplica a FBNeo) y 4 salidas esperadas ilegibles |
| `hiscore.dat` de FBNeo instalado (5856 juegos) | 2588 tienen definición; 2467 están soportadas; 2450 son además compatibles en tamaño y regiones de memoria con lo que guarda FBNeo (13 difieren en tamaño o archivo, 4 en regiones) |
| Colección de la iMac (586 juegos) | 437 guardan récords en FBNeo y 244 se pueden leer hoy; detalle en [COBERTURA_FBNEO.md](COBERTURA_FBNEO.md) |

De los 644 casos de prueba aplicables y soportados, 621 (96 %) dan la tabla principal idéntica a la del motor original. Varias diferencias restantes vienen de salidas esperadas generadas con versiones antiguas del motor o de las definiciones (por ejemplo, hexadecimal en minúsculas). Que una definición cargue no garantiza que el juego funcione en FBNeo: hace falta que las regiones de su `hiscore.dat` coincidan y, en lo posible, una muestra real.

Las definiciones de hi2txt-xml se probaron con MAME. Para cada juego de FBNeo, el intérprete elige la estructura por tamaño de archivo y, si se le pasan, por las regiones de `hiscore.dat`. Si no coinciden, informa un error en vez de leer.

## Notas previas

La primera inspección de `galaga.hi` (51 bytes) y la correspondencia provisional están en [la investigación](INVESTIGACION_GALAGA.md#primera-comparación-entre-archivo-y-pantalla). Las secciones siguientes describen el protocolo original; siguen siendo útiles para obtener nuevas muestras.

## Entorno comunicado

- iMac Late 2013 Intel con macOS Catalina.
- RetroArch **1.22.2 nightly**, según el usuario; fecha de compilación pendiente.
- Core FinalBurn Neo **1.0.0.03**, según el usuario; revisión concreta pendiente.
- Archivo `galaga.hi`: localizado por el usuario e inspeccionado desde una copia privada. Nombre del set candidato: `galaga`, pendiente de confirmar con el contenido cargado.
- Tabla visible: fotografía recibida y comparada con la primera muestra; siguiente evidencia necesaria: una entrada de puntuación e iniciales distintas y su `.hi` guardado tras cerrar contenido.
- `hiscore.dat` instalado: pendiente de inspección.

## Localizar los archivos en la iMac

1. En la entrada de Galaga de la lista de RetroArch, consultar **Información / Information** y anotar el nombre y la ruta del archivo de contenido. Interesa el nombre del ZIP sin extensión: por ejemplo, `galaga.zip` indica el candidato `galaga`; `galagamw.zip` indica otro set. No renombrar el archivo. Si no aparece la ruta, localizar el archivo desde el que se carga el juego.
2. Con Galaga abierto, ir a **Ajustes → Directorio / Settings → Directory** y anotar las rutas de **Sistema/BIOS / System/BIOS** y **Archivos de guardado / Save Files**. Los nombres pueden variar con el idioma y el menú. Consultar, sin cambiarlas, las opciones de organización de guardados en **Ajustes → Guardado / Settings → Saving**: puede haber subcarpetas por core o contenido. La [guía oficial de directorios](https://docs.libretro.com/guides/change-directories/) explica los directorios configurables y sus valores especiales.
3. En Finder usar **Ir → Ir a la carpeta…** (`Cmd+Shift+G`) para abrir la ruta de Sistema/BIOS anotada. Buscar `fbneo/hiscore.dat`. Es la definición de guardado; no contiene las puntuaciones del jugador. Si la ruta indicada es una opción por defecto en lugar de una carpeta concreta, resolverla antes de buscar, según la guía anterior.
4. Con Galaga abierto, revisar **Menú rápido → Opciones del núcleo / Quick Menu → Core Options → Hiscores**. Anotar su estado. Si está desactivado y se quieren generar puntuaciones persistentes, activarlo; si el menú solicita reiniciar el contenido, hacerlo normalmente. La [documentación oficial de FBNeo](https://docs.libretro.com/library/fbneo/#hiscores) requiere esta opción y `hiscore.dat`. Si falta la definición, registrar primero esa ausencia; no sustituirla por un archivo vacío.
5. Dejar que el juego termine de arrancar y muestre su tabla de puntuaciones. Después usar **Menú rápido → Cerrar contenido / Quick Menu → Close Content** para permitir el guardado normal.
6. Abrir en Finder la carpeta de guardados anotada. Buscar `<set>.hi` dentro de `fbneo` y de las subcarpetas del core o contenido, si existen. Para el set `galaga`, el nombre esperado es `galaga.hi`; no asumir que todos los sets usan ese nombre. Las rutas candidatas se basan en el [código investigado](INVESTIGACION_GALAGA.md), pendiente de contrastar con esta instalación.
7. Anotar nombre, ruta y tamaño del archivo encontrado mediante **Obtener información** de Finder (`Cmd+I`). Los 51 bytes son una expectativa para la definición investigada, no una condición para descartar sin análisis un archivo real diferente. Con el contenido cerrado, copiar el `.hi` a una carpeta privada fuera del repositorio y conservar el original intacto.

El resultado de esta primera localización es: nombre del ZIP, ruta efectiva de guardados, presencia de `hiscore.dat`, estado de Hiscores y nombre/tamaño del `.hi`. Si no aparece, registrar cuál de esos pasos falla antes de ampliar la búsqueda. No hace falta compartir ROMs ni BIOS.

## Preparación privada

1. Registrar iMac/CPU, macOS, versión y arquitectura de Python, versiones de RetroArch y del core FBNeo y nombre exacto del set. No es necesario compartir ROMs ni BIOS.
2. Registrar dificultad, vidas y demás DIP switches, opciones de guardado y uso de savestates, rewind o runahead. Mantener condiciones constantes durante la comparación.
3. Localizar los directorios efectivos de sistema y guardados desde RetroArch; confirmar el archivo de definición y el `.hi` del set. Registrar hash SHA-256 del `hiscore.dat` instalado y su entrada relevante en notas privadas.
4. Usar una carpeta de evidencias fuera del repositorio. Conservar copias de los `.hi` después del cierre normal del contenido y capturas de la tabla visible. No editar ni reiniciar los originales para fabricar casos; no cargar estados que alteren la secuencia de prueba.
5. Asociar a cada copia un identificador, tamaño, SHA-256, condiciones y tabla esperada fila por fila. Usar iniciales de prueba que no revelen datos personales. Las capturas y los hashes reales permanecen privados.

Si no existe `.hi`, comprobar soporte y opción Hiscores, dejar iniciar el juego y cerrar contenido normalmente. No crear un `.hi` vacío ni renombrar otro archivo para satisfacer el protocolo. Si la ruta continúa sin aparecer, registrar diagnóstico y detener la decodificación.

## Secuencia mínima de evidencia

Actualización: esta secuencia describe escenarios de contraste, no una obligación de conseguir nuevas marcas antes de avanzar. Se encontraron [definiciones publicadas en hi2txt](TRABAJO_EXISTENTE.md) para ambos juegos. Compararlas primero con los archivos y fotos disponibles; solicitar otra captura únicamente cuando resuelva una discrepancia concreta. Los eventos del núcleo se pueden verificar con tablas sintéticas sin nuevas partidas.

| Captura | Acción controlada | Qué verifica |
| --- | --- | --- |
| A | Registrar estado existente y cerrar contenido | Línea base y todas las filas visibles |
| B | Volver a abrir sin mejorar puntuaciones y cerrar | Persistencia y ausencia de cambios falsos |
| C | Lograr entrada de tabla con iniciales de prueba conocidas | Relación entre posición, puntuación y caracteres |
| D | Superar el primer puesto con otras iniciales conocidas | Identificación del nuevo propietario y desplazamiento de filas |
| E | Mejorar nuevamente con el mismo propietario | Mejora propia y evento sin cambio de titular |
| F | Reiniciar RetroArch y verificar la tabla | Persistencia entre sesiones y lectura repetida |

Si fuera necesario deducir campos no documentados, obtener estados que permitan distinguir las hipótesis y reservar una captura independiente para contrastarlas. Si una acción no se puede reproducir, registrarla como pendiente; no presentarla como validada. No exigir un número fijo de partidas cuando una definición publicada y una muestra real ya permitan comprobar el campo. No asumir soporte de símbolos sin evidencia o documentación.

## Especificación del formato a completar

| Dato | Evidencia necesaria |
| --- | --- |
| Identidad y tamaño | Set, versión, definición instalada y longitud observada |
| Filas | Número, stride si existe y offsets de cada campo |
| Puntuación | Codificación, orden, ceros, límites conocidos y ejemplos reales |
| Iniciales | Mapa de bytes a caracteres, longitud y tratamiento de espacios |
| Otros bytes | Función conocida o campo reservado; no inventar su semántica |
| Errores | Tamaños no admitidos, códigos desconocidos y orden incoherente |

Por cada campo documentar hipótesis, capturas que la apoyan y resultado esperado. Contrastarlo con la pantalla, no con un encoder construido a partir de la misma hipótesis. Cualquier divergencia deja la compatibilidad pendiente.

## Pruebas automatizadas

Implementadas: lector, intérprete (definiciones sintéticas propias en `tests/synthetic.py`), formatos, `hiscore.dat`, descarga segura y comprobación opcional con muestras reales. La tabla siguiente incluye además lo previsto para las etapas siguientes.

Usar `unittest` y directorios temporales. Los tests públicos no requieren emulador ni material privado.

| Área | Casos relevantes |
| --- | --- |
| Intérprete | Definiciones y bytes sintéticos: BCD, base 16, base 40, índices, punteros de rango, formatos, charsets, entidades, `sameas`; tamaños incorrectos, BCD inválido, caracteres no imprimibles y operaciones no soportadas |
| Lector | Origen de solo lectura, ausencia, permisos, modificaciones entre lecturas, tamaño excesivo y exclusión de salidas dentro del árbol de guardados |
| Integridad de origen | Comparar contenido, hash y mtime antes/después de éxito, error y reimportación; no exigir atime inmutable, pues leer puede actualizarlo |
| SQLite | Reimportar sin duplicar, reiniciar y reimportar, fallo a mitad de transacción sin datos parciales, fuentes separadas y persistencia de atribución |
| Historial | Primera importación sin evento, superación por otra persona, mejora propia, empate sin superación, cambio solo de iniciales y máximo descendente pendiente |
| Restauración | Secuencia A → B → A detectada, estado pendiente repetido sin duplicados y aceptación explícita de nueva línea base |
| General | Dos juegos frente a uno sin sumar puntos, empates, múltiples filas de la misma persona, iniciales desconocidas y exclusión de variantes duplicadas |

Los casos sintéticos serán código o datos creados expresamente por el proyecto, con procedencia documentada. No copiar bloques de ROM ni publicar volcados reales bajo la etiqueta de sintéticos. Evitar pruebas que solo confirmen el propio encoder.

La comprobación local opcional leerá muestras externas y expectativas privadas. Solo se omite si no están disponibles; su omisión no cuenta como aprobación de compatibilidad. Registrar versión del adaptador y resultado en un informe sin datos personales ni rutas del usuario. No subir muestras a CI.

## Prueba manual de plataforma y rendimiento

En Catalina Intel y en una distribución Linux identificada: arrancar desde un entorno limpio, importar, reiniciar, verificar historial, abrir las tres vistas, navegar por teclado y salir de pantalla completa. Probar origen inaccesible y recuperación sin perder resultados.

Medir cinco minutos en reposo y una actualización, con y sin emulador activo: CPU media normalizada a un núcleo, RSS máxima, intervalo configurado y latencia desde archivo estable. Registrar resolución y escala de pantalla. Contrastar los objetivos de REQUISITOS.md; una prueba en Windows o CI Linux no certifica la iMac.

## Condición para declarar válida la prueba de concepto

La especificación debe explicar las filas de todas las capturas, incluida la reservada, y el adaptador debe reproducir sus puntuaciones e iniciales sin discrepancias. Las pruebas públicas y la validación privada deben pasar, con evidencia de que no se modifican originales. Después se valida el flujo completo en la iMac y Linux. Hasta entonces, Galaga figura como experimental y ningún otro adaptador entra en implementación.
