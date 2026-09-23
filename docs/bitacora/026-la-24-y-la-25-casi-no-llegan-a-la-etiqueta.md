---
id: 026
titulo: La 24 y la 25 son el 4,9 % de las posiciones y el 0,37 % de los pasos etiquetados; a la 24 la trocea la puerta física del tracker y a la 25 una fuente que alterna el trayecto a mitad de ruta
fecha: 2026-09-23
tipo: anomalia
capa: tracking
capitulo: metodologia
impacto: alto
estado: mitigado
evidencia: uv run python -m project.analysis.medir_rutas lineas | rupturas | contrafactual | alternancia --dia 2026-08-20
trampa: 013
---

## Qué se observó

Sobre la salida de `prepare` (32 jornadas, 10.457.901 posiciones, 2.103.594
pasos):

| línea | posiciones | tramos | asignados | cortos | éxito con cortos | pasos |
|---|---|---|---|---|---|---|
| 25 | 308.119 | 40.601 | 186 | 40.411 | **0,5 %** | 1.562 |
| 24 | 208.191 | 13.628 | 678 | 12.913 | **5,0 %** | 6.360 |
| resto con > 100.000 posiciones | | | | | 33-82 % | |

Juntas son el **4,94 %** de las posiciones y el **0,37 %** de los pasos (7.922):
13 veces menos de lo que les toca. La tasa de éxito de la entrada 024 (94 %) no
lo ve porque cuenta sobre los tramos de servicio, que excluyen los cortos, y es
ahí donde acaban las dos líneas.

**Son dos causas distintas, y el contrafactual las separa.** Rastreando el
mismo día con la puerta física de `tracking.py` (70 km/h, 800 m) y abierta a
100 km/h y 1.200 m:

| línea | 20/08, puerta actual → abierta | 27/08, puerta actual → abierta |
|---|---|---|
| 24 | 363 → **144** trayectorias, mediana 13 → **48** posiciones | 599 → **169**, mediana 2 → **36** |
| 25 | 1.259 → 731, mediana 3 → 5 | 1.636 → 871, mediana 2 → 4 |
| 31 (control) | 227 → 223, mediana 110 → 111 | 216 → 212, mediana 110 → 111 |

- **La 24: la puerta.** Entre el final de una trayectoria y su sucesora, dentro
  de los dos sondeos siguientes (268 casos el 20/08, de 7 a 21 h), hay 773 m de
  mediana. Con el reloj de sondeo que usa la puerta son 88,5 km/h, y el 99 %
  pasa de 70. Con el `ts_utc` del propio bus son **62,7 km/h**, y el 95 % queda
  por debajo de 90. Es la velocidad de un autobús por la CV-500. Las rupturas
  por posición son del 3,6-11,2 % en las franjas de carretera, frente al 1,8 %
  en el centro. Con la puerta abierta del todo (1.000 km/h, 5 km) la 24 baja a
  105 trayectorias con mediana de 87.
- **La 25: la fuente.** Con la puerta abierta del todo sigue en 465
  trayectorias con mediana de 6, con 6 buses por sondeo estables. La capa
  publica **el trayecto contrario para el mismo bus a mitad de ruta**: un bus que
  avanza hacia el norte de 39,3589 a 39,3764 alterna «El Perelló - Pta. de la
  Mar» y «Pta. de la Mar - El Perelló» cada uno o dos sondeos. El tracker agrupa
  por (línea, trayecto) y cada alternancia corta la cadena.

Alternancia limpia —pasos de un mismo bus a más de 1 km de cabecera en que
cambia el texto, descontados los que pueden ser dos buses que se cruzan—:

| línea | 17/08 | 20/08 | 27/08 | 03/09 |
|---|---|---|---|---|
| **25** | **8,0 %** | **9,0 %** | **6,9 %** | **7,7 %** |
| 24 | 0,8 % | 0,6 % | 0,6 % | 1,4 % |
| 31 | 0,0 % | 0,0 % | 0,0 % | 0,2 % |

El 20/08, la 99, la 93 y la C3 dan 0,3-0,4 %. Es una cota inferior: se descuenta
como posible cruce todo cambio con un bus del trayecto original a menos de
700 m.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_rutas lineas
uv run python -m project.analysis.medir_rutas rupturas --dia 2026-08-20
uv run python -m project.analysis.medir_rutas contrafactual --dia 2026-08-20   # y --dia 2026-08-27
uv run python -m project.analysis.medir_rutas alternancia --dia 2026-08-20     # y 17/08, 27/08, 03/09
```

Las cifras de la primera tabla son de la salida de `prepare` de `cdcd097`, antes
de excluir el 31/08-07/09 y de procesar por día de servicio (entrada 027). Con la
salida actual, las dos líneas son el 4,94 % de las posiciones y el **0,33 %** de
los pasos (5.098 de 1.550.607): la conclusión no cambia.

`lineas` lee `data/interim/`; `contrafactual` y `alternancia` vuelven a
`data/curated/` con `prepare.cargar_dia`. El contrafactual cambia
`tracking.VEL_MAX_KMH` y `tracking.SALTO_MAX_M` en memoria y los restaura: no toca
el código. La cifra de 1.000 km/h y 5 km sale del mismo procedimiento con esos
valores.

**El instrumento se comprobó antes que lo medido.** La primera lectura atribuía
también la 25 a la puerta, por la velocidad inferida en sus rupturas. El
contrafactual lo desmintió (la 25 apenas se recompone) y obligó a buscar la
segunda causa. La alternancia se validó contra cuatro líneas urbanas de control
(31, 99, 93 y C3), que dan 0,0-0,4 %.

## Por qué importa

- **Sesgo de selección favorable a la hipótesis.** Es la trampa 006, que entra
  por otra capa. La 24 y la 25 son las líneas con peor cobertura de sensores de
  tráfico (20 % y 28 %). Perderlas deja la muestra en los corredores urbanos
  bien instrumentados e infla la aparente utilidad de la fusión con tráfico, sin
  tocar la etiqueta de ninguna otra línea.
- **La tasa de éxito publicada lo esconde.** Cualquier tasa calculada «sobre los
  tramos de servicio» excluye justo los tramos cortos, donde acaban las líneas
  troceadas. En adelante, la cobertura se informa por línea y con los cortos en
  el denominador.
- La 25 tiene además su caída de publicación desde el 09/09 (entrada 025): lo
  poco que hay de ella en septiembre tampoco se etiqueta.

## Qué se hizo / qué queda abierto

Hecho: el medidor `src/project/analysis/medir_rutas.py`, la ficha de trampa
013 (puerta física) y el mutante 072 (`VEL_MAX_KMH = 40.0`) al catálogo, previsto
como hueco.

Abierto:

- ~~La puerta (24).~~ Resuelto en la entrada 028: la puerta cuenta también el
  reloj de la posición. La 24 pasa de 4.272 a 13.596 pasos y la 25 de 826 a
  7.413, sin mover las líneas urbanas.
- **La alternancia (25).** Agrupar por línea sin trayecto se descartó en la 008
  y la 009 porque dobla la contaminación en las líneas urbanas. Hace falta una
  regla que trate el trayecto como ruidoso solo cuando alterna, o decidir el
  sentido por el movimiento, como ya hace el map-matching.
- Guardia que falta: un bus cuyo `trayecto` alterna a mitad de ruta. La de la
  puerta es `test_un_bus_cuyas_posiciones_llegan_con_retraso_no_se_parte`.

## Para la memoria

> Las dos líneas que salen del término municipal por la costa sur, la 24 y la
> 25, aportan el 4,9 % de las posiciones capturadas, pero solo el 0,37 % de los
> pasos por parada etiquetados. La pérdida se produce en la reconstrucción de
> trayectorias y obedece a dos causas independientes, separadas mediante un
> experimento contrafactual. En la línea 24, el umbral físico de velocidad del
> emparejamiento, fijado en 70 km/h para un autobús urbano, rechaza los pasos
> por carretera interurbana, donde los vehículos circulan a unos 63 km/h
> medidos con su propia marca temporal. Relajarlo reduce sus trayectorias de
> 363 a 144 en una jornada, sin alterar las de una línea urbana de control. En
> la línea 25, la fuente publica de forma intermitente el sentido contrario para
> un mismo vehículo a mitad de recorrido, entre el 6,9 % y el 9,0 % de sus pasos,
> frente a menos del 0,5 % en las líneas de control. Como el emparejamiento se
> restringe a vehículos de la misma línea y sentido, cada alternancia interrumpe
> la trayectoria. Ambas líneas son las de menor cobertura de sensores de
> tráfico, por lo que su exclusión sesgaría la muestra hacia los corredores
> mejor instrumentados. La cobertura del etiquetado se informa por línea,
> incluyendo en el denominador los tramos que no alcanzan la longitud mínima.
