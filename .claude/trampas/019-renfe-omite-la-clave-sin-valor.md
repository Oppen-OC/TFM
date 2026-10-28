---
id: 019
titulo: Renfe omite la clave que no tiene valor, no la manda a null
estado: cerrada
capa: fuentes
detectada: 2026-10-23
test: tests/test_ingest.py::test_renfe_tolera_trenes_de_valencia_sin_una_clave
---

## Síntoma

`parse_renfe` lanzaba `KeyError` en 254 payloads del 17/08 al 18/10:
`codEstDest` (154), `porAvanc` (97) y `codEstOrig` (3), con 1 a 3 trenes en
toda la flota y ninguno de València. Los de `porAvanc` y `codEstOrig`, de
madrugada; 128 de los de `codEstDest`, de día, en cinco episodios de 1,5 a 5 h
en que Renfe sirvió la flota con uno o dos trenes (bitácora 062). `reprocesar`
los contaba en `metrics/curar.json` y seguía; nadie lo vio hasta que
`medir_completitud`, que no captura la excepción, se cayó (issue #4).

## Causa

Un tren sin valor en una clave no la trae a `null`: la omite. En 4 días de
crudo, 0 nulos explícitos en 1.591.665 trenes, y a 10.303 de los 106.551 de
València les falta `porAvanc` (commit 2dcb177). `pd.DataFrame(trenes)` crea la
columna si algún tren de la flota nacional la trae; si no la trae ninguno, no
existe, y la lista fija de columnas de salida falla. Pasa cuando la flota es de
uno o dos trenes. El filtro de núcleo quita filas, no columnas.

## Por qué se vuelve a caer aquí

De día no se ve: cualquier muestra, y el fixture, trae todas las claves, y al
tren que le falta una pandas lo pinta como `NaN`, así que parece que Renfe
manda `null` (así lo decía `docs/01`). La columna solo desaparece cuando la
flota entera es uno o dos trenes, de madrugada o cuando la fuente se degrada.
El error no da la cara: `reprocesar` y el
colector lo capturan, y queda un contador agregado que el pipeline no lee.
Con trenes de València, el sondeo entero se habría perdido igual de callado.

Y el arreglo obvio tiene su propia trampa: completar a nulo todas las claves,
`nucleo` incluida, convierte un cambio de esquema en 0 filas sin error, que es
la [003](003-raiz-renfe-es-objeto.md) por otro camino.

## Guardia

`tests/test_ingest.py::test_renfe_tolera_trenes_de_valencia_sin_una_clave`
quita cada una de las 13 claves de todos los trenes del fixture real y exige
las filas de València con la columna a nulo; mutantes 195 y 197.
`tests/test_ingest.py::test_renfe_sin_nucleo_en_toda_la_flota_falla` exige
`KeyError` si falta `nucleo`; mutante 196.
