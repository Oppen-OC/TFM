---
id: 001
titulo: gid identifica al refresco, no al vehículo
estado: cerrada
capa: fuentes
detectada: 2026-08-19
test: demo/selftest.py::"gids de dos sondeos consecutivos son disjuntos"
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
`rastrear()` en `demo/track.py:54`.

## Guardia

`demo/selftest.py`, checks *"gids de dos sondeos consecutivos son disjuntos"* y
*"los bloques son contiguos (truncate + reinsert)"*.

Uso legítimo de `gid`: como `snapshot_id`, tomando el mínimo del bloque para
identificar el refresco y deduplicar. Cubierto por el check *"emt: snapshot_id =
gid mínimo del bloque"*.
