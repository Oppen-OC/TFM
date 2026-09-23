---
id: 013
titulo: La puerta física de 70 km/h corta las trayectorias de las líneas que salen por carretera
estado: vigente
capa: tracking
detectada: 2026-09-23
test: ninguno
---

## Síntoma

La línea 24 llega a la etiqueta con el 5 % de sus tramos asignados, frente al
33-82 % del resto de líneas con más de 100.000 posiciones. No hay ningún error:
sus tramos salen como `corto` y la tasa de éxito publicada (bitácora 024) los deja fuera del
denominador. El 20/08, la 24 son 363 trayectorias con una mediana de 13
posiciones; la 31, 227 con 110.

## Causa

`tracking.py` rechaza todo emparejamiento que supere
`min(SALTO_MAX_M, VEL_MAX_KMH / 3,6 · dt)` con el reloj de sondeo: 583 m en un
sondeo de 30 s. En la CV-500 hacia El Saler y El Palmar, el paso entre el final
de una trayectoria y su sucesora es de 773 m de mediana (el 99 % por encima de
70 km/h con ese reloj, 62,7 km/h con el `ts_utc` del propio bus). Es el ritmo
normal de un autobús por carretera, no un error de asignación. Abrir la puerta a
100 km/h y 1.200 m recompone la 24 (363 → 144 trayectorias, mediana 13 → 48) y
no mueve la 31 (227 → 223). Medida y evidencia: bitácora 026.

## Por qué se vuelve a caer aquí

El umbral se calibró, y se validó, para un «bus urbano». La bitácora 003 midió
su coste en un −0,3 % de emparejamientos sobre el total, que es una cifra que
tranquiliza, y no lo desglosó por línea: el coste está concentrado en las líneas que
salen del término por carretera (la 24, y en parte la 25). La flota simulada no
pasa de unos 30 km/h (p90 de 26,7, `docs/11_auditoria_tests.md`), así que ningún
test ve la diferencia entre 70 y 40 km/h (mutante 072).

Es la trampa 006 con otra puerta de entrada. Las líneas 24 y 25 son las peor
cubiertas por sensores de tráfico: perderlas sesga la muestra hacia los
corredores bien cubiertos, a favor de la hipótesis del TFM y sin tocar la
etiqueta de nadie más. Endurecer la puerta tras un caso de 110 km/h es la
reacción natural, y cualquier ajuste de este umbral vuelve a hacerlo.

## Guardia

Ninguna todavía. La que falta: un escenario con un bus a 60-80 km/h por un
trazado recto que exige una sola trayectoria, en `tests/test_tracking.py`, y el
mutante 072 (`VEL_MAX_KMH = 40.0`) pasando a detectado.
