---
id: 036
titulo: Todas las líneas etiquetadas entran en la muestra; con 5 días de prueba, 24 tienen soporte para una cifra propia y, con 100-299 viajes, no se distingue una mejora de menos de 1-2 s, ni de menos de 6 s si el modelo se aleja de la persistencia
fecha: 2026-09-30
tipo: medicion
capa: pipeline
capitulo: metodologia
impacto: alto
estado: aceptado
evidencia: uv run python -m project.analysis.medir_rutas lineas; uv run python -m project.analysis.medir_soporte
trampa: —
---

## Qué se observó

**Cuánto de cada línea llega a la etiqueta.** Posiciones en tramos asignados a
un viaje programado, sobre las posiciones de la línea en días no excluidos:

| línea | posiciones válidas | en viajes asignados |
|---|---|---|
| 96, 98E, 100, 8 | 78.387 | 0 % (sin trazado u horario en el GTFS) |
| 73 | 15.396 | 14,3 % |
| 25 | 206.710 | 17,7 % |
| 63 | 35.823 | 29,0 % |
| 24 | 140.297 | 46,4 % |
| 14 | 839 | 57,1 % |
| las otras 38 | | 70,0 - 92,4 % |

**Excluir las tres de menos del 30 % no cambia casi nada.** Son 10.023 filas, el
0,67 % de la tabla. Sin ellas, la persistencia pasa de 37,62 a 37,54 s de MAE en
la prueba. Y lo que sí se etiqueta de ellas no es más dudoso: el margen del
viaje asignado sobre el segundo candidato, en su percentil 10, es de 449 s en la
25 y 534 s en la 63, frente a 372 s de mediana en las demás. En la 73, con solo
30 viajes asignados, es de 273 s: por debajo de la mediana, como otras 7 de las
31 líneas con las que se compara.

**Qué se distingue con cada soporte.** Mediana, entre líneas, del semiancho del
intervalo del 95 %, remuestreando viajes:

| viajes de la línea en la prueba | líneas | del MAE de la persistencia | de la diferencia con un predictor parecido | con uno muy distinto |
|---|---|---|---|---|
| menos de 100 | 17 | 3,21 s | 2,70 s | 16,60 s |
| de 100 a 299 | 7 | 1,57 s | 0,86 s | 6,32 s |
| 300 o más | 19 | 1,02 s | 0,58 s | 3,75 s |

El predictor «parecido» es la persistencia encogida un 10 %; el «muy distinto»,
la persistencia encogida a la mitad. Son sustitutos de un modelo que aún no
existe.

**Los grupos**, con 100 viajes en 3 días de prueba y 100 de entrenamiento:

| grupo | líneas | filas de prueba | MAE de la persistencia |
|---|---|---|---|
| cifra propia | 24 | 252.306 | 37,56 s |
| poco soporte | 9 (25, 28, 4, 40, 6, 62, 70, 71, 98) | 9.564 | 36,69 s |
| sin entrenamiento | 10 (10, 11, 14, 59, 60, 63, 64, 73, 9, C1) | 7.623 | 40,96 s |

## Cómo se midió

```bash
uv run python -m project.analysis.medir_rutas lineas    # columna pos_asignadas
uv run python -m project.analysis.medir_soporte         # soporte e intervalos por línea
uv run dvc repro features                               # metrics/features.json
```

El indicador sale de `data/interim/viajes`: suma de `posiciones` con
`motivo = 'asignado'` entre la suma con `motivo <> 'excluido'`. Los intervalos
remuestrean viajes enteros 1.000 veces con semilla fija. Los grupos están en
`metrics/features.json`, en `baselines_test.por_grupo`.

El efecto de excluir y los márgenes de asignación se midieron una vez, sin
medidor propio:

```python
import duckdb, pandas as pd
from project.config import settings
te = pd.read_parquet(settings.processed_dir / "test.parquet")
sin = te[~te["linea"].isin(["25", "63", "73"])]
(sin["retraso_s"] - sin["retraso_siguiente_parada_s"]).abs().mean()   # 37,54
v = (settings.interim_dir / "viajes" / "*" / "*.parquet").as_posix()
duckdb.sql(f"""select linea, quantile_cont(margen_s, 0.1) from
    read_parquet('{v}', hive_partitioning=false, union_by_name=true)
    where motivo = 'asignado' group by 1""")
# 25: 449 · 63: 534 · 73: 273 (30 viajes) · mediana de las 31 líneas con 100
# viajes asignados o más, sin la 24, la 25, la 63 y la 73: 372
```

**El instrumento se corrigió dos veces antes de la cifra.** La primera
justificación del umbral de 100 viajes usaba solo el intervalo del MAE, y daba
por hecho que el de una diferencia sobre los mismos viajes sería siempre menor.
Medido, solo lo es si el predictor se parece a la persistencia: con uno muy
distinto es varias veces mayor.

Y el primer predictor «muy distinto» mentía. Era la media de la persistencia y
el retraso medio de la línea en los 5 min anteriores, que falta donde no ha
pasado otro viaje de la línea; los huecos se rellenaban con la propia
persistencia. En las líneas de menos de 100 viajes faltaba en el 89 % de las
filas (mediana por línea): ahí la diferencia era cero y el semiancho salía en
6,91 s, menor que en la banda siguiente (9,67 s). Lo encontró la revisión
independiente de la rama. Con un predictor definido en todas las filas son
16,60 s, y la columna vuelve a decrecer con el soporte
(`tests/test_medir_soporte.py`).

## Por qué importa

- **Acotar a corredores tiraba tres cuartas partes del dato.** Los cinco
  propuestos en agosto (93, C3, 98E, 99, 81) son el 22,8 % de las filas, y la 98E
  no aporta ninguna: no tiene trazado en el GTFS.
- **Excluir líneas por su etiqueta costaba más de lo que daba.** Movía el
  resultado 0,08 s y obligaba a defender un umbral puesto después de ver los
  datos y un sesgo a favor de la hipótesis: la 25 es también la línea peor
  cubierta por sensores (27 %). La regla de soporte ya deja esas líneas fuera de
  las cifras por línea.
- **Una cifra por línea con pocos viajes no distingue nada.** En la 98, con 16
  viajes, el intervalo del MAE es de ±6,2 s sobre 44,5.
- **El tráfico no se verá línea a línea.** Con 100 a 299 viajes no se distingue
  una mejora de menos de 1-2 s si el modelo se parece a la persistencia, ni de
  menos de unos 6 s si se aleja de ella. Lo que la flota detecta por encima del
  sesgo del horario es pequeño (bitácora 032). Hay que juzgarlo en el conjunto y
  en el estrato con sensor.
- **Las diez líneas sin entrenamiento son un resultado aparte:** miden cómo
  generaliza el modelo a líneas que no ha visto.

## Qué se hizo / qué queda abierto

Hecho: `features.soporte_por_linea`, los baselines por grupo, los dos medidores,
los mutantes 088 y 089 y el ADR-018, con el criterio de mejora.

Abierto:

- El estrato de sensores: falta medir la cobertura por tramo entre paradas.
- Repetirlo todo con la captura posterior al 18/09 y el corte rehecho. De las
  nueve líneas de «poco soporte», cuatro se quedan cerca del umbral (70, 28, 4 y
  40, con 87-98 viajes) y pasarían con pocos días más; la 25 y la 62 necesitan
  el doble, y la 6, la 71 y la 98 tienen entre 2 y 16 viajes.
- El intervalo remuestrea viajes y da por buenos los días de la prueba: no
  recoge lo que cambia de un día a otro, así que es un suelo. Con 5 días no se
  puede medir esa variación; está en los pendientes de `docs/07_decisiones.md`.
- Cómo se codifica `linea` para que el modelo prediga líneas no vistas.
- El intervalo de la diferencia con el modelo de verdad, cuando exista.

## Para la memoria

> El conjunto de datos comprende todas las líneas para las que existe trazado y
> horario publicados. La proporción de posiciones que el procedimiento logra
> asociar a un viaje programado se sitúa entre el 57 % y el 92 % en 39 de ellas y
> en el 46 % en una más; tres líneas quedan por debajo del 30 %. Se valoró
> excluir estas últimas y se descartó: representan el 0,67 % de las
> observaciones, su exclusión modifica el error de referencia en 0,08 segundos y
> las asignaciones que sí se obtienen no son más ambiguas que en el resto en
> las dos líneas con volumen suficiente para medirlo. La proporción se informa por línea como limitación. Para presentar
> resultados desagregados se exige un mínimo de 100 viajes en tres días distintos
> del periodo de prueba y otros 100 en el de entrenamiento, requisito que cumplen
> 24 de las 43 líneas; las restantes se informan agrupadas, distinguiendo las que
> el modelo no ha visto durante el entrenamiento. Toda comparación entre modelos
> se expresa como diferencia de error sobre los mismos viajes, con un intervalo
> de confianza del 95 % obtenido remuestreando viajes completos, y se considera
> que existe mejora cuando el intervalo no contiene el cero. Con el soporte
> disponible, una diferencia inferior a uno o dos segundos no es distinguible
> línea a línea, y el umbral sube a unos seis segundos si el modelo se aparta de
> la persistencia, por lo que la contribución de las variables de tráfico se evalúa
> sobre el conjunto y sobre el subconjunto de tramos con sensor.
