# TFM — Daniel Alpeñes

**Predicción de retrasos del transporte público urbano de València mediante fusión
de posiciones GPS de flota y estado del tráfico en tiempo real.**

Pipeline ML end-to-end: ingesta en streaming de datos abiertos municipales,
preparación y entrenamiento reproducibles (DVC + MLflow), modelo XGBoost servido
por FastAPI y consumido por una UI Streamlit.

---

## El problema

Las apps de transporte estiman la llegada del autobús con reglas simples que
fallan justo cuando importa: hora punta, lluvia, incidencias. La EMT de València
publica la posición GPS de su flota en tiempo real, y el Ajuntament publica el
estado de congestión de 446 tramos viarios, pero **nadie ha cruzado las dos
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
| Tráfico · capa `192` | estado de congestión, 446 tramos | 60 s | variable explicativa |
| Tráfico · capa `188` | intensidad medida, veh/h | 5 min | variable explicativa |
| Renfe Cercanías · núcleo 40 | posición **+ retraso ya calculado** | 30 s | validación cruzada / plan B |
| Valenbisi · capa `228` | disponibilidad, 273 estaciones | 10 min | demanda de movilidad |
| GTFS estático EMT | rutas, paradas, horarios teóricos | semanal | referencia de horario |

> **Metrovalencia / FGV no tiene datos en tiempo real públicos.** Solo GTFS
> estático. Entra en el trabajo como red teórica, nunca como dato observado.

**~145 M de filas en tres meses de captura.** En CSV es inmanejable en un
portátil; en Parquet particionado + DuckDB, no.

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
├── demo/                    # prototipo de exploración de las fuentes (aislado)
│   ├── sources.py           # endpoints, parsers y corrección de zona horaria
│   ├── explore.py           # sondeo one-shot: esquema, latencia, volumen
│   ├── collect.py           # colector asíncrono -> NDJSON crudo + Parquet
│   ├── track.py             # reconstrucción de identidad de vehículo
│   ├── selftest.py          # 24 comprobaciones sin red
│   └── fixtures.json        # payloads reales del 15/08/2026
├── docs/
│   ├── 00_tema_y_alcance.md # decisiones tomadas y estado del trabajo
│   ├── 01_viabilidad_fuentes_valencia.md
│   └── 02_exploracion_de_temas.md
├── src/project/
│   ├── config.py            # Pydantic Settings (.env) — única fuente de configuración
│   ├── features.py          # transformaciones compartidas train/inferencia
│   ├── prepare.py           # tracking + etiquetado de retraso desde data/raw
│   ├── train.py             # entrenamiento XGBoost + logging a MLflow
│   ├── evaluate.py          # métricas sobre test → metrics/eval.json
│   ├── predict.py           # inferencia sobre modelo entrenado
│   ├── api/ · services/ · ui/
├── tests/
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
python demo\explore.py
python demo\selftest.py
```

### 2. Capturar

```powershell
python demo\collect.py --minutes 1440
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
demo/collect.py ──(fuera de DVC)──> data/raw/
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
| `APP_NAME` | `tfm` | Nombre de la aplicación |
| `ENV` | `development` | Entorno de ejecución |
| `LOG_LEVEL` | `info` | Nivel de logging |
| `API_HOST` | `0.0.0.0` | Host de bind de la API |
| `API_PORT` | `8000` | Puerto de la API |
| `MODEL_PATH` | `models/model.pkl` | Ruta del modelo serializado |
| `API_KEY` | *(vacío)* | Clave de API |

---

## Autor y licencia

**Daniel Alpeñes** — Trabajo de Fin de Máster, Máster en Big Data.

Sin licencia declarada: uso académico. Los datos proceden de fuentes abiertas del
Ajuntament de València y de Renfe; ver
[docs/01_viabilidad_fuentes_valencia.md](docs/01_viabilidad_fuentes_valencia.md)
para condiciones de uso y limitaciones.
