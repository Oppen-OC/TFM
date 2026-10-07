---
id: 017
titulo: Las variables calculadas en t_obs ven pasos que aún no han llegado
estado: cerrada
capa: pipeline
detectada: 2026-10-07
test: tests/test_features.py::test_t_disp_no_es_anterior_a_ninguna_posicion_que_usa_cruces_de_verdad
---

## Síntoma

La v2 batía al listón por 2,09 s, pero con variables que en tiempo real no
estarían. El retraso de un paso se sabe, de mediana, 80,7 s después de
`t_obs`. Con una parada de horizonte, el 45 % de las filas llega cuando el bus
ya ha pasado por la siguiente. Más de la mitad de la mejora estaba en el primer
paso de cada viaje, cuyo retraso no existe hasta que se asigna el viaje
(bitácora 046).

## Causa

`t_obs` es la salida interpolada de la parada (`etiquetado.cruces`). Para
calcularla hacen falta la primera posición tras el cruce y la siguiente, y el
retraso necesita además el viaje programado, que se elige con los tres
primeros pasos. `features` usaba `t_obs` como «ahora».

## Por qué se vuelve a caer aquí

El orden de los eventos es correcto, y los tests de fuga (mutantes 079-082)
lo guardan. Lo que falla es la disponibilidad: el evento ocurrió, pero el dato
no había llegado. Y se cae dos veces: la primera corrección tomó la posición
que confirma el cruce y no vio que `cruces` usa también la siguiente. Solo un
test contra `cruces` de verdad lo ve.

## Guardia

`tests/test_features.py::test_t_disp_no_es_anterior_a_ninguna_posicion_que_usa_cruces_de_verdad`
y la sección «Disponibilidad» de `tests/test_features.py`. La ponen roja los
mutantes 114-123.
