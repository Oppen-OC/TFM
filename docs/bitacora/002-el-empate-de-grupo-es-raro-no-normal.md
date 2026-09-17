---
id: 002
titulo: El 55 % de vehículos con compañero cerca es de cualquier línea; restringido a la misma (línea, trayecto), que es lo que empareja el tracker, baja al 1,9 %
fecha: 2026-09-01
tipo: medicion
capa: tracking
capitulo: calidad-dato
impacto: medio
estado: abierto
evidencia: uv run python -m project.analysis.medir_reales --hora 8
trampa: —
---

## Qué se observó

El docstring de `src/project/tracking.py` afirma que sobre la captura del
16/08/2026 **el 55 % de los vehículos tiene un compañero de su misma
(línea, trayecto) a menos de un paso de refresco**, y de ahí concluye que la
configuración degenerada que rompe el emparejamiento "es el caso normal, no el
raro".

La cifra existe, pero es de otra cosa. Medido sobre la misma captura, franja de
servicio (06–20 UTC, 120 snapshots muestreados a lo largo del día, 12.221
posiciones):

| definición de "compañero cerca" | posiciones |
|---|---|
| vecino de **cualquier** línea a < 250 m | **55,9 %** |
| vecino de cualquier línea a < 125 m | 32,6 % |
| vecino de **la misma (línea, trayecto)** a < 800 m | 7,5 % |
| vecino de la misma (línea, trayecto) a < 500 m | 4,2 % |
| vecino de la misma (línea, trayecto) a < 250 m | 2,5 % |
| vecino de la misma (línea, trayecto) a < 125 m | **1,9 %** |

El 55 % es la primera fila: **cualquier** autobús cerca, no uno de su mismo
grupo. El emparejamiento se hace exclusivamente dentro de (línea, trayecto), así
que un bus de otra línea a 30 m no genera ninguna ambigüedad — el tracker no lo
ve siquiera.

Con la restricción que sí aplica, la configuración ambigua es **treinta veces
menos frecuente** que lo que dice el docstring: 1,9 % de las posiciones a 125 m,
que es el paso de un bus urbano a 15 km/h en un refresco de 30 s.

Estructura de la flota en esa franja: 34 líneas, 72 grupos (línea, trayecto),
tamaño de grupo con mediana 2, p90 4 y máximo 8. El 85,1 % de las posiciones
tiene algún compañero de grupo en el mismo sondeo —aunque casi siempre lejos— y
el **58,5 % está en grupos de tres o más vehículos**, que es donde el empate
puede darse.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_reales --hora 8
uv run python -m project.analysis.medir_reales --hora 17
```

`vecindad()` de `src/project/analysis/medir_reales.py` calcula, para cada
posición, la distancia al vecino más próximo de su misma (línea, trayecto) en el
mismo sondeo, y la compara con tres umbrales: el paso propio de ese vehículo en
ese refresco —que aporta el propio tracker en `dist_m`—, el paso mediano de la
franja y los 125 m nominales.

Dos comprobaciones del instrumento antes de dar la cifra por buena:

- **La franja horaria cambia el resultado por completo.** Los 150 primeros
  snapshots de un día son de medianoche: paso mediano de 2,2 m por refresco y
  mediana de **un** vehículo por grupo. Medir la dificultad del emparejamiento
  ahí no dice nada del servicio. Por eso el medidor lleva `--hora`.
- **Barrido de 24 horas** para descartar que el 55 % fuera una franja concreta:
  el máximo del día con restricción de grupo es 6,1 % (06 UTC) y en horario de
  servicio pleno se queda entre 0,7 % y 3,2 %.

## Por qué importa

La conclusión operativa del docstring —"la configuración degenerada es el caso
normal"— es lo que justifica `_sembrar_por_centroide`, el sembrado del arranque
en frío. Esa justificación **sigue en pie, pero por otra razón y con otro
tamaño**: el empate no es el caso normal, es el 1,9 % de las posiciones. Sobre
las ~380.000 posiciones que deja un día de captura, eso son unas 7.000
situaciones ambiguas diarias, y por la entrada
[001](001-error-identidad-se-mide-en-trayectorias.md) sabemos que cada
intercambio de identidad que se cuele contamina la trayectoria entera a partir de
ahí. Raro por posición, permanente por trayectoria: exactamente el patrón que
hace que las dos cifras haya que darlas juntas.

La lección de método es la misma que la de la 001, con otro disfraz: **una
frecuencia sin su denominador no significa nada**. Aquí el denominador no era el
número de posiciones sino el conjunto de vecinos que el algoritmo puede
confundir, y ese conjunto lo define el propio algoritmo al agrupar por
(línea, trayecto).

Llevado a la memoria sin comprobar, el 55 % habría sido una afirmación fácil de
desmontar: basta preguntar contra qué vecinos empareja el tracker.

## Qué se hizo / qué queda abierto

Hecho:

- `src/project/analysis/medir_reales.py` deja las dos lecturas reproducibles y
  con la franja horaria explícita.

Abierto:

- **El docstring de `src/project/tracking.py` sigue diciendo 55 % atribuido al
  grupo**, y `tests/test_tracking_identidad.py` repite la frase en su cabecera.
  Hay que corregir las dos: la cifra de grupo es 1,9 % a 125 m, y el 55 % es de
  cualquier línea a 250 m.
- **Nada guarda esta cifra.** Un test que la fije necesita datos reales, y
  `data/` no está en el repo: sería un test que solo corre en la máquina que
  tiene la captura. Alternativa realista: fijar en la simulación la proporción
  de grupos de tres o más vehículos (58,5 % de las posiciones reales) para que
  el escenario sintético no sea más fácil que la calle.
- **21 filas de 280.586 (0,01 %) llegan sin `trayecto`.** `groupby(["linea",
  "trayecto"])` las descarta silenciosamente, así que esos vehículos nunca se
  emparejan y abren trayectoria nueva en cada sondeo. Es marginal en volumen,
  pero es exactamente el tipo de fila que desaparece sin avisar.

## Para la memoria

> La reconstrucción de identidad empareja vehículos únicamente dentro de cada
> par (línea, trayecto), de modo que la dificultad del problema no la determina
> la densidad global de la flota sino la proximidad entre vehículos de un mismo
> grupo. Sobre la captura del 16 de agosto de 2026, en franja de servicio, el
> 55,9 % de las posiciones tiene otro autobús a menos de 250 metros, pero al
> restringir el cómputo a vehículos de la misma línea y sentido —que son los
> únicos que el emparejador puede confundir entre sí— la proporción cae al 2,5 %
> a esa misma distancia y al 1,9 % a 125 metros, que es el desplazamiento de un
> autobús urbano a 15 km/h entre dos sondeos consecutivos.
>
> La flota observada se reparte en 34 líneas y 72 pares (línea, sentido), con una
> mediana de dos vehículos por par, percentil 90 de cuatro y máximo de ocho; el
> 58,5 % de las posiciones corresponde a grupos de tres o más vehículos, que son
> aquellos en los que la ambigüedad puede materializarse. La configuración que
> degrada el emparejamiento es, por tanto, poco frecuente en términos relativos,
> pero sistemática en términos absolutos: alrededor de siete mil situaciones
> ambiguas por día de captura, cada una de las cuales, de resolverse mal,
> contamina de forma permanente la trayectoria afectada.
