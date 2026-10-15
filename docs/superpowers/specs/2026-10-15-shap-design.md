# Explicación SHAP de los modelos: diseño

_Diseño aprobado en conversación el 15/10/2026. Va después del servicio por
API (`docs/superpowers/specs/2026-10-15-servicio-api-design.md`), cuyas
respuestas amplía. Tiene que estar listo antes del 21/10: corre en el
`dvc repro` de la fase B del ADR-024 y se repite cuando lleguen más datos._

## Problema

El tribunal preguntará qué usa el modelo. La pregunta de investigación pide,
además, cuánto pesa el tráfico. Las métricas dicen cuánto acierta cada modelo,
no por qué. CLAUDE.md tiene `shap` como dependencia pendiente. La API, por su
parte, devuelve una cifra sin decir de dónde sale.

## Decisiones

1. **Un cálculo, dos usos.** Explicación global para la memoria y explicación
   de cada petición en la API, las dos con la misma función.
2. **Valores nativos de XGBoost** (`pred_contribs=True`, TreeSHAP exacto), no
   los de la librería `shap`. Comprobado el 15/10 sobre `models/model.pkl`: 26
   columnas (25 variables más el sesgo), y la suma reproduce la salida bruta
   con un error máximo de 1,1e-4, el redondeo de `float32`. `shap` entra solo
   para las figuras.
3. **La global, sobre la prueba y después de la evaluación única.** Los
   stages dependen de las métricas de `evaluate*`, así que corren detrás. Explicar
   el modelo no cambia ninguna cifra prerregistrada; se declara descriptivo.
   La validación queda descartada porque sus filas están dentro del reajuste
   final. Se repite cuando lleguen datos nuevos, como el resto del pipeline.
4. **Tres modelos por horizonte**: la regresión sin tráfico, la regresión con
   la capa 192 (la que responde a la pregunta de investigación) y el
   clasificador del ADR-025. La API solo explica los dos que sirve.

## Qué se explica, y en qué unidad

- **La regresión v2 es de residuo** (ADR-021): los árboles predicen
  ŷ − `retraso_s`. Sus contribuciones explican ese residuo, en segundos:
  ŷ = `retraso_s` + sesgo + Σ contribuciones. La persistencia queda como la
  línea base explícita, que es lo que el modelo corrige. Con un artefacto que no
  sea de residuo, la base es 0 y las contribuciones explican ŷ entero. El
  artefacto dice cuál de los dos casos es (`artefacto["residuo"]`).
- **El clasificador** se explica en log-odds de «más de 5 min», no en
  probabilidad: es la escala en la que las contribuciones suman.

## Componentes

| fichero | cambio |
|---|---|
| `src/project/predict.py` | `contribuciones(artefacto, tabla) -> pd.DataFrame`: una columna por variable del artefacto más `sesgo`, con el índice de `tabla`. Pasa por `features.matriz`, como `predecir`. |
| src/project/explicar.py (nuevo) | `GRUPOS`: cada variable en un grupo. `resumen(contrib, t)`: media de \|SHAP\| por variable y por grupo, sobre la población (ADR-022) y en el estrato con sensor (`evaluate.estratos_trafico`, `CON_SENSOR`). `figuras(...)`: las PNG. `main(horizonte)`: carga los tres modelos y la prueba, y escribe el JSON y las figuras. En MLflow, cada modelo recibe en su propio run (`mlflow_run_id` del artefacto) su parte del JSON y sus figuras, como hace `evaluate`. |
| `services/model_service.py` | Con `explicar=True`, las respuestas añaden las contribuciones. |
| `api/schemas.py` y api/routers/prediccion.py | `?explicar=true` (por defecto `false`) y el esquema `Contribuciones`. |
| `dvc.yaml` | `explicar` y `explicar_h` (`foreach` del barrido). Dependencias: la tabla de prueba, los tres modelos, src/project/explicar.py, `predict.py`, `features.py`, `evaluate.py` y las tres métricas de `evaluate*` del horizonte, que fijan el orden. Salidas: el JSON (`metrics`, `cache: false`) y la carpeta de figuras (`outs`, `cache: false`). |
| `pyproject.toml` | `shap`, añadido con `uv add`. |
| `.claude/tests/test_memoria.py` | Los dos stages en `documentados`. |
| `CLAUDE.md` | La lista de stages y «Dependencias todavía por añadir». |

### Grupos

| grupo | variables |
|---|---|
| persistencia | `retraso_s`, `retraso_lag1_s`, `retraso_lag2_s`, `retraso_delta_s` |
| recorrido | `t_prog_hasta_objetivo_s`, `dist_objetivo_m`, `stop_sequence`, `abscisa_parada_m` |
| línea en servicio | `linea_retraso_*`, `linea_pasos_*`, `bus_anterior_retraso_s`, `bus_anterior_edad_s` |
| flota en el tramo | `tramo_ganado_*`, `tramo_soporte_*` |
| sesgo del horario | `tramo_sesgo_s` |
| calendario | `hora`, `dia_semana`, `fin_de_semana` |
| identidad de la línea | `linea` |
| tráfico (capa 192) | `features.TRAFICO` |

Un test exige que cada variable de `features.variables` con todas las opciones
activas caiga en un solo grupo. Así, una variable nueva no puede quedarse fuera
del resumen sin que algo falle.

## Salidas

- metrics/explicacion.json y metrics/horizontes/h<h>/explicacion.json. Por
  modelo (`regresion`, `regresion_trafico` y `clasificador`):
  - `unidad`: «s del residuo» o «log-odds»;
  - `filas`;
  - `sesgo`;
  - `media_abs` por variable y por grupo, en dos estratos: `poblacion` y
    `con_sensor`.

  El estrato con sensor es donde la capa 192 tiene algo que decir: medida sobre
  todo el conjunto, se diluye. Como en el resto del pipeline, un estrato vacío
  da `{"filas": 0}` y el JSON se escribe con `allow_nan=False`.
- figuras/shap/h<h>/, también para h = 1: DVC no deja que una salida contenga
  a otra, y la carpeta de h = 1 contendría las del barrido. Para cada modelo:
  - el resumen (beeswarm);
  - la dependencia de `tramo_sesgo_s`, de `tramo_ganado_15min` y, en el modelo
    con tráfico, de `trafico_congestion_frac`.

  El JSON y las figuras salen de la misma muestra fija de 20.000 filas de la
  población, con `evaluate.SEMILLA`. **Por qué una muestra** (medido el 15/10
  sobre los modelos del corte antiguo): TreeSHAP con 705-775 árboles de
  profundidad 8 va a unas 300 filas/s. La población entera de h = 1, 451.671
  filas, serían 25 min por regresión y más de 4 h los cinco horizontes. El
  clasificador, con 148 árboles, va a 4.000 filas/s. El JSON guarda el tamaño
  de la muestra y el de la población.

## API

`POST /prediccion/retraso` y `POST /prediccion/mas-de-5min` aceptan
`?explicar=true`. La respuesta añade:

```json
"contribuciones": {
  "unidad": "s del residuo",
  "base": 140.0,
  "sesgo": 3.1,
  "principales": [{"variable": "tramo_sesgo_s", "valor": 41.2}, "..."],
  "resto": -2.4
}
```

- `principales` son las 5 de mayor valor absoluto.
- `resto` suma las demás, para que la cuenta cierre: `base` + `sesgo` +
  Σ `principales` + `resto` es la salida bruta. En la regresión, `base` es
  `retraso_s` si el modelo es de residuo y 0 si no.
- Sin `explicar`, la respuesta no cambia.

## Pruebas y mutantes

En tests/test_explicar.py y tests/test_servicio.py, con los artefactos
sintéticos de `tests/test_modelo.py`:

1. **Aditividad.** `sesgo` + Σ contribuciones = salida bruta, con tolerancia
   1e-3, en la regresión de residuo (más `retraso_s` da `predecir`) y en el
   clasificador (log-odds).
2. **Índice.** `contribuciones` conserva el índice de la tabla aunque llegue
   desordenada (trampa 012).
3. **Grupos.** Toda variable cae en un solo grupo.
4. **Población.** El resumen no cuenta filas fuera de `features.poblacion`.
5. **API.** Con `explicar=true` la cuenta cierra con la predicción devuelta;
   sin él, la respuesta es la de antes.

Mutantes, desde el siguiente id libre de `auditoria/catalogo.toml`:

- olvidar `retraso_s` en la base del residuo;
- devolver las contribuciones por posición y no por índice;
- quitar el filtro de población;
- dejar una variable sin grupo.

## Primer paso: compatibilidad de `shap`

Antes de nada se comprueba que `uv add shap` resuelve con numpy 2.4, XGBoost
3.2 y Python 3.11, y que `shap.plots.beeswarm` dibuja un `shap.Explanation`
construido a mano. Si falla, `shap` no entra y las figuras se dibujan con
matplotlib, que ya está instalado: barras de media |SHAP| y dispersión de la
dependencia. Eso no cambia nada más del diseño.

## Calendario

- **Antes del 21/10**, en este orden:
  1. el plan del servicio por API;
  2. este plan.
  3. Un ensayo de `explicar` sobre las tablas del corte antiguo, sin
     `dvc repro`. Los modelos con tráfico y los clasificadores todavía no
     existen: el ensayo los entrena a mano sobre esas mismas tablas, con
     `train --trafico` y `train --clasificador`, y después borra todo lo que
     haya escrito, artefactos, métricas, figuras y runs de MLflow, como en la
     tarea 6 del plan del clasificador. `explicar.main` exige los tres modelos,
     y en el pipeline DVC lo garantiza.
- **El 21/10:** el `dvc repro` de la tarea 13 del plan de la fase 2 los
  ejecuta detrás de la evaluación. Su commit añade figuras/shap/.

## No-objetivos

- Interacciones SHAP y explicaciones de modelos que no sean de árboles.
- Cambiar variables o hiperparámetros por lo que salga.
- La UI de Streamlit.
- Explicar con la validación o el entrenamiento.
