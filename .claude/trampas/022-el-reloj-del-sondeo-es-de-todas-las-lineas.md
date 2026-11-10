---
id: 022
titulo: Rastrear un subconjunto de líneas cambia el etiquetado sin error, porque el reloj de cada sondeo es el de todas las líneas
estado: vigente
capa: tracking
detectada: 2026-11-10
test: ninguno
---

## Síntoma

Etiquetar el 01/10 hasta las 18:00 locales solo con las 11 líneas de la parada
2277 da **5.333** pasos de esas líneas; con todas las líneas, **5.334**. Tres
pasos salen solo con todas y dos solo recortados, en la 31 (parada 1, otro
viaje programado) y en la 72 (parada 11, 13 s de diferencia en el retraso).
Hasta las 10:00 sale idéntico. No hay error ni aviso, y dos etiquetados con
todas las líneas son idénticos entre sí: no es azar. Medición en
`docs/bitacora/064-*`.

## Causa

`rastrear` empareja dentro de (línea, trayecto), pero el reloj de cada sondeo
es el `ts_utc` máximo de **todas** sus filas (`tracking.py:629`, y también en
`_coser_alternancias` y `_suavizar_intercambios`, `:285` y `:465`). Al recortar
líneas, ese máximo cambia en 1.025 de 1.615 sondeos (p50 1 s, p90 4 s, máximo
11 s). El reloj entra en el `dt` del predictor, en el tope de huecos y en la
puerta física, así que un empate casi exacto se resuelve de otra forma. Con una
fila fantasma por sondeo que devuelve el reloj de todas las líneas, el recorte
sale idéntico: 5.334 de 5.334.

## Por qué se vuelve a caer aquí

Todo dice que el tracker es separable por línea: solo empareja dentro de
(línea, trayecto) (bitácora 002) y la puerta, la predicción y el coste son por
pareja. Recortar a las líneas que interesan es lo primero que se hace para que
quepa en un ciclo en vivo, y la diferencia es del 0,09 %, plausible y sin
error. Hasta las 10:00 la comprobación sale idéntica: basta mirar solo por la
mañana para darlo por bueno. El plan de la demo lo daba por bueno.

## Guardia

Ninguna. La demo en vivo, que es lo único que recorta líneas, tiene que pasar
el reloj de todas las líneas y un test que exija el mismo etiquetado que con
todas. Mientras tanto, se comprueba con
`uv run python -m project.analysis.medir_ciclo_vivo --dia 2026-10-01 --hasta 18:00 --comprobar-lineas`
(`recorte_con_reloj_identico`).
