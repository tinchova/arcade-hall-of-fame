# Contribuir

El proyecto está en prueba de concepto. Antes de añadir código, revisar [requisitos](docs/REQUISITOS.md), [plan](docs/PLAN.md) y [protocolo de validación](docs/VALIDACION.md).

## Alcance inicial

Los juegos se leen con el intérprete de definiciones hi2txt (`src/arcade_hall_of_fame/hi2txt/`); no se escriben adaptadores por juego. Para ampliar la cobertura, implementar operaciones del formato que falten, partiendo de la [referencia pública](https://greatstoneex.github.io/hi2txt-doc/doc/xml.html) y midiendo con `python -m arcade_hall_of_fame.hi2txt.conformance`. Las contribuciones de investigación deben separar hechos, inferencias y resultados reproducidos, con enlaces a fuentes primarias y revisiones concretas.

## Material admitido

- Código original, documentación y recursos propios con licencia compatible.
- Casos sintéticos creados para las pruebas, identificados como tales y con procedencia.
- Informes de validación sin nombres personales, rutas privadas ni datos originales.

No incorporar ROMs, BIOS, binarios de emuladores, volcados reales de memoria, partidas guardadas, `.hi`, bases de datos personales, capturas con datos privados ni archivos propietarios. No incluir un `hiscore.dat` descargado: enlazar su origen y documentar la definición investigada. No copiar código del emulador para implementar el parser.

No incorporar definiciones, DTD, casos de prueba ni código de hi2txt, hi2txt-xml u OpenHi2txt (GPL): se descargan con `fetch` en `local/`. Las pruebas usan definiciones sintéticas mínimas escritas para el proyecto.

## Verificación y futura publicación

Las pruebas se ejecutan con `python -m unittest` desde la raíz. Más adelante se añadirá CI Linux con Python 3.11 y comprobación manual de Catalina Intel.

Antes de publicar, revisar los archivos preparados y el historial completo de Git. `.gitignore` evita inclusiones accidentales comunes, pero no elimina contenido ya versionado ni garantiza ausencia de datos sensibles. Confirmar licencia y titular del código propio (decisión pendiente). Añadir avisos y licencias de terceros si se incorporan recursos externos.

Cada cambio debe describir problema, comportamiento resultante y validación realizada. Los adaptadores futuros necesitan su propia investigación y muestras privadas; una extensión compartida no acredita formato compatible.
