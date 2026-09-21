---
id: 025
titulo: Desde el 9 de septiembre la capa de la EMT deja de publicar casi toda la 71 y buena parte de la 28, la 25, la 4 y la 73, y esos buses no reaparecen con otro número
fecha: 2026-09-21
tipo: anomalia
capa: fuentes
capitulo: limitaciones
impacto: medio
estado: abierto
evidencia: consulta de «Cómo se midió» sobre data/curated
trampa: —
---

## Qué se observó

Posiciones por línea en día laborable completo, mediana de cada periodo:

| línea | 01-08/09 | 09-17/09 | cambio |
|---|---|---|---|
| 71 | 15.474 | 1.011 | **−93 %** |
| 28 | 12.743 | 3.286 | −74 % |
| 25 | 12.804 | 4.602 | −64 % |
| 73 | 5.966 | 1.641 | −72 % |
| 4 | 7.202 | 2.584 | −64 % |
| C3 | 38.115 | 32.329 | −15 % |

La 71 tenía 14.257 posiciones de mediana en agosto. En el mismo cambio suben la
18 (+5.004), la 64 (que no aparecía y pasa a 3.559), la 7, la 70, la 12 y la
40, que suman unas 18.000 posiciones. Las caídas suman unas 47.000. En
laborable, la suma de medianas pasa de 446.085 a 407.169 (−9 %).

**Los buses que faltan no se publican con otro número de línea.** Las posiciones
de 7 a 22 h de otras líneas que caen fuera de su propio trazado y a menos de
20 m del de la 71, la 4 o la 28 son 745, 227 y 248 el 16/09, frente a 1.182, 175
y 179 el 27/08, cuando esas líneas se publicaban con normalidad.

## Cómo se midió

```python
import duckdb
duckdb.sql("set TimeZone = 'UTC'")
d = duckdb.sql("""
    select cast(ts_ingest_utc as date) dia, cast(linea as varchar) linea, count(*) n
    from read_parquet('data/curated/source=emt_buses/*/*.parquet', hive_partitioning=false)
    group by all""").df()
# laborables completos: 01-04, 07-09 y 15-17/09; mediana por línea antes y después del 09/09
```

La comprobación de la línea mal publicada proyecta, sobre la salida de
`validar_mapmatching --guardar`, las posiciones fuera de ruta de su propia
línea contra los trazados de la 71, la 4 y la 28 del feed `19-09-2026`.

## Por qué importa

- **La cobertura de la etiqueta en septiembre la limita la fuente, no el
  método.** El 16/09 se etiquetó el 54,7 % de los viajes programados, pero el
  86,5 % de los tramos de servicio observados (entrada 024). La diferencia son
  viajes que la capa no publica.
- **Sesga la muestra por línea y por fecha.** La 71 y la 28 están bien cubiertas
  en agosto y casi ausentes desde el 09/09. Un split temporal con el corte en
  septiembre deja esas líneas en entrenamiento y fuera de la prueba.
- No se sabe si esos buses no circulan (un cambio de servicio que el GTFS de
  septiembre no refleja, porque sigue programando 184 viajes de la 71 el 16/09)
  o si circulan sin publicarse.

## Qué se hizo / qué queda abierto

Nada que corregir en el pipeline: los viajes no publicados no se pueden
etiquetar.

Abierto:

- Seguir la evolución en las capturas siguientes: si la 71 no vuelve, cambia el
  conjunto de líneas disponibles para evaluar.
- Contrastar con la EMT si es un cambio de servicio o un fallo de publicación.
- Al fijar el split temporal, medir la cobertura por línea a cada lado del corte.

## Para la memoria

> A partir del 9 de septiembre, la capa de posiciones de la EMT deja de publicar
> la mayor parte de los vehículos de varias líneas: la línea 71 pasa de unas
> 15.000 posiciones diarias a unas 1.000, y la 28, la 25, la 4 y la 73 pierden
> entre dos tercios y tres cuartos. Los vehículos ausentes no reaparecen con otro
> número de línea: las posiciones de otras líneas sobre esos recorridos se
> mantienen en los niveles previos. El horario publicado sigue programando esos
> servicios, de modo que la fracción de viajes programados que puede etiquetarse
> cae en septiembre por una causa ajena al método. La cobertura se informa por
> línea y por periodo, y el corte temporal entre entrenamiento y prueba debe
> tenerla en cuenta.
