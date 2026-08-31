# TFM — Daniel Alpeñes

Proyecto ML end-to-end: entrenamiento reproducible (DVC + MLflow), servido por
FastAPI, consumido por una UI Streamlit.

## Contexto

Trabajo de Fin de Máster: *Fusión de posiciones GPS de flota y estado de tráfico
urbano en tiempo real para la predicción de retrasos del transporte público: el
caso de la EMT de València.*

**Pregunta de investigación:** ¿cuánto del retraso de un autobús urbano se explica
por la congestión medida aguas abajo de su ruta, y con cuánta antelación puede
anticiparse?

- Tema, alcance, pilares de defensa, riesgos y plan B: `docs/00_tema_y_alcance.md`
- Decisiones cerradas con sus consecuencias: `docs/07_decisiones.md`
- Veredicto sobre cada fuente: `docs/01_viabilidad_fuentes_valencia.md`
- Calidad del dato medida sobre captura real: `docs/05_hallazgos_primera_captura.md`

## Dominio

Predicción de retrasos del transporte público urbano de València fusionando
posiciones GPS de la flota de la EMT con el estado del tráfico municipal.

- **Objetivo:** segundos de retraso en la siguiente parada (regresión). Variante
  binaria `retraso > 5 min` para el endpoint de la API.
- **Fuentes:** ArcGIS REST del geoportal del Ajuntament (buses
  `EMT/Seguimiento_EMT/384`, tráfico `OPENDATA/Trafico/192` y `188`, Valenbisi
  `228`), `flota.json` de Renfe Cercanías filtrado por `nucleo == "40"`, y GTFS
  estático de la EMT.
- **No hay histórico recuperable.** Ninguna fuente guarda pasado: lo que no capture
  el colector se pierde para siempre. El colector guarda **siempre** el payload
  crudo antes de parsear.

### Trampas que NO hay que redescubrir

Registro único en `.claude/trampas/`. El índice se importa abajo, así que está
siempre en contexto — tuyo y de los subagentes. Abre la ficha completa antes de
tocar la capa correspondiente. **No dupliques su contenido aquí ni en los prompts
de los agentes:** la copia diverge, y ya divergió tres veces con la trampa 002.

@.claude/trampas/README.md

**Si el código contradice a esta documentación, a `docs/` o a una ficha, gana el
código.** Señala la discrepancia y corrige la fuente de verdad, en vez de seguir
la versión escrita.

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
- **`demo/` está deliberadamente aislado** de `src/project/`: no se importan
  mutuamente. Es el prototipo de exploración y el arnés de verdad-terreno del que
  dependen varias fichas de trampas. Cuando su lógica se consolide, se porta a
  `src/project/ingest/`.

## Configuración

- Todo ajuste sale de `config.py` (Pydantic Settings leyendo `.env`). **No usar
  `os.getenv` fuera de `config.py`.**
- Rutas nunca hardcodeadas: `MODEL_PATH`, rutas de datos, etc. vienen de settings.
- `.env.example` es la fuente de verdad de qué variables existen: si añades una a
  `config.py`, añádela también ahí.
- `.env` está gitignorado y nunca se commitea.

## Pipeline ML

- **DVC gobierna el pipeline**, no scripts sueltos. Cada etapa
  (prepare → features → train → evaluate) es un stage en `dvc.yaml` con sus
  `deps`, `params` y `outs` declarados. Un script de entrenamiento sin stage es un
  error.
- **La ingesta NO es un stage.** Capturar un stream en vivo no es idempotente ni
  reejecutable. El colector corre aparte; el pipeline empieza en `data/raw/`.
- **Stages en `dvc.yaml`, hiperparámetros en `params.yaml`**, bajo las claves
  `prepare`, `features` y `train`. Hasta 08/2026 estaban al revés y `dvc repro` no
  ejecutaba nada; no volver a moverlos.
- **Parquet, no CSV,** en `data/interim/` y `data/processed/`. ~145 M de filas
  proyectadas en tres meses.
- **El split de train/test es TEMPORAL, nunca aleatorio.** Con series de
  posiciones, un split aleatorio filtra el futuro y da métricas falsas. Es el
  error que el tribunal buscará primero.
- **MLflow registra todo run**: params, métricas y modelo. Las métricas por stdout
  no son salida suficiente.
- **Baselines obligatorios** antes de presumir de nada: horario teórico
  (retraso = 0) y persistencia (el retraso actual se mantiene).
- `data/` y `models/*.pkl` los versiona DVC, no git. No editar `dvc.lock` ni
  `uv.lock` a mano.

## Estado

**El paquete `src/project/` está casi todo vacío.** `config.py`, `prepare.py`,
`features.py`, `train.py`, `predict.py`, `evaluate.py` y `services/model_service.py`
son ficheros de 0 líneas. Lo que funciona hoy vive en `demo/`: captura, parseo,
tracking y diagnóstico.

Las reglas de este fichero son **prescriptivas**, no descriptivas: dicen cómo debe
escribirse ese código cuando se escriba. No asumas que ya está implementado —
comprueba antes de importar.

## Tests

- `demo/selftest.py` corre sin red y debe seguir en verde. Es el arnés real del
  proyecto y del que dependen las guardias del registro de trampas.
- `tests/test_api.py` usa `httpx` + `TestClient`; mockea `services/`, no carga el
  modelo real. Endpoint nuevo ⇒ test nuevo.
- `tests/test_features.py` **está vacío**: se escribirá con `features.py`. Cubrirá
  las transformaciones, que es la capa donde un bug es silencioso.
- **El etiquetado y el tracking necesitarán tests con datos sintéticos de
  verdad-terreno conocida**, como los de `demo/selftest.py`. Un bug ahí contamina
  todas las etiquetas sin dar la cara.

`tests/` es el software del TFM. El andamiaje de agentes se valida aparte, en
`.claude/tests/`: `test_trampas.py` (frontmatter, `cerrada` sin guardia, `test:`
que cita checks inexistentes, índice desincronizado) y `test_memoria.py` (deriva
entre la documentación y el código). Pytest no los recoge solo — los directorios
con punto quedan fuera — así que corren con ruta explícita:

```bash
uv run pytest                  # tests del TFM
uv run pytest .claude/tests    # andamiaje de agentes
```

## Comandos

```bash
uv sync                      # instalar deps (nunca pip install)
uv add <pkg>                 # añadir dep (--dev para desarrollo)
uv run pytest
uv run ruff format . && uv run ruff check --fix .
uv run dvc repro             # reejecutar pipeline
uv run mlflow ui
uv run uvicorn project.api.main:app --reload --port 8000
uv run streamlit run src/project/ui/app.py

python demo/explore.py       # ¿siguen vivas las fuentes?
python demo/selftest.py      # validación offline del demostrador
python demo/collect.py --minutes 1440
```

Dependencias todavía por añadir: `xgboost`, `shap`, `polars`.

**Entorno: Windows + PowerShell.** `run.sh` es bash y no funciona aquí tal cual:
lanzar API y UI en terminales separadas.

## Comportamiento del agente

1. Entiende el objetivo. Pregunta lo que no esté claro en vez de asumirlo.
2. **Presenta un plan escrito y espera aprobación** antes de una tarea multipaso.
   También en las tareas que parezcan simples.
3. Ejecútalo paso a paso, revisa la salida y refuerza lo débil.
4. Nunca priorices velocidad sobre calidad.
