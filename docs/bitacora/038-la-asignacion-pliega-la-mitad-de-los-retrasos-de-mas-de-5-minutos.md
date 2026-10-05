---
id: 038
titulo: La asignación al viaje programado pliega al viaje siguiente un 3-4 % de los viajes sin que nada lo delate, y la mitad de los buses que salen con más de 5 min de retraso; la etiqueta pierde justo los retrasos grandes
fecha: 2026-10-05
tipo: limitacion
capa: etiquetado
capitulo: metodologia
impacto: alto
estado: abierto
evidencia: PYTHONIOENCODING=utf-8 uv run python -m project.analysis.medir_asignacion (salida en auditoria/resultados/asignacion_c6f06c7.txt)
trampa: —
---

## Qué se observó

`_asignar_tramo` asigna cada tramo observado al viaje programado cuya salida
explica mejor las tres primeras paradas, con 120 s de ventaja sobre el segundo.
Un bus que va más de medio intervalo tarde queda más cerca del viaje
**siguiente**: se le asigna ese viaje, con margen de sobra y un retraso creíble
(δ − H, aparentemente adelantado). Es el sesgo declarado en el abierto 3 de la
024. Sobre la salida de `c6f06c7` (64.887 viajes asignados, 1.435.851 pasos):

| | asignados | rechazos por margen observados | predichos | pliegues |
|---|---|---|---|---|
| todo | 64.887 | 2.379 | 2.342 | **4,1 %** |
| H ≤ 8 min | 5.205 | 798 | 681 | 11,2 % |
| 8-15 min | 40.285 | 1.447 | 1.523 | 4,4 % |
| 15-30 min | 14.917 | 132 | 133 | 1,7 % |
| > 30 min | 4.480 | 2 | 5 | 0,0 % |
| punta (7-9 y 13-15 h) | 14.020 | 512 | 550 | 4,0 % |

- **Pliegues: unos 2.670 viajes (4,1 %), 59.000 pasos.** Parte pierde después
  el conflicto con el bus que de verdad cubría el viaje y da la cara: el 33,9 %
  de los 2.414 conflictos aparece adelantado más de 120 s, frente al 3,5 % de
  los asignados. Son unos 734 pliegues cazados.
- **Sin delatar: unos 1.936 viajes (3,0 %).** Como mínimo 256 (0,4 %), si todos
  los conflictos fueran pliegues.
- **De los buses que salen con más de 300 s de retraso, el 52,3 % se pliega y
  el 20,4 % se rechaza por margen.** Ese 52,3 % se cuenta antes de descontar
  los conflictos.
- Cola del retraso de salida, corregida del truncamiento: P(δ > 60 s) = 0,49;
  P(δ > 300 s) = 0,062; P(δ > 600 s) = 0,020.

## Cómo se midió

```bash
PYTHONIOENCODING=utf-8 uv run python -m project.analysis.medir_asignacion
```

Por qué la cifra es creíble:

- **El estimador.** Un viaje bien asignado es una observación de δ truncada en
  (H − 120)/2, con H distinto en cada viaje. El estimador de Lynden-Bell
  recupera la cola P(δ > x) sin suponer su forma, solo que δ no depende de H.
  Cada viaje bien asignado representa 1/P(bien | H) buses de su intervalo.
- **La validación.** Con la misma cola se predicen los rechazos por margen, que
  sí se ven en `viajes`. Salen **2.342 frente a 2.379**, y por banda de
  intervalo, 133 frente a 132 o 1.523 frente a 1.447. La estimación se calibra
  por esa razón (1,016 en total).
- **El estimador se probó antes que la cifra.** En
  `tests/test_medir_asignacion.py`, una flota sintética con retrasos decididos
  por el test se pliega como lo hace `_asignar_tramo`. La cota bruta nunca
  queda por debajo de la verdad: se pasa entre 1,1 y 2,2 veces, porque el mal
  asignado parece un adelanto y engorda la otra cola. Los rechazos predichos se
  pasan en la misma proporción. Calibrada, devuelve la verdad a ±15 % con tres
  colas distintas. Mutantes 093-095.
- **El instrumento mintió una vez.** La primera versión contaba como
  competidores en la cabecera a los viajes que **terminan** en ella: toda
  primera parada es final de los del otro sentido. Dio un intervalo mediano de
  8 min y el 92 % de los viajes en la banda ≤ 8 min. Corregido, el intervalo
  mediano es de 14 min en agosto y 11 en septiembre.

Supuestos que pueden mover la cifra:

- **δ independiente de H.** En la banda ≤ 8 min hay un 17 % más de rechazos de
  los predichos, así que la cola es más gruesa donde más frecuencia hay. La
  calibración por banda lo recoge.
- **H en la primera parada y sin variantes de otro trazado.** El H real es
  menor o igual, así que la cota queda corta si algo.
- **El 52,3 % se calcula a la salida.** Es el retraso en las paradas de
  referencia, no en cada paso.

## Por qué importa

- **La persistencia no lo nota y el modelo sí.** Un viaje plegado se desplaza
  entero, así que la diferencia entre paradas consecutivas no cambia. Pero el
  nivel del retraso de ese viaje pasa a ser negativo.
- **La etiqueta pierde justo los retrasos grandes.** Tres de cada cuatro buses
  que salen con más de 5 min de retraso se pliegan o se rechazan. La variante
  binaria (> 5 min) del endpoint tiene sus positivos recortados por
  construcción. Y la congestión que el TFM quiere medir es lo que produce
  esos retrasos.
- **Se acumula con la frecuencia.** Las líneas de 8 min o menos pliegan el
  11 %; las de más de 15 min, menos del 2 %. Un resultado medido sobre todas
  mezcla dos calidades de etiqueta.

## Qué se hizo / qué queda abierto

Hecho: el medidor `analysis/medir_asignacion.py`, su test con verdad
sintética y los mutantes 093-095. No se ha tocado `etiquetado.py`.

Abierto:

- **Evaluar por banda de intervalo** como estrato, igual que la cobertura de
  sensores (ADR-018). Las bandas de más de 15 min son la referencia limpia.
- **Usar la continuidad del vehículo.** El viaje anterior del mismo bus fija
  cuál le toca después. El GTFS no trae `block_id` y el tracker parte en la
  cabecera (`xfail` de `test_tracking_fragmentacion.py`), así que hoy no se
  puede.
- **Declarar el sesgo de la variante binaria** antes de publicar sus métricas.
- Si se corrige algo, la guardia sería
  `test_un_bus_mas_de_medio_intervalo_tarde_no_se_asigna_al_siguiente` en
  `tests/test_etiquetado.py`, con un viaje programado a 6 min y un bus que sale
  con 5 min de retraso.

## Para la memoria

> La asignación de cada viaje observado al viaje programado se basa en la
> proximidad de los horarios de paso por las primeras paradas. Cuando un
> autobús acumula un retraso superior a la mitad del intervalo de la línea,
> queda más próximo al servicio siguiente que al propio y se le asigna aquel,
> con un retraso aparente pequeño y negativo. Este error no es observable
> directamente, pero puede acotarse: los viajes correctamente asignados
> constituyen una muestra del retraso truncada en la mitad de su intervalo, y
> el estimador de Lynden-Bell recupera su distribución. El modelo así ajustado
> predice 2.342 rechazos por margen insuficiente frente a los 2.379 observados.
> Se estima que alrededor del 4,1 % de los viajes asignados corresponde en
> realidad al servicio anterior. Descontados los que el propio procedimiento
> detecta como conflicto, quedan sin detectar en torno al 3,0 %. La proporción
> alcanza el 11 % en las líneas con intervalos de ocho minutos o menos, y no
> llega al 2 % en las de más de quince. El sesgo no es neutro: de los autobuses
> que inician el recorrido con más de cinco minutos de retraso, en torno a la
> mitad se asignan al servicio siguiente y una quinta parte se descarta. La
> etiqueta subrepresenta los retrasos grandes, precisamente los asociados a la
> congestión. Por ello la evaluación se presenta estratificada por intervalo de
> paso.
