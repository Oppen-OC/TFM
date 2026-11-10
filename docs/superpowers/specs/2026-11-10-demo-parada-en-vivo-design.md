# Demo en vivo por parada: diseño

_Diseño aprobado en conversación el 10/11/2026. Sin fecha de demo todavía._

## Para qué

Enseñar al tutor, en una reunión, que el modelo funciona con los datos de
**hoy**: elige una parada de la EMT, ve los buses que van hacia ella con la
probabilidad de que lleguen más de 5 min tarde y, cuando cada bus pasa, si se
cumplió. Es una demostración, no una evaluación: la cifra del TFM sigue siendo
la de la prueba del 07-19/10 (ADR-024, ADR-025). Nada de lo que se vea en la demo
entra en la memoria como resultado.

Hasta ahora el servido en tiempo real estaba fuera del alcance (06/11) y la API
solo acepta el vector de variables ya calculado (spec del 15/10). Esto añade lo
que faltaba en medio: construir ese vector en vivo.

## Lo que ve el tutor

Una página de Streamlit con:

1. **Selector de parada**, por nombre o código, entre las paradas del GTFS
   vigente hoy.
2. **Tabla de los buses que van hacia esa parada**, refrescada sola en cada
   ciclo. Una fila por viaje:

   | columna | qué es |
   |---|---|
   | Línea | `linea` |
   | A | paradas que faltan según el horario, `h` |
   | Va ahora | retraso en su último paso etiquetado, con su antigüedad |
   | Modelo | `P(> 5 min)` del clasificador del horizonte `h` y si supera τ |
   | Regla simple | persistencia: «ya va más de 5 min tarde ⇒ llegará tarde» |
   | Resultado | ⏳ esperando paso, o ✅/❌ con el retraso real en la parada |

   Un viaje a una distancia sin modelo (hoy, 4 y 6-9 paradas) sale en gris, sin
   predicción.
3. **Marcador de la sesión**: aciertos del modelo, aciertos de la regla y
   número de casos en que discrepan.
4. **Mensaje de error** cuando la API de la EMT falla o deja de dar datos
   nuevos. La tabla sigue con el último dato bueno.
5. **Desplegable «¿Cómo se calcula esto?»** con el texto del anexo.

Boceto aprobado: opción B con la columna de la regla
(`.superpowers/brainstorm/1380-1794315069/content/pantalla-parada-v2.html` y
`-v3.html`, fuera de git).

### Por qué la regla simple va al lado

El 8,06 % de los pasos de la prueba llega más de 5 min tarde
(`metrics/clasificador.json`, `titular.tasa_base`). Diciendo siempre «a tiempo»
se acierta el 92 %: un marcador sin listón no demuestra nada. Lo que convence
son las filas en que el modelo y la regla discrepan. Serán pocas: de los que aún
no van tarde, el 1,26 % acaba llegando tarde (`por_estado_actual.aún no`), y es
ahí donde el modelo gana claramente (PR-AUC 0,52 frente a 0,24). En 20 minutos
puede no salir ninguna. Se acepta: la demo no se maquilla.

## Decisiones

1. **Solo en vivo.** Sin modo de reproducción de días pasados. Si la API de la
   EMT da errores, se capturan y se muestran en un mensaje; no hay plan B.
2. **El clasificador sin la capa 192** (ADR-025), el que se sirve ya. No hace
   falta sondear el tráfico en vivo.
3. **Las mismas funciones del pipeline, sin reescribir ninguna variable.** El
   vector sale de `tracking.rastrear` → `etiquetado.etiquetar` →
   `features.instante_disponible` → `features.construir`, con los parámetros de
   `params.yaml`. Es el train/serve skew que `CLAUDE.md` prohíbe.
4. **El «ahora» de una fila es su `t_disp`** (ADR-022, trampa 017). Un viaje
   entra en la tabla con su último paso cuyo `t_disp` ya ha pasado. Ningún
   cálculo usa un paso con `t_disp` posterior al instante del ciclo.
5. **Horizonte.** Para un viaje cuyo último paso disponible es la parada `k` y
   la parada elegida está `h` posiciones más allá en su horario, se usa el
   clasificador de `h` si está cargado (`model_service.horizontes()`). Es la
   misma regla de parada objetivo que `features.construir`: por clave en el
   horario, no por pasos observados.
6. **Qué se verifica.** La primera predicción que se mostró en la sesión para
   un (viaje, parada) queda congelada, y es la que puntúa el marcador. La fila
   enseña además la actual. La verdad es `retraso_s > umbral_retraso_s` en la
   parada elegida, cuando ese paso queda etiquetado (≈ 81 s después de pasar,
   bitácora 046). La regla simple se congela en el mismo instante. _Decisión de
   Claude: congelar la primera evita que el marcador premie la predicción a una
   parada, que es la fácil para los dos._
7. **Arquitectura de siempre.** `ui/` → HTTP → `api/routers/` → `services/`.
   Endpoints nuevos en un router propio (`vivo.py`), incluido en `main.py`.
8. **Una carpeta propia para la demo, fuera de `data/`.** Guarda el historial
   reciente traído de la Pi, su etiquetado y la captura del día de la demo. El
   colector existente (`ingest.collect`) corre en el PC con `DATA_ROOT`
   apuntando a ella, y la API se lanza con el mismo `DATA_ROOT`. El corpus de
   `data/` se queda congelado en el 19/10 y DVC no se entera de la demo.
   Escribir en `data/raw/` mezclaría la captura del PC con el corpus de la Pi
   (trampa 016). _Decisión de Claude: la alternativa, ampliar el corpus, movía
   `curar.json` y `prepare.json`, que la bitácora cita._
9. **Arranque una hora antes.** El viaje programado se decide con las tres
   primeras paradas (`prepare.paradas_referencia`): un bus que salió antes de
   empezar a capturar no tiene horario y no aparece. Con una hora de captura,
   casi todos los viajes en curso empezaron dentro.
10. **Primero, medir.** La primera tarea del plan mide cuánto tarda un ciclo
    sobre un día real ya capturado, limitado a las líneas de una parada
    concurrida y a las horas de captura del día. Si cabe en 30 s, se refresca
    cada 30 s; si no, cada lo que tarde. La cifra se dice antes de construir
    nada más.

## Restricciones que el código ya impone

- **El colector se queda la primera captura de cada sondeo; `reprocesar`, la
  que más filas trae** (trampa 011). Leer el curated que escribe el colector en
  vivo vuelve a tener sondeos a medias. Las posiciones de la demo pasan por la
  misma elección que `reprocesar`. Hoy esa lógica vive dentro de
  `ingest.reprocesar.reprocesar` y escribe a disco; si se extrae a una función
  en memoria, `reprocesar` es dependencia del stage `curar`, así que se prueba
  la equivalencia byte a byte del curated y se hace `dvc commit`, no `dvc repro`.
- **`t_disp` necesita la hora de llegada de cada sondeo**, `min(ts_ingest_utc)`
  por `snapshot_id`, como en `features.main_disponibilidad`. El crudo la guarda.
- **El sesgo del tramo sale de días anteriores con la misma versión del GTFS**
  (`features._sesgo_tramo`, clave `CLAVE_TRAMO`). En noviembre la versión ya no
  es la de septiembre-octubre: sin pasos etiquetados de días recientes, la
  variable sale nula en todos los tramos. Antes de la demo hay que traer de la
  Pi la captura reciente a la carpeta de la demo y etiquetarla. Ver
  *Preparación*.
- **El GTFS del día** tiene que estar en `settings.gtfs_dir`; se elige con
  `gtfs.elegir_horario` (ADR-014). Lo captura la Pi (issue #6). `gtfs_dir` no
  se deriva de `data_root`: con la demo hay que darle `GTFS_DIR` aparte.
- **Las CLIs escriben métricas en el `metrics/` del repo** (`prepare` y
  `reprocesar`, por defecto). Con la carpeta de la demo, `--metricas` va dentro
  de ella; sobrescribir `metrics/prepare.json` o `metrics/curar.json` cambia
  cifras que DVC versiona.
- **La Pi y el colector del PC no escriben en los mismos ficheros**: el
  `rsync` de una sobre los de la otra deja días truncados sin error (trampa
  016). Lo de la Pi se trae antes de arrancar el colector, o a otra
  subcarpeta.
- **`ui/` no importa `services/` ni carga modelos. `api/` no lleva pandas ni
  sklearn.** El estado del marcador es lógica: vive en `services/`.
- **`ingest/` no importa de aguas abajo.** `services/` sí puede importar de
  `ingest/` (fuentes, parser, elección de sondeos).

## Preparación antes de la demo

1. Traer de la Pi a la carpeta de la demo los últimos días con la versión del
   GTFS vigente, con `deploy_pi/pull_data.sh` (`DESTINO=<demo>/raw`) y
   `--verificar`. Cuántos días hacen falta lo dice el soporte del sesgo del
   tramo (`features.soporte_min`); quien construye lo mide.
2. Etiquetarlos con las CLIs de siempre y `DATA_ROOT`/`GTFS_DIR` de la demo:
   `reprocesar`, `prepare` y `features --disponibilidad`. Sin DVC: no toca
   `data/`, `train.parquet`, `test.parquet` ni los modelos.
3. Arrancar el colector con la carpeta de la demo al menos una hora antes.
4. Arrancar la API (mismo `DATA_ROOT`) y la UI.

Todo esto queda escrito como guion en un README corto de la demo.

## Errores

- Payload de error de la EMT, timeout o red caída: mensaje en la UI con el
  error y la hora del último sondeo bueno; la tabla sigue con él.
- Un sondeo es un payload con filas (trampa 018): un `{"error": …}` no cuenta
  como dato nuevo.
- Sin datos nuevos durante más de un margen (a decidir), mensaje aunque no haya
  error explícito: el colector puede estar parado.
- Parada sin buses en camino: tabla vacía con un texto, no un error.

## Pruebas

- `tests/test_api.py`: los endpoints nuevos, con `services/` mockeado.
- El servicio en vivo, con datos sintéticos de instantes conocidos:
  - ningún cálculo ve un paso con `t_disp` posterior al ciclo (la guardia de
    la trampa 017 en vivo);
  - el horizonte se elige por posición en el horario y un `h` sin modelo no
    predice;
  - la primera predicción queda congelada y la verdad es la del paso en la
    parada elegida;
  - un payload de error no cuenta como sondeo nuevo.
- Cada guardia nueva lleva su mutante en `auditoria/catalogo.toml` (ADR-011);
  el siguiente número libre era el 214.
- Si se extrae la elección de sondeos de `reprocesar`: los tests de
  `tests/test_persistencia.py` siguen en verde y el curated sale idéntico.

## No-objetivos

- Reproducir días pasados como si fueran en vivo.
- Mapa.
- Capa 192 en vivo, Kafka o cualquier broker (ADR-016 se actualiza con esto).
- Guardar un histórico de predicciones o del marcador: vive en memoria y se
  pierde al reiniciar.
- SHAP en la tabla.
- Desplegarlo en la Pi o en un servidor: corre en el PC del autor.
- Usar lo que salga en la demo como resultado del TFM.

## Antiobjetivos

Sería un fracaso aunque funcione:

- un marcador sin la regla simple al lado;
- una variable calculada de otra forma que en el entrenamiento;
- la captura de la demo escrita en `data/raw/` o en `data/interim/` del corpus,
  o sus métricas en el `metrics/` del repo;
- tocar los modelos entrenados, las tablas de la prueba o `dvc.lock` de forma
  que cambie una cifra ya publicada.

## Lo que decide quien construye

- Cómo se recorta el cálculo para que quepa en el ciclo (solo las líneas de la
  parada, solo la jornada en curso, cachear lo que no cambia entre ciclos).
- Si el cálculo corre en un hilo de fondo del proceso de la API o bajo demanda
  con caché; el modelo se sigue cargando una vez al arrancar.
- La forma de los endpoints y de sus esquemas.
- El margen de «sin datos nuevos» y el refresco de la UI (`st.fragment` con
  `run_every`, Streamlit 1.59).
- Si el historial reciente se recalcula al arrancar la API o se lee ya hecho.

## Entrega

- Este diseño y su plan en `docs/superpowers/`.
- ADR-016 actualizado: la demo existe y no usa broker.
- `docs/00_tema_y_alcance.md`: el servido en tiempo real pasa a demo.
- README: cómo lanzar la demo.
- Bitácora si la medición del ciclo o la demo misma dan una cifra o una
  anomalía que valga la pena.
- Cierra o reescribe el issue #10, que pedía la UI sobre un paso de la prueba.

## Anexo: texto de «¿Cómo se calcula esto?»

Borrador aprobado; las cifras se comprueban contra el código antes de
publicarlas.

1. **Dónde está cada bus.** La EMT publica cada ~30 s la posición GPS de toda
   la flota, pero no dice qué bus es cuál: borra la tabla y la vuelve a llenar.
   La identidad se reconstruye emparejando cada posición con la del sondeo
   anterior que sea más cercana y físicamente posible (nada de saltos a más de
   70 km/h, `tracking.VEL_MAX_KMH`).
2. **Por dónde va en su ruta.** Cada posición se proyecta sobre el trazado de
   su línea, sacado del GTFS de la EMT, y se convierte en metros recorridos
   desde la cabecera.
3. **Qué horario sigue.** Con las tres primeras paradas del viaje se busca en
   el GTFS el viaje programado que mejor encaja con lo observado.
4. **Cuándo pasó por cada parada.** El bus casi nunca se ve justo en la parada:
   el instante de paso se interpola entre la última posición antes y la primera
   después.
5. **Si va tarde.** Retraso = hora real de paso − hora programada. Se conoce
   unos 80 s después del paso, cuando llega la posición siguiente y el viaje ya
   está asignado.
6. **La predicción.** El modelo parte del retraso que el bus lleva ahora y de
   cuánto suele ganar o perder en el tramo que le queda, y lo corrige con lo que
   han hecho en ese mismo tramo otros buses de su línea en los últimos 5-15 min.
   El resultado es la probabilidad de llegar a tu parada más de 5 min tarde.
