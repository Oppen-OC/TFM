# 00 · Tema, alcance y decisiones tomadas

_Última actualización: 15/08/2026. Este archivo es el punto de entrada del
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

## Por qué es defendible

1. **La etiqueta no existe en la fuente.** La capa de la EMT publica posición,
   línea y sentido, pero ni `trip_id`, ni identificador de vehículo, ni retraso.
   Construirla exige tracking, segmentación de viajes, map-matching sobre la
   traza del GTFS e interpolación del paso por parada. Ese es el ETL que
   convierte esto en un TFM y no en un `pd.read_csv`.
2. **La fusión con tráfico no está hecha.** Existen decenas de trabajos que
   predicen retrasos con feeds GTFS-Realtime genéricos. Cruzar posiciones de
   flota con el estado de congestión de 446 tramos del propio Ayuntamiento, en
   el mismo instante, no está publicado para València.
3. **El volumen es real.** ~145 M de filas en tres meses de captura. En CSV es
   inmanejable en un portátil; en Parquet particionado + DuckDB, sí. Esa
   demostración es la competencia de Big Data que el esqueleto MLOps original
   (DVC + MLflow + FastAPI) no acreditaba por sí solo.

## Decisiones cerradas

Registro completo, con consecuencias y condiciones de reapertura, en
[`07_decisiones.md`](07_decisiones.md). Resumen: DVC como orquestador, ingesta
fuera de DVC, Parquet + zstd, DuckDB/Polars, XGBoost, split temporal,
Metrovalencia descartado, Renfe capturado desde el día 1 como plan B.

## Alcance

**Dentro:**

- Captura continua de EMT, tráfico (estado e intensidad), Renfe Cercanías núcleo
  40 y Valenbisi.
- Reconstrucción de identidad de vehículo y trayectorias.
- Etiquetado de retraso por paso por parada contra el GTFS estático.
- Modelo XGBoost de regresión + variante de clasificación.
- Servido por FastAPI, consumido por Streamlit.
- Renfe Cercanías como validación cruzada entre modos.

**Fuera:**

- Predicción a nivel de red completa u optimización de horarios.
- Deep learning sobre secuencias (se menciona como trabajo futuro).
- Cualquier dato privado o convenio con la EMT.
- Metrovalencia como dato observado.

---

## Estado actual

- [x] Tema elegido y fuentes verificadas en vivo (15/08/2026)
- [x] Demostrador de exploración funcionando (`demo/`, 24 tests en verde)
- [x] Bug de DVC resuelto: stages en `dvc.yaml`, hiperparámetros en `params.yaml`
- [ ] **Captura de 24 h ejecutada y medida** ← lo siguiente, y es urgente
- [ ] Dependencias añadidas: `xgboost shap httpx scipy pyarrow duckdb`
- [ ] `src/project/prepare.py` — tracking + etiquetado (portar desde `demo/track.py`)
- [ ] `src/project/features.py` — features de bus, tráfico, calendario y meteo
- [ ] `src/project/train.py` — XGBoost + MLflow
- [ ] `src/project/evaluate.py` — métricas + baselines
- [ ] `schemas.py` — sustituir los campos placeholder por los reales
- [ ] Correo al Ajuntament / EMT sobre condiciones de uso (para el anexo)
- [ ] Tema cerrado con el tutor

## Lo urgente

**Lanzar el colector.** Ninguna de las fuentes guarda histórico: la tabla de la
EMT se trunca y se reinserta entera en cada refresco, y una consulta por gids
anteriores devuelve cero filas. Lo que no se capture hoy no se puede recuperar
nunca.

```powershell
python demo\collect.py --minutes 1440
```

Con 24 horas mides el ciclo diario completo: hora punta, valle, servicio
nocturno, tamaño real en disco, tasa de errores y estabilidad del servidor
municipal. **Descubrir en enero que la captura no aguanta no tiene arreglo.**

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| La captura se cae o se degrada durante meses | media | monitorización desde el día 1; medir en la prueba de 24 h; reintentos y payload crudo siempre guardado |
| El map-matching consume todo el tiempo | media-alta | Renfe Cercanías como plan B: trae `retrasoMin` ya calculado y `tripId` estable |
| El endpoint de Renfe cambia o desaparece | media | no documentado oficialmente; se guarda payload crudo para reprocesar |
| El GTFS cambia y corrompe etiquetas antiguas | media | descargar el GTFS semanalmente y versionarlo con DVC; etiquetar cada captura con el GTFS vigente en esa fecha |
| Intercambios de identidad en el tracking | media | asignación húngara + predicción de movimiento (100 % vs 97,8 % del vecino más cercano en el autotest) |
| Convención horaria de la EMT | alta si se ignora | **la fuente alterna UTC y local naive entre sondeos**, no hay desfase fijo: se resuelve por snapshot en `resolver_convencion()`. Ficha [002](../.claude/trampas/002-emt-alterna-convencion-horaria.md) |

## Plan B

Si en diciembre el etiquetado de la EMT no está resuelto, se pivota a **Renfe
Cercanías del núcleo 40**: `retrasoMin` viene ya calculado y `tripId` es estable,
así que hay dataset etiquetado y modelo entrenable en dos semanas. Por eso el
colector captura las dos fuentes desde el primer día: cuesta lo mismo.

---

## Documentos relacionados

- [`01_viabilidad_fuentes_valencia.md`](01_viabilidad_fuentes_valencia.md) —
  exploración en vivo de los endpoints, esquemas, latencias medidas, trampas de
  los datos y qué extraer de cada fuente. **Lectura obligatoria antes de tocar
  la ingesta.**
- [`02_exploracion_de_temas.md`](02_exploracion_de_temas.md) — las diez
  propuestas evaluadas y por qué se descartaron las otras nueve. Material para
  la sección de justificación del tema en la memoria.
- [`../demo/README.md`](../demo/README.md) — cómo usar el demostrador.
- [`../CLAUDE.md`](../CLAUDE.md) — reglas de arquitectura del repo.
