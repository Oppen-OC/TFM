---
id: 018
titulo: Un payload de error del geoportal no es un sondeo
estado: cerrada
capa: fuentes
detectada: 2026-10-22
test: tests/test_completitud.py::test_un_payload_de_error_no_cuenta_como_sondeo
---

## Síntoma

El 13/10 la EMT y la 192 estuvieron 3 h 45 min sin posiciones, de 11:54 a
15:39 UTC, y `medir_completitud` dio el día por completo: 2.845 sondeos de
2.880 y ningún hueco de más de 15 min. El criterio de día útil del ADR-024 lo
descarta, pero el día entró en la prueba y se evaluó con él. Lo encontró el
tribunal, después de evaluar (corrección del 22/10 al ADR-024).

## Causa

Cuando el geoportal falla, ArcGIS responde `{"error": …}` y el colector, que
guarda el crudo antes de parsear, lo escribe como un payload más, con su
`ts_ingest_utc`. `medir_completitud` contaba líneas del crudo. `reprocesar`
descarta esos payloads porque no traen filas, pero no los cuenta como error:
`metrics/curar.json` dice `errores: 0`.

## Por qué se vuelve a caer aquí

La regla de guardar siempre el crudo antes de parsear es correcta, y por eso
un fallo de la fuente deja el mismo rastro que un sondeo bueno: una línea a su
hora. Contar líneas es lo natural y coincide con los contadores del colector.
Y el bajón de viajes del día en `prepare.json` se lee como servicio reducido
(martes después de festivo) y no como un hueco.

## Guardia

`tests/test_completitud.py::test_un_payload_de_error_no_cuenta_como_sondeo`:
un sondeo es un payload que `parse` convierte en filas. Lo pone rojo el
mutante 183.
