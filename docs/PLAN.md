# Arquitectura y plan de implementación

Estado: lector implementado como prueba de concepto (etapa 2); el resto, diseño propuesto.

Cambio de rumbo (2026-11-25): en lugar de un adaptador escrito a mano por juego, el proyecto usa las [definiciones publicadas por hi2txt-xml](TRABAJO_EXISTENTE.md) mediante un intérprete propio de su formato. El usuario tiene unos 500 juegos de FBNeo; escribir un adaptador por juego no escala. Galaga sigue siendo la prueba de concepto y Bubble Bobble el segundo caso contrastado con fotos.

## Arquitectura mínima

Un paquete Python, SQLite local y una interfaz de escritorio. Registro explícito de adaptadores mediante un diccionario; no hace falta un sistema de plugins. La fuente (emulador, versión, set, perfil) se configura separadamente del intérprete específico del juego.

Flujo: configuración → lectura estable de bytes → intérprete hi2txt con la definición del juego → resultado normalizado → transacción SQLite → consultas de clasificación → CLI o interfaz.

| Módulo previsto | Responsabilidad |
| --- | --- |
| `config.py` | Leer TOML con `tomllib`, validar rutas y seleccionar fuente/perfil |
| `reader.py` | Abrir en `rb` (**implementado**); falta comprobar estabilidad y calcular SHA-256 |
| `hi2txt/definition.py` | **Implementado.** Cargar una definición XML (con `sameas` y entidades del DTD local) y rechazar lo no soportado |
| `hi2txt/decoder.py`, `formats.py`, `output.py` | **Implementado.** Aplicar la definición a los bytes y construir tablas y campos |
| `hi2txt/fetch.py` | **Implementado.** Descargar hi2txt-xml en una revisión fijada, fuera de Git |
| `hi2txt/conformance.py` | **Implementado.** Medir cobertura y comparar con las salidas esperadas de hi2txt-xml |
| `models.py` | **Implementado.** Errores de lectura, definición y formato; faltan dataclasses de fuente |
| `service.py` | Coordinar importación, línea base, clasificación y eventos |
| `storage.py` | SQL explícito, transacciones, consultas y versión del esquema |
| `cli.py` | Importación puntual, seguimiento y consultas para diagnóstico e integración |
| `ui.py` | Tres vistas, navegación, pantalla completa y actualización con Tkinter |

El intérprete no abre archivos ni conoce SQLite o Tkinter: `decode` recibe bytes y una definición. Devuelve las tablas de la definición y, de la tabla principal, filas con posición, puntuación e iniciales decodificadas. La atribución a jugadores queda fuera. Rechaza definiciones con operaciones no implementadas al cargarlas y bytes incompatibles al leerlos, sin sustituir caracteres desconocidos por letras inventadas. Cada observación deberá guardar la revisión de hi2txt-xml y la versión del intérprete.

Las tablas de fábrica que publica hi2txt-xml (`db_defaults`) permitirán reconocer entradas precargadas, que según la regla 5 no otorgan crédito.

Para la prueba inicial habrá una instancia de la aplicación escribiendo SQLite. No introducir procesos auxiliares, colas o servidor. Las operaciones pequeñas se programan sin bloquear la interfaz durante esperas; el núcleo no depende del bucle gráfico.

## Persistencia propuesta

Cuatro tablas bastan inicialmente; concretar DDL y migración inicial durante la implementación:

- `sources`: identidad estable de fuente, juego, set y perfil; referencia a última observación aceptada y estado operativo. Rutas privadas fuera de exportaciones públicas.
- `observations`: fuente, hash, hora UTC de detección, versión de adaptador, estado aceptado o pendiente, referencia a la línea base y motivo del cambio.
- `score_entries`: observación, posición, puntuación, iniciales y clave local de jugador cuando esté atribuida.
- `record_events`: observación causante, referencia al estado previo, máximo anterior y nuevo, propietarios anteriores y nuevos. Un evento por superación, aunque haya varios propietarios empatados.

La configuración local aporta las correspondencias de iniciales. Los eventos conservan la atribución observada; cambiar una correspondencia puede actualizar la presentación actual, pero no reescribe silenciosamente el historial.

La tabla actual se consulta desde la última observación aceptada. La general se calcula desde las tablas actuales, sin contador mutable duplicado. Historial de observaciones y eventos se conserva al reiniciar. Usar claves foráneas y una transacción por importación; versionar esquema con `PRAGMA user_version`. No almacenar binarios originales en SQLite en esta primera versión.

## Lecturas, repetición y recuperación

Comparar tamaño y mtime antes y después de leer, y exigir dos lecturas idénticas separadas por un intervalo configurable. Limitar tamaño de entrada según el perfil validado. Un cambio durante lectura cancela el intento; reintentar en el siguiente ciclo, sin espera ocupada ni bloqueo del emulador. Estas comprobaciones reducen lecturas parciales; no equivalen a una instantánea atómica del escritor externo.

El hash se compara con el último estado de esa fuente, persistido en SQLite. No usar una restricción global de hash único: la secuencia A → B → A debe poder detectarse como restauración. Releer consecutivamente un estado pendiente tampoco duplica avisos. Cambiar solo mtime sin cambiar bytes no crea evento.

Una importación fallida revierte completamente la transacción. Al recuperar la fuente se vuelve a intentar; la interfaz muestra último éxito y error actual. Un cambio de perfil requiere una nueva línea base, no una comparación con reglas distintas.

## Etapas y condiciones de salida

| Etapa | Trabajo | Condición de salida |
| --- | --- | --- |
| 0. Especificación — esta entrega | Requisitos, investigación pública, arquitectura, protocolo y política del repositorio | Documentos revisables; incertidumbres explícitas |
| 1. Evidencia real | Identificar instalación y obtener secuencia privada de Galaga; probar Python, SQLite y ventana Tk mínima | Persistencia reproducible; mapa de campos contrastado; entorno viable |
| 2. Lector — prueba de concepto | Intérprete de definiciones hi2txt, lector `rb`, casos sintéticos y comprobación local contra muestras reales | Galaga y Bubble Bobble coinciden con las fotos; entradas inválidas se rechazan; originales intactos |
| 3. Núcleo y SQLite | CLI de importación, observaciones, reglas de clasificación, eventos y recuperación | Repetición, empates, mejora propia, reinicios y transacciones cubiertos por pruebas |
| 4. Interfaz | General, Galaga y últimos récords, teclado, pantalla completa y estilo arcade con texto y formas propias | Uso completo en iMac, sin ratón y dentro del presupuesto medido |
| 5. Preparación pública | Instalación reproducible, CI Linux/Python 3.11, licencia, guía de contribución y revisión de archivos | Pruebas y revisión del repositorio aprobadas; resultados de Catalina y Linux documentados |
| 6. Ampliaciones | Evaluar MAME e integraciones opcionales de Attract-Mode/ES-DE | Solo tras cerrar la prueba de Galaga; requisitos y muestras propios antes de cada adaptador |

Las etapas 3–6 no convierten un decodificador sin evidencia en uno validado. Los tests de la general podrán usar tablas normalizadas ficticias de varios juegos.

## Estado de las etapas

| Etapa | Estado |
| --- | --- |
| 0. Especificación | Hecha |
| 1. Evidencia real | Parcial: muestras de Galaga y Bubble Bobble con foto. Falta Python/Tk en la iMac y fecha/revisión de las compilaciones |
| 2. Lector | Prueba de concepto hecha en Windows con Python 3.14 y 3.13; falta correr las pruebas en Python 3.11, Catalina y Linux. Cobertura medida en [VALIDACION.md](VALIDACION.md#cobertura-del-intérprete) |
| 3. Núcleo y SQLite | Hecho, sin configuración TOML ni correspondencias de iniciales: `scanner.py`, `storage.py`, `rankings.py` y `cli.py`, con pruebas sintéticas. Probado en la iMac con las partidas reales, en modo lectura y con la base en `/tmp` |
| 4–6 | Sin empezar. Sin interfaz gráfica hasta que se indique |

Decisiones del 2026-11-25: los juegos que no guardan iniciales (como Pac-Man) aparecen en su tabla con el máximo, pero no cuentan para el ranking; las entradas de fábrica no cuentan para nadie; por ahora no se escriben definiciones nuevas para los juegos que no tienen. La regla 5 se simplificó: las iniciales se cuentan tal cual, también en el primer escaneo. Las correspondencias entre iniciales y personas van en un `jugadores.json` opcional (JSON porque `tomllib` no existe en Python 3.8).

Esquema implementado (`PRAGMA user_version = 1`): `sources` (un juego por `.hi`, con hash, última lectura, último error y tabla vigente), `observations` (cada contenido distinto, `aceptada` o `pendiente`), `entries` (filas con puntuación, iniciales y marca de fábrica), `record_events` (máximo anterior y nuevo, con sus titulares) y `scans`. Un archivo sin cambios solo actualiza la hora de última lectura. Un máximo menor que el vigente queda `pendiente` hasta `aceptar`. Cada archivo se lee dos veces y se comparan tamaño y fecha de modificación; si cambió, se reintenta en el siguiente escaneo.

Pendientes del intérprete, por frecuencia en las definiciones: charsets predefinidos `CS_*`, `base="256"`, `format@formatter` (formato estilo Java), operación `shift`, columnas dentro de `divide`, y archivos `nvram` de varios ficheros (no afectan a los `.hi` de FBNeo).

## Estructura prevista cuando comience el código

```text
arcade-hall-of-fame/
  README.md
  CONTRIBUTING.md
  LICENSE                    # tras concretar licencia y titular
  docs/
  pyproject.toml             # empaquetado mínimo; sin dependencias de ejecución
  src/arcade_hall_of_fame/
    hi2txt/                  # intérprete de definiciones (implementado)
    config.py
    reader.py
    models.py
    service.py
    storage.py
    cli.py
    ui.py
  tests/
    fixtures/synthetic/      # creadas por el proyecto; documentar procedencia
    test_hi2txt_*.py         # implementados, con definiciones sintéticas propias
    test_muestras_reales.py  # opcional, con variables de entorno
    test_reader.py
    test_history.py
    test_rankings.py
  .github/workflows/tests.yml
```

Los módulos vacíos, los tests sin comportamiento y el workflow no se crean todavía. La configuración real, las definiciones descargadas y las muestras privadas viven fuera del repositorio (`local/` está excluido).

## Dependencias y distribución

Usar `argparse`, `dataclasses`, `pathlib`, `hashlib`, `sqlite3`, `tomllib`, `logging`, `unittest` y `xml.etree.ElementTree` (para las definiciones). Tkinter es la primera opción para evitar un navegador o framework; en Linux puede requerir un paquete del sistema. Validar la disponibilidad y el comportamiento en Catalina antes de comprometer la elección. No añadir otra biblioteca gráfica sin evidencia de necesidad.

Primero ejecución desde entorno virtual, sin aplicación empaquetada ni servicio de arranque. Los comandos públicos definitivos se documentarán cuando existan. Las integraciones futuras invocarán esos comandos con argumentos escapados y sin escribir en los guardados originales; su API concreta se investigará en esa etapa.
