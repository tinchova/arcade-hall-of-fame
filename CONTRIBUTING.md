# Contribuir

El proyecto está en planificación. Antes de añadir código, revisar [requisitos](docs/REQUISITOS.md), [plan](docs/PLAN.md) y [protocolo de validación](docs/VALIDACION.md).

## Alcance inicial

Solo Galaga con el set y formato confirmados mediante evidencia real. No añadir otros adaptadores mientras no se haya validado el primero. Las contribuciones de investigación deben separar hechos, inferencias y resultados reproducidos, con enlaces a fuentes primarias y revisiones concretas.

## Material admitido

- Código original, documentación y recursos propios con licencia compatible.
- Casos sintéticos creados para las pruebas, identificados como tales y con procedencia.
- Informes de validación sin nombres personales, rutas privadas ni datos originales.

No incorporar ROMs, BIOS, binarios de emuladores, volcados reales de memoria, partidas guardadas, `.hi`, bases de datos personales, capturas con datos privados ni archivos propietarios. No incluir un `hiscore.dat` descargado: enlazar su origen y documentar la definición investigada. No copiar código del emulador para implementar el parser.

## Verificación y futura publicación

Con el código implementado se usarán pruebas `unittest`, CI Linux con Python 3.11 y comprobación manual de Catalina Intel. Los comandos concretos se añadirán cuando existan; actualmente no hay suite ejecutable.

Antes de publicar, revisar los archivos preparados y el historial completo de Git. `.gitignore` evita inclusiones accidentales comunes, pero no elimina contenido ya versionado ni garantiza ausencia de datos sensibles. Confirmar licencia y titular del código propio; MIT es la propuesta inicial. Añadir avisos y licencias de terceros si se incorporan recursos externos.

Cada cambio debe describir problema, comportamiento resultante y validación realizada. Los adaptadores futuros necesitan su propia investigación y muestras privadas; una extensión compartida no acredita formato compatible.
