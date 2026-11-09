---
id: 009
tema: puerta · mutante 205, copia del crudo de clima a la Pi y fichas 020-021 (capa 157)
fecha: 2026-11-09
fuentes: src/project/ingest/sources.py (resolver_convencion, parse_meteo, ESTACIONES_MUNICIPALES), .claude/trampas/002-emt-alterna-convencion-horaria.md, docs/bitacora/063
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · una lectura decide por las cinco
<!-- concepto: convencion-la-pone-quien-sirve -->

En la capa 157, la convención de las cinco filas de un sondeo la decide una sola
lectura: la más fresca de W01/W02. Después esa conversión se aplica también a
W03, W04 y W06, que no han votado. ¿Por qué es legítimo convertir las lecturas de
AEMET con una convención decidida mirando solo W01? ¿Y por qué no vale decidirla
con la lectura más fresca de AEMET, aunque sea la única que haya?

**Respuesta:**

> porque w01 es la que se actualiza con más frecuencia, dando un resultado más
> fresco. porque tiene una hora de retraso con respecto a cuando da el dato y
> cuando se recibe

**Veredicto:** a-medias

_Rondas._ Ronda 1, a-medias. La frescura explica por qué W01 vota bien, pero no
por qué su veredicto vale para la fila de W03. ¿Quién pone la convención en
`fecha_carg`: la estación al medir, o quien arma la respuesta? Si fuera la
estación, ¿podrías aplicar a W03 la de W01? Mira la Causa de la trampa 002. En
la segunda parte vas bien con «una hora de retraso», pero falta la coincidencia:
¿cuánto vale hoy el desfase entre la hora de València y UTC, y dónde caen los
51-91 min de AEMET respecto a él?

**Respuesta (ronda 2):**

> la convención horaria la pone quien arma la respuesta. no se podría aplicar W03
> a W01 porque esta da la respuesta con una hora de retraso. El desfase de hoy de
> valencia es de una hora con el UTC, esos minutos caen sobre la hora de
> valencia, no la utc.

**Veredicto (ronda 2):** a-medias

_Respuesta completa._ Aciertas el qué en las dos partes (la convención la pone
quien arma la respuesta; el retraso de AEMET es del tamaño del desfase), pero
faltan las consecuencias, que son el porqué de la regla.

Si la convención la pone el nodo que arma la respuesta, todas las filas de esa
respuesta salen con la misma: por eso basta un testigo cuya latencia no deje
dudas. Si W01 dice UTC, W03 también está en UTC aunque su lectura sea vieja: lo
viejo es la estación, la convención es del servidor.

AEMET no sirve de testigo porque su retraso (51-91 min) coincide con el desfase
de invierno (CET, UTC+1). Una lectura con 61 min de retraso servida en hora
local y leída como UTC da 1 min de latencia, que es plausible: las dos
hipótesis cuadran, y si gana la equivocada el sondeo entero queda +1 h sin
aviso. W01/W02 llegan con ~7 min, y leídas al revés salen a −53 min o a +67 min,
fuera de la horquilla [−180, 2400] s: no hay empate posible. Sin ellas, `DUDOSA`
(mutante 207, ficha 021).
