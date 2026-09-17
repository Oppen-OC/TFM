---
id: 017
titulo: Emparejar sobre el recorrido en vez de sobre el plano quita el 7,6 % de los intercambios de identidad, no el 35 % que aparentaban cinco semillas de ajuste
fecha: 2026-09-18
tipo: medicion
capa: tracking
capitulo: metodologia
impacto: alto
estado: mitigado
evidencia: uv run python auditoria/banco_tracker.py --gtfs --reservadas --etiqueta abscisa
trampa: 007
---

## Qué se observó

La entrada 015 dejó abierto un residuo de intercambios de identidad que el
suavizado no deshace, y señaló la causa probable: dos buses de la misma línea
comparten calle, y eso no se ve en coordenadas sueltas. Con el map-matching
(entrada 016) esa información existe: la abscisa sobre el trazado.

**Primero hubo que construir el árbitro.** `simular_flota` mueve cada bus con
rumbo propio, así que no sirve para esto. `project.analysis.simulacion_gtfs`
pone los buses sobre los **trazados reales del GTFS**, con paradas, ruido,
cadencia irregular y velocidad comercial por línea. Calibrado contra la captura:

| magnitud | simulado | real (laborable) |
|---|---|---|
| pasos parado | 28-30 % | 29 % |
| vecino del mismo grupo p10 | 256-698 m | 611 m |
| vehículos por grupo p50 | 3 | 3 |
| cambio de rumbo p90 | 47° | 57° |
| paso entre sondeos p99 | 32,4 s | 33 s |
| velocidad p50 | 10,5-11,3 km/h | 7,5 km/h |

Sobre ese banco, el tracker de `b57663c` produce 98 saltos en las cinco semillas
de ajuste: el defecto es visible, que es lo que hacía falta.

**La medida que engaña.** Con las semillas de ajuste, emparejar sobre el
recorrido bajaba de 98 a 64 saltos: un 35 %. Con **20 semillas de desarrollo
nuevas** (200-219) la misma configuración daba 195 frente a 196, es decir, nada.
El 35 % era ajuste a cinco semillas.

**Lo que sí generaliza**, con las 20 semillas de desarrollo:

| | con suavizado | sin suavizado |
|---|---|---|
| sin abscisa | 196 | 236 |
| con abscisa | **181** | 195 |

La abscisa y el suavizado de la entrada 015 **se solapan**: cada uno por su
cuenta deja unos 195 saltos y juntos 181. Confirmado una sola vez sobre 20
semillas **reservadas** (9201-9220): **210 → 194, un 7,6 % menos**.

**Dos piezas que el banco obligó a añadir:**

- **Hipótesis de parada.** Sobre el recorrido, un bus que se detiene justo cuando
  otro lo alcanza vuelve a producir el empate exacto de la trampa 007 (correcto
  150 + 0, intercambiado 60 + 90). El coste pasa a ser el menor entre «sigue a su
  ritmo» y «se ha parado», con 15 m de margen para que el ruido no decida.
- **Penalización de adelantamiento** (`PENALIZACION_CRUCE_M`). Un bus que arranca
  tras una parada «avanza» 187 m de golpe, y el intercambio sale **2 m más
  barato** que la verdad: 186 frente a 188. Lo que distingue las dos opciones es
  que el intercambio pone detrás al que iba delante, o sea, inventa un
  adelantamiento. Barrido con semillas de ajuste: 0 m → 86 saltos, 50 → 74,
  100 → 64. El techo no lo pone el ajuste sino un fenómeno real: en el escenario
  de adelantamiento de `tests/test_tracking_abscisa.py` la asignación correcta
  gana por 135 m, y a partir de 120 m el tracker deja de reconocer
  adelantamientos auténticos. Queda en 100.

**Sobre jornadas reales**, con las dos pasadas (rastrear → map-matching →
rastrear con abscisa):

| jornada | trayectorias | mediana (min) | fuera de la puerta | abscisa fiable |
|---|---|---|---|---|
| 17/08 | 7.654 → 7.782 (+1,7 %) | 26,90 → 25,78 | 0 → 0 | 89,6 % |
| 23/08 | 6.001 → 6.069 (+1,1 %) | 23,13 → 22,62 | 0 → 0 | 89,5 % |
| 27/08 | 7.658 → 7.793 (+1,8 %) | 20,84 → 19,98 | 0 → 0 | 87,6 % |

## Cómo se midió

```bash
uv run python auditoria/banco_tracker.py --gtfs --etiqueta abscisa            # ajuste
uv run python auditoria/banco_tracker.py --gtfs --reservadas --etiqueta final  # UNA vez
uv run pytest tests/test_tracking_abscisa.py
```

El banco corre las dos pasadas que hará `prepare.py`: rastrear para tener
identidad aproximada, `mapmatching.emparejar` para la abscisa —`NaN` donde no es
fiable— y rastrear otra vez con ella. Las jornadas reales se midieron con el
mismo procedimiento sobre los días 17, 23 y 27 de agosto.

Comprobación del instrumento: la flota sobre trazados del GTFS se calibró contra
las cifras de las entradas 013 y 016 antes de usarla, y el map-matching sobre
ella acierta el trazado en el 100 % de las posiciones con un error de abscisa de
1,4 m (p90 3 m), así que lo que mide el banco es el emparejamiento y no el
map-matching.

Y un tropiezo del propio método: la primera versión daba a cada bus una velocidad
uniforme entre 6 y 26 km/h, con lo que buses de la misma línea se adelantaban
continuamente y la penalización de adelantamiento salía perjudicial. Con
velocidad comercial por línea y variación de tráfico paso a paso, los
adelantamientos bajan a 3-11 por ejecución y la penalización pasa a ayudar.

## Por qué importa

Un 7,6 % menos de intercambios es poco comparado con lo que parecía, pero es
real y no cuesta nada aguas abajo: la puerta física sigue intacta y la
fragmentación sube un 1,8 % como mucho.

La lección de método vale más que la cifra. **Cinco semillas no son una
medición**: con ellas, esta misma configuración parecía quitar un tercio de los
errores. La única forma de saberlo fue reservar semillas y mirarlas una sola vez,
y de hecho el primer conjunto reservado (9101-9120) se gastó en una variante que
resultó peor que la línea base (162 frente a 155). Mirar dos veces el mismo
conjunto lo convierte en conjunto de ajuste.

## Qué se hizo / qué queda abierto

Hecho: `rastrear()` acepta la columna `abscisa_m` y, donde la hay, empareja sobre
el recorrido con las dos hipótesis y la penalización de adelantamiento; el
suavizado mide también sobre el recorrido. Sin esa columna el comportamiento es
el de siempre, y hay test que lo fija. `tracking.py` no importa el GTFS: la
abscisa la aporta quien llama (ADR-012). Instrumento nuevo:
`project.analysis.simulacion_gtfs`. Guardias en `tests/test_tracking_abscisa.py`
y mutantes 048-052.

Abierto:

- La mediana de duración baja un 4 % y el 27/08 queda en 19,98 min, justo por
  debajo del suelo de 20 min que se había fijado como supuesto.
- El 10-12 % de las posiciones reales no tiene abscisa fiable y sigue con el
  criterio del plano.
- El banco no cubre el giro en cabecera ni la entrada y salida de servicio: los
  buses de `simulacion_gtfs` dejan de emitir al llegar al final del recorrido.

## Para la memoria

> La reconstrucción de identidad se amplió incorporando la posición de cada
> vehículo a lo largo del recorrido teórico, obtenida por proyección sobre la
> geometría del GTFS. La asignación entre sondeos consecutivos pasa así de
> compararse en el plano a compararse sobre un eje unidimensional, en el que dos
> vehículos de la misma línea mantienen un orden. El criterio incorpora dos
> hipótesis de movimiento —continuación a ritmo constante y detención— y penaliza
> las asignaciones que invierten el orden entre vehículos, que equivalen a
> afirmar un adelantamiento; el valor de esa penalización está acotado
> superiormente por la necesidad de seguir reconociendo los adelantamientos
> reales, frecuentes cuando un vehículo se detiene en parada.
>
> La evaluación se realizó sobre una flota sintética que circula por los
> recorridos reales de la red, con paradas y perturbaciones calibradas sobre la
> captura. Sobre veinte semillas reservadas para validación, los intercambios de
> identidad se redujeron un 7,6 %, con un incremento del número de trayectorias
> inferior al 2 % y sin desplazamientos que violen la restricción física. Debe
> señalarse que una evaluación preliminar sobre cinco semillas de desarrollo
> sugería una reducción del 35 %, magnitud que no se confirmó al ampliar la
> muestra: la diferencia ilustra la necesidad de reservar conjuntos de
> evaluación antes de ajustar.
