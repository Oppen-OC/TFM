# Día 6 · Pipeline y arquitectura

## Objetivo del día

Poder dibujar de memoria la dirección de dependencias, explicar por qué cada regla
existe (qué se rompe si se cruza) y decir con precisión **qué está implementado y qué
no**.

> **Corrección importante respecto al plan original.** El plan decía «saber qué falta
> por implementar» pensando en un `src/` casi vacío. En esta rama `src/project/` está
> completo: `train.py` (349 líneas), `features.py` (782), `evaluate.py` (645),
> `prepare.py` (277), `predict.py` (66), `services/model_service.py` (182), etc. Lo que
> falta es una lista corta y concreta, abajo.

## Lecturas

En este orden:

1. `dvc.yaml`, entero (cabecera l. 1-22 con el esquema del pipeline; 20 stages).
2. `params.yaml`, entero: `prepare` (l. 10-), `features` (l. 40-), `train`.
3. `CLAUDE.md`, secciones *Arquitectura — reglas duras*, *Configuración* y *Pipeline ML*.
4. `src/project/api/main.py` (26 líneas), `api/routers/prediccion.py` (67),
   `api/routers/vivo.py` (39), `api/schemas.py` (174, solo la docstring y los modelos).
5. `src/project/services/model_service.py`: docstring (l. 1-8) y `Servicio`
   (l. 106-182). `src/project/predict.py` entero (66 líneas).
6. `src/project/ui/app.py`: cabecera (l. 1-15) y las llamadas HTTP (l. 150-160, 227-280).
7. `tests/test_api.py` (ver qué se mockea) y `tests/test_servicio.py` (docstring).
8. `docs/12_flujo_de_datos.html` en el navegador: el flujo por etapa con sus guardias.

## Comandos a ejecutar

En PowerShell, desde la raíz:

```powershell
uv run pytest tests/test_api.py tests/test_servicio.py tests/test_ui.py -q
uv run dvc dag                                  # el grafo de stages (necesita `uv sync`)
Start-Process docs/12_flujo_de_datos.html
```

Para ver las fronteras de la arquitectura comprobadas por una herramienta del repo,
usa el comando `/check-fronteras` en Claude Code. No lances `dvc repro`: necesita
`data/` y tarda horas.

Para levantar el servicio (si hay modelo en `models/` y `.env`):

```powershell
uv run uvicorn project.api.main:app --reload --port 8000     # terminal 1
uv run python -m project.ui.app                              # terminal 2
```

`run.sh` es bash y aquí no funciona tal cual (`CLAUDE.md`, *Comandos*).

## Qué tienes que saber explicar

**P1. Dibuja la dirección de dependencias y di qué prohíbe cada flecha.**
```
ingest/ (proceso aparte) ──> data/raw/ ──> tracking.py ───────────────┐
                            gtfs.py ──> mapmatching.py ──> etiquetado.py ──┴──> prepare.py
ui/  ──HTTP──>  api/  ──>  services/  ──>  predict.py / train.py / features.py  ──>  config.py
```
(`CLAUDE.md`, *Arquitectura*). `ui/` no importa `services/` ni carga el modelo: habla
por HTTP. `api/` no tiene lógica de negocio. `services/` es la única capa que carga el
modelo. `features.py` es compartido por train e inferencia. `ingest/` no importa de
aguas abajo. `analysis/` está fuera del grafo de DVC.

**P2. ¿Por qué `ui/` habla por HTTP y no importa `services/`?**
Para que el modelo tenga un único dueño y la UI pueda cambiar sin tocarlo; y las
peticiones van dentro de `run.io_bound` porque NiceGUI comparte un bucle de eventos
entre todos los navegadores y una petición de 40 s lo congelaría
(`src/project/ui/app.py:1-15`, `227-236`; `CLAUDE.md`). Si la UI necesita algo nuevo, se
añade un endpoint, no un import.

**P3. ¿Qué es el train/serve skew y cómo se evita aquí?**
Es que la transformación de la entrada difiera entre entrenamiento e inferencia, el bug
clásico al duplicarla. Aquí la lista de variables sale de `features.variables()`
(`features.py:55-70`), `train.py` y `predict.py` la leen de ahí
(`predict.py:33,44,56` pasan por `features.matriz`) y `services/` comprueba el vector
contra el artefacto (`model_service.py:1-8`). Ninguna lista de columnas se escribe a
mano (`train.py:1-12`).

**P4. ¿Por qué el modelo se carga al arrancar y no por petición?**
Porque cargar un `pkl` en cada petición cuesta latencia y memoria, y porque así hay un
único dueño del modelo; `main.py:12-18` lo carga en el `lifespan` y los tests lo
sustituyen (`api/routers/prediccion.py:21-24`).

**P5. ¿Por qué la ingesta no es un stage de DVC?**
Porque DVC asume que cada stage es idempotente y reejecutable, y capturar un stream en
vivo no lo es: `dvc repro` no puede volver a capturar el martes pasado. El colector
corre aparte y el pipeline empieza en `data/raw/`; `curar` sí es stage porque
reconstruye `data/curated/` determinísticamente desde el crudo (`dvc.yaml:1-8, 25-44`;
ADR-002 `docs/07_decisiones.md:45`; ADR-015 `docs/07_decisiones.md:414`).

**P6. ¿Por qué el split es temporal?**
Un split aleatorio filtra el futuro y da métricas falsas: es el error que el tribunal
busca primero. Está fijado por tres fechas en `params.yaml` y las aplica
`features.partir` (`features.py:460-488`; ADR-007, `docs/07_decisiones.md:154`).
Además, el «ahora» de una fila es cuándo se supo su retraso (`t_disp`), no cuándo
ocurrió el paso (trampa 017; ADR-022, `docs/07_decisiones.md:751`).

**P7. ¿Por qué baselines obligatorios y cuáles son?**
Porque sin ellos «el modelo funciona» no significa nada. Son el horario teórico
(retraso = 0), la persistencia (el retraso actual se mantiene) y la persistencia más el
sesgo del tramo, que es el listón real: batir la persistencia es sobre todo aprender el
sesgo fijo del horario (`features.py:535-548`; `CLAUDE.md`, *Pipeline ML*). Una mejora
es una diferencia sobre los mismos viajes cuyo IC del 95 % no contiene el cero
(ADR-018, `docs/07_decisiones.md:511`).

**P8. ¿Qué registra MLflow y por qué no basta con stdout?**
Todo run: parámetros, métricas y modelo (`train.py:242-245`; `evaluate.py:499-507`).
Las métricas por stdout no se pueden comparar ni reproducir (`CLAUDE.md`, *Pipeline ML*).

**P9. ¿Qué ofrece la API?**
`GET /health`, `GET /modelos`, `POST /prediccion/retraso` y
`POST /prediccion/mas-de-5min` (ambos con `?horizonte=` y `?explicar=true`, que
devuelve contribuciones SHAP), y la demo `GET /vivo/paradas` y
`GET /vivo/parada/{stop_id}` (`api/main.py:14-26`; `api/routers/prediccion.py:29-67`;
`api/routers/vivo.py:21-39`). Errores: 422 por entrada inválida, 503 sin modelo o sin
datos, 404 parada desconocida.

**P10. ¿Qué está implementado y qué no?**
*Implementado y con tests* (`CLAUDE.md`, *Estado*; `docs/00_tema_y_alcance.md:79-98`):
ingesta, tracking, map-matching, etiquetado, `prepare`, features, entrenamiento,
evaluación con baselines, SHAP, API, UI NiceGUI y demo en vivo por parada. *Pendiente*
(`docs/00_tema_y_alcance.md:99-104`; `docs/07_decisiones.md:1141-1152`):

- Meteorología: la capa 157 se captura desde el 09/11 pero no pasa por `curar` (issue #8)
  ni es variable del modelo (`incluir_meteo: false`, `params.yaml`).
- Servido en tiempo real **incremental** (ADR-016): hoy hay demo por parada sobre el
  crudo, sin broker, y **no es un resultado**.
- Correo al Ajuntament/EMT sobre condiciones de uso (anexo).
- Tema cerrado con el tutor.
- Cadencia de la capa 192, sin remedir (pendiente de decidir).
- Defecto conocido del tracker con paradas y giros reales, `xfail(strict=True)`
  (`tests/test_tracking_realismo.py`).

## Ejercicio

1. **Dibuja de memoria** el grafo de dependencias de la P1, sin mirar. Luego compáralo
   con `CLAUDE.md` y marca qué flechas olvidaste.
2. Para cada regla de la P1, escribe **una frase** de qué se rompe el día que se cruza y
   si el daño da la cara o no. (Ejemplo: `features.py` duplicado → train/serve skew: no
   da la cara, el modelo sigue prediciendo.)
3. Tabla de 5 filas: *qué está implementado / qué falta / dónde se ve* y léela en voz alta
   sin dudar. Es la pregunta de cierre del tribunal.

## Mis respuestas / dudas

