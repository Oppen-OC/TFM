---
id: 014
titulo: La capa 192 entrega 412 filas con idtramo para 410 tramos: los tramos 211 y 216 llegan duplicados en cada sondeo, con el mismo estado
fecha: 2026-09-17
tipo: anomalia
capa: fuentes
capitulo: calidad-dato
impacto: medio
estado: abierto
evidencia: uv run python -m project.analysis.auditar_supuestos
trampa: 005
---

## Qué se observó

Cada payload de `OPENDATA/Trafico/192` trae 446 filas. En los 5.961 payloads de
los 13 días completos:

- **34 filas sin `idtramo`** en todos, sin excepción (mínimo 34, máximo 34). La
  ficha 005 hablaba de "~35".
- **412 filas con `idtramo`**, pero **410 identificadores distintos**. Los tramos
  **211 y 216** aparecen dos veces en cada payload revisado (1.715 de 1.715 en
  los días 17 y 27), y las dos copias **nunca contradicen su `estado`**.

La cifra de 410 tramos de la entrada 005 es correcta en identificadores; en filas
que devuelve el parser son 412.

## Cómo se midió

```bash
uv run python -m project.analysis.auditar_supuestos --json auditoria/resultados/supuestos_fc5d15c.json
```

`filas_hueco_192()` recorre el crudo con `read_raw()` y cuenta filas totales y
filas sin `idtramo` por payload. Los duplicados se contaron agrupando por
`idtramo` dentro de cada payload sobre los días 17 y 27 y comparando el conjunto
de estados de cada grupo.

## Por qué importa

`parse_trafico_estado()` descarta las filas hueco pero conserva los duplicados.
Leer el estado de un tramo no se ve afectado. Cualquier agregado **por filas** sí:
porcentaje de tramos congestionados, media de estado de un corredor o un join
espacial que asigne un bus al tramo 211 devolverán ese tramo dos veces.

## Qué se hizo / qué queda abierto

Hecho: la medición.

Abierto: decidir si se deduplica por `idtramo` en el parser —cambia `curated/` y
exige reprocesar— o aguas abajo en `features.py`. Ver si las dos copias difieren
en geometría, que explicaría la duplicación como tramo en dos partes.

## Para la memoria

> La capa municipal de estado del tráfico devuelve 446 registros por consulta,
> de los cuales 34 carecen de identificador de tramo, geometría y estado, y se
> descartan de forma sistemática en todas las consultas observadas. De los 412
> restantes, dos tramos aparecen duplicados en la totalidad de las respuestas con
> idéntico estado, de modo que la red instrumentada consta de 410 tramos
> distintos. La duplicación no altera el estado leído para cada tramo, pero debe
> tenerse en cuenta en cualquier agregación por registros para no ponderar dos
> veces esos segmentos.
