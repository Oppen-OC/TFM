---
id: 039
titulo: Lo que la persistencia no explica vive en el tramo, no en la línea; corregirla con el sesgo histórico del horario en cada par de paradas baja su MAE de 36,8 a 26,5 s (−28 %), y la línea sola lo baja 0,07 s
fecha: 2026-10-06
tipo: medicion
capa: pipeline
capitulo: metodologia
impacto: alto
estado: aceptado
evidencia: PYTHONIOENCODING=utf-8 uv run python -m project.analysis.medir_sesgo_tramo (salida en auditoria/resultados/sesgo_tramo.txt); metrics/features.json, persistencia_tramo
trampa: —
---

## Qué se observó

Con el corte del 21/09 (`c721899`: 1.525.118 filas de entrenamiento, 840.022 de
prueba en 14 días), la persistencia predice la parada siguiente con un MAE de
36,80 s. Se corrigió su error con la mediana del error en el entrenamiento,
agrupada a distintos niveles, y se midió en la prueba:

| corrección aprendida en entrenamiento | MAE en la prueba |
|---|---|
| ninguna | 36,80 s |
| global | 36,40 s |
| por línea | 36,33 s |
| por línea y hora | 36,33 s |
| por línea y parada objetivo | 27,48 s |
| por versión del horario, línea, parada y parada objetivo | 26,58 s |

- **La línea sola apenas aporta:** 0,07 s sobre la corrección global. Su efecto
  es pequeño (la media por línea va de −13,6 a +10,5 s) aunque estable entre
  periodos: la correlación ponderada de las medias por línea entre
  entrenamiento y prueba es de 0,864.
- **El tramo sí:** el horario se equivoca de forma fija entre ciertas paradas,
  y siempre hacia el mismo lado. Es el «sesgo estático» de la bitácora 032.

La variable que entra al modelo, `tramo_sesgo_s`, no congela el entrenamiento.
Usa todo lo que acabó el tramo antes de la primera observación de cada día, con
la versión del horario en la clave. Como tercer baseline (`persistencia_tramo`
en `metrics/features.json`, commit de esta entrada):

| baseline | MAE | RMSE |
|---|---|---|
| horario (retraso 0) | 144,54 s | 200,73 s |
| persistencia | 36,80 s | 68,29 s |
| **persistencia + sesgo del tramo** | **26,48 s** | **53,35 s** |

- Sin la versión del horario en la clave, el mismo cálculo da 26,96 s.
- Con soporte mínimo de 2 viajes cubre el 99,8 % de la prueba.
- La única línea de la prueba sin entrenamiento, la 8 (314 filas), no tiene
  historia y queda igual que la persistencia: 31,54 s.

## Cómo se midió

```bash
PYTHONIOENCODING=utf-8 uv run python -m project.analysis.medir_sesgo_tramo
uv run dvc repro features      # metrics/features.json → baselines_test.persistencia_tramo
```

- **El instrumento mintió dos veces antes de dar estas cifras.**
  - Con una sola clave, `groupby` devuelve un índice simple. Reindexado con un
    `MultiIndex` de un nivel, no casaba ninguna fila: «por línea» salía igual
    que la corrección global. Corregido en el medidor.
  - Agrupar por la hora con decimales hacía de cada fila un grupo: daba 36,77 s
    «por línea y hora». Se agrupa por la hora entera.
- **La variante sin fuga se midió fuera del pipeline y se reprodujo dentro.**
  Con todo lo anterior al día da 26,96 s sin versión del horario y 26,48 s con
  ella. `dvc repro features` reproduce 26,48 s.
- **La frontera del día la guarda
  `test_el_sesgo_del_tramo_solo_ve_lo_acabado_antes_del_dia`.** El nocturno de
  la víspera acaba el tramo ya dentro del día, y un corte por fecha lo contaba.
  Mutantes 096-100.

## Por qué importa

- **El listón del tráfico es 26,5 s, no 36,8.** Un modelo que bata la
  persistencia lo hará sobre todo por aprender el sesgo fijo del horario, que
  sale del GTFS y de la historia, no del tráfico. La aportación de la congestión
  aguas abajo solo se demuestra contra el tercer baseline.
- **Sesgo y congestión comparten tramo.** La flota como sensor
  (`tramo_ganado_*`) correlacionaba +0,45 con el residuo, y +0,07 sin el sesgo
  (bitácora 032). Con el sesgo como variable separada, el modelo puede
  repartirlos en vez de confundirlos.
- **`linea` entra, pero no por lo que aporta sola** (ADR-019). Es barata,
  estable y deja al árbol cruzarla. Si el modelo sin ella no se distingue, sale.

## Qué se hizo / qué queda abierto

Hecho:

- `features.categorias_linea` y `features.matriz`, con las categorías de
  `linea` fijadas con el entrenamiento.
- `_sesgo_tramo`, con `tramo_sesgo_s` y `tramo_sesgo_soporte` en
  `variables()`, y `persistencia_tramo` en los baselines.
- ADR-019, el medidor `analysis/medir_sesgo_tramo.py` y los mutantes 096-100.

Abierto:

- El primer día de una versión nueva del horario el sesgo es nulo. Hay que
  medir cuántos días tarda en estabilizarse: el 19-09-2026 entró el 14/09.
- Si el sesgo deriva dentro de una versión, una ventana móvil puede ganar a la
  mediana acumulada.
- El ablativo del modelo con y sin `linea`, cuando exista `train.py`.

## Para la memoria

> Se descompuso el error del predictor de persistencia en la prueba según el
> nivel al que se agrupa su corrección. Restar la mediana del error por línea,
> estimada en el periodo de entrenamiento, apenas modifica el error absoluto
> medio (de 36,40 a 36,33 segundos frente a una corrección global). Hacerlo por
> tramo entre paradas consecutivas lo reduce a 27,5 segundos. Si además el
> tramo se distingue por la versión del horario y la corrección se actualiza con
> todo lo observado antes de cada jornada, baja a 26,5 segundos. Es una
> reducción del 28 % que no procede del tráfico: el horario publicado asigna a
> ciertos tramos un tiempo de recorrido que se incumple de forma sistemática y
> siempre en el mismo sentido. Por ello se adoptó como tercer modelo de
> referencia la persistencia corregida con este sesgo histórico del tramo. La
> contribución de la congestión se evalúa frente a él, y no frente a la
> persistencia simple.
