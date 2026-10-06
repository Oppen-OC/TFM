---
id: 045
titulo: La mejora de la v2 aguanta remuestreando días (−2,09 s, IC [−2,25, −1,95]) y con cinco semillas (−2,04 a −2,09 s); la flota como sensor aporta 0,11 s y las ventanas de línea no se distinguen del ruido
fecha: 2026-10-06
tipo: medicion
capa: pipeline
capitulo: resultados
impacto: alto
estado: aceptado
evidencia: uv run dvc repro evaluate (metrics/eval.json, modelo_menos_remuestreando_dias); uv run python -m project.analysis.semillas_v2 (auditoria/resultados/semillas_v2.json); uv run python -m project.analysis.robustez_v2 (auditoria/resultados/robustez_v2.json)
trampa: —
---

## Qué se observó

Son las pruebas de robustez que la bitácora 043 dejó abiertas, sobre el modelo
v2 sin cambios: residuo con pérdida absoluta.

**Intervalo remuestreando días** (14 días de prueba), frente a
`persistencia_tramo`:

| estrato | por viajes | por días |
|---|---|---|
| global | [−2,14, −2,04] | **[−2,25, −1,95]** |
| intervalo ≤ 8 min | [−2,33, −2,11] | [−2,44, −2,08] |
| 8-15 min | [−2,08, −1,93] | [−2,18, −1,87] |
| 15-30 min | [−2,17, −1,95] | [−2,40, −1,82] |
| > 30 min | [−2,35, −2,08] | [−2,34, −2,10] |
| soporte propio | [−2,18, −2,08] | [−2,29, −1,99] |
| poco soporte | [−1,25, −0,70] | [−1,46, −0,51] |

El intervalo por días es entre dos y tres veces más ancho que el de viajes, y
**no contiene el cero en ningún estrato**. La línea sin entrenamiento circula
un solo día, así que su intervalo por días no existe.

**Semillas.** El brazo fijado, entrenado entero con otras cuatro semillas
(`subsample` y `colsample_bytree` en 0,8):

| semilla | árboles | MAE | frente a `persistencia_tramo` | por días |
|---|---|---|---|---|
| 0 | 1.146 | 24,44 s | −2,04 | [−2,20, −1,91] |
| 1 | 1.345 | 24,42 s | −2,07 | [−2,23, −1,93] |
| 2 | 1.194 | 24,44 s | −2,04 | [−2,20, −1,91] |
| 3 | 1.429 | 24,41 s | −2,07 | [−2,23, −1,93] |
| 42 (`eval.json`) | 1.517 | 24,39 s | −2,09 | [−2,25, −1,95] |

La semilla mueve la diferencia unos 0,05 s.

**Ablación en la validación** (semana del 14-20/09), sobre el brazo elegido y
sobre los mismos viajes:

| modelo | frente al completo |
|---|---|
| sin la flota (`tramo_ganado_*`, `tramo_soporte_*`) | +0,11 s [0,09, 0,13] |
| sin la flota ni las ventanas de línea | +0,01 s [−0,01, 0,03] |

**Líneas no vistas.** En las 10 líneas de la validación que el ajuste (agosto)
no tiene (678 viajes), el modelo mejora a `persistencia_tramo` en −1,99 s
[−2,52, −1,47]. Por la regla fijada antes de ejecutarlo (`4e5e94b`), `predict`
**no** lleva respaldo.

## Cómo se midió

```bash
uv run dvc repro evaluate                          # metrics/eval.json
uv run python -m project.analysis.semillas_v2      # 4 semillas, evalúa la prueba
uv run python -m project.analysis.robustez_v2      # solo validación
```

El intervalo por días aplica `evaluate.diferencia` con el día de servicio como
unidad, en lugar del viaje. `train` importa `evaluate.diferencia`, así que
cambiar `evaluate.py` reentrena: el modelo salió con las mismas cifras, y su
`model.pkl` cambia de hash porque guarda el id del run de MLflow.

## Por qué importa

- **La cifra resiste las dos objeciones de la bitácora 043.** Lo que cambia de
  un día a otro ensancha el intervalo pero no lo acerca al cero. La semilla
  mueve la diferencia cuarenta veces menos que el efecto.
- **La flota como sensor aporta, pero poco.** Son 0,11 s de los 2,09: unas dos
  veces el ruido de la semilla. Quitar también las ventanas de línea no empeora
  más, así que sus décimas son del orden del ruido entre ajustes. El intervalo
  por viajes no recoge esa variabilidad. Para la pregunta de investigación, la
  flota es una variable menor; el tráfico de la capa 192 tendrá que medirse
  contra un listón que ya incluye esa décima.
- **Las líneas no vistas no son un problema general.** En la validación, el
  modelo las predice mejor que el listón. La línea 8 de la prueba (+17 s, 22
  viajes en un día) queda como anécdota declarada, sin corrección a posteriori.

## Qué se hizo / qué queda abierto

Hecho:
- El intervalo por días en `evaluate` (mutante 113), y los scripts
  `semillas_v2` y `robustez_v2`.
- El pendiente del ADR-018 queda resuelto: hay mejora si ninguno de los dos
  intervalos contiene el cero.

Abierto (bitácora 043):
- La disponibilidad de `t_obs`: la cifra sigue siendo un techo.
- Confirmar la v2 congelada en días posteriores al 04/10.
- La sensibilidad sin las líneas 13 y 35 en la semana 2.
- La capa 192.
- La dependencia `train` → `evaluate.py`, que obliga a reentrenar cuando solo
  cambia la evaluación.

## Para la memoria

> La mejora del modelo sobre la persistencia corregida con el sesgo del
> horario se sostiene frente a dos fuentes de incertidumbre que el intervalo
> por viajes no recoge. Remuestreando los 14 días de la prueba, la diferencia
> es de 2,09 s (IC 95 %: 1,95-2,25 s), y el intervalo no contiene el cero en
> ninguna banda de intervalo programado. Entrenado con cinco semillas
> distintas, el modelo da diferencias entre 2,04 y 2,09 s. En la validación,
> retirar las variables de la flota como sensor del tramo siguiente aumenta el
> error en 0,11 s (IC 95 %: 0,09-0,13 s), de modo que su aportación es
> pequeña frente a la del planteamiento del modelo. Tampoco empeora en las
> líneas ausentes del entrenamiento: en las diez que solo aparecen en la
> validación mejora a la referencia en 1,99 s.
