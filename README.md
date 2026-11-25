# Arcade Hall of Fame

Proyecto para clasificar jugadores de máquinas arcade por la cantidad de juegos en los que poseen el récord número uno. Python, SQLite y funcionamiento local, independiente del frontend de emulación.

**Estado: requisitos y planificación. No hay aplicación ni adaptadores implementados.** La primera prueba de concepto será exclusivamente Galaga en RetroArch + FinalBurn Neo, validada con archivos reales. La compatibilidad con MAME y las integraciones con Attract-Mode y ES-DE son posteriores.

## Documentación

- [Trabajo existente: hi2txt y definiciones publicadas](docs/TRABAJO_EXISTENTE.md). La próxima investigación parte de estas fuentes y de las muestras ya disponibles.
- [Requisitos y reglas de clasificación](docs/REQUISITOS.md).
- [Investigación inicial de FinalBurn Neo y Galaga](docs/INVESTIGACION_GALAGA.md), con fuentes fijadas a una revisión.
- [Evidencia alternativa de Bubble Bobble](docs/INVESTIGACION_BUBBLE_BOBBLE.md): primera tabla contrastada con archivo real, sin adaptador implementado.
- [Arquitectura y plan de implementación](docs/PLAN.md).
- [Protocolo de validación con archivos reales](docs/VALIDACION.md).
- [Contribución y preparación para GitHub](CONTRIBUTING.md).

## Primer entorno objetivo

iMac Late 2013, Intel, macOS Catalina 10.15. Versiones comunicadas por el usuario: RetroArch **1.22.2 nightly** y FinalBurn Neo **1.0.0.03**. Linux será el segundo entorno de validación. La fecha/revisión de las compilaciones, el set exacto y las rutas efectivas siguen pendientes; los [pasos para localizarlos](docs/VALIDACION.md#localizar-los-archivos-en-la-imac) no requieren modificar los guardados.

El repositorio inicial estaba vacío. Esta entrega contiene documentación y exclusiones para datos locales; no incluye ROMs, BIOS, archivos del emulador, bases de datos ni capturas de partidas.

## Próximo hito

Obtener una secuencia privada de archivos reales de Galaga y sus resultados visibles, documentar la correspondencia entre bytes, puntuaciones e iniciales, y solo entonces implementar el adaptador. Un caso sintético no acredita compatibilidad real.

Licencia propuesta para el código propio: MIT. La elección y los titulares deben concretarse antes de publicar; todavía no se declara una licencia concedida. El código y los recursos de terceros conservan sus condiciones originales.
