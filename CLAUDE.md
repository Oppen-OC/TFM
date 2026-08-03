# TFM — Daniel Alpeñes

Proyecto ML end-to-end: entrenamiento reproducible (DVC + MLflow), servido por FastAPI, consumido por una UI Streamlit.

## Arquitectura — reglas duras

Dirección de dependencias (nunca al revés):

```
ui/  ──HTTP──>  api/  ──>  services/  ──>  predict.py / train.py / features.py  ──>  config.py
```

- **`ui/` NO importa `services/` ni carga el modelo.** Habla con la API por HTTP (`requests`). Si Streamlit necesita algo nuevo, se añade un endpoint en `api/`, no un import.
- **`api/` no contiene lógica de negocio.** Los routers validan entrada (Pydantic), delegan en `services/` y devuelven la respuesta. Sin sklearn ni pandas en `api/`.
- **`services/` es la única capa que carga el modelo.** `model_service.py` mantiene el modelo en memoria (carga única al arranque, no por request).
- **`features.py` es compartido entre train e inferencia.** La transformación de entrada vive aquí y solo aquí; duplicarla en `train.py` y `predict.py` es el bug clásico (train/serve skew).
- **Endpoints nuevos van en `api/routers/`**, uno por dominio, incluidos con `include_router` en `main.py`.

## Configuración

- Todo ajuste sale de `config.py` (Pydantic Settings leyendo `.env`). **No usar `os.getenv` fuera de `config.py`.**
- Rutas nunca hardcodeadas: `MODEL_PATH`, rutas de datos, etc. vienen de settings.
- `.env.example` es la fuente de verdad de qué variables existen: si añades una a `config.py`, añádela también ahí.
- `.env` está gitignorado y nunca se commitea.

## Comandos

```bash
uv sync                      # instalar deps (nunca pip install)
uv add <pkg>                 # añadir dep de runtime
uv add --dev <pkg>           # añadir dep de desarrollo
uv run pytest                # tests
uv run ruff format . && uv run ruff check --fix .
uv run dvc repro             # reejecutar pipeline
uv run mlflow ui             # ver experimentos
uv run uvicorn project.api.main:app --reload --port 8000
uv run streamlit run src/project/ui/app.py
```

## Pipeline ML

- **DVC gobierna el pipeline**, no scripts sueltos. Cada etapa (features → train → eval) es un stage en `dvc.yaml` con sus `deps` y `outs` declarados. Un script nuevo de entrenamiento sin stage en `dvc.yaml` es un error.
- **MLflow registra todo run de entrenamiento**: params, métricas y modelo. `train.py` no imprime métricas por stdout como única salida.
- `data/` y `models/*.pkl` los versiona DVC, no git. No commitear binarios ni datasets.
- No editar `dvc.lock` ni `uv.lock` a mano.

## Tests

- `tests/test_api.py` usa `httpx` + `TestClient`; mockea `services/`, no carga el modelo real.
- `tests/test_features.py` cubre las transformaciones — es la capa donde un bug es silencioso.
- Test de API nuevo por cada endpoint nuevo.

## Entorno

Windows + PowerShell. `run.sh` es bash y no funciona aquí tal cual: lanzar API y UI en terminales separadas.
