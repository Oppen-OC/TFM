# TFM — Daniel Alpeñes

> **TODO (dominio):** definir en una frase el problema que resuelve el modelo (dataset y variable objetivo). Los contratos en [schemas.py](src/project/api/schemas.py) asumen **clasificación binaria** (`prediction: int`, `probability: float`); el dominio concreto está sin decidir.

Pipeline ML end-to-end: preparación y entrenamiento reproducibles (DVC + MLflow), modelo servido por FastAPI y consumido por una UI Streamlit.

> **Estado:** el esqueleto (API, UI, Docker, CI, tests) está en pie; los módulos del pipeline (`features.py`, `prepare.py`, `train.py`, `evaluate.py`, `predict.py`, `config.py`, `model_service.py`) están vacíos. Ver [Estado actual del pipeline](#estado-actual-del-pipeline).

---

## Arquitectura

Dirección de dependencias — nunca al revés:

```text
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
├── src/project/
│   ├── config.py            # Pydantic Settings (.env) — única fuente de configuración
│   ├── features.py          # transformaciones compartidas train/inferencia
│   ├── prepare.py           # preparación/split del dataset crudo
│   ├── train.py             # entrenamiento + logging a MLflow
│   ├── evaluate.py          # métricas sobre test → metrics/eval.json
│   ├── predict.py           # inferencia sobre modelo entrenado
│   ├── api/
│   │   ├── main.py          # app FastAPI, /health, include_router
│   │   ├── schemas.py       # contratos Pydantic (PredictRequest/Response)
│   │   └── routers/
│   │       └── predict.py   # endpoint /predict
│   ├── services/
│   │   └── model_service.py # carga y cachea el modelo en memoria
│   └── ui/
│       └── app.py           # Streamlit, consume la API por HTTP
├── tests/
│   ├── test_api.py          # httpx + TestClient, mockea services/
│   └── test_features.py     # transformaciones (donde el bug es silencioso)
├── data/                    # raw/ interim/ processed/ — versionado por DVC, no por git
├── models/                  # *.pkl — versionado por DVC, no por git
├── metrics/eval.json        # métricas de la etapa evaluate (no cacheado)
├── mlruns/ · mlflow.db      # tracking local de MLflow (gitignorados)
├── notebooks/ · docs/
├── dvc.yaml · params.yaml   # definición del pipeline y sus parámetros
├── Dockerfile · docker-compose.yml
├── pyproject.toml · uv.lock # dependencias gestionadas con uv
└── .env.example             # fuente de verdad de las variables de entorno
```

---

## Quickstart

Requisitos: Python ≥ 3.10 y [uv](https://docs.astral.sh/uv/). Entorno de referencia: Windows + PowerShell.

```powershell
uv sync                      # instala deps (nunca pip install)
Copy-Item .env.example .env  # rellenar valores; .env está gitignorado
```

`run.sh` es bash y no funciona en PowerShell. Lanzar los dos procesos en **terminales separadas**:

**Terminal 1 — API**

```powershell
uv run uvicorn project.api.main:app --reload --port 8000
```

Docs interactivas en `http://127.0.0.1:8000/docs`, health en `http://127.0.0.1:8000/health`.

**Terminal 2 — UI**

```powershell
uv run streamlit run src/project/ui/app.py
```

UI en `http://localhost:8501`. Lee `API_HOST` / `API_PORT` del entorno para construir la URL de la API.

### Docker

```powershell
docker compose up --build
```

Levanta `api` (8000) y `ui` (8501); a `ui` se le inyecta `API_HOST=api`. La imagen copia `models/`, así que el modelo debe existir antes de construir.

### Dependencias

```powershell
uv add <pkg>                 # runtime
uv add --dev <pkg>           # desarrollo
```

`uv.lock` y `dvc.lock` no se editan a mano.

---

## Pipeline ML

DVC gobierna el pipeline; no hay scripts sueltos. Cada etapa declara sus `deps`, `params` y `outs`:

```text
features (data/raw/dataset.csv) ──> data/processed/{train,test}.csv
train    (train.csv)            ──> models/model.pkl
evaluate (test.csv + model.pkl) ──> metrics/eval.json
```

```powershell
uv run dvc repro             # reejecuta solo las etapas cuyas deps cambiaron
uv run dvc metrics show      # métricas de la etapa evaluate
uv run dvc dag               # grafo de dependencias
```

Un script de entrenamiento nuevo sin stage en `dvc.yaml` es un error. `data/` y `models/*.pkl` los versiona DVC, no git: no se commitean datasets ni binarios.

### Experimentos (MLflow)

Todo run de entrenamiento registra params, métricas y modelo. `train.py` no usa stdout como única salida.

```powershell
uv run mlflow ui             # http://127.0.0.1:5000
```

Backend local: `mlflow.db` y `mlruns/`, ambos gitignorados.

### Estado actual del pipeline

Las definiciones de stages están **en `params.yaml`**, mientras que `dvc.yaml` contiene esas mismas stages comentadas. Con esa distribución `dvc repro` no ejecuta nada, y las claves `params: [features, train]` que las stages referencian no existen en ningún sitio. Antes de correr el pipeline: mover el bloque `stages:` a `dvc.yaml` y dejar en `params.yaml` los hiperparámetros bajo las claves `features:` y `train:`.

---

## Tests

```powershell
uv run pytest                # toda la suite
uv run pytest tests/test_api.py -v
```

- `tests/test_api.py` — `httpx` + `TestClient`. Mockea `services/`; no carga el modelo real.
- `tests/test_features.py` — cubre las transformaciones.
- Endpoint nuevo ⇒ test de API nuevo.

Lint y formato (lo mismo que corre CI):

```powershell
uv run ruff format . && uv run ruff check --fix .
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) ejecuta `ruff check`, `ruff format --check` y `pytest` en push a `main`/`develop` y en cada pull request.

---

## Variables de entorno

[.env.example](.env.example) es la fuente de verdad: si añades una variable a `config.py`, añádela también ahí. `.env` está gitignorado y nunca se commitea.

| Variable | Por defecto | Uso |
|---|---|---|
| `APP_NAME` | `tfm` | Nombre de la aplicación |
| `ENV` | `development` | Entorno de ejecución |
| `LOG_LEVEL` | `info` | Nivel de logging |
| `API_HOST` | `0.0.0.0` | Host de bind de la API (`api` bajo docker compose) |
| `API_PORT` | `8000` | Puerto de la API |
| `MODEL_PATH` | `models/model.pkl` | Ruta del modelo serializado |
| `API_KEY` | *(vacío)* | Clave de API |

---

## Autor y licencia

**Daniel Alpeñes** — Trabajo de Fin de Máster (TFM).

Sin licencia declarada: uso académico.
