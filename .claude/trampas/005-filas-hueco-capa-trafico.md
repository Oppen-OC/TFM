---
id: 005
titulo: El 8 % de la capa de tráfico son filas hueco, no tramos con estado desconocido
estado: mitigada
capa: fuentes
detectada: 2026-08-16
test: ninguno
---

## Síntoma

La capa de tráfico `OPENDATA/Trafico/192` devuelve 446 filas en cada sondeo. Unas
35 llegan sin `idtramo`, sin geometría y sin `estado`. Contadas como nulos,
inflaban artificialmente el porcentaje de dato ausente de la fuente.

## Causa

No son tramos con estado desconocido: **no son tramos**. Son filas vacías que la
capa emite igualmente. Tramos reales utilizables: **410**.

Medido en `docs/05_hallazgos_primera_captura.md`, sección 3.

## Por qué se vuelve a caer aquí

"446 tramos" es la cifra que aparece en la descripción de la capa y la que se
repite en la documentación del proyecto. Tomarla como denominador es lo natural,
y hace que la calidad del dato parezca peor de lo que es (8 % de ausencia
inventada).

En sentido contrario, es igual de fácil imputar el estado de esas filas o
arrastrarlas como categoría "desconocido" hasta las features, metiendo 35
pseudo-tramos fantasma en el modelo.

Ojo al reportar en la memoria: el denominador correcto para cobertura y
disponibilidad es **410**, no 446. El dato de cobertura espacial del 57,7 % ya
está calculado sobre 410.

## Guardia

Falta. `parse_trafico_estado()` en `demo/sources.py:235` las descarta, pero no hay
test que lo fije: si alguien reescribe el parser, vuelven a colarse sin que nada
avise.

**Pendiente:** test en `demo/selftest.py` con un payload de fixture que incluya
filas hueco, comprobando que el parser devuelve solo las filas con `idtramo`.
Mientras no exista, esta ficha no pasa a `cerrada`.
