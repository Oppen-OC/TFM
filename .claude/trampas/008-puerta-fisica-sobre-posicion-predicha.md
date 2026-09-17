---
id: 008
titulo: La puerta de velocidad se evalúa sobre la posición predicha, no sobre el desplazamiento real
estado: cerrada
capa: tracking
detectada: 2026-09-01
test: tests/test_tracking_identidad.py::test_la_puerta_fisica_se_respeta_tras_sondeos_perdidos
---

## Síntoma

Autobuses urbanos a más de 100 km/h en la salida del tracker, sin ninguna
excepción ni fila mal formada. Sobre la captura del 16/08/2026, entre 24 y 46
emparejamientos por ventana de 150 sondeos superaban la puerta física, con
máximos de 110,2 km/h y 949 m de desplazamiento.

## Causa

`_emparejar_grupo` construye una única matriz de distancias contra la posición
**predicha** —que es lo correcto para el coste— y aplicaba sobre ella también la
puerta `tope = min(SALTO_MAX_M, VEL_MAX_KMH / 3,6 · dt)`. Con `predictivo=True`
predicción y posición real divergen, así que un candidato lejano entra por la
puerta si está cerca de la extrapolación.

## Por qué se vuelve a caer aquí

**El coste y la restricción responden a preguntas distintas y aquí comparten
matriz.** El coste mide plausibilidad frente a un modelo de movimiento y debe ir
contra la predicción; la puerta es una afirmación física sobre lo que un autobús
puede hacer en 30 s y solo se puede comprobar sobre el desplazamiento real.
Reutilizar la matriz que ya está calculada es la simplificación natural, no un
descuido: el código queda más corto y aparentemente equivalente.

Además no se ve. La violación no rompe nada: produce `dist_m` y `vel_kmh` bien
formados, y el único síntoma es el máximo de una columna que nadie mira. Con
`predictivo=False` ni siquiera existe, porque predicción y posición coinciden;
aparece solo al activar la extrapolación, que es la mejora.

Cualquier restricción futura sobre el emparejamiento —aceleración máxima,
coherencia de rumbo— vuelve a caer aquí si se evalúa sobre la matriz de coste.

## Guardia

`tests/test_tracking_identidad.py::test_la_puerta_fisica_se_respeta_tras_sondeos_perdidos`
—dos sondeos perdidos a cadencia de 60 s— y el caso de 550 m de
`test_salto_imposible_rompe_la_cadena`. Los dos caen si la puerta vuelve a
evaluarse solo sobre la predicha.

Hasta 09/2026 la ficha citaba `test_ningun_desplazamiento_supera_la_puerta_fisica`
y `test_la_puerta_fisica_se_respeta_en_la_flota_simulada`, que **no guardaban**:
sus escenarios van a velocidad constante con pasos de 30 s, predicción y posición
real nunca divergen, y deshacer el arreglo los dejaba en verde. Con pasos de
180 s, ese código acepta 34 desplazamientos por encima de `SALTO_MAX_M`
(`docs/bitacora/012-tres-guardias-de-trampas-cerradas-no-guardan.md`). Es la
misma lección que la ficha, un nivel más arriba: el test de una restricción
tiene que construir el caso en que la restricción importa.

Cifras, comparación antes/después y comando reproducible:
`docs/bitacora/003-puerta-fisica-sobre-la-posicion-predicha.md`.
