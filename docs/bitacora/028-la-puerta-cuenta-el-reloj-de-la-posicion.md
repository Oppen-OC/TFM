---
id: 028
titulo: La puerta física cuenta también el reloj de la posición y la 24 pasa de 4.272 a 13.596 pasos etiquetados, sin mover las líneas urbanas; subir el umbral a 100 km/h recuperaba lo mismo pero aceptaba saltos imposibles
fecha: 2026-09-23
tipo: tecnica
capa: tracking
capitulo: metodologia
impacto: alto
estado: resuelto
evidencia: uv run dvc repro prepare && uv run python -m project.analysis.medir_rutas lineas; barrido con auditoria/banco_tracker.py --tracker
trampa: 013
---

## Qué se observó

La entrada 026 atribuyó a la puerta física la pérdida de la línea 24. Tenía dos
componentes que se suman: el umbral urbano (70 km/h, 583 m por sondeo) y el
reloj con que se medía el paso, el `ts_utc` máximo del sondeo. Cuando la
posición de un bus llega atrasada en un sondeo y al día en el siguiente, el
desplazamiento real de ~50 s se divide entre ~30.

Barrido de candidatos sobre el 20/08 y el 27/08 (días de servicio completos;
trayectorias por línea con las seis líneas de la tabla, `ida_vuelta` y
trayectorias totales con el banco sobre la jornada entera):

| candidato | 24 | urbanas (31, 99, 93, C3) | trayectorias totales | `ida_vuelta` | tests |
|---|---|---|---|---|---|
| actual (70 km/h, reloj del sondeo) | 410 · 631 | — | 7.392 · 7.627 | 234 · 230 | verde |
| A: 100 km/h | 190 · 228 | −0,9 a −3,6 % | 6.499 · 6.418 | 240 · 235 | **rompe dos guardias** |
| A: 100 km/h, 1.200 m | 132 · 141 | −1,1 a −3,6 % | 6.193 · 6.003 | 240 · 233 | rompe dos guardias |
| **B: máximo de los dos relojes, 70 km/h** | **214 · 244** | **−0,7 a −2,2 %** | 6.643 · 6.596 | 234 · 233 | verde, reescrita la del suavizado |
| B con 1.200 m | 155 · 163 | −1,1 a −2,8 % | 6.357 · 6.284 | 234 · 232 | ídem |
| A+B, 100 km/h, 1.200 m | 122 · 113 | — | 6.068 · 5.694 | 239 · 234 | rompe dos guardias |

Subir el umbral rompe `test_salto_imposible_rompe_la_cadena[550m]` (acepta que
un bus a 15 km/h aparezca 675 m más allá en 30 s) y
`test_la_puerta_fisica_sigue_mandando_con_abscisa`. Con `SALTO_MAX_M` en 800 m,
además, el umbral de velocidad deja de pesar a 30 s de cadencia y el mutante 022
pasaría inadvertido.

**Se eligió B, el mínimo que cumple.** La versión integrada en `tracking.py`
(`_dt_puerta`, también en el suavizado y en `dt_s`) da en el banco real 6.643 y
6.596 trayectorias, **0** desplazamientos por encima de su puerta y
`ida_vuelta` 236 y 232: dos más cada día que la actual (+0,9 %). El indicador es
una cota inferior de intercambios; la simulación, con semillas de ajuste y con
las reservadas miradas una vez, sale idéntica a la actual, porque la flota
simulada no pasa de 30 km/h y la puerta no llega a actuar.

Tras `dvc repro prepare`, por línea, frente a la salida de `25c4e5b`:

| línea | asignados | pasos | cambio en pasos |
|---|---|---|---|
| **24** | 457 → **900** | 4.272 → **13.596** | **×3,2** |
| **25** | 100 → **551** | 826 → **7.413** | **×9,0** |
| 23 (Forn d'Alcedo) | | 21.049 → 23.706 | +12,6 % |
| 26 (Moncada) | | 32.292 → 33.342 | +3,3 % |
| 31, 99, 93, C3, 92, 95, 19 | idénticos ±2 | | 0,0 a +0,4 % |

La 24 y la 25 pasan del 0,33 % al **1,33 %** de los pasos, con el 4,94 % de las
posiciones. Total: 1.550.607 → 1.574.436 pasos (+1,5 %), 70.600 → 71.537
asignados, 76.061 → 60.424 tramos cortos. Las líneas que mejoran son las que
salen del término por carretera: el mismo mecanismo, con menos peso.

## Cómo se midió

```bash
# candidatos: copias de tracking.py con el cambio, fuera del repo
uv run python auditoria/banco_tracker.py --tracker CAND.py --real 2026-08-20 2026-08-27 --etiqueta X
uv run python auditoria/banco_tracker.py --reservadas --etiqueta final     # una vez
uv run dvc repro prepare
uv run python -m project.analysis.medir_rutas lineas
```

Las trayectorias por línea de la tabla del barrido rastrean solo las seis
líneas medidas, así que la 24 da 410 y no las 363 de la entrada 026, que rastreó
la 24 sola: el reloj del sondeo sale de las filas que se le pasan. La
comparación entre candidatos usa siempre el mismo subconjunto. El «antes» por
línea se leyó de la caché de DVC con los `md5` de `dvc.lock` en `25c4e5b`.

## Por qué importa

- Resuelve la mitad de la entrada 026 que tocaba al tracker, y la 25 se recupera
  también en parte (×9 en pasos), aunque su causa principal, la alternancia del
  trayecto en la fuente, sigue abierta.
- La etiqueta de las líneas urbanas no cambia. El sesgo que retiraba del corpus
  las líneas con menos sensores de tráfico se reduce sin tocar el resto.
- La elección deja escrito por qué no se sube el umbral: es el arreglo obvio y
  rompe dos guardias.

## Qué se hizo / qué queda abierto

Hecho: `tracking._dt_puerta` en el emparejamiento, en el suavizado y en `dt_s`;
el predictor sigue con el reloj del sondeo, porque mezclar relojes en su
cociente es la trampa 009. Test nuevo
`test_un_bus_cuyas_posiciones_llegan_con_retraso_no_se_parte`;
`test_el_suavizado_mide_el_tiempo_con_el_reloj_de_sondeo` pasa a exigir el
máximo de los dos relojes y nunca menos que el del sondeo. Mutante 075 nuevo, y
el 072 (`VEL_MAX_KMH = 40`) previsto como detectado. Trampa 013 cerrada.

Abierto:

- `ida_vuelta` +2 al día. Pequeño, pero es el único indicador real de
  intercambios y no baja.
- La alternancia de la 25 (entrada 026).
- Las cifras de la entrada 024 se calcularon con el tracker anterior.

## Para la memoria

> El umbral físico del emparejamiento limita el desplazamiento de un vehículo
> entre dos consultas a lo que recorrería a 70 km/h. Inicialmente, el tiempo
> transcurrido se medía con la marca más reciente de cada consulta. Cuando la
> posición de un vehículo llega con retraso en una consulta y actualizada en la
> siguiente, esa medida subestima el tiempo real y convierte velocidades de
> carretera de unos 63 km/h en velocidades aparentes de unos 88 km/h, lo que
> fragmentaba las líneas interurbanas. Se evaluaron dos alternativas: elevar el
> umbral a 100 km/h, el límite legal de los autobuses, y medir el tiempo con la
> mayor de las dos marcas, la de la consulta y la de la propia posición. Ambas
> recuperan las líneas afectadas, pero la primera admite desplazamientos
> físicamente imposibles en un vehículo que circula despacio, por lo que se
> adoptó la segunda. Con ella, los pasos etiquetados de la línea 24 se
> multiplican por 3,2 y los de la 25 por 9, mientras que el etiquetado de las
> líneas urbanas varía menos de un 0,5 %.
