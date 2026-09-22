---
id: 024
titulo: La cascada etiqueta el 94 % de los tramos de servicio de agosto con 2,1 M de pasos; del 31/08 al 11/09 el feed vigente no es el horario que se circula y el éxito cae al 70-75 %
fecha: 2026-09-21
tipo: medicion
capa: etiquetado
capitulo: metodologia
impacto: alto
estado: abierto
evidencia: uv run dvc repro prepare && uv run python -m project.analysis.medir_etiquetado (salida en auditoria/resultados/etiquetado_ead89e9.txt)
trampa: 012
---

## Qué se observó

`dvc repro prepare` sobre las 32 jornadas (15/08-18/09, sin el hueco del
geoportal) en 42 min:

| | |
|---|---|
| posiciones | 10.457.901 (más 5.851 sin trayecto, descartadas y contadas) |
| tramos observados | 221.073 |
| asignados a un viaje programado | 95.960 |
| cortos (esperas, cochera, fragmentos) | 105.618 |
| rechazados por margen, en conflicto o por desfase | 7.846, 7.218 y 472 |
| **pasos por parada con retraso** | **2.103.594** |

Retraso por paso: mediana +17 s, p5 −305 s, p95 +344 s; 1.757 pasos (0,08 %)
superan los 20 min en valor absoluto. El margen del viaje asignado sobre el
segundo candidato tiene p5 de 218 s.

**Éxito sobre los tramos de servicio** (asignados sobre todos los que no son
cortos ni de líneas sin trazado), por periodo:

| periodo | feed | éxito | conflicto | margen | retraso: desv. típica / p95 |
|---|---|---|---|---|---|
| 15/08-30/08 | `01-09-2026` | **94,1 %** | 3,3 % | 2,2 % | 182 s / 291 s |
| 31/08-10/09 | `01-09-2026` | **74,7 %** | 11,1 % | 12,8 % | 252 s / 423 s |
| 14/09-18/09 | `19-09-2026` | **86,9 %** | 4,5 % | 7,8 % | 195 s / 313 s |

**El periodo del medio lo etiqueta un horario que no es el que se circula.** El
`01-09-2026` declara vigencia hasta el 30/09, pero desde el lunes 31/08 hay más
buses que viajes programados (los conflictos se triplican) y el retraso se
ensancha. Forzando el feed `19-09-2026` (vigente desde el 12/09) sobre dos de
esos días:

| día | éxito con 01-09 → con 19-09 | conflicto | desv. típica | asignados |
|---|---|---|---|---|
| 03/09 | 74,7 % → 84,4 % | 10,9 % → 3,6 % | 256 → 222 s | 3.248 → 3.732 |
| 08/09 | 70,7 % → 87,7 % | 12,9 % → 3,9 % | 243 → 188 s | 3.227 → 4.081 |

Cobertura sobre los viajes programados de las líneas capturadas: 78-93 % en los
días completos de agosto y 54-63 % desde el 15/09. Esa caída la pone la fuente,
que deja de publicar líneas (entrada 025), no el método.

Comprobación de cordura, prediciendo el retraso de la parada siguiente de un
mismo viaje: MAE de 151,5 s con el horario (retraso 0) y de 36,3 s con
persistencia (el de la parada actual).

## Cómo se midió

```bash
uv run dvc repro prepare                                  # curar + prepare, ead89e9
uv run python -m project.analysis.medir_etiquetado        # auditoria/resultados/etiquetado_ead89e9.txt
```

El experimento del feed forzado adelanta en memoria el calendario del
`19-09-2026` al 31/08 y etiqueta el mismo día con cada feed:

```python
b = cargar_horario(settings.gtfs_dir / "versiones" / "google_transit2026-09-18.zip")
cal = b.calendar.assign(start_date="20260831")
b = dataclasses.replace(b, calendar=cal, vigencia=(date(2026, 8, 31), b.vigencia[1]),
                        calendario=(date(2026, 8, 31), b.calendario[1]))
r = prepare.etiquetar_dia(prepare.cargar_dia("2026-09-08"), [b], Parametros())
```

Antes, el etiquetado se validó con una verdad conocida:
`tests/test_etiquetado.py` monta un GTFS sintético y una flota con retrasos
decididos por el test, y exige recuperarlos en cada parada con ±5 s. Los
mutantes 056-068 salen detectados salvo el 057 (quitar el máximo acumulado),
que es equivalente con esa flota: se deja declarado en el catálogo.

## Por qué importa

- **La etiqueta existe y es creíble** donde el horario es el que se circula: 94 %
  de los tramos de servicio de agosto asignados, con margen amplio y un retraso
  mediano de +17 s.
- **La vigencia declarada del feed no basta para elegirlo.** Del 31/08 al 11/09
  hay unos 690.000 pasos etiquetados contra el horario de verano. Cada uno
  tiene aspecto de dato bueno. Los rechazos (margen, conflicto) son el síntoma
  visible; los asignados a un viaje equivocado, no.
- La persistencia a una parada deja un MAE de 36 s: para que el modelo aporte,
  tendrá que batirla. Es el baseline que hay que vigilar, no el horario.

## Qué se hizo / qué queda abierto

Hecho: `etiquetado.py`, `prepare.py`, los stages `curar` y `prepare`,
ADR-013, 014 y 015, y los mutantes 056-069. Trampa 012.

Abierto:

1. ~~**Qué horario usar del 31/08 al 11/09.**~~ **Cerrado el 22/09 para el
   31/08-07/09:** no existe. En el historial de Transitland no hay ninguna
   versión entre la del 02/09 (`d2d4cb8899ae`, la `01-09-2026` local: mismo
   sha1, servicio de verano) y la del 10/09 (calendario desde el 08/09). La EMT
   no publicó nada en medio. Esos días se excluyen de forma definitiva
   (ADR-014). Reproducir:
   `uv run python -m project.ingest.transitland --desde 2026-08-31 --hasta 2026-09-07`
   (salida en `auditoria/resultados/transitland_versiones_2026-09-22.txt`).
   **Sigue abierto el 08-11/09:** las versiones del 10 al 18/09 lo cubren con
   horario de septiembre, pero descargar zips archivados exige el plan de pago
   de Transitland (401 con la key gratuita). Hoy se etiqueta con el de verano.
2. Los 7.218 conflictos y los tramos cortos: cuántos son buses partidos por el
   tracker, que pierden la etiqueta de un tramo.
3. El sesgo declarado de la asignación: un bus que va más de medio intervalo
   fuera de horario se asigna al viaje contiguo, sin que nada lo delate.

## Para la memoria

> La etiqueta se construye reconstruyendo el paso de cada vehículo por cada
> parada, por interpolación sobre su avance a lo largo del recorrido, y
> asignando cada viaje observado al viaje programado cuyo horario de salida
> explica mejor el paso por las primeras paradas, con la exigencia de que el
> segundo candidato quede al menos dos minutos más lejos. Sobre 32 jornadas se
> obtuvieron 2,1 millones de pasos etiquetados, con un retraso mediano de 17
> segundos. En agosto se asignó el 94 % de los viajes observados en servicio.
> Entre el 31 de agosto y el 11 de septiembre la proporción cayó al 75 % y
> los viajes observados en conflicto se triplicaron: la versión del horario que
> declaraba vigencia para esos días no correspondía al servicio que circulaba.
> Etiquetar esos días con la versión posterior eleva la asignación al 84-88 % y
> reduce la dispersión del retraso, lo que muestra que la vigencia declarada por
> el editor no es un criterio suficiente para elegir el horario de referencia.
