---
id: 017
titulo: Las variables calculadas en t_obs ven pasos que aún no han llegado
estado: vigente
capa: pipeline
detectada: 2026-10-07
test: ninguno
---

## Síntoma

La v2 bate al listón por 2,09 s (bitácora 043), pero en tiempo real sus
variables no tendrían todo lo que usan. Un paso por parada se conoce, de
mediana, 37 s después de `t_obs` (p90, 60 s). En el 11-13 % de las filas, el
bus ya ha pasado por la parada siguiente cuando el sistema se entera del paso
por la actual (bitácora 046). Las métricas salen mejores que en producción, sin
ningún error.

## Causa

`t_obs` es la SALIDA interpolada de la parada (`etiquetado.cruces`). Se sabe
cuando llega la primera posición más allá de ella, un sondeo después, a lo que
se suma la latencia de la fuente. `features.construir` usa `t_obs` como «ahora»
de la fila y como el instante en que se conocen los pasos de los demás buses:
en las ventanas `[t − N, t)`, en el bus anterior y en la flota del tramo.

## Por qué se vuelve a caer aquí

El orden de los eventos es correcto: nada usa lo que ocurre después de
`t_obs`, y los tests de fuga lo guardan (mutantes 079-082). La trampa no está
en el orden, sino en la disponibilidad: el evento ya ocurrió, pero el dato
todavía no había llegado. En un histórico todo está disponible a la vez, así
que nada lo delata.

## Guardia

Pendiente: un test sintético en `tests/test_features.py` con un paso ocurrido
antes de `t_obs(i)` pero llegado después de `t_disp(i)`, que no debe contar.
