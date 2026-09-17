---
id: 001
titulo: El error de identidad del tracker no se cuenta en posiciones; contado así, alargar la captura lo mejora sin arreglar nada
fecha: 2026-09-01
tipo: medicion
capa: tracking
capitulo: metodologia
impacto: alto
estado: mitigado
evidencia: uv run python -m project.analysis.medir_tracking
trampa: 004
---

## Qué se observó

El emparejamiento **ingenuo** (vecino más cercano, sin extrapolar posición) deja
un **2,167 % de posiciones asignadas al vehículo equivocado** sobre la flota
simulada de referencia: 60 buses, 20 snapshots cada 30 s, 1.200 posiciones,
semilla 7.

Ese 2,167 % son en realidad **4 saltos de identidad**, y ahí está el hallazgo:

| longitud de la captura | posiciones | err_ident | saltos | trayectorias contaminadas | cola contaminada |
|---|---|---|---|---|---|
| 20 snapshots | 1.200 | 2,167 % | 4 | 5,0 % | 2,92 % |
| 40 snapshots | 2.400 | 1,333 % | 4 | 5,0 % | 3,96 % |
| 80 snapshots | 4.800 | 0,667 % | 4 | 5,0 % | 4,48 % |
| 160 snapshots | 9.600 | 1,792 % | 6 | 8,3 % | 6,20 % |

Al pasar de 20 a 80 snapshots el error **cae a un tercio** con exactamente los
mismos cuatro fallos. Lo único que ha cambiado es el denominador. Mientras tanto
la cola contaminada —las posiciones posteriores al primer salto de su
trayectoria, que son las que heredan la identidad equivocada— **sube** del 2,92 %
al 4,48 %.

Dispersión entre semillas, misma configuración: de 0 % (semilla 101) a 3,583 %
(semilla 42, 8 saltos, 11,7 % de trayectorias contaminadas). Una sola ejecución
del método ingenuo no dice nada.

El tracker **predictivo**, que es el que está en producción, da 0 saltos en las
cinco semillas y hasta 160 snapshots. No es perfecto: degrada con la densidad y
con el intervalo de refresco.

| modo | buses | dt | err_ident | saltos | trayectorias contaminadas | cola |
|---|---|---|---|---|---|---|
| predictivo | 60 | 30 s | 0,000 % | 0 | 0,0 % | 0,00 % |
| predictivo | 60 | 60 s | 0,000 % | 0 | 0,0 % | 0,00 % |
| predictivo | 120 | 30 s | 0,083 % | 2 | 1,7 % | 1,58 % |
| predictivo | 120 | 60 s | 0,250 % | 6 | 5,0 % | 4,75 % |
| ingenuo | 120 | 60 s | 7,375 % | 36 | 27,5 % | 19,21 % |

## Cómo se midió

```bash
uv run python -m project.analysis.medir_tracking
```

Sobre `simular_flota()` de `src/project/analysis/simulacion.py`, que es la misma
entrada que consume la fixture `flota_simulada` de `tests/conftest.py`: los
umbrales de `tests/test_tracking.py` y estas cifras hablan del mismo generador,
no de dos copias que puedan divergir.

Las cuatro métricas de `medir()`:

- **err_ident** — posiciones que no pertenecen al bus mayoritario de su
  trayectoria, sobre el total de posiciones. Es la métrica que engaña.
- **saltos** — veces que una trayectoria reconstruida cambia de bus real. Es el
  número de fallos; no depende de la duración de la captura.
- **contaminadas** — trayectorias con más de un bus real dentro, sobre el total.
- **cola** — posiciones posteriores al primer salto de su trayectoria, sobre el
  total. Es lo que aguas abajo hereda una etiqueta de otro autobús.

Calibración contra datos reales (`data/curated/source=emt_buses`, 20/08/2026:
2.754 snapshots, 380.993 posiciones): mediana de **183 buses por snapshot**
(máximo 212) repartidos en **75 grupos (línea, trayecto)**, con mediana de 2
buses por grupo, p90 de 5 y máximo de 10. Refresco real: mediana 31 s.

El emparejamiento se hace **dentro** de cada grupo (línea, trayecto), así que lo
que determina la dificultad no es el tamaño de la flota sino la ocupación del
grupo. La simulación base pone 60 buses en 16 grupos —3,75 por grupo, entre la
mediana y el p90 reales— y la configuración de estrés pone 7,5 por grupo, que es
la banda de los grupos reales más cargados. Es decir: **el punto donde el tracker
predictivo empieza a fallar existe en los datos reales**, en los grupos del p90
hacia arriba.

## Por qué importa

Un salto de identidad **no se corrige solo**. A partir de él, la trayectoria
reconstruida mezcla dos autobuses, y todo lo que se calcule sobre ella —velocidad
instantánea, paso por parada, retraso frente al horario teórico— pertenece a un
vehículo que no es el que dice la etiqueta. El daño no es la posición mal
asignada: es la cola.

Por eso el denominador correcto es **trayectorias**, no posiciones. Contado en
posiciones, el error de una captura larga tiende a cero por dilución mientras el
número de trayectorias envenenadas crece. Es una métrica que mejora sola sin que
mejore nada, y es exactamente el tipo de número que un tribunal desmonta en una
pregunta.

Segundo orden, y es la lección que hermana esta entrada con la trampa
[004](../../.claude/trampas/004-sort-inestable-en-snapshot.md): allí el
instrumento **exageraba** el fallo (11 % siendo 99 %) y llevaba a romper código
sano; aquí el instrumento lo **esconde**. La misma capa, el mismo tipo de error,
signos opuestos.

## Qué se hizo / qué queda abierto

Hecho:

- El tracker en producción es el predictivo (`predictivo=True` es el valor por
  defecto de `rastrear()`), y
  `tests/test_tracking.py::test_predictivo_mejora_al_ingenuo` impide volver al
  ingenuo sin que salte un test.
- El generador de flota se movió a `src/project/analysis/simulacion.py` para que
  las cifras de esta entrada y los umbrales de los tests no puedan divergir.
- `src/project/analysis/medir_tracking.py` deja la medición reejecutable.
- La guardia pasa a estar expresada en la unidad que no se diluye:
  `tests/test_tracking.py::test_sin_saltos_de_identidad` (0 saltos y 0 % de
  trayectorias contaminadas sobre la flota base) y
  `tests/test_tracking.py::test_captura_larga_no_esconde_saltos` (lo mismo a 160
  snapshots, que es donde el umbral por posición es ciego).
- `tests/test_tracking.py::test_la_metrica_por_posicion_no_delataria_el_fallo`
  fija el hallazgo en sí: el ingenuo a 80 snapshots saca un 99,3 % de precisión
  por posición contaminando el 5 % de las trayectorias. Si esa combinación deja
  de darse, el test cae y esta entrada hay que remedirla.

Abierto:

- El umbral histórico `acc >= 0.99` de
  `tests/test_tracking.py::test_tracker_predictivo_identidad_correcta` sigue en
  su sitio: es la guardia de la trampa 004, que se detecta precisamente por
  posición (con el bug caía al 11 %). Se queda, pero ya no es el único aserto.
- **No hay medición sobre grupos reales cargados.** La calibración de arriba dice
  que existen grupos con hasta 10 buses; la simulación llega a 7,5 por grupo. El
  borde superior real no está medido.
- El efecto sobre la etiqueta de retraso no está cuantificado porque todavía no
  hay etiqueta: falta el GTFS estático de la EMT. Cuando la haya, la pregunta es
  qué fracción de etiquetas cae en la cola contaminada.

## Para la memoria

> La capa de seguimiento de la EMT no publica identificador de vehículo, de modo
> que la identidad de cada autobús debe inferirse emparejando posiciones entre
> sondeos consecutivos. Evaluar ese emparejamiento exige verdad-terreno, que los
> datos reales no ofrecen, por lo que se construyó una flota simulada de 60
> vehículos en 16 pares (línea, trayecto) muestreada cada 30 s, con densidad por
> grupo comprendida entre la mediana y el percentil 90 de la observada en la
> captura real del 20/08/2026 (183 vehículos por sondeo repartidos en 75 grupos).
>
> Sobre esa flota, el emparejamiento por vecino más cercano asigna
> incorrectamente el 2,2 % de las posiciones. Esa cifra, sin embargo, es
> engañosa: corresponde a cuatro saltos de identidad que, al prolongar la captura
> de 20 a 80 sondeos, se diluyen hasta el 0,7 % sin que se haya corregido
> ninguno. Un salto de identidad no es un error puntual, sino permanente: a
> partir de él la trayectoria reconstruida mezcla dos vehículos, y las magnitudes
> derivadas —velocidad, paso por parada, retraso— quedan atribuidas al autobús
> equivocado. Medido en la unidad adecuada, esos cuatro saltos contaminan el 5 %
> de las trayectorias y el 4,5 % de las posiciones a 80 sondeos, proporción que
> crece con la duración de la captura mientras el error por posición decrece.
>
> Se adoptó por ello un emparejamiento con extrapolación de posición mediante un
> modelo de velocidad constante, que elimina los saltos en las cinco semillas
> evaluadas y en capturas de hasta 160 sondeos. Su degradación es conocida y
> depende de la ocupación del grupo y del intervalo de refresco: al duplicar la
> densidad hasta 7,5 vehículos por grupo aparecen dos saltos (1,7 % de
> trayectorias contaminadas), y al duplicar además el intervalo a 60 s, seis
> (5,0 %). Ambas condiciones se dan en los grupos reales más cargados, lo que
> acota el alcance de la reconstrucción de identidad y se recoge en las
> limitaciones del trabajo.
