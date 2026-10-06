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

### Bitácora de hallazgos

`docs/bitacora/` guarda lo que se mide, se descarta o se acepta durante el
desarrollo, con la cifra, el comando que la reproduce y el párrafo ya redactado
para la memoria. El formato y la tabla de encaminamiento —qué va a la bitácora,
qué a `.claude/trampas/`, qué a `docs/07_decisiones.md` y qué a GitHub Issues—
están en `docs/bitacora/README.md`. No los dupliques aquí.

**Ofrécelo tú.** Cuando en una sesión aparezca alguna de estas cosas, propón
fichar en una línea y sigue con lo que estabas haciendo si la respuesta es no:

- una cifra medida sobre datos propios (calidad, cobertura, error, latencia),
- una hipótesis descartada con evidencia,
- una anomalía de la fuente o un workaround que se acepta,
- un límite del alcance descubierto sobre la marcha,
- una decisión técnica tomada porque la alternativa se probó y falló.

No es lo mismo que documentar el código: aquí entra el *porqué* y el número, que
es justo lo que no se recuerda tres semanas después y lo que pregunta el tribunal.
El comando `/bitacora <suceso>` hace la investigación y escribe la entrada;
verifica la cifra antes de escribirla, porque el instrumento también miente
(trampa 004).

## Arquitectura — reglas duras

Dirección de dependencias (nunca al revés):

```
ingest/ (proceso aparte) ──> data/raw/ ──> tracking.py ──────────────┐
                            gtfs.py ──> mapmatching.py ──> etiquetado.py ──┴──> prepare.py
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
- **`ingest/` no importa de aguas abajo.** Captura y parsea; no sabe nada de
  `features.py`, del modelo ni de la API. Es lo que permite que el colector corra
  en una Raspberry sin arrastrar sklearn ni FastAPI.
- **`analysis/` está fuera del grafo de DVC.** `diagnose.py` es exploración: no
  produce entradas de `train`. Nada del pipeline importa de `analysis/`.
- **`tracking.py` es la reconstrucción de identidad de vehículo.** Lo consume
  `prepare.py`. La EMT no publica id de vehículo, así que se infiere: cualquier
  error aquí contamina todas las etiquetas sin dar la cara (trampa 004).
- **`tracking.py` NO importa el GTFS.** Acepta la abscisa como columna opcional
  (ADR-012), pero `prepare.py` rastrea en UNA pasada: la segunda con abscisa no
  mejora la identidad en jornada real (bitácora 023, ADR-013). Al revés la
  dependencia sería circular, porque el map-matching necesita identidad para
  decidir el sentido.
- **`etiquetado.py` es la cascada**: viajes, paso por parada, viaje programado y
  retraso. Funciones puras sobre la salida de `rastrear`; `prepare.py` sólo
  orquesta la E/S. **Toda columna se une por índice o identificador, nunca por
  posición de fila**: `rastrear` reordena, y así se falseó la 017 (bitácora 023).
- **El GTFS se elige por fecha de servicio** (`gtfs.elegir_horario`): hay varias
  versiones con vigencias solapadas en `settings.gtfs_dir` (ADR-014).
- **`mapmatching.py` filtra por distancia al trazado, nunca por caja geográfica**
  (trampa 006), y la abscisa se proyecta sobre la geometría: el
  `shape_dist_traveled` del feed es el horario reescalado (trampa 010).

## Configuración

- Todo ajuste sale de `config.py` (Pydantic Settings leyendo `.env`). **No usar
  `os.getenv` fuera de `config.py`.**
- Rutas nunca hardcodeadas: `MODEL_PATH`, rutas de datos, etc. vienen de settings.
- `.env.example` es la fuente de verdad de qué variables existen: si añades una a
  `config.py`, añádela también ahí.
- `.env` está gitignorado y nunca se commitea.

## Pipeline ML

- **DVC gobierna el pipeline**, no scripts sueltos. Cada etapa
  (curar → prepare → features → train → evaluate) es un stage en `dvc.yaml` con sus
  `deps`, `params` y `outs` declarados. Un script de entrenamiento sin stage es un
  error.
- **La ingesta NO es un stage.** Capturar un stream en vivo no es idempotente ni
  reejecutable. El colector corre aparte; el pipeline empieza en `data/raw/`.
  **Curar sí lo es**: `curar` reconstruye `data/curated/` desde el crudo con
  `reprocesar`, que es determinista. El curated que escribe el colector en vivo
  es una vista previa; el del pipeline es el reprocesado (bitácoras 019 y 020).
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
- **La muestra son todas las líneas etiquetadas.** La cobertura de sensores de
  tráfico es un estrato de evaluación, nunca un recorte, y no se excluye una
  línea por el error del modelo. Una línea se informa con cifra propia solo con
  soporte mínimo (`features.soporte_por_linea`). **Una mejora es una diferencia
  sobre los mismos viajes cuyo intervalo del 95 %, remuestreando viajes, no
  contiene el cero.** ADR-018.
- `data/` y `models/*.pkl` los versiona DVC, no git. No editar `dvc.lock` ni
  `uv.lock` a mano.

## Estado

**El pipeline llega de punta a punta; el modelo v2 bate al listón sin tráfico.**

Implementado y con tests: `config.py`, `ingest/` (sources, collect, reprocesar,
explore), `tracking.py`, `gtfs.py`, `mapmatching.py`, `etiquetado.py`,
`prepare.py`, `features.py` (fase 1, bitácora 030; fase 2, la flota como sensor:
bitácora 032; sesgo del horario por tramo y `linea` categórica: bitácora 039,
ADR-019; la capa 192, pendiente), `train.py`, `predict.py`, `evaluate.py` y
`analysis/`.
`dvc repro` corre entero: los pasos por parada con `retraso_s` salen en
`data/interim/pasos/`, la tabla partida en `data/processed/{train,test}.parquet`
con los baselines en `metrics/features.json`, el modelo en `models/model.pkl` y
su evaluación, con la diferencia por viajes y su intervalo, en
`metrics/eval.json`. Las variables del modelo las da `features.variables()`;
`train.py` y `predict.py` las leen de ahí. La v1 empataba con la persistencia
más el sesgo del tramo (bitácora 041). La v2, residuo con pérdida absoluta
(ADR-021), la bate por 2,09 s de MAE sin la capa 192 (bitácora 043).

Vacío, 0 líneas: `services/model_service.py`.

Las reglas de este fichero son **prescriptivas**, no descriptivas: dicen cómo debe
escribirse el código que falta. No asumas que ya está implementado — comprueba
antes de importar.

## Tests

- `tests/test_ingest.py` y `tests/test_tracking.py` corren **sin red** y deben
  seguir en verde: son las guardias de las trampas 001-004. Los fixtures de
  `tests/fixtures.json` tienen la forma exacta de los payloads reales, con sus
  rarezas dentro; un mock limpio no detectaría las regresiones que detectan ellos.
- `tests/conftest.py` genera la **flota simulada con verdad-terreno conocida**. Sin
  verdad conocida no se puede distinguir "60 trayectorias" de "60 trayectorias
  correctas", que es justo lo que escondió la trampa 004.
- `tests/test_persistencia.py` guarda la capa que no se puede arreglar después:
  crudo antes de parsear, append, partición, deduplicación, `reprocesar`.
- `tests/test_tracking_realismo.py` prueba el tracker con paradas y giros al
  ritmo real. Es `xfail(strict=True)`: defecto conocido, no corregido.
- **Un test en verde no demuestra que guarde nada.** `auditoria/mutar.py` rompe a
  propósito cada invariante y comprueba que algún test cae (ADR-011). Guardia
  nueva ⇒ mutante en `auditoria/catalogo.toml` que la ponga roja. Tras actualizar
  dependencias, se vuelve a ejecutar: la guardia de la trampa 004 caducó con numpy.
- `tests/test_diagnose.py` valida que el diagnóstico **discrimina**: señal en el
  escenario A, nada en el B. Si dijera lo mismo en los dos, validaría la hipótesis
  del TFM por accidente.
- `tests/test_api.py` usa `httpx` + `TestClient`; mockea `services/`, no carga el
  modelo real. Endpoint nuevo ⇒ test nuevo.
- `tests/test_features.py` guarda la **fuga de futuro**, que es silenciosa:
  pasos sintéticos con instantes conocidos y variables que no pueden ver nada
  en `t_obs` o después, ni el propio viaje, ni los diagnósticos de la
  asignación. Mutantes 079-082.
- `tests/test_etiquetado.py` monta un **GTFS sintético y una flota con retraso
  conocido** y exige recuperarlo en cada parada (±5 s): regulación en cabecera,
  huecos, desvíos, refuerzos, punta, variantes, nocturnos, calendario, versión del
  feed y orden de la entrada. Un bug ahí contamina todas las etiquetas sin dar la
  cara; mutantes 056-068.

`tests/` es el software del TFM. El andamiaje de agentes se valida aparte, en
`.claude/tests/`: `test_trampas.py` (frontmatter, `cerrada` sin guardia, `test:`
que cita un node id inexistente, índice desincronizado) y `test_memoria.py` (deriva
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

uv run python -m project.ingest.explore              # ¿siguen vivas las fuentes?
uv run python -m project.ingest.collect --minutes 1440   # captura (fuera de DVC)
uv run python -m project.ingest.collect --status     # estado del colector
uv run python -m project.ingest.reprocesar           # reconstruye curated/ desde raw/
uv run python -m project.analysis.diagnose           # GO / NO-GO de la hipótesis
uv run python auditoria/mutar.py                     # ¿detectan los tests? (~40 min)
```

Dependencias todavía por añadir: `shap`.

**Entorno: Windows + PowerShell.** `run.sh` es bash y no funciona aquí tal cual:
lanzar API y UI en terminales separadas.

## Comportamiento del agente

1. Entiende el objetivo **y complétalo**: el encargo llega corto y las
   restricciones se callan (ver *Encargos incompletos*).
2. **Presenta un plan escrito y espera aprobación** antes de una tarea multipaso.
   También en las tareas que parezcan simples.
3. Ejecútalo paso a paso, revisa la salida y refuerza lo débil.
4. Nunca priorices velocidad sobre calidad.
5. Si por el camino aparece un hallazgo de los que lista la bitácora, ofrécelo
   antes de cerrar la tarea. Lo que no se ficha el día que pasa, se pierde.

## Encargos incompletos

Los prompts de este repo llegan cortos: piden el *qué* y callan las restricciones
que lo condicionan. Completar ese hueco es trabajo tuyo, no descuido del usuario.

**Antes del plan**, en tareas multipaso, devuelve el encargo reformulado:
objetivo, entradas, salidas, criterio de aceptación, **no-objetivos** y supuestos.
Un hueco se rellena con **supuesto marcado**, nunca con silencio. Pregunta solo lo
que, supuesto al revés, daría un trabajo distinto; lo demás se asume en voz alta y
se sigue. Un supuesto explícito es defendible, uno tácito no.

Recorre estas ocho dimensiones y nombra **solo las que muerden** en este encargo:

- **dato** — ¿existe ya capturado, o supone capturar N semanas más? Nada de esto
  es recuperable a posteriori.
- **alcance** — qué queda explícitamente fuera. Sin no-objetivos se desborda solo.
- **acoplamiento** — qué invalida aguas abajo: etiquetas ya generadas, `dvc.lock`,
  una captura en curso, los fixtures.
- **temporalidad** — split temporal, orden de los eventos, convención horaria.
- **evidencia** — qué test o qué cifra lo demuestra, y cuál lo falsaría.
- **frontera** — dirección de dependencias, `config.py`, aislamiento de `ingest/`
  y de `analysis/`.
- **trampa** — ficha aplicable del índice, leída antes de tocar esa capa.
- **entrega** — qué queda escrito y dónde: bitácora, `docs/07_decisiones.md`,
  ficha de trampa o issue.

La lista vive aquí y solo aquí. `/encargo` la aplica a una petición cruda y
`/grill-me` a un plan ya formado; ninguno de los dos la copia.
