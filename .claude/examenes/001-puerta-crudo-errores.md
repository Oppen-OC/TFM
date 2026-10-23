---
id: 001
tema: puerta · trampa 018
fecha: 2026-10-23
fuentes: trampas/018, src/project/ingest/collect.py, src/project/analysis/medir_completitud.py, bitacora/044, bitacora/059, CLAUDE.md (Dominio)
estado: cerrado
ronda: 2
nota: 1/1
---

## P1 · el error de la fuente se guarda en el crudo
<!-- concepto: crudo-guarda-errores-de-la-fuente -->

El 13/10 el geoportal devolvió `{"error": …}` durante 3 h 45 min y el colector
guardó cada respuesta en el crudo como si fuera un sondeo bueno. El arreglo se
hizo en el instrumento de medida (`medir_completitud`), no en el colector. ¿Por
qué no se arregla haciendo que el colector deje de guardar esos payloads de
error? ¿Qué perdería el proyecto si lo hiciera?

**Respuesta:**

> no se pdorian recuperar si se descartan al momento, es improtante mantenerlo
> porque estamos creando un historico
> fallaba la fuente, si falla el crudo entonces muestra menos entradas de las
> esperadas para un determinado momento

**Veredicto:** correcta

_Rondas._ Ronda 1, a-medias: «perdería el contexto y las pruebas de que la api
funciona mal, es importante para la defensa del proyecto y saber que falta esa
informacion aporta mucho mas uqe borrarla». Acertaba el qué y le faltaba el
porqué de la capa. Pista: CLAUDE.md, *Dominio*, y el 05/10 de la bitácora 044.
A petición, la pista se concretó en dos preguntas guiadas. Ronda 2, correcta:
reconstruye la irreversibilidad. La segunda mitad, qué distingue en el crudo
un fallo de la fuente de uno del colector, quedó imprecisa. No cuenta como
acierto limpio y no entra en `debilidades.md`, que solo recoge fallos en
ronda 2.
