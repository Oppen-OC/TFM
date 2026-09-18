---
id: 022
titulo: El map-matching aguanta en septiembre (4,2 m de mediana, avance 0,996 frente a 0,03) y los abiertos de la 016 tienen causa, casi todos cocheras, cabeceras y desvíos
fecha: 2026-09-18
tipo: medicion
capa: etiquetado
capitulo: calidad-dato
impacto: alto
estado: mitigado
evidencia: uv run python -m project.analysis.investigar_mapmatching DIR resumen (tras validar_mapmatching --guardar DIR); salidas en auditoria/resultados/*_0501d58.*
trampa: 006
---

## Qué se observó

Se validaron 32 jornadas (del 15/08 al 10/09 y del 14 al 18/09) sobre el curated
reprocesado (entrada 019). Los agregados usan sólo los **26 días completos**, los
que tienen al menos el 90 % de los sondeos de un día normal: 14 de agosto y 12 de
septiembre. Los días 15, 18 y 21/08 y 10, 14 y 18/09 se miden, pero no entran
en los agregados.

| mediana de los días | ago < 24 | ago ≥ 24 | sep |
|---|---|---|---|
| días completos | 6 | 8 | 12 |
| posiciones | 2,10 M | 2,90 M | 4,80 M |
| distancia al trazado, p50 | 3,95 m | 4,12 m | 4,21 m |
| fuera de ruta, 7-22 h | 4,3 % | 5,0 % | 5,1 % |
| ambiguas | 2,1 % | 2,7 % | 2,6 % |
| sin trazado en el GTFS | 0,9 % | 0,9 % | **2,5 %** |

El sentido se decide por el avance, medido en los grupos (línea, trayecto) con al
menos 1.000 posiciones en el mes:

| | agosto | septiembre |
|---|---|---|
| grupos, y parte de las posiciones que cubren | 69 (99,90 %) | 91 (99,85 %) |
| avance sobre el trazado elegido, p50 (mínimo) | 0,997 (0,909) | 0,996 (0,88) |
| avance sobre el mejor alternativo, p50 | 0,02 | 0,03 |
| cobertura, p50 (p10) | 0,902 (0,777) | 0,904 (0,727) |

**Veredicto: el map-matching vale para septiembre.** Los abiertos de la 016:

1. **Línea 40: el trazado no está mal.** Sus dos sentidos casan en 15-21 días,
   con p50 de 4,3 y 5,1 m. En los días sin cobertura (6 en un sentido y 2 en el
   otro), la mayoría de sus posiciones caen en celdas fijas de cochera (1.028 de
   1.308 y 744 de 890): es un bus aparcado que publica la línea. La **6 Torrefiel → Hosp. La Fe** tiene
   cobertura 0 a 2,6 km en septiembre, y es el mismo caso: 1.229 posiciones en
   una sola celda, sólo el 0,2 % en horario de servicio.

   Clasificados todos los grupo-día con cobertura inferior al 20 % y al menos
   50 posiciones:

   | clase | grupos | posiciones |
   |---|---|---|
   | aparcados en cochera | 19 | 17.223 |
   | circulan sobre el trazado de **otra** línea | 16 | 2.135 |
   | sin explicar | 5 | 2.038 |

   Los segundos son buses publicados con otro número de línea: la
   «70 La Malva-rosa - P. Congressos» va exacta sobre la 99, y la
   «19 Hosp. Dr. Peset - Platges» sobre la 18.
2. **C3 Campanar → C. Benlloch (cobertura del 65 %).** El 95,2 % de lo que se
   sale de ruta está **antes del inicio del trazado**, a 95 m de mediana, en
   dos celdas contiguas: (39,484, −0,392). Es la regulación en la cabecera de
   Campanar. Sobre el recorrido, el fuera de ruta es del 0 al 2 %, salvo en el
   tramo de 4,5-5 km (10,8 %).
3. **Línea 24.** Vehículo a vehículo, el sentido no deja dudas: hacia El
   Palmar, 869 de 895 trayectorias eligen 1049_2253_2172, con cobertura y
   avance de 1,0. Las variantes de un mismo sentido empatan porque comparten
   recorrido:
   - 2253_2172 queda entera a ≤ 20 m de 2253_2173, que se alarga 634 m por el
     final;
   - 2172_2253 y 2173_2253 sólo se separan en los primeros 600 m.

   **La 73 tiene el mismo problema, pero sus variantes se separan en mitad del
   recorrido**: un kilómetro, entre los 2.850 y los 3.825 m de abscisa.
4. **Umbral de 60 m.** La densidad de distancias baja al 0,02 % por metro entre
   50 y 60 m, y mover el umbral de 50 a 80 m cambia el fuera de ruta en 0,5 pp.
   Hay un segundo máximo entre 80 y 100 m. La franja de 60-200 m la explican la
   C3 (el 44 %), la 92, la 28 y la 67: regulación en cabecera. **El umbral se
   queda en 60 m.**
5. **Ambiguas: 2,5 %, igual en los dos meses.** La 23 aporta el 17 % (el
   25,6 % de sus propias posiciones son ambiguas); le siguen la 27, la 93, la 26
   y la 28. Se acumulan en el primer y el último 20 % del recorrido y hacia la
   mitad: bucles de cabecera y calles de ida y vuelta.
6. **La subida del fuera de ruta tras el 24/08 no está en las cocheras**, que
   se mantienen en 1,5-1,6 pp. Sube el resto, de 2,8 % a 3,9 %:
   - El pico del 27 al 30/08 lo causan las **25 y 24**, costeras del sur: su
     fuera de ruta pasa del 2,2 % al 24,3 % y al 15,4 %, y en septiembre vuelve
     al 4-5 %. Es un desvío temporal.
   - En septiembre suben la **92** (de 1,4 % a 7,6 %), la **32** (de 2,4 % a
     7,5 %) y la **4** (de 2,3 % a 9,7 %).
7. **Grupos que cambian de trazado: 19 de 146**, con 707.000 de 10,3 M de
   posiciones. O el grupo entero está ese día fuera de ruta (cobertura 0, y
   entonces la elección no importa), o son variantes del mismo sentido (la 24
   y la 73).
8. **Líneas sin GTFS.**
   - La 96 (98.446 posiciones en 29 días), la 98E (11.955) y la 100 (6.486) no
     están en `routes.txt`.
   - La **63 Campus de Burjassot - Est. del Nord** aparece el 31/08 (66.258
     posiciones en 14 días). Está en `routes.txt`, pero con **0 viajes**. Es la
     razón de que el sin trazado pase del 0,9 % al 2,5 %.
9. **Sin abscisa fiable: el 13,4 % en todas las horas**, pero de 7 a 22 h es
   el 6,6 % en agosto y el 8,2 % en septiembre. El resto es cochera nocturna. En
   septiembre, de 7 a 22 h, se reparte así: fuera de ruta 5,2 %, sin trazado
   2,1 %, ambigua 0,9 % y sin trayecto 0,05 %.

## Cómo se midió

```bash
uv run python -m project.analysis.validar_mapmatching --dias <los 32 días> \
    --procesos 8 --guardar DIR --json auditoria/resultados/mapmatching_ago_sep_0501d58.json
uv run python -m project.analysis.investigar_mapmatching DIR resumen linea40 c3 l24 \
    variantes umbral ambiguas fuera fuera_lineas sin_abscisa nulos sin_cobertura
```

Las salidas están en `auditoria/resultados/*_0501d58.*`. El avance mensual sale
de `grupos_por_dia` del JSON: media de `avanza` y `avanza_otro` por grupo,
ponderada por posiciones y **sólo sobre los días con avance medido**, en los
días completos.

El feed se inspeccionó leyendo `routes.txt` y `trips.txt` del zip de
`settings.gtfs_zip` (versión `01-09-2026`, vigente del 24/08 al 30/09).

**Control del instrumento.** El 27/08 sobre el curated del colector reproduce
exactamente la 016: 353.604 posiciones, fuera de ruta 10,75 %, ambiguas 2,8 %,
p50 4,1 m y p90 94,2 m. Antes de fichar se corrigieron dos fallos propios:

- El reparto de la C3 por tramos excluía la abscisa 0 (`pd.cut` sin
  `include_lowest`), que es donde está el 95 % de lo que se sale.
- El avance mensual ponderado contaba en el denominador los días sin avance
  medido, y daba un mínimo de 0,359 que no existe.

## Por qué importa

Es el visto bueno para etiquetar septiembre con este feed, con cuatro
condiciones para el paso 2:

- **La segmentación tiene que distinguir tres estados.** Una posición en celda
  de cochera es un bus fuera de servicio; una espera antes de la abscisa 0 es
  regulación en cabecera, no retraso en ruta; y el resto es servicio.
- **La variante se decide por viaje, no por grupo y día** (24 y 73). El paso
  por parada se interpola sobre el mismo trazado que se usó para la abscisa
  del vehículo; si no, la 73 arrastra un kilómetro de desfase.
- **Hay líneas que no se pueden etiquetar con este feed**: la 63, que no tiene
  horario, y la 96, la 98E y la 100, que ni siquiera tienen ruta.
- **Los tramos desviados no tienen abscisa** (la 24 y la 25 a finales de
  agosto; la 92, la 32 y la 4 en septiembre), así que ahí no se puede
  interpolar el paso por parada.

La línea mal publicada no es un error del método, pero sí de la fuente: el
número de línea no siempre dice qué recorrido hace el bus. Son 2.135 posiciones
y se pueden ignorar; que existan ya es un dato.

## Qué se hizo / qué queda abierto

Hecho: `validar_mapmatching --guardar` y `analysis/investigar_mapmatching.py`.
No se ha tocado `mapmatching.py`, ni sus constantes.

Abierto:

- **Un feed más reciente.** Hace falta para la 63, y para comprobar si la 92,
  la 32 y la 4 cambiaron de recorrido en septiembre. El GTFS tampoco guarda
  histórico: cada versión que se descargue hay que conservarla.
- Los 5 grupos de la clase "sin explicar" (2.038 posiciones).
- La elección de variante por viaje, en el paso 2.
- Lo que queda de la 016 y no se cierra aquí: resolver las ambiguas con la
  continuidad de la trayectoria, que es trabajo de la segmentación.

## Para la memoria

> La validación de la correspondencia con la red teórica se repitió sobre 26
> jornadas completas, catorce de agosto y doce de septiembre. La distancia
> mediana al trazado se mantiene entre 3,95 y 4,21 metros. El criterio de
> sentido distingue el recorrido correcto del opuesto con una fracción de
> avance mediana de 0,996 frente a 0,03 en los 91 grupos que concentran el
> 99,85 % de las posiciones de septiembre. Las posiciones que no se
> corresponden con su recorrido tienen causas identificables: vehículos
> aparcados en cocheras, que siguen publicando su línea; esperas de regulación
> en cabecera, antes del inicio del trazado; desvíos temporales, que en las
> líneas costeras del sur llegaron a afectar a una cuarta parte de sus
> posiciones durante cuatro días de agosto; y vehículos publicados con el
> número de otra línea. El feed vigente no contiene el horario de una línea
> universitaria que comenzó a circular el 31 de agosto, lo que eleva al 2,5 %
> las posiciones sin trazado en septiembre y la deja fuera del etiquetado
> mientras no se disponga de una versión posterior del GTFS.
