---
id: 003
tema: puerta · issue #4
fecha: 2026-10-23
fuentes: src/project/ingest/sources.py, src/project/ingest/reprocesar.py, src/project/ingest/collect.py, src/project/analysis/medir_completitud.py, metrics/curar.json, trampas/003
estado: corregido
ronda: 1
nota: 0/1
---

## P1 · dónde se arregla
<!-- concepto: donde-se-arregla-el-parser -->

Ninguno de los 254 payloads con error trae trenes del núcleo 40. Una línea
—devolver vacío si tras el filtro del 40 no queda ningún tren— los deja todos a
cero errores y el curated queda idéntico. ¿Por qué eso no basta como arreglo?
¿Qué pasaría, y dónde se notaría, el día que el defecto llegue en un tren de
València?

**Respuesta:**

> Porque unicamente trata los 254 payloads ya vistos, no previene nuevos, en
> curated.json, en una variable aditiva.

**Veredicto:** a-medias

_Rondas._ Ronda 1, a-medias: acierta el qué —parche del caso visto, rastro
solo en un contador agregado de `curar.json`— y falta el porqué. La columna
solo existe si algún tren de la flota nacional trae la clave, y el filtro del 40
quita filas, no columnas. Falta también la consecuencia: con trenes de València
salta el `KeyError`, `reprocesar` lo cuenta y el sondeo entero desaparece del
curated sin excepción visible. La respuesta completa la obtuvo de otra sesión
antes de la ronda 2, que mediría eco, así que no hay segunda ronda y el concepto
entra en `debilidades.md`.
