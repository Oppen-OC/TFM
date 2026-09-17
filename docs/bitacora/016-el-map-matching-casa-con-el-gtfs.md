---
id: 016
titulo: Las posiciones de la EMT casan con los trazados del GTFS a 4 m de mediana y el sentido se decide por el movimiento con avance 0,998 frente a 0,018; lo que queda fuera de ruta son buses en cochera
fecha: 2026-09-17
tipo: medicion
capa: etiquetado
capitulo: calidad-dato
impacto: alto
estado: mitigado
evidencia: uv run python -m project.analysis.validar_mapmatching
trampa: 010
---

## Qué se observó

Map-matching de los 17 días capturados, **5.163.031 posiciones**, proyectando
cada una sobre el trazado GTFS de su línea (`src/project/mapmatching.py`):

| magnitud, por jornada | mínimo | mediana | máximo |
|---|---|---|---|
| distancia al trazado, p50 | 3,7 m | 4,0 m | 4,3 m |
| distancia al trazado, p90 | 13,1 m | 52,0 m | 410,3 m |
| fuera de ruta (> 60 m) | 2,6 % | 9,9 % | 12,5 % |
| **fuera de ruta, 7-22 h** | **2,3 %** | **4,8 %** | **9,1 %** |
| fuera de ruta, 0-6 h | 3,3 % | 52,4 % | 66,3 % |
| parte del fuera de ruta en 10 celdas de 100 m | 48,9 % | 67,0 % | 77,4 % |
| ambiguas (el trazado pasa dos veces cerca) | 0,8 % | 2,4 % | 3,2 % |
| línea sin trazado en el GTFS | 0,3 % | 0,9 % | 2,5 % |

**Lo que queda lejos del trazado no es error de proyección: son buses fuera de
servicio.** De madrugada lo está la mitad de la flota, y entre el 49 % y el 77 %
de esas posiciones caen en diez celdas de 100 m. Las dos que se repiten todos
los días son (39,481, −0,334) y (39,452, −0,407), dos emplazamientos fijos
compatibles con cocheras. En horario de servicio el fuera de ruta baja al 4,8 %
de mediana.

**El sentido se decide por el movimiento y no deja lugar a dudas.** En los 70
grupos (línea, trayecto) con más de 1.000 posiciones —el **99,84 %** del total:

| | trazado elegido | mejor alternativo |
|---|---|---|
| fracción de pasos que avanzan, mediana | **0,998** | **0,018** |
| cobertura (posiciones a < 60 m), mediana | 91,9 % | — |
| distancia mediana al trazado | 3,6 m | — |

La cobertura p10 es 78,9 % y el avance mínimo, 0,809. Los trazados de ida y
vuelta van por las mismas calles y están a la misma distancia: sin el criterio
de avance, la mitad de los grupos quedarían en el trazado contrario y la abscisa
correría hacia atrás.

**Tres anomalías**, todas acotadas:

- **Línea 40, sentido Universitats → Est. del Nord**: cobertura **0**, a 826 m de
  mediana del único trazado que el GTFS ofrece. 1.163 posiciones en 8 días. Su
  recorrido real no está en este feed.
- **C3, Campanar → C. Benlloch**: cobertura 65,3 %. El trazado elegido es el
  único sobre el que sus buses avanzan (1,0 frente a 0,004), pero un tercio de
  sus posiciones queda a más de 60 m.
- **Línea 24, sentido Pta. Mar → El Palmar**, 3 días: dos variantes del trazado
  (El Saler y El Palmar) empatan en cobertura (0,444) y en avance (0,809 y
  0,805). La elección entre variantes de un mismo sentido no está resuelta.

Además, 10 de 103 grupos reciben trazados distintos según el día; todos son
grupos pequeños, por debajo de 1.000 posiciones.

**Vigencia del feed.** Los nueve días anteriores al 24/08 no casan peor: la
distancia mediana es 3,88 m antes y 4,13 m después. Lo que sube después es el
fuera de ruta (7,8 % → 11,3 %), también en horario de servicio (4,1 % → 5,8 %).
No se explica por geometría desfasada y queda abierto.

**Coste**: emparejar los 17 días cuesta **259 s** en total; reconstruir la
identidad con `rastrear`, 4.637 s.

## Cómo se midió

```bash
uv run python -m project.analysis.validar_mapmatching --json auditoria/resultados/mapmatching_17dias.json
uv run python auditoria/mutar.py --solo 041 042 043 044 045 046 047
```

Cada jornada se carga filtrando por `ts_ingest_utc` sobre todas las particiones,
no por `date=` (entrada 011). Resultados por día y por grupo en
`auditoria/resultados/mapmatching_17dias.json`.

Comprobación del instrumento, y un fallo propio que ilustra el riesgo: la
primera versión elegía el trazado con una muestra de los primeros `vehicle_id`,
que son **los buses aparcados de madrugada**. Con ellos, todos los candidatos
quedaban a kilómetros y el sentido se decidía sobre ruido: la línea 24 quedó
asignada a un trazado a 4 km de mediana cuando sus buses circulan a 2 m del
suyo. Se corrigió haciendo que solo cuenten las posiciones que están sobre algún
candidato. El primer test que escribí para guardarlo **no discriminaba** —los
buses de la cochera sintética se proyectaban todos sobre el mismo extremo y no
votaban—; el catálogo de mutantes lo delató (044 salió equivalente) y el
escenario se rehízo con buses maniobrando a 150 m de la ruta en sentido
contrario.

## Por qué importa

La abscisa es el eje sobre el que se interpola el paso por parada, y por tanto
el primer término del retraso. Que el 99,84 % de las posiciones caiga a 4 m de
un trazado con el sentido bien resuelto es la condición que hace viable el
etiquetado.

Y da la información que el tracker no tiene. Dos buses de la misma línea y
sentido recorren la misma calle en el mismo orden: eso no se ve en coordenadas
sueltas, y es lo que dejó sin resolver el 30 % de los intercambios de identidad
(entrada 015).

El fuera de ruta no es una tasa de error del método sino una **medida de tiempo
fuera de servicio**, y como tal habrá que tratarla al segmentar viajes: un bus en
cochera no tiene retraso que medir.

## Qué se hizo / qué queda abierto

Hecho: `src/project/gtfs.py`, `src/project/mapmatching.py`,
`src/project/analysis/validar_mapmatching.py`, 14 tests con verdad-terreno
sintética y los mutantes 041-047 del catálogo. Cierran dos fichas de trampa: la
**006** (el filtro es la distancia al trazado, nunca una caja geográfica) y la
**010** (`shape_dist_traveled` se ignora).

Abierto:

- El recorrido real de la línea 40 en sentido Universitats → Est. del Nord, y el
  tercio de la C3 que no cae sobre su trazado.
- La elección entre variantes de un mismo sentido (línea 24: El Saler o El Palmar).
- El umbral de 60 m para fuera de ruta es provisional: se eligió antes de medir.
  Con la distribución ya medida —p90 de 13 a 52 m en jornada— conviene revisarlo.
- Las ambiguas (2,4 %) se marcan pero no se resuelven: hacerlo con la continuidad
  de la trayectoria es trabajo de la segmentación en viajes.
- Por qué sube el fuera de ruta después del 24/08.

## Para la memoria

> La correspondencia entre las posiciones observadas y la red teórica se
> establece proyectando cada punto sobre la polilínea del recorrido publicado en
> el GTFS, y calculando su abscisa curvilínea, es decir, la distancia recorrida
> desde el inicio del trayecto. Sobre los 5.163.031 registros capturados, la
> distancia mediana entre la posición observada y el trazado asignado es de
> cuatro metros, del orden del error del posicionamiento. La asignación del
> sentido de circulación no puede basarse en la distancia, dado que los
> recorridos de ida y vuelta discurren por las mismas calles: se determina
> exigiendo que la abscisa crezca con el tiempo, criterio que en los grupos que
> concentran el 99,8 % de los registros distingue el trazado correcto del
> opuesto con fracciones de avance de 0,998 frente a 0,018. Las posiciones
> alejadas del recorrido no constituyen error de proyección sino vehículos fuera
> de servicio: representan el 4,8 % de los registros en horario de servicio
> frente a más de la mitad en horario nocturno, y se concentran en unas pocas
> localizaciones fijas correspondientes a cocheras.
