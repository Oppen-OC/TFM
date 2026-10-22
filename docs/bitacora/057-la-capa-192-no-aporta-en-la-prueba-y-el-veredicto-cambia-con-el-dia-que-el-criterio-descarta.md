---
id: 057
titulo: En la prueba prerregistrada (07-19/10 sin el 13/10), la capa 192 no aporta, con un IC por días de [−0,30, +0,01] s; con el 13/10 dentro, que el criterio de día útil descarta, la regla se cumplía por 3 milésimas
fecha: 2026-10-22
tipo: medicion
capa: pipeline
capitulo: resultados
impacto: alto
estado: aceptado
evidencia: metrics/trafico.json, metrics/horizontes/h{2,3,5,10}/{trafico,eval,clasificador}.json en 0e849cb (12 días) y en 18e3927 (13 días); sin redondear, uv run python -m project.analysis.primaria_sin_redondeo --horizonte 5
trampa: 018
---

## Qué se observó

Prueba del ADR-024, días de servicio del 07 al 19/10 sin el 13/10: **12 días**.
- Horario `19-09-2026`.
- Modelos entrenados hasta el 04/10, con la validación del 28/09 al 04/10.
- Las diferencias son el MAE con la 192 menos el MAE sin ella, sobre las
  mismas filas de `features.poblacion`.

**Primaria (*h* = 5, con sensor): no hay aportación.**

| | filas | MAE sin | diferencia | IC por viajes | IC por días |
|---|---|---|---|---|---|
| con sensor (primaria) | 312.609 | 56,03 s | −0,128 s (−0,23 %) | [−0,172, −0,082] | **[−0,295, +0,0118]** |
| sin sensor (control) | 26.701 | 46,13 s | −0,124 s (−0,27 %) | [−0,230, −0,012] | [−0,254, −0,004] |
| congestión observada (secundario) | 12.426 | 98,00 s | −4,85 s (−4,95 %) | [−5,55, −4,15] | [−7,32, −2,98] |
| fluido observado | 342.674 | 54,18 s | +0,04 s | [+0,01, +0,08] | [−0,05, +0,18] |

- El intervalo por días contiene el cero.
- Aunque no lo contuviera, la primaria no supera al control: una mejora del
  mismo tamaño aparece en filas sin ningún sensor en el recorrido.
- Donde la capa veía fluido, el modelo con tráfico es algo **peor** (IC por
  viajes).
- Toda la mejora del conjunto sale del 3,2 % de filas con congestión observada.

**Por horizonte (12 días):**

| *h* | con sensor | IC por días | sin sensor | congestión observada | IC por días |
|---|---|---|---|---|---|
| 1 | −0,04 s | [−0,07, −0,02] | −0,03 | −1,64 s (−3,8 %) | [−2,45, −0,94] |
| 2 | −0,10 s | [−0,15, −0,06] | −0,00 | −3,14 s (−5,2 %) | [−4,53, −1,91] |
| 3 | −0,16 s | [−0,24, −0,09] | −0,14 | −4,19 s (−5,6 %) | [−6,05, −2,53] |
| 5 | −0,13 s | [−0,30, +0,01] | −0,12 | −4,85 s (−5,0 %) | [−7,32, −2,98] |
| 10 | −0,26 s | [−0,54, −0,05] | −0,24 | −6,59 s (−4,7 %) | [−10,1, −3,41] |

Solo con *h* = 2 el estrato con sensor se separa del control.

**Confirmación de la v2** (modelo menos persistencia más sesgo del tramo, todas
las filas de la población):
- *h* = 1: −1,46 s;
- *h* = 2: −1,81 s;
- *h* = 3: −2,39 s;
- *h* = 5: −3,37 s (−5,8 %), IC por días [−3,77, −2,92];
- *h* = 10: −5,56 s.

Ningún intervalo contiene el cero.

**Clasificador de más de 5 min** (ADR-025, descriptivo, estrato titular):
- **Frente a la persistencia del tramo**, F1 de +0,005 a +0,046 de *h* = 2 en
  adelante, con los intervalos lejos del cero. Con *h* = 1 empata.
- **Frente a la regresión umbralizada**, empata o pierde de *h* = 1 a *h* = 5,
  y gana con *h* = 10 solo por viajes: +0,0096, IC por viajes [+0,002, +0,018].

**Con 13 días** (18e3927, el 13/10 dentro), la primaria daba −0,14 s, con un IC
por días de [−0,29, −0,0026]: cumplía la regla por 2,6 milésimas.

## Cómo se midió

```bash
git show 0e849cb:metrics/horizontes/h5/trafico.json      # 12 días (primaria)
git show 18e3927:metrics/horizontes/h5/trafico.json      # 13 días (descriptiva)
uv run python -m project.analysis.primaria_sin_redondeo --horizonte 5
```

- `dvc repro` de los stages `evaluate_trafico`, `evaluate_trafico_h`,
  `evaluate_h` y `evaluate_clasificador(_h)`. Una ejecución con 13 días
  (18e3927) y otra con 12 (0e849cb), esta solo por la regla de día útil,
  escrita antes de calcularla (15de1c8).
- `evaluate.diferencia` redondea a dos decimales, y el extremo por días salía
  `-0.0` con 13 días y `0.01` con 12. Los extremos exactos salen de
  `project.analysis.primaria_sin_redondeo`: repite `comparacion_trafico` con la
  semilla 0 y 1.000 réplicas y reproduce `trafico.json`.
- Antes de evaluar se comprobó:
  - que `validacion.dias` = 28/09-04/10 en los 15 `.pkl`;
  - que `dias.test` = 12;
  - que las tablas de entrenamiento eran idénticas byte a byte a las de los 13
    días. Los stages de entrenamiento se volvieron a firmar con `dvc commit -f`,
    sin reentrenar.

## Por qué importa

- **Es la pregunta de investigación.** A unos 7 min vista, el estado de la 192
  no reduce el error de forma que se pueda distinguir del ruido entre días.
- **La señal existe, pero es rara.**
  - Donde la capa veía congestión, el error baja un 5 % en todos los horizontes.
  - Esas filas son el 3 % de la prueba.
  - En fluido, la capa añade varianza.
- **La primaria se diseñó contra el 82 % de filas con sensor.** Ahí la
  congestión casi nunca aparece, así que el diseño no podía ver el efecto
  donde lo hay. Es el resultado: la cobertura geométrica no es exposición a la
  congestión.
- **El veredicto dependía del día que la regla descarta.** Con 13 días la regla
  se cumplía por 2,6 milésimas. Ese margen es menor que el error de Monte Carlo
  del percentil con 1.000 réplicas, que el tribunal estimó en unos 0,006 s. Sin
  el criterio fijado de antemano, el 13/10 decidía el titular.
- **Hay variabilidad que el intervalo no recoge.** Cambiar la semilla del
  entrenamiento mueve la diferencia unos 0,05 s (bitácora 045). Es del orden de
  la primaria y no entra en el intervalo.

## Qué se hizo / qué queda abierto

Hecho:
- El 13/10 sale de toda tabla (`features.excluir_dias`, mutante 182).
- La trampa 018 y su guardia: el instrumento contaba los payloads de error como
  sondeos.
- El resultado se anota en el ADR-024.

Abierto, como límites declarados:
- **Contraste del GTFS:** bitácora 058.
- **Estrato con sensor.** `trafico_cubierto_m` suma los solapes de tramos
  superpuestos. El estrato mide metros de tramo por metro de recorrido, no la
  fracción del recorrido cubierta. Está así desde la enmienda del 10/10 y no se
  ha medido la diferencia.
- **Festivos.** La prueba lleva dos, el 09 y el 12/10, y la validación ninguno.
- **Hueco de la 192 el 16/10**, de 08:28 a 09:44 UTC: deja filas sin tráfico
  observado.
- **La v2 es la configuración congelada reentrenada hasta el 04/10,** no el
  artefacto evaluado en la 043.

Cualquier análisis posterior de la prueba es exploratorio.

## Para la memoria

> La aportación del estado del tráfico se evaluó en una prueba nueva, del 7 al
> 19 de octubre, con la métrica primaria, el estrato, las variables y el
> criterio de descarte de días fijados y publicados antes de capturarla. A
> cinco paradas vista (unos siete minutos) y en el 82 % de las predicciones
> cuyo recorrido está instrumentado por la capa de estado del tráfico, el
> modelo con tráfico reduce el error absoluto medio en 0,13 s sobre 56,0 s
> (−0,23 %). El intervalo del 95 % remuestreando viajes excluye el cero
> ([−0,17, −0,08] s), pero el que remuestrea días lo incluye ([−0,30, +0,01]
> s), de modo que, según el criterio prerregistrado, el tráfico no aporta. Las
> predicciones sin ningún sensor en el recorrido, que sirven de control,
> mejoran lo mismo (−0,12 s): la pequeña ganancia corresponde a la diferencia
> entre los dos modelos y no a la información de congestión. La señal aparece
> donde la capa veía congestión en el momento de predecir: allí el error baja
> un 5 % en todos los horizontes, de 1,6 s a una parada a 6,6 s a diez, con
> intervalos lejos del cero. Pero esas predicciones son el 3 % de la prueba, y
> donde la capa veía tráfico fluido el modelo con tráfico es ligeramente peor.
> La ventaja del modelo frente a la persistencia corregida por el sesgo del
> tramo se confirma en la prueba: 3,4 s a cinco paradas (−5,8 %), con
> intervalos lejos del cero en todos los horizontes. El protocolo incluía un
> criterio de día útil: un día se descarta si la captura de la flota tiene un
> hueco de más de una hora. Ese criterio se aplicó tarde. Una caída del
> geoportal de 3 h 45 min el 13 de octubre pasó inadvertida porque el
> instrumento contaba como sondeos las respuestas de error. Con ese día dentro,
> el intervalo por días excluía el cero por 0,003 s, un margen inferior al
> error de Monte Carlo del propio intervalo. El resultado que se informa es el
> de los doce días que el criterio deja, y el de trece se publica como
> descriptivo.
