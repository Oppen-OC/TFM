---
id: 061
titulo: El silencio legítimo más largo entre dos sondeos buenos va de 10 min (Valenbisi) a casi 6 h (Renfe de madrugada), y el GTFS pasa hasta 32 días sin versión nueva; con las tolerancias que salen de ahí, `collect --status` habría dado 2 falsas alarmas en 66 días y 46 avisos de huecos reales
fecha: 2026-10-23
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: medio
estado: resuelto
evidencia: uv run python -m project.analysis.medir_silencios --data C:/Users/oppen/Code/TFM/data (sobre el crudo y el curated del 15/08 al 20/10); para el GTFS, el código de «Cómo se midió» sobre auditoria/resultados/transitland_versiones_2026-09-22.txt
trampa: —
---

## Qué se observó

Cada hueco entre dos sondeos buenos, los que mueven el `ultimo_ok` del colector,
se clasifica con el crudo que cae dentro:
- **colector:** el proceso estaba parado; el resto de fuentes tampoco guarda nada.
- **error:** la fuente devuelve `{"error": …}` o deja de contestar. Aquí entran
  también las excepciones del parser, que disparan el retroceso.
- **legítimo:** la fuente contesta a su cadencia, pero sin filas o con el mismo
  sondeo.

| fuente | cada | legítimo más largo | lo recurrente | un fallo aislado¹ | tolerancia | legítimos que avisan | huecos reales que avisan² |
|---|---|---|---|---|---|---|---|
| `emt_buses` | 30 s | 38,3 min, una vez (10/09 07:16) | 17,2 min cada día hacia las 05 h | 2,1 min | 30 min | 1 | 5 |
| `trafico_estado` | 5 min | — (la clave no se repite) | — | 15,3 min | 30 min | 0 | 12 |
| `trafico_intensidad` | 15 min | — | — | 45,3 min | 60 min | 0 | 8 |
| `valenbisi` | 5 min | 140,2 min, una vez (29/09 00:53) | 10,0 min | 15,3 min | 30 min | 1 | 12 |
| `renfe_cercanias` | 30 s | 358,7 min (26/08 23:50 → 05:48) | cada noche sin trenes del núcleo 40 | 1,8 min | 30 min de día, 8 h de 0 a 7 h | 0 | 9 |
| `gtfs_emt` | 6 h | 32 días (01/08 → 02/09) | casi una versión al día | — | no se juzga | — | — |

¹ Mediana de los huecos con error: un sondeo fallido más su retroceso, 3 periodos
en el tráfico y en Valenbisi.
² Huecos de error o de colector parado.

Horas en hora local.

- **Renfe de madrugada.** Hay 25 noches limpias. Su silencio empieza de 23:44 a
  00:00 y acaba de 04:31 a 05:48. De día, lo legítimo más largo son 20,3 min
  (01/10, 22:47 → 23:08). Por eso la tolerancia depende de la hora: 30 min a
  cualquier hora avisaría cada noche, y 8 h a cualquier hora habría tapado las
  6,1 h sin crudo de Renfe del 28/08, de 06:35 a 12:42.
- **Las dos falsas alarmas son la fuente congelada, no ruido.**
  - La EMT contestó sin un sondeo nuevo 38 min, de 07:16 a 07:55 del 10/09. A
    las 08:24 empezó la caída de 103,7 h de la 021.
  - Valenbisi hizo lo mismo de 00:53 a 03:13 del 29/09.
- **El instrumento reproduce las cifras ya fichadas:**
  - 6.221,5 min de la EMT el 10-14/09 (021), clase error, con Renfe viva;
  - 2.276,8 min del fallo del disco (054), clase colector;
  - 385 y 821 min de la 192 el 22 y 23/09 (060);
  - 225,8 min de la EMT el 13/10 (trampa 018).
- **Renfe también calla de día.** El 26/09, de 02:00 a 15:00, sirvió 1.060
  payloads sin un tren del núcleo 40, con el primero de vuelta a las 15:03.
  Entre ellos van 33 `KeyError: codEstDest` del parser (#4), y cada uno espacia
  el crudo siguiente hasta 480 s (#5).

## Cómo se midió

```bash
$env:PYTHONUTF8 = "1"   # PowerShell; la consola rompe los acentos (#3)
uv run python -m project.analysis.medir_silencios --data C:/Users/oppen/Code/TFM/data
```

`medir_silencios`:
- toma los sondeos buenos del curated, que `reprocesar` reconstruye con el
  mismo `parse` y la misma `clave_sondeo` que el colector. De un sondeo
  repetido se queda la captura más completa y no la primera, lo que mueve un
  instante como mucho un periodo;
- del crudo lee solo el instante y si el payload empieza por `{"error"`;
- descarta los huecos de menos de 1,5 periodos y 30 s;
- llama «colector» al hueco en que las demás fuentes callan más de 5 min y de
  la mitad del hueco;
- `avisa` aplica `Source.silencio_tolerado` hora a hora local, como
  `collect --status`.

La versión anterior del instrumento, con 5 min a secas, daba por parado el
colector del 10-14/09 con que Renfe pausara 5 min en algún momento de esos
cuatro días. La primera
hipótesis ante una cifra rara es el medidor (trampa 004).

El GTFS no tiene captura propia en el corpus: la Pi nunca corrió
`capturar_gtfs` (051). Su cadencia sale del listado de Transitland:

```python
import pandas as pd
d = pd.read_csv("auditoria/resultados/transitland_versiones_2026-09-22.txt",
                sep=r"\s+", header=None, usecols=[1])
f = pd.to_datetime(d[1]).drop_duplicates().sort_values()
print(len(f), f.diff().dt.days.nlargest(4).tolist())  # 99 [32.0, 26.0, 23.0, 20.0]
```

## Por qué importa

- **Una tolerancia de N periodos no sirve.** La noche de Renfe son 717 periodos
  y el silencio diario de la EMT, 34. Con 10 periodos, `--status` habría avisado
  cada noche por Renfe, cada madrugada por la EMT y en cada fallo aislado del
  tráfico.
- **Con estas tolerancias, dos falsas alarmas en 66 días**, y las dos señalan
  una fuente de verdad congelada. Los 46 huecos reales que pasan de la
  tolerancia, contados por fuente, habrían avisado; el de la 021 cuenta cuatro
  veces. Se habría visto a los 30 min, no a las 103,7 h.
- **El GTFS no admite tolerancia sobre su `ultimo_ok`:** 32 días es legítimo.
  Necesita otra señal (#6).
- **Medido en horario de verano y con los horarios de agosto a octubre.** La
  ventana de Renfe es la de su horario de servicio. Si cambia, o con el horario
  de invierno desde el 25/10, se repite la medida.

## Qué se hizo / qué queda abierto

Hecho:
- Las tolerancias van en `Source.silencio_max_s` y `silencio_madrugada_s`
  (`src/project/ingest/sources.py`).
- `collect --status` sale con 3 cuando el latido está vivo y alguna fuente pasa
  de su tolerancia.
- Guardias en `tests/test_persistencia.py`, mutantes 187-194 (issue #1).
- Queda resuelto el punto abierto de la 021, salud por fuente en `--status`.

Abierto:
- Señal de vida del GTFS (#6).
- El retroceso trata un fallo del parser como una fuente caída (#5).
- La tolerancia mira la hora de ahora y no las que cubre el silencio: una
  caída de Renfe que empieza de tarde sale VIVO de madrugada. Anotado como
  `ponytail:` en `Source.silencio_tolerado`.
- Repetir la medida con el horario de invierno.

## Para la memoria

> Para detectar a tiempo una fuente que deja de entregar datos se midió, sobre
> los 66 días de captura, cuánto puede pasar cada fuente sin un refresco nuevo
> estando operativa. Cada intervalo entre dos refrescos útiles se clasificó con
> los datos crudos: equipo de captura detenido, fuente con error o sin
> respuesta, o fuente que responde sin novedad. En este último caso, el
> silencio más largo fue de 10 minutos para el servicio de bicicletas, de 17
> minutos para la flota de autobuses, que repite cada madrugada el mismo
> refresco hacia las cinco, y de casi seis horas para Cercanías, que deja de
> publicar trenes de València cada noche, nunca antes de las 23:44, y vuelve
> a hacerlo como tarde a las 05:48. Las capas de tráfico no
> repiten refresco, y un fallo aislado con su reintento las deja 15 y 45
> minutos sin dato. El horario programado llegó a pasar 32 días sin una
> versión nueva. Un umbral proporcional a la cadencia de sondeo habría dado
> falsas alarmas cada noche. Con tolerancias de 30 minutos, 60 para la capa de
> intensidad y 8 horas de madrugada para Cercanías, el diagnóstico habría
> señalado 46 interrupciones reales, contadas por fuente, y solo dos falsas
> alarmas, ambas de una fuente congelada. La interrupción de 103,7 horas de
> septiembre se habría detectado a los 30 minutos.
