---
id: 008
titulo: Medido en ventanas de 1 h, agrupar por línea parecía el mejor arreglo del tracker; sobre el día completo fabrica una trayectoria de 19,8 h
fecha: 2026-09-16
tipo: descarte
capa: tracking
capitulo: metodologia
impacto: alto
estado: resuelto
evidencia: PYTHONPATH=$SB uv run python $SB/dia_completo.py
trampa: —
---

## Qué se observó

Sobre la captura del 27/08/2026, el tracker parte el autobús medio en muchos
trozos: **12.709 trayectorias** en el día para un censo mediano de 168 vehículos
por sondeo, con longitud mediana de **10,5 min** frente a un servicio real de
30-60 min.

Se probaron tres arreglos. Medidos sobre una ventana de **1 h en punta** (117
snapshots, 22.208 posiciones), agrupar por `linea` en vez de por
`(linea, trayecto)` —para que el giro en cabecera no corte la cadena— combinado
con tolerar huecos de 2 sondeos parecía resolverlo del todo:

| ventana de 1 h | trayectorias | longitud p50 | emparejamiento |
|---|---|---|---|
| actual | 1.075 | 7,0 min | 0,957 |
| agrupar por línea + tolerar hueco | 279 | **57,0 min** | 0,993 |

**Esa cifra de 57 min es un artefacto de la ventana.** 117 snapshots a 30 s son
58,5 min: una trayectoria de 57 min está tocando el techo de la ventana, y la
métrica no puede distinguir «reconstruida correctamente» de «fusionada de más».

Repetida la medición sobre el día completo (352.923 filas, 2.750 snapshots), la
distribución se invierte:

| día completo | trays | p50 | p90 | p99 | max |
|---|---|---|---|---|---|
| actual | 12.709 | 10,5 min | 31,5 | 54,0 | 149,5 min |
| solo tolerar hueco | 7.632 | 21,1 min | 56,0 | 83,9 | 437,1 min |
| agrupar por línea + tolerar hueco | 3.009 | **2,5 min** | 153,2 | **838,0** | **1.187,5 min** |

**1.187,5 min son 19,8 horas.** La mediana cae a 2,5 min mientras el p99 sube a
14 h: la distribución es bimodal, unas pocas cadenas gigantes absorben las
posiciones y el resto se pulveriza.

Aislado el mecanismo sobre la ventana de 20:00 a 01:40 local (5,5 h, incluye el
apagado del servicio), el culpable es agrupar por línea, no tolerar huecos:

| config | trays | span p50 | span max | hueco interno max | posiciones de la cadena mayor |
|---|---|---|---|---|---|
| actual | 2.045 | 8,0 min | 63,1 min | 2,2 min | 125 |
| **agrupar por línea** | 1.339 | 7,3 min | **332,1 min** | 2,2 min | **653** |
| tolerar hueco | 1.551 | 6,9 min | 98,0 min | 2,9 min | 189 |
| ambos | 893 | 0,7 min | 332,2 min | 2,8 min | 653 |

332,1 min es **la ventana entera**. La cadena encadena 653 posiciones sin un solo
hueco interno mayor de 2,2 min: no está saltando por encima del apagado nocturno,
va saltando de autobús en autobús dentro de la misma línea, de forma continua.

## Cómo se midió

Banco de pruebas en el scratchpad, fuera del repo, con el tracker parametrizado
por los tres arreglos como conmutadores independientes:

```bash
SB=<scratchpad>/sandbox_tracking
PYTHONPATH=$SB uv run python $SB/experimento.py      # sintético + real 1 h
PYTHONPATH=$SB uv run python $SB/dia_completo.py     # día completo, 5 configuraciones
PYTHONPATH=$SB uv run python $SB/diagnostico_dia.py  # distribución de longitudes
```

Con los tres conmutadores apagados, el tracker del banco reproduce
`project.tracking.rastrear()` **exactamente** —mismo `vehicle_id`, `dist_m` y
`dt_s`— sobre seis conjuntos, incluidas las 22.208 posiciones reales de la
ventana de 1 h. Sin esa verificación previa, las diferencias medidas podrían
proceder de la reescritura y no de los arreglos.

## Por qué importa

El error no está en el arreglo: está en **el instrumento**. La longitud mediana
de trayectoria es una métrica censurada por la ventana de observación, y en una
ventana de 1 h no puede tomar valores por encima de 58,5 min. Cualquier
configuración que fusione identidades sin límite obtiene en esa ventana la misma
puntuación que la configuración perfecta.

Es la tercera vez en este trabajo que el instrumento miente, y las tres con
signo distinto: en la trampa 004 **exageraba** el fallo (11 % siendo 99 %); en la
bitácora [001](001-error-identidad-se-mide-en-trayectorias.md) lo **escondía** por
dilución del denominador; aquí lo **acota por arriba** y hace indistinguibles el
acierto y el desastre.

La regla que se extrae es concreta: **una métrica de duración no se mide en una
ventana del orden de la duración que se quiere medir.** El banco de pruebas debe
cubrir al menos un ciclo completo del fenómeno —aquí, una jornada de servicio con
su arranque y su apagado.

Aguas abajo el efecto habría sido grave y silencioso: una trayectoria de 19,8 h
atribuye a un único vehículo las posiciones de docenas, y todas las etiquetas de
retraso derivadas de ella pertenecen a autobuses distintos del que dice la
etiqueta.

## Qué se hizo / qué queda abierto

Hecho:

- **Descartado agrupar por `linea` sin restricción.** Es el arreglo con más
  potencial —el giro en cabecera explica el 93 % de las bajas de trayectoria,
  349 de 375 por hora— pero quitar `trayecto` de la clave elimina la única cota
  que hoy limita la longitud de cadena, y la puerta física (70 km/h, 800 m) no
  distingue «el mismo autobús» de «otro de la misma línea a 60 m».
- **Aplicado tolerar huecos de 2 sondeos** (`rastrear(..., tolerar_hueco=2)`, ya
  el valor por defecto): mantiene la distribución acotada (p99 = 83,9 min,
  coherente con un servicio real) y lleva la mediana de 10,5 a 21,1 min sin
  descartar ninguna posición. Verificado que `tolerar_hueco=0` reproduce el
  comportamiento previo **exactamente** —mismo `vehicle_id`, `dist_m` y `dt_s`—
  sobre siete conjuntos, incluidas 22.208 posiciones reales.
- **El puente se acota en segundos, no solo en sondeos** (`HUECO_MAX_S = 120`).
  Dos sondeos no siempre son 60 s: durante la parada de 445 s del colector,
  «dos sondeos» eran 7,5 min, y la puerta física satura en `SALTO_MAX_M` a
  partir de 41 s, de modo que más allá de ahí admitiría a cualquier vehículo
  dentro de 800 m. Guardias:
  `tests/test_tracking_fragmentacion.py::test_el_puente_se_acota_en_segundos_y_no_en_sondeos`
  y `::test_el_paso_inmediato_no_lo_acota_el_tope`, que fija la frontera: el tope
  acota el puente, **no** el paso inmediato.
- **Retirado el tope de longitud de cadena que esta entrada proponía.** Se
  propuso por la longitud sola, y la longitud sola no era evidencia. Examinadas
  las doce cadenas más largas que deja tolerar huecos: ninguna cambia de línea,
  ninguna cambia de sentido, el hueco interno máximo es de 103 s y la cobertura
  temporal es del 0,89-0,97. Se reparten en dos clases, ambas legítimas:
  **vehículos parados** —v00000 recorre 0,2 km en 3,3 h, desplazamiento neto de
  1 m— y **servicios de baja ocupación**: la cadena de 437,1 min es de la línea
  96 «Especial IDA», que tiene **2 autobuses por sondeo** (p50, p90 y máximo), y
  recorre 79,8 km reales a 10,9 km/h de media. En un grupo de uno o dos
  vehículos el emparejamiento no tiene con qué equivocarse. El 6,6 % de las filas
  del día está en grupos (línea, trayecto) con mediana de un solo autobús.
- **Descartado filtrar los snapshots parciales** como arreglo: consigue lo mismo
  que tolerar huecos en el escenario sintético y además descarta el 0,7 % de las
  posiciones del día. La detección sigue siendo útil, pero como marca de calidad
  del dato para el etiquetado, no como filtro del tracking.

Abierto:

- La variante restringida de agrupar por línea —permitir el cambio de `trayecto`
  **solo cerca de una cabecera**— no está implementada ni medida. Ahora es
  viable: el GTFS estático está en `data/raw/gtfs/`.
- **Los escenarios sintéticos duran 20 snapshots (10 min)** y por eso aprobaron
  agrupar por línea en las cinco pruebas. Falta un escenario largo con el censo
  cayendo a casi cero y volviendo a subir, y una aserción sobre el **span
  máximo** de trayectoria, no solo sobre la fragmentación.
- **El paso inmediato no está acotado en segundos.** Si el sondeo intermedio no
  llegó a existir —colector parado—, el paso largo es el paso directo, y ese
  compite siempre. Acotarlo cambiaría el comportamiento histórico con
  `tolerar_hueco=0`, que es una decisión aparte de esta. La frontera está fijada
  por test para que el día que se cambie, se cambie a sabiendas.
- El 6,6 % de las filas vive en grupos (línea, trayecto) con **un solo autobús**.
  Ahí la identidad es trivial, y eso **infla artificialmente** cualquier métrica
  agregada de calidad del tracking. Conviene reportar las métricas separando por
  ocupación de grupo antes de afirmar nada sobre la reconstrucción en conjunto.

## Para la memoria

> La reconstrucción de identidad produce trayectorias considerablemente más
> cortas que los servicios reales: sobre la jornada del 27 de agosto de 2026 se
> obtuvieron 12.709 trayectorias con una mediana de 10,5 minutos, frente a
> servicios de entre 30 y 60 minutos. Se identificaron dos causas dominantes de
> esa fragmentación —el cambio de sentido en cabecera, que altera la clave de
> agrupación, y los sondeos con carga útil truncada— y se evaluaron tres
> correcciones en un banco de pruebas aislado, verificando previamente que con
> las correcciones desactivadas reproducía el comportamiento de referencia de
> forma exacta.
>
> La evaluación inicial se realizó sobre una ventana de una hora y señalaba como
> mejor corrección la agrupación por línea, que elevaba la longitud mediana de 7
> a 57 minutos. Esa conclusión resultó ser un artefacto del procedimiento de
> medida: una ventana de 117 sondeos abarca 58,5 minutos, de modo que la métrica
> está censurada por arriba y no distingue una reconstrucción correcta de una
> fusión indiscriminada de identidades. Repetida la evaluación sobre la jornada
> completa, esa misma configuración produjo una trayectoria de 19,8 horas y un
> percentil 99 de 14 horas, con una mediana de 2,5 minutos: una distribución
> bimodal en la que unas pocas cadenas absorben la mayor parte de las posiciones.
> El examen de una ventana de 5,5 horas que incluye el cese del servicio mostró
> el mecanismo: una cadena de 653 posiciones cubre la ventana completa sin
> discontinuidades temporales superiores a 2,2 minutos, encadenando vehículos
> sucesivos de la misma línea.
>
> Se concluye que el campo de sentido actuaba como cota implícita de la longitud
> de cadena y que eliminarlo de la clave de agrupación requiere sustituir esa
> cota por una restricción geográfica a las proximidades de cabecera. De ello se
> deriva un criterio metodológico aplicado en lo sucesivo: una métrica de
> duración no puede evaluarse sobre una ventana de observación del mismo orden de
> magnitud que la duración que pretende medir.
