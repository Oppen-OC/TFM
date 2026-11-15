# 00 · Tema, alcance y decisiones tomadas

_Última actualización: 13/11/2026. Este archivo es el punto de entrada del
trabajo: si vuelves al proyecto después de tres semanas, o si abres una sesión
nueva de Claude Code en VS Code, empieza aquí._

---

## Tema

**Predicción de retrasos del transporte público urbano de València mediante
fusión de posiciones GPS de flota y estado del tráfico en tiempo real.**

Título de trabajo para la memoria: *Fusión de posiciones GPS de flota y estado
de tráfico urbano en tiempo real para la predicción de retrasos del transporte
público: el caso de la EMT de València.*

## Pregunta de investigación

¿Cuánto del retraso de un autobús urbano se explica por la congestión medida
aguas abajo de su ruta, y con cuánta antelación puede anticiparse?

## Pilares de defensa

1. **La etiqueta no existe en la fuente.** La capa de la EMT publica posición,
   línea y sentido, pero ni `trip_id`, ni identificador de vehículo, ni retraso.
   Construirla exige tracking, segmentación de viajes, map-matching sobre la
   traza del GTFS e interpolación del paso por parada. Ese es el ETL que
   convierte esto en un TFM y no en un `pd.read_csv`.
2. **La fusión con tráfico no está hecha.** Existen decenas de trabajos que
   predicen retrasos con feeds GTFS-Realtime genéricos. Cruzar posiciones de
   flota con el estado de congestión de los 410 tramos del propio Ayuntamiento,
   en el mismo instante, no está publicado para València.
3. **El volumen pide formato columnar, no infraestructura distribuida.** ~32 M
   de filas en 57 días de captura, ~56 M a tres meses, 433 MB en Parquet
   (bitácora 056; la proyección inicial de ~145 M suponía sondear el tráfico
   cada minuto). En Parquet particionado + DuckDB se trata en un portátil
   sin broker (ADR-016). Esa demostración es la competencia de datos que el
   esqueleto MLOps original (DVC + MLflow + FastAPI) no acreditaba por sí solo.

## Decisiones cerradas

Registro completo, con consecuencias y condiciones de reapertura, en
[`07_decisiones.md`](07_decisiones.md). Resumen: DVC como orquestador, ingesta
fuera de DVC, Parquet + zstd, DuckDB, XGBoost, split temporal,
Metrovalencia descartado, Renfe capturado desde el día 1 como plan B.

## Alcance

**Dentro:**

- Captura continua de EMT, tráfico (estado e intensidad), Renfe Cercanías núcleo
  40 y Valenbisi.
- Reconstrucción de identidad de vehículo y trayectorias.
- Etiquetado de retraso por paso por parada contra el GTFS estático.
- Modelo XGBoost de regresión + variante de clasificación.
- Servido por FastAPI, consumido por Streamlit.
- Demo en vivo por parada, sobre el crudo que captura el PC, sin broker (ADR-016).
  Es una demostración: **no es un resultado del TFM**.

**Fuera:**

- Predicción a nivel de red completa u optimización de horarios.
- Deep learning sobre secuencias (se menciona como trabajo futuro).
- Cualquier dato privado o convenio con la EMT.
- Metrovalencia como dato observado.
- Servido en tiempo real como resultado: nada de lo que salga en la demo se cita
  como cifra, y sin capa 192 ni broker.
- Renfe Cercanías como validación cruzada entre modos: se captura como respaldo
  (ver *Plan B*) y queda como trabajo futuro.

---

## Estado actual

El detalle, con sus bitácoras, está en la sección *Estado* de
[`../CLAUDE.md`](../CLAUDE.md); aquí va el resumen.

- [x] Tema elegido y fuentes verificadas en vivo (15/08/2026)
- [x] Captura continua desde el 15/08: 31,7 M de filas al 13/10 (bitácora 056),
  con los huecos del geoportal (021) y del disco de la Pi (054) declarados
- [x] GTFS de la EMT en varias versiones, elegidas por día de servicio (ADR-014)
- [x] Tracking, map-matching y etiquetado de punta a punta (`tracking.py`,
  `mapmatching.py`, `etiquetado.py`, `prepare.py`)
- [x] Features, entrenamiento y evaluación con baselines: el modelo v2 bate a la
  persistencia más el sesgo del tramo, de 2 a 14 min por delante un 3-4 %
  (bitácoras 043, 045-047)
- [x] Capa 192 y clasificador de más de 5 min, con su protocolo fijado antes de
  la prueba (ADR-024, ADR-025)
- [x] Prueba del 07 al 19/10, evaluada una sola vez sobre 12 días (el 13/10 cae
  por el criterio de día útil, trampa 018): la capa 192 no aporta en la primaria
  y la v2 se confirma, −3,37 s frente al listón (ADR-024, bitácora 057)
- [x] Servido por API: `services/model_service.py` carga la regresión y el
  clasificador de cada horizonte, y `api/` los expone
- [x] SHAP sobre la prueba (`explicar.py`)
- [x] Demo en vivo por parada, que no es un resultado (bitácora 064)
- [ ] Meteorología: la capa 157 se captura desde el 09/11, pero aún no pasa por
  `curar` (issue #8) ni es variable del modelo (`features.incluir_meteo` sigue
  en `false`)
- [ ] Servido en tiempo real incremental (ADR-016)
- [ ] Correo al Ajuntament / EMT sobre condiciones de uso (para el anexo)
- [ ] Tema cerrado con el tutor

## Lo urgente

**La prueba está cerrada.** La captura del 07 al 19/10 se evaluó una vez
(ADR-024, bitácora 057); todo análisis posterior sobre ella es exploratorio.

- **La captura no se para.** Ninguna fuente guarda histórico. Traerla siempre
  con `deploy_pi/pull_data.sh`, nunca con `rsync` sobre `data/raw/` (trampa 016).
- **La Pi se redesplegó el 09/11** (servicio arrancado a las 10:30 UTC, bitácora
  063) con la rama `raspberry`, cuyo colector guarda cada versión nueva del GTFS
  y captura la capa 157. Entre el 06/10 y esa fecha la Pi no guardó el GTFS
  (bitácora 051): las versiones de ese tramo son las que se bajaron a mano.
- El resto de lo pendiente son las casillas sin marcar de *Estado actual*.

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| La captura se cae o se degrada durante meses | media | `collect --status` (no dice VIVO con una fuente callada); reintentos y payload crudo siempre guardado; huecos medidos y declarados (bitácoras 021, 044, 054) |
| El map-matching consume todo el tiempo | resuelto | casa a 4 m de mediana (bitácora 016); Renfe queda como respaldo (ver *Plan B*) |
| El endpoint de Renfe cambia o desaparece | media | no documentado oficialmente; se guarda payload crudo para reprocesar |
| El GTFS cambia y corrompe etiquetas antiguas | media | descargar el GTFS semanalmente y versionarlo con DVC; etiquetar cada captura con el GTFS vigente en esa fecha |
| Intercambios de identidad en el tracking | media | asignación húngara + predicción de movimiento: 0 saltos de identidad frente a 4 del vecino más cercano en la flota simulada (100 % frente a 97,8 % de posiciones, bitácora 001). Con paradas y giros reales produce 2-4 saltos: defecto conocido, `test_tracking_realismo.py` (`xfail`) |
| Convención horaria de la EMT | alta si se ignora | **la fuente alterna UTC y local naive entre sondeos**, no hay desfase fijo: se resuelve por snapshot en `resolver_convencion()`. Ficha [002](../.claude/trampas/002-emt-alterna-convencion-horaria.md) |

## Plan B

Si en diciembre el etiquetado de la EMT no estaba resuelto, se pivotaba a
**Renfe Cercanías del núcleo 40**: `retrasoMin` viene ya calculado y `tripId` es
estable. La condición no se ha dado: el etiquetado de la EMT funciona de punta a
punta (bitácora 024). Renfe se sigue capturando como respaldo —el crudo cuesta
lo mismo y no se puede recuperar después— y su uso como validación cruzada
entre modos queda como trabajo futuro.

---

## Documentos relacionados

- [`01_viabilidad_fuentes_valencia.md`](01_viabilidad_fuentes_valencia.md) —
  exploración en vivo de los endpoints, esquemas, latencias medidas, trampas de
  los datos y qué extraer de cada fuente. **Lectura obligatoria antes de tocar
  la ingesta.**
- [`02_exploracion_de_temas.md`](02_exploracion_de_temas.md) — las diez
  propuestas evaluadas y por qué se descartaron las otras nueve. Material para
  la sección de justificación del tema en la memoria.
- [`03_fuentes_valencia_primer_barrido.md`](03_fuentes_valencia_primer_barrido.md) —
  primer barrido de fuentes, anterior a la exploración en vivo. Superado por el
  01; se conserva como antecedente.
- [`04_propuesta_para_tutor.md`](04_propuesta_para_tutor.md) — la propuesta de
  agosto, tal como se envió.
- [`05_hallazgos_primera_captura.md`](05_hallazgos_primera_captura.md) — calidad
  del dato medida sobre la primera captura real.
- [`06_veredicto_capas_trafico.md`](06_veredicto_capas_trafico.md) — las capas de
  tráfico en agosto, y qué quedó de ese veredicto con el corpus entero.
- [`07_decisiones.md`](07_decisiones.md) — registro canónico de decisiones (ADR).
- [`09_gtfs_emt.md`](09_gtfs_emt.md) — qué trae el GTFS estático de la EMT y para
  qué sirve cada fichero.
- [`11_auditoria_tests.md`](11_auditoria_tests.md) — auditoría de validez de los
  tests.
- [`12_flujo_de_datos.html`](12_flujo_de_datos.html) — diagrama del flujo de datos.
- [`bitacora/README.md`](bitacora/README.md) — bitácora de hallazgos: lo medido,
  lo descartado y lo aceptado, con el comando que reproduce cada cifra.
- [`../CLAUDE.md`](../CLAUDE.md) — reglas de arquitectura del repo.
