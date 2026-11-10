---
id: 064
titulo: Un ciclo de la demo en vivo tarda 11-12 s a las 10:00 y 27-32 s a las 18:00 si se etiquetan solo las líneas de la parada, y unos 3 min con todas. El recorte no es neutro: cambia 5 de 5.334 pasos porque el reloj de cada sondeo del tracker es el de todas las líneas; con ese reloj, sale idéntico
fecha: 2026-11-10
tipo: medicion
capa: serving
capitulo: metodologia
impacto: medio
estado: abierto
evidencia: uv run python -m project.analysis.medir_ciclo_vivo --dia 2026-10-01 --hasta 18:00 --comprobar-lineas (y --hasta 10:00; y --dia 2026-10-19 --hasta 18:00 --stop 2277)
trampa: 022
---

## Qué se observó

La tarea 1 del plan de la demo en vivo
(`docs/superpowers/plans/2026-11-10-demo-parada-en-vivo.md`) mide cuánto tarda un
ciclo sobre un día ya capturado. Un ciclo relee el crudo del día, lo etiqueta con
las funciones del pipeline, calcula `t_disp` y construye las variables con `h = 2`.
La parada elegida es la 2277, la del horario `19-09-2026` con más líneas (11).

| corrida | lectura del crudo | etiquetado | `t_disp` | variables | ciclo |
|---|---|---|---|---|---|
| 01/10, hasta las 10:00 | 2,7 s | 7,9 s | 0,04 s | 1,8 s | **11,3-12,4 s** |
| 01/10, hasta las 18:00 | 6,5 s | 19,1 s | 0,07 s | 1,9 s | **26,6-32,0 s** |
| 19/10, hasta las 18:00 (34 días de histórico) | — | — | — | 4,8 s | **31,4 s** |
| 01/10, hasta las 18:00, todas las líneas | 6,3 s | 158,8 s | 0,4 s | 2,4 s | **167,9-193,3 s** |

- El desglose es el de la primera corrida de cada fila. Los rangos van de dos a
  tres corridas.
- A las 18:00 se leen 1.657 payloads, 1.616 sondeos y 226.332 posiciones. Las 11
  líneas son 22.219 posiciones; todas, 226.256.
- El etiquetado domina el ciclo y crece con las horas capturadas. Las variables
  crecen con el histórico: 1,9-2,6 s con 17 días y 4,8 s con 34.
- El arranque se paga una vez: el GTFS, unos 5 s, y el histórico, 2-2,5 s.
- **El recorte por líneas no es idéntico.** Hasta las 10:00 sale igual, con 1.735
  pasos. Hasta las 18:00 salen 5.333 pasos de esas líneas frente a 5.334 con todas:
  3 solo con todas y 2 solo recortados. Las diferencias están en la 31 (parada 1,
  con otro viaje programado) y en la 72 (parada 11, con 13 s de diferencia en el
  retraso). Dos etiquetados con todas las líneas dan las mismas 44.253 filas, así
  que no es azar.
- **La causa es el reloj del sondeo** (trampa 022). Sobre el mismo frame, recortar
  no quita ningún sondeo, pero cambia su `ts_utc` máximo en 1.025 de 1.615
  sondeos (p50 1 s, p90 4 s, máximo 11 s). Se añadió al recorte una fila fantasma
  por sondeo con el reloj de todas las líneas, en una línea que no está en el
  GTFS. Así sale idéntico: 5.334 de 5.334. Se ha reproducido en dos corridas.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_ciclo_vivo --dia 2026-10-01 --hasta 10:00
uv run python -m project.analysis.medir_ciclo_vivo --dia 2026-10-01 --hasta 18:00 --comprobar-lineas
uv run python -m project.analysis.medir_ciclo_vivo --dia 2026-10-19 --hasta 18:00 --stop 2277
```

- Es solo lectura sobre el corpus, y el JSON sale por stdout.
- `--hasta` es hora local.
- La lectura del crudo es el bucle de `reprocesar`: la captura con más filas de
  cada sondeo (trampa 011), y solo payloads con filas (trampa 018).
- El frame que se etiqueta y las `llegadas` salen de esa misma lectura.
- Ningún paso usa un `t_disp` posterior al corte: se descartan 0 en todas las
  corridas.
- La comparación no va por `CLAVE_PASO`. `viaje_id` lleva el `vehicle_id`, que se
  numera entre todas las líneas, así que recortar renumera sin cambiar ningún
  paso. Por eso se compara el multiconjunto de (fecha, línea, trayecto, viaje
  programado, parada, `t_obs_utc`, `retraso_s`).
- `recorte_con_reloj_identico` repite el recorte con `con_reloj_de_todas`.

El instrumento mintió una vez. Las dos corridas de verificación de las 15:16 y
las 15:28 dieron 37,2 y 42,8 s recortado y 246-258 s con todas las líneas, hasta
un 60 % más. Desde las 15:15 había un juego abierto en el PC con la CPU al 70 %:
incluso la carga del GTFS pasó de 5,3 a 8,5 s. Se descartaron para el tiempo,
aunque no para la comparación, que no depende de la carga. Las cifras de la tabla
son de las corridas de las 14:40-15:08. El salto de 26,6 a
32,0 s entre corridas del mismo corte, sin ese proceso, sigue sin explicar.

## Matiz: el ciclo completo no es el de la tarea 1

La tarea 1 midió un ciclo con `h = 2` (una sola llamada a `construir`). El ciclo
real llama a `construir` una vez por cada horizonte con modelo, así que la cifra
del ciclo completo es la del humo de `parada` a las 16:00Z del 01/10 sobre la
2277: 35,5 s y 41,9 s (la segunda con la máquina cargada), no los 27-32 s de la
tabla. Además la caché se estampa al terminar el ciclo, no al empezar: en hora
punta el refresco efectivo es el ciclo más `CICLO_S`, no `CICLO_S`.

## Por qué importa

- El periodo de refresco de la demo sale de aquí. Etiquetando solo las líneas de
  la parada cabe en 30-40 s hasta las 18:00. Con todas, en 3 min. El retraso de un
  paso se sabe unos 81 s después (bitácora 046), así que un refresco de 3 min más
  que duplica esa espera.
- El recorte a secas cambia el 0,09 % de los pasos sin error. Va contra la
  decisión 3 del diseño: las mismas variables que en el entrenamiento. Con el
  reloj de todas las líneas el recorte es exacto y cuesta lo mismo: 23.834
  posiciones frente a 22.219.
- El ciclo crece con las horas y con el histórico. A las 23:00, o con más días de
  la misma versión, no cabe en 30 s.

## Qué se hizo / qué queda abierto

- Hecho: el medidor (`src/project/analysis/medir_ciclo_vivo.py`) con las dos
  comprobaciones, y la ficha de la trampa 022.
- Decidido por el autor: recortar a las líneas de la parada **con el reloj de
  todas** (exacto, `services/vivo.con_reloj_de_todas`) y `CICLO_S = 40`
  (`ui/app.py` lo repite en `REFRESCO_S`, porque la UI no importa `services/`).
- Hecho: la guardia de la 022, `tests/test_vivo.py::test_el_recorte_conserva_el_reloj_y_los_sondeos_de_todas_las_lineas`,
  con el mutante 222. La ficha pasa a `cerrada`.
- Abierto: repetir los tiempos con la máquina libre y tres corridas por corte. Las
  de la tabla son dos o tres por fila, y 40 s no se ha comprobado a las 23:00 ni
  con más días de la misma versión.

## Para la memoria

> Para la demostración en vivo, el vector de variables se reconstruye en cada
> ciclo con las mismas funciones del pipeline. Sobre un día ya capturado, un ciclo
> que etiqueta solo las once líneas de una parada concurrida tarda entre 11 y 12 s
> con la captura hasta las 10:00 y entre 27 y 32 s hasta las 18:00. Etiquetando
> toda la flota tarda entre 2,8 y 3,2 min. El coste lo domina el etiquetado, que
> crece con las horas capturadas.
>
> Limitar el cálculo a las líneas de la parada no resultó neutro. Aunque el
> seguimiento de vehículos solo empareja posiciones de la misma línea y el mismo
> sentido, toma como reloj de cada sondeo la última marca temporal de toda la
> flota. Al recortar, ese reloj cambia en el 63 % de los sondeos, en una mediana
> de un segundo. Basta para resolver de otro modo algunos empates casi exactos: 5
> de 5.334 pasos por parada difieren a las 18:00, y ninguno a las 10:00.
> Restituyendo a cada sondeo el reloj de la flota entera, el resultado recortado
> coincide con el completo en todos los pasos: el recorte puede conservar el
> etiquetado del entrenamiento sin aproximarlo.
