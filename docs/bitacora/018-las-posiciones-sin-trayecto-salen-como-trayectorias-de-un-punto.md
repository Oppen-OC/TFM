---
id: 018
titulo: Las posiciones sin trayecto no se emparejan con nada y salen como trayectorias de una sola posición, el 1 % de las trayectorias de un día
fecha: 2026-09-18
tipo: anomalia
capa: tracking
capitulo: calidad-dato
impacto: bajo
estado: abierto
evidencia: consulta DuckDB sobre curated/source=emt_buses (ver «Cómo se midió»)
trampa: —
---

## Qué se observó

La capa de la EMT publica algunas posiciones con `trayecto` nulo. En el curated
del colector (15/08-31/08, 17 días) son **1.834 de 5.163.031** posiciones
(0,036 %), repartidas en **31 líneas**.

`rastrear()` agrupa por `(linea, trayecto)` con `groupby` de pandas, que **descarta
las claves nulas**: esas filas nunca entran en el emparejamiento y cada una sale
como una trayectoria propia de una sola posición. El 27/08, sobre el curated del
colector: **82** posiciones sin trayecto, **82** trayectorias, las 82 de una
posición, de **7.658** trayectorias del día (**1,07 %**).

La proporción en trayectorias es treinta veces la de posiciones porque cada fila
huérfana cuenta como un vehículo entero.

## Cómo se midió

```python
import duckdb
from project.tracking import rastrear
p = "data/curated/source=emt_buses/*/*.parquet"
duckdb.sql(f"select count(*), count(*) filter (where trayecto is null), "
           f"count(distinct linea) filter (where trayecto is null) "
           f"from read_parquet('{p}', hive_partitioning=false)")
df = duckdb.sql(f"select snapshot_id, linea, trayecto, lat, lon, ts_utc "
                f"from read_parquet('{p}', hive_partitioning=false) "
                f"where ts_ingest_utc >= '2026-08-27' and ts_ingest_utc < '2026-08-28' "
                f"and lat is not null").df()
out = rastrear(df)
out[out.trayecto.isna()].vehicle_id.nunique(), out.vehicle_id.nunique()
```

Las cifras de arriba se tomaron sobre la copia del curated que escribió el
colector, **no** sobre el reprocesado del 18/09, que duplica sondeos (entrada
019) e infla el recuento de trayectorias.

## Por qué importa

Poco para la identidad —no contamina ninguna trayectoria ajena—, pero sí para las
**métricas del tracker**: una trayectoria de un punto baja la mediana de duración
y sube el recuento de fragmentos. Sin filtrarlas, el 1 % de «trayectorias» no son
vehículos. Aguas abajo no generan etiqueta —con una posición no hay retraso que
medir—, así que el daño se queda en los diagnósticos.

## Qué se hizo / qué queda abierto

Nada en el código todavía. Opciones, sin decidir:

- descartarlas en `prepare.py` antes de rastrear, contándolas;
- inferir el sentido con el map-matching (el avance decide el trazado) y
  rastrearlas después con su trayecto.

Abierto: si las posiciones sin trayecto se concentran en algún momento del
servicio (entrada o salida de cochera, cambio de sentido en cabecera). No se ha
mirado.

## Para la memoria

> Una fracción residual de las posiciones publicadas por la EMT (0,04 % en la
> captura de agosto, repartida en 31 líneas) carece del sentido de circulación.
> Como el emparejamiento entre sondeos se realiza dentro de cada par
> línea-sentido, estas posiciones quedan aisladas y aparecen como trayectorias de
> una sola observación, que llegan a suponer el 1 % de las trayectorias de una
> jornada. No afectan a la identidad del resto de vehículos ni producen etiquetas,
> pero deben excluirse de las métricas de reconstrucción para no sesgar la
> duración y la fragmentación reportadas.
