---
id: 034
titulo: Medir el horario desde la medianoche habría asignado, el día del cambio de hora, el 77,5 % de los viajes a otro viaje programado sin un solo error; el GTFS cuenta desde «mediodía menos 12 h»
fecha: 2026-09-30
tipo: anomalia
capa: etiquetado
capitulo: metodologia
impacto: medio
estado: resuelto
evidencia: uv run python -m project.analysis.medir_cambio_hora; uv run pytest tests/test_etiquetado.py -k cambio_de_hora
trampa: 015
---

## Qué se observó

El etiquetado convertía las horas del GTFS en instantes sumándolas a la
medianoche local del día de servicio. El GTFS las cuenta desde «mediodía menos
12 h», y las dos referencias se separan una hora los dos días de cambio de hora
(causa y guardia: trampa 015). La captura cruza el del 25/10/2026.

**Contrafactual sobre una jornada real**, el domingo 30/08: el mismo día,
etiquetado sobre las mismas trayectorias con el origen bueno y con el origen una
hora antes, que es lo que habría ocurrido el 25/10.

| de los 2.837 viajes asignados con el origen bueno | | |
|---|---|---|
| asignados a **otro** viaje programado | 2.200 | **77,5 %** |
| asignados al mismo | 0 | 0 % |
| rechazados por margen | 393 | 13,9 % |
| rechazados por desfase | 123 | 4,3 % |
| rechazados por conflicto | 121 | 4,3 % |

Otros 74 tramos que no estaban asignados pasan a estarlo. De los 64.477 pasos
por parada quedan 51.186, todos con aspecto de dato bueno. En los 49.633 que
coinciden en viaje y parada:

- el horario contra el que se mide se va **+3.660 s** de mediana: el viaje
  programado una hora después;
- el retraso sale con un error absoluto de **238 s** de mediana y 586 s de p90;
- solo el **15,4 %** queda a menos de 60 s del retraso correcto.

Ese día el retraso correcto tiene una mediana absoluta de 96 s y una desviación
típica de 175 s: el error supera a lo que se quiere medir.

Con el feed sintético de los tests, antes del arreglo: un bus 45 s tarde sobre
el viaje de las 07:10 casa el 25/10/2026 con el de las 08:10, con 45,8 s de
desfase; el 28/03/2027 se rechaza por desfase (−2.954 s).

## Cómo se midió

```bash
uv run python -m project.analysis.medir_cambio_hora          # 30/08, domingo
uv run pytest tests/test_etiquetado.py -k cambio_de_hora
```

`medir_cambio_hora` rastrea el día una vez y llama dos veces a
`etiquetado.etiquetar`, la segunda con `_medianoche` desplazada una hora en
memoria; los `viaje_id` son los mismos en las dos y se comparan uno a uno.

**El instrumento se comprobó antes que la cifra.** La pasada con el origen bueno
da 64.477 pasos y 2.837 viajes asignados, los mismos que
`data/interim/pasos/date=2026-08-30` y `viajes/`. El sentido del desplazamiento
coincide con el del test sintético: el viaje de una hora después.

Que el arreglo no toca lo ya etiquetado: la función devuelve el mismo instante
en las 35 fechas del 15/08 al 18/09, y reprocesar el 20/08 y el 16/09 da
`emt_tracked`, `viajes` y `pasos` idénticos fila a fila a los de `data/interim`
(commit `c596688`).

## Por qué importa

- **No da la cara.** No hay excepción ni caída de cobertura que mirar: tres de
  cada cuatro viajes siguen saliendo asignados, con un retraso de magnitud
  creíble. La tasa de éxito del día habría bajado del orden de 20 puntos, dentro
  de lo que ya varía entre periodos (bitácora 024).
- **Un día entero de etiquetas falsas.** El error mediano, 238 s, es seis veces
  el MAE de la persistencia (37,6 s, bitácora 030). Si ese día cayera en un
  conjunto de prueba de cinco, sería una quinta parte de la evaluación.
- **El límite estaba escrito y nadie lo vigilaba.** El docstring decía «ningún
  cambio de hora cae en la captura (el próximo es el 25/10)». Era cierto el día
  que se escribió; la captura siguió. Se encontró revisando docstrings, no por
  un test ni por una cifra.
- La cifra es de un domingo con horario de verano. El 25/10 circula el de
  invierno: la proporción exacta será otra, el orden de magnitud no.

## Qué se hizo / qué queda abierto

Hecho: el origen es «mediodía menos 12 h» (`2444b92`), el test con los dos
cambios de hora y la salida real escrita a mano en UTC, la trampa 015, el
mutante 087 (detectado, `08e4ff1`) y el medidor `analysis/medir_cambio_hora.py`.

Abierto:

- **La madrugada del 24 al 25/10.** Pertenece al día de servicio del sábado,
  donde el origen sí es la medianoche y el código coincide con la norma. Si la
  EMT circula los nocturnos con el reloj de la calle después del cambio, saldrá
  un desfase de una hora que es de la fuente. No lo guarda un test: se mide con
  `medir_etiquetado` sobre esas dos jornadas cuando se sincronice la captura.
- Buscar otros límites escritos con fecha en docstrings y fichas.

## Para la memoria

> La especificación GTFS no mide las horas de paso desde la medianoche, sino
> desde doce horas antes del mediodía del día de servicio, de modo que el horario
> coincida con la hora oficial también tras un cambio de hora. Ambas referencias
> coinciden todos los días salvo los dos del año en que cambia la hora, en los
> que difieren sesenta minutos. El etiquetado empleaba inicialmente la
> medianoche. Para cuantificar el efecto antes de que la captura alcanzara el
> cambio del 25 de octubre, se reetiquetó una jornada real desplazando el origen
> una hora: de 2.837 viajes observados correctamente asignados, el 77,5 % quedó
> asociado a otro viaje programado —el de una hora después— y el 22,5 % fue
> rechazado; ninguno conservó su asignación. Los retrasos resultantes diferían
> del valor correcto en 238 segundos de mediana, por encima de la dispersión del
> propio retraso ese día, sin que el procedimiento emitiera error alguno. El
> origen se corrigió conforme a la especificación y se añadió una prueba con
> ambos cambios de hora. El caso ilustra que un procedimiento validado sobre
> semanas de datos puede fallar por entero en un día concreto sin alterar sus
> indicadores agregados.
