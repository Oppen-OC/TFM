# TFM Big Data · Análisis del repositorio y 10 propuestas de tema

_Documento generado el 14/08/2026 a partir del repositorio `C:\Users\oppen\Code\TFM`_

---

## Paso 1 · Qué tienes montado

Tienes un esqueleto **MLOps de nodo único, batch y orientado a reproducibilidad**, no una arquitectura Big Data. El pipeline lo gobierna **DVC** (tres stages: `features → train → evaluate`, con CSV en `data/raw|processed` y el modelo serializado a `models/model.pkl`), el tracking es **MLflow local** (SQLite + `mlruns/`), y el servicio es **FastAPI → services → predict/features → config**, consumido por una UI **Streamlit** vía HTTP, todo empaquetado en Docker Compose con CI de GitHub Actions (ruff + pytest) y gestión de dependencias con `uv`.

Decisiones ya cerradas que condicionan el tema: **orquestador = DVC** (no Airflow/Prefect), **formato = CSV plano de una sola tabla**, **`features.py` compartido entre train e inferencia** (evitas train/serve skew, y eso te obliga a un feature engineering determinista, sin fugas de futuro), y **`schemas.py` asume clasificación binaria** con `prediction: int` + `probability: float`, es decir, scoring **fila a fila en línea**. Encaja de forma natural un problema **tabular supervisado, con una unidad de predicción que tenga sentido puntuar de una en una** (un municipio-día, una hora del mercado, un viaje, un paciente), alimentado por ETL batch desde APIs públicas.

> **Aviso crítico para un máster de *Big Data*:** tal cual está, el repo no acredita ninguna competencia de Big Data. DVC + MLflow + FastAPI es ingeniería de ML, no Big Data. Si defiendes esto ante un tribunal del máster que has cursado (con módulos de *Procesado de Datos en Tiempo Real*, *NoSQL*, *Herramientas de Última Generación* y *Cloud*), te van a preguntar dónde está eso. Elige un tema que te obligue a añadir **al menos uno** de: ingesta en streaming (Kafka/Redpanda), volumen real con Parquet particionado + DuckDB/Polars, o un almacén NoSQL (Mongo/Redis) en la capa de servicio. Las ideas marcadas con ⭐ lo llevan de serie.

**Dos deudas técnicas a arreglar antes de empezar** (ya documentadas en tu README): el bloque `stages:` está en `params.yaml` en vez de en `dvc.yaml`, así que `dvc repro` no ejecuta nada; y las claves `features:` / `train:` que las stages referencian como `params` no existen. Además, `xgboost` todavía no está en `pyproject.toml` (solo `scikit-learn`).

---

## Paso 2 · 10 propuestas de TFM

### 1. Predicción de horas de precio negativo y vertido renovable en el mercado eléctrico europeo

1. **Título tentativo:** *Predicción a día vista de episodios de precio negativo en el mercado diario eléctrico europeo: un pipeline reproducible con datos de ENTSO-E y variables meteorológicas.*
2. **Problema real:** las horas con precio marginal ≤ 0 €/MWh se han multiplicado en Europa desde 2023 por la penetración solar y eólica, y provocan vertido (curtailment) de renovables y pérdidas para los productores. Anticipar esas horas en la ventana de casación (antes de las 12:00 del día D-1) permite decidir paradas, cargas de baterías o consumo flexible.
3. **Aportación:** no es un forecast de precio más. Se predice un **evento operativo accionable** en el instante real en que existe la información (nada de usar generación observada, solo previsiones publicadas antes del cierre de subasta), se compara contra un baseline de persistencia y un modelo lineal, y se hace **transferencia entre países** (entrenar en España + Alemania, evaluar en Países Bajos) para probar si los drivers son estructurales. Se cierra con análisis SHAP de qué combinación de renovable prevista, demanda e interconexión dispara el evento.
4. **Datasets:**
   - [ENTSO-E Transparency Platform · API RESTful](https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html) (precios day-ahead, carga y previsión de carga, generación por tecnología, previsión eólica/solar, flujos entre fronteras). Token gratuito solicitando por email.
   - [ESIOS · Red Eléctrica, API de descarga](https://www.esios.ree.es/es/pagina/api) para el detalle español.
   - [AEMET OpenData](https://www.aemet.es/es/datos_abiertos/AEMET_OpenData) o ERA5 (Copernicus CDS) para meteorología.
5. **Encaje técnico:** el ETL es la parte cara y se ve. Ingesta paginada por rangos de fechas contra tres APIs con formatos distintos (XML de ENTSO-E, JSON de ESIOS, GRIB/NetCDF de ERA5), armonización de **husos horarios y cambios de hora** (la fuente de bugs número uno en datos de mercado), resampling entre resoluciones (ENTSO-E convive con MTU de 15 min y horaria), imputación de huecos de publicación y construcción de lags/ventanas móviles y features de calendario en `features.py`. **XGBoost: clasificación binaria** (`precio ≤ 0` en la hora h) con evaluación por PR-AUC y calibración; variante de regresión sobre el precio como estudio secundario.
6. **Dificultad: media.** **Riesgo principal:** desbalanceo de clases en España (bastantes menos horas negativas que en Alemania o Países Bajos). Mitigación: define el objetivo como "precio en el percentil 5 inferior" o mueve el foco a mercados con más eventos.

---

### 2. Alerta temprana de riesgo de incendio forestal a escala municipal

1. **Título tentativo:** *Modelo de riesgo de incendio forestal a 7 días vista con datos de EFFIS, ERA5 y cobertura del suelo: validación espacio-temporal y comparación con el índice FWI operativo.*
2. **Problema real:** los veranos de 2022-2026 han batido registros de superficie quemada en el sur de Europa. Los servicios de emergencia priorizan recursos con el FWI, un índice meteorológico que ignora combustible, orografía y presión humana. Un ranking de riesgo por municipio ayuda a preposicionar medios.
3. **Aportación:** dos cosas que casi nadie hace bien y que se defienden solas. Primera, el **muestreo de negativos**: definir explícitamente qué es un "municipio-semana sin incendio" y demostrar que la elección cambia el modelo. Segunda, **validación por bloques espacio-temporales** (dejar fuera regiones y años completos) en lugar del split aleatorio, que infla las métricas por autocorrelación. El benchmark contra el FWI oficial convierte el trabajo en una evaluación, no en un ejercicio.
4. **Datasets:**
   - [EFFIS / Copernicus · Data and services](https://forest-fire.emergency.copernicus.eu/applications/data-and-services) y [instrucciones de descarga](https://forest-fire.emergency.copernicus.eu/downloads-instructions) (áreas quemadas y eventos de incendio históricos).
   - [Fire events in EFFIS · JRC Data Catalogue](https://data.jrc.ec.europa.eu/dataset/022cdeed-159f-407d-be18-0dface69ef92).
   - ERA5-Land (Copernicus Climate Data Store) para meteorología diaria; CORINE Land Cover para combustible; densidad de población y red viaria de Eurostat/OSM para presión humana.
5. **Encaje técnico:** ETL geoespacial de verdad. Cruce de polígonos de área quemada con la malla municipal (GeoPandas), reproyecciones, agregación de rejilla ERA5 a municipio con medias ponderadas, cálculo de acumulados móviles (días sin lluvia, DMC/DC), y generación del panel municipio × semana. **XGBoost: clasificación binaria muy desbalanceada** (`scale_pos_weight`, evaluación por PR-AUC y por *precision@k* municipios, que es la métrica que le importa a un jefe de emergencias).
6. **Dificultad: alta.** **Riesgo principal:** fuga espacial y definición del negativo. Si haces split aleatorio te sale un 0.98 de AUC que no significa nada y el tribunal lo verá.

---

### 3. ⭐ Predicción de retrasos del transporte público con ingesta GTFS-Realtime en streaming

1. **Título tentativo:** *Arquitectura de ingesta en streaming de GTFS-Realtime y predicción de retrasos de llegada: construcción de un dataset abierto reproducible.*
2. **Problema real:** las apps de transporte muestran la posición del autobús pero predicen la llegada con reglas simples que fallan justo cuando importa (hora punta, incidencias). Un modelo de retraso mejora la información al viajero y permite al operador detectar tramos crónicamente degradados.
3. **Aportación:** el **dataset es parte de la aportación**. Los feeds GTFS-RT son efímeros: nadie publica el histórico. Capturando cada 30 segundos durante 3-4 meses generas un corpus de decenas de millones de observaciones que puedes publicar como artefacto reproducible. A eso se suma un análisis de **fiabilidad de servicio** (regularidad de headway, no solo retraso medio) que es lo que de verdad mide la calidad de una línea de alta frecuencia.
4. **Datasets:**
   - [MobilityDatabase](https://mobilitydatabase.org/feeds) · catálogo global de feeds GTFS y GTFS-Realtime abiertos, con API.
   - [511.org Transit Data](https://511.org/open-data/transit) (Bay Area, feeds RT abiertos y bien mantenidos) o feeds municipales españoles (EMT Madrid, EMT Valencia).
   - [Especificación GTFS-Realtime](https://developers.google.com/transit/gtfs-realtime).
5. **Encaje técnico:** aquí sí hay Big Data. Productor Python que hace polling de los feeds Protobuf → **Kafka/Redpanda** → consumidor que escribe **Parquet particionado por día/ruta** → capa de features con DuckDB o Polars. La reconstrucción de "retraso real en la parada n" a partir de `TripUpdate` y `VehiclePosition` es un problema de casado de eventos no trivial y luce en la memoria. **XGBoost: regresión** sobre segundos de retraso en la siguiente parada, más una **variante de clasificación** ("¿llegará con más de 5 minutos de retraso?") que encaja directamente con los contratos actuales de tu `schemas.py`.
6. **Dificultad: media-alta.** **Riesgo principal:** la captura tiene que empezar el día 1 o no llegas. Sin datos acumulados no hay TFM. Mitigación: arranca el colector antes de cerrar el resto del diseño y ten un feed de respaldo.

---

### 4. ⭐ Detección de comportamiento anómalo en tráfico marítimo a partir de datos AIS

1. **Título tentativo:** *Procesamiento a escala de trayectorias AIS y detección supervisada de apagones de transpondedor en el Báltico.*
2. **Problema real:** el "apagado" deliberado del AIS es el indicador operativo de trasvases ilegales, pesca no declarada y evasión de sanciones. La vigilancia marítima europea es un tema caliente desde 2024 y las autoridades trabajan con reglas fijas fácilmente evadibles.
3. **Aportación:** el volumen real, y una estrategia de **etiquetado débil** honesta: no hay ground truth de "barco haciendo algo ilegal", pero sí puedes etiquetar objetivamente un **gap de transmisión anómalo** (silencio prolongado en zona de buena cobertura, con reaparición desplazada) y predecirlo a partir del comportamiento previo. Discutir abiertamente esa limitación es exactamente el tipo de rigor que puntúa.
4. **Datasets:**
   - [Danish Maritime Authority · Download data (AIS histórico)](https://www.dma.dk/safety-at-sea/navigational-information/download-data) · ficheros diarios CSV, del orden de 1-2 GB/día sin comprimir, con años de histórico. Descarga libre, sin registro.
   - Complementos: batimetría EMODnet, zonas de fondeo y rutas de OpenSeaMap.
5. **Encaje técnico:** el ETL es el corazón. Descarga masiva → conversión a **Parquet particionado y comprimido** (reducción típica de 10-20×) → limpieza de posiciones imposibles y MMSI corruptos → **segmentación de trayectorias en viajes** → cálculo de features cinemáticas por ventana (velocidad, rumbo, aceleración, sinuosidad, distancia a costa). Todo procesable en un portátil con **DuckDB/Polars** sin cluster, lo cual en sí es un resultado defendible. **XGBoost: clasificación binaria** sobre segmentos de trayectoria.
6. **Dificultad: alta.** **Riesgo principal:** te comes el proyecto entero en la ingeniería de datos y llegas al modelo con dos semanas. Acota desde el principio: una región, un rango de un año, un tipo de buque.

---

### 5. Triaje en urgencias con auditoría de conformidad al Reglamento Europeo de IA

1. **Título tentativo:** *Predicción de ingreso hospitalario desde urgencias con MIMIC-IV-ED: calibración, equidad y documentación técnica conforme al AI Act.*
2. **Problema real:** la saturación de urgencias es estructural. Predecir en el momento del triaje qué pacientes acabarán ingresando permite activar camas antes y reducir el tiempo de estancia. Y desde agosto de 2026 los sistemas de IA sanitarios entran de lleno en las obligaciones de alto riesgo del Reglamento (UE) 2024/1689.
3. **Aportación:** el modelo predictivo es el medio, no el fin. La aportación es el **paquete de conformidad**: curvas de calibración y *decision curve analysis* en vez de solo AUC, auditoría de equidad por subgrupos con métricas de paridad, análisis de degradación temporal, y una **documentación técnica estilo Anexo IV** generada automáticamente desde los artefactos de MLflow. Eso convierte un clasificador manido en un trabajo actual y diferencial.
4. **Datasets:**
   - [MIMIC-IV-ED v2.2 · PhysioNet](https://physionet.org/content/mimic-iv-ed/2.2/) (~425.000 estancias en urgencias, gratuito pero de **acceso acreditado**: curso CITI + solicitud, entre 1 y 3 semanas).
   - [MIMIC-IV-ED Demo v2.2](https://physionet.org/content/mimic-iv-ed-demo/2.2/) · acceso abierto, 100 pacientes, sirve para desarrollar el pipeline mientras tramitas la acreditación.
   - [Calendario de aplicación del AI Act](https://artificialintelligenceact.eu/implementation-timeline/) como marco normativo.
5. **Encaje técnico:** ETL relacional sobre varias tablas (`edstays`, `triage`, `vitalsign`, `medrecon`, `diagnosis`), con el problema clave de **respetar la ventana temporal**: solo puede entrar información disponible en el momento del triaje. Es un caso de libro de fuga de datos, y controlarlo bien es defendible. **XGBoost: clasificación binaria** (ingreso sí/no), con umbral optimizado por coste asimétrico.
6. **Dificultad: media.** **Riesgo principal:** el tiempo de acreditación de PhysioNet y que el tema base está muy trillado. Sin el ángulo regulatorio y de equidad, esto es un ejercicio de clase.

---

### 6. Anticipación de superaciones de los nuevos límites europeos de calidad del aire

1. **Título tentativo:** *Predicción a 24-48 horas de superaciones de los límites de la Directiva (UE) 2024/2881 de calidad del aire: evaluación del impacto del endurecimiento normativo.*
2. **Problema real:** la nueva directiva recorta drásticamente los valores límite de PM2.5 y NO₂ con horizonte 2030. Muchas estaciones que hoy cumplen dejarán de cumplir. Las ciudades necesitan saber cuántos días de superación tendrían **con los umbrales nuevos** y poder anticiparlos para activar protocolos.
3. **Aportación:** el doble enfoque. Por un lado un modelo de aviso a 24-48 h; por otro un **análisis contrafactual** que reetiqueta el histórico con los límites nuevos y cuantifica el salto de incumplimiento por ciudad. Ese segundo bloque le da relevancia de política pública y es original respecto a la literatura estándar de predicción de contaminantes.
4. **Datasets:**
   - [OpenAQ · API v3](https://docs.openaq.org/) (clave gratuita) y su [espejo en AWS Open Data](https://registry.opendata.aws/openaq/) para descarga masiva.
   - European Environment Agency · Air Quality Download Service (series horarias validadas de todas las estaciones EEA).
   - ERA5 / AEMET para meteorología, y datos abiertos de aforos de tráfico municipales.
5. **Encaje técnico:** ETL multiestación con **series irregulares y huecos masivos** (el problema real de las redes de calidad del aire), armonización de unidades y de códigos de estación entre fuentes, features meteorológicas rezagadas y de estabilidad atmosférica, y agregación estación → ciudad. **XGBoost: clasificación binaria** de superación al día siguiente, por estación, con evaluación separada en episodios de invierno y verano.
6. **Dificultad: media.** **Riesgo principal:** las superaciones con los límites actuales son eventos raros, lo que da un desbalanceo severo. Con los límites de 2030 el problema se suaviza, y ese es justamente el argumento del trabajo.

---

### 7. Mantenimiento predictivo en aerogeneradores con datos SCADA abiertos

1. **Título tentativo:** *Detección anticipada de fallos de componente en aerogeneradores a partir de SCADA de 10 minutos: horizonte de aviso, censura y coste de la falsa alarma.*
2. **Problema real:** una parada no planificada de multiplicadora o generador cuesta decenas de miles de euros y días de indisponibilidad. El parque eólico europeo envejece y el O&M predictivo es la palanca de rentabilidad más clara del sector.
3. **Aportación:** casi toda la literatura publica un AUC y se va. Aquí el trabajo es **el horizonte de aviso**: cuantificar cómo cae el rendimiento a medida que alejas la predicción del fallo (24 h, 72 h, 7 días) y traducir el umbral de decisión a **euros** mediante una matriz de coste (falsa alarma = inspección innecesaria; falso negativo = fallo catastrófico). Añadir un análisis de deriva de concepto entre turbinas del mismo parque redondea.
4. **Datasets:**
   - Engie · La Haute Borne open data: SCADA a 10 minutos de 4 aerogeneradores, varios años, con registro de incidencias (`opendata-renewables.engie.com`).
   - EDP Open Data / Wind Turbine Fault Detection dataset (histórico del reto EDP, con fallos etiquetados por componente).
   - Complemento meteorológico con ERA5 para features de recurso eólico.
5. **Encaje técnico:** ETL de series multivariante de alta frecuencia: resampling, detección y filtrado de estados de operación no válidos (curva de potencia), construcción de la **ventana de etiquetado previa al fallo** (la decisión de diseño central), y features estadísticas por ventana móvil (media, desviación, tendencia, residuos frente a la curva de potencia esperada). **XGBoost: clasificación binaria** por turbina-ventana, con validación temporal y por turbina.
6. **Dificultad: media.** **Riesgo principal:** poquísimos eventos de fallo (decenas, no miles). Es el cuello de botella estadístico. Mitigación: agrupa componentes, usa ventanas solapadas y sé explícito sobre la incertidumbre de las métricas.

---

### 8. ⭐ Predicción de picos de volatilidad en criptomercados a partir del libro de órdenes en tiempo real

1. **Título tentativo:** *Ingesta en streaming de microestructura de mercado y predicción de picos de volatilidad a corto plazo: un enfoque de gestión de riesgo, no de generación de alfa.*
2. **Problema real:** los mercados cripto operan 24/7 y sufren saltos de volatilidad que disparan liquidaciones en cascada. Anticipar un pico de volatilidad a 15 minutos vista sirve para ajustar tamaños de posición y márgenes, un problema de riesgo real para exchanges y creadores de mercado.
3. **Aportación:** el encuadre. **No se predice la dirección del precio** (camino directo a que el tribunal te desmonte con la hipótesis de eficiencia), sino la **magnitud** de la volatilidad, que es persistente y sí predecible. Las features de microestructura (desequilibrio de flujo de órdenes, profundidad del libro, tasa de cancelación) rara vez se explotan en TFMs porque exigen capturar el stream, y la evaluación es **walk-forward estricta** con baseline GARCH/HAR-RV, no un split aleatorio.
4. **Datasets:**
   - Binance WebSocket API (`stream.binance.com`): trades y actualizaciones de libro de órdenes en tiempo real, sin coste ni autenticación para datos públicos de mercado.
   - Binance Public Data (`data.binance.vision`): histórico de klines y trades agregados en CSV, para bootstrap y validación.
   - Complemento opcional: métricas on-chain abiertas (Blockchair, Etherscan API).
5. **Encaje técnico:** cliente WebSocket → **Kafka/Redpanda** → escritura a Parquet particionado por símbolo/hora; agregación de eventos a barras de 1 minuto y cálculo de volatilidad realizada; features de microestructura por ventana. Aquí también encaja **Redis o MongoDB** como almacén del estado del libro, cubriendo el módulo de NoSQL. **XGBoost: clasificación binaria** ("¿la volatilidad realizada de los próximos 15 min superará su percentil 90 histórico?"), con regresión sobre log-volatilidad como comparación.
6. **Dificultad: media-alta.** **Riesgo principal:** escepticismo del tribunal ante cualquier cosa que huela a predicción de mercados. Se neutraliza siendo explícito desde la introducción: el objetivo es riesgo y calibración, no rentabilidad, y no se presenta ningún backtest de trading.

---

### 9. Predicción de disponibilidad de puntos de recarga de vehículo eléctrico

1. **Título tentativo:** *Predicción de ocupación de infraestructura de recarga de vehículo eléctrico a partir de datos abiertos multi-operador.*
2. **Problema real:** la "ansiedad de recarga" es hoy más de disponibilidad que de autonomía: el conductor llega y el cargador está ocupado o averiado. El reglamento AFIR obliga a los operadores europeos a publicar datos estáticos y dinámicos de disponibilidad, así que la materia prima existe y está creciendo.
3. **Aportación:** trabajo de **fusión multi-operador**. Cada red publica con su propio esquema, granularidad y fiabilidad; construir un histórico armonizado y demostrar que la ocupación se predice mejor con contexto (día, meteorología, eventos, ocupación de cargadores vecinos) que con el perfil horario medio es un resultado concreto y útil. Se puede cerrar con un mapa de "desiertos de recarga" por franja horaria.
4. **Datasets:**
   - [Open Charge Map · API](https://openchargemap.org/site/develop/api) · inventario global de puntos de recarga, clave gratuita.
   - Datos dinámicos AFIR de operadores y portales nacionales (por ejemplo el Nationaal Laadpalen Register neerlandés, o los portales de datos abiertos de ayuntamientos españoles).
   - Meteorología (AEMET/ERA5) y calendario de eventos locales.
5. **Encaje técnico:** el histórico **hay que construirlo por polling** (snapshot cada 5-10 min durante meses), lo que reproduce el patrón de la idea 3 con menor volumen. ETL de deduplicación e identidad de puntos entre catálogos (mismo cargador, distinto id según fuente), reconstrucción de sesiones de ocupación a partir de cambios de estado, y features de vecindario espacial. **XGBoost: clasificación binaria** ("¿estará ocupado el punto X dentro de 30 minutos?").
6. **Dificultad: media.** **Riesgo principal:** la cobertura de datos dinámicos abiertos es desigual por país; valida la disponibilidad real en tu zona objetivo **antes** de comprometerte con el tema.

---

### 10. Estimación de rendimiento agrícola con teledetección y clima

1. **Título tentativo:** *Predicción intraestacional de rendimiento de cultivo herbáceo a escala regional combinando series de índices de vegetación Sentinel-2, reanálisis climático y estadística agraria.*
2. **Problema real:** la seguridad alimentaria y los mercados de materias primas dependen de estimar la cosecha antes de la cosecha. Las sequías recurrentes en el sur de Europa han vuelto crítico anticipar caídas de rendimiento con meses de antelación.
3. **Aportación:** la **curva de anticipación**: cuantificar mes a mes cuánta señal aporta la teledetección frente a un baseline climatológico, y determinar la fecha más temprana en la que la predicción ya es útil. Es una pregunta de valor operativo, no un simple R².
4. **Datasets:**
   - Copernicus Data Space Ecosystem (`dataspace.copernicus.eu`) para Sentinel-2 / índices de vegetación; alternativa ligera vía Google Earth Engine o MODIS NDVI.
   - ERA5-Land (Copernicus Climate Data Store) para variables agroclimáticas.
   - Eurostat *Crop production* y JRC MARS para los rendimientos regionales de referencia (variable objetivo).
   - CORINE Land Cover / mapas de cultivo para enmascarar píxeles no agrícolas.
5. **Encaje técnico:** ETL geoespacial pesado: descarga por teselas, enmascarado de nubes, cálculo de NDVI/EVI, **agregación de píxel a región NUTS2/NUTS3** con máscara de cultivo, y construcción de perfiles fenológicos por temporada. **XGBoost: regresión** sobre toneladas/hectárea (requiere cambiar `schemas.py` a `prediction: float`), con validación *leave-one-year-out*.
6. **Dificultad: alta.** **Riesgo principal:** pocas observaciones en la variable objetivo (una por región y año: del orden de cientos de filas), lo que limita mucho a XGBoost. Mitigación: bajar a NUTS3, ampliar el número de países y años, o cambiar el objetivo a anomalía relativa de rendimiento.

---

## Paso 3 · Recomendación

**Las tres que defenderías mejor, en este orden:**

**1) Idea 3 · Retrasos de transporte público con GTFS-Realtime en streaming.** Es la única de la lista que activa a la vez el módulo de *Procesado de Datos en Tiempo Real*, el de arquitecturas Big Data y el de ML, que es exactamente lo que un tribunal de este máster quiere ver. El dataset que construyes es en sí una aportación publicable, el dominio es comprensible sin explicaciones y las métricas se traducen a algo que cualquiera entiende ("el usuario espera 4 minutos menos de lo que cree"). La contrapartida es de calendario, no técnica: el colector tiene que estar corriendo en semana 1.

**2) Idea 1 · Precios negativos en el mercado eléctrico.** La más segura de las tres. Datos abiertos, estables, bien documentados y con volumen suficiente si cruzas varios países a resolución de 15 minutos. El ETL tiene dificultad real y visible (tres fuentes heterogéneas, husos horarios, resoluciones mixtas), el problema es de máxima actualidad en el sector energético español, y el diseño "solo información disponible antes del cierre de subasta" te da un argumento metodológico sólido frente a la pregunta inevitable de "¿esto no tiene fuga de datos?". Si quieres minimizar riesgo de no terminar, esta es tu opción.

**3) Idea 4 · Anomalías en tráfico marítimo AIS.** La que más impresiona en la memoria si la sacas adelante: cientos de gigabytes procesados sin infraestructura de pago, con Parquet y DuckDB, es la demostración más limpia de competencia en Big Data de toda la lista, y el dominio (vigilancia marítima, sanciones) es geopolíticamente actual. La incluyo en tercer lugar y no en primero porque el riesgo de agotar los cinco meses en ingeniería de datos es real, y porque el etiquetado débil te obliga a defender una hipótesis discutible.

**Combinación óptima si quieres cubrirte:** empieza por la **idea 1** como núcleo (bajo riesgo, entregable garantizado) y añade la capa de streaming de la **idea 3** aplicada a la ingesta de datos de mercado casi en tiempo real. Consigues el sello Big Data sin depender de que una captura de meses salga perfecta.

**Descartaría** para un tribunal exigente: la 5 sin el ángulo regulatorio (demasiado trillada), la 10 (el número de observaciones no justifica XGBoost) y la 8 si no eres muy disciplinado con el encuadre de riesgo frente a rentabilidad.

---

## Anexo · Cambios que necesita el repo, elijas lo que elijas

1. Mover el bloque `stages:` de `params.yaml` a `dvc.yaml` y dejar en `params.yaml` los hiperparámetros bajo `features:` y `train:`. Hoy `dvc repro` no hace nada.
2. `uv add xgboost` (no está en las dependencias) y `uv add shap` para la parte de interpretabilidad.
3. Si eliges regresión (ideas 3 y 10), ajustar `PredictResponse` en `schemas.py`: `prediction: float` y eliminar `probability`.
4. Añadir un stage `ingest` previo a `features` en `dvc.yaml` para que la descarga desde las APIs quede dentro del pipeline reproducible y no en un notebook suelto.
5. Cambiar CSV por **Parquet** en `data/processed/` en cuanto pases de unos pocos millones de filas. Es un cambio de una línea y una diferencia de orden de magnitud en tiempos.
6. Para las ideas con streaming, añadir un servicio `redpanda` (o `kafka`) a `docker-compose.yml` y un módulo `src/project/ingest/` con productor y consumidor, respetando la regla de dependencias que ya tienes documentada en `CLAUDE.md`.

---

## Fuentes

- [ENTSO-E Transparency Platform · Restful API User Guide](https://transparency.entsoe.eu/content/static_content/Static%20content/web%20api/Guide.html)
- [ENTSO-E · Electricity Market Transparency](https://www.entsoe.eu/data/transparency-platform/)
- [ESIOS · API para descarga de información (Red Eléctrica)](https://www.esios.ree.es/es/pagina/api)
- [AEMET OpenData](https://www.aemet.es/es/datos_abiertos/AEMET_OpenData)
- [EFFIS · Data and services (Copernicus)](https://forest-fire.emergency.copernicus.eu/applications/data-and-services)
- [EFFIS · Downloads Instructions](https://forest-fire.emergency.copernicus.eu/downloads-instructions)
- [Fire events in EFFIS · JRC Data Catalogue](https://data.jrc.ec.europa.eu/dataset/022cdeed-159f-407d-be18-0dface69ef92)
- [MobilityDatabase · Transit Feeds](https://mobilitydatabase.org/feeds)
- [511.org · Transit Data](https://511.org/open-data/transit)
- [GTFS Realtime Overview · Google for Developers](https://developers.google.com/transit/gtfs-realtime)
- [Danish Maritime Authority · Download data (AIS)](https://www.dma.dk/safety-at-sea/navigational-information/download-data)
- [MIMIC-IV-ED v2.2 · PhysioNet](https://physionet.org/content/mimic-iv-ed/2.2/)
- [MIMIC-IV-ED Demo v2.2 · PhysioNet](https://physionet.org/content/mimic-iv-ed-demo/2.2/)
- [EU AI Act · Implementation Timeline](https://artificialintelligenceact.eu/implementation-timeline/)
- [OpenAQ API Docs](https://docs.openaq.org/)
- [OpenAQ · Registry of Open Data on AWS](https://registry.opendata.aws/openaq/)
