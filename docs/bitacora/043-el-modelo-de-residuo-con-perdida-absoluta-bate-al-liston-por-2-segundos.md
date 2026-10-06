---
id: 043
titulo: El modelo v2, residuo sobre la persistencia con pérdida absoluta, bate a la persistencia más el sesgo del tramo por 2,09 s de MAE (IC por viajes [2,04, 2,14]) en todas las bandas de intervalo; es la segunda evaluación de la prueba y un techo, no una cifra en tiempo real
fecha: 2026-10-06
tipo: medicion
capa: pipeline
capitulo: resultados
impacto: alto
estado: abierto
evidencia: uv run python -m project.analysis.elegir_brazo (auditoria/resultados/elegir_brazo_v2.json); uv run dvc repro evaluate (metrics/eval.json; run de MLflow 32a8d78ffdd0467189e3725a3307ada3)
trampa: —
---

## Qué se observó

La v1 empataba con el listón (bitácora 041). La v2 sigue el protocolo del
ADR-021, commiteado antes de entrenar (`f777259`):
- cuatro brazos ajustados con agosto;
- parada temprana por MAE en la semana del 14 al 20/09, de lunes a domingo;
- sin `tramo_sesgo_soporte`.

**Validación** (423.647 filas; `persistencia_tramo`: 27,67 s):

| brazo | árboles | MAE | frente a `persistencia_tramo` |
|---|---|---|---|
| nivel + cuadrática | 276 | 26,97 s | −0,71 [−0,96, −0,40] |
| nivel + absoluta | 863 | 26,36 s | −1,32 [−1,56, −1,01] |
| residuo + cuadrática | 204 | 26,11 s | −1,57 [−1,64, −1,48] |
| **residuo + absoluta** | 1.517 | **25,43 s** | **−2,24 [−2,32, −2,16]** |

Ningún brazo más simple empata con el mejor: frente a él, sus intervalos van
de [+0,64, +0,71] a [+1,30, +1,83]. Por la regla del ADR-021 gana residuo +
absoluta. Sin `linea` el MAE empeora +0,17 s [0,15, 0,19], así que `linea` se
queda. El brazo se fijó en `params.yaml` y se commiteó antes de evaluar la
prueba (`9ed47cf`).

**Prueba** (21/09-04/10, 840.022 filas, 40.032 viajes):

| | MAE | RMSE |
|---|---|---|
| persistencia | 36,80 s | 68,29 s |
| persistencia + sesgo del tramo | 26,48 s | 53,35 s |
| v1 (bitácora 041) | 26,51 s | 50,42 s |
| **v2** | **24,39 s** | **44,00 s** |

Diferencias de la v2, con su intervalo remuestreando viajes:
- frente a `persistencia_tramo`: **−2,09 s [−2,14, −2,04]** en MAE y −9,35 s
  [−9,93, −8,85] en RMSE;
- frente a la persistencia: −12,41 s [−12,49, −12,31].

| estrato | viajes | MAE frente a `persistencia_tramo` |
|---|---|---|
| intervalo ≤ 8 min | 9.321 | −2,22 [−2,33, −2,11] |
| 8-15 min | 19.846 | −2,01 [−2,08, −1,93] |
| 15-30 min | 8.270 | −2,06 [−2,17, −1,95] |
| > 30 min | 2.595 | −2,22 [−2,35, −2,08] |
| soporte propio | 38.891 | −2,13 [−2,18, −2,08] |
| poco soporte | 1.119 | −0,97 [−1,25, −0,70] |
| sin entrenamiento (línea 8) | 22 | +17,41 [12,14, 22,91] |

Entre las 26 líneas con soporte propio, 24 mejoran, ninguna empeora y 2 no se
distinguen: la 7 (−0,43 [−1,21, 0,29]) y la 24 (−0,33 [−0,76, 0,07]). Los
estratos y las líneas son **descriptivos**, sin corrección por comparaciones
múltiples. La primaria es una sola: el global.

## Cómo se midió

```bash
uv run python -m project.analysis.elegir_brazo   # brazos y ablación, solo validación
uv run dvc repro                                 # entrena el brazo fijado y evalúa la prueba
cat metrics/eval.json
```

El intervalo es un bootstrap percentil de 1.000 réplicas que remuestrea viajes
(`evaluate.diferencia`). El orden de los commits
(`f777259` → `140cc5a` → `9ed47cf` → `071f950`) muestra que el protocolo y la
elección son anteriores a esta evaluación. El experimento `elegir_brazo_v2` de
MLflow tiene exactamente los 5 runs declarados: 4 brazos y la ablación.

## Por qué importa

- **Se pasa del empate a una mejora.** Lo que separaba a la v1 del listón era
  el planteamiento: aprender el residuo evita que el árbol reconstruya a trozos
  la identidad `retraso_s → objetivo`, y la pérdida absoluta apunta a la
  mediana, que es lo que premia el MAE. Del paso v1 → v2 no se puede atribuir
  la mejora a un solo cambio: cambian seis cosas a la vez (pérdida, objetivo,
  parada, validación, tope y una variable menos).
- **La mejora no se concentra en las bandas contaminadas por el pliegue.** Es
  la misma, −2,22 s, en la banda de más de 30 min (bitácora 038) que en la de
  8 min o menos. Eso no demuestra que el modelo no aprenda nada del pliegue,
  pero el pliegue no explica la mejora.
- **No se sabe qué variables la producen.** En particular, no se puede
  atribuir a la flota como sensor sin una ablación sobre el brazo elegido. Y
  la capa 192 de tráfico no está en el modelo: la cifra todavía no responde a
  la pregunta de investigación. Es el listón del pilar 2.

## Qué se hizo / qué queda abierto

Hecho:
- `train.residuo`, la parada por MAE, el selector `analysis/elegir_brazo.py` y
  `tramo_sesgo_soporte` fuera de las variables.
- Mutantes 110-112.

Abierto. Lo revisó el `tribunal`; cada punto se comprobó contra el repo:

- **Es la segunda evaluación de la prueba, no la primera.** La v1 se evaluó en
  ella, y el espacio de brazos, la retirada del soporte y la clave del listón
  se decidieron después de verla (ADR-021, matices). La confirmación limpia es
  evaluar la v2 congelada en días posteriores al 04/10.
- **La validación no es del todo como la prueba.**
  - El 8,8 % de sus filas no tiene sesgo del tramo, frente al 0,18 % de la
    prueba: el 14/09 es el primer día del horario `19-09-2026`.
  - Diez líneas solo aparecen en ella.
  - Que anticipara la prueba (−2,24 frente a −2,09) es una sola observación;
    con la v1 no lo hizo.
- **Es un techo, no una cifra en tiempo real.** La disponibilidad de `t_obs`
  (bitácora 041) sigue pendiente: las ventanas dan por conocido en `t` lo que
  llega con un sondeo de retraso más la latencia. Tampoco se ha medido la
  antelación: el horizonte es una parada.
- **Intervalo por días y semillas.** El intervalo por viajes es un suelo
  (ADR-018). Falta el remuestreo por días, con 14 en la prueba, y repetir con
  3-5 semillas, informando el rango.
- **La línea sin entrenamiento empeora 17 s** (22 viajes de un solo día; la
  cifra es anecdótica). La línea entra con `linea` nula y el modelo de
  residuo, en vez de dejarla como dato faltante inocuo, le aplica una
  corrección sesgada. No hay script en el repo que lo mida. El respaldo para
  líneas no vistas va en `predict.predecir`, no en `services/`, y se justifica
  con una línea retenida en la validación, no con la prueba.
- **Etiquetas dudosas.** En la semana 2, las líneas 13 y 35 tienen horario
  discutido (bitácora 042). Falta una sensibilidad sin ellas, declarada como
  tal, no como exclusión.
- **Regla de `linea_sale`** (`analysis/elegir_brazo.py`) sin test ni mutante.

## Para la memoria

> Siguiendo un protocolo fijado antes de entrenar, se compararon en una semana
> completa de validación cuatro configuraciones del modelo: función de pérdida
> cuadrática o absoluta, y objetivo en nivel o como desviación respecto a la
> persistencia. La elegida, la desviación con pérdida absoluta, reduce en la
> validación el error absoluto medio en 2,24 s frente a la persistencia
> corregida con el sesgo del horario por tramo. En el periodo de prueba, en el
> que ya se había evaluado un primer modelo, el error absoluto medio en la
> parada siguiente es de 24,4 s frente a 26,5 s de esa referencia: una mejora
> de 2,09 s (IC 95 % remuestreando viajes: 2,04-2,14 s). Se mantiene en todas
> las bandas de intervalo programado, incluida la de más de 30 minutos, cuya
> etiqueta está libre del error de asignación, y aparece en 24 de las 26 líneas
> con soporte suficiente. La cifra es una cota superior de lo alcanzable en
> tiempo real: las variables suponen disponible en cada instante información
> que llega con algún retraso. El modelo aún no incorpora el estado del
> tráfico, y esta cifra es el listón frente al que se mide su aportación.
