---
id: 056
titulo: El corpus son 31,7 M de filas en 57 días y proyecta 56 M a tres meses, no los 145 M que sostienen el pilar del volumen
fecha: 2026-10-15
tipo: medicion
capa: fuentes
capitulo: metodologia
impacto: medio
estado: aceptado
evidencia: uv run python -m project.analysis.medir_volumen --filas
trampa: —
---

## Qué se observó

El tercer pilar de la defensa («el volumen es real») cita **~145 M de filas en
tres meses**. Es la proyección de `docs/01` §6, hecha antes de capturar y con
cadencias supuestas. Medido sobre el curated reprocesado (15/08-13/10, 57 días
con datos de los 60 del calendario):

| fuente | filas | mediana/día | proyectado/día (`docs/01`) | MB en disco |
|---|---|---|---|---|
| emt_buses | 16.770.584 | 336.161 | 480.000-900.000 | 337 |
| trafico_estado | 6.969.442 | 118.244 | ~642.000 | 25 |
| valenbisi | 3.978.975 | 78.078 | ~79.000 | 36 |
| trafico_intensidad | 2.078.776 | 37.632 | ~113.000 | 10 |
| renfe_cercanias | 1.923.254 | 35.571 | ~49.000 | 25 |
| **total** | **31.721.031** | **605.686** | ~1,58 M | **433** |

A la mediana diaria, 92 días dan **55,7 M** de filas: **2,6 veces menos** que
los 145 M. El crudo comprimido ocupa **2,57 GB**.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_volumen --filas
```

Cuenta con DuckDB las filas de `data/curated/source=*/` por día de captura (UTC)
y suma el tamaño de los Parquet. La proyección usa la **suma de medianas por
día**, no total/días: los días partidos por el hueco del geoportal (bitácora 021)
o por el disco de la Pi (bitácora 054) no la arrastran hacia abajo.

**El instrumento se comprobó antes que la cifra.** Las capas de cadencia fija
cuadran con elementos × sondeos: la 192 da 412 filas (bitácora 014) × 288
sondeos de 5 min = 118.656, frente a 118.244 de mediana; la 188, 37.632 = 392 ×
96 sondeos de 15 min, el mismo valor que midió la 033. Faltan 3 días enteros
(11-13/09 y 05/10), que es lo que dicen la 021 y la 054. El curated es el que
reconstruye `curar` (bitácoras 019 y 020): sondeos deduplicados y Renfe ya
filtrada al núcleo 40 (trampa 003).

## Por qué importa

- **La diferencia sale casi entera del tráfico y la EMT.** `docs/01` suponía la
  capa de estado sondeada cada 60 s. El colector la sondea cada 5 min desde que
  en agosto solo 8 tramos cambiaron de estado en 2.033 sondeos
  (`ingest/sources.py`, `trafico_estado`), y eso la divide por 5,4. Es una
  decisión de captura, no un límite de la fuente: la 031 ve la capa animarse en
  periodo lectivo y la cadencia no se ha reevaluado con ese dato. La EMT da 336.000 filas al día, por
  debajo incluso del supuesto «noche» (480.000).
- **El pilar se sostiene con otro argumento, no con esa cifra.** 31,7 M de filas
  ocupan 433 MB en Parquet; el volumen justifica Parquet + DuckDB frente a CSV
  en un portátil, pero no es «Big Data» en el sentido de caudal, y la 033 ya
  descartó un broker por eso. Citar 145 M ante el tribunal choca con la propia
  bitácora.
- **La cifra estaba copiada en diez sitios**: `README.md`, `CLAUDE.md`,
  `docs/00`, `docs/01`, `docs/04`, ADR-003 y cuatro ficheros de `.claude/`
  (`tribunal`, `etl-labeler`, `pipeline-dvc`, `grill-me`).

## Qué se hizo / qué queda abierto

Hecho: el medidor (`medir_volumen --filas`) y esta entrada.

Abierto: corregir la cifra donde se cita como hecho (pilar 3 en `docs/00`,
`README.md`, `CLAUDE.md`, `tribunal.md`; ADR-003). `docs/01` y `docs/04` son
documentos fechados y la proyección queda como lo que era, con un puntero aquí.
La captura sigue: la cifra final del corpus se vuelve a medir al cerrarla.

## Para la memoria

> La propuesta inicial estimaba un volumen de unos 145 millones de registros en
> tres meses de captura, calculado con las cadencias de refresco supuestas para
> cada fuente. El volumen medido es inferior: en 57 días con datos, las cinco
> fuentes produjeron 31,7 millones de registros, con una mediana de 605.686 al
> día, lo que proyecta unos 56 millones a tres meses. La diferencia procede
> sobre todo de la capa de estado del tráfico, que se sondea cada cinco minutos y
> no cada minuto porque en las primeras semanas apenas cambiaba entre sondeos, y
> de una flota de autobuses observada menor que la estimada. Almacenado en Parquet comprimido, el corpus ocupa 433 MB; el
> volumen no exige infraestructura distribuida, pero sí un formato columnar y un
> motor analítico embebido para tratarlo en un ordenador personal, que es la
> elección que se justifica en el capítulo de arquitectura.
