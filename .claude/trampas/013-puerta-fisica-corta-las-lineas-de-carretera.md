---
id: 013
titulo: La puerta física de 70 km/h corta las trayectorias de las líneas que salen por carretera
estado: cerrada
capa: tracking
detectada: 2026-09-23
test: tests/test_tracking_identidad.py::test_un_bus_cuyas_posiciones_llegan_con_retraso_no_se_parte
---

## Síntoma

La línea 24 llegaba a la etiqueta con el 5 % de sus tramos asignados, frente al
33-82 % del resto de líneas con más de 100.000 posiciones. No había ningún
error: sus tramos salían como `corto` y la tasa de éxito publicada (bitácora 024)
los deja fuera del denominador.

## Causa

La puerta `min(SALTO_MAX_M, VEL_MAX_KMH / 3,6 · dt)` medía `dt` solo con el reloj
del sondeo (su `ts_utc` máximo). Cuando la posición de un bus llega atrasada en
un sondeo y al día en el siguiente, el desplazamiento real de ~50 s se divide
entre ~30: un bus a 62,7 km/h por la CV-500 parecía ir a 88,5 y la cadena se
cortaba. Detalle y barrido de candidatos: bitácoras 026 y 028.

## Por qué se vuelve a caer aquí

El reloj del sondeo se eligió a propósito: medir por fila daba pasos de 8 s o
negativos y falsas violaciones de la puerta. Volver a él «por robustez», o subir
`VEL_MAX_KMH` para recuperar la 24, es la reacción natural. Lo primero parte
otra vez las líneas de carretera sin error; lo segundo acepta el salto de 675 m
que un bus a 15 km/h no puede dar (`test_salto_imposible_rompe_la_cadena[550m]`).
El coste de la puerta se midió en total y no por línea (bitácora 003), y la
flota simulada no pasa de 30 km/h: ninguna de las dos cosas lo habría visto.

## Guardia

`_dt_puerta` toma el mayor de los dos relojes, el del sondeo y el de la
posición, en el emparejamiento, en el suavizado y en `dt_s`.
`test_un_bus_cuyas_posiciones_llegan_con_retraso_no_se_parte` exige una sola
trayectoria a un bus a 50 km/h con posiciones atrasadas 20 s un sondeo sí y otro
no. La ponen roja el mutante 075 (solo el reloj del sondeo) y el 072
(`VEL_MAX_KMH = 40`). `test_el_suavizado_mide_el_tiempo_con_el_reloj_de_sondeo`
exige que `dt_s` nunca baje del reloj del sondeo.
