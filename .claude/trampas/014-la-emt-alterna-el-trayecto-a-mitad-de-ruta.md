---
id: 014
titulo: La EMT publica a veces el trayecto contrario para el mismo bus a mitad de ruta
estado: cerrada
capa: fuentes
detectada: 2026-09-23
test: tests/test_tracking_fragmentacion.py::test_la_alternancia_del_trayecto_no_parte_la_trayectoria
---

## Síntoma

La línea 25 salía troceada en cientos de trayectorias de dos o tres posiciones
aun con la puerta física abierta del todo: 465 para 6 buses el 20/08. Sin
ningún error; los trozos acababan como tramos `corto`, fuera del denominador
del éxito. Las posiciones con el texto invertido, proyectadas sobre el trazado
del otro sentido, «retrocedían» y partían el viaje en el etiquetado.

## Causa

La capa publica durante 1-4 sondeos el `trayecto` del sentido contrario para un
bus que sigue su marcha: en la 25, entre el 6,9 y el 9,0 % de sus pasos a mitad
de ruta; también en la 99 y en otras. El tracker agrupa por (línea, trayecto) y
cada racha lo parte en tres. Detalle, cifras y diseños descartados: bitácoras
026 y 029.

## Por qué se vuelve a caer aquí

`trayecto` parece la clave más fiable de la capa, y la que impide que se mezclen
los dos sentidos de una calle (bitácoras 008 y 009). Nada avisa de que a veces
miente, y a mitad de ruta, no solo en cabecera. El arreglo que sale solo,
permitir el cambio de trayecto al emparejar, recupera la 25 y engancha buses de
sentidos opuestos en todas las líneas urbanas: hasta un 25 % menos de
trayectorias sin un solo error visible.

## Guardia

`tracking._coser_alternancias` une A + F + C después de rastrear, sin tocar el
emparejamiento. `test_la_alternancia_del_trayecto_no_parte_la_trayectoria` y
`test_la_alternancia_del_trayecto_se_corrige_al_sentido_real` (eficacia),
`test_coser_la_alternancia_no_mezcla_buses` (seguridad en flota densa) y
`test_la_alternancia_del_trayecto_no_corta_el_viaje` (etiquetado). Mutantes
076-078.
