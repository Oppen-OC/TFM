---
id: 011
titulo: La primera captura de un sondeo de la EMT puede ser el bloque a medio reinsertar
estado: cerrada
capa: fuentes
detectada: 2026-09-18
test: tests/test_persistencia.py::test_reprocesar_completa_el_sondeo_que_llego_a_medias
---

## Síntoma

Dos capturas seguidas con el mismo `snapshot_id` parecen el mismo sondeo servido
dos veces, y quedarse la primera parece deduplicar. En 1.200 de 77.952 sondeos
(15/08-18/09) la primera trae sólo el prefijo de `gid` del bloque, con una
mediana del 48 % de sus filas. La segunda trae el bloque entero. Quedarse la
primera tira 109.063 posiciones sin error alguno: salen sondeos parciales que
el tracker absorbe con `tolerar_hueco` y que parecen ruido de la fuente.

## Causa

La tabla de la capa se trunca y se reinserta en cada refresco (trampa 001), en
orden de `gid`. Una consulta a mitad de la reinserción ve los `gid` ya escritos,
que incluyen el mínimo: el mismo `snapshot_id` que el bloque completo. Cifras y
método en `docs/bitacora/020-la-emt-sirve-el-bloque-a-medio-reinsertar.md`.

## Por qué se vuelve a caer aquí

"Misma clave, me quedo la primera" es la deduplicación de manual, y es
exactamente la que escribió el colector (`collect.recordar`). La clave dice que
es el mismo refresco, y lo es: lo que cambia es cuánto del refresco llegó.
Comparar las huellas de las dos capturas tampoco lo delata a simple vista, porque
el 9 % de las repeticiones distintas son sólo la alternancia horaria de la
trampa 002. Y el colector de la Raspberry sigue quedándose la primera a
propósito: quien lea su curated en vez del reprocesado vuelve a tener el
problema.

## Guardia

`tests/test_persistencia.py::test_reprocesar_completa_el_sondeo_que_llego_a_medias`:
el colector recibe un sondeo a medias seguido del bloque completo, y
`reprocesar` debe quedarse el bloque entero sin mezclar filas de dos capturas.
La pone roja el mutante 055, que vuelve al criterio de la primera captura.
