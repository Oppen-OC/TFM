---
id: 046
titulo: El retraso de un paso se sabe 80,7 s después de ocurrir (mediana); a una parada de horizonte el 45 % de las predicciones llega tarde, y sobre las que llegan a tiempo la v2 mejora 1,17 s al listón
fecha: 2026-10-07
tipo: limitacion
capa: pipeline
capitulo: resultados
impacto: alto
estado: aceptado
evidencia: uv run dvc repro (metrics/features.json, disponibilidad_test; metrics/eval.json, poblacion, global, nowcast y por_horizonte; run de MLflow 3d7cb0acc52b400cac63fe4286a37be2)
trampa: 017
---

## Qué se observó

**Cuándo se sabe un retraso.** El retraso de un paso por parada no se conoce
cuando ocurre (`t_obs`), sino cuando han llegado las dos posiciones que usa
`cruces` (k1 y k1+1) y, en las primeras paradas, cuando se ha asignado el
viaje programado con sus tres primeros pasos (ADR-022). En la prueba
(21/09-04/10, 840.022 filas):

| | p10 | p50 | p90 |
|---|---|---|---|
| retardo de disponibilidad, `t_disp − t_obs` | 57,3 s | **80,7 s** | 116,0 s |
| horizonte previsto (horario menos lo ya consumido) | −44,2 s | 4,1 s | 60,1 s |
| horizonte útil real, `t_obs(i+1) − t_disp(i)` | −65,9 s | −1,5 s | 71,3 s |

Con una parada de horizonte, **el 45,1 % de las filas** tiene un horizonte
previsto ≤ 0: cuando se sabe el retraso, ya no queda tiempo, según el horario,
para que la predicción sirva. Son *nowcast*. Con el horizonte real, son el
51,3 %. De los primeros pasos de cada viaje queda en la población el 0,1 %; de
los segundos, el 4,9 %; de los terceros, el 65,8 %.

**El instrumento mintió dos veces.** La exploración del 07/10 dio 37 s de
mediana, porque aceptaba la posición que coincide con `t_obs`, que es la de
antes del cruce. La primera versión del pipeline dio 47,7 s, porque se quedaba
en k1 y no veía que `cruces` corrige la velocidad con k1+1 ni que el retraso
espera a la asignación. Lo encontró el tribunal; la cifra buena es 80,7 s.

**El modelo** (v2: residuo con pérdida absoluta, 758 árboles; entrenado y
evaluado sobre la población, horizonte previsto > 0):

| población (461.115 filas, 39.836 viajes) | MAE | RMSE |
|---|---|---|
| persistencia | 37,57 s | — |
| persistencia + sesgo del tramo | 26,66 s | 44,18 s |
| **modelo** | **25,49 s** | **43,23 s** |

Frente a `persistencia_tramo`, **−1,17 s**: [−1,20, −1,14] remuestreando
viajes y [−1,28, −1,07] remuestreando días. Frente a la persistencia, −12,08 s
[−12,17, −11,99].

| horizonte previsto | filas | `persistencia_tramo` | diferencia (IC por días) |
|---|---|---|---|
| 0-30 s | 253.187 | 24,16 s | −1,02 [−1,11, −0,93] |
| 30-60 s | 123.608 | 27,28 s | −1,26 [−1,38, −1,13] |
| 60-120 s | 69.649 | 31,03 s | −1,38 [−1,50, −1,26] |
| > 120 s | 14.671 | 43,92 s | −2,17 [−2,62, −1,75] |

- Mejora en las cuatro bandas de intervalo: de −1,08 a −2,02 s, intervalos
  por días lejos del cero.
- 25 de las 26 líneas con soporte propio mejoran y ninguna empeora.
- El grupo de poco soporte no se distingue: −0,32 [−0,72, 0,04].
- La línea sin entrenamiento empeora +8,7 s (185 filas).
- **En el *nowcast*** (378.907 filas), el modelo es **+9,56 s peor** que
  `persistencia_tramo` (35,82 frente a 26,26). No se ha entrenado con esas
  filas, que incluyen los primeros pasos de cada viaje. En producción no se
  predicen.

## Cómo se midió

```bash
uv run dvc repro                   # features -> train -> evaluate
cat metrics/features.json          # disponibilidad_test
cat metrics/eval.json              # poblacion, global, nowcast, por_horizonte
```

`features.instante_disponible` cruza los pasos con las posiciones fiables de
`emt_tracked` y la llegada de cada sondeo en el curated (`ts_ingest_utc`
mínimo por `snapshot_id`). La guardia es un test de extremo a extremo contra
`etiquetado.cruces` (trampa 017, mutantes 114-123).

## Por qué importa

- **A una parada de horizonte, predecir el retraso es casi siempre llegar
  tarde.** Un dato que tarda 81 s en estar disponible, frente a un horario
  mediano de 84 s hasta la parada siguiente (`t_prog_hasta_objetivo_s` en la
  prueba), deja un horizonte previsto mediano de 4 s. La parte «con
  cuánta antelación» de la pregunta exige horizontes de varias paradas.
- **La mejora honesta del modelo es de 1,17 s**, un 4,4 % del error del
  listón, no los 2,09 s de la bitácora 043. Más de la mitad de aquella venía
  del primer paso de cada viaje, cuyo retraso no se conoce hasta asignarlo. La
  ganancia crece con el horizonte: −1,0 s a menos de 30 s y −2,2 s a más de
  2 min.
- **Lo que llega a tiempo depende de la latencia de la fuente**, 26,6 s de
  mediana entre la posición y nuestro disco (`latencia_s` del curated en la
  prueba; p90, 41,7 s), **y de la cadencia de sondeo**.
  Es un límite del sistema, no del modelo.

## Qué se hizo / qué queda abierto

Hecho:
- ADR-022 (`t_disp`, horizonte previsto y población) y ficha 017 cerrada.
- La primaria del ADR-018 pasa a calcularse sobre la población.

Abierto:
- **El barrido de horizontes**: h = 1, 2, 3… paradas, con la antelación
  definida antes de predecir. Es la siguiente tanda.
- **El brazo del ADR-021 se eligió** sobre todas las filas y con `t_obs`. No
  se ha vuelto a elegir con la población nueva.
- **`ts_ingest_utc` se toma antes de la petición HTTP** (`collect.py`): el
  retardo real es algo mayor, en lo que tarde la respuesta.
- **Cuándo existe un viaje** también depende del futuro: los filtros de
  recorrido mínimo se calculan sobre el viaje entero. Se declara.

## Para la memoria

> En tiempo real, el retraso de un autobús en una parada no se conoce cuando
> el autobús pasa por ella, sino cuando llegan las posiciones que permiten
> situar ese paso y, en las primeras paradas de cada viaje, cuando se ha
> identificado el servicio programado. En el periodo de prueba ese retardo es
> de 80,7 s de mediana. Con un horizonte de una parada, en el 45 % de los casos
> el horario no deja ya margen para que la predicción sea útil: esas
> predicciones se informan aparte como estimaciones del estado presente. Sobre
> las restantes (461.115 pasos de 39.836 viajes), el modelo reduce el error
> absoluto medio en 1,17 s respecto a la persistencia corregida con el sesgo
> del horario por tramo (IC 95 % remuestreando días: 1,07-1,28 s). La mejora
> crece con el horizonte disponible, de 1,0 s a 2,2 s. La antelación con la
> que puede anticiparse el retraso exige, por tanto, horizontes de varias
> paradas.
