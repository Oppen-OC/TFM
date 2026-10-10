---
id: 048
titulo: En la validación, la capa 192 mejora la predicción unas décimas de segundo en conjunto y de 1 a 1,5 s donde veía congestión al predecir, que es solo el 2-4 % de las filas; el 82 % de los recorridos tiene sensor en más de tres cuartos
fecha: 2026-10-10
tipo: medicion
capa: pipeline
capitulo: resultados
impacto: alto
estado: aceptado
evidencia: uv run python -m project.analysis.trafico_validacion (auditoria/resultados/trafico_validacion.json); los huecos de la 192 y la antigüedad del sondeo, con el código de «Cómo se midió»
trampa: —
---

## Qué se observó

Fase 1 del ADR-024. Se toma el corte que tendrá la fase 2:
- ajuste hasta el 27/09;
- validación del 28/09 al 04/10, de lunes a domingo.

Para cada horizonte se ajusta el mismo modelo (ADR-021) con y sin las tres
variables de la 192 y se comparan sobre las mismas filas de la población. Las
diferencias son el MAE con tráfico menos el MAE sin él.

**Cobertura del recorrido.**
- `tramos_ruta` da 3.558 intervalos de trazado bajo 365 de los 410 tramos.
- Los 194 trazados de las dos versiones del GTFS tienen algún tramo.
- Con *h* = 5, en la validación:
  - el 81,7 % de las filas tiene más del 75 % del recorrido *i* → *i* + *h*
    cubierto;
  - el 6,7 % no tiene ninguno;
  - el 11 % restante cae en las bandas intermedias.
- Con *h* = 10, más del 75 % cubierto llega al 84,1 % de las filas.

**En conjunto, la aportación son décimas de segundo:**

| *h* | filas (validación) | MAE sin tráfico | diferencia | IC por viajes | IC por días |
|---|---|---|---|---|---|
| 2 | 329.113 | 32,61 s | −0,08 | [−0,10, −0,07] | [−0,11, −0,05] |
| 3 | 311.817 | 41,04 s | −0,10 | [−0,12, −0,07] | [−0,15, −0,06] |
| 5 | 275.835 | 55,49 s | −0,06 | [−0,11, −0,03] | [−0,12, −0,00] |
| 10 | 189.339 | 86,19 s | −0,26 | [−0,36, −0,18] | [−0,55, −0,01] |

**En el estrato con más del 75 % cubierto**, la primaria de la fase 2:

| *h* | filas | diferencia | IC por viajes | IC por días |
|---|---|---|---|---|
| 5 | 225.235 | −0,07 | [−0,12, −0,03] | [−0,14, 0,00] |
| 10 | 159.201 | −0,33 | [−0,43, −0,24] | [−0,68, −0,05] |

Las bandas intermedias no muestran nada: con *h* = 5, de −0,14 a +0,02, y
todos los intervalos por viajes contienen el cero.

**La señal está donde la capa veía congestión al predecir**
(`trafico_congestion_frac > 0`). Son pocas filas:
- en el ajuste, del 1,2 % (*h* = 2) al 2,7 % (*h* = 10);
- en la validación, del 1,9 al 4,4 %.

| *h* | filas | MAE sin tráfico | diferencia | relativa | IC por días |
|---|---|---|---|---|---|
| 2 | 6.272 | 51,66 s | −1,30 | −2,5 % | [−2,10, −0,66] |
| 3 | 7.296 | 61,37 s | −1,50 | −2,4 % | [−2,68, −0,30] |
| 5 | 8.511 | 77,81 s | −0,99 | −1,3 % | [−2,46, 0,72] |
| 10 | 8.373 | 111,67 s | −1,28 | −1,1 % | [−4,41, 1,22] |

**Parte de la mejora global no es congestión.** Las filas sin ningún sensor en
el recorrido también mejoran: −0,05 s con *h* = 2 (IC por días [−0,09, −0,02])
y de −0,04 a −0,11 s en el resto, con el intervalo por días conteniendo el cero. Las filas
con la capa en fluido mejoran de −0,04 a −0,06 s con *h* ≤ 5. Esas filas
reciben `trafico_edad_s` y `trafico_cubierto_m = 0`, y el modelo con tráfico
tiene otros árboles.

**Huecos de la 192.**
- Del 15/08 al 04/10 hay 15.046 sondeos, con 5 min de mediana entre uno y otro.
- Hay 37 huecos de más de 15 min, que suman 159,0 h. Los mayores de 1 h:
  - 18/08: 14,7 h;
  - 21/08: 10,6 h;
  - 10-14/09: 103,7 h (bitácora 021);
  - 22/09: 6,4 h;
  - 23/09: 13,7 h.
- Los del 22 y el 23/09 no son de la captura entera: la EMT siguió llegando,
  con 735 y 1.580 sondeos dentro de cada hueco. Esos dos días, el 37,7 % y el
  73,0 % de las filas no tienen un sondeo de la 192 de menos de 15 min.
- En toda la tabla (*h* = 5), el 3,46 % de las filas está así. La antigüedad
  del sondeo vigente es de 145 s en la mediana y de 297 s en el p95.

## Cómo se midió

```bash
uv run python -m project.analysis.trafico_validacion   # ~2 h, 8 ajustes
```

Hay dos ejecuciones con el mismo resultado global en los cuatro horizontes: el
ajuste es determinista. La segunda añadió el estrato por estado observado.

Los huecos y la antigüedad:

```python
import pandas as pd
from project import features
from project.config import settings
e = pd.read_parquet(settings.curated_dir / "source=trafico_estado", columns=["ts_ingest_utc"])
t = pd.Series(e["ts_ingest_utc"].unique()).sort_values()
t = t[t < pd.Timestamp("2026-10-05", tz="UTC")]
dt = t.diff(); g = dt > pd.Timedelta(minutes=15)
print(g.sum(), dt[g].sum())                                     # 37 huecos, 159,0 h
r = features.salidas(5)
tab = pd.concat([pd.read_parquet(r["tabla"] / f) for f in ("train.parquet", "test.parquet")])
tab = tab[(tab["fecha_servicio"] < "2026-10-05") & features.poblacion(tab)]
viejo = tab["trafico_edad_s"].isna() | (tab["trafico_edad_s"] > 900)
print(viejo.mean())                                             # 3,46 %
```

**Límite del instrumento.** La parada temprana usa la misma validación en la
que se mide, así que los dos MAE salen algo optimistas. La comparación sirve de
diagnóstico, no de resultado.

## Por qué importa

- Responde, provisionalmente, a la primera mitad de la pregunta del TFM. La
  congestión aguas abajo explica muy poco del retraso medio porque casi nunca
  se observa: la 192 marca congestión en el recorrido inmediato del bus en el
  2-4 % de las predicciones. Cuando la marca, el modelo mejora entre 1 y 1,5 s.
- La primaria prerregistrada (*h* = 5, estrato con sensor) va justa: con una
  semana, el intervalo por días toca el cero. Con dos semanas de prueba y la
  congestión de octubre puede salir distinguible, pero la magnitud sería del
  orden de 0,1 s sobre 56 s.
- La mejora en las filas sin sensor es el control. Sin él, una diferencia
  global de −0,08 s se leería entera como efecto del tráfico.

## Qué se hizo / qué queda abierto

- **Enmienda al ADR-024**, antes de traer la prueba:
  - estrato con sensor = más del 75 % del recorrido cubierto;
  - variables congeladas;
  - secundario con congestión observada;
  - control sin sensor.
- **Abierto.** Por qué la 192 falta el 22 y el 23/09 con la EMT llegando: si
  es la fuente o el colector. No es recuperable. La fase 2 tiene que medir
  sus propios huecos del 06 al 19/10.

## Para la memoria

> Antes de abrir la prueba nueva se midió en la validación lo que aporta el
> estado del tráfico municipal (capa 192) en el recorrido que le queda al
> autobús. La cobertura no es el límite: el 82 % de las predicciones a cinco
> paradas tiene sensor en más de tres cuartos de su recorrido. El límite es que
> la congestión casi nunca aparece. La capa la marca en el 2-4 % de las
> predicciones, y en conjunto el modelo con tráfico mejora al mismo modelo sin
> él entre 0,06 y 0,26 s de MAE, un 0,1-0,3 %. La mejora se concentra donde
> la capa veía congestión al predecir: de 1,0 a 1,5 s, un 1-2,5 %, distinguible
> remuestreando días con dos y tres paradas de horizonte. Las filas sin ningún
> sensor también mejoran unas centésimas, así que esa parte de la diferencia
> global no puede atribuirse a la congestión. Con estas cifras se fijaron, antes
> de ver la prueba, el estrato con sensor, las variables y un estrato secundario
> con congestión observada.
