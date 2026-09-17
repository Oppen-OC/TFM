---
id: 010
titulo: shape_dist_traveled del GTFS de la EMT no es distancia, es el horario reescalado
estado: cerrada
capa: etiquetado
detectada: 2026-09-04
test: tests/test_mapmatching.py::test_la_abscisa_es_geometria_y_no_shape_dist_traveled
---

## Síntoma

El retraso calculado sale pegado a cero en todas las paradas de todos los
viajes, con la distribución limpia, sin excepciones ni valores raros. Parece un
servicio puntual.

## Causa

`stop_times.txt` y `shapes.txt` traen `shape_dist_traveled` poblado en el 100 %
de las filas, y la especificación GTFS lo define como distancia recorrida sobre
el trazado. En el feed de la EMT **es una función lineal exacta del tiempo
programado** dentro de cada viaje: $R^2 = 1{,}00000$ en los 300 viajes de la
muestra, con una constante propia por viaje de 6,7 a 20,5 unidades por segundo.
Frente a la longitud real de la polilínea que lo acompaña, el cociente va de
1,65 a 4,25 en los 95 trazados: ni siquiera es un cambio de unidad.

Medido en `notebooks/EDA/06_cascada_etiqueta_retraso.ipynb` y `docs/09_gtfs_emt.md`.

## Por qué se vuelve a caer aquí

Es el campo que la especificación dice que hay que usar para interpolar el paso
por parada, viene completo y ahorra el trabajo geométrico entero. Nadie proyecta
posiciones sobre una polilínea si el feed ya trae la abscisa calculada.

Y el fallo es de los que aprueban: si el eje de interpolación es el propio
horario, el paso observado se mide contra sí mismo y el retraso sale
estructuralmente cero, con aspecto de dato bueno. Es el patrón de la trampa 004:
el instrumento miente y el resultado parece excelente.

## Guardia

`tests/test_mapmatching.py::test_la_abscisa_es_geometria_y_no_shape_dist_traveled`:
feed sintético con el campo a tres veces la longitud real de la polilínea. La
abscisa tiene que salir en metros de geometría.

`src/project/gtfs.py` ignora el campo y acumula la longitud de la polilínea.
Verificado por mutación: hacer que la abscisa use `shape_dist_traveled` pone
rojos seis tests (mutante 042, `docs/11_auditoria_tests.md`).
