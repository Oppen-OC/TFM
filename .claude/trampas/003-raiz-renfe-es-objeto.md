---
id: 003
titulo: La raíz del JSON de Renfe es un objeto, no un array
estado: cerrada
capa: fuentes
detectada: 2026-08-19
test: tests/test_ingest.py::test_renfe_filtra_solo_nucleo_40
---

## Síntoma

Iterar el payload de `flota.json` directamente da las claves del objeto raíz en
vez de los trenes.

## Causa

La raíz es:

```json
{"fechaActualizacion": "...", "trenes": [...]}
```

Los trenes cuelgan de `trenes`. Además el fichero trae la flota nacional
completa: hay que filtrar por `nucleo == "40"` para quedarse con Cercanías
València.

## Por qué se vuelve a caer aquí

Trampa menor, pero entra por dos motivos. Primero, el resto de fuentes del
proyecto son ArcGIS REST y devuelven `{"features": [...]}` con una forma
distinta, así que el parser de Renfe rompe el patrón mental del resto.

Segundo, y más importante: **olvidar el filtro de núcleo no da error**. Da la
flota nacional entera, que parece un volumen alto normal. Renfe es el plan B del
TFM si el map-matching de la EMT se desborda, así que un parser silenciosamente
mal filtrado contamina justo la vía de escape.

`fechaActualizacion` llega como ISO naive y sufre el mismo problema de zona
horaria que [002](002-emt-alterna-convencion-horaria.md).

## Guardia

`parse_renfe()` en `src/project/ingest/sources.py:335`, con `nucleo="40"` por defecto.

`tests/test_ingest.py::test_renfe_filtra_solo_nucleo_40` y
`tests/test_ingest.py::test_renfe_retraso_min_es_numerico`.
