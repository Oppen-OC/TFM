---
id: 012
titulo: Una columna calculada fuera de rastrear no se pega por posición de fila
estado: cerrada
capa: tracking
detectada: 2026-09-18
test: tests/test_etiquetado.py::test_el_orden_de_las_filas_de_entrada_no_cambia_la_etiqueta
---

## Síntoma

La bitácora 017 dio, en jornada real, 7.658 → 7.793 trayectorias y una mediana
de 20,84 → 19,98 min al añadir la abscisa en una segunda pasada: una mejora
modesta y creíble. Era falsa: al 99,7 % de las filas le llegó la abscisa de otra.
Bien alineada, la segunda pasada no cambia nada (bitácora 023).

## Causa

`rastrear` ordena por `snapshot_id` (estable, trampa 004) y **reinicia el
índice**. La abscisa se calculó sobre su salida y se pegó con `np.where(...)`
a la entrada ORIGINAL, que venía de DuckDB con un único par de filas fuera de
orden. Desde ese par, cada fila recibió la abscisa de su vecina.

## Por qué se vuelve a caer aquí

ADR-012 manda exactamente eso: rastrear, emparejar y volver a rastrear con la
columna nueva. Pegarla a la entrada es lo natural, y el propio banco lo hace con
la flota simulada, donde es correcto porque la simulación llega ordenada. Con
datos reales no falla ni avisa: da una mejora pequeña, que es lo que se espera
de una mejora.

## Guardia

`tests/test_etiquetado.py::test_el_orden_de_las_filas_de_entrada_no_cambia_la_etiqueta`:
la misma flota, barajada, tiene que dar los mismos retrasos. La pone roja el
mutante 069, que pega por posición columnas de la entrada a la salida de
`rastrear`. `banco_tracker --real-abscisa` construye la segunda pasada desde la
salida de la primera.
