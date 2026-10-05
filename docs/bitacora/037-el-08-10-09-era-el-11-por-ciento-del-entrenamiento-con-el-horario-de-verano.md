---
id: 037
titulo: El 08-10/09, etiquetado con el horario de verano, era el 10,9 % de la tabla de entrenamiento y sus días más cercanos a la prueba; excluirlo deja el entrenamiento entero en agosto, con un 4,88 % de positivos frente al 5,85 % de la prueba
fecha: 2026-10-05
tipo: medicion
capa: etiquetado
capitulo: metodologia
impacto: alto
estado: aceptado
evidencia: consulta de «Cómo se midió» sobre la tabla de entrenamiento de 706bb60 en la caché de DVC; metrics/features.json de c6f06c7
trampa: —
---

## Qué se observó

En la tabla de entrenamiento de `706bb60` (`data/processed/train.parquet`, md5
`9588fe63…`), las filas del 08 al 10/09 llevan todas `feed_version =
01-09-2026`, el horario de verano:

| | filas | viajes |
|---|---|---|
| 08-10/09 | **135.114** | 6.769 |
| total | 1.236.585 | 58.427 |
| proporción | **10,9 %** | 11,6 % |

Son los tres días más cercanos a la prueba (14-18/09) y los únicos de
septiembre que entrenaban. Su calidad de asignación, de `metrics/prepare.json`:

| | conflictos | rechazos por margen | asignados |
|---|---|---|---|
| media de un día de agosto (15-30/08) | 109 | 76 | 3.229 |
| 08/09 | 576 (×5,3) | 673 (×8,9) | 3.271 |
| 09/09 | 632 (×5,8) | 586 (×7,8) | 3.228 |

Tras ampliar `excluir_fechas` hasta el 11/09 y rehacer `prepare` y `features`
(`c6f06c7`):

- Entrenamiento: 1.236.585 → **1.101.471** filas, de 19 a 16 días.
- Pasos con retraso: 1.577.736 → 1.435.851 (−141.885 = 71.004 + 66.400 + 4.481).
- Prueba y baselines: idénticos (269.493 filas; MAE de 139,9 s con el horario
  y de 37,6 s con la persistencia).
- Positivos (retraso > 5 min): **5,70 % → 4,88 %** en entrenamiento, frente al
  **5,85 %** de la prueba.

## Cómo se midió

```python
import duckdb
p = ".dvc/cache/files/md5/95/88fe63989479a1f6d588fba3ef94a4"  # train.parquet en 706bb60
duckdb.sql(f"""select feed_version, fecha_servicio >= '2026-09-08' sept,
               count(*) filas, count(distinct viaje_id) viajes
               from read_parquet('{p}') group by all""")
```

El md5 sale de `git show 706bb60:dvc.lock`. Los recuentos por día salen de
`git show 706bb60:metrics/prepare.json` (`por_dia[].viajes_por_motivo`).
Después: `uv run dvc repro features` en `4a7288f`, con el resultado en
`metrics/features.json` de `c6f06c7`. Las filas que se van coinciden al dígito
con las del 08-10/09 de la tabla anterior.

## Por qué importa

- Un 10,9 % del entrenamiento estaba etiquetado contra un horario que no se
  circulaba. Cada fila tenía aspecto de dato bueno: las señales visibles eran
  los conflictos y los rechazos, no las filas asignadas (bitácora 024).
- **El precio es un entrenamiento solo de agosto** contra una prueba en
  septiembre lectivo. La tasa de positivos ya lo muestra (4,88 % frente a
  5,85 %), y la capa 192 se anima en periodo lectivo (bitácora 031). Lo que el
  modelo pierda en la prueba puede ser cambio de régimen, no falta de señal.
  Hay que decirlo así al presentar las métricas.

## Qué se hizo / qué queda abierto

Hecho: `params.yaml → prepare.excluir_fechas` hasta el 2026-09-11, el test de
`test_cada_clave_de_params_prepare_llega_al_etiquetado` con los dos bordes y
el ADR-014 ampliado (`4a7288f`). El issue #2 (esquema de los días excluidos) se
cerró antes de reejecutar (`19cdfaf`).

Abierto:

- ~~Mover el corte con la captura posterior al 18/09.~~ Hecho el 05/10
  (`c721899`, ADR-007): con la captura hasta el 04/10 y `test_desde =
  2026-09-21`, el entrenamiento son 1.525.118 filas de 23 días (agosto y la
  semana del 14 al 20/09) y la prueba 840.022 de 14. Positivos: 5,39 % frente a
  7,09 %; el desfase entre periodos se reduce pero no desaparece.
- Si aparece la versión del GTFS del 10/09 (Transitland de pago), el 08-11/09
  se puede recuperar (ADR-014, condición de reapertura).

## Para la memoria

> Entre el 8 y el 10 de septiembre circuló el servicio de septiembre, pero la
> única versión del horario disponible para esas fechas era la de verano. Los
> pasos etiquetados contra ella suponían el 10,9 % de las filas de
> entrenamiento (135.114 de 1.236.585) y eran los días más próximos al periodo
> de prueba. En esas jornadas los viajes observados en conflicto se
> multiplicaban por 5,3-5,8 y los rechazados por margen insuficiente por
> 7,8-8,9 respecto a un día medio de agosto. Se excluyeron del conjunto, que
> quedó en 1.101.471 filas de 16 jornadas. La exclusión tiene un coste
> declarado: el entrenamiento procede íntegramente de agosto y la prueba de
> septiembre, con periodo lectivo, y la proporción de pasos con más de cinco
> minutos de retraso pasa del 4,88 % en entrenamiento al 5,85 % en prueba.
