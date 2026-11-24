# Día 5 · El ETL

## Objetivo del día

Entender cómo se fabrica la etiqueta que la fuente no publica: de posiciones sueltas a
«segundos de retraso en esta parada». Es el capítulo que convierte el trabajo en un
TFM. Al acabar, debes poder explicar el emparejamiento húngaro con predicción frente
al vecino más cercano, y la cascada del etiquetado.

## Lecturas

Equivalencias con el plan original (`demo/*` ya no existe, ADR-009): `demo/track.py` →
`tracking.py`, `demo/diagnose.py` → `analysis/diagnose.py`, `demo/test_diagnose.py` →
`tests/test_diagnose.py`.

En este orden:

1. `src/project/tracking.py` (774 líneas). Lee la docstring completa (l. 1-37), las
   constantes (l. 47-97), `_dt_puerta` (l. 100), `_emparejar_grupo` (l. 115-181, el
   corazón: coste, puerta física, `linear_sum_assignment` en l. 174),
   `_sembrar_por_centroide` (l. 218) y `rastrear` (l. 561). No hace falta seguir cada
   helper de cosido y suavizado.
2. `docs/bitacora/001-error-identidad-se-mide-en-trayectorias.md`: cómo se mide el
   error de identidad, y por qué contar posiciones engaña.
3. `src/project/ingest/collect.py` (453 líneas): docstring (l. 1-45), el bucle de
   sondeo (l. 240-310) y `mostrar_estado` (l. 186). `src/project/ingest/reprocesar.py`:
   la docstring y `elegir_capturas`.
4. `src/project/analysis/diagnose.py` (450 líneas): docstring (l. 1-25), con las cuatro
   preguntas, y `main` (l. 211). `tests/test_diagnose.py` (docstring l. 1-15 y
   `test_diagnose_discrimina`, l. 188).
5. **Cómo se fabrica la etiqueta**: la docstring de `src/project/etiquetado.py`
   (l. 1-50), `etiquetar` (l. 405), `src/project/prepare.py` (docstring l. 1-26,
   `procesar_dia` l. 207), `src/project/mapmatching.py` (`emparejar` l. 146) y
   `docs/09_gtfs_emt.md`.
6. `tests/conftest.py` (`flota_simulada`, l. 29) y `tests/test_etiquetado.py`
   (docstring): cómo se prueba contra una verdad conocida.

## Comandos a ejecutar

En PowerShell, desde la raíz. Sin red:

```powershell
uv run pytest tests/test_tracking.py tests/test_tracking_identidad.py tests/test_diagnose.py -q
uv run pytest tests/test_etiquetado.py tests/test_mapmatching.py -q
uv run python -m project.analysis.medir_tracking      # reproduce las cifras de la bitácora 001
uv run python -m project.ingest.collect --status      # estado del colector (sin tocarlo)
```

`medir_tracking` usa la flota simulada: no necesita `data/`. `collect --status` termina
con código 1 si no hay `_status.json`; en un equipo sin captura es lo esperado.
`diagnose` sin argumentos necesita `data/` con captura; en este equipo no se ejecuta.

## Qué tienes que saber explicar

**P1. ¿Por qué hace falta inferir la identidad del vehículo y cómo se hace?**
Porque la EMT no publica identificador de vehículo, `trip_id` ni retraso, y `gid` no
sirve (ficha 001). Se empareja, entre dos sondeos consecutivos y dentro de cada
(línea, trayecto), cada bus con su posición siguiente mediante **asignación óptima
global** (`scipy.optimize.linear_sum_assignment`, `tracking.py:174`) sobre una matriz
de costes, con una puerta física de velocidad máxima y una predicción de movimiento
(`tracking.py:1-37`, `115-181`).

**P2. ¿Húngaro con predicción frente a vecino más cercano?**
El vecino más cercano decide cada bus por separado, y dos buses de la misma línea
cercanos se pueden «robar» el emparejamiento; el húngaro minimiza el coste **total**,
así que un reparto malo de uno obliga a repartir bien el otro. Y la predicción
(extrapolar a velocidad constante) acerca la posición esperada a la real, que es lo que
separa a dos buses próximos. Medido sobre la flota simulada (60 buses, 30 s): el
ingenuo deja 4 saltos de identidad (2,167 % de las posiciones) y el predictivo 0
(bitácora 001, tabla; `docs/04_propuesta_para_tutor.md:53-61`). Con 120 buses a 60 s el
ingenuo sube al 7,375 % y el predictivo se queda en 0,25 %.

**P3. ¿Por qué «97,8 % frente a 100 %» engaña?**
Porque el error de identidad **no se cuenta en posiciones**: son 4 saltos, y al alargar
la captura el porcentaje baja (de 2,167 % a 0,667 %) con exactamente los mismos
cuatro fallos, mientras la cola contaminada sube. Se mide en trayectorias contaminadas
y en saltos (bitácora 001, *Qué se observó*). Es una cifra de `docs/04` que conviene
citar con cuidado.

**P4. ¿Qué es el arranque en frío del tracker (trampa 007)?**
La predicción necesita el paso anterior, que no existe en la primera transición de cada
trayectoria; ahí el emparejamiento vuelve a ser vecino más cercano puro, y con buses de
la misma línea a menos de un paso de refresco (1,9 % de las posiciones) coste correcto y
cruzado **empatan exacto** y Hungarian desempata por orden de fila. Propaga: 35 % de
acierto en convoy. Romper la cadena ante la duda es peor (`tracking.py:12-25`; ficha 007;
`tests/test_tracking_identidad.py:151`).

**P5. ¿Por qué la puerta física no puede compartir matriz con el coste (trampa 008)?**
Porque el coste se mide contra la posición **predicha**, que es lo correcto, pero la
puerta es una afirmación física sobre lo que un bus puede recorrer: debe medirse sobre
el desplazamiento **real**. Compartida, colaba buses a más de 100 km/h sin ningún error
(`tracking.py:145-150`; ficha 008;
`tests/test_tracking_identidad.py:246`).

**P6. ¿Cómo se fabrica la etiqueta de retraso?**
`retraso = t_paso_observado − t_llegada_programada`, y ninguno de los dos términos
viene en la fuente. Cascada (`etiquetado.py:1-50`): (1) día de servicio y versión del
GTFS por fecha; (2) cortar viajes donde la abscisa retrocede; (3) trazado por viaje,
decidiendo las variantes viaje a viaje; (4) paso por parada: proyectar las paradas sobre
el trazado en orden e interpolar el instante a la salida; (5) viaje programado: el que
programa las primeras paradas más cerca de lo observado, exigiendo un margen sobre el
segundo mejor.

**P7. ¿Qué sesgo declara el etiquetado que no puede evitar?**
Un bus que va más de medio intervalo fuera de su horario se asigna al viaje contiguo, y
su retraso sale con signo y magnitud equivocados sin que nada lo delate
(`etiquetado.py:33-36`). El margen solo descarta los que quedan cerca de la mitad.

**P8. ¿Por qué `shape_dist_traveled` no sirve (trampa 010)?**
Porque en el GTFS de la EMT es el horario reescalado ($R^2 = 1$ contra el tiempo
programado): usado como eje de abscisa, el retraso sale estructuralmente cero y parece
puntual. La abscisa se proyecta sobre la geometría (ficha 010;
`tests/test_mapmatching.py:137`).

**P9. ¿Por qué se une todo por índice o identificador, nunca por posición?**
Porque `rastrear` reordena y reinicia el índice: una columna calculada sobre su salida
y pegada por posición a la entrada se cruza entre filas sin error (trampas 004 y 012;
`etiquetado.py:38-40`).

**P10. ¿Qué responde `diagnose.py` y por qué hay un test que lo valida?**
Cuatro preguntas: cobertura espacial, varianza del `estado` por hora, dinámica por tramo
y señal (¿los buses van más lentos donde el tramo declara congestión?) (`diagnose.py:6-23`).
`test_diagnose.py` comprueba que **discrimina**: señal clara en el escenario A, ninguna
en el B. Si dijera lo mismo en los dos validaría la hipótesis del TFM por accidente
(`tests/test_diagnose.py:1-15`).

**P11. ¿Por qué `curar` es un stage y la captura no?**
Porque `curar` reconstruye `data/curated/` desde el crudo con `reprocesar`, que es
determinista; capturar un stream en vivo no es idempotente (`dvc.yaml:1-20`; ADR-015,
`docs/07_decisiones.md:414`; ADR-002, `docs/07_decisiones.md:45`).

## Ejercicio

Dibuja, sin mirar, la cascada de la etiqueta en cinco cajas (de la posición al
`retraso_s`) y marca en cada caja **qué trampa** vive ahí (pistas: 004/007/008/013/014 en
el tracker; 006/010/015 en el etiquetado). Después tacha cada trampa que acertaste y
repasa las que no.

Segundo ejercicio, oral: explica a un compañero de otro máster, en 90 s, por qué
asignar «el bus más cercano» a cada bus **no** es lo mismo que asignar por coste total
mínimo.

## Mis respuestas / dudas

