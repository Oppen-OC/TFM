---
id: 020
titulo: La clave de sondeo por la marca máxima tira la estación que publica con una marca anterior
estado: cerrada
capa: fuentes
detectada: 2026-11-08
test: tests/test_ingest.py::test_la_estacion_que_llega_tarde_es_un_sondeo_nuevo
---

## Síntoma

En los 120 sondeos de la capa 157 del 06/11, la clave por la mayor marca da 25
sondeos distintos donde hay 32: se pierden 3 de las 64 lecturas, todas de W02, y
12 de AEMET entran 4-6 min tarde (bitácora 063). Ningún error: las respuestas
perdidas cuentan como `dup`.

## Causa

`clave_sondeo` identificaba un sondeo con marca propia por `ts_utc.max()`. En la
capa 157 cada estación publica a su ritmo, y una que publica con una marca
anterior al máximo vigente (AEMET, o W02 cuando W01 ya marcó la hora) no cambia
el máximo: su respuesta se descarta como duplicada.

## Por qué se vuelve a caer aquí

El máximo es la clave correcta en Renfe y Valenbisi, donde la capa entera se
refresca de golpe, y `clave_sondeo` es compartida: una fuente nueva con `ts_utc`
la hereda sin tocar nada. El síntoma se parece a la salud: sondeando cada 5 min
una capa que publica cada 10, la mitad de las respuestas ya son `dup` legítimos.
Y el crudo está entero, porque se guarda antes de parsear: lo que falta es la
tabla curada, y `reprocesar` la reconstruye igual de corta porque usa la misma
clave.

El arreglo tiene su cara: la rama por estación se elige por `fecha_carg`, no por
`fiwareid`, que también trae el tráfico.

## Guardia

`tests/test_ingest.py::test_la_estacion_que_llega_tarde_es_un_sondeo_nuevo`
(06/11, W03 publica su lectura de las 16:10 con el máximo en las 17:30) exige
claves distintas; mutante 203.
`tests/test_ingest.py::test_la_clave_del_trafico_sigue_siendo_el_instante_de_captura`
guarda la condición por `fecha_carg`; mutante 206. Arreglo en 9f9e066.
