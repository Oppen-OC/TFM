---
id: 032
titulo: La flota como sensor del tramo aguas abajo correlaciona +0,45 con lo que la persistencia no explica, pero casi todo es el sesgo estático del horario en cada tramo; sin él quedan +0,07, y sin el perfil diario +0,03
fecha: 2026-09-25
tipo: medicion
capa: pipeline
capitulo: resultados
impacto: alto
estado: abierto
evidencia: uv run dvc repro features && uv run python -m project.analysis.medir_flota
trampa: —
---

## Qué se observó

Fase 2, opción 1 (`docs/10_respuestas_tutor.md`, enfoque 2). Para la fila
(viaje, parada *i*, instante *t*), `tramo_ganado_{W}min` es la **mediana** del
retraso que ganaron **otros** viajes, de cualquier línea, al recorrer el mismo
tramo: el par (parada *i*, parada objetivo). Solo cuentan los que acabaron el
tramo en [*t* − W, *t*). `tramo_soporte_{W}min` es cuántos son; con menos de 2,
la variable es nula («no estimable» no es «cero»).

**Cobertura**, fracción de filas con la variable estimada:

| | W = 5 min | W = 15 min | de 8 a 21 h, W = 15 |
|---|---|---|---|
| entrenamiento | 3,8 % | 32,2 % | 31-38 % |
| prueba | 3,8 % | 36,2 % | 34-43 % |

Por línea, con W = 15 y más de 5.000 filas, va del 4 % (25 y 35) al 73 % (81).
El 66-74 % de las filas cae en paradas que sirven dos o más líneas.

**Señal**, Spearman con lo que la persistencia no explica (objetivo − retraso
actual):

| variable | entrenamiento | prueba |
|---|---|---|
| `tramo_ganado_15min` | **+0,454** | **+0,473** |
| `tramo_ganado_5min` | +0,336 | +0,389 |
| `bus_anterior_retraso_s` | +0,102 | +0,091 |
| `linea_retraso_15min` | +0,052 | +0,028 |
| `retraso_delta_s` | −0,020 | −0,021 |

**Casi toda es estática.** Descomponiendo `tramo_ganado_15min` por tramo:

| Spearman, con… | entrenamiento | prueba |
|---|---|---|
| la variable tal cual | +0,454 | +0,473 |
| la media de cada tramo quitada | **+0,068** | +0,097 |
| la media de cada tramo × hora quitada | **+0,030** | +0,001 |

Si el horario se queda corto en un tramo, todos los buses ganan retraso en él a
cualquier hora, y la flota lo «mide» sin medir tráfico. Es el sesgo estático
del horario. Por encima de él queda el perfil diario (+0,07) y, por encima de
este, la congestión no recurrente (+0,03).

## Cómo se midió

```bash
uv run dvc repro features
uv run python -m project.analysis.medir_flota
```

Las medias por tramo y por tramo × hora se calculan sobre el mismo conjunto: es
una descomposición, no una variable del modelo. Las celdas tramo × hora tienen
una mediana de 15 filas en entrenamiento y de 7 en prueba (p10 = 1 en ambos).
Con celdas tan pequeñas, quitar su media encoge la correlación por
construcción, así que el +0,001 de prueba no es fiable; el +0,030 de
entrenamiento es la cifra defendible.

El tramo es el par exacto de paradas (`stop_id`, `stop_objetivo_id`). En la
tabla, `stop_objetivo_id` es una clave, no una variable del modelo.

Tests: fuga (un tramo acabado en *t* o después no cuenta), mediana (un extremo
de 900 s no la mueve), soporte (un solo bus da nulo) y cruce de líneas (otra
línea con las mismas paradas cuenta). Mutantes 083-086.

## Por qué importa

- **Es el resultado central de la descomposición de varianza que pidió el
  tutor.** La mayor parte de lo que la flota «sabe» del tramo es sistemático:
  el horario de la EMT reparte mal el tiempo entre paradas. Lo que covaría
  entre vehículos en una ventana es pequeño.
- **Para el modelo: sin un control estático, la atribución es falsa.** Si
  `train.py` solo ve `tramo_ganado`, la importancia que le dé irá sobre todo al
  sesgo del horario, y se leería como «congestión». Hace falta el sesgo
  histórico del tramo como variable de control, calculado solo con días
  anteriores a la prueba, para que la ablación aísle lo que varía en el tiempo.
- La cobertura con W = 5 es baja (3,8 %): la flota solo mide un tramo con la
  frecuencia de paso, y en 5 minutos rara vez pasan dos buses.

## Qué se hizo / qué queda abierto

Hecho:

- `features._tramo_flota`, con las claves `incluir_flota`,
  `ventanas_flota_min` y `soporte_min` en `params.yaml`.
- `stop_objetivo_id` como clave en la tabla.
- 2 tests nuevos y los mutantes 083-086.
- El medidor `analysis/medir_flota.py`.

Abierto:

- El sesgo histórico del tramo como variable de control, sin fuga (solo días
  anteriores), en `features.py` o en `train.py`.
- Repetir la descomposición con la captura posterior al 18/09, con más días
  lectivos y celdas más grandes.
- La capa 192 aguas abajo (la siguiente variable), medida con la misma
  descomposición.
- Tramos por geometría y no por par de paradas, si hace falta más cobertura
  entre líneas que comparten viario sin compartir paradas.

## Para la memoria

> Se construyó una medida de congestión a partir de la propia flota: para cada
> paso por parada, la mediana del retraso que ganaron los demás autobuses, de
> cualquier línea, al recorrer el mismo tramo entre dos paradas en los quince
> minutos anteriores, exigiendo al menos dos vehículos. La medida está
> disponible en el 32-36 % de las observaciones y correlaciona 0,45 (rango de
> Spearman) con la parte del retraso que la persistencia no explica, frente a
> 0,10 o menos de las variables de la línea. Sin embargo, al descomponerla, la
> mayor parte de esa asociación corresponde a un sesgo estático del horario en
> cada tramo: descontada la media de cada tramo, la correlación baja a 0,07, y
> descontada también la media por hora, a 0,03. La congestión no recurrente
> que la flota detecta es, por tanto, una fracción pequeña de su señal, y su
> contribución debe medirse frente a un modelo que ya conozca el sesgo del
> horario en cada tramo.
