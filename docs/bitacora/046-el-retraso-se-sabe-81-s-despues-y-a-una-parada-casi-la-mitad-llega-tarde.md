---
id: 046
titulo: El retraso de un paso se sabe 80,7 s después de ocurrir (mediana); a una parada de horizonte el 45 % de las predicciones llega tarde, y sobre las que llegan a tiempo la v2 mejora 1,01 s al listón, un 4 % estable con el horizonte
fecha: 2026-10-07
tipo: limitacion
capa: pipeline
capitulo: resultados
impacto: alto
estado: aceptado
evidencia: uv run dvc repro (metrics/features.json, disponibilidad_test; metrics/eval.json, poblacion, global, nowcast y por_horizonte; run de MLflow f3dfde9553744f76ae677ef41f31c0e7). Latencia, horario y peso de los primeros pasos, con los comandos de «Cómo se midió»
trampa: 017
---

> **Revisada por la bitácora 047 (08/10).** La población añade que la fila sea
> el último paso conocido de su viaje, y el objetivo ya no exige las paradas
> intermedias. Con eso, en *h* = 1 la mejora es de −1,06 s. Partida por la
> antelación real, la parte con más de 30 s no mejora al listón (+0,28 s): a una
> parada no hay antelación útil. Las cifras de abajo son las del 07/10.

## Qué se observó

**Cuándo se sabe un retraso.** El retraso de un paso por parada no se conoce
cuando ocurre (`t_obs`). Hacen falta las dos posiciones que usa `cruces` (k1 y
k1+1, y de ellas la que llegue más tarde). En las primeras paradas de cada
viaje, además, hay que haber asignado el viaje programado con sus tres primeros
pasos (ADR-022). En la prueba (21/09-04/10, 835.304 filas):

| | p10 | p50 | p90 |
|---|---|---|---|
| retardo de disponibilidad, `t_disp − t_obs` | 57,4 s | **80,7 s** | 115,8 s |
| horizonte previsto (horario menos lo ya consumido) | −44,3 s | 3,9 s | 58,8 s |
| horizonte útil real, `t_obs(i+1) − t_disp(i)` | −66,0 s | −1,8 s | 69,5 s |

- El horario mediano hasta la parada siguiente es de 84 s, y la latencia
  mediana entre la posición y nuestro disco, de 26,6 s (p90, 41,7 s).
- Con una parada de horizonte, **el 45,3 % de las filas** tiene un horizonte
  previsto ≤ 0: cuando se sabe el retraso, según el horario ya no queda tiempo
  para que la predicción sirva. Son *nowcast*.
- Con el horizonte real, son el 51,5 %.

**El instrumento mintió dos veces.**
1. La exploración del 07/10 dio 37 s, porque aceptaba la posición que coincide
   con `t_obs`, que es la de antes del cruce.
2. La primera versión del pipeline dio 47,7 s. Se quedaba en k1: no veía que
   `cruces` corrige la velocidad con k1+1, ni que el retraso espera a la
   asignación. Lo encontró el tribunal.

**El objetivo saltaba paradas.** Si la parada siguiente no se había observado,
el objetivo era la de después, y el horario y la distancia hasta él sabían de
un hueco que aún no había ocurrido: el 0,54 % de las filas, y una cuarta parte
de la banda de más de 120 s. Ahora el objetivo es la parada siguiente del
horario (ADR-006).

**El modelo** (v2: residuo con pérdida absoluta, 348 árboles, entrenado y
evaluado sobre la población, horizonte previsto > 0):

| población (456.823 filas, 39.801 viajes) | MAE | RMSE |
|---|---|---|
| persistencia | 36,99 s | — |
| persistencia + sesgo del tramo | 26,27 s | 41,93 s |
| **modelo** | **25,26 s** | **41,08 s** |

Frente a `persistencia_tramo`, **−1,01 s**: [−1,04, −0,99] remuestreando
viajes y [−1,12, −0,91] remuestreando días. El RMSE baja −0,84 s, con
intervalo por días [−0,98, −0,71]. Frente a la persistencia, −11,73 s.

| horizonte previsto | filas | `persistencia_tramo` | diferencia (IC por días) | relativa |
|---|---|---|---|---|
| 0-30 s | 253.160 | 24,14 s | −0,88 [−0,98, −0,79] | −3,6 % |
| 30-60 s | 123.548 | 27,26 s | −1,08 [−1,20, −0,97] | −4,0 % |
| 60-120 s | 69.173 | 30,86 s | −1,19 [−1,32, −1,08] | −3,9 % |
| > 120 s | 10.942 | 35,56 s | −2,11 [−2,69, −1,63] | −5,9 % |

- **En segundos la ganancia crece con el horizonte; en proporción es casi
  plana, en torno al 4 %:** el error del listón crece con él.
- Mejora en las cuatro bandas de intervalo: de −0,92 a −1,83 s.
- 25 de las 26 líneas con soporte propio mejoran y ninguna empeora.
- El grupo de poco soporte **no se distingue**: −0,01 [−0,41, 0,34].
- La línea sin entrenamiento empeora +4,2 s (185 filas).
- **En el *nowcast*** (378.481 filas), el modelo es **+7,69 s peor** que
  `persistencia_tramo`. No se entrena con esas filas, que incluyen los primeros
  pasos de cada viaje. En producción no se predicen.

## Cómo se midió

```bash
uv run dvc repro                   # features -> train -> evaluate
cat metrics/features.json          # disponibilidad_test
cat metrics/eval.json              # poblacion, global, nowcast, por_horizonte
```

`features.instante_disponible` cruza los pasos con las posiciones fiables de
`emt_tracked` y la llegada de cada sondeo en el curated (`ts_ingest_utc`
mínimo por `snapshot_id`). La guarda un test de extremo a extremo contra
`etiquetado.cruces` (trampa 017, mutantes 114-125).

La latencia y el horario mediano, sin `metrics/`:

```python
import duckdb, pandas as pd
duckdb.sql("select median(latencia_s), quantile_cont(latencia_s, 0.9) from read_parquet("
           "'data/curated/source=emt_buses/*/*.parquet', hive_partitioning=false) "
           "where ts_ingest_utc >= '2026-09-21' and ts_ingest_utc < '2026-10-05'")
pd.read_parquet("data/processed/test.parquet")["t_prog_hasta_objetivo_s"].median()
```

## Por qué importa

- **A una parada de horizonte, predecir el retraso es casi siempre llegar
  tarde.** Con 81 s para saber el dato y 84 s de horario hasta la parada
  siguiente, el horizonte previsto mediano es de 4 s. La parte «con cuánta
  antelación» de la pregunta exige horizontes de varias paradas.
- **La mejora honesta del modelo es de 1,01 s, un 4 % del error del listón**,
  no los 2,09 s de la bitácora 043. Entre las dos cifras cambian a la vez la
  disponibilidad, la población y el objetivo, así que la diferencia no se
  puede atribuir a una sola causa. Que el primer paso de cada viaje llevara
  mucho peso (−23 s en esas filas con la definición anterior) es un hecho; qué
  parte de los 1,08 s perdidos explica, no.
- **Lo que llega a tiempo depende de la fuente y de la cadencia,** no del
  modelo: casi un tercio del retardo es la latencia entre la posición y
  nuestro disco.

## Qué se hizo / qué queda abierto

Hecho:
- ADR-022 (`t_disp`, horizonte previsto y población), la precisión del
  ADR-006 (el objetivo es la parada siguiente del horario) y la ficha 017
  cerrada.

Abierto:
- **El barrido de horizontes,** h = 1, 2, 3… paradas, con la antelación
  definida antes de predecir. Es la siguiente tanda.
- **El brazo del ADR-021** se eligió sobre todas las filas y con `t_obs`; no
  se ha vuelto a elegir.
- **`ts_ingest_utc` se toma antes de la petición HTTP** (`collect.py`): el
  retardo real es algo mayor.
- **La asignación tiene límites declarados en el ADR-022:** rivales que se
  resuelven después del tercer paso, `conflicto` y los filtros de recorrido
  mínimo, que miran el futuro, y una máscara `fiable` distinta en torno al 1 %
  de los viajes.

## Para la memoria

> En tiempo real, el retraso de un autobús en una parada no se conoce cuando
> el autobús pasa por ella, sino cuando llegan las posiciones que permiten
> situar ese paso y, en las primeras paradas de cada viaje, cuando se ha
> identificado el servicio programado. En el periodo de prueba ese retardo es
> de 80,7 s de mediana, frente a un horario mediano de 84 s entre paradas. Con
> un horizonte de una parada, en el 45 % de los casos el horario ya no deja
> margen para que la predicción sea útil: esas predicciones se informan aparte
> como estimaciones del estado presente. Sobre las restantes (456.823 pasos de
> 39.801 viajes), el modelo reduce el error absoluto medio en 1,01 s respecto a
> la persistencia corregida con el sesgo del horario por tramo (IC 95 %
> remuestreando días: 0,91-1,12 s), en torno a un 4 % de su error, una
> proporción que se mantiene con el horizonte disponible. La antelación con la
> que puede anticiparse el retraso exige, por tanto, horizontes de varias
> paradas.
