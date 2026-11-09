---
id: 021
titulo: Decidir la convención con una estación que llega una hora tarde desplaza el sondeo +1 h sin aviso
estado: cerrada
capa: fuentes
detectada: 2026-11-09
test: tests/test_ingest.py::test_meteo_de_aemet_en_hora_local_no_se_lee_como_utc
---

## Síntoma

En invierno, con la capa 157 servida en hora local y sin W01/W02, una lectura de
AEMET con 61 min de retraso real se lee como UTC con 1 min de latencia:
`resolver_convencion` devuelve `YA_EN_UTC` y las cinco filas del sondeo quedan
una hora desplazadas, con `tz_convencion` limpio. No se ha visto en datos: lo
encontró la revisión final de la rama de la capa 157 (arreglo en c4bbcd0).

## Causa

La capa 157 decide con la lectura más fresca (`agg="min"`) porque mezcla redes de
ritmos distintos. Las tres de AEMET aparecen con 51-91 min de retraso (bitácora
063), del tamaño del desfase de invierno (CET, 60 min). Servida en hora local y
leída como UTC, una lectura con retraso L da L − 3.600 s, dentro de la horquilla
[−180, 2.400] s si L está entre 57 y 100 min; la lectura correcta, L, cae fuera.
Solo cuadra la equivocada.

## Por qué se vuelve a caer aquí

La lección de la [002](002-emt-alterna-convencion-horaria.md) es decidir respuesta
a respuesta por la latencia, y bien aprendida: la convención la pone quien sirve,
así que una fila vale de testigo para todas. Lo que no dice es que el testigo
necesita una latencia lejos del desfase. Con las municipales presentes no pasa;
solo cuando faltan o se paran, en hora local y en invierno (en verano el desfase
es de 2 h y AEMET no llega tan tarde). La captura de noviembre venía en UTC, y el
test que prometía `DUDOSA` sin las municipales solo cubría ese caso.

## Guardia

`tests/test_ingest.py::test_meteo_de_aemet_en_hora_local_no_se_lee_como_utc`
exige `DUDOSA` con solo AEMET, en hora local y a 61 min; mutante 207. La
convención se decide solo con W01/W02 (`ESTACIONES_MUNICIPALES`), que llegan a
~7 min: leídas al revés salen a −53 o +67 min, fuera de la horquilla.
`tests/test_ingest.py::test_meteo_con_w02_parada_decide_la_municipal_mas_fresca`
guarda que entre ellas decide la más fresca; mutante 205.
