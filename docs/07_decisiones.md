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

**Consecuencias.** Lectura con proyección de columnas y predicate pushdown.

**Particionado (cerrado el 30/09/2026).** Por fecha, en todas las capas, que es
lo que ya hacía el código:

- `curated/source=<fuente>/date=<día>/`: día de **captura**, en UTC.
- `interim/{emt_tracked,viajes,pasos}/date=<día>/`: día de **servicio**, de
  04:00 a 04:00 en hora local (`prepare.ventana_servicio`).
- `processed/train.parquet` y `test.parquet`: un fichero cada uno.

Los dos días no son el mismo. Quien lea `curated/` por un día de servicio filtra
por `ts_utc` sobre todas las particiones, no por `date=` (bitácora 011).

**Alternativas.** CSV descartado por volumen. Formatos de tabla (Delta, Iceberg):
sin evaluación registrada.

---

## ADR-004 · DuckDB como motor analítico, pandas para transformar · cerrada

**Decisión.** DuckDB lee y filtra el Parquet; pandas y numpy hacen las
transformaciones por día. Sobre el portátil, sin cluster. **Polars no se usa**
(cerrado el 30/09/2026): la decisión original decía «DuckDB y Polars» y dejaba
el reparto sin fijar, y el código lo resolvió solo. No está instalado ni se
importa en ningún módulo.

**Por qué.** El volumen es grande para pandas en memoria pero pequeño para Spark.
DuckDB lee Parquet particionado sin cargarlo entero, y entrega a pandas un día
cada vez.

**Consecuencias.** `rastrear()` recorre snapshots en Python y se identificó como
cuello de botella (`docs/05`, sección 7). Procesando por día y en paralelo no lo
ha sido: `prepare` tarda 42 min sobre 32 jornadas con 8 procesos (bitácora 024).

**Qué la reabriría.** Que una transformación deje de caber en memoria por día, o
que `prepare` pase de un par de horas con la captura completa.

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

**Precisión (07/10).** «Siguiente parada» es la parada `stop_sequence + h` del
horario, si se observó. Hasta esta fecha era el h-ésimo paso *observado*: con
una parada sin observar saltaba a la de después, y el horario y la distancia
hasta el objetivo sabían de un hueco que aún no había ocurrido (0,54 % de las
filas de prueba). Sin esa parada, la fila no tiene objetivo (bitácora 046).

---

## ADR-007 · Split temporal, nunca aleatorio · cerrada

**Decisión.** El corte train/test es por fecha (`features.test_desde`).

**Por qué.** Con series de posiciones, un split aleatorio mete futuro en el
entrenamiento y produce métricas infladas.

**Consecuencias.** El test es un bloque temporal contiguo, así que hereda lo que
haya pasado esos días (obras, festivos, meteorología). Hay que declararlo como
limitación en la memoria.

**Corte (05/10).** `test_desde = 2026-09-21` con la captura hasta el 04/10: la
prueba son dos semanas enteras, de lunes a domingo, y el entrenamiento agosto
(15-30/08) más la semana lectiva del 14 al 20/09. El 31/08-11/09 está excluido
(ADR-014) y el 10-14/09 falta en la captura (bitácora 021). Con el corte del 14/09
y la captura hasta el 18/09, el entrenamiento era solo agosto frente a una prueba
lectiva (bitácora 037). Se descartó el 28/09: dos semanas lectivas en
entrenamiento, pero una sola de prueba, y el soporte por línea pide días de
prueba (bitácora 036).

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

**Lo que no cambió.** La ingesta sigue fuera del grafo de DVC (ADR-002), y
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

**Ampliada al 11/09 (05/10).** Etiquetados con el de verano, el 08-10/09 eran
135.114 filas de `train.parquet` (el 10,9 %), con 5-6 veces los conflictos y
8-9 veces los rechazos por margen de un día medio de agosto (bitácora 037). Se excluyen igual
que el 31/08-07/09. Consecuencia: el entrenamiento queda entero en agosto y la
prueba en septiembre lectivo. Se corrige moviendo el corte con la captura
posterior al 18/09, no volviendo a incluir estos días.

**Versión posterior archivada y no usada (06/10).** La `05-10-2026` (vigente
28/09-04/11) contradice el 3,6-7,0 % de los pasos etiquetados del 28/09-04/10.
Quita la línea 13, que siguió circulando y etiquetándose con retrasos
plausibles. En la 35 prolonga el horario excepcional (`601`) donde la
`19-09-2026` vuelve al normal (`606`), y ajustar los viajes observados a uno u
otro no decide cuál circuló (bitácora 042). Se guarda en `data/raw/gtfs_archivo/`,
fuera de `gtfs_dir`, y la prueba sigue etiquetada con la `19-09-2026`: cubre el
periodo entero y casa con lo observado. Es una excepción declarada a «manda la
más reciente».

**Reabrir si** aparece una versión archivada (Transitland) que cubra 15-23/08 o el
08-11/09, o si una versión posterior al 19/09 resulta casar mejor con lo
observado en la 13 o la 35.

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
  decir, 0,07 por segundo, y 317 MB sin comprimir (unos 42 MB en gzip). La
  mediana de las 32 jornadas es de 6.336 payloads y 297 MB (bitácora 033). Un broker
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

Reproducir la cifra: `uv run python -m project.analysis.medir_volumen --dias 2026-09-16`.

---

## ADR-017 · La geometría de tráfico se guarda una vez; el crudo llega sin ella · cerrada

**Decisión.** Las capas 192 y 188 se piden con `returnGeometry=false`. La
geometría se descarga una vez a `data/reference/<fuente>_geometria.parquet` y no
se repite en cada sondeo (`Source.geometria_estatica`, `collect.asegurar_geometria`).

**Por qué.** Repetir la geometría era el 74 % del disco (`docs/05`). Medido sobre
el crudo, por payload: la 192 pasa de 258 kB a 64 kB y la 188 de 156 kB a 74 kB.

**Consecuencias.** El crudo deja de ser la respuesta completa de la fuente desde
el 19/08/2026. Los días 15-18/08 sí traen la geometría en cada sondeo. Si el
Ajuntament cambiara el trazado de un tramo, el colector no lo vería: la
referencia es la del primer sondeo.

**Alternativas.** Crudo íntegro, por su valor probatorio: descartada por el
disco. Ese valor lo conservan los cuatro primeros días.

**Qué la reabriría.** Un tramo cuyo `idtramo` no esté en la referencia.

Reproducir la cifra: `uv run python -m project.analysis.medir_volumen`. `max_kb`
es el payload con geometría y `mb_dia` entre `payloads_dia`, el habitual sin ella.

---

## ADR-018 · Todas las líneas entran en la muestra; la cobertura de sensores es un estrato y una mejora es una diferencia con intervalo · revisable

**Decisión.** Cinco, que sustituyen a la propuesta de acotar a 4-6 corredores:

1. Se entrena y se evalúa con **todas las líneas etiquetadas**. No se excluye
   ninguna.
2. La cobertura de sensores de tráfico define un **estrato de evaluación**, no
   recorta la muestra.
3. Una línea se informa con cifra propia con al menos **100 viajes en 3 días de
   servicio** en la prueba y 100 viajes en entrenamiento
   (`features.soporte_por_linea`). Las demás cuentan en la métrica global y se
   informan agrupadas en `poco_soporte` y `sin_entrenamiento`.
4. **Qué es una mejora.** Toda comparación —modelo contra persistencia, modelo
   con tráfico contra modelo sin él— se informa como diferencia sobre los mismos
   viajes, con su intervalo del 95 % remuestreando viajes. Hay mejora si el
   intervalo no contiene el cero; si lo contiene, el resultado es «no se
   distingue». No hay mínimo de magnitud: se informa el tamaño del efecto.
5. Lo que aporta el tráfico se juzga **en el conjunto y en el estrato con
   sensor**, no línea a línea.

**Nunca** se excluye una línea por el error del modelo ni por su cobertura de
sensores.

**Por qué.** Los dos motivos para acotar eran el coste de etiquetar las 47
líneas y la cobertura de sensores. El primero desapareció: el pipeline etiqueta
todas, y los cinco corredores propuestos (93, C3, 98E, 99 y 81) eran el 22,8 %
de las filas; la 98E ni siquiera tiene trazado en el GTFS. Recortar
por cobertura deja fuera justo las líneas periféricas y sesga la muestra a favor
de la hipótesis (bitácora 026). El criterio de mejora no estaba escrito en
ningún sitio: «por un margen claro» no es un criterio.

**Consecuencias.** Con la prueba actual, de 5 días, 24 líneas tienen cifra
propia, 9 poco soporte y 10 no tienen entrenamiento. Por línea, con 100 a 299
viajes, no se distingue una mejora de menos de 1-2 s si el modelo se parece a la
persistencia, ni de menos de unos 6 s si se aleja de ella; de ahí la decisión 5. La
evaluación del modelo tendrá que calcular el intervalo de la diferencia
remuestreando viajes, no filas.

**Límite conocido.** El intervalo por viajes da por buenos los días de la prueba:
no recoge lo que cambia el resultado de un día a otro, así que es un suelo de la
incertidumbre, no su medida. Con 5 días de prueba esa variación no se puede
estimar. Está en los pendientes.

**Alternativas.** Acotar a corredores: descartada, por lo anterior. Excluir las
líneas con menos del 40 % de sus posiciones en viajes asignados (25, 63 y 73):
descartada, porque la regla de soporte ya las aparta de las cifras por línea,
excluirlas movía el resultado global 0,08 s, lo que sí se etiqueta de ellas no es
peor que en el resto, y obligaba a defender un umbral elegido después de ver los
datos y un sesgo a favor de la hipótesis. Un mínimo de mejora en segundos:
descartado por arbitrario.

**Qué la reabriría.** Que el modelo, con y sin las líneas de indicador bajo, dé
resultados distintos más allá de su intervalo. Que el estrato de sensores, una
vez medido, solo aporte ruido. Que con la captura completa casi ninguna línea
quede por debajo del soporte. Que el tutor pida un mínimo de magnitud.

Reproducir: `uv run python -m project.analysis.medir_rutas lineas` y
`uv run python -m project.analysis.medir_soporte`. Detalle en la bitácora 036.

**Unidad de remuestreo (06/10).** Con 14 días de prueba, `evaluate` da también
el intervalo remuestreando días, en el conjunto, los grupos y las bandas. Por
línea no, porque una línea puede tener solo tres días. Hay mejora si **ninguno
de los dos** intervalos contiene el cero. El de días es el más ancho, así que en
la práctica manda él: con la v2, [−2,25, −1,95] frente a [−2,14, −2,04] por
viajes (bitácora 045).

---

## ADR-019 · `linea` entra como categórica fijada; el sesgo del horario por tramo es variable y listón · revisable

**Decisión.** Tres, en `features.py`:

1. `linea` entra al modelo como **categórica nativa**, con las categorías del
   entrenamiento fijadas (`features.categorias_linea`) y aplicadas en
   entrenamiento e inferencia por `features.matriz`. Una línea que el
   entrenamiento no vio queda nula.
2. **Sesgo del tramo** (`tramo_sesgo_s`, `tramo_sesgo_soporte`): mediana de lo
   que gana la persistencia en (versión del horario, línea, parada, parada
   objetivo), con lo que acabó el tramo antes de la primera observación del día.
3. **Tercer baseline**, `persistencia_tramo`: la persistencia más ese sesgo. Lo
   que aporte el tráfico se mide contra él, no contra la persistencia.

**Por qué.** La línea sola apenas explica el error de la persistencia: corregirla
por línea, con lo aprendido en entrenamiento, baja el MAE de la prueba de 36,40
a 36,33 s (bitácora 039). Entra porque es barata, su efecto es estable entre
periodos (correlación 0,86) y deja al árbol cruzarla con otras variables. Lo que
pesa es el tramo: 36,80 → 26,48 s. Es el sesgo fijo del horario (bitácora 032);
un modelo que bata la persistencia lo hará sobre todo por aprenderlo.

**Consecuencias.** `train.py` guarda las categorías con el modelo y `predict.py`
las lee de ahí. El primer día de una versión nueva del horario no hay sesgo del
tramo: la variable es nula hasta que acumula `soporte_min` viajes.

**Alternativas.** `linea` como texto: XGBoost no lo admite. Categórica con las
categorías de cada tabla: cada tabla numera las suyas, y la prueba lee otra
línea sin error (mutante 099) si el modelo recibe los códigos. XGBoost 3.2,
con entrada pandas, recodifica por valor las líneas que vio y rechaza con error
la que no vio: la 8 de la prueba tiraría la evaluación entera (mutante 104,
bitácora 040). Codificación por media del objetivo: fuga si se
calcula con la fila dentro. El par (línea, parada) como categórica: miles de
niveles; la mediana histórica condensa lo mismo en una columna. El sesgo
congelado con el entrenamiento: 27,48 s frente a 26,48 s con todo lo anterior al
día y la versión del horario en la clave.

**Qué la reabriría.** Que el modelo sin `linea` no se distinga del modelo con
ella (ADR-018, criterio de mejora): fuera por simplicidad. Que el sesgo cambie
dentro de una versión del horario más de lo que capta la mediana acumulada.

Reproducir: `uv run python -m project.analysis.medir_sesgo_tramo` y
`metrics/features.json` (`persistencia_tramo`). Detalle en la bitácora 039.

---

## ADR-020 · El colector guarda cada versión del GTFS; el etiquetado no la usa sin revisarla · cerrada

**Decisión.** El colector consulta cada 6 h el GTFS vigente en VLCi y guarda
cada versión nueva, una vez por sha1, en `raw/source=gtfs_emt/date=<día>/`, con
una línea en `capturas.ndjson`. **No** va a `settings.gtfs_dir`. Una versión
entra en el etiquetado a mano, después de contrastarla con lo ya etiquetado
(`analysis/comparar_gtfs`).

**Por qué.** El GTFS tampoco guarda histórico. La EMT lo republica casi a
diario (14 versiones entre el 19/09 y el 06/10), y una publicación posterior
puede reescribir días ya etiquetados (bitácora 042). Hasta ahora se descargaba
a mano, y así se perdieron las versiones del 10-18/09, que solo están en
Transitland de pago (ADR-014).

**Consecuencias.**
- Unos 7 MB por versión nueva, una al día: unos 2,5 GB al año en la Pi.
- `pull_data.sh` lo trae a `data/raw/source=gtfs_emt/` sin cambios (patrón
  `source=*/date=*/`), y `reprocesar` lo ignora porque solo recorre `SOURCES`.
- Pasar una versión a `gtfs_dir` cambia etiquetas y obliga a reejecutar
  `prepare`.
- Está en las dos copias del colector: `demo/` en la rama `raspberry`, que es
  lo que corre la Pi, y `src/project/ingest/` en `develop`, para que el
  redespliegue pendiente del ADR-009 no lo pierda.

**Alternativas.**
- Seguir descargando a mano: es lo que perdió las versiones de septiembre.
- Guardar directamente en `gtfs_dir`: la versión del 05/10 habría dejado la
  línea 13 sin etiquetar en media prueba, sin ningún aviso.
- Pagar Transitland: cuesta dinero y depende de un tercero. Queda como
  respaldo para lo ya perdido.

**Qué la reabriría.** Que VLCi publique el histórico de versiones.

---

## ADR-021 · Protocolo del modelo v2: un listón, cuatro brazos en validación y la prueba una vez · cerrada

Escrito y commiteado **antes** de entrenar ningún brazo.

**Decisión.**
1. **Métrica primaria:** la diferencia de MAE global entre el modelo y
   `persistencia_tramo` en la prueba, con su intervalo del 95 % remuestreando
   viajes (`evaluate.diferencia`). Hay mejora si el intervalo no contiene el
   cero (ADR-018). El RMSE, los grupos de soporte, las bandas de intervalo y las
   líneas se informan, pero no deciden.
2. **Validación:** la semana del 14 al 20/09 (`train.dias_validacion: 7`), de
   lunes a domingo, con la composición de la prueba. El ajuste es agosto. Tras
   la parada temprana se reajusta con todo el entrenamiento, como en la v1.
3. **Cuatro brazos, fijados aquí:** pérdida {`reg:squarederror`,
   `reg:absoluteerror`} × objetivo {nivel, residuo sobre `retraso_s`}.
   - El residuo significa que el modelo aprende `objetivo − retraso_s` y
     `predict` suma `retraso_s` de vuelta.
   - Todos con parada temprana por MAE (`eval_metric: mae`), tope de 3.000
     árboles y el resto de hiperparámetros de la v1.
   - Ninguno lleva `tramo_sesgo_soporte`, que crece con el calendario
     (bitácora 041).
4. **Elección.** Gana el brazo con menor MAE en la validación, con una
   excepción: si su diferencia, sobre los mismos viajes, con un brazo con menos
   cambios respecto a la v1 tiene un intervalo que contiene el cero, gana el de
   menos cambios. Los cambios se cuentan así: nivel + cuadrática, 0; nivel +
   absoluta, 1; residuo + cuadrática, 1; residuo + absoluta, 2. Si empatan dos
   con el mismo número de cambios, decide el MAE.
5. **Ablación de `linea`** sobre el brazo elegido, también en la validación. Si
   el modelo sin `linea` no se distingue del modelo con ella, `linea` sale
   (ADR-019).
6. **La prueba se evalúa una sola vez**, con el modelo resultante.
   - Se declara lo probado en la validación: 4 brazos y 1 ablación.
   - La v1 (bitácora 041) se conserva como referencia.

**Por qué.** La v1 empató con el listón, y su validación (viernes a domingo) no
anticipó la prueba. Elegir una variante mirando la prueba convierte la prueba en
validación y la cifra final deja de ser honesta. Con el protocolo escrito
antes, la elección se puede defender. Los brazos salen de dos hipótesis con un
mecanismo detrás:
- el MAE premia la mediana y la pérdida cuadrática estima la media;
- un árbol reconstruye a trozos la identidad `retraso_s → objetivo`.

**Consecuencias.**
- `predict` necesita saber si el modelo es de residuo, y lo lee del artefacto.
- Quitar una variable de `features.variables()` obliga a reejecutar
  `features`; la tabla no cambia.
- Los brazos se entrenan con `analysis/elegir_brazo.py`, fuera del grafo de
  DVC: solo elige, y lo que entra en `train` es el valor fijado en
  `params.yaml`. Cada brazo se registra en MLflow.

**Alternativas.**
- Búsqueda de hiperparámetros: multiplica los brazos y el sobreajuste a la
  validación. Queda fuera hasta que algún modelo bata al listón.
- Validar con el 18-20/09: no tiene la composición de la prueba.
- Evaluar cada brazo en la prueba y quedarse el mejor: es elegir con la prueba.

**Qué la reabriría.** Que ningún brazo bata a `persistencia_tramo` en la
validación. Entonces el problema no es la pérdida ni el objetivo, sino las
variables.

**Matices de la revisión (06/10, tras evaluar).** Lo de arriba es el texto
commiteado antes de entrenar y no se toca. La revisión del tribunal precisó
tres cosas:
- **La prueba no estaba sin ver.** La v1 ya se había evaluado en ella. Además,
  el espacio de brazos, la retirada de `tramo_sesgo_soporte` y la clave del
  listón se decidieron después de verla (bitácoras 039 y 041). La v2 es la
  **segunda** evaluación de la prueba, con el diseño fijado tras la primera.
  La confirmación limpia es evaluar la v2 congelada en días posteriores al
  04/10.
- **La validación casa con la prueba en los días de la semana, no en todo.**
  - El 8,8 % de sus filas no tiene sesgo del tramo, frente al 0,18 % de la
    prueba: el 14/09 es el primer día del horario `19-09-2026`.
  - Diez líneas aparecen solo en ella. Para los brazos, ajustados con agosto,
    son líneas no vistas.
- **Los «cambios» se cuentan respecto a la configuración base de la v2**
  (nivel + cuadrática, con parada por MAE y validación de 7 días), no respecto
  a la v1, que difiere en más cosas.

---

## ADR-022 · El «ahora» de cada fila es cuándo se supo su retraso, y la primaria mide lo que aún llega a tiempo · cerrada

**Decisión.**
1. **`t_disp(i)`, cuándo se sabe el retraso del paso**
   (`features.instante_disponible`), es el más tardío de dos instantes:
   - la llegada a nuestro disco del sondeo con la última posición que usa
     `cruces`: la primera tras el cruce (k1), o la siguiente (k1+1) si llega
     en menos de `max_hueco_cruce_s`, porque con ella corrige la velocidad;
   - el `t_disp` del paso número `paradas_referencia` del viaje, porque el
     viaje programado, y con él el retraso, se elige con esos primeros pasos.

   Solo cuentan las posiciones fiables, como en `cruces`. En la parada final,
   la última posición, y nunca antes de `t_obs`.
2. **Toda variable cuenta solo lo que había llegado antes del `t_disp` de la
   fila:** las ventanas de línea, la flota del tramo, el bus anterior y el
   corte del sesgo del día.
3. **Horizonte previsto:** `t_prog_hasta_objetivo_s − (t_disp − t_obs)`, el
   horario hasta la parada objetivo menos lo que ya se ha ido en saber el paso.
   Solo usa lo que se sabe al predecir.
4. **Población** (`features.poblacion`): horizonte previsto > 0. `train`
   entrena con ella y `evaluate` da la primaria sobre ella. El resto se
   informa aparte como *nowcast*. Los estratos van por horizonte previsto:
   0-30, 30-60, 60-120 y más de 120 s.
5. Se calcula en `features`, cruzando `pasos` con `emt_tracked` y con la
   llegada de cada sondeo en el curated.

**Por qué.** Trampa 017. La primera versión de esta decisión tomaba k1 y
olvidaba la asignación. El tribunal lo encontró: más de la mitad de la mejora
estaba en el primer paso de cada viaje (−23 s), cuyo retraso no se conoce hasta
el tercero. Estratificar por el horizonte real, `t_obs(i+1) − t_disp(i)`, es
condicionar por el resultado.

**Consecuencias.**
- Un retraso se sabe 80,7 s después del paso, de mediana.
- Con una parada de horizonte, el 45 % de las filas de la prueba no llega a
  tiempo: queda fuera de la población.
- Sobre la población, el modelo mejora a `persistencia_tramo` en −1,01 s,
  en torno a un 4 % de su error en todos los horizontes.
- En el *nowcast* es peor (+7,7 s): no se usa ahí.
- La antelación necesita un horizonte de más de una parada (bitácora 046).
- El ADR-018 sigue mandando sobre la población: hay mejora si ningún intervalo,
  ni por viajes ni por días, contiene el cero.

**Alternativas.**
- Calcular `t_disp` dentro de `cruces`: obliga a reejecutar `prepare` (más de
  1 h) y a tocar la capa más protegida. El cruce en `features` repite la misma
  regla, y un test de extremo a extremo contra `cruces` lo guarda.
- Primaria sobre todas las filas: mezcla un 45 % de predicciones que llegan
  tarde.
- Filtrar por el horizonte real: es condicionar por el resultado.

**Límites declarados** (segunda revisión del tribunal, sin cuantificar en el
repo):
- La asignación compara el viaje ganador con patrones rivales, cada uno con sus
  propios primeros cruces, y exige margen sobre el segundo. Puede saberse
  después del tercer paso del ganador.
- `conflicto` descarta un viaje si otro vehículo, quizá más tarde ese día, lo
  reclama con menor coste. Y los filtros de recorrido mínimo miran el viaje
  entero. Las dos cosas seleccionan filas por el futuro.
- `emt_tracked.fiable` sale del trazado elegido por (línea, trayecto) y día, no
  del candidato con el que `cruces` decide el viaje. En torno al 1 % de los
  viajes, las posiciones que mira `t_disp` pueden diferir de las de `cruces`.

**Qué la reabriría.** Un horizonte de más de una parada, que cambia qué filas
llegan a tiempo, o que `cruces` deje de usar la posición k1+1.

---

## ADR-023 · La antelación se mide barriendo horizontes con la configuración fija · cerrada

**Decisión.**
1. Se barren los horizontes de 1, 2, 3, 5 y 10 paradas
   (`features.horizonte_paradas` y `features.horizontes_barrido`). Con 84 s de
   horario mediano por parada, cubren de unos 1,4 a unos 14 min.
2. **Un modelo por horizonte**, con la configuración del ADR-021 (residuo con
   pérdida absoluta) y su propia parada temprana. No se elige brazo por
   horizonte.
3. Cada horizonte se evalúa **una vez**, sobre su población (horizonte
   previsto > 0, ADR-022), frente a sus baselines. La persistencia más el sesgo
   del tramo usa el par (parada *i*, parada *i* + *h*).
4. **Stages de DVC:**
   - `disponibilidad` calcula `t_disp` una vez para todo el barrido.
   - `features_h`, `train_h` y `evaluate_h` (`foreach`) escriben en
     `data/processed/h<h>/`, `models/h<h>/` y `metrics/horizontes/h<h>/`.
   - El horizonte 1 conserva sus rutas, porque la bitácora las cita.
5. La antelación se lee por horizonte previsto en minutos (0-1, 1-2, 2-5, 5-10
   y más de 10), dentro de cada horizonte.

**Por qué.** A una parada de horizonte, el retraso se sabe cuando casi no
queda tiempo: el horizonte previsto mediano es de 4 s y el 45 % de las filas
llega tarde (bitácora 046). La parte «con cuánta antelación» de la pregunta
pide horizontes más largos.

**Consecuencias.**
- Cinco modelos y unas 3-4 h de máquina para reconstruir el barrido.
- Con *h* grande, la flota del tramo y el sesgo tienen menos soporte, porque
  hay menos viajes que recorran ese mismo par de paradas: hay más nulos.
- La columna objetivo se sigue llamando `retraso_siguiente_parada_s`, aunque
  con *h* > 1 sea la parada *h*.

**Alternativas.**
- Un solo modelo con *h* como variable: mezcla poblaciones y dificulta leer cada
  horizonte.
- Elegir brazo por horizonte: multiplica las comparaciones en la validación.
- Recalcular `t_disp` en cada `features`: unos 10 min más por horizonte para un
  resultado que no depende de él.

**Qué la reabriría.** Que la mejora caiga a cero antes de los 10 min, que pediría
horizontes intermedios, o la capa 192, que añade el pilar del tráfico.

---

## Pendientes de decidir

- **Cobertura de sensores por tramo.** El estrato de evaluación del ADR-018
  necesita saber qué tramos entre paradas tienen un sensor de la capa 192
  encima. Hoy la cobertura solo está medida por posición (69,4 % a menos de
  50 m, `docs/10`). Se mide al meter la capa 192 en `features.py`.
- **Variante binaria por banda de intervalo.** `evaluate.py` ya estratifica por
  banda de intervalo programado (≤ 8, 8-15, 15-30, > 30 min y `sin_intervalo`),
  como el estrato de sensores (bitácora 038). Falta decidir si la variante
  binaria se publica solo en las bandas largas: se decide con el clasificador.
- **Cadencia de la capa 192.** Sigue en 5 min, fijada cuando la capa parecía
  estática. En periodo lectivo se anima (bitácora 031) y nadie ha vuelto a medir
  si 5 min bastan. Lo que no se capture no se recupera.
- **Servido en tiempo real.** Broker o proceso en `services/` (ADR-016). Se
  decide con el modelo ya entrenado.
- **Tope del índice de trampas.** `.claude/tests/test_trampas.py` lo limita a 45
  líneas y cada ficha ocupa una: con 16 fichas solo cabe uniendo párrafos. Medir
  caracteres o subir el tope.
