---
id: 033
titulo: Las cinco fuentes suman 6.336 payloads al día, 0,07 por segundo y 297 MB sin comprimir; el volumen no pide un broker y Kafka queda fuera de la captura
fecha: 2026-09-30
tipo: descarte
capa: fuentes
capitulo: metodologia
impacto: medio
estado: aceptado
evidencia: uv run python -m project.analysis.medir_volumen
trampa: —
---

## Qué se observó

La propuesta al tutor (`docs/04`) ponía Kafka o Redpanda entre la ingesta y el
Parquet. Volumen real del crudo, mediana por día de captura sobre las 32
jornadas (15/08-18/09; Renfe, 35):

| fuente | payloads/día | MB/día sin comprimir | payload mayor |
|---|---|---|---|
| emt_buses | 2.851 | 65,0 | 43 kB |
| renfe_cercanias | 2.817 | 182,9 | 127 kB |
| trafico_estado | 286,5 | 18,3 | 258 kB |
| valenbisi | 286 | 24,1 | 84 kB |
| trafico_intensidad | 96 | 7,1 | 156 kB |
| **total** | **6.336** | **297** | |

Son **0,073 payloads por segundo**. El 16/09, día completo: 6.222 payloads y
317 MB. Renfe es el 62 % de los bytes y es la flota nacional entera: se filtra al
núcleo 40 al parsear.

La proyección que motivó el broker no se cumplió. `docs/03` estimaba 4,3 M de
filas de tráfico al día (1.500 tramos cada 30 s). Las dos capas dan una mediana
de 155.464 filas por día de captura —117.832 la 192, sondeada cada 5 min, y
37.632 la 188, cada 15—: **28 veces menos**. La EMT estaba en 720.000 filas al
día y da 371.377 de mediana.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_volumen                  # mediana de todos los días
uv run python -m project.analysis.medir_volumen --dias 2026-09-16
```

Cuenta las líneas de cada `payloads.ndjson.gz` (una por sondeo) y sus bytes sin
comprimir, envoltorio `{"ts_ingest_utc": …, "payload": …}` incluido. La mediana
entre días deja fuera el efecto de los días partidos.

Las filas por día salen del curated, por día de captura en UTC:

```python
import duckdb
from project.config import settings
p = (settings.curated_dir / "source=trafico_estado" / "*" / "*.parquet").as_posix()
duckdb.sql(f"""select median(n) from (select cast(ts_ingest_utc as date) d, count(*) n
    from read_parquet('{p}', hive_partitioning=false) group by 1)""")
# lo mismo con source=trafico_intensidad y source=emt_buses
```

**El instrumento se comprobó antes que la cifra.** El primer recuento se hizo con
`zcat | wc -l`, y `zcat` se para en el relleno de ceros que deja un corte de
corriente (bitácora 011). Repetido con `gzip.open`, que lo salta, el 16/09 da
los mismos 6.222 payloads. Los 314 MB de aquel recuento eran la suma de cinco
cifras truncadas al megabyte: son 317.

## Por qué importa

- **El argumento del volumen no existe.** Un broker se justifica con caudales de
  miles de mensajes por segundo; aquí entra un mensaje cada 14 segundos. Citar
  Kafka en la memoria como respuesta al volumen no resistiría esta tabla.
- **No hay obstáculo técnico, tampoco necesidad.** El payload mayor son 258 kB,
  por debajo del límite por defecto de 1 MB por mensaje de Kafka. Lo que un
  broker daría en la captura —separar capturar de procesar, poder reejecutar— ya
  lo da el crudo guardado antes de parsear.
- **Sí hay un coste.** Un proceso más en el camino de unos datos que no se
  pueden recapturar, en una Raspberry cuyo colector está limitado a 512 MB.

## Qué se hizo / qué queda abierto

Hecho: el medidor `analysis/medir_volumen.py` y la decisión, con sus
alternativas y lo que la reabriría, en ADR-016 (`docs/07_decisiones.md`). Los
docstrings de `collect.py` y `reprocesar.py` dejan de prometer Kafka.

Abierto: si el servido en tiempo real necesita un bus de mensajes o le basta un
proceso en `services/`. Se decide al montarlo, después de `train.py`, con la
latencia y la memoria medidas.

## Para la memoria

> La arquitectura propuesta inicialmente situaba un sistema de mensajería entre
> la captura y el almacenamiento, en previsión de un volumen de varios millones
> de registros diarios. El volumen medido es muy inferior: las cinco fuentes
> generan en conjunto una mediana de 6.336 respuestas al día, es decir, una cada
> catorce segundos, que ocupan 297 MB sin comprimir. La diferencia con la
> previsión procede sobre todo de las capas de tráfico, que tienen menos tramos
> de los supuestos y se muestrean cada cinco y cada quince minutos: unas 155.000
> filas diarias frente a los 4,3 millones estimados. Con
> ese caudal, un sistema de mensajería no aporta capacidad y añade un punto de
> fallo a una captura que no puede repetirse. La separación entre captura y
> procesamiento se obtiene almacenando cada respuesta tal como llega, antes de
> interpretarla, lo que permite reconstruir todas las tablas derivadas cuando se
> corrige un error de interpretación. El sistema de mensajería se reserva, como
> opción, para el servicio de predicciones en tiempo real.
