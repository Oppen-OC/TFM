---
id: 019
titulo: reprocesar no deduplica sondeos como el colector, y el curated reconstruido infla un 53 % las trayectorias del día
fecha: 2026-09-18
tipo: anomalia
capa: fuentes
capitulo: calidad-dato
impacto: alto
estado: abierto
evidencia: uv run python -m project.ingest.reprocesar --sources emt_buses (y comparar contra data/_curated_previo)
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

La copia del curated anterior quedó en `data/_curated_previo/`. La misma
consulta sobre las dos raíces, para el 27/08:

```python
import duckdb
from project.tracking import rastrear
for raiz in ("data/_curated_previo", "data/curated"):
    p = f"{raiz}/source=emt_buses/*/*.parquet"
    dia = (f"from read_parquet('{p}', hive_partitioning=false) where "
           "ts_ingest_utc >= '2026-08-27' and ts_ingest_utc < '2026-08-28'")
    print(duckdb.sql(f"select count(*), count(distinct snapshot_id), "
                     f"count(distinct ts_ingest_utc) {dia}").fetchone())
    df = duckdb.sql(f"select snapshot_id, linea, trayecto, lat, lon, ts_utc "
                    f"{dia} and lat is not null").df()
    print(rastrear(df).vehicle_id.nunique())
```

Los sondeos repetidos salen agrupando por `snapshot_id` con
`count(distinct ts_ingest_utc) > 1`.

## Por qué importa

Es la capa que no se puede arreglar después, invertida: el crudo está bien, pero
**la herramienta que existe precisamente para regenerar el curated lo estropea
sin avisar**. Cualquier medida sobre el curated reprocesado —la validación del
map-matching de septiembre, las cifras de fragmentación, las etiquetas— hereda
sondeos repetidos. Ningún test lo detecta: `tests/test_persistencia.py` prueba
que `reprocesar` reconstruye, no que reconstruya **lo mismo** que el colector.

## Qué se hizo / qué queda abierto

Nada en el código todavía; el curated reprocesado sigue en `data/curated/` y el
del colector en `data/_curated_previo/` (sólo hasta 31/08).

Abierto, en este orden:

1. Deduplicar en `reprocesar` con el mismo criterio que `recordar`: primera
   captura de cada `snapshot_id` por fuente.
2. Test en `test_persistencia.py`: crudo con un sondeo repetido ⇒ curated de
   `reprocesar` igual al del colector. Mutante en `auditoria/catalogo.toml` que
   quite la deduplicación y lo ponga rojo.
3. Volver a reprocesar y comprobar que el 27/08 vuelve a 353.604 filas y 7.658
   trayectorias.
4. Revisar si Renfe, tráfico y Valenbisi tienen `snapshot_id` con la misma
   semántica antes de aplicarles el criterio.

## Para la memoria

> La separación entre captura y procesado permite regenerar los datos limpios a
> partir del crudo siempre que se corrija un analizador. Esa regeneración debe
> reproducir exactamente las reglas del colector: al reconstruir la captura se
> detectó que el procedimiento no descartaba los sondeos que la fuente sirve
> repetidos, que el colector sí descarta. Un aumento del 2,5 % en las filas se
> tradujo en un 53 % más de trayectorias reconstruidas, porque las posiciones
> duplicadas no pueden asignarse a los vehículos existentes. La corrección exige
> una prueba de equivalencia entre ambos caminos, no sólo de que el segundo
> produzca un resultado.
