---
id: 023
titulo: En jornada real la segunda pasada con abscisa no cambia las trayectorias y sube un 30-55 % el indicador de intercambios; la mejora real de la 017 era abscisa desalineada
fecha: 2026-09-18
tipo: anomalia
capa: tracking
capitulo: metodologia
impacto: alto
estado: abierto
evidencia: uv run python auditoria/banco_tracker.py --real 2026-08-27 2026-09-03 2026-09-17 --real-abscisa --sin-sim --etiqueta dos_pasadas
trampa: 004
---

## Qué se observó

**La tabla de jornadas reales de la 017 es un artefacto.** Para el 27/08 dice
7.658 → 7.793 trayectorias y una mediana de 20,84 → 19,98 min al añadir la
abscisa. Ningún comando del repo lo reproducía: `banco_tracker --real` hacía
una sola pasada. Esas cifras salen **exactas** al pegar la abscisa **por
posición** sobre la entrada original, que es lo que hace `medir_gtfs` con la
flota simulada. En datos reales, eso cruza la abscisa entre filas:

- `rastrear` ordena por `snapshot_id` y reinicia el índice;
- la entrada leída del curated del colector tenía **un único par** de filas
  fuera de orden;
- eso basta para que **352.684 de 353.604 filas (el 99,7 %)** reciban la
  abscisa de otra posición.

Con la segunda pasada construida desde la salida de la primera, las jornadas
reales quedan así:

| día | curated | trayectorias (1 → 2 pasadas) | mediana (min) | `ida_vuelta` | abscisa fiable |
|---|---|---|---|---|---|
| 27/08 | colector | 7.658 → 7.659 | 20,84 → 20,83 | — → 299 | 87,6 % |
| 27/08 | reprocesado | 7.627 → 7.628 | 21,12 → 21,13 | 230 → **300** | 87,6 % |
| 03/09 | reprocesado | 9.276 → 9.272 | 17,62 → 17,62 | 326 → **453** | 85,2 % |
| 17/09 | reprocesado | 8.197 → 8.191 | 16,55 → 16,67 | 250 → **387** | 83,9 % |

La abscisa no mueve el número de trayectorias ni la mediana, y **el indicador
de intercambios `ida_vuelta` sube un 30 %, un 39 % y un 55 %**. Es una cota
inferior, validada en simulación con `--validar-indicador`.

**Las medianas de septiembre, por debajo de 20 min, las bajan los buses
aparcados sin trayecto.** Cada fila sin `trayecto` sale como una trayectoria de
un punto (entrada 018). Los días con ráfagas acumulan miles: 1.965 trayectorias
de un punto el 03/09 y 2.291 el 17/09, frente a 901 el 27/08. Sin esas filas,
la mediana del tracker de una pasada es de 21,9, 22,8 y 27,7 min.

Cada ráfaga es un solo vehículo aparcado. El 17/09, la 12 (669 posiciones), la
24 (635) y la 81 (191) tienen como mucho un vehículo por sondeo sin trayecto, y
ninguna de esas posiciones está a menos de 60 m de un trazado de su línea.

## Cómo se midió

```bash
uv run python auditoria/banco_tracker.py --real 2026-08-27 2026-09-03 2026-09-17 --sin-sim --etiqueta una
uv run python auditoria/banco_tracker.py --real 2026-08-27 2026-09-03 2026-09-17 --real-abscisa --sin-sim --etiqueta dos
DATA_ROOT=<raíz con curated -> data/_curated_colector> uv run python auditoria/banco_tracker.py \
    --real 2026-08-27 --real-abscisa --sin-sim --etiqueta control
```

Salidas: `auditoria/resultados/banco_real_*_0501d58.json`. La reproducción del
artefacto, sobre el curated del colector:

```python
casada = emparejar(rastrear(df), cargar_trazados())       # df tal cual sale de duckdb
fiable = ~casada.fuera_de_ruta.fillna(True).astype(bool) & ~casada.ambigua.fillna(True).astype(bool)
mal = rastrear(df.assign(abscisa_m=np.where(fiable, casada.abscisa_m, np.nan)))
# -> 7.793 trayectorias, mediana 19,98 min: las cifras de la 017
```

Las medianas sin filas nulas salen de la salida guardada por
`validar_mapmatching --guardar`, descartando `trayecto` nulo antes de agrupar
por `vehicle_id`.

**Control del instrumento.** Con dos pasadas, la abscisa fiable del control
(87,59 %) coincide con la de la 017 (87,6 %): el map-matching es el mismo. Lo
único que cambia es la alineación.

## Por qué importa

- **La justificación de las dos pasadas en datos reales desaparece.** ADR-012
  se apoyaba en el −7,6 % de intercambios de la simulación, que sigue valiendo
  porque la flota simulada llega ordenada, y en esta confirmación sobre jornada
  real, que era el artefacto. En datos reales, la segunda pasada no reduce la
  fragmentación y empeora la cota inferior de intercambios.
- **Es exactamente el error que cometerá `prepare.py`.** ADR-012 manda rastrear,
  emparejar y rastrear con la abscisa. Pegar la columna a la entrada original
  es lo natural, lo hace el propio banco con la simulación, y no da error:
  produce una mejora del 1,8 % que parece real.
- **El "suelo de 20 min" del abierto 10 no era un problema del tracker.** Era
  el artefacto y, en septiembre, las ráfagas sin trayecto.

## Qué se hizo / qué queda abierto

Hecho: `banco_tracker --real-abscisa` construye la segunda pasada desde la
salida de la primera. La tabla de la 017 lleva una nota que remite aquí.

Abierto, antes de escribir `prepare.py`:

1. **Por qué sube `ida_vuelta`.** Hay que ver en qué líneas y tramos, si los
   eventos nuevos caen donde hay abscisa o donde se vuelve al plano, y si son
   intercambios reales o el indicador responde de otro modo a la abscisa. El
   indicador se validó sólo en la flota sin abscisa.
2. **Decidir si se mantienen las dos pasadas.** Si la abscisa no mejora la
   identidad real, se usa sólo para el paso por parada y el tracker vuelve a
   una pasada.
3. **Guardia de alineación** para quien construya la segunda pasada: un test
   con entrada desordenada que falle si la abscisa se pega por posición.

## Para la memoria

> La mejora que la abscisa curvilínea aportaba a la reconstrucción de
> identidades en simulación no se reproduce sobre jornadas reales. Una
> primera medición indicaba un 1,8 % más de trayectorias y una duración
> mediana cuatro por ciento menor. Resultó ser un artefacto: la abscisa se
> asoció a las posiciones por su orden de fila, y el rastreador reordena los
> registros por refresco, de modo que un único par de filas desordenado en la
> entrada bastó para que el 99,7 % de las posiciones recibiera la abscisa de
> otra. Con la asociación correcta, la segunda pasada no altera el número de
> trayectorias ni su duración en tres jornadas, y el indicador de
> intercambios de identidad aumenta entre un 30 % y un 55 %. El episodio
> justifica dos cautelas del procedimiento: toda columna calculada sobre la
> salida del rastreador se une por identificador y no por posición, y
> ninguna mejora simulada se da por confirmada hasta medirla sobre datos
> reales con el mismo procedimiento que usará el pipeline.
