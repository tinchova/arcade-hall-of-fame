# Requisitos

Estado: propuesta inicial, 2026-11-25. Las decisiones indicadas como provisionales se resolverán mediante evidencia de la prueba de concepto.

## Alcance

Crear un salón de la fama local para una máquina arcade. La clasificación general cuenta primeros puestos actuales por juego; las puntuaciones de juegos distintos no se suman. Se conserva un historial de cambios observados.

La primera entrega funcional usará FinalBurn Neo como fuente, con Galaga como prueba de concepto. Los juegos se leen con un intérprete genérico de las definiciones de hi2txt-xml, no con un adaptador por juego; cada juego se considera validado solo cuando una muestra real coincide con su pantalla. El diseño permitirá incorporar MAME después de investigar y validar sus propios archivos.

## Requisitos funcionales verificables

| ID | Requisito | Criterio de aceptación |
| --- | --- | --- |
| RF-01 | Configurar explícitamente archivo, emulador, set y perfil de competición | No se adivinan rutas ni formatos por extensión; una fuente no soportada produce un diagnóstico |
| RF-02 | Leer originales exclusivamente en modo binario de lectura | No se crean, modifican, renombran, bloquean ni eliminan archivos del emulador; pruebas comprueban bytes, hash y mtime |
| RF-03 | Interpretar cada juego con su definición de hi2txt-xml (Galaga como prueba de concepto) | Todas las filas disponibles coinciden con las capturas reales de referencia, incluidas puntuaciones e iniciales; una definición no soportada produce un diagnóstico |
| RF-04 | Generar clasificación por juego | Muestra posiciones, iniciales, puntuaciones y estado de actualización; datos desconocidos se señalan |
| RF-05 | Generar clasificación general | Cuenta juegos con primer puesto vigente y propietario identificado; una persona cuenta como máximo una vez por juego |
| RF-06 | Conservar historial en SQLite | Una importación válida guarda observación, tabla y cambios de récord de forma atómica |
| RF-07 | Mostrar últimos récords batidos | Solo superaciones estrictas del máximo vigente; incluye anterior, nuevo, jugador y fecha de detección |
| RF-08 | Actualizar sin duplicados | Releer el mismo estado consecutivo o reiniciar el proceso no duplica observaciones ni eventos |
| RF-09 | Resistir errores de origen | Un archivo ausente, incompleto, inestable o incompatible no sustituye la última tabla válida |
| RF-10 | Interfaz arcade a pantalla completa | Vistas general, por juego y últimos récords; navegación por teclado y salida accesible, sin ratón obligatorio |
| RF-11 | Funcionar sin frontend específico | Importación manual, consulta y visualización funcionan con RetroArch y frontends cerrados |
| RF-12 | Configurar sin editar código | Rutas, intervalo, fuente, perfil y correspondencias de jugadores se guardan en configuración local excluida de Git |

## Reglas de clasificación propuestas

1. Un juego representa una competición configurada con set y condiciones conocidas. La prueba usa una sola. No mezclar dificultad, vidas, hacks, emuladores ni variantes de manera automática. En futuras versiones, cada competición tendrá su clasificación; la general seleccionará una competición por juego para evitar contar clones varias veces.
2. El primer puesto lo determina la puntuación máxima decodificada de la tabla validada. Si varios jugadores empatan en ese máximo, cada uno recibe un juego a su nombre. Se conserva también el orden original de la tabla; varios registros de una persona no multiplican su crédito.
3. La general ordena por cantidad de juegos en primer puesto, de mayor a menor. La igualdad comparte posición; el orden alfabético solo estabiliza la presentación. Ejemplo de prueba de dominio: dos primeros puestos frente a uno, aun cuando el segundo jugador tenga una puntuación numérica mayor.
4. Las iniciales son un identificador local, no una identidad verificada. Se conservan los símbolos decodificados. Un archivo de configuración opcional (`jugadores.json`) puede agrupar varias iniciales de una misma persona, por ejemplo `ANA` y `A.N`; sin él, cada combinación de iniciales es un jugador. Una colisión de iniciales entre personas distintas no se puede resolver desde el binario.
5. Las iniciales se cuentan tal cual aparecen en la tabla, también las presentes en el primer escaneo, sin pedir una atribución explícita. No otorgan crédito las iniciales vacías o ilegibles, las entradas de fábrica (reconocidas con las tablas `db_defaults` de hi2txt-xml) ni los juegos que no guardan iniciales (por ejemplo, Pac-Man). Esos juegos se escanean y se guardan en la base con su máximo, pero la pantalla no los muestra por defecto; se pueden mostrar con la opción `--mostrar-sin-iniciales` (o `ARCADE_HOF_MOSTRAR_SIN_INICIALES=1`).
6. La primera importación establece la línea base, sin anunciar un récord recién batido. Una subida del máximo genera un evento aunque el propietario sea el mismo. Un empate o una modificación de iniciales sin subida conserva la nueva observación, sin evento de superación.
7. La fecha guardada es la de detección en UTC, presentada en hora local. No equivale a la hora de la partida. Si hubo varias partidas entre lecturas, solo se conocen los estados persistidos que llegaron a observarse.
8. Una bajada del máximo o una tabla vaciada se marca como posible reinicio/restauración y queda pendiente; no borra historia ni sustituye automáticamente la tabla vigente. Aceptar ese estado abre una nueva línea base explícita dentro de los datos de la aplicación. Una restauración que eleve el máximo no puede distinguirse siempre de una partida: documentar esta limitación.
9. Una fuente desaparecida conserva su última tabla con aviso de antigüedad. No transfiere ni elimina títulos por una ausencia temporal.

## Restricciones técnicas

- Python y SQLite mediante `sqlite3`; núcleo con biblioteca estándar, sin ORM ni servidor de base de datos.
- Intérprete puro que recibe bytes y una definición y devuelve resultados o un error explícito. La longitud correcta por sí sola no acredita validez. Las definiciones de terceros no se incluyen en el repositorio.
- Procesamiento local, sin cuenta ni red obligatoria. Sin Docker, servicios distribuidos, telemetría ni descarga de ROMs.
- macOS Catalina Intel y Linux como plataformas objetivo; compatibilidad anunciada únicamente después de pruebas en ambas.
- Python 3.11 como base provisional. La versión exacta y su distribución deben verificarse en la iMac antes de fijar instalación y CI.
- Interfaz propuesta con Tkinter, sujeta a prueba temprana de Tcl/Tk en Catalina y Linux. SQLite y la importación deben funcionar sin interfaz gráfica instalada.
- Sondeo de rutas configuradas, inicialmente cada cinco segundos; sin recorridos globales ni vigilancia de todo el disco. Redibujar solo cuando cambien datos o vista; sin animación continua obligatoria.
- Objetivos provisionales a medir en la iMac: CPU media en reposo inferior al 2 % de un núcleo y memoria residente inferior a 150 MiB con interfaz. Detectar un archivo estable en un máximo de dos intervalos, salvo reintentos. Informar también del coste con el emulador activo.
- Escrituras únicamente en el directorio propio de datos y configuración. Rechazar configuraciones que sitúen base de datos, logs o temporales dentro del árbol de guardados del emulador.

## Fuera de la primera prueba

Otros juegos, soporte funcional de MAME, lectura de RAM del proceso, OCR, servicios online, autenticación, antitrampas, panel web, descubrimiento automático de bibliotecas, empaquetado de emuladores y control del lanzamiento de partidas.

Las integraciones con Attract-Mode y ES-DE serán opcionales y posteriores. Podrán invocar el comando público de la aplicación; no serán necesarias para importar ni clasificar.
