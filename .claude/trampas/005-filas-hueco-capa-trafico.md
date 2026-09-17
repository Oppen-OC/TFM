---
id: 005
titulo: El 8 % de la capa de tráfico son filas hueco, no tramos con estado desconocido
estado: cerrada
capa: fuentes
detectada: 2026-08-16
test: tests/test_ingest.py::test_filas_hueco_de_trafico_se_descartan
---

## Síntoma

La capa `OPENDATA/Trafico/192` devuelve 446 filas por sondeo. **34** llegan sin
`idtramo`, sin geometría y sin `estado` —constante en los 5.961 payloads de los
13 días completos de agosto—. Contadas como nulos, inflan un 8 % el dato
ausente de la fuente.

## Causa

No son tramos con estado desconocido: no son tramos. Quedan 412 filas y **410
tramos distintos**, porque el 211 y el 216 llegan duplicados en cada sondeo
(`docs/bitacora/014-la-capa-192-duplica-los-tramos-211-y-216.md`).

## Por qué se vuelve a caer aquí

"446 tramos" es la cifra de la descripción de la capa. Tomarla como denominador
es lo natural y hace que la calidad del dato parezca peor de lo que es. En el
sentido contrario, es igual de fácil arrastrar esas filas como categoría
"desconocido" hasta las features y meter 34 pseudo-tramos en el modelo.

Y el fixture no lo delata: está recortado a tres filas reales y ninguna es hueco,
así que quitar el filtro del parser no rompía ningún test.

## Guardia

`tests/test_ingest.py::test_filas_hueco_de_trafico_se_descartan`, sobre las dos
capas de tráfico, con filas hueco inyectadas en la forma que tienen en el crudo.
Verificada por mutación: quitar el filtro en cualquiera de los dos parsers la
pone roja (`docs/11_auditoria_tests.md`).
