---
id: 041
titulo: El primer XGBoost bate a la persistencia por 10,3 s de MAE pero empata con la persistencia más el sesgo del tramo (+0,03 s, IC 95 % [−0,18, 0,24]); en la banda de más de 30 min, la de etiqueta limpia, pierde 3,0 s
fecha: 2026-10-06
tipo: medicion
capa: pipeline
capitulo: resultados
impacto: alto
estado: abierto
evidencia: uv run dvc repro evaluate (metrics/eval.json; validación en el run de MLflow 879c3387e2704a5d878ca713946b6b4c, métricas val.*)
trampa: —
---

## Qué se observó

Es el primer modelo: XGBoost con las variables de `features.variables()` (fases
1 y 2, la flota como sensor y el sesgo del tramo, sin la capa 192), los
hiperparámetros de `params.yaml → train` sin búsqueda, la pérdida cuadrática y
la parada temprana en el 18-20/09. Salen 193 árboles y se reajusta con todo el
entrenamiento.

Prueba: 21/09-04/10, 840.022 filas, 40.032 viajes.

| | MAE | RMSE |
|---|---|---|
| horario (0) | 144,54 s | 200,73 s |
| persistencia | 36,80 s | 68,29 s |
| persistencia + sesgo del tramo | 26,48 s | 53,35 s |
| **modelo** | **26,51 s** | **50,42 s** |

La diferencia del modelo, con su intervalo del 95 % remuestreando viajes
(ADR-018):

| frente a | MAE | RMSE |
|---|---|---|
| persistencia | −10,29 [−10,51, −10,06] | −17,88 [−21,45, −13,81] |
| persistencia + sesgo del tramo | **+0,03 [−0,18, 0,24]** | −2,93 [−6,46, 0,89] |

Frente al listón del tráfico, **no se distingue** en ninguna de las dos
métricas. Por estratos, MAE frente a persistencia + sesgo del tramo:

| estrato | viajes | diferencia de MAE |
|---|---|---|
| soporte propio | 38.891 | −0,04 [−0,24, 0,19] |
| poco soporte | 1.119 | +2,32 [1,07, 3,84] |
| sin entrenamiento (línea 8) | 22 | +4,18 [0,68, 7,74] |
| intervalo ≤ 8 min | 9.321 | −0,41 [−0,80, 0,06] |
| 8-15 min | 19.846 | −0,17 [−0,44, 0,15] |
| 15-30 min | 8.270 | +0,07 [−0,34, 0,57] |
| > 30 min | 2.595 | **+2,99 [2,03, 4,00]** |

Entre las 26 líneas con soporte propio, frente a persistencia + sesgo del
tramo, el modelo mejora en 8, empeora en 9 y no se distingue en 9. Los
extremos son la 31 (−2,64 s) y la 23 (+3,32 s).

En la validación, la misma comparación daba ventaja al modelo: 25,38 s frente
a 26,07 s de MAE, y 39,79 frente a 48,43 de RMSE. En la prueba la ventaja
desaparece.

## Cómo se midió

```bash
uv run dvc repro                 # features -> train -> evaluate
cat metrics/eval.json            # global, por_grupo, por_banda, por_linea
uv run mlflow ui                 # run 879c3387…: val.* y test.*
```

La ejecución es determinista: dos `dvc repro` seguidos (commits `2f8358b` y
`8f2a68f`) dieron los mismos 193 árboles y las mismas cifras. El intervalo es
un bootstrap percentil de 1.000 réplicas sobre las sumas por viaje
(`evaluate.diferencia`). La banda de intervalo sale del GTFS de cada día
(`evaluate.banda_intervalo`, bitácora 038).

## Por qué importa

- **Lo que bate a la persistencia es el sesgo del horario, no el modelo.** La
  bitácora 039 lo anticipaba: el tercer baseline, una mediana por tramo sin
  ningún aprendizaje, hace lo mismo que el modelo. Hoy, nada de las variables
  de las fases 1 y 2, la flota como sensor incluida, añade una mejora medible
  en el conjunto.
- **Donde la etiqueta es limpia, el modelo pierde.** En la banda de más de
  30 min, donde la asignación casi no pliega (bitácora 038), empeora 3,0 s de
  MAE y 8,5 s de RMSE. Donde gana algo de RMSE es en la banda de 8 min o menos,
  la más contaminada por el pliegue. Antes de atribuir una mejora al tráfico,
  hay que descartar que el modelo esté aprendiendo el pliegue del etiquetador.
- **La validación no predijo la prueba.** El 18-20/09 es de viernes a domingo;
  la prueba son dos semanas enteras.
- **Esto no dice nada aún sobre la pregunta de investigación.** La capa 192 no
  está en el modelo (`incluir_trafico: false`).

## Qué se hizo / qué queda abierto

Hecho: `train.py`, `predict.py` y `evaluate.py`, con los mutantes 101-106.
Este modelo se conserva como resultado de referencia: la versión siguiente se
compara con él, no lo sustituye en silencio.

Abierto. Lo revisó el agente `tribunal` y cada punto se comprobó contra el
código o los datos:

- **Pérdida y parada.** La parada temprana usa el RMSE, el `eval_metric` por
  defecto de `reg:squarederror`, pero la métrica titular es el MAE. El sesgo
  del tramo es una mediana, que es lo que premia el MAE.
- **Modelar el residuo.** Con la pérdida cuadrática y el objetivo en nivel, el
  árbol tiene que reconstruir a trozos la identidad `retraso_s → objetivo`.
  Alternativas: el objetivo menos `retraso_s`, o `base_margin = retraso_s`.
- **Validación.** Elegir días con la composición de la prueba, por ejemplo la
  semana entera del 14-20/09.
- **`tramo_sesgo_soporte` no es estacionaria.** Crece con el calendario: la
  mediana es 276 en entrenamiento y 768 en la prueba. El árbol la ve fuera del
  rango en que aprendió.
- **Disponibilidad.** `t_obs` es la salida de la parada, y solo se conoce con
  la posición siguiente, a lo que se suma la latencia de la fuente (p50 36 s,
  `docs/01`). Las ventanas `[t − N, t)` la dan por conocida en `t`. No es una
  fuga del futuro en el orden de eventos, pero sí una sobreestimación de la
  antelación. Afecta a la segunda mitad de la pregunta de investigación.
- **Primeras paradas.** El viaje se asigna con los tres primeros cruces
  (`etiquetado.py`), así que `retraso_s` en las paradas 1 y 2 depende de
  cruces posteriores. Son el 7,7 % de la prueba.
- **El listón se eligió mirando la prueba.** La clave del sesgo del tramo
  (bitácora 039) se escogió comparando MAE en la prueba. Eso endurece el
  listón, no favorece al modelo, pero hay que declararlo.
- **Protocolo.** Fijar antes la métrica primaria, MAE global frente a
  persistencia + sesgo del tramo. Comparar las variantes en la validación,
  declarar cuántas se probaron, elegir una y evaluar la prueba una sola vez.

## Para la memoria

> El primer modelo de gradient boosting, entrenado con las variables del
> propio viaje, de la línea, del calendario, de la flota como sensor del tramo
> siguiente y del sesgo histórico del horario por tramo, obtiene en el periodo
> de prueba (21 de septiembre a 4 de octubre, 40.032 viajes) un error absoluto
> medio de 26,5 s en la parada siguiente. Mejora en 10,3 s a la persistencia
> (IC 95 % por viajes: 10,1-10,5 s), pero no se distingue de la persistencia
> corregida con el sesgo del horario por tramo: +0,03 s (IC 95 %: −0,18 a
> 0,24 s). La mejora sobre la persistencia se explica, por tanto, por la
> corrección del horario teórico, que una mediana histórica por tramo ya
> captura. En la banda de intervalos de más de 30 minutos, donde la etiqueta
> está libre del error de asignación, el modelo es 3,0 s peor que esa
> referencia (IC 95 %: 2,0-4,0 s). Este resultado fija el listón frente al que
> se mide la aportación del estado del tráfico.
