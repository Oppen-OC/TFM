---
id: 019
titulo: reprocesar no deduplica sondeos como el colector, y el curated reconstruido infla un 53 % las trayectorias del día
fecha: 2026-09-18
tipo: anomalia
capa: fuentes
capitulo: calidad-dato
impacto: alto
estado: resuelto
evidencia: uv run python -m project.ingest.reprocesar --dry-run (repetidos y completados por fuente); consulta de «Cómo se midió» para el 27/08
trampa: —
---

## Qué se observó

El colector descarta un sondeo cuyo `snapshot_id` ya ha visto
(`collect.recordar`). `reprocesar` vuelve a parsear **todos** los payloads del
crudo y los escribe tal cual (`src/project/ingest/reprocesar.py`, bucle sobre
`read_raw`): el mismo sondeo servido varias veces por la EMT entra varias veces.

Tras reconstruir el curated el 18/09 con los datos copiados de la Raspberry, el
27/08 queda así (EMT):

| | curated del colector | curated reprocesado |
|---|---|---|
| filas | 353.604 | 362.332 |
| `snapshot_id` distintos | 2.784 | 2.784 |
| capturas (`ts_ingest` distintos) | 2.784 | **2.854** |
| pares (`snapshot_id`, `gid`) únicos | — | 358.142 |
| trayectorias de `rastrear()` | 7.658 | **11.730** |

El caso extremo del día: el sondeo `1664101649` aparece en **14 capturas** (700
filas). Un 2,5 % más de filas se convierte en un 53 % más de trayectorias,
porque cada réplica del sondeo son posiciones idénticas a las que el tracker no
puede asignar dos veces y arranca vehículos nuevos.

## Cómo se midió

La copia del curated del colector está en `data/_curated_colector/` (hasta el
31/08 a las 16:30 UTC). La misma consulta sobre cada raíz, para el 27/08:

```python
import duckdb
from project.tracking import rastrear
duckdb.sql("set TimeZone = 'UTC'")
for raiz in ("data/_curated_colector", "data/curated"):
    p = f"{raiz}/source=emt_buses/*/*.parquet"
    dia = (f"from read_parquet('{p}', hive_partitioning=false) where "
           "ts_ingest_utc >= '2026-08-27 00:00:00+00' "
           "and ts_ingest_utc < '2026-08-28 00:00:00+00'")
    print(duckdb.sql(f"select count(*), count(distinct snapshot_id), "
                     f"count(distinct ts_ingest_utc) {dia}").fetchone())
    df = duckdb.sql(f"select snapshot_id, linea, trayecto, lat, lon, ts_utc "
                    f"{dia} and lat is not null").df()
    print(rastrear(df).vehicle_id.nunique())
```

Los sondeos repetidos salen agrupando por `snapshot_id` con
`count(distinct ts_ingest_utc) > 1`. La semántica por fuente y la clasificación
de las repeticiones, con
`uv run python -m project.analysis.medir_sondeos_repetidos` (entrada 020).

**El día es UTC y hay que decirlo.** La primera versión de esta consulta
comparaba con `'2026-08-27'` a secas, y DuckDB interpreta ese literal en la
zona de la sesión, `Europe/Madrid` en este equipo: el colector daba entonces
353.738 filas y 2.785 sondeos, no las cifras de la tabla. Las de la tabla son
del día UTC.

## Por qué importa

Es la capa que no se puede arreglar después, invertida: el crudo está bien, pero
**la herramienta que existe precisamente para regenerar el curated lo estropea
sin avisar**. Cualquier medida sobre el curated reprocesado —la validación del
map-matching de septiembre, las cifras de fragmentación, las etiquetas— hereda
sondeos repetidos. Ningún test lo detecta: `tests/test_persistencia.py` prueba
que `reprocesar` reconstruye, no que reconstruya **lo mismo** que el colector.

## Qué se hizo / qué queda abierto

Resuelto en 76a1921. La clave de sondeo sale de `collect.sondear` a
`sources.clave_sondeo`, que comparten el colector y `reprocesar`.

**Semántica por fuente**, medida sobre el crudo del 15/08 al 18/09 antes de
aplicar el criterio. Una captura cuenta como repetida si trae la clave de una
captura anterior:

| fuente | clave | capturas repetidas | con contenido distinto |
|---|---|---|---|
| EMT | `snapshot_id` | 2.078 de 80.069 | **1.340** |
| Renfe | `fechaActualizacion` | 179 de 90.250 | 0 |
| Valenbisi | `update_jcd` más reciente | 0 de 8.033 | — |
| tráfico (192 y 188) | instante de captura | 0 | — |

Las repeticiones son siempre consecutivas: la captura anterior es del mismo
sondeo en las 2.078 de la EMT y las 179 de Renfe. La memoria acotada del
colector no cambia, por tanto, el resultado. (Una primera versión del contador
decía «como mucho un sondeo nuevo entre medias»: tenía un error de uno.)

**En la EMT, «la primera captura» no era el criterio correcto.** De las 1.340
repeticiones con contenido distinto, 126 sólo cambian `fecha` en ±2 h (la
trampa 002, que el parseo iguala). Las otras 1.214 traen el mismo `snapshot_id`
con un conjunto de `gid` que **contiene estrictamente** al de la primera
captura, con la misma posición en los comunes: la primera captura era el bloque
a medio reinsertar. Son 1.200 sondeos (el 1,54 % de 77.952) y 109.063 filas que
el colector descartó. Decisión: `reprocesar` se queda la captura con más filas,
y a igualdad la primera. El colector no se toca (sigue la primera). El curated
canónico es el reprocesado.

Guardias: `test_reprocesar_reconstruye_lo_mismo_que_el_colector` (cinco
fuentes) y `test_reprocesar_completa_el_sondeo_que_llego_a_medias`. Los
mutantes 053-055 salen detectados (`auditoria/resultados/mutantes_76a1921.json`).

**Reprocesado el 18/09**, contra el curated del colector, del 15/08 al 31/08 y
en día UTC:

| 27/08 | filas | sondeos | capturas | trayectorias |
|---|---|---|---|---|
| colector | 353.604 | 2.784 | 2.784 | 7.658 |
| reprocesado sin deduplicar | 362.332 | 2.784 | 2.854 | 11.730 |
| reprocesado ahora | **358.142** | 2.784 | 2.784 | **7.627** |

358.142 = 353.604 + 4.538 filas de los 54 sondeos completados ese día. En los
17 días:

- 0 sondeos del colector faltan en el reprocesado.
- 602 sondeos completados, con 52.907 filas.
- 18 sondeos del 15 y el 16/08 que el colector guardaba con dos capturas quedan
  con una (973 filas menos).
- 1.038 sondeos están en el crudo y no en el curated del colector. 871 son
  posteriores a la copia del 31/08 a las 16:30 UTC. Los otros 167 forman seis
  bloques contiguos de 5 a 22 minutos: buffers que el colector perdió al caer,
  y que el crudo conserva.

Curated nuevo: EMT 10.463.752 filas en 32 días (el reprocesado sin deduplicar
tenía 10.651.473). El sin deduplicar queda en `data/_curated_previo/`, y el del
colector, en `data/_curated_colector/`.

Queda abierto:

- Renfe tiene **98 capturas que no parsean**, anteriores a este cambio y sin
  investigar.
- Los sondeos parciales que NO tienen una segunda captura siguen parciales, y
  para ellos sigue haciendo falta `tolerar_hueco`. La causa que citan
  `tracking.py` y `simulacion.py` (`_TRUNCADOS.txt`) es falsa (entrada 011).
  En los 1.200 que sí tienen segunda captura, la causa medida es la
  reinserción de la tabla. Para el resto es la hipótesis más probable, sin
  medir.

## Para la memoria

> La separación entre captura y procesado permite regenerar los datos limpios a
> partir del crudo siempre que se corrija un analizador. Al reconstruir la
> captura se detectó que el procedimiento no descartaba los sondeos que la
> fuente sirve repetidos, que el colector sí descarta: un aumento del 2,5 % en
> las filas se tradujo en un 53 % más de trayectorias reconstruidas, porque las
> posiciones duplicadas no pueden asignarse a los vehículos existentes. Al
> contrastar los dos caminos apareció además que la regla del colector,
> quedarse con la primera captura de cada sondeo, no era neutral: en 1.200
> sondeos (el 1,5 %) esa primera captura era el bloque a medio reinsertar, y la
> siguiente traía el bloque completo con el mismo identificador. El reprocesado
> se queda la captura más completa y recupera 109.063 posiciones que sólo
> conservaba el crudo. Una prueba de equivalencia garantiza que, fuera de esos
> sondeos, los dos caminos producen exactamente lo mismo.
