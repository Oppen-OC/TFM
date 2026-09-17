---
id: 001
titulo: gid identifica al refresco, no al vehículo
estado: cerrada
capa: fuentes
detectada: 2026-08-19
test: tests/test_ingest.py::test_emt_snapshot_id_es_el_gid_minimo_del_bloque
---

## Síntoma

`gid` parece un identificador estable de vehículo: es un entero, es único dentro
del sondeo y la capa lo devuelve siempre. Cualquier intento de seguir un bus
agrupando por `gid` produce trayectorias de exactamente una posición.

## Causa

La tabla detrás de la capa `EMT/Seguimiento_EMT/384` se **trunca y se reinserta
entera** en cada refresco. `gid` es el autoincrement de esa tabla, así que avanza
en bloque contiguo con cada sondeo:

```
sondeo t0 : gid ∈ [1 659 987 635 … 1 659 987 800]   166 filas
sondeo t1 : gid ∈ [1 659 987 801 … 1 659 987 967]   167 filas
```

La intersección entre dos sondeos consecutivos es **exactamente cero**. Consultar
por `gid <` el mínimo del primer sondeo devuelve 0 filas: no hay histórico
detrás.

Medido en `docs/01_viabilidad_fuentes_valencia.md`, líneas 59-78.

## Por qué se vuelve a caer aquí

Un OID entero y monótono es exactamente lo que tiene pinta de clave primaria de
entidad. Nada en la respuesta de la capa dice lo contrario, y la documentación
del geoportal no lo menciona. El error no falla: produce 65.000 trayectorias de
un punto, que parece un problema de filtrado y no de identidad.

Es la trampa que define el trabajo del TFM: la capa de la EMT publica posición,
línea y sentido, pero ni `trip_id`, ni id de vehículo, ni retraso. **La identidad
hay que inferirla** — asignación húngara con predicción de movimiento,
`rastrear()` en `src/project/tracking.py:59`.

## Guardia

`tests/test_ingest.py::test_emt_snapshot_id_es_el_gid_minimo_del_bloque`: fija el
único uso legítimo de `gid`, como `snapshot_id` tomando el mínimo del bloque.

Hasta 09/2026 la ficha citaba `test_gids_de_sondeos_consecutivos_son_disjuntos`
y `test_los_bloques_de_gid_son_contiguos`. Siguen en la suite, pero comprueban
el **fixture** —documentan el hecho de la fuente—, no el código: ningún cambio en
`src/` puede ponerlos rojos (auditoría de mutación, `docs/11_auditoria_tests.md`).
