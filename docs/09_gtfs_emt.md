# 09 · GTFS estático de la EMT: qué hay dentro y para qué sirve cada fichero

_Descargado el 04/09/2026. Cifras medidas sobre el propio ZIP, no copiadas de la
especificación._

El GTFS (*General Transit Feed Specification*) es el formato estándar con el que
una operadora publica su **horario teórico**. Aquí es la pieza que faltaba para
tener variable objetivo: sin horario programado no existe la resta que define el
retraso.

- **Fichero:** `data/raw/gtfs/emt_google_transit.zip` — 7.161.519 B, md5
  `a87aa72b12b2fa9c3d63bee454f8e759`, fijado en
  `data/raw/gtfs/emt_google_transit.zip.dvc`.
- **Origen:** [Plataforma VLCi, dataset *Google Transit*](https://opendata.vlci.valencia.es/dataset/google-transit-lines-stops-bus-schedules), CC BY 4.0.
- **Ruta esperada por el código:** `config.gtfs_zip` y `params.yaml → prepare.gtfs_zip`.
- **Versión del feed:** `01-09-2026`. Vigencia declarada 24/08/2026 – 30/09/2026.

Codificación UTF-8 en los nueve ficheros. `agency_timezone = Europe/Madrid`.

## Los nueve ficheros

| fichero | filas | qué contiene |
|---|---:|---|
| `agency.txt` | 1 | La operadora. Un solo registro: `EMT Valencia`, zona horaria `Europe/Madrid`. Es de donde sale la convención horaria contra la que hay que normalizar las posiciones capturadas. |
| `feed_info.txt` | 1 | Metadatos de esta publicación: editor, versión (`01-09-2026`) y ventana de vigencia (`feed_start_date` 20260824, `feed_end_date` 20260930). |
| `routes.txt` | 47 | Las **líneas**. `route_id` interno (`1017`), `route_short_name` visible (`4`, `C3`), `route_long_name` con cabeceras, color de línea. `route_type = 3` (autobús) en todas. |
| `trips.txt` | 33.843 | Los **viajes**: cada pasada concreta de un autobús. Campos: `route_id`, `service_id`, `trip_id`, `trip_headsign`, `trip_short_name`, `shape_id`. Es la unidad a la que hay que asignar cada trayectoria observada. |
| `stops.txt` | 1.160 | Las **paradas** con `stop_lat`/`stop_lon`, nombre, código visible y accesibilidad. Sirven para detectar el paso del autobús. |
| `stop_times.txt` | 845.736 | **El horario.** Por cada `trip_id` y cada parada: `arrival_time`, `departure_time`, `stop_sequence` y `shape_dist_traveled`. Es el término programado del retraso: el fichero grande (56 MB) y el que importa. |
| `shapes.txt` | 26.478 | Las **polilíneas** de los recorridos: 95 trazados distintos, mediana de 244 puntos cada uno. Sobre esto se proyecta la posición GPS para obtener el avance a lo largo de la ruta. La geometría es buena; su columna `shape_dist_traveled`, no (punto 1 de «Seis cosas que muerden»). |
| `calendar.txt` | 281 | Qué **días de la semana** circula cada `service_id`, y entre qué fechas. Todos los servicios declaran 20260815 – 20260930. |
| `calendar_dates.txt` | 564 | **Excepciones** al calendario: 282 supresiones (`exception_type = 2`) y 282 altas (`1`), todas entre 20260724 y 20260815. Festivos y cambio de servicio de verano. |

Relación entre ellos: `routes` → `trips` → `stop_times`, y `trips` apunta además a
un `shape_id` y a un `service_id`. Un `trip` es una pasada concreta (el 70 que
sale de Alboraia a las 08:14), no la línea entera.

## Papel de cada uno en la etiqueta de retraso

```
retraso(parada) = t_paso_observado − t_llegada_programada
                        │                     │
    shapes + stops ─────┘                     └───── stop_times (+ trips, calendar)
```

1. `shapes.txt` convierte cada posición GPS en un escalar monótono: metros
   recorridos desde cabecera.
2. `stops.txt` da la posición de cada parada, que se proyecta sobre ese mismo
   trazado para obtener su abscisa; el cruce se interpola entre las dos
   posiciones que la encierran.
3. `calendar` + `calendar_dates` dicen qué viajes existían ese día concreto.
4. `stop_times.arrival_time` del viaje asignado da el término programado.

**La abscisa se recalcula; el campo del feed no vale.** Ver el punto 1 de abajo.
La proyección es fiable: sobre la línea 31, las 34 paradas del sentido caen a
mediana 3,4 m del trazado (máximo 15,1 m) y las posiciones reales de un vehículo
a mediana 1,8 m. Medido en
[notebooks/EDA/06_cascada_etiqueta_retraso.ipynb](../notebooks/EDA/06_cascada_etiqueta_retraso.ipynb).

## Seis cosas que muerden

**1. `shape_dist_traveled` no es distancia: es el horario reescalado.** Viene
poblado en el 100 % de las 845.736 filas de `stop_times.txt`, y parece regalar el
trabajo geométrico hecho. No lo regala: dentro de cada viaje es una función lineal
**exacta** del tiempo programado — $R^2 = 1{,}00000$ en los 300 viajes de la
muestra, con una constante propia por viaje (6,7–20,5 unidades/s). Contra la
geometría que lo acompaña no cuadra en ninguno de los 95 trazados: el cociente
entre lo declarado y la longitud real de la polilínea va de 1,65 a 4,25.

Usarlo como eje para interpolar el paso por parada mediría el horario contra sí
mismo: el retraso saldría estructuralmente pegado a cero, sin excepción, sin aviso
y sin nada raro en las gráficas. Es el patrón de la trampa 004. **La abscisa se
recalcula proyectando sobre `shapes.txt`**, cuya geometría sí es correcta.

**2. `trips.txt` no trae `direction_id`.** El sentido hay que deducirlo del
`shape_id` (95 trazados para 47 líneas, ≈2 por línea) o del `trip_headsign`, y
casarlo con el campo `trayecto` de la capa de la EMT. Ortografías e idiomas
distintos: `Plaça de l'Ajuntament - Ateneu` frente a `Alboraia - La Fontsanta`.
Emparejamiento por texto, no por clave.

**3. `route_short_name` no es única.** `73`, `C2` y `C3` aparecen dos veces con
`route_id` distinto. Como la capa en vivo solo publica `linea`, esas tres son
ambiguas de entrada y hay que desempatarlas por trazado.

**4. Horas de servicio mayores que 24.** 32.785 filas de `stop_times.txt` las
tienen, con máximo `28:03:00`. Es legal en GTFS: significa 04:03 del día
siguiente, dentro del mismo día de servicio. Hay que parsear a segundos desde la
medianoche de servicio, no con `pd.to_datetime`.

**5. `timepoint = 0` en las 845.736 filas.** La EMT declara **todos** sus horarios
como aproximados, ninguno como punto de control exacto. La referencia contra la
que medimos el retraso está marcada por el propio editor como interpolada. No
invalida la etiqueta, pero es una limitación que hay que declarar antes de que la
pregunte el tribunal.

**6. La vigencia no cubre la captura entera.** `feed_start_date` es 20260824 y la
captura empieza el 15/08: **9 de los 17 días** capturados caen antes de la ventana
declarada, aunque `calendar.txt` afirme validez desde el 15/08. El paso de
servicio de verano a servicio de septiembre cae justo ahí. Etiquetar esos días con
este feed es un supuesto, no un hecho. Hay más de cien versiones archivadas en
[Transitland](https://www.transit.land/feeds/f-ezp8-emtvalencia) para contrastar
cuál estaba viva el 15/08.

## Cobertura frente a lo capturado

Contra 5.303.729 posiciones de autobús de 17 días (15/08 – 31/08/2026):

- **42 líneas** distintas capturadas.
- **3 sin ruta en el GTFS** — `100`, `96`, `98E` — con 49.052 posiciones, el
  **0,92 %**. No son etiquetables y caen del dataset.
- **5 rutas del GTFS nunca vistas** — `59`, `60`, `73`, `9`, `C1` — coherente con
  el servicio reducido de agosto.

## Reproducir la descarga

```bash
curl -sSL -o data/raw/gtfs/emt_google_transit.zip \
  "https://opendata.vlci.valencia.es/dataset/ab058cf8-ad3e-4d9c-ac89-0c6367ecf351/resource/c81b69e6-c082-44dc-acc6-66fc417b4e66/download/google_transit2026-09-02.zip"
uv run dvc add data/raw/gtfs/emt_google_transit.zip
```

La URL lleva la fecha de publicación dentro, así que cambia en cada versión del
feed: si devuelve 404, hay que volver al dataset de VLCi a por la nueva. Por eso
el md5 queda fijado en el `.dvc` — un feed que cambia sin avisar cambia todas las
etiquetas en silencio.

## Versiones del feed

El feed tampoco guarda histórico: cada publicación sustituye a la anterior en la
misma ficha de VLCi. Cada versión que se descarga se conserva bajo DVC y no se
sobrescribe.

| versión | vigencia (`feed_info`) | `calendar` | fichero | md5 |
|---|---|---|---|---|
| `01-09-2026` | 24/08 – 30/09 | 15/08 – 30/09 | `data/raw/gtfs/emt_google_transit.zip` | `a87aa72b…` |
| `19-09-2026` | 12/09 – 19/10 | 12/09 – 19/10 | `data/raw/gtfs/versiones/google_transit2026-09-18.zip` | `5ca9c99d…` |

La segunda se descargó el 21/09 (el recurso de VLCi se modificó el 20/09). Frente
a la primera:

- **La línea 63 (Campus de Burjassot - Estació del Nord) tiene 92 viajes.** En la
  primera tenía la ruta y cero viajes, aunque circula desde el 31/08: entre el
  31/08 y el 11/09 no hay horario con el que etiquetarla.
- **Cambian de trazado o de ruta la 18, la 24, la 64, la 92 y la 95.** La 92 cambia
  de cabecera, de 1162↔1272 a 1272↔1546. La 62 y la 98 ganan variantes, y la C3
  mueve entre un 9 y un 11 % de su geometría.
- 50 rutas, 36.964 viajes y 100 trazados, frente a 47, 33.843 y 94.
- 96, 98E y 100 siguen sin ruta.

Del 12 al 30/09 **las dos versiones son vigentes a la vez**. El etiquetado tiene
que elegir el feed por fecha de servicio, no cargar uno fijo.

```bash
curl -sSL -o data/raw/gtfs/versiones/google_transit2026-09-18.zip \
  "https://opendata.vlci.valencia.es/dataset/ab058cf8-ad3e-4d9c-ac89-0c6367ecf351/resource/c81b69e6-c082-44dc-acc6-66fc417b4e66/download/google_transit2026-09-18.zip"
uv run dvc add data/raw/gtfs/versiones/google_transit2026-09-18.zip
```

La publicación vigente se consulta con la API CKAN de VLCi:
`https://opendata.vlci.valencia.es/api/3/action/package_show?id=google-transit-lines-stops-bus-schedules`.

### Versiones archivadas en Transitland

Transitland (`f-ezp8-emtvalencia`) registra una versión cada vez que el zip
cambia, así que su historial es el registro de lo que la EMT publicó y cuándo.
Los metadatos se leen con la API key gratuita; **el zip no**: la descarga exige
plan professional o enterprise y que la licencia del feed permita redistribuirlo
(la del feed de la EMT sale `null`), y con la key gratuita devuelve 401
(22/09). Las que rodean la captura, contrastadas por sha1 contra los zips
locales:

```bash
uv run python -m project.ingest.transitland --desde 2026-08-31 --hasta 2026-09-07
```

Salida completa en `auditoria/resultados/transitland_versiones_2026-09-22.txt`.

| descargada | sha1 | calendario | `feed_version` |
|---|---|---|---|
| 01/08 | `f6c77d81478a` | 24/07 – 30/08 | — |
| 02/09 | `d2d4cb8899ae` | 24/07 – 30/09 | (la `01-09-2026` de este repo) |
| 10/09 | `c58040a67325` | 08/09 – 09/10 | — |
| 11/09 | `ae0e01c6f907` | 08/09 – 10/10 | — |
| 13/09 | `7ee6a4935247` | 08/09 – 11/10 | — |
| 15/09 | `4ace8676b3b8` | 08/09 – 14/10 | `14-09-2026` |
| 16/09 | `1cc90a40ec7f` | 08/09 – 15/10 | `15-09-2026` |
| 17/09 | `4040b443bbaa` | 09/09 – 16/10 | `16-09-2026` |
| 18/09 | `058434992a85` | 08/09 – 17/10 | `17-09-2026` |
| 21/09 | `565b839146c0` | 12/09 – 19/10 | `19-09-2026` (la de este repo) |

**El servicio de septiembre aparece publicado con calendario desde el 08/09**, y
no hay ninguna versión archivada con horario de septiembre para el 31/08-07/09,
aunque lo observado esos días encaja mejor con él (bitácora 024). **Entre el 02/09
y el 10/09 la EMT no publicó nada**: no hay versión intermedia, y Transitland la
habría registrado. El único horario publicado para el 31/08-07/09 es la
`01-09-2026` (`d2d4cb8899ae`, sha1 idéntico al zip local), con servicio de verano.
Ningún otro archivo puede tener lo que el editor nunca publicó, así que esos
días quedan excluidos de forma definitiva (ADR-014).

Las versiones del 10 al 18/09 sí servirían para el **08-11/09**, que hoy se
etiqueta con la `01-09-2026` porque la `19-09-2026` empieza el 12/09. No son
descargables con la key gratuita.

**Después del 19/09 la EMT publicó una versión casi cada día** (14 hasta el
06/10), con el calendario corriendo: empieza unos 8 días antes de la captura y
acaba unas 4 semanas después. La del 06/10 (`21a5e04c727f`, `05-10-2026`,
vigente 28/09-04/11) se descargó de VLCi y está en `data/raw/gtfs_archivo/`,
**fuera de `gtfs_dir`** para que la etiqueta no la use: quita la línea 13 y
prolonga el horario excepcional de la 35 (bitácora 042, ADR-014). Para
contrastar otra versión con lo etiquetado:

```bash
uv run python -m project.analysis.comparar_gtfs data/raw/gtfs_archivo/google_transit2026-10-04.zip
```
