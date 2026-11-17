---
id: 012
tema: puerta · actualizar los notebooks de EDA sobre data/curated
fecha: 2026-11-16
fuentes: notebooks/EDA/eda_utils.py, src/project/ingest/reprocesar.py, .claude/trampas/011-primera-captura-puede-ser-bloque-a-medias.md, docs/bitacora/019
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · curated del colector frente al de `curar`
<!-- concepto: primera-captura-bloque-a-medias -->

Los notebooks leen `data/curated/`. Ese directorio puede venir del colector en
vivo o del stage `curar` (`reprocesar`). ¿Por qué no da lo mismo para las cifras
de sondeos y filas de la EMT que los notebooks van a recontar, y qué trampa lo
explica?

**Respuesta:**

> reprocesar que hace? no recordaba que existia

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: no conocía `reprocesar`. Pista: los dos leen los
mismos payloads; cuando un sondeo llega capturado más de una vez, cada uno se
queda una copia distinta. Puntero: docstring de `src/project/ingest/reprocesar.py`,
líneas 19-31.

**Respuesta (ronda 2):**

> No da lo mismo porque a veces el primer sondeo de la EMT da una insersion
> parcial y que no está completa, por lo que el reprocesra se queda con la
> siguiente captura completa y reemplaza la anterior. Lo explica la trampa de la
> bitacora 19

**Veredicto (ronda 2):** a-medias

_Respuesta completa._

- **El mecanismo está bien.** La primera captura de un `snapshot_id` puede ser el
  bloque a medio reinsertar. El colector se la queda; `reprocesar` se queda la
  que más filas trae.
- **La trampa no es esa.** Es la **011**. La bitácora 019 es otro mecanismo: el
  sondeo servido repetido e idéntico, que sin `clave_sondeo` entra dos veces
  (+53 % de trayectorias el 27/08). Una mete filas de más; la otra pierde filas.
  Confundirlas es justo lo que hace dudar de qué arregla cada guardia.
- **Faltaba la consecuencia en cifras.** Del 15/08 al 18/09, el curated del
  colector perdía 1.200 sondeos (1,5 %) y 109.063 posiciones. Recontar sondeos y
  filas sobre el curated en vivo da menos, y con el sesgo de las horas en que la
  EMT reinserta a medias.
