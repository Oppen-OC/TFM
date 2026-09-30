---
id: 015
titulo: El día del cambio de hora, las horas del GTFS no se miden desde la medianoche local
estado: cerrada
capa: etiquetado
detectada: 2026-09-30
test: tests/test_etiquetado.py::test_el_dia_del_cambio_de_hora_el_horario_va_con_el_reloj_de_la_calle
---

## Síntoma

El día de servicio del cambio de hora, el horario entero sale desplazado una
hora, sin ningún error. En octubre, un bus que va 45 s tarde casa con el viaje
programado **una hora después**, con 45 s de desfase y un retraso creíble en
cada parada: la etiqueta parece buena y el `trip_id` es de otro viaje. En marzo
no casa con ninguno y se rechaza por `desfase` (−2.954 s). Reproducido con el
feed sintético antes del arreglo: `1_07` en vez de `1_01`.

## Causa

El GTFS mide `arrival_time` desde «mediodía menos 12 h» del día de servicio, no
desde la medianoche (referencia de GTFS Schedule, `stop_times.txt`). Las dos
coinciden siempre menos los dos días de cambio de hora, en que se separan una
hora: el 25/10/2026 el origen son las 01:00 de la madrugada y el 28/03/2027 las
23:00 de la víspera. `etiquetado._medianoche` usaba la medianoche local.

## Por qué se vuelve a caer aquí

«Segundos desde la medianoche» es lo que dice el nombre de la función, lo que
dice `gtfs.a_segundos` y lo que hace cualquiera que sume un `HH:MM:SS` a una
fecha. Es correcto 363 días al año y todos los tests usaban un miércoles de
septiembre. La captura empezó en agosto y sus primeras 32 jornadas no tienen
ningún cambio de hora: el fallo llega con los datos de octubre, cuando el
etiquetado lleva semanas validado, y en las líneas frecuentes no deja ni un
rechazo que mirar.

## Guardia

`test_el_dia_del_cambio_de_hora_el_horario_va_con_el_reloj_de_la_calle`, con el
25/10/2026 y el 28/03/2027: la salida real se escribe a mano en UTC y el retraso
tiene que salir en el viaje programado correcto. Mutante 087.

No cubre la madrugada del 24 al 25/10, que pertenece al día de servicio del
sábado: ahí el origen sí es la medianoche, y si la EMT circula los nocturnos
con el reloj de la calle tras el cambio, el desfase de una hora es de la fuente
y solo se verá en la captura.
