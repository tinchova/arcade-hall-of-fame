# Lectores y definiciones existentes

Investigación ampliada el 2026-11-25. La búsqueda inicial se centró demasiado en la persistencia de FBNeo y omitió lectores ya existentes. No es necesario deducir todos los formatos mediante partidas nuevas.

## Fuentes encontradas

- [hi2txt, documentación del autor](https://greatstoneex.github.io/hi2txt-doc/doc/index.html): convierte archivos de puntuaciones en texto y utiliza descripciones específicas por juego. Tiene motores Java y C#.
- [hi2txt-xml](https://github.com/GreatStoneEx/hi2txt-xml): repositorio de definiciones, separado del motor. Se inspeccionó la revisión `990fca26edb8cd9e37ab0b569d5d59b06e31f0e0`.
- [Definición de Galaga](https://github.com/GreatStoneEx/hi2txt-xml/blob/990fca26edb8cd9e37ab0b569d5d59b06e31f0e0/src/main/db/galaga.xml): longitud de 51 bytes; cinco puntuaciones, cinco nombres, máximo y conversión de caracteres. Incluye las dos regiones de memoria investigadas.
- [Definición de Bubble Bobble](https://github.com/GreatStoneEx/hi2txt-xml/blob/990fca26edb8cd9e37ab0b569d5d59b06e31f0e0/src/main/db/bublbobl.xml): longitud de 86 bytes; cinco filas con puntuación, ronda y nombre. Documenta multiplicación de puntuación por diez y ronda más uno, además del máximo y contadores adicionales.
- [OpenHi2txt](https://github.com/inigomonyota/openhi2txt): lector C++ con biblioteca y CLI compatibles con definiciones hi2txt. No se ha probado en Catalina ni con las muestras aportadas.
- [ArcadeScore](https://github.com/mikedmor/ArcadeScore): proyecto existente de gestión de puntuaciones arcade; candidato para una comparación funcional, sin afirmar equivalencia con la clasificación por cantidad de primeros puestos solicitada.

## Qué cambia

Las definiciones de Galaga y Bubble Bobble aportan documentación independiente de los formatos. Sus tamaños coinciden con las muestras reales recibidas; la descripción de campos de Bubble Bobble concuerda con las cinco filas contrastadas con la foto. No se ha ejecutado el motor hi2txt contra esas muestras: distinguir esa coincidencia de una prueba del programa completo.

El paso siguiente es contrastar las definiciones publicadas con los archivos disponibles y evaluar reutilización, dependencias y condiciones de distribución. No pedir más partidas como requisito previo de esta comparación. Los casos de historial, idempotencia y cambios de titular se podrán probar con resultados normalizados sintéticos, sin obligar al usuario a conseguir récords para cada caso.

Las definiciones documentan versiones de MAME; su coincidencia con FBNeo debe comprobarse por juego y perfil. Mantener validación con archivos reales, pero reservar nuevas capturas para discrepancias concretas o una prueba final del flujo completo.

Python y SQLite siguen siendo la base propuesta. Ejecutar hi2txt como herramienta auxiliar o usar su documentación para un adaptador pequeño son alternativas a evaluar; no introducir todavía un intérprete XML general ni una dependencia Java/C++ obligatoria. Si se reutilizan código o definiciones, revisar sus licencias antes de copiarlos o fijar la licencia del proyecto. En esta investigación solo se incorporan enlaces y conclusiones, no archivos de terceros.

Se mantiene un solo adaptador inicial: no implementar Galaga y Bubble Bobble simultáneamente. El cambio de prioridad es investigar reutilización antes de continuar con la deducción manual.
