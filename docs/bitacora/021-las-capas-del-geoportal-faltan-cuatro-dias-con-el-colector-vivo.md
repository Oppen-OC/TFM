---
id: 021
titulo: Las cuatro capas del geoportal faltan 4 días y 7,7 h (10/09-14/09) con el colector vivo, y nada avisó
fecha: 2026-09-18
tipo: limitacion
capa: fuentes
capitulo: limitaciones
impacto: medio
estado: aceptado
evidencia: consulta de huecos de «Cómo se midió», sobre data/curated
trampa: —
---

## Qué se observó

Las cuatro capas ArcGIS del geoportal no tienen ninguna captura entre el 10/09
y el 14/09. Renfe, que se sirve desde otro dominio, no tiene hueco: su crudo
del 11/09 tiene 2.856 capturas de 2.880 posibles. En su curated sólo faltan las horas de
la noche, sin trenes, que dan payloads vacíos.

| fuente | última captura (UTC) | primera captura después (UTC) | hueco |
|---|---|---|---|
| `emt_buses` | 10/09 06:24:17 | 14/09 14:05:44 | 4 d 07:41 |
| `trafico_estado` | 10/09 06:21:36 | 14/09 14:05:44 | 4 d 07:44 |
| `trafico_intensidad` | 10/09 06:10:48 | 14/09 14:05:44 | 4 d 07:55 |
| `valenbisi` | 10/09 06:22:39 | 14/09 14:05:44 | 4 d 07:43 |

Tres hechos acotan lo que pasó:

- **Empezó con un único suceso sobre las 06:25 UTC del 10/09.** Cada capa falla
  en su siguiente sondeo tras la última captura: 30 s para la EMT, 5 min para
  estado y Valenbisi, 15 min para intensidad.
- **El colector estaba vivo.** Renfe es continua de 06:15 a 06:35 del 10/09 (el
  mayor salto entre capturas es de 30 s) y durante los días siguientes.
- **Terminó con un reinicio del colector, no con la vuelta de la fuente.** Las
  cuatro capas vuelven en el mismo segundo, las 14:05:44 del 14/09. Justo
  antes, Renfe tiene un salto de 7 min 54 s, el único entre las 13:55 y las
  14:10. Si el geoportal
  hubiera vuelto antes con el proceso sano, cada capa habría reanudado sola en
  como mucho 16 periodos (retroceso exponencial de `collect.sondear`, entre 8 min
  y 4 h), y lo habría hecho escalonada.

Tampoco hay crudo de las cuatro capas del 11, el 12 y el 13/09. El colector
guarda el crudo antes de parsear, también cuando ArcGIS responde con un error en
JSON. Por tanto, o ninguna petición obtuvo respuesta (error HTTP, tiempo de
espera, conexión), o las tareas dejaron de pedir.

Lo perdido de la EMT, estimado con la media de los días completos de septiembre:
unos **11.900 sondeos y 1,6 M de posiciones**. El hueco abarca de jueves a lunes,
con el fin de semana del 12 y el 13 entero.

## Cómo se midió

```python
import duckdb
duckdb.sql("set TimeZone = 'UTC'")
for s in ("emt_buses", "trafico_estado", "trafico_intensidad", "valenbisi",
          "renfe_cercanias"):
    print(s, duckdb.sql(f"""
        with t as (select distinct ts_ingest_utc t from read_parquet(
                   'data/curated/source={s}/*/*.parquet', hive_partitioning=false)),
             l as (select lag(t) over (order by t) desde, t hasta from t)
        select desde, hasta, hasta - desde as hueco from l
        order by hueco desc nulls last limit 3""").df())
```

Los saltos de Renfe en torno a los dos extremos salen con la misma consulta,
restringida a 10/09 06:15-06:35 y a 14/09 13:55-14:10. Que no hay crudo se ve
en los directorios: `data/raw/source=emt_buses/` salta de `date=2026-09-10` a
`date=2026-09-14`. La estimación de lo perdido sale de filas y sondeos por día
completo de septiembre (01-09 y 15-17), multiplicados por 103,7 h.

## Por qué importa

- **Es irrecuperable.** Ninguna fuente guarda histórico.
- **Parte en dos el periodo con GTFS válido** (24/08-30/09). El split temporal no
  puede tener el corte cerca del hueco sin que un lado quede mutilado. Las
  features con retardo, empezando por el baseline de persistencia, no pueden
  cruzarlo: el sondeo anterior al 14/09 14:05 es de hace cuatro días.
- **Afecta a la validación de septiembre del map-matching.** No se pueden usar
  solo "el 11, el 12 y el 13": **el 10 y el 14 también son parciales**. El 10/09
  sólo tiene hasta las 08:24 hora local y el 14/09, desde las 16:05. Con días
  parciales, el reparto horario de las métricas cambia.
- **Nada avisó durante cuatro días.** `collect --status` da `VIVO` con que haya
  latido, aunque cuatro de las cinco fuentes lleven días sin un sondeo bueno. El
  "último ok" por fuente se imprime, pero no cuenta para el diagnóstico de
  salud.
- Las dos caídas de agosto eran otra cosa: el 18/08, 14,7 h desde las 01:35
  UTC, y el 21/08, 10,6 h desde las 01:54. Afectan a las cinco fuentes, Renfe
  incluida, así que fue el colector el que cayó.

## Qué se hizo / qué queda abierto

Nada que recuperar: se acepta como limitación de la captura.

Abierto:

- **Causa.** O el geoportal estuvo caído hasta el minuto exacto del reinicio, o
  las tareas ArcGIS del colector dejaron de recuperarse dentro del proceso
  mientras la de Renfe seguía. El log de la Raspberry (si corre con `--log`) y
  el `ultimo_error` de su `_status.json` lo dirían. La copia local de
  `data/_status.json` es del 18/08 y no sirve.
- **Salud por fuente en `--status`.** Una fuente sin sondeo bueno en N periodos
  debería poner el diagnóstico en rojo. Abierto como issue #1.

## Para la memoria

> La captura presenta una interrupción de las cuatro capas del geoportal
> municipal —posiciones de la EMT, estado e intensidad del tráfico y
> Valenbisi— entre las 06:24 UTC del 10 de septiembre y las 14:05 UTC del 14 de
> septiembre: 103,7 horas, que incluyen un fin de semana completo. El colector
> siguió activo durante el intervalo, como muestra la captura de Renfe, servida
> desde otro dominio, y las cuatro capas volvieron al reiniciarlo. Se estiman perdidos unos
> 11.900 refrescos de la flota de la EMT (1,6 millones de posiciones), que no
> pueden recuperarse porque ninguna fuente conserva histórico. El intervalo se
> excluye de la validación. La partición temporal entre entrenamiento y
> prueba debe situarse de modo que ninguna ventana de variables retardadas lo
> atraviese.
