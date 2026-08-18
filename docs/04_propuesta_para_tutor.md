# Propuesta de TFM

**Daniel Alpeñes** · Máster en Big Data · agosto de 2026

---

## Título

Fusión de posiciones GPS de flota y estado del tráfico urbano en tiempo real
para la predicción de retrasos del transporte público: el caso de la EMT de
València.

## Pregunta de investigación

> ¿Cuánta información anticipatoria sobre el retraso del autobús urbano contiene
> el estado del tráfico que el Ayuntamiento de València ya publica en abierto, y
> hasta qué horizonte temporal se mantiene esa señal?

La pregunta es falsable: puede responderse que la aportación es nula. Ese
resultado, bien medido, también es un resultado.

## Motivación

La EMT de València publica la posición GPS de su flota en tiempo real, y el
Ajuntament publica simultáneamente el estado de congestión de 446 tramos viarios
y la intensidad medida en 394. **Las dos fuentes nunca se han cruzado.** La
literatura sobre predicción de retrasos de autobús se apoya casi siempre en
feeds GTFS-Realtime que ya entregan el retraso calculado, y rara vez incorpora
estado de tráfico medido de forma independiente.

Anticipar el retraso permite mejorar la información al viajero y detectar tramos
crónicamente degradados, pero el interés del trabajo no es construir un predictor
más: es **cuantificar el valor marginal de una fuente de datos abierta y
desaprovechada**.

## Aportaciones

**1. Aportación de recurso.** No existe un conjunto de datos de trayectorias de
la EMT etiquetado con retraso y sincronizado con el estado del tráfico. Y no
puede reconstruirse retroactivamente: la fuente municipal trunca y reinserta su
tabla en cada refresco, sin conservar histórico (verificado empíricamente). El
trabajo genera ese corpus mediante captura continua, y lo publica como artefacto
reproducible.

**2. Aportación metodológica.** La fuente no publica identificador de vehículo,
`trip_id` ni retraso: la etiqueta hay que derivarla. El trabajo desarrolla y
evalúa un procedimiento de reconstrucción de identidad de vehículo entre
snapshots (asignación óptima con modelo de movimiento), segmentación de viajes,
proyección sobre la traza del GTFS e interpolación del paso por parada. Sobre
flota simulada con verdad-terreno conocida, el emparejamiento por vecino más
cercano recupera el 97,8 % de las identidades y el método con predicción de
movimiento el 100 %.

**3. Aportación empírica.** Cuantificación, mediante ablación controlada, de la
mejora que aportan las variables de tráfico sobre un modelo equivalente sin
ellas, y de cómo se degrada esa mejora al alejar el horizonte de predicción.

## Diseño experimental

**Variable objetivo:** segundos de retraso en la siguiente parada. Variante de
clasificación binaria (`retraso > 5 min`) para el servicio en línea.

**Modelo:** XGBoost (regresión y clasificación), con interpretación por SHAP.

**Baselines de comparación**, en orden creciente de exigencia:

1. Horario teórico del GTFS (predecir retraso = 0).
2. Persistencia (el retraso actual del vehículo se mantiene).
3. **Modelo idéntico sin features de tráfico.** Esta es la comparación que
   responde a la pregunta de investigación; las dos anteriores solo acreditan
   que el modelo es competente.

**Validación:** división temporal estricta (nunca aleatoria: con series de
posiciones, un split aleatorio filtra el futuro). Evaluación separada por franja
horaria y por tipología de corredor.

**Validación externa del etiquetado.** Las etiquetas de retraso de la EMT son
derivadas, no observadas, y no existe verdad-terreno para ellas. Para acotar ese
riesgo se aprovecha que Renfe Cercanías publica **simultáneamente posición y
retraso oficial**: se aplica el mismo procedimiento de etiquetado a las
posiciones de Renfe, ignorando su campo `retrasoMin`, y se mide el error con el
que se recupera el valor oficial. Esto calibra el método de etiquetado contra
una referencia real antes de aplicarlo a la EMT.

## Datos

Todas las fuentes son abiertas, sin clave y verificadas en vivo (15/08/2026).

| Fuente | Contenido | Cadencia medida |
|---|---|---|
| EMT · `Seguimiento_EMT/384` | posición GPS de la flota | refresco 29,3 s |
| Tráfico · capas `192` y `188` | congestión (446 tramos) e intensidad (394) | 60 s / 5 min |
| Renfe Cercanías · núcleo 40 | posición + retraso oficial | 12 s de latencia |
| GTFS estático EMT | rutas, paradas y horarios teóricos | semanal |
| AEMET | precipitación y temperatura | horaria |

**Volumen proyectado: ~145 millones de filas en tres meses de captura.**
Inviable en CSV sobre un equipo personal; tratable con Parquet particionado y
DuckDB. La demostración de esa diferencia forma parte del trabajo.

## Arquitectura

Ingesta asíncrona → Kafka/Redpanda → Parquet particionado → ETL de tracking y
etiquetado → DVC (`prepare → features → train → evaluate`) → MLflow → modelo
XGBoost servido por FastAPI y consumido por una interfaz Streamlit.

La ingesta queda deliberadamente fuera del pipeline DVC: capturar un flujo en
vivo no es idempotente ni reejecutable.

## Alcance

**Incluido:** 4-6 corredores con perfiles contrastados (carril bus segregado,
travesía central saturada, periférico), un único horizonte de predicción en la
fase principal, ablación de tráfico, validación cruzada con Renfe y demostrador
funcional de punta a punta.

**Excluido:** optimización de horarios, predicción a escala de red completa,
comparación con arquitecturas de aprendizaje profundo (se deja como trabajo
futuro) y cualquier dato privado o convenio con el operador.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| La captura debe sostenerse durante meses y no hay histórico recuperable | prueba de carga de 24 h antes de cerrar el tema; payload crudo siempre persistido; monitorización desde el día 1 |
| El etiquetado por map-matching consume el calendario | Renfe Cercanías entrega retraso ya calculado e identidad estable: dataset alternativo entrenable en dos semanas |
| El resultado de la ablación es nulo | un resultado negativo con intervalo de confianza responde igualmente a la pregunta de investigación |
| Condiciones de uso de los datos no publicadas | consulta formal al Ajuntament y a EMT, documentada en anexo |

## Calendario orientativo

| Fase | Duración | Hito |
|---|---|---|
| Captura continua | desde la semana 1, en paralelo a todo | corpus creciente |
| ETL de tracking y etiquetado | 6 semanas | dataset etiquetado v1 |
| Validación del etiquetado con Renfe | 2 semanas | error de calibración medido |
| Modelado y ablación | 5 semanas | curva de anticipación |
| Servicio y demostrador | 3 semanas | API + UI funcionando |
| Redacción | 4 semanas | memoria |

## Estado a fecha de esta propuesta

Fuentes verificadas en vivo, prototipo de ingesta implementado y probado
(24 comprobaciones automáticas), pipeline DVC definido y esqueleto de servicio en
pie. Pendiente: prueba de captura de 24 horas y validación del alcance con el
tutor.

Documentación técnica completa en `docs/`.
