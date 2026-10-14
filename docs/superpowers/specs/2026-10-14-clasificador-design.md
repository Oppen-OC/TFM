# Clasificador «más de 5 minutos tarde»: diseño

_Diseño aprobado en conversación el 14/10/2026, sección a sección. El
protocolo de la sección «Protocolo» se commitea como ADR-025 antes de traer la
prueba del ADR-024 (21/10)._

## Problema

El ADR-006 fijó una variante binaria del objetivo, `retraso > 300 s`, para el
endpoint de la API: es lo que consume un usuario («¿llego tarde?»). El alcance
de `docs/00_tema_y_alcance.md` la incluye. La etiqueta ya existe:
`features.construir` escribe `retraso_siguiente_parada_s_bin` en las tablas de
todos los horizontes. Faltan el modelo, su evaluación y sus stages. En
`docs/07_decisiones.md` sigue pendiente decidir si se publica solo en las
bandas de intervalo largas.

La persistencia es un listón alto. En las filas de la población con datos
hasta el 04/10, que con el corte del ADR-024 son entrenamiento:

| | h = 1 | h = 5 |
|---|---|---|
| tasa base (`> 300 s`) | 6,1 % | 6,8 % |
| P(positivo \| ahora > 300 s) | 85 % | 75 % |
| P(positivo \| ahora ≤ 300 s) | 1,0 % | 3,0 % |
| F1 de la persistencia | 0,85 | 0,65 |

A *h* = 5, la persistencia no detecta el 42 % de los positivos. Son los buses
que cruzan el umbral entre la parada *i* y la *i* + *h*. Ahí es donde un
clasificador tiene que justificar que existe.

La prueba del 07 al 19/10 no la ha visto nadie. Si el protocolo se fija antes
de traerla, la cifra del clasificador también sale limpia.

## Decisiones

1. **Papel: descriptivo y para la API.** No tiene hipótesis primaria propia,
   que se sumaría a la del ADR-024 sin corrección por multiplicidad. El
   protocolo se fija antes del 21/10 y se evalúa una vez sobre la prueba.
2. **Horizontes: el barrido entero**, *h* = 1, 2, 3, 5 y 10 (ADR-023). Así la
   curva de antelación cubre también «¿llego tarde?».
3. **Bandas.** Se entrena con todas las filas (ADR-018: nada se recorta). La
   cifra titular va en las bandas de intervalo de más de 15 min. Un bus con más
   de medio intervalo de retraso se asigna al viaje siguiente y parece puntual
   (bitácora 038). El truncamiento cae en (H − 120)/2, y solo supera los 300 s
   con intervalos de más de 12 min. Con el corpus hasta el 04/10, el 53 % de los
   buses que salen con más de 300 s se pliega. Por encima de 15 min, el pliegue
   baja del 2 %.
4. **Enfoque: clasificador propio, con la regresión umbralizada como listón.**
   Descartados:
   - *Solo la regresión umbralizada* (ŷ > 300). Con pérdida absoluta, ŷ estima
     la mediana condicional y la regla equivale a P > 0,5. No da probabilidad
     ni deja elegir el punto de operación, y con un 6 % de positivos pierde la
     mayoría de los cruces. Entra como listón.
   - *Regresión con calibración isotónica.* La calibración saldría del modelo
     de parada temprana y se aplicaría al reajustado con todo el entrenamiento.
     En la cola del 6 % tiene pocos puntos.
5. **Sin la capa 192.** La aportación del tráfico la decide el ADR-024. Meterla
   aquí le abriría una segunda vía que no se prerregistró.

## Protocolo (ADR-025)

- **Etiqueta:** `retraso_siguiente_parada_s_bin`, es decir, el objetivo
  `> features.umbral_retraso_s` (300 s, en sentido estricto: 300 s exactos son
  negativo).
- **Población:** `features.poblacion`, la misma que la regresión (ADR-022). El
  nowcast no entra.
- **Modelo:** XGBoost con `params.yaml → train`, salvo `objective:
  binary:logistic` y `eval_metric: logloss`, que se fijan en el código. Sin
  residuo, sin `scale_pos_weight` (para no deformar la probabilidad) y sin
  ajustar hiperparámetros. Las variables son las de `features.variables` con
  `trafico=False`. Parada temprana en la validación (28/09-04/10,
  `train.dias_validacion`) y reajuste con todo el entrenamiento, como en
  `train.entrenar`.
- **Umbral de decisión τ:** el que maximiza F1 sobre la población de la
  validación, con la predicción del modelo de parada temprana. Se avisa si
  P ≥ τ, la misma convención que `precision_recall_curve`. Se guarda en el
  artefacto y la prueba no lo modifica. Si la validación no tiene positivos,
  no hay τ: el entrenamiento se para con un error en vez de inventárselo.
- **Listones**, sobre las mismas filas:
  - horario: nunca positivo; solo da contexto;
  - persistencia: `retraso_s > 300`;
  - persistencia del tramo: `retraso_s + tramo_sesgo_s > 300`, con el sesgo
    nulo como 0 (`features.predicciones_baseline`);
  - regresión umbralizada: `ŷ > 300`, con el modelo de regresión del mismo
    horizonte.
- **Métricas.** Todas son descriptivas.
  - Tasa base, siempre al lado de cualquier otra cifra (ADR-006).
  - PR-AUC (`average_precision_score`) de cada uno, con su puntuación continua:
    P en el clasificador, `retraso_s` en la persistencia, `retraso_s +
    tramo_sesgo_s` en la del tramo y ŷ en la regresión. Solo el valor puntual.
  - Brier, solo del clasificador.
  - Precisión, sensibilidad y F1 en el punto de operación: τ en el
    clasificador y 300 s en los listones. Sin positivos predichos, la
    precisión es nula; sin positivos ni predichos ni reales, F1 también.
  - **Diferencia de F1, clasificador menos listón** (positivo: el clasificador
    acierta más), frente a la persistencia, la persistencia del tramo y la
    regresión umbralizada. Se dan los dos IC 95 %, uno remuestreando viajes y
    otro remuestreando días de servicio (ADR-018). Se suman VP, FP y FN por
    grupo, igual que `evaluate.diferencia` suma los errores. F1 = 2 VP / (2 VP
    + FP + FN). Son `evaluate.REPLICAS` réplicas con `evaluate.SEMILLA`. Si una
    réplica tiene el denominador a cero, cuenta como nula y queda fuera del
    percentil.
- **Estratos:**
  - **titular:** bandas de intervalo `15-30 min` y `> 30 min` juntas
    (`evaluate.banda_intervalo`);
  - conjunto de la población;
  - por banda, las cinco, incluida `sin_intervalo`. Las de 15 min o menos, con
    el aviso de la bitácora 038;
  - por estado actual: `retraso_s > 300` («ya tarde») o no («aún no»). Se sabe
    al predecir. Muestra si el modelo detecta los cruces del umbral o solo
    repite la persistencia.

  Un estrato vacío da `{"filas": 0}`, como en `evaluate.comparacion_trafico`.
  Lo que no se puede calcular sale nulo, nunca NaN: el JSON se escribe con
  `allow_nan=False`.
- **Una ejecución sobre la prueba**, en el mismo `dvc repro` que las
  comparaciones del ADR-024. Lo que se haga después de mirar es exploratorio y
  se declara.

## Componentes

| fichero | cambio |
|---|---|
| `src/project/features.py` | `salidas` añade la clave `clasificador`: `models/model_clasificador.pkl`, y `models/h<h>/model_clasificador.pkl` en el barrido. |
| `src/project/train.py` | `_xgb` acepta la clase de XGBoost. Una función devuelve τ a partir de P y la etiqueta de validación. `entrenar_clasificador` hace la parada temprana, calcula τ, reajusta con todo y devuelve `{modelo, columnas, categorias, umbral, n_arboles, validacion, mlflow_run_id}`. En `validacion`: días, tasa base, τ, PR-AUC y F1 del clasificador y de las dos persistencias. La regresión umbralizada se compara solo en `evaluate.py`, que carga los dos modelos. `main` admite `--clasificador`, excluyente con `--trafico`. Experimento de MLflow `retraso_mas_de_5min`. |
| `src/project/predict.py` | `probabilidad(art, tabla)` devuelve P(retraso > 300 s) con el índice de `tabla`, pasando por `features.matriz` con las categorías guardadas. `predecir` no cambia. Es lo que usará `services/`. |
| `src/project/evaluate.py` | La comprobación de pareja exige al clasificador y a la regresión del mismo horizonte las mismas columnas, las mismas categorías y los mismos días de validación; si no, se niega a evaluar. La diferencia de F1 por grupo, la comparación por estratos y `main` con `--clasificador`, que escribe `clasificador.json` en la carpeta de métricas de su horizonte y lo registra en el run del clasificador. |
| `dvc.yaml` | `train_clasificador`, `evaluate_clasificador` y sus versiones `_h` en `features.horizontes_barrido`. `evaluate_clasificador` depende del modelo de regresión (el listón), de `data/raw/gtfs` (las bandas) y de `features.umbral_retraso_s`. |
| `params.yaml` | Sin claves nuevas. |
| `.claude/tests/test_memoria.py` | Los cuatro stages nuevos en `documentados`. |

`scikit-learn` ya es dependencia (1.9): `precision_recall_curve`,
`average_precision_score` y `brier_score_loss`. `api/` no lo importa.

## Tests y mutantes

En `tests/test_modelo.py`, con datos sintéticos. Cada uno con un mutante en
`auditoria/catalogo.toml` que lo pone en rojo, desde el 163:

1. τ sale de la validación: con un entrenamiento y una validación que piden
   umbrales distintos, se elige el de la validación.
2. El clasificador ve exactamente `features.variables`, sin la 192.
3. Si la pareja está cruzada (categorías o días de validación distintos), la
   evaluación se niega a correr.
4. Los listones cortan en `> 300` estricto: una fila con 300 s exactos es
   negativa.
5. El F1 puntual coincide con el calculado a mano. Su IC remuestrea viajes, no
   filas: un viaje con muchas filas repetidas no estrecha el intervalo.
6. El titular junta solo `15-30 min` y `> 30 min`, y las filas fuera de la
   población no cuentan.

## Calendario

**Antes del 21/10**, en este orden:

1. Commitear el ADR-025 en `docs/07_decisiones.md` con el contenido de
   «Protocolo». Es el prerregistro. Cierra el pendiente «variante binaria por
   banda de intervalo».
2. Código, tests y mutantes, con TDD.
3. **Ensayo sin `dvc repro`**: `uv run python -m project.train --clasificador`
   y `evaluate --clasificador` sobre las tablas que ya hay en `data/processed/`.
   Son del corte antiguo: el entrenamiento llega al 20/09 y la prueba es el
   21/09-04/10, que con el corte nuevo ya es entrenamiento. Se comprueba que
   corre, que τ está en el artefacto, que el JSON sale con su forma, que la
   pareja pasa y cuánto dura el entrenamiento. No se ajusta nada por lo que
   salga. Después se borran los artefactos del ensayo.
4. `dvc status` muestra solo los stages nuevos sin ejecutar.
5. `CLAUDE.md`: la lista de stages de «Pipeline ML».

**El 21/10 o después**, en el plan de
`docs/superpowers/plans/2026-10-11-fase2-trafico.md`:

- En la tarea 12, el paso 4 añade `train_clasificador train_clasificador_h`, y
  el paso 5 comprueba también los días de validación de los clasificadores
  (quince modelos, no diez).
- La tarea 13 no cambia: su `dvc repro` ejecuta `evaluate_clasificador` y
  `evaluate_clasificador_h` con lo demás, una vez.
- Después, una entrada de bitácora con los resultados descriptivos.

## Límites declarados

- τ se elige con el modelo de parada temprana y se aplica al reajustado. Es el
  mismo límite que tiene `n_arboles` en la regresión.
- La prueba tiene dos festivos (09 y 12/10) y otra tasa base. F1 depende de la
  tasa base, así que se informa siempre al lado.
- Fuera de las bandas largas, la etiqueta pierde positivos por el pliegue
  (bitácora 038). Por eso el titular va en más de 15 min.
- Son cinco entrenamientos más. El ensayo da su duración.

## No-objetivos

- Endpoint, `services/` y UI: van en un trabajo aparte, que usa
  `predict.probabilidad` y τ del artefacto.
- Ajustar hiperparámetros, la capa 192 en el clasificador, calibrar después y
  SHAP.
- Otros umbrales (120 s, 600 s).
- Los estratos por línea, por grupo de soporte y por horizonte útil, y el
  nowcast.
