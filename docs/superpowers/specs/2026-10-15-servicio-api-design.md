# Servicio de predicción por API: diseño

_Diseño aprobado en conversación el 15/10/2026. Va antes que SHAP
(`docs/superpowers/specs/2026-10-15-shap-design.md`), que amplía sus
respuestas._

## Problema

La API solo tiene `/health`. `services/model_service.py` está vacío,
`api/routers/predict.py` también, y `api/schemas.py` guarda los modelos de la
plantilla. El ADR-006 fija qué consume un usuario: el retraso en segundos y
la variante binaria `> 300 s`. El ADR-025 deja el clasificador listo para
servirlo con su probabilidad y su τ. Falta la capa que carga los modelos y los
endpoints que los sirven, probables desde Swagger (`/docs`).

## Decisiones

1. **La entrada es el vector de variables del modelo**, las 25 de
   `features.variables`, ya calculadas. Es el contrato que usará después el
   servido en tiempo real (ADR-016), que solo tendrá que construir el vector.
   No se repiten filas guardadas: si la tabla fuera la prueba, se mirarían
   predicciones antes de la evaluación única del 21/10.
2. **Dos endpoints, un modelo cada uno**: el retraso (regresión v2 sin
   tráfico) y más de 5 min (clasificador del ADR-025). Si falta uno, el otro
   sigue funcionando. Hoy no hay clasificador: lo crea el `dvc repro` del 21/10.
3. **Todos los horizontes**: 1 y `features.horizontes_barrido` (2, 3, 5, 10).
   Por defecto, `features.horizonte_paradas` (1).
4. **Sin los modelos con la capa 192**: su aportación la decide el ADR-024.

## Contrato

| método y ruta | entrada | salida |
|---|---|---|
| `GET /health` | — | `{"status": "ok"}` (sin cambios) |
| `GET /modelos` | — | por horizonte y modelo: `columnas`, `n_arboles`, `mlflow_run_id`, `dias_validacion`; el clasificador, además, `umbral` y `tasa_base_validacion` |
| `POST /prediccion/retraso?horizonte=h` | `{"variables": {...}}` | `{"horizonte_paradas", "retraso_s"}` |
| `POST /prediccion/mas-de-5min?horizonte=h` | `{"variables": {...}}` | `{"horizonte_paradas", "probabilidad", "umbral", "llega_tarde", "tasa_base_validacion"}` |

- `llega_tarde` es `probabilidad >= umbral`, la convención con la que se eligió
  τ (ADR-025). La tasa base va al lado, como exige el ADR-006.
- `variables` es un `dict[str, float | str | None]`. Las claves deben ser
  **exactamente** las columnas del artefacto de ese horizonte: ni una más ni
  una menos. Los valores pueden ser nulos, porque `bus_anterior_*`,
  `tramo_ganado_*` y otras son nulas de verdad en los datos, y XGBoost las
  trata como faltantes igual que en el entrenamiento. `linea` es texto; el
  resto, números o nulos.
- El cuerpo trae en Swagger un **ejemplo real**, el vector de una fila de
  **entrenamiento**, nunca de la prueba, para que «Try it out» funcione sin
  teclear. Un test exige que sus claves sean `features.variables` con la
  configuración de `params.yaml`.

## Capas

- **`api/schemas.py`**: los modelos Pydantic de entrada y de salida, con el
  ejemplo. No importa pandas ni conoce la lista de variables, salvo en el
  ejemplo.
- **api/routers/prediccion.py**: los tres endpoints, incluidos con
  `include_router` en `main.py`. Validan, delegan en `services/` y traducen sus
  errores a HTTP. Se borran `api/routers/predict.py` (vacío) y los modelos de la
  plantilla.
- **`services/model_service.py`**: la única capa que carga modelos (CLAUDE.md).
  - Carga todos los artefactos una vez, al arrancar, desde el `lifespan` de
    FastAPI. Las rutas salen de `features.salidas(h)` y los horizontes, de
    `params.yaml`. Un fichero que falta no tumba el arranque: ese modelo queda
    como no disponible.
  - Valida las claves y los tipos del vector contra `artefacto["columnas"]`.
  - Construye una fila con las columnas numéricas en `float64` y `linea` en
    texto, y llama a `predict.predecir` o `predict.probabilidad`, que pasan por
    `features.matriz`. Así no hay desviación entre entrenamiento y servido, y
    una línea que el modelo no vio da predicción en vez de error (bitácora
    040).
  - Devuelve tipos de Python, no de pandas.

**Por qué el `float64` es obligatorio.** Comprobado el 15/10 sobre
`models/model.pkl`: una fila construida desde JSON con algún nulo deja esas
columnas como `object`, y XGBoost la rechaza («DataFrame.dtypes for data must
be int, float, bool or category»). Convertidas a `float64`, 200 filas reales
dan exactamente la misma predicción que desde la tabla (diferencia máxima 0,0).

## Errores

| caso | código | cuerpo |
|---|---|---|
| falta o sobra alguna variable | 422 | las que faltan y las que sobran, por nombre |
| `linea` no es texto, o un número no es número | 422 | la variable y el tipo esperado |
| horizonte fuera de 1, 2, 3, 5 y 10 | 422 | los horizontes válidos |
| horizonte válido sin su modelo cargado | 503 | qué modelo y qué horizonte faltan |

`services/` lanza excepciones propias (`VariablesInvalidas` y
`ModeloNoDisponible`) y el router las traduce a HTTP. `services/` no importa
nada de `api/`.

## Pruebas y mutantes

- `tests/test_api.py` mockea `services/` y no carga modelos reales (CLAUDE.md).
  Cubre los tres endpoints, el 422, el 503 y que `/openapi.json` lleva el
  ejemplo.
- tests/test_servicio.py prueba `services/` con artefactos sintéticos
  diminutos en `tmp_path`, entrenados con el patrón de `tests/test_modelo.py`:
  - la predicción coincide con `predict.predecir` sobre la misma fila;
  - una fila con nulos predice;
  - una línea no vista predice;
  - P = τ da `llega_tarde`;
  - una clave que falta, o que sobra, se rechaza;
  - un artefacto que falta deja el otro disponible;
  - las claves del ejemplo de Swagger son `features.variables`.
- Mutantes, desde el siguiente id libre de `auditoria/catalogo.toml`:
  - aceptar claves de más;
  - avisar con `>` en vez de `>=`;
  - quitar la conversión a `float64`;
  - que un modelo ausente tumbe el arranque.
- Comprobación a mano: `uv run uvicorn project.api.main:app --port 8000`,
  `/docs` y la petición de ejemplo contra el `models/model.pkl` real, que debe
  dar 200. El clasificador da 503 hasta el 21/10.

## No-objetivos

- El tiempo real y el cálculo de variables en vivo (ADR-016).
- Los modelos con la capa 192.
- La UI de Streamlit, autenticación, Docker y despliegue.
- SHAP: va en su spec, y amplía estas respuestas con `?explicar=true`.
- Lotes de varias filas por petición.
