---
id: 009
titulo: La posición anterior no arrastra cuánto duró el paso que la produjo, así que el predictor extrapola en pasos de snapshot y no en segundos
estado: cerrada
capa: tracking
detectada: 2026-09-16
test: tests/test_tracking.py::test_un_sondeo_que_falta_no_rompe_la_identidad
---

## Síntoma

Emparejamientos erróneos **uno o dos sondeos después** de un hueco en la serie,
nunca en el hueco mismo. Al evaluar el arreglo que descarta los sondeos
truncados, aparecían 4 saltos de identidad y un 3,3 % de trayectorias
contaminadas donde antes había cero; localizados, caían en los snapshots 1009 y
1010, mientras que el sondeo descartado era el 1007 y la transición que lo
salvaba, la 1006 → 1008.

La distancia entre el retraso del síntoma y su causa es lo que hace que se
atribuya al cambio equivocado: la lectura natural era «el arreglo rompe la
identidad», y el arreglo no tenía nada que ver.

## Causa

`rastrear()` guarda en `_plat` / `_plon` la posición del paso anterior y
extrapola con `lat_pred = 2 · lat − _plat`, que es un modelo de velocidad
constante **medido en pasos de snapshot**. Esa fórmula asume que el paso que
produjo `_plat` dura lo mismo que el paso que se va a predecir.

En cuanto un sondeo falta —porque se descartó, porque el colector tuvo un hueco o
porque el emparejador saltó por encima de él— `_plat` pasa a estar dos sondeos
atrás mientras la predicción sigue siendo de uno. El desplazamiento leído es el
doble del real, la extrapolación se pasa de largo, y el candidato correcto deja
de ser el más próximo a la posición predicha.

El arreglo es guardar junto a `_plat` la duración del paso que lo generó y
extrapolar por la razón entre ambas duraciones, que con sondeos regulares vale 1
y reproduce el comportamiento actual de forma exacta.

## Por qué se vuelve a caer aquí

**Un modelo de velocidad constante escrito en pasos de rejilla es correcto
mientras la rejilla sea uniforme, y la rejilla es uniforme el 99,8 % del tiempo.**
La fórmula `2 · lat − _plat` es la expresión canónica del movimiento rectilíneo
uniforme en diferencias finitas: cualquiera la escribe así, y en revisión pasa por
correcta porque lo es, bajo una hipótesis que nadie enuncia.

El colector de la EMT refuerza el engaño: sobre la jornada del 27/08/2026, solo
**5 de 2.749 transiciones** cambian de duración más de 2× (0,18 %), aunque el
máximo llega a 445 s frente a los 31 s medianos. Con esa regularidad, el defecto
casi nunca se manifiesta sobre el dato tal cual llega.

Y está latente, no activo: muerde de verdad al introducir **cualquier** mecanismo
que altere la cadencia —tolerar huecos, descartar sondeos truncados, submuestrear
la serie—, que son justo los cambios que se proponen para reducir la
fragmentación. El defecto no lo causa ese cambio, pero aparece con él, y se le
atribuye.

## Guardia

`tests/test_tracking.py::test_un_sondeo_que_falta_no_rompe_la_identidad` sobre
`simular_flota(huecos=(7,))`: 60 buses, un sondeo que desaparece entero. Con el
bug da **4 saltos y 3,3 % de trayectorias contaminadas**; sin él, cero.

`test_el_hueco_discrimina_de_verdad` fija que el escenario ejercita el defecto:
comprueba que la cadencia deja de ser uniforme (`dt.max() == 2 * dt.min()`) y que
la fragmentación se queda en 1,00, porque esta trampa es **fusión pura** y el eje
de partición es ciego a ella.

Portado verificando que no cambia nada con cadencia regular: mismo `vehicle_id` y
`dist_m` que la versión anterior sobre seis conjuntos, incluidas 22.208
posiciones reales.

Contexto y cifras: `docs/bitacora/010-plat-sin-su-dt.md`.
