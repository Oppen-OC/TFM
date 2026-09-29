# 07 · Decisiones cerradas

Registro canónico de las decisiones estructurales del TFM. Una entrada por
decisión, con su porqué, las consecuencias que arrastra y qué la reabriría.

**Este fichero es la fuente de verdad de las decisiones.** No dupliques la tabla en
`CLAUDE.md` ni en `docs/00`: apuntan aquí. Si el código contradice a una entrada,
gana el código y la entrada se marca obsoleta.

**Estados.** `cerrada` — se da por buena y no se rediscute sin motivo nuevo.
`revisable` — tomada, pero con condición explícita de reapertura.

Cuando una decisión se cierra en un `/grill-me`, su entrada se escribe aquí.

---

## ADR-001 · DVC como orquestador · cerrada

**Decisión.** El pipeline lo gobierna DVC. Cada etapa (prepare → features → train
→ evaluate) es un stage declarado en `dvc.yaml` con sus `deps`, `params` y `outs`.

**Por qué.** Ya estaba en el esqueleto del trabajo y es suficiente para cuatro
stages. Da reproducibilidad y caché de resultados sin infraestructura.

**Consecuencias.** Un script de entrenamiento sin stage en `dvc.yaml` es un error,
no una excepción. Los hiperparámetros van en `params.yaml` bajo la clave del
stage; hasta 08/2026 el bloque `stages:` vivía en `params.yaml` y `dvc repro` no
ejecutaba nada.

**Alternativas.** Airflow o Prefect: sin evaluación registrada. Serían
desproporcionados para cuatro stages en un portátil, pero el argumento no está
documentado más allá de esto.

**Qué la reabriría.** Que el pipeline pase de ~6 stages o necesite ejecución
programada.

---

## ADR-002 · La ingesta queda fuera de DVC · cerrada

**Decisión.** El colector corre como proceso aparte. El pipeline reproducible
empieza en `data/raw/`.

**Por qué.** Capturar un stream en vivo no es idempotente ni reejecutable, que es
justo lo que DVC asume de cada stage. Un `dvc repro` no puede volver a capturar el
martes pasado.

**Consecuencias.** La captura no está versionada como stage y su calidad se vigila
aparte (`src/project/analysis/diagnose.py`). A cambio, **el colector guarda siempre el payload
crudo antes de parsear**, lo que permitió arreglar la trampa 002 sin recapturar
nada. Capturar es irreversible; procesar es reintentable.

**Qué la reabriría.** Nada previsible. Es la decisión que más se ha pagado sola.

---

## ADR-003 · Parquet + zstd como formato intermedio · cerrada

**Decisión.** Parquet comprimido con zstd en `data/interim/` y `data/processed/`.
Nunca CSV.

**Por qué.** El volumen proyectado son ~145 M de filas en tres meses. Medido sobre
la primera captura: 76,7 MB en 12,5 h, ~147 MB/día, ~13 GB en 90 días. En CSV es
inmanejable sobre un portátil.

**Consecuencias.** Lectura con proyección de columnas y predicate pushdown. El
particionado por fecha aún está por decidir (ver ADR-004).

**Alternativas.** CSV descartado por volumen. Formatos de tabla (Delta, Iceberg):
sin evaluación registrada.

---

## ADR-004 · DuckDB / Polars como motor analítico · cerrada

**Decisión.** DuckDB y Polars sobre el portátil. Sin cluster.

**Por qué.** El volumen es grande para pandas en memoria pero pequeño para Spark.
DuckDB lee Parquet particionado sin cargarlo entero.

**Consecuencias.** `rastrear()` recorre snapshots en Python y está identificado
como cuello de botella: con 12,5 h va sobrado, con 3 meses habrá que vectorizarlo
o pasarlo a DuckDB (`docs/05`, sección 7).

**Pendiente.** El criterio de reparto entre DuckDB y Polars no está fijado.

---

## ADR-005 · XGBoost como modelo · cerrada

**Decisión.** XGBoost, regresión.

**Por qué.** Restricción del trabajo. Además es el modelo adecuado para datos
tabulares con features heterogéneas.

**Consecuencias.** Deep learning sobre secuencias queda como trabajo futuro,
declarado fuera de alcance. La interpretabilidad viene por SHAP.

**Qué la reabriría.** Nada: es restricción impuesta, no elección.

---

## ADR-006 · Objetivo: segundos de retraso, más variante binaria · cerrada

**Decisión.** Regresión sobre `retraso_siguiente_parada_s`. Variante de
clasificación con umbral `features.umbral_retraso_s` (300 s) para el endpoint de
la API.

**Por qué.** La regresión es la pregunta de investigación; la binaria es lo que un
usuario final consume ("¿llego tarde o no?").

**Consecuencias.** Dos conjuntos de métricas. La binaria se reporta siempre junto
a la tasa base de la clase positiva: sin ella, un F1 no se puede leer.

---

## ADR-007 · Split temporal, nunca aleatorio · cerrada

**Decisión.** El corte train/test es por fecha (`features.test_desde`).

**Por qué.** Con series de posiciones, un split aleatorio mete futuro en el
entrenamiento y produce métricas infladas.

**Consecuencias.** El test es un bloque temporal contiguo, así que hereda lo que
haya pasado esos días (obras, festivos, meteorología). Hay que declararlo como
limitación en la memoria.

**Por qué está aquí.** Es el primer error que busca un tribunal en un trabajo de
series temporales. La decisión no se rediscute: se defiende.

---

## ADR-008 · Metrovalencia descartado como dato observado · cerrada

**Decisión.** Fuera del alcance.

**Por qué.** No publica tiempo real.

**Consecuencias.** El estudio cubre autobús urbano (EMT) y cercanías (Renfe). No
es multimodal completo, y así debe describirse.

---

## ADR-009 · `demo/` aislado de `src/project/` · cerrada por consumación (31/08/2026)

**Decisión original.** El prototipo de exploración vivía en `demo/` y no importaba
nada de `project`, ni al revés.

**Por qué.** Permitió validar que las fuentes siguen vivas y capturar mientras el
pipeline se construía, sin arrastrar el prototipo a la arquitectura definitiva.

**Cómo se cerró.** Por consumación, que es exactamente lo que esta ficha decía que
la cerraría. `demo/` se portó entero y desapareció:

| origen (ya no existe) | destino |
|---|---|
| demo/sources.py | `src/project/ingest/sources.py` |
| demo/collect.py | `src/project/ingest/collect.py` |
| demo/reprocesar.py, demo/explore.py | `src/project/ingest/` |
| demo/track.py | `src/project/tracking.py` |
| demo/diagnose.py | `src/project/analysis/diagnose.py` |
| demo/selftest.py | `tests/test_ingest.py` + `tests/test_tracking.py` |

**Consecuencias.** Los 30 checks del arnés casero pasaron a pytest sin cambiar un
solo umbral, y se verificó que el recuento coincide. Las fichas 001-004
dejan de citar `demo/selftest.py::"<check>"` y citan node ids; el validador
`.claude/tests/test_trampas.py` ya solo admite ese formato. Con el porte apareció
`config.py`, que hasta entonces tenía 0 líneas: las rutas dejan de estar
hardcodeadas y `DATA_ROOT` es lo único que hay que cambiar para que el colector
escriba en `/srv/tfm-data` en vez de en `data/`.

**Lo que no cambió.** La ingesta sigue fuera del grafo de DVC (ADR-003), y
`analysis/` tampoco entra: `diagnose.py` no produce entradas de `train`.

**Deuda que deja.** La Raspberry sigue ejecutando su copia de `/opt/tfm/demo/` y
no se tocó para no interrumpir la captura — no hay histórico recuperable. El
redespliegue a `-m project.ingest.collect` está documentado en `deploy_pi/` y
pendiente de una ventana controlada.

---

## ADR-010 · Renfe Cercanías capturado desde el día 1 · cerrada

**Decisión.** El colector captura EMT y Renfe núcleo 40 desde el primer día,
aunque Renfe no sea el objeto del trabajo.

**Por qué.** Es el plan B. El riesgo principal del TFM es que el map-matching de
la EMT consuma todo el tiempo disponible. Renfe trae `retrasoMin` ya calculado y
`tripId` estable: hay dataset etiquetado y modelo entrenable en dos semanas.
Capturar las dos cuesta lo mismo, y **no hay histórico recuperable**: si en
diciembre hiciera falta pivotar y no se hubiera capturado, no habría plan B.

**Consecuencias.** Renfe funciona además como validación cruzada entre modos, que
es aportación aunque el plan A salga bien.

**Condición de activación.** Si en diciembre de 2026 el etiquetado de la EMT no
está resuelto, se pivota.

---

## ADR-011 · Los tests se validan por mutación dirigida y la simulación contra la captura real · cerrada

**Decisión.** Que la suite esté en verde no se acepta como evidencia de que
guarda algo. La validez de los tests se mide con un catálogo de mutantes
dirigidos (`auditoria/catalogo.toml`), cada uno atado a una trampa, un invariante
documentado o una función sin cubrir, y ejecutado sobre un worktree desechable
por `auditoria/mutar.py`. Los supuestos de la flota simulada se contrastan con la
captura real usando el mismo instrumento en ambos lados
(`src/project/analysis/auditar_supuestos.py`), y un supuesto solo se da por
bueno si inyectar el fenómeno real no cambia el resultado del tracker
(`auditoria/escenarios.py`).

**Por qué.** El tracker se ajustó contra la misma simulación con la que se
prueba: validarlo solo ahí es circular. Y una ficha `cerrada` afirma que un test
impide recaer, afirmación que nadie comprobaba. La primera ejecución
([docs/11](11_auditoria_tests.md)) encontró tres guardias que no guardaban y una
simulación que nunca para, frente al 29 % real.

**Consecuencias.**

- Un mutante sin detectar solo cuenta como hueco si una sonda determinista ve
  salida distinta; si no, es equivalente. Sin esa distinción la auditoría se
  inventa huecos.
- El runner se detiene si falla un control: suite de referencia no verde,
  `import project` fuera del worktree, mutante nulo no equivalente o control
  positivo no detectado.
- Se audita un commit, nunca el árbol de trabajo: el runner exige `src/` y
  `tests/` sin cambios con seguimiento.
- Fuera de CI: tarda unos 40 minutos. Se ejecuta a mano antes de cerrar un
  capítulo, tras tocar `tracking.py` y **tras actualizar dependencias** (la
  guardia de la trampa 004 caducó con numpy).
- Una guardia nueva no se da por buena hasta que detecta su mutante del catálogo.

**Alternativas.** `mutmut` automático: no funciona bien en Windows nativo y
genera miles de mutantes sintácticos que ahogan la señal. Revisión por lectura:
opina sobre la validez en vez de medirla.

**Reabrir si** el catálogo deja de encontrar huecos en dos ejecuciones
consecutivas con código nuevo, o si la CI pasa a correr en una plataforma donde
el coste de 40 minutos sea asumible.

---

## ADR-012 · El tracker recibe la abscisa; no calcula el map-matching · cerrada

> **Revisada por ADR-013 (21/09):** las dos pasadas de `prepare.py` se
> sustituyen por una. Lo demás sigue en pie.

**Decisión.** `rastrear()` acepta una columna `abscisa_m` opcional y, donde la
hay, empareja sobre el recorrido. Quien llama —`prepare.py`— hace dos pasadas:
rastrear para tener identidad aproximada, `mapmatching.emparejar` para la
abscisa, y rastrear otra vez con ella. `tracking.py` no importa `gtfs.py` ni
`mapmatching.py`.

**Por qué.** La dependencia sería circular: el map-matching necesita identidad
para decidir el sentido de cada (línea, trayecto) —los trazados de ida y vuelta
van por las mismas calles— y el tracker necesitaría la abscisa. Además el
tracker sigue siendo utilizable sin el GTFS, que es lo que permite probarlo con
escenarios construidos a mano y lo que mantiene la capa de ingesta limpia.

**Consecuencias.**

- Dos pasadas de `rastrear` por jornada: unos 7 min de reloj frente a 3,5.
- Las posiciones sin abscisa fiable (10-12 % en real: fuera de ruta o ambiguas)
  entran como `NaN` y se emparejan con el criterio del plano, fila a fila.
- `prepare.py` orquesta; ningún módulo de `src/project/` gana dependencias
  nuevas hacia abajo.

**Alternativas.** Que `tracking.py` llamara al map-matching: una sola llamada,
pero dependencia circular y tracker inseparable del GTFS. Descartada.

**Reabrir si** el map-matching deja de necesitar identidad para decidir el
sentido —por ejemplo, si la fuente publicase `direction_id` o el GTFS trajera
una correspondencia con el campo `trayecto`.

---

## ADR-013 · El tracker rastrea en una pasada; la abscisa es para el paso por parada · revisable

**Decisión.** `prepare.py` llama a `rastrear` una sola vez, sin abscisa. El
map-matching se hace después y se usa para segmentar viajes e interpolar el paso
por parada (`etiquetado.py`). Sustituye la parte de ADR-012 que mandaba rastrear
dos veces; el resto de ADR-012 sigue en pie: `rastrear` acepta la abscisa y
`tracking.py` no importa el GTFS.

**Por qué.** La confirmación de ADR-012 sobre jornada real era un artefacto: la
abscisa se pegó por posición a una entrada desordenada (bitácora 023). Bien
alineada, la segunda pasada no cambia ni el número de trayectorias ni su
duración en tres jornadas, y el indicador de intercambios `ida_vuelta` sube un
30-55 %. La mejora del −7,6 % de la simulación no se transfiere a lo real.

**Consecuencias.** Unos 3,5 min de reloj menos por jornada (una pasada de
`rastrear` en lugar de dos, ADR-012). Las guardias de la abscisa en el tracker (mutantes
048-052) siguen vigentes porque el código sigue ahí.

**Reabrir si** se explica la subida de `ida_vuelta` y una segunda pasada mejora
la identidad sobre jornada real, medida con `banco_tracker --real-abscisa`.

---

## ADR-014 · El GTFS se elige por día de servicio entre todas sus versiones · cerrada

**Decisión.** Todas las versiones descargadas del feed se guardan en
`settings.gtfs_dir` (una por zip, bajo DVC). Para cada día de servicio manda la
versión más reciente cuya vigencia declarada lo cubre; si ninguna lo declara, la
más reciente cuyo `calendar.txt` lo cubre, y la etiqueta se marca
`fuera_de_vigencia`.

**Por qué.** El feed no guarda histórico y las versiones se solapan: la
`01-09-2026` (vigente 24/08-30/09) y la `19-09-2026` (12/09-19/10) conviven del
12 al 30/09, y sólo la segunda tiene los viajes de la línea 63 y los recorridos
nuevos de la 92, la 18 o la 95 (`docs/09_gtfs_emt.md`). Un feed fijo etiqueta
septiembre con el horario de agosto, o agosto con el de octubre, sin error.

**Consecuencias.** Los días del 15 al 23/08 se etiquetan con la `01-09-2026`, cuyo
calendario los cubre pero cuya vigencia no: quedan marcados. El día de servicio
empieza a las 04:00 locales (`etiquetado.HORA_CORTE`), porque el feed escribe la
madrugada como 25:10.

**Excepción declarada (21/09).** Del 31/08 al 07/09 no se etiqueta
(`params.yaml → prepare.excluir_fechas`). Lo que circuló esos días encaja con el
servicio de septiembre, pero la EMT no lo publicó hasta el 10/09 y con
calendario desde el 08/09 (versiones archivadas en Transitland, `docs/09`). El
único horario publicado para esos días es el de verano, con el que se asignaba
el 75 % de los tramos y se triplicaban los conflictos (bitácora 024).

**Excepción definitiva (22/09).** El historial de Transitland muestra que entre
el 02/09 y el 10/09 la EMT no publicó ninguna versión: no existe un horario de
septiembre para el 31/08-07/09 en ningún archivo (`docs/09`,
`auditoria/resultados/transitland_versiones_2026-09-22.txt`). Las versiones del
10 al 18/09 cubrirían el 08-11/09, que hoy se etiqueta con el horario de verano,
pero descargarlas exige el plan de pago de Transitland; `ingest.transitland`
queda como consulta de metadatos.

**Reabrir si** aparece una versión archivada (Transitland) que cubra 15-23/08.

---

## ADR-015 · `curar` es un stage de DVC; la ingesta no · cerrada

**Decisión.** `reprocesar` (crudo → curated) entra en `dvc.yaml` como stage
`curar`, antes de `prepare`. El colector sigue fuera (ADR-002).

**Por qué.** `reprocesar` es determinista y el curated que produce es el de
referencia: deduplica los sondeos y se queda la captura más completa, cosa que el
colector no hace (bitácoras 019 y 020). Sin stage, `prepare` dependería de un
curated que nadie sabe cómo se regeneró.

**Consecuencias.** Un cambio en el crudo o en el parser reejecuta `curar` (unos
17 min sobre 32 días) y todo lo que cuelga de él.

---

## ADR-016 · Kafka no entra en la captura; queda para el servido en tiempo real · revisable

**Decisión.** El colector escribe a disco (crudo NDJSON y curated Parquet), sin
broker de por medio. Kafka, o Redpanda, que habla su mismo protocolo, queda como
opción del demostrador en tiempo real: en `docker-compose`, en el PC y no en la
Pi, y solo cuando exista el modelo. La arquitectura de la propuesta al tutor
(`docs/04`: ingesta → Kafka/Redpanda → Parquet) no es la implementada.

**Por qué.**

- **El volumen no lo pide.** Día completo del 16/09/2026: 6.222 payloads (EMT
  2.821, Renfe 2.767, estado del tráfico 277, Valenbisi 267, intensidad 90), es
  decir, 0,07 por segundo, y unos 314 MB sin comprimir (42 MB en gzip). Un broker
  se justifica varios órdenes de magnitud por encima. Presentar Kafka como
  respuesta al volumen no resiste esa cifra.
- **Desacoplar y reejecutar ya está resuelto.** El crudo se guarda antes de
  parsear y `reprocesar` lo reconstruye todo (ADR-002, ADR-015).
- **Riesgo.** En la captura, un broker es un punto de fallo más sobre datos que
  no se pueden recapturar.
- **Hardware.** Kafka arranca por defecto con 1 GB de heap y Redpanda pide
  alrededor de 1 GB en modo desarrollo. La Pi sirve además el DNS de casa, el
  servicio del colector está limitado a `MemoryMax=512M` y su RAM no está
  verificada.

**Dónde sí aporta.** Predecir un bus en vivo exige variables calculadas sobre la
flota en ese momento: `tramo_ganado_{W}min`, las ventanas de la línea y el bus
anterior. Hace falta un proceso que consuma el flujo y mantenga ese estado, y un
bus de mensajes lo separa del colector y del escritor del curated. El coste de
verdad no es el broker: `rastrear`, `etiquetar` y `features.construir` trabajan
por día completo y tendrían que funcionar de forma incremental sin separarse de
lo que vio el entrenamiento (train/serve skew).

**Alternativas.** Kafka en la captura: descartada, por lo anterior. Sin Kafka en
ningún punto: válida, y con 0,07 mensajes/s puede bastar un proceso en
`services/` que sondee las fuentes y guarde la ventana en memoria.

**Qué la reabriría.** Montar el servido en tiempo real, después de `train.py`.
Ahí se elige entre broker y proceso en `services/`, con la latencia y la memoria
medidas.

Reproducir la cifra: contar las líneas de
`data/raw/source=*/date=2026-09-16/payloads.ndjson.gz` (una por payload).

---

## Pendientes de decidir

- **Selección de corredores.** `docs/05` mide 57,7 % de cobertura de tráfico y
  propone acotar a 4-6 corredores (93, C3, 98E, 99, 81) en vez de las 47 líneas.
  Es un criterio objetivo de selección de muestra, pero la decisión no está
  formalmente cerrada.
- **Geometría en el crudo de tráfico.** El 74 % del disco lo genera repetir la
  geometría de los 446 tramos en cada sondeo. `&returnGeometry=false` ahorraría
  ~90 % de esa fuente, pero el crudo verbatim tiene valor probatorio para la
  memoria.
- **Particionado de Parquet.** Por fecha es lo obvio; no está fijado.
- **Reparto DuckDB / Polars.** Ver ADR-004.
