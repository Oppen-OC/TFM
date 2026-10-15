# 00 · Tema, alcance y decisiones tomadas

_Última actualización: 15/10/2026. Este archivo es el punto de entrada del
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

**Fuera:**

- Predicción a nivel de red completa u optimización de horarios.
- Deep learning sobre secuencias (se menciona como trabajo futuro).
- Cualquier dato privado o convenio con la EMT.
- Metrovalencia como dato observado.
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
- [ ] Prueba del 07 al 19/10: captura en curso; se evalúa una vez a partir del
  21/10 (ADR-024, nota del 11/10)
- [ ] Servido: `services/model_service.py` vacío y `api/schemas.py` placeholder
- [ ] `shap` sin añadir; meteorología sin fuente capturada
  (`features.incluir_meteo`)
- [ ] Correo al Ajuntament / EMT sobre condiciones de uso (para el anexo)
- [ ] Tema cerrado con el tutor

## Lo urgente

**Cerrar la prueba sin huecos.** Ninguna fuente guarda histórico: lo que no se
capture del 07 al 19/10 no se recupera, y es la única prueba del ADR-024.

- **No redesplegar el colector de la Pi antes del 20/10**: un reinicio fallido
  dejaría un hueco en la prueba (ADR-024, nota del 11/10).
- **A partir del 21/10:** traer la captura con `deploy_pi/pull_data.sh`, nunca
  con `rsync` sobre `data/raw/` (trampa 016); `dvc repro`; contrastar el horario
  con `analysis/comparar_gtfs`; y ejecutar las comparaciones **una sola vez**.
- **Después:** redesplegar el colector con la captura del GTFS, que la Pi no
  guarda desde el 06/10 (bitácora 051).

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| La captura se cae o se degrada durante meses | media | monitorización desde el día 1; medir en la prueba de 24 h; reintentos y payload crudo siempre guardado |
| El map-matching consume todo el tiempo | resuelto | casa a 4 m de mediana (bitácora 016); Renfe queda como respaldo (ver *Plan B*) |
| El endpoint de Renfe cambia o desaparece | media | no documentado oficialmente; se guarda payload crudo para reprocesar |
| El GTFS cambia y corrompe etiquetas antiguas | media | descargar el GTFS semanalmente y versionarlo con DVC; etiquetar cada captura con el GTFS vigente en esa fecha |
| Intercambios de identidad en el tracking | media | asignación húngara + predicción de movimiento (100 % vs 97,8 % del vecino más cercano en el autotest) |
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
- [`../CLAUDE.md`](../CLAUDE.md) — reglas de arquitectura del repo.
