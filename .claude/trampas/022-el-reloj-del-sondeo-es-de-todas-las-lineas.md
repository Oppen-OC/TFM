---
id: 022
titulo: Rastrear un subconjunto de líneas cambia el etiquetado sin error, porque el reloj de cada sondeo es el de todas las líneas
estado: cerrada
capa: tracking
detectada: 2026-11-10
test: tests/test_vivo.py::test_el_recorte_conserva_el_reloj_y_los_sondeos_de_todas_las_lineas
---

## Síntoma

Etiquetar el 01/10 hasta las 18:00 solo con las 11 líneas de la parada 2277 da
**5.333** pasos de esas líneas; con todas, **5.334** (3 solo con todas, 2 solo
recortados). Hasta las 10:00 sale idéntico. Sin error, y dos etiquetados con
todas son idénticos entre sí. Medición en `docs/bitacora/064-*`.

## Causa

El reloj de cada sondeo en `rastrear` es el `ts_utc` máximo de **todas** sus
filas (también en `_coser_alternancias` y `_suavizar_intercambios`). Entra en el
`dt` del predictor, en el tope de huecos y en la puerta física.

La fila fantasma que lo corrige también cuenta en la media de `lat` del frame, con
la que `_suavizar_intercambios` escala x: va en la posición media de las filas con
trayecto de su sondeo, no en (0, 0), que desplazaba esa media. Guardia:
`test_la_fila_fantasma_no_desplaza_la_posicion_media_del_frame`.

## Por qué se vuelve a caer aquí

Todo dice que el tracker es separable por línea: empareja dentro de (línea,
trayecto), pero el reloj de cada sondeo es el `ts_utc` máximo de **todas** sus
filas (`tracking.py`), y al recortar cambia en 1.025 de 1.615 sondeos. Recortar
a las líneas que interesan es lo primero que se hace para que quepa en un ciclo
en vivo, y la diferencia, del 0,09 %, es plausible. Mirar solo por la mañana lo
da por bueno.

## Guardia

`tests/test_vivo.py::test_el_recorte_conserva_el_reloj_y_los_sondeos_de_todas_las_lineas`:
`con_reloj_de_todas` añade al recorte una fila fantasma por sondeo con el reloj
de todas las líneas, y el etiquetado recortado tiene que ser el del completo. La
pone roja el mutante 222 (el reloj de solo las líneas recortadas).
