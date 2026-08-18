# TFM — Daniel Alpeñes

Proyecto ML end-to-end: entrenamiento reproducible (DVC + MLflow), servido por
FastAPI, consumido por una UI Streamlit.

## Dominio

**Predicción de retrasos del transporte público urbano de València fusionando
posiciones GPS de la flota de la EMT con el estado del tráfico municipal en
tiempo real.**

- **Objetivo:** segundos de retraso en la siguiente parada (regresión). Variante
  binaria `retraso > 5 min` para el endpoint de la API.
- **Fuentes:** ArcGIS REST del geoportal del Ajuntament (buses `EMT/Seguimiento_EMT/384`,
  tráfico `OPENDATA/Trafico/192` y `188`, Valenbisi `228`), `flota.json` de Renfe
  Cercanías filtrado por `nucleo == "40"`, y GTFS estático de la EMT.
- **Contexto completo:** `docs/00_tema_y_alcance.md`. Antes de tocar la ingesta o
  el etiquetado, leer `docs/01_viabilidad_fuentes_valencia.md`.

### Tres trampas de los datos que NO hay que redescubrir

1. **`gid` no identifica al vehículo.** Es un autoincrement de una tabla que se
   trunca y reinserta entera en cada refresco: dos sondeos consecutivos tienen
   intersección de gids exactamente cero. Sirve como `snapshot_id` para
   deduplicar, nada más. La identidad de vehículo hay que **inferirla**
   (asignación húngara con predicción de movimiento; ver `demo/track.py`).
2. **El campo `fecha` de la EMT va adelantado.** Es epoch-ms construido desde
   hora local de Madrid tratada como UTC: +2 h en verano, +1 h en invierno. Hay
   que corregirlo con `zoneinfo` por fecha o la serie se parte en el cambio de
   hora. Mismo problema con `fechaActualizacion` de Renfe.
3. **La raíz del JSON de Renfe es un objeto, no un array:**
   `{fechaActualizacion, trenes: [...]}`.

### No hay histórico recuperable

Ninguna de las fuentes guarda pasado. Lo que no capture el colector se pierde
para siempre. El colector guarda **siempre** el payload crudo antes de parsear.

## Arquitectura — reglas duras

Dirección de dependencias (nunca al revés):

```
ingesta (proceso aparte) ──> data/raw/
ui/  ──HTTP──>  api/  ──>  services/  ──>  predict.py / train.py / features.py  ──>  config.py
```

- **`ui/` NO importa `services/` ni carga el modelo.** Habla con la API por HTTP
  (`requests`). Si Streamlit necesita algo nuevo, se añade un endpoint en `api/`,
  no un import.
- **`api/` no contiene lógica de negocio.** Los routers validan entrada
  (Pydantic), delegan en `services/` y devuelven la respuesta. Sin sklearn ni
  pandas en `api/`.
- **`services/` es la única capa que carga el modelo.** `model_service.py`
  mantiene el modelo en memoria (carga única al arranque, no por request).
- **`features.py` es compartido entre train e inferencia.** La transformación de
  entrada vive aquí y solo aquí; duplicarla en `train.py` y `predict.py` es el
  bug clásico (train/serve skew).
- **Endpoints nuevos van en `api/routers/`**, uno por dominio, incluidos con
  `include_router` en `main.py`.

## La carpeta `demo/`

Prototipo de exploración de las fuentes, **deliberadamente aislado** del paquete
`src/project/`. No importa nada de `project` ni al revés. Sirve para validar que
las fuentes siguen vivas y para capturar mientras el pipeline se construye.

Cuando su lógica se consolide, se porta a `src/project/ingest/` respetando las
reglas de arriba. Mientras tanto **no lo mezcles con `src/`**: si `src/project/`
empieza a importar de `demo/`, la separación se ha roto.

`demo/selftest.py` corre sin red y debe seguir en verde (24 comprobaciones).

## Configuración

- Todo ajuste sale de `config.py` (Pydantic Settings leyendo `.env`). **No usar
  `os.getenv` fuera de `config.py`.**
- Rutas nunca hardcodeadas: `MODEL_PATH`, rutas de datos, etc. vienen de settings.
- `.env.example` es la fuente de verdad de qué variables existen: si añades una a
  `config.py`, añádela también ahí.
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

python demo/explore.py       # ¿siguen vivas las fuentes?
python demo/selftest.py      # validación offline del demostrador
python demo/collect.py --minutes 1440
```

Dependencias todavía por añadir: `xgboost`, `shap`, `httpx`, `scipy`, `pyarrow`,
`duckdb`.

## Pipeline ML

- **DVC gobierna el pipeline**, no scripts sueltos. Cada etapa
  (prepare → features → train → evaluate) es un stage en `dvc.yaml` con sus
  `deps`, `params` y `outs` declarados. Un script nuevo de entrenamiento sin
  stage en `dvc.yaml` es un error.
- **La ingesta NO es un stage de DVC.** Capturar un stream en vivo no es
  idempotente ni reejecutable. El colector corre aparte; el pipeline empieza en
  `data/raw/`.
- **Los stages viven en `dvc.yaml` y los hiperparámetros en `params.yaml`**, bajo
  las claves `prepare`, `features` y `train`. Hasta 08/2026 estaban al revés y
  `dvc repro` no ejecutaba nada; no volver a moverlos.
- **Parquet, no CSV,** en `data/interim/` y `data/processed/`. El volumen
  proyectado son ~145 M de filas en tres meses.
- **El split de train/test es TEMPORAL, nunca aleatorio.** Con series de
  posiciones, un split aleatorio filtra el futuro y da métricas falsas. Es el
  error que el tribunal buscará primero.
- **MLflow registra todo run de entrenamiento**: params, métricas y modelo.
  `train.py` no imprime métricas por stdout como única salida.
- `data/` y `models/*.pkl` los versiona DVC, no git. No commitear binarios ni
  datasets.
- No editar `dvc.lock` ni `uv.lock` a mano.
- **Baselines obligatorios** antes de presumir de nada: horario teórico
  (retraso = 0) y persistencia (el retraso actual se mantiene).

## Tests

- `tests/test_api.py` usa `httpx` + `TestClient`; mockea `services/`, no carga el
  modelo real.
- `tests/test_features.py` cubre las transformaciones — es la capa donde un bug
  es silencioso.
- Test de API nuevo por cada endpoint nuevo.
- El etiquetado de retraso y el tracking necesitan tests con datos sintéticos de
  verdad-terreno conocida, como los de `demo/selftest.py`. Un bug ahí contamina
  todas las etiquetas sin dar la cara.

## Entorno

Windows + PowerShell. `run.sh` es bash y no funciona aquí tal cual: lanzar API y
UI en terminales separadas.
