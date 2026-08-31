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
aparte (`demo/diagnose.py`). A cambio, **el colector guarda siempre el payload
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

## ADR-009 · `demo/` aislado de `src/project/` · cerrada

**Decisión.** El prototipo de exploración vive en `demo/` y no importa nada de
`project`, ni al revés.

**Por qué.** Permite validar que las fuentes siguen vivas y capturar mientras el
pipeline se construye, sin arrastrar el prototipo a la arquitectura definitiva.

**Consecuencias.** Hay lógica de parseo que acabará portándose a
`src/project/ingest/`. Mientras tanto, `demo/selftest.py` es el arnés de
verdad-terreno del proyecto y varias fichas de `.claude/trampas/` dependen de él.

**Qué la reabriría.** El porte de `demo/sources.py` a `src/project/ingest/`, que
es cuándo se cierra esta decisión por consumación.

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
