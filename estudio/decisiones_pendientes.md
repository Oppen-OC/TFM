# Decisiones pendientes

Lo que depende de ti o de tu tutor. Reverificado el 24/11/2026 contra esta rama
(`oppen/estudio`, desde `develop`): **de las cinco que planteaba el encargo, solo dos
siguen abiertas de verdad** (a y c); las otras tres ya las cerró el repo. Para cada una:
contexto, opciones, recomendación y qué documento cambiaría. Al final, otras abiertas que
sí figuran en el repo.

| Decisión | Estado en esta rama | ¿Hay que decidir? |
|---|---|---|
| (a) Rumbo tras `docs/06` | Resuelto en la práctica: `docs/06:87-165` y ADR-024 | Contrastado el 26/11 con `develop`; no hay que decidir |
| (b) Particionado de Parquet | **Cerrado** el 30/09/2026 (ADR-003, `docs/07_decisiones.md:80-90`) | No |
| (c) Kafka | ADR-016 **revisable**: fuera de la captura, abierto para el servido | **Sí**, para el servido |
| (d) `returnGeometry` | **Cerrado**: ADR-017 (`docs/07_decisiones.md:487`) | No (solo un diff, auditoría 9) |
| (e) DuckDB / Polars | **Cerrado**: ADR-004 (`docs/07_decisiones.md:96-115`), Polars no se usa | No (solo limpiar la mención) |

---

## (a) Rumbo tras `docs/06`: ¿mantener la fusión o reformular?

**Contexto.** En agosto, `docs/06` concluía que las capas de tráfico eran estáticas
(192: 8 de 409 tramos cambian en un lunes; 188: 1 de 294 snapshots) y proponía invertir
la pregunta (buses como sensores del tráfico). Hoy `docs/06:9-14` avisa de que se
reformuló el 13/11: con el corpus entero la 188 sigue congelada y la 192 **se anima en
periodo lectivo** (de 8,5 a 34 tramos con congestión por día laborable, `docs/06:104-119`).
La hipótesis se contrastó con la primaria fijada de antemano (ADR-024,
`docs/07_decisiones.md:872`): la 192 no aporta (−0,13 s sobre 56 s, IC por días
[−0,30, +0,01]); la v2 sin tráfico bate al listón en −3,37 s (`docs/06:126-143`). Y se
decidió **no invertir** la pregunta (`docs/06:144-154`).

**Opciones.**

1. **Mantener** la pregunta actual y presentar el resultado negativo con su IC (lo que
   ya dicen `docs/00`, `CLAUDE.md` y ADR-024).
2. **Reformular** hacia «los buses como sensores» (la propuesta de agosto de `docs/06`).
3. **Híbrida**: pregunta actual en el título, y la flota como sensor como aportación
   secundaria (ya entró como variables, bitácora 032).

**Recomendación.** Opción 1, con la 3 como argumento de apoyo. Razones: la prueba ya
está evaluada una sola vez y todo análisis posterior es exploratorio (`CLAUDE.md`,
*Estado*); reformular ahora sería elegir la pregunta después de ver el resultado; y un
resultado negativo bien medido responde igualmente a una pregunta falsable
(`docs/04:21-27`). Por tanto **no hace falta un ADR nuevo para invertir nada**.

**Qué cambiaría.** Nada, si se mantiene. Si aun así quieres un ADR que recoja la decisión
del 13/11, **el siguiente número libre es el 026** (el encargo proponía «ADR-011», pero el
011 ya existe: los tests se validan por mutación, `docs/07_decisiones.md:257`; el último
es el 025, `docs/07_decisiones.md:1068`).

**Contrastado el 26/11 contra `develop` (versión de referencia):** `docs/06:133-147`, ADR-024 (`docs/07:1036-1045`) y bitácora 057 dan las mismas cifras (−0,13 s, IC [−0,30, +0,01], −3,37 s). Queda por decidir:

- La pregunta de investigación: `docs/00:18-21` («cuánto del retraso se explica por la
  congestión…») y `docs/04:21-25` («cuánta información anticipatoria…») están
  formuladas distinto (auditoría N3). Decide cuál defiendes en la memoria y por qué
  cambió; el tribunal puede preguntarlo.
- Las cifras de la capa 188 (394/358/354/355, auditoría 10): coherentes entre docs, pero no re-medibles aquí (falta `data/`); cita cada una con su definición.

**Para el tutor.** Llévale la lectura del resultado negativo (¿le basta como aportación
empírica?) y la formulación de la pregunta.

---

## (b) Particionado de Parquet

**Contexto.** El encargo decía «por fuente y día» en `docs/01`/`03`/`04` frente a «no
fijado» en `docs/07` Pendientes. **Ya está cerrado:** «Por fecha, en todas las capas»
(ADR-003, `docs/07_decisiones.md:80-90`): `curated/` por día de captura (UTC),
`interim/{emt_tracked,viajes,pasos}/` por día de servicio (04:00 a 04:00 local) y
`processed/` en un fichero por conjunto. «Pendientes de decidir» (`docs/07:1141-1152`)
ya no lo lista.

**Recomendación.** Nada que decidir. Sí que tengas claro que **día de captura y día de
servicio no son lo mismo**: quien lea `curated/` por día de servicio filtra por `ts_utc`
sobre todas las particiones, no por `date=` (bitácora 011).

**Qué cambiaría.** Nada.

---

## (c) Kafka: ¿arquitectura objetivo o descartada?

**Contexto.** La propuesta al tutor planteaba ingesta → Kafka/Redpanda
(`docs/04:112`). ADR-016 lo sacó de la **captura** (volumen de 0,07 payloads/s, el crudo
ya desacopla, un broker es un punto de fallo más sobre datos irrecuperables, y la Pi no
tiene RAM de sobra) y lo dejó **revisable** para el servido en tiempo real
(`docs/07_decisiones.md:429-486`). El servido en vivo existe como **demo** sin broker
(nota del 10/11) y se midió: 11-12 s a las 10:00 y 27-32 s a las 18:00 con las líneas de
una parada. «Servido en tiempo real incremental» sigue sin decidir (`docs/07:1141-1152`).

**Opciones.**

1. **Descartado del todo.** El Big Data del trabajo es captura continua irrecuperable,
   Parquet y DuckDB sin broker.
2. **Trabajo futuro**: servido incremental con broker, solo si una latencia medida lo
   pide.
3. **Implementarlo** para el servido incremental.

**Recomendación.** Opción 2. Es lo que ADR-016 ya razona: presentar Kafka como respuesta
al volumen no resiste la cifra, y el coste real del servido incremental no es el broker
sino hacer `rastrear`, `etiquetar` y `features.construir` incrementales sin train/serve
skew. **Riesgo a asumir con el tutor:** `docs/02:21` advertía de que un tribunal de
Big Data pregunta «dónde está el streaming». La respuesta honesta ya está escrita
(ADR-016 y bitácora 033), pero conviene que tu tutor la valide.

**Qué cambiaría.** Si pasa a objetivo: ADR-016 (estado y «Qué la reabriría»), `docs/00`
(casilla de servido incremental) y `docker-compose.yml`. Si queda descartado/futuro:
solo el aviso de vigencia de `docs/04` (ya lo dice).

---

## (d) Política de `returnGeometry`

**Contexto.** El encargo decía «pendiente de decidir» (`docs/05:154`). **Está decidido**:
ADR-017 (`docs/07_decisiones.md:487`): las capas 192 y 188 se piden sin geometría y la
geometría se baja una vez a `data/reference/` (`src/project/ingest/sources.py:171-174`,
usado en `src/project/ingest/collect.py:271`). La 192 pasa de 258 kB a 64 kB por payload.
Coste aceptado: el crudo ya no es la respuesta completa de la fuente desde el 19/08, y si
el Ajuntament cambiara el trazado de un tramo, el colector no lo vería.

**Recomendación.** Nada que decidir. Qué reabriría ADR-017: un `idtramo` que no esté en
la referencia.

**Qué cambiaría.** Solo `docs/05:154` (auditoría, diff 9).

---

## (e) Reparto DuckDB / Polars

**Contexto.** La decisión original decía «DuckDB y Polars» y no fijaba el reparto.
ADR-004 lo cerró el 30/09/2026: **DuckDB lee y filtra el Parquet; pandas y numpy
transforman por día; Polars no se usa** (no está instalado ni se importa,
`docs/07_decisiones.md:96-115`). Solo quedan menciones de Polars en documentos históricos
(`docs/02:21,66,79`).

**Recomendación.** Nada que decidir. Si el tribunal pregunta por Polars: la tabla cabe en
memoria por día (el volumen es grande para pandas entero, pequeño para Spark), y `prepare`
tarda 42 min sobre 32 jornadas con 8 procesos (ADR-004, consecuencias). Qué reabriría: que
una transformación deje de caber por día, o que `prepare` pase de un par de horas con la
captura completa.

**Qué cambiaría.** Nada; `docs/02` ya es histórico.

---

## Otras abiertas que sí figuran en el repo

Tomadas de `docs/00_tema_y_alcance.md:99-104` y `docs/07_decisiones.md:1141-1152`:

| Qué | Dónde se decide | Nota |
|---|---|---|
| Tema cerrado con el tutor | `docs/00:104` | Tuya |
| Correo al Ajuntament/EMT sobre condiciones de uso (y frecuencia de las capas 188 y 192) | `docs/00:103`; `docs/06:155-160` | La respuesta, o su ausencia, va al anexo |
| Meteorología: capa 157 sin pasar por `curar` (issue #8) ni como variable | `docs/00:99-101` | Alcance: ¿entra o se declara fuera? |
| Servido en tiempo real incremental | ADR-016; `docs/07:1141-1152` | Ver (c) |
| Cadencia de la capa 192 (5 min, fijada cuando parecía estática) | `docs/07:1141-1152` | Lo que no se captura no se recupera: decidir pronto |
| Tope del índice de trampas (45 líneas, 22 fichas, justo) | `docs/07:1141-1152` | La próxima ficha rompe `.claude/tests/test_trampas.py` |
| Qué pregunta de investigación defiendes | auditoría N3 | Ver (a) |
