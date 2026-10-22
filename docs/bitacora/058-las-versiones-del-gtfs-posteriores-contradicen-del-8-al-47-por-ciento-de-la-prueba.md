---
id: 058
titulo: Dos versiones del GTFS posteriores contradicen del 12 al 24 % y del 8 al 47 % de los pasos de la prueba, frente al 3,6-7,0 % de la validación; la 12 y la 27 faltan enteras en una de ellas y circularon
fecha: 2026-10-22
tipo: limitacion
capa: etiquetado
capitulo: limitaciones
impacto: medio
estado: aceptado
evidencia: uv run python -m project.analysis.comparar_gtfs "data/raw/source=gtfs_emt/date=2026-10-13/489e90825696_google_transit2026-10-11.zip"; uv run python -m project.analysis.comparar_gtfs data/raw/gtfs_archivo/google_transit2026-10-19.zip
trampa: —
---

## Qué se observó

Los pasos de la prueba se etiquetan con la `19-09-2026` (nota del 11/10 al
ADR-024). Se contrastaron dos versiones posteriores con `comparar_gtfs`, que da
el porcentaje de pasos etiquetados cuyo (línea, parada, hora programada) no
existe en la otra versión:

**`12-10-2026`**, vigente del 05/10 al 11/11. Contradice del **12,3 al 15,6 %**
de los pasos de los días laborables y sábados del 07 al 19/10. En el festivo
del 12/10 llega al **21,7 %** y el domingo 18/10 al **24,2 %**.
- La **12** y la **27** no existen en esa versión: el 100 % de sus pasos queda
  contradicho. La flota publicó posiciones de las dos durante toda la prueba.
- La **35** también queda al 100 %, y la 19, a un 9-19 %.

**`20-10-2026`**, vigente del 13/10 al 19/11:
- Del 13 al 19/10, del **8,1 al 9,8 %** los laborables, sobre todo por la 18 y
  la 35 (91-100 %).
- El viernes 16/10, el **17,8 %**.
- **El fin de semana, el 41,3 % (sábado 17) y el 47,3 % (domingo 18)**, con
  entre ocho y diez líneas al 100 %.

En la validación, la versión del 05/10 contradecía el 3,6-7,0 % (bitácora 042).

## Cómo se midió

```bash
uv run python -m project.analysis.comparar_gtfs "data/raw/source=gtfs_emt/date=2026-10-13/489e90825696_google_transit2026-10-11.zip"
uv run python -m project.analysis.comparar_gtfs data/raw/gtfs_archivo/google_transit2026-10-19.zip
```

Sobre `data/interim/pasos` del `dvc repro` del
21/10. La `12-10-2026` es la que bajó a mano el 13/10 (bitácora 051). La
`20-10-2026` se bajó de VLCi el 21/10 y está archivada fuera de `gtfs_dir`, con
`dvc add`.

## Por qué importa

- Una versión posterior reescribe días ya pasados, y no se sabe cuál operó. Si
  el horario del fin de semana cambió hacia el 17/10, las etiquetas de ese fin
  de semana miden el retraso frente a un horario que no se circuló.
- Afecta poco a la comparación con y sin tráfico: es pareada sobre las mismas
  etiquetas.
- Afecta más a la tasa base del clasificador y a la ventaja de la v2 sobre el
  listón, que se miden contra la etiqueta.
- Que la 12 y la 27 falten en una versión y circulen es el patrón de la 13 en
  la 042, y la 051 mostró que se deshace en versiones siguientes. El feed no es
  un registro fiable de lo que opera.

## Qué se hizo / qué queda abierto

- Declarado como límite. No se reetiqueta: la versión se fijó antes de la
  prueba (ADR-014 y nota del 11/10).
- Abierto: medir la v2 y el clasificador de la prueba sin el fin de semana del
  17-18/10, como análisis exploratorio declarado.

## Para la memoria

> La Empresa Municipal de Transportes publica una versión nueva del horario
> casi a diario, y algunas reescriben días ya pasados. Las etiquetas de la
> prueba se construyeron con la versión fijada de antemano. Dos versiones
> posteriores la contradicen en una fracción notable de los pasos etiquetados.
> La primera, vigente durante toda la prueba, discrepa entre el 12 % y el 16 %
> en los días laborables y llega al 24 % en domingo, sobre todo porque omite
> dos líneas que la flota siguió operando. La segunda discrepa entre el 8 % y
> el 10 % en los laborables, pero en el 41 % y el 47 % de los pasos del último
> fin de semana. En la semana de validación, la discrepancia era del 3,6-7,0 %.
> Como la versión publicada no siempre coincide con el servicio que se presta,
> no se puede saber qué horario operó cada día. La comparación con y sin
> tráfico, pareada sobre las mismas etiquetas, apenas se ve afectada. Las
> métricas absolutas de la prueba sí, y en particular la tasa de retrasos de
> más de cinco minutos, deben leerse con esta salvedad.
