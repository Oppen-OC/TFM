# TFM — Daniel Alpeñes

**Predicción de retrasos del transporte público urbano de València mediante fusión
de posiciones GPS de flota y estado del tráfico en tiempo real.**

Pipeline ML end-to-end: captura continua en tiempo real de datos abiertos municipales,
preparación y entrenamiento reproducibles (DVC + MLflow), modelo XGBoost servido
por FastAPI y consumido por una UI Streamlit.

---

## El problema

Las apps de transporte estiman la llegada del autobús con reglas simples que
fallan justo cuando importa: hora punta, lluvia, incidencias. La EMT de València
publica la posición GPS de su flota en tiempo real, y el Ajuntament publica el
estado de congestión de 410 tramos viarios, pero **nadie ha cruzado las dos
fuentes**. La pregunta del trabajo es cuánto del retraso de un autobús se explica
por la congestión medida aguas abajo de su ruta, y con cuánta antelación se puede
anticipar.

**Variable objetivo:** segundos de retraso en la siguiente parada (regresión).
Variante de clasificación binaria (`retraso > 5 min`) para el endpoint de la API,
que es la que asumen los contratos actuales de
[schemas.py](src/project/api/schemas.py).

**Aportación:** la etiqueta no existe en la fuente y hay que fabricarla. La capa
de la EMT no publica identificador de vehículo ni `trip_id`, así que el ETL tiene
que reconstruir la identidad de cada bus entre snapshots, segmentar viajes,
proyectar posiciones sobre la traza de la ruta e interpolar el paso por parada
contra el horario teórico del GTFS. Ese es el núcleo del trabajo.

Justificación completa y comparación con las alternativas descartadas en
[docs/](docs/).

---

## Fuentes de datos

Todas abiertas, sin clave y verificadas en vivo el 15/08/2026. Detalle en
[docs/01_viabilidad_fuentes_valencia.md](docs/01_viabilidad_fuentes_valencia.md).

| Fuente | Contenido | Cadencia | Papel |
|---|---|---|---|
| EMT · `Seguimiento_EMT/384` | posición GPS de la flota | refresco 29,3 s | fuente principal |
| Tráfico · capa `192` | estado de congestión, 410 tramos | sondeo 5 min | variable explicativa |
| Tráfico · capa `188` | intensidad medida, veh/h | sondeo 15 min | variable explicativa |
| Renfe Cercanías · núcleo 40 | posición **+ retraso ya calculado** | 30 s | validación cruzada / plan B |
| Valenbisi · capa `228` | disponibilidad, 273 estaciones | 10 min | demanda de movilidad |
| GTFS estático EMT | rutas, paradas, horarios teóricos | semanal | referencia de horario |

> **Metrovalencia / FGV no tiene datos en tiempo real públicos.** Solo GTFS
> estático. Entra en el trabajo como red teórica, nunca como dato observado.

**~32 M de filas en 57 días de captura, ~56 M a tres meses, 433 MB en Parquet**
(bitácora 056). Pide formato columnar, no infraestructura distribuida: en
Parquet particionado + DuckDB se trata en un portátil.

---

## Arquitectura

Dirección de dependencias — nunca al revés:

```text
ingesta (proceso aparte) ──> data/raw/
                                 │
ui/  ──HTTP──>  api/  ──>  services/  ──>  predict.py / train.py / features.py  ──>  config.py
```

| Capa | Responsabilidad | Restricción |
|---|---|---|
| [ui/](src/project/ui/) | Streamlit. Formularios y visualización. | No importa `services/` ni carga el modelo. Habla con la API por HTTP (`requests`). Si necesita algo nuevo, se añade un endpoint, no un import. |
| [api/](src/project/api/) | FastAPI. Valida entrada (Pydantic), delega, devuelve respuesta. | Sin lógica de negocio. Sin sklearn ni pandas. Endpoints nuevos en `api/routers/`, uno por dominio, montados con `include_router` en `main.py`. |
| [services/](src/project/services/) | Única capa que carga el modelo. `model_service.py` lo mantiene en memoria: carga única al arranque, no por request. | Nunca importa nada de `api/`. |
| `predict.py` / `train.py` / [features.py](src/project/features.py) | Lógica ML. `features.py` es **compartido entre train e inferencia**. | Duplicar la transformación en `train.py` y `predict.py` es train/serve skew. Vive en `features.py` y solo ahí. |
| [config.py](src/project/config.py) | Pydantic Settings leyendo `.env`. | Ningún `os.getenv` fuera de este módulo. Rutas (`MODEL_PATH`, datos) siempre desde settings. |

---

## Estructura

```text
.
├── docs/
│   ├── 00_tema_y_alcance.md # decisiones tomadas y estado del trabajo
│   ├── 01_viabilidad_fuentes_valencia.md
│   └── 02_exploracion_de_temas.md
├── src/project/
│   ├── config.py            # Pydantic Settings (.env) — única fuente de configuración
│   ├── ingest/              # captura y parseo — fuera del grafo de DVC
│   │   ├── sources.py       # endpoints, parsers y corrección de zona horaria
│   │   ├── explore.py       # sondeo one-shot: esquema, latencia, volumen
│   │   ├── collect.py       # colector asíncrono -> NDJSON crudo + Parquet
│   │   └── reprocesar.py    # reconstruye curated/ desde raw/
│   ├── tracking.py          # reconstrucción de identidad de vehículo
│   ├── analysis/diagnose.py # GO / NO-GO de la hipótesis (fuera de DVC)
│   ├── features.py          # transformaciones compartidas train/inferencia
│   ├── prepare.py           # tracking + etiquetado de retraso desde data/raw
│   ├── train.py             # entrenamiento XGBoost + logging a MLflow
│   ├── evaluate.py          # métricas sobre test → metrics/eval.json
│   ├── predict.py           # inferencia sobre modelo entrenado
│   ├── api/ · services/ · ui/
├── tests/                   # fixtures.json: payloads reales del 15/08/2026
├── scripts/                 # supervisar.ps1 — arranque/parada del colector
├── data/                    # raw/ interim/ processed/ — versionado por DVC
├── models/ · metrics/ · mlruns/ · notebooks/
├── dvc.yaml · params.yaml
├── Dockerfile · docker-compose.yml
└── pyproject.toml · uv.lock · .env.example
```

---

## Quickstart

Requisitos: Python ≥ 3.10 y [uv](https://docs.astral.sh/uv/). Entorno de
referencia: Windows + PowerShell.

```powershell
uv sync
Copy-Item .env.example .env
```

**Dependencias que aún faltan** para el pipeline y el demostrador:

```powershell
uv add xgboost shap httpx scipy pyarrow duckdb
```

### 1. Comprobar que las fuentes siguen vivas

```powershell
uv run python -m project.ingest.explore
uv run pytest
```

### 2. Capturar

```powershell
uv run python -m project.ingest.collect --minutes 1440
```

**Esto es lo urgente.** Los datos no tienen histórico recuperable: la tabla de la
EMT se trunca en cada refresco, así que lo que no se capture se pierde para
siempre. Sin captura acumulada no hay TFM.

### 3. API y UI

`run.sh` es bash y no funciona en PowerShell. Dos terminales:

```powershell
uv run uvicorn project.api.main:app --reload --port 8000
uv run streamlit run src/project/ui/app.py
```

Docs en `http://127.0.0.1:8000/docs`, UI en `http://localhost:8501`.

### 4. Demo en vivo por parada

Una parada, los buses que van hacia ella y su retraso predicho, con el marcador
de lo que se acertó (diseño en
[`docs/superpowers/specs/2026-11-10-demo-parada-en-vivo-design.md`](docs/superpowers/specs/2026-11-10-demo-parada-en-vivo-design.md)).
**Es una demo, no un resultado del TFM.** Corre en el PC y en una carpeta propia
(`$demo`), para no tocar `data/`, las métricas ni nada que versione DVC. Los
modelos sí salen de `models/`.

El sesgo del tramo sale de días anteriores **con la misma versión del GTFS**: antes
hay que traer y etiquetar días anteriores. **Tal cual, el guion trae y procesa el
corpus entero** (unos 2,6 GB y 63 días al 10/11, ~40 MB/día entre fuentes;
`reprocesar` y `prepare`, del orden de una hora para dos meses), como un
`dvc repro`. Para acotarlo, ver el final del paso 2. En PowerShell:

1. **Traer de la Pi a `$demo\raw`**, con WSL (Git Bash no trae `rsync`). Va
   **antes** de arrancar el colector del PC: un `rsync` sobre ficheros que el
   colector ya escribe los trunca (trampa 016). Con `$demo\raw` vacío copia todo lo
   que tiene la Pi, menos el día de hoy en UTC, y con ello los zips del GTFS;
   `--verificar` no escribe, enseña lo que difiere.

   ```powershell
   $demo = 'C:\Users\oppen\Code\demo'
   New-Item -ItemType Directory -Force "$demo\raw", "$demo\metrics"
   wsl env DESTINO=/mnt/c/Users/oppen/Code/demo/raw bash deploy_pi/pull_data.sh
   wsl env DESTINO=/mnt/c/Users/oppen/Code/demo/raw bash deploy_pi/pull_data.sh --verificar
   ```

2. **Reprocesar y etiquetar**, con las variables de la demo. `--metricas` va
   siempre dentro de `$demo`: `metrics/curar.json` y `metrics/prepare.json` del
   repo son cifras versionadas. `prepare` escribe en `$demo\interim` y
   `features --disponibilidad` deja ahí `disponibilidad/`. Sin DVC.

   ```powershell
   $env:DATA_ROOT = $demo
   $env:GTFS_DIR  = "$demo\raw\source=gtfs_emt"
   uv run python -m project.ingest.reprocesar --data $demo --metricas "$demo\metrics\curar.json"
   uv run python -m project.prepare --metricas "$demo\metrics\prepare.json"
   uv run python -m project.features --disponibilidad
   ```

   **Acotar a unos pocos días.** `reprocesar` no filtra días y `prepare` sin
   `--dias` procesa todos los capturados. Solo hacen falta los días cuya versión
   del GTFS es la vigente el día de la demo (el sesgo del tramo usa los
   anteriores con la misma versión). Tras traer, borra de `$demo\raw\source=*\`
   las carpetas `date=` que sobren, **menos las de `source=gtfs_emt`**, y deja
   también el `date=` del día siguiente a cada día elegido (el crudo se parte en
   UTC y el día de servicio no). Es la copia de la demo, nunca `data\raw`; un
   `pull_data.sh` posterior devuelve lo borrado. Y pasa los días a `prepare`:

   ```powershell
   uv run python -m project.prepare --dias 2026-11-03 2026-11-04 2026-11-05 --metricas "$demo\metrics\prepare.json"
   ```

3. **Colector con la carpeta de la demo, al menos una hora antes** (el ciclo
   relee el crudo de hoy). `--minutes 0` es indefinido:

   ```powershell
   uv run python -m project.ingest.collect --out $demo --minutes 0
   uv run python -m project.ingest.collect --out $demo --status
   ```

   Si el colector muere a la fuerza (no con Ctrl-C), mueve el
   `payloads.ndjson.gz` del día antes de relanzarlo: un miembro gzip cortado a
   mitad de fichero hace que el ciclo lea solo hasta ahí.

4. **API y UI**, en terminales separadas y con las mismas `DATA_ROOT` y
   `GTFS_DIR` en cada una:

   ```powershell
   uv run uvicorn project.api.main:app --port 8000
   uv run streamlit run src/project/ui/app.py
   ```

5. **Elegir una parada a mitad de ruta.** La 2277, la de más líneas, resultó casi
   una cabecera (la 72 acaba allí) y apenas tenía buses «en camino». Un ciclo
   tarda 35-42 s en hora punta (`CICLO_S = 40`, bitácora 064): es la cifra del
   ciclo completo, que llama a `construir` una vez por cada horizonte con modelo,
   no los 27-32 s de la medida de la tarea 1. La primera petición de una parada
   tarda eso. La UI refresca cada `REFRESCO_S = 40`, que debe ir a la par; el
   resultado se estampa al terminar, así que en punta el refresco efectivo es el
   ciclo más 40 s. Endpoints: `GET /vivo/paradas` y `GET /vivo/parada/{stop_id}`
   (503 sin datos u horario, 404 parada desconocida).

### Docker

```powershell
docker compose up --build
```

Levanta `api` (8000) y `ui` (8501). La imagen copia `models/`, así que el modelo
debe existir antes de construir.

---

## Pipeline ML

La ingesta **no** es un stage de DVC: capturar un stream en vivo no es
idempotente ni reejecutable, que es justo lo que DVC asume. El colector corre
aparte y deja el crudo en `data/raw/`; el pipeline reproducible empieza ahí.

```text
project/ingest/collect.py ──(fuera de DVC)──> data/raw/
                                        │
prepare   ──> data/interim/emt_tracked.parquet
features  ──> data/processed/{train,test}.parquet
train     ──> models/model.pkl
evaluate  ──> metrics/eval.json
```

```powershell
uv run dvc repro
uv run dvc metrics show
uv run dvc dag
```

`dvc repro` fallará hasta que exista `data/raw/` con captura real y los módulos
de `src/project/` dejen de estar vacíos. Ese fallo es correcto.

> **Bug histórico, ya resuelto (08/2026):** el bloque `stages:` vivía en
> `params.yaml` mientras `dvc.yaml` los tenía comentados, de modo que
> `dvc repro` no ejecutaba nada y las claves `params: [features, train]` no
> existían en ningún sitio. Ahora los stages están en `dvc.yaml` y los
> hiperparámetros en `params.yaml`, bajo las claves `prepare`, `features` y
> `train`.

### Experimentos (MLflow)

```powershell
uv run mlflow ui             # http://127.0.0.1:5000
```

Backend local: `mlflow.db` y `mlruns/`, ambos gitignorados. Todo run registra
params, métricas y modelo; `train.py` no usa stdout como única salida.

### Baselines obligatorios

Sin batir estos dos, no hay trabajo que defender:

1. **Horario teórico puro** — predecir retraso = 0.
2. **Persistencia** — el retraso actual del vehículo se mantiene.

---

## Tests

```powershell
uv run pytest
uv run ruff format . && uv run ruff check --fix .
```

- `tests/test_api.py` — `httpx` + `TestClient`. Mockea `services/`; no carga el
  modelo real.
- `tests/test_features.py` — cubre las transformaciones.
- Endpoint nuevo ⇒ test de API nuevo.

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) ejecuta `ruff check`,
`ruff format --check` y `pytest` en push a `main`/`develop` y en cada PR.

---

## Variables de entorno

[.env.example](.env.example) es la fuente de verdad: si añades una variable a
`config.py`, añádela también ahí.

| Variable | Por defecto | Uso |
|---|---|---|
| `API_URL` | `http://127.0.0.1:8000` | URL a la que se conecta la UI |
| `MODEL_PATH` | `models/model.pkl` | Ruta del modelo serializado |

---

## Autor y licencia

**Daniel Alpeñes** — Trabajo de Fin de Máster, Máster en Big Data.

Sin licencia declarada: uso académico. Los datos proceden de fuentes abiertas del
Ajuntament de València y de Renfe; ver
[docs/01_viabilidad_fuentes_valencia.md](docs/01_viabilidad_fuentes_valencia.md)
para condiciones de uso y limitaciones.
