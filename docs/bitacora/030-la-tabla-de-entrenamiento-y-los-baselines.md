---
id: 030
titulo: La tabla de entrenamiento tiene 1,24 M de filas en 19 días y la prueba 269.493 en 5; la persistencia deja el MAE de la parada siguiente en 37,6 s frente a 139,9 del horario, y los diagnósticos de la asignación miraban el futuro
fecha: 2026-09-25
tipo: medicion
capa: pipeline
capitulo: metodologia
impacto: alto
estado: aceptado
evidencia: uv run dvc repro features (métricas en metrics/features.json)
trampa: —
---

## Qué se observó

`features.py`, fase 1, sin tráfico. Una fila es el paso de un viaje por la
parada *i*, en *t* = `t_obs(i)`. El objetivo es el retraso en el paso siguiente
observado del mismo viaje (h = 1, ADR-006), y la variante binaria, si pasa de
300 s. Las variables usan solo lo observado antes de *t*:

- los retrasos del viaje en *i*, *i − 1* e *i − 2*;
- la distancia y el tiempo programado hasta el objetivo;
- el retraso medio de *otros* viajes de la línea en [*t* − N, *t*), con N = 1, 5
  y 15 min;
- el retraso del último viaje de la línea que pasó por la parada objetivo antes
  de *t*, y cuánto hace;
- hora, día de la semana y la línea.

Split por día de servicio (ADR-007), con `test_desde` = 14/09:

| | días | filas | positivos (> 300 s) |
|---|---|---|---|
| entrenamiento | 19 (15-30/08 y 08-10/09) | 1.236.585 | 5,70 % |
| prueba | 5 (14-18/09) | 269.493 | 5,85 % |

Ningún viaje queda a los dos lados del corte. Del 31/08 al 07/09 no hay datos:
son los días excluidos (bitácora 024). Del 11 al 13/09 tampoco, por el hueco del
geoportal (bitácora 021); el 10 y el 14 son parciales.

**Baselines sobre la prueba** (MAE / RMSE, en segundos):

| baseline | MAE | RMSE |
|---|---|---|
| horario (retraso 0) | 139,9 | 195,8 |
| persistencia (el retraso de *i*) | **37,6** | 72,6 |

Por línea, en las que tienen más de 5.000 filas de prueba, la persistencia va
de 32,5 s (99) a 46,2 s (C3). La 24 y la 25 quedan en 26,6 y 26,9 s, pero solo
con 2.060 y 509 filas: el 0,95 % de la prueba, frente al 1,47 % del
entrenamiento. Es la caída de publicación de la 25 desde el 09/09 (bitácora
025).

**Dos cosas que salieron al construirla:**

- **Fuga de los diagnósticos.** `pasos` trae `desfase_s`, `margen_s` y
  `coste_s`, que resumen la asignación del viaje. `desfase_s` es la mediana del
  desfase en las primeras paradas: en la parada 1 o 2 incluye el retraso de
  paradas **futuras**. Quedan fuera de la tabla (`FUERA_DE_LA_TABLA`), y las
  variables del modelo las da `features.variables()`, que es la lista que leerán
  `train.py` y `predict.py`.
- **Tipos mezclados.** `fecha_servicio` llega como `datetime64` en unas
  particiones y como `date` en otras; concatenadas, la columna ni se ordena. Es
  la misma familia que el issue #2. `construir` la normaliza al entrar.

## Cómo se midió

```bash
uv run dvc repro features        # tabla, split y metrics/features.json
```

Los baselines se calculan en `features.baselines()` sobre la prueba, globales y
por línea (`metrics/features.json → baselines_test`).

## Por qué importa

- El listón para el modelo es la persistencia, no el horario. Con 37,6 s de MAE
  a una parada, un modelo que no la bata por un margen claro no aporta, y la
  contribución del tráfico (fase 2) se medirá contra ella y contra el modelo sin
  tráfico.
- Las comprobaciones de fuga son las que el tribunal hará primero. Los tests
  construyen pasos con instantes conocidos y los mutantes 079-082 confirman que
  cada una cae si se relaja la condición: el mismo instante *t*, el propio
  viaje, el bus anterior en *t* y los diagnósticos de la asignación.

## Qué se hizo / qué queda abierto

Hecho: `features.py`, `tests/test_features.py` (8 tests), mutantes 079-082,
`params.yaml → features.test_desde` al 14/09 y el stage con sus métricas.

Abierto:

- Fase 2: el tráfico aguas abajo (capas 192 y 188 proyectadas sobre el trazado
  entre *i* e *i + h*).
- Horizontes mayores (`horizonte_paradas`) para la segunda parte de la pregunta:
  con cuánta antelación.
- El bus anterior no tiene límite de antigüedad: el primero del día hereda al
  último de la noche anterior. Su edad es una variable, y el modelo la ve.
- La prueba es corta (5 días, septiembre) y con menos líneas publicadas.
  Rehacer el corte cuando se sincronice la captura posterior al 18/09.

## Para la memoria

> Cada observación de entrenamiento corresponde al paso de un viaje por una
> parada, y el objetivo es el retraso en la parada siguiente del mismo viaje. Las
> variables se construyen exclusivamente con información disponible en el
> instante del paso: los retrasos previos del propio viaje, el retraso medio de
> los demás viajes de la línea en los últimos 1, 5 y 15 minutos y el retraso del
> último vehículo que atravesó la parada objetivo. Se excluyeron expresamente los
> indicadores del proceso de asignación, que resumen paradas posteriores del
> mismo viaje. La partición entre entrenamiento y prueba es temporal, por día de
> servicio: 19 días y 1,24 millones de observaciones para entrenar, y los 5
> últimos días, con 269.493 observaciones, para evaluar. Sobre la prueba, suponer
> que el vehículo circula según horario da un error absoluto medio de 139,9 s, y
> suponer que mantiene su retraso actual, de 37,6 s. Esta última es la referencia
> que cualquier modelo debe superar.
