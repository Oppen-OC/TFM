# Clasificador «más de 5 min tarde» — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dejar prerregistrado (ADR-025), construido, probado y con sus stages el clasificador de `retraso > 300 s` **antes del 21/10**, para que corra una sola vez sobre la prueba del 07 al 19/10 en el mismo `dvc repro` que el ADR-024.

**Architecture:** XGBoost `binary:logistic` con las variables y la configuración de la regresión sin tráfico, entrenado por `train.entrenar_clasificador` con parada temprana y umbral de decisión τ sacados de la validación. `evaluate.comparacion_clasificador` lo enfrenta, sobre las mismas filas de la población, a la persistencia, la persistencia del tramo y la regresión umbralizada del mismo horizonte, con la diferencia de F1 y sus intervalos por viajes y por días. Stages de DVC nuevos para h = 1 y para el barrido.

**Tech Stack:** Python 3.11, pandas, XGBoost 3.2, scikit-learn 1.9 (ya instalado), DVC, MLflow, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-10-14-clasificador-design.md`, aprobada sección a sección el 14/10.

## Global Constraints

- **Prohibido `dvc repro` antes del 21/10.** El crudo del 07 al 12/10 ya está en `data/raw/`, y `features.partir` lo metería en la prueba. Ninguna tarea de este plan ejecuta stages de DVC.
- Etiqueta: `retraso_siguiente_parada_s_bin`, que es el objetivo `> features.umbral_retraso_s` (300 s) en sentido **estricto**. 300 s exactos son negativo, también en los listones y en el estado actual.
- Población: `features.poblacion` (ADR-022), la misma que la regresión.
- Modelo: `params.yaml → train`, salvo `objective: binary:logistic` y `eval_metric: logloss`. Sin residuo, sin `scale_pos_weight`, sin la capa 192 y sin ajustar hiperparámetros.
- τ: el de mejor F1 en la validación, calculado con la predicción del modelo de parada temprana. Se avisa si **P ≥ τ**. Si la validación no tiene positivos, error.
- Listones: horario (nunca avisa), persistencia `retraso_s > 300`, persistencia del tramo `retraso_s + tramo_sesgo_s > 300` (sesgo nulo = 0, `features.predicciones_baseline`) y regresión umbralizada `ŷ > 300`, con el modelo de regresión del mismo horizonte.
- Titular: bandas `15-30 min` y `> 30 min`. Después, el conjunto, `por_banda` y `por_estado_actual` (`ya tarde` / `aún no`).
- Intervalos: `evaluate.REPLICAS` (1000) réplicas con `evaluate.SEMILLA` (0), remuestreando viajes y remuestreando días.
- Lo que no tiene cifra sale nulo, nunca NaN. El JSON se escribe con `allow_nan=False`.
- Horizontes: 1 (sin carpeta) y `features.horizontes_barrido` (2, 3, 5, 10).
- `src/project/` no importa de `analysis/`. Ningún `os.getenv`. Las rutas salen de `settings` y de `features.salidas`. `api/` no importa sklearn.
- Los `.md` de `docs/` pasan `.claude/tests/test_memoria.py`: toda ruta citada entre comillas invertidas (con `/` y extensión) debe existir, y toda función citada como nombre seguido de `()` también. Las rutas de `metrics/` que aún no existen se escriben **sin** comillas invertidas.
- Commits en `develop`, sin push. Siempre `uv`, nunca `pip`. No leer `.env`.
- Subagentes en Sonnet (agente `pipeline-dvc` en las tareas 2-5). Las tareas 1, 6 y 7 van en línea.
- `uv run pytest` en verde, salvo el `xfail` estricto ya conocido de `tests/test_tracking_realismo.py`.

## Review Focus

1. **Una fila con P exactamente igual a τ.** Lo esperable es que se avise (`>=`, la convención de `precision_recall_curve` con la que se eligió τ). Lo guarda la llamada con τ = 0,9 del test de la tarea 2 (mutante 173).
2. **Una línea de la prueba que el entrenamiento no vio** (en la prueba aparece la 8). Lo esperable es una probabilidad y no un error que tire la evaluación. Lo guarda la línea Z del test de variables de la tarea 3.
3. **Una validación sin ningún positivo.** Lo esperable es un error explícito, no un τ arbitrario. Lo guarda el test de la tarea 3 (mutante 174).
4. **`tramo_sesgo_s` nulo.** Lo esperable es que el listón del tramo lo cuente como 0, como en la regresión. Lo guarda el grupo B del test de la tarea 2.
5. **Un estrato sin positivos ni avisos.** Lo esperable es F1 nulo, no 0 ni NaN, y un JSON que se puede escribir con `allow_nan=False`. Lo guarda el subconjunto C del test de la tarea 2.

---

## Task 1: ADR-025 (prerregistro, en línea)

**Files:**
- Modify: `docs/07_decisiones.md` (tras el ADR-024, antes de «Pendientes de decidir»)

**Interfaces:** el ADR es la fuente de verdad de las tareas 2-7.

- [ ] **Step 1: insertar el ADR-025.** En `docs/07_decisiones.md`, sustituir

```markdown
    dejaría un hueco en ella.

---

## Pendientes de decidir
```

por

```markdown
    dejaría un hueco en ella.

---

## ADR-025 · El clasificador de más de 5 min es descriptivo y su protocolo se fija antes de la prueba · cerrada

Escrito y commiteado **antes** de entrenar ningún clasificador y de traer la
prueba del ADR-024 (07-19/10). Diseño completo en
`docs/superpowers/specs/2026-10-14-clasificador-design.md`.

**Pregunta.** ¿Cuánto mejor que los listones dice un modelo si un bus llegará
con más de 5 min de retraso a la parada *i* + *h*?

**Decisión.**
1. **Descriptivo**, sin primaria propia: se sumaría a la del ADR-024 sin
   corrección por multiplicidad. Alimenta el endpoint de la API (ADR-006).
2. **Etiqueta y población.** `retraso_siguiente_parada_s_bin`: el objetivo pasa
   de `features.umbral_retraso_s`, 300 s, en sentido estricto. Las filas de
   `features.poblacion` (ADR-022).
3. **Modelo.** XGBoost con `params.yaml → train`, salvo `objective:
   binary:logistic` y `eval_metric: logloss`. Sin residuo, sin
   `scale_pos_weight`, sin la capa 192 y sin ajustar hiperparámetros. Parada
   temprana en la validación (28/09-04/10) y reajuste con todo el
   entrenamiento, como la regresión.
4. **Umbral de decisión τ:** el de mejor F1 en la validación, con el modelo de
   parada temprana; se avisa si P ≥ τ. Va dentro del modelo y la prueba no lo
   toca. Sin positivos en la validación no hay τ y el entrenamiento se para.
5. **Listones**, sobre las mismas filas: horario (nunca avisa; contexto),
   persistencia (`retraso_s > 300`), persistencia del tramo (`retraso_s +
   tramo_sesgo_s > 300`) y la regresión del mismo horizonte umbralizada
   (ŷ > 300). El clasificador y esa regresión tienen que salir del mismo
   entrenamiento: si no, la evaluación no corre.
6. **Métricas:** la tasa base al lado de todo; la PR-AUC de cada uno con su
   puntuación continua; el Brier del clasificador; precisión, sensibilidad y
   F1 en el punto de operación; y la diferencia de F1, clasificador menos
   listón, con el IC 95 % remuestreando viajes y remuestreando días (ADR-018).
   Lo que no se puede calcular sale nulo.
7. **Estratos.** Titular: las bandas de intervalo `15-30 min` y `> 30 min`.
   Después, el conjunto, cada banda y el estado actual (`retraso_s > 300` o
   no), que se sabe al predecir.
8. **Horizontes:** 1, 2, 3, 5 y 10 paradas (ADR-023). La prueba se evalúa
   **una vez**, en el mismo `dvc repro` que el ADR-024.

**Por qué.**
- Con los datos hasta el 04/10, la persistencia ya acierta tres de cada cuatro
  avisos a *h* = 5. Un clasificador tiene que mostrar dónde aporta, y el
  estrato del estado actual lo separa.
- Con intervalos de 15 min o menos, la asignación pliega al viaje siguiente la
  mitad de los buses con más de 5 min de retraso (bitácora 038). La etiqueta
  positiva pierde justo lo que se quiere detectar. Se entrena con todo
  (ADR-018) y el titular va donde la etiqueta es limpia.
- Fijar el protocolo antes de mirar la prueba es lo que hace defendible la
  cifra, aunque sea descriptiva.

**Consecuencias.**
- Cierra el pendiente «variante binaria por banda de intervalo».
- Stages `train_clasificador` y `evaluate_clasificador`, y sus `_h`. La fase B
  del plan del ADR-024 los añade a su `dvc repro`.
- La API usa la probabilidad y el τ del artefacto.
- Límites que se declaran: τ se elige con el modelo de parada temprana y se
  aplica al reajustado, como `n_arboles`; la prueba tiene dos festivos y otra
  tasa base, que se informa siempre al lado (ADR-006).

**Alternativas.**
- Solo la regresión umbralizada: equivale a avisar con P > 0,5, sin
  probabilidad ni punto de operación. Queda como listón.
- Calibrar la regresión con isotónica: el modelo calibrado no sería el
  reajustado, y la cola del 6 % tiene pocos puntos.
- Hipótesis primaria propia: otra primaria sin corrección por multiplicidad.
- Entrenar solo con las bandas largas: choca con el ADR-018 y deja sin
  respuesta a las líneas de intervalo corto.

**Qué la reabriría.** Que el titular de la prueba no tenga positivos con los
que medir, o que la prueba del ADR-024 se descarte.

---

## Pendientes de decidir
```

- [ ] **Step 2: cerrar el pendiente.** En la misma sección, borrar el punto entero:

```markdown
- **Variante binaria por banda de intervalo.** `evaluate.py` ya estratifica por
  banda de intervalo programado (≤ 8, 8-15, 15-30, > 30 min y `sin_intervalo`),
  como el estrato de sensores (bitácora 038). Falta decidir si la variante
  binaria se publica solo en las bandas largas: se decide con el clasificador.
```

- [ ] **Step 3: la documentación sigue en verde**

Run: `uv run pytest .claude/tests -q`
Expected: todo PASS.

- [ ] **Step 4: commit**

```bash
git add docs/07_decisiones.md
git commit -m "docs(decisiones): ADR-025, el clasificador de más de 5 min, prerregistrado antes de la prueba"
```

---

## Task 2: la comparación del clasificador en `evaluate.py` (agente `pipeline-dvc`)

**Files:**
- Modify: `src/project/evaluate.py` (imports; constantes tras `CONGESTION`; funciones nuevas tras `comparacion_trafico`)
- Test: `tests/test_modelo.py`

**Interfaces:**
- Consumes: `features.predicciones_baseline`, `features.poblacion`, `features.CLAVE_VIAJE`, `REPLICAS`, `SEMILLA` (ya existen).
- Produces:
  - `metricas_binarias(decision: pd.Series, real: pd.Series, puntuacion: pd.Series | None = None) -> dict` con las claves `precision`, `sensibilidad`, `f1` y, con puntuación, `pr_auc`. Valores `float` con 4 decimales, o `None`.
  - `diferencia_f1(dec_a, dec_b, real, grupo, replicas=REPLICAS) -> {"f1": float | None, "f1_ic95": [lo, hi]}`.
  - `comprobar_pareja_clasificador(clf: dict, reg: dict) -> None`, que lanza `ValueError`.
  - `comparacion_clasificador(t, prob, pred_regresion, objetivo, umbral_s, umbral_decision) -> dict` con las claves `dias`, `umbral_decision`, `titular`, `conjunto`, `por_banda` y `por_estado_actual`. `t` trae `_banda`. Cada estrato da `{"filas": 0}` si está vacío, o `filas`, `viajes`, `dias`, `tasa_base`, `brier_clasificador`, `metricas` (claves `clasificador`, `persistencia`, `persistencia_tramo`, `regresion` y `horario`) y `clasificador_menos` (claves `persistencia`, `persistencia_tramo` y `regresion`, cada una con `viajes` y `dias`).
  - Constantes `BANDAS_LARGAS`, `YA_TARDE`, `AUN_NO` y `LISTONES_BINARIOS`.

- [ ] **Step 1: tests que fallan.** En `tests/test_modelo.py`, añadir `import json` a los imports y, al final:

```python
BIN = OBJ + "_bin"


def _binaria():
    """Seis grupos de 4 viajes × 3 filas en dos días, con τ = 0,5. Cada grupo pone
    a prueba una frontera del ADR-025."""
    grupos = {
        # grupo: (banda, retraso ahora, sesgo del tramo, llega tarde, P, ŷ, previsto)
        # E va primero: tras el filtro de población el índice deja de ser contiguo.
        "E": ("> 30 min", 0.0, 0.0, True, 0.9, 0.0, -10.0),  # fuera de la población
        "A": ("15-30 min", 300.0, 0.0, True, 0.9, 350.0, 60.0),  # 300 s justos
        "B": ("> 30 min", 400.0, np.nan, True, 0.9, 350.0, 60.0),  # ya tarde
        "C": ("> 30 min", 0.0, 0.0, False, 0.1, 0.0, 60.0),  # puntual
        "D": ("<= 8 min", 0.0, 0.0, True, 0.1, 0.0, 60.0),  # banda corta
        "F": ("8-15 min", 0.0, 0.0, False, 0.9, 0.0, 60.0),  # banda corta
    }
    filas = [
        {
            "fecha_servicio": pd.Timestamp("2026-10-07") + pd.Timedelta(days=v % 2),
            "viaje_id": f"{g}{v}",
            "_banda": banda,
            "retraso_s": ahora,
            "tramo_sesgo_s": sesgo,
            "horizonte_previsto_s": previsto,
            "ultimo_conocido": True,
            OBJ: 400.0 if tarde else 0.0,
            BIN: int(tarde),
            "_p": p,
            "_reg": reg,
        }
        for g, (banda, ahora, sesgo, tarde, p, reg, previsto) in grupos.items()
        for v in range(4)
        for _ in range(3)
    ]
    t = pd.DataFrame(filas)
    return t, t["_p"], t["_reg"]


def test_el_clasificador_se_compara_con_los_listones_en_los_estratos_del_adr_025():
    t, p, reg = _binaria()
    r = evaluate.comparacion_clasificador(t, p, reg, OBJ, 300, 0.5)
    tit = r["titular"]
    # Sin la población entraría E; con la banda de 8-15 min, F.
    assert tit["filas"] == 36
    assert tit["tasa_base"] == 0.6667
    assert tit["brier_clasificador"] == 0.01
    m = tit["metricas"]
    assert m["clasificador"] == {
        "precision": 1.0,
        "sensibilidad": 1.0,
        "f1": 1.0,
        "pr_auc": 1.0,
    }
    # 300 s justos no pasan de 300: la persistencia no avisa al grupo A.
    assert m["persistencia"]["sensibilidad"] == 0.5
    assert m["persistencia"]["f1"] == 0.6667
    # El sesgo nulo de B cuenta como 0: 400 s siguen pasando de 300.
    assert m["persistencia_tramo"]["f1"] == 0.6667
    assert m["regresion"]["f1"] == 1.0
    assert m["horario"] == {"precision": None, "sensibilidad": 0.0, "f1": 0.0}
    d = tit["clasificador_menos"]["persistencia"]
    assert d["viajes"]["f1"] == 0.3333 and d["dias"]["f1"] == 0.3333
    assert tit["clasificador_menos"]["regresion"]["viajes"]["f1"] == 0.0
    # El conjunto: al clasificador se le escapa D y F es una falsa alarma.
    assert r["conjunto"]["filas"] == 60
    assert r["conjunto"]["metricas"]["clasificador"]["f1"] == 0.6667
    assert r["conjunto"]["metricas"]["persistencia"]["f1"] == 0.5
    # «Ya tarde» es más de 300 s ahora: solo B.
    assert r["por_estado_actual"]["ya tarde"]["filas"] == 12
    assert set(r["por_banda"]) == {"<= 8 min", "8-15 min", "15-30 min", "> 30 min"}
    json.dumps(r, allow_nan=False)
    # P igual a τ avisa: es la convención con la que se eligió τ.
    r = evaluate.comparacion_clasificador(t, p, reg, OBJ, 300, 0.9)
    assert r["titular"]["metricas"]["clasificador"]["f1"] == 1.0
    # Un estrato vacío no tira la única evaluación de la prueba.
    cortas = t["_banda"].isin(["<= 8 min", "8-15 min"])
    r = evaluate.comparacion_clasificador(t[cortas], p[cortas], reg[cortas], OBJ, 300, 0.5)
    assert r["titular"] == {"filas": 0}
    # Sin positivos ni avisos no hay F1: nulo, ni 0 ni NaN.
    c = t["viaje_id"].str[0] == "C"
    r = evaluate.comparacion_clasificador(t[c], p[c], reg[c], OBJ, 300, 0.5)
    assert r["titular"]["metricas"]["clasificador"]["f1"] is None
    assert r["titular"]["clasificador_menos"]["persistencia"]["viajes"]["f1"] is None
    json.dumps(r, allow_nan=False)


def test_la_diferencia_de_f1_remuestrea_viajes_y_no_filas():
    """30 viajes de 40 filas, todos tarde. El clasificador avisa a los 15 primeros
    enteros y el listón a ninguno: F1 = 2·½ / (2·½ + ½) = 2/3.

    Remuestreando filas, el intervalo saldría √40 ≈ 6 veces más estrecho.
    """
    n_viajes, filas = 30, 40
    viaje = pd.Series(np.repeat(np.arange(n_viajes), filas))
    real = pd.Series(True, index=viaje.index)
    a = viaje < 15
    b = pd.Series(False, index=viaje.index)
    r = evaluate.diferencia_f1(a, b, real, viaje)
    assert r["f1"] == 0.6667
    lo, hi = r["f1_ic95"]
    assert lo < r["f1"] < hi
    assert 0.15 < hi - lo < 0.6


def test_la_pareja_del_clasificador_es_la_regresion_del_mismo_entrenamiento():
    """El listón de la regresión sale del mismo entrenamiento que el clasificador:
    si no, la comparación enfrenta modelos de filas o variables distintas."""
    reg = {
        "columnas": train.columnas(CFG),
        "categorias": ["A", "B"],
        "residuo": True,
        "validacion": {"dias": ["2026-09-28"]},
    }
    clf = {
        "columnas": train.columnas(CFG),
        "categorias": ["A", "B"],
        "umbral": 0.4,
        "validacion": {"dias": ["2026-09-28"]},
    }
    evaluate.comprobar_pareja_clasificador(clf, reg)
    for mal in (
        {**clf, "categorias": ["A"]},  # otro entrenamiento
        {**clf, "validacion": {"dias": ["2026-09-27"]}},  # otra validación
        {**clf, "columnas": train.columnas({**CFG, "incluir_trafico": True})},
    ):
        with pytest.raises(ValueError):
            evaluate.comprobar_pareja_clasificador(mal, reg)
```

Cuentas del titular (A, B y C): 24 positivos de 36. El clasificador avisa a A y B, así que VP = 24 y F1 = 1. La persistencia avisa a B y no a A, que va a 300 s justos: VP = 12 y FN = 12, F1 = 24/36 = 0,6667. En el conjunto, el clasificador suma 12 FN (D) y 12 FP (F): F1 = 48/72. La persistencia tiene FN = 24 (A y D): F1 = 24/48.

- [ ] **Step 2: comprobar que fallan**

Run: `uv run pytest tests/test_modelo.py -q -k "clasificador or diferencia_de_f1"`
Expected: 3 FAIL con `AttributeError: module 'project.evaluate' has no attribute ...`

- [ ] **Step 3: implementación.** En `src/project/evaluate.py`:

Import, después de `import yaml`:

```python
from sklearn.metrics import average_precision_score
```

Constantes, después de `CONGESTION = "con congestión"`:

```python
# Más de 5 min tarde (ADR-025). El titular son las bandas largas: con 15 min o
# menos, la asignación pliega la mitad de esos retrasos (bitácora 038).
BANDAS_LARGAS = ["15-30 min", "> 30 min"]
YA_TARDE, AUN_NO = "ya tarde", "aún no"
LISTONES_BINARIOS = ("persistencia", "persistencia_tramo", "regresion")
```

Funciones, después de `comparacion_trafico` y antes de `def main`:

```python
def _r4(v: float) -> float | None:
    """Redondeo del JSON: nulo, nunca NaN, donde no hay cifra (ADR-025)."""
    v = float(v)
    return None if np.isnan(v) else round(v, 4)


def _f1(vp, fp, fn):
    """F1 = 2 VP / (2 VP + FP + FN). NaN sin positivos reales ni predichos."""
    d = np.asarray(2 * vp + fp + fn, dtype=float)  # con floats de Python, 0/0 lanza
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(d > 0, 2 * vp / d, np.nan)


def _aciertos(decision: pd.Series, real: pd.Series) -> pd.DataFrame:
    """VP, FP y FN fila a fila, como números para poder sumarlos."""
    d, r = decision.astype(bool), real.astype(bool)
    return pd.DataFrame({"vp": d & r, "fp": d & ~r, "fn": ~d & r}).astype(float)


def metricas_binarias(
    decision: pd.Series, real: pd.Series, puntuacion: pd.Series | None = None
) -> dict:
    """Precisión, sensibilidad y F1 en el punto de operación y, con una
    puntuación continua, su PR-AUC (ADR-025). Nulas donde no hay cifra."""
    vp, fp, fn = _aciertos(decision, real).sum()
    m = {
        "precision": _r4(vp / (vp + fp)) if vp + fp else None,
        "sensibilidad": _r4(vp / (vp + fn)) if vp + fn else None,
        "f1": _r4(_f1(vp, fp, fn)),
    }
    if puntuacion is not None:
        r = real.astype(bool)
        m["pr_auc"] = _r4(average_precision_score(r, puntuacion)) if r.any() else None
    return m


def diferencia_f1(
    dec_a: pd.Series,
    dec_b: pd.Series,
    real: pd.Series,
    grupo: pd.Series,
    replicas: int = REPLICAS,
) -> dict:
    """F1 de `dec_a` menos el de `dec_b` (positivo: `a` acierta más), con el
    intervalo del 95 % remuestreando `grupo` —viajes o días—, no filas (ADR-018).

    Como en `diferencia`, se remuestrean sumas por grupo: VP, FP y FN de cada
    uno. Una réplica sin positivos reales ni predichos no tiene F1: no cuenta.
    """
    sumas = (
        pd.concat(
            [
                _aciertos(dec_a, real).add_suffix("_a"),
                _aciertos(dec_b, real).add_suffix("_b"),
            ],
            axis=1,
        )
        .groupby(grupo)
        .sum()
        .to_numpy()
    )

    def medida(s: np.ndarray) -> float:
        return float(_f1(*s[:3]) - _f1(*s[3:]))

    rng = np.random.default_rng(SEMILLA)
    k = len(sumas)
    rep = np.array(
        [medida(sumas[rng.integers(0, k, k)].sum(0)) for _ in range(replicas)]
    )
    rep = rep[~np.isnan(rep)]
    lo, hi = np.percentile(rep, [2.5, 97.5]) if len(rep) else (np.nan, np.nan)
    return {"f1": _r4(medida(sumas.sum(0))), "f1_ic95": [_r4(lo), _r4(hi)]}


def comprobar_pareja_clasificador(clf: dict, reg: dict) -> None:
    """El clasificador y la regresión del mismo horizonte salen del mismo
    entrenamiento, con las mismas variables (ADR-025). Si no, el listón de la
    regresión es de otro modelo y la comparación no dice nada."""
    if not (
        clf["columnas"] == reg["columnas"]
        and clf["categorias"] == reg["categorias"]
        and clf["validacion"]["dias"] == reg["validacion"]["dias"]
    ):
        raise ValueError(
            "el clasificador y la regresión no son la misma pareja (ADR-025)"
        )


def comparacion_clasificador(
    t: pd.DataFrame,
    prob: pd.Series,
    pred_regresion: pd.Series,
    objetivo: str,
    umbral_s: float,
    umbral_decision: float,
) -> dict:
    """Más de `umbral_s` tarde: el clasificador contra los listones sobre las
    mismas filas de la población (ADR-022 y ADR-025). `t` trae `_banda`.

    Todo es descriptivo. El titular son las bandas largas, donde la etiqueta no
    pierde positivos por el pliegue (bitácora 038). El estado actual se sabe al
    predecir: separa los buses que ya van tarde de los que cruzarían el umbral
    por el camino, que es donde la persistencia no llega.
    """
    real = t[f"{objetivo}_bin"].astype(bool)
    base = features.predicciones_baseline(t)
    puntos = {
        "clasificador": prob,
        "persistencia": base["persistencia"],
        "persistencia_tramo": base["persistencia_tramo"],
        "regresion": pred_regresion,
    }
    decision = {
        "clasificador": prob >= umbral_decision,
        **{k: puntos[k] > umbral_s for k in LISTONES_BINARIOS},
        "horario": pd.Series(False, index=t.index),
    }
    p = t[features.poblacion(t)]
    p = p.assign(_estado=np.where(p["retraso_s"] > umbral_s, YA_TARDE, AUN_NO))

    def en(g: pd.DataFrame) -> dict:
        if g.empty:
            return {"filas": 0}
        i = g.index
        viaje = g.groupby(features.CLAVE_VIAJE, sort=False).ngroup()
        return {
            "filas": int(len(g)),
            "viajes": int(viaje.nunique()),
            "dias": int(g["fecha_servicio"].nunique()),
            "tasa_base": _r4(real[i].mean()),
            "brier_clasificador": _r4(((prob[i] - real[i].astype(float)) ** 2).mean()),
            "metricas": {
                k: metricas_binarias(
                    decision[k][i], real[i], puntos[k][i] if k in puntos else None
                )
                for k in decision
            },
            "clasificador_menos": {
                k: {
                    "viajes": diferencia_f1(
                        decision["clasificador"][i], decision[k][i], real[i], viaje
                    ),
                    "dias": diferencia_f1(
                        decision["clasificador"][i],
                        decision[k][i],
                        real[i],
                        g["fecha_servicio"],
                    ),
                }
                for k in LISTONES_BINARIOS
            },
        }

    def por(col: str) -> dict:
        return {str(k): en(g) for k, g in p.groupby(col, observed=True)}

    return {
        "dias": int(p["fecha_servicio"].nunique()),
        "umbral_decision": _r4(umbral_decision),
        "titular": en(p[p["_banda"].isin(BANDAS_LARGAS)]),
        "conjunto": en(p),
        "por_banda": por("_banda"),
        "por_estado_actual": por("_estado"),
    }
```

- [ ] **Step 4: comprobar que pasan**

Run: `uv run pytest tests/test_modelo.py -q`
Expected: todo PASS.

- [ ] **Step 5: formato y commit**

```bash
uv run ruff format src/project/evaluate.py tests/test_modelo.py
uv run ruff check --fix src/project/evaluate.py tests/test_modelo.py
git add src/project/evaluate.py tests/test_modelo.py
git commit -m "feat(evaluate): el clasificador contra los listones, con F1 por viajes y días (ADR-025)"
```

---

## Task 3: el clasificador en `train.py`, `predict.py` y `features.salidas` (agente `pipeline-dvc`)

**Files:**
- Modify: `src/project/features.py` (`salidas`)
- Modify: `src/project/predict.py` (función nueva al final)
- Modify: `src/project/train.py` (imports, constantes, `_xgb`, funciones nuevas tras `entrenar`)
- Test: `tests/test_modelo.py`

**Interfaces:**
- Consumes: `evaluate.metricas_binarias` (tarea 2), `features.matriz`, `features.categorias_linea`, `features.predicciones_baseline` y `separar_validacion`.
- Produces:
  - `features.salidas(h)["clasificador"]`: `Path`, `models/model_clasificador.pkl` o `models/h<h>/model_clasificador.pkl`.
  - `predict.probabilidad(artefacto: dict, tabla: pd.DataFrame) -> pd.Series`: P en [0, 1], con el índice de `tabla`.
  - `train.CLASIFICADOR` y `train.EXPERIMENTO_CLASIFICADOR`.
  - `train.columnas_clasificador(cfg: dict) -> list[str]`.
  - `train.umbral_f1(p: pd.Series, y: pd.Series) -> float`.
  - `train.entrenar_clasificador(train, variables, objetivo, umbral_s, params) -> dict`, que devuelve el artefacto con las claves `modelo`, `columnas`, `categorias`, `umbral`, `n_arboles` y `validacion`. `validacion` lleva `dias`, `tasa_base`, `umbral`, `clasificador`, `persistencia` y `persistencia_tramo`.
  - `train.validar_clasificador(p, val, objetivo, umbral_s, umbral) -> dict`.

- [ ] **Step 1: tests que fallan.** Al final de `tests/test_modelo.py`:

```python
def _tabla_bin():
    """Más de 5 min tarde si `retraso_s` pasa de 1 en los días de ajuste y de 0 en
    los dos de validación. En la validación lo mejor es avisar a todos (F1 = 2/3);
    en el ajuste, solo a los que pasan de 1. El τ de cada uno es otro."""
    t = _tabla()
    corte = sorted(t["fecha_servicio"].unique())[-PARAMS["dias_validacion"]]
    val = t["fecha_servicio"] >= corte
    t[OBJ] = np.where(t["retraso_s"] > np.where(val, 0.0, 1.0), 400.0, 100.0)
    t[BIN] = (t[OBJ] > 300).astype(int)
    return t


def test_el_clasificador_no_pisa_a_la_regresion():
    """Con la misma ruta, el listón de la regresión sería el propio clasificador."""
    for h in (None, 5):
        r = features.salidas(h)
        assert r["clasificador"] not in (r["modelo"], r["modelo_trafico"])
        assert r["clasificador"].parent == r["modelo"].parent


def test_el_umbral_de_decision_es_el_de_mejor_f1():
    """A mano: con τ = 0,7 se avisa a 0,7, 0,8 y 0,9, los tres tarde, y se escapa
    el de 0,3: F1 = 6/7. Con 0,3, F1 = 8/10; con 0,6, 6/8; con 0,8, 4/6."""
    p = pd.Series([0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9])
    y = pd.Series([0, 0, 1, 0, 0, 1, 1, 1])
    assert train.umbral_f1(p, y) == pytest.approx(0.7)


def test_sin_positivos_en_la_validacion_no_hay_umbral():
    """Sin ningún retraso de más de 5 min, cualquier τ es arbitrario:
    `precision_recall_curve` da sensibilidad nula y argmax elige sin avisar."""
    with pytest.raises(ValueError, match="positivos"):
        train.umbral_f1(pd.Series([0.1, 0.5, 0.9]), pd.Series([0, 0, 0]))


def test_el_umbral_de_decision_sale_de_la_validacion():
    """En la validación lo mejor es avisar a todos: τ es la P más baja. Con el
    ajuste, τ saldría por encima de 0,5."""
    t = _tabla_bin()
    art = train.entrenar_clasificador(t, train.columnas(CFG), OBJ, 300, PARAMS)
    assert art["umbral"] < 0.2
    assert art["validacion"]["umbral"] == art["umbral"]
    assert art["validacion"]["dias"] == ["2026-09-05", "2026-09-06"]
    assert art["modelo"].n_estimators == art["n_arboles"]


def test_el_clasificador_ve_las_variables_de_la_regresion_sin_la_192():
    """La 192 la decide el ADR-024: aunque `params.yaml` la active, el
    clasificador no la ve (ADR-025)."""
    con_trafico = {**CFG, "incluir_trafico": True}
    assert train.columnas_clasificador(con_trafico) == features.variables((1, 5), (5,))
    t = _tabla_bin()
    cols = train.columnas_clasificador(CFG)
    art = train.entrenar_clasificador(t, cols, OBJ, 300, PARAMS)
    assert art["columnas"] == cols
    assert art["modelo"].get_booster().feature_names == cols
    # La probabilidad conserva el índice de la tabla y separa a los que van tarde.
    al_reves = t.iloc[::-1]
    p = predict.probabilidad(art, al_reves)
    assert p.index.equals(al_reves.index)
    assert p.between(0, 1).all()
    assert p[t["retraso_s"] > 1.5].mean() > p[t["retraso_s"] < -0.5].mean()
    # Una línea que el entrenamiento no vio (la 8 en la prueba) no tira nada.
    assert predict.probabilidad(art, t.tail(5).assign(linea="Z")).notna().all()
```

- [ ] **Step 2: comprobar que fallan**

Run: `uv run pytest tests/test_modelo.py -q -k "clasificador or umbral"`
Expected: los 5 tests nuevos FAIL (`KeyError: 'clasificador'` o `AttributeError`). Los de la tarea 2 siguen PASS.

- [ ] **Step 3: `features.salidas`.** Sustituir el cuerpo de `salidas` desde `modelo = RAIZ / settings.model_path` hasta el final:

```python
    modelo = RAIZ / settings.model_path
    con_trafico = f"{modelo.stem}_trafico{modelo.suffix}"
    clasificador = f"{modelo.stem}_clasificador{modelo.suffix}"
    if horizonte is None:
        return {
            "tabla": settings.processed_dir,
            "modelo": modelo,
            "modelo_trafico": modelo.with_name(con_trafico),
            "clasificador": modelo.with_name(clasificador),
            "metricas": RAIZ / "metrics",
        }
    h = f"h{horizonte}"
    return {
        "tabla": settings.processed_dir / h,
        "modelo": modelo.parent / h / modelo.name,
        "modelo_trafico": modelo.parent / h / con_trafico,
        "clasificador": modelo.parent / h / clasificador,
        "metricas": RAIZ / "metrics" / "horizontes" / h,
    }
```

Y en su docstring, tras «El modelo con la capa 192 va junto al de sin ella (ADR-024).», añadir: «El clasificador de más de 5 min, también (ADR-025).»

- [ ] **Step 4: `predict.probabilidad`.** Al final de `src/project/predict.py`:

```python
def probabilidad(artefacto: dict, tabla: pd.DataFrame) -> pd.Series:
    """P(más de `umbral_retraso_s` tarde) en la parada objetivo, con el índice de
    `tabla` (ADR-025). Llegará tarde si es `>= artefacto["umbral"]`.

    Pasa por `features.matriz` con las categorías guardadas, como `predecir`.
    """
    x = features.matriz(tabla, artefacto["columnas"], artefacto["categorias"])
    return pd.Series(artefacto["modelo"].predict_proba(x)[:, 1], index=tabla.index)
```

Y en el docstring del módulo, cambiar la primera línea por: «Predicción con los modelos entrenados: la usan `evaluate.py` y, después, `services/`.»

- [ ] **Step 5: `train.py`.** Imports: sustituir `from xgboost import XGBRegressor` por

```python
from sklearn.metrics import precision_recall_curve
from xgboost import XGBClassifier, XGBRegressor
```

Constantes, después de `EXPERIMENTO = "retraso_siguiente_parada"`:

```python
EXPERIMENTO_CLASIFICADOR = "retraso_mas_de_5min"
# El clasificador cambia la pérdida y nada más (ADR-025).
CLASIFICADOR = {"objective": "binary:logistic", "eval_metric": "logloss"}
```

Después de `columnas`:

```python
def columnas_clasificador(cfg: dict) -> list[str]:
    """Las de la regresión sin la capa 192, la active o no `params.yaml`: su
    aportación la decide el ADR-024, no este modelo (ADR-025)."""
    return columnas({**cfg, "incluir_trafico": False})
```

Sustituir `_xgb`:

```python
def _xgb(params: dict, clase: type = XGBRegressor, **cambios):
    p = {k: v for k, v in params.items() if k not in PROPIAS}
    return clase(**{**p, **cambios}, **FIJOS)
```

Después de `entrenar`:

```python
def umbral_f1(p: pd.Series, y: pd.Series) -> float:
    """El umbral de probabilidad con el mejor F1 (ADR-025): se avisa si P ≥ τ.

    `precision_recall_curve` devuelve un punto más que umbrales, el de
    sensibilidad cero, que no tiene umbral. Sin positivos no hay τ: se para.
    """
    if not y.astype(bool).any():
        raise ValueError("la validación no tiene positivos: no hay umbral (ADR-025)")
    precision, sensibilidad, umbrales = precision_recall_curve(y, p)
    f1 = 2 * precision * sensibilidad / np.maximum(precision + sensibilidad, 1e-12)
    return float(umbrales[np.argmax(f1[:-1])])


def validar_clasificador(
    p: pd.Series, val: pd.DataFrame, objetivo: str, umbral_s: float, umbral: float
) -> dict:
    """El clasificador y las dos persistencias en la validación (ADR-025). La
    regresión umbralizada se compara en `evaluate.py`, que carga los dos modelos."""
    real = val[f"{objetivo}_bin"].astype(bool)
    base = features.predicciones_baseline(val)
    return {
        "dias": sorted(val["fecha_servicio"].dt.strftime("%Y-%m-%d").unique()),
        "tasa_base": round(float(real.mean()), 4),
        "umbral": umbral,
        "clasificador": evaluate.metricas_binarias(p >= umbral, real, p),
        **{
            k: evaluate.metricas_binarias(base[k] > umbral_s, real, base[k])
            for k in ("persistencia", "persistencia_tramo")
        },
    }


def entrenar_clasificador(
    train: pd.DataFrame,
    variables: list[str],
    objetivo: str,
    umbral_s: float,
    params: dict,
) -> dict:
    """Más de `umbral_s` tarde (ADR-025): parada temprana y τ con la validación,
    y reajuste con todo `train`, como `entrenar`.

    τ se elige con el modelo de parada temprana y se aplica al reajustado: el
    mismo límite que `n_arboles` (declarado en el ADR-025).
    """
    etiqueta = f"{objetivo}_bin"
    categorias = features.categorias_linea(train)
    ajuste, val = separar_validacion(train, params["dias_validacion"])

    def x(t: pd.DataFrame) -> pd.DataFrame:
        return features.matriz(t, variables, categorias)

    m = _xgb(params, XGBClassifier, **CLASIFICADOR)
    m.fit(
        x(ajuste),
        ajuste[etiqueta],
        eval_set=[(x(val), val[etiqueta])],
        verbose=False,
    )
    n = m.best_iteration + 1
    p_val = pd.Series(m.predict_proba(x(val))[:, 1], index=val.index)
    umbral = umbral_f1(p_val, val[etiqueta])

    final = _xgb(
        params,
        XGBClassifier,
        **CLASIFICADOR,
        n_estimators=n,
        early_stopping_rounds=None,
    )
    final.fit(x(train), train[etiqueta], verbose=False)
    return {
        "modelo": final,
        "columnas": variables,
        "categorias": categorias,
        "umbral": umbral,
        "n_arboles": n,
        "validacion": validar_clasificador(p_val, val, objetivo, umbral_s, umbral),
    }
```

- [ ] **Step 6: comprobar que pasan**

Run: `uv run pytest tests/test_modelo.py tests/test_features.py -q`
Expected: todo PASS.

- [ ] **Step 7: formato y commit**

```bash
uv run ruff format src/project tests/test_modelo.py
uv run ruff check --fix src/project tests/test_modelo.py
git add src/project/features.py src/project/predict.py src/project/train.py tests/test_modelo.py
git commit -m "feat(train): clasificador de más de 5 min con el umbral de la validación (ADR-025)"
```

---

## Task 4: entradas, stages y documentación (agente `pipeline-dvc`)

**Files:**
- Modify: `src/project/train.py` (función nueva tras `main` y bloque `__main__`)
- Modify: `src/project/evaluate.py` (función nueva tras `main_trafico` y bloque `__main__`)
- Modify: `dvc.yaml` (al final)
- Modify: `.claude/tests/test_memoria.py` (`documentados`)
- Modify: `CLAUDE.md` («Pipeline ML»)
- Modify: `docs/superpowers/plans/2026-10-11-fase2-trafico.md` (tareas 12, 13 y 14)

**Interfaces:**
- Consumes: todo lo de las tareas 2 y 3.
- Produces: `uv run python -m project.train [--horizonte H] --clasificador` y `uv run python -m project.evaluate [--horizonte H] --clasificador`; los stages `train_clasificador`, `evaluate_clasificador`, `train_clasificador_h` y `evaluate_clasificador_h`. La salida va a `clasificador.json` en la carpeta de métricas del horizonte: metrics/clasificador.json y metrics/horizontes/h<h>/clasificador.json.

- [ ] **Step 1: test que falla.** En `.claude/tests/test_memoria.py`, añadir al conjunto `documentados` de `test_los_stages_de_dvc_son_los_documentados`, después de `"evaluate_trafico_h",`:

```python
        # más de 5 min tarde (ADR-025): el clasificador y su comparación
        "train_clasificador",
        "evaluate_clasificador",
        "train_clasificador_h",
        "evaluate_clasificador_h",
```

Run: `uv run pytest .claude/tests/test_memoria.py -q -k stages`
Expected: FAIL («dvc.yaml declara … la documentación describe …»).

- [ ] **Step 2: `train.main_clasificador`.** En `src/project/train.py`, después de `main`:

```python
def main_clasificador(horizonte: int | None = None) -> None:
    """Stage `train_clasificador`: más de `umbral_retraso_s` tarde (ADR-025). Sin
    horizonte, el de `params.yaml`; con él, el del barrido (ADR-023)."""
    params = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    cfg, p = params["features"], params["train"]
    rutas = features.salidas(horizonte)
    train = pd.read_parquet(rutas["tabla"] / "train.parquet")
    # Se entrena con las filas en las que el modelo se va a usar (ADR-022).
    train = train[features.poblacion(train)].reset_index(drop=True)

    mlflow.set_experiment(EXPERIMENTO_CLASIFICADOR)
    with mlflow.start_run() as run:
        art = entrenar_clasificador(
            train,
            columnas_clasificador(cfg),
            cfg["objetivo"],
            cfg["umbral_retraso_s"],
            p,
        )
        art["mlflow_run_id"] = run.info.run_id
        mlflow.log_params(
            {
                **p,
                **CLASIFICADOR,
                "n_arboles": art["n_arboles"],
                "umbral_decision": art["umbral"],
                "umbral_retraso_s": cfg["umbral_retraso_s"],
                **{k: cfg[k] for k in ("train_hasta", "test_desde", "test_hasta")},
                "horizonte_paradas": horizonte or cfg["horizonte_paradas"],
            }
        )
        mlflow.log_dict(
            {"variables": art["columnas"], "categorias": art["categorias"]},
            "variables.json",
        )
        mlflow.log_dict(art["validacion"], "validacion.json")
        mlflow.xgboost.log_model(art["modelo"], name="modelo")

    ruta = rutas["clasificador"]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(pickle.dumps(art))
    print(
        json.dumps(
            {k: art[k] for k in ("n_arboles", "umbral", "validacion")},
            indent=2,
            ensure_ascii=False,
        )
    )
```

Sustituir el bloque `if __name__ == "__main__":` de `train.py` por:

```python
if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--horizonte", type=int, default=None, help="paradas (ADR-023)")
    modo = a.add_mutually_exclusive_group()
    modo.add_argument(
        "--trafico", action="store_true", help="con la capa 192 (ADR-024)"
    )
    modo.add_argument(
        "--clasificador", action="store_true", help="más de 5 min tarde (ADR-025)"
    )
    args = a.parse_args()
    if args.clasificador:
        main_clasificador(args.horizonte)
    else:
        main(args.horizonte, args.trafico)
```

- [ ] **Step 3: `evaluate.main_clasificador`.** En `src/project/evaluate.py`, después de `main_trafico`:

```python
def main_clasificador(horizonte: int | None = None) -> None:
    """Stage `evaluate_clasificador`: más de 5 min tarde contra los listones, en
    la prueba (ADR-025). Sin horizonte, el de `params.yaml`; con él, el del
    barrido."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    rutas = features.salidas(horizonte)
    clf = predict.cargar(rutas["clasificador"])
    reg = predict.cargar(rutas["modelo"])
    comprobar_pareja_clasificador(clf, reg)
    test = pd.read_parquet(rutas["tabla"] / "test.parquet")
    horarios = [gtfs.cargar_horario(r) for r in gtfs.versiones(settings.gtfs_dir)]
    metricas = {
        "horizonte_paradas": horizonte or cfg["horizonte_paradas"],
        "prueba": [cfg["test_desde"], cfg["test_hasta"]],
        "umbral_retraso_s": cfg["umbral_retraso_s"],
        "modelos": {
            nombre: {
                "n_arboles": a["n_arboles"],
                "mlflow_run_id": a["mlflow_run_id"],
                "validacion": a["validacion"]["dias"],
            }
            for nombre, a in (("clasificador", clf), ("regresion", reg))
        },
        "remuestreo": {
            "unidad": "viaje y día",
            "replicas": REPLICAS,
            "semilla": SEMILLA,
        },
        **comparacion_clasificador(
            test.assign(_banda=banda_intervalo(test, horarios)),
            predict.probabilidad(clf, test),
            predict.predecir(reg, test),
            cfg["objetivo"],
            cfg["umbral_retraso_s"],
            clf["umbral"],
        ),
    }
    rutas["metricas"].mkdir(parents=True, exist_ok=True)
    (rutas["metricas"] / "clasificador.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    plano = pd.json_normalize(
        {k: metricas[k] for k in ("titular", "conjunto")}, sep="."
    ).iloc[0]
    with mlflow.start_run(run_id=clf["mlflow_run_id"]):
        mlflow.log_metrics(
            {
                f"test.{k}": float(v)
                for k, v in plano.items()
                if isinstance(v, (int, float)) and np.isfinite(v)
            }
        )
        mlflow.log_dict(metricas, "clasificador.json")
    print(json.dumps(metricas["titular"], indent=2, ensure_ascii=False))
```

Sustituir el bloque `if __name__ == "__main__":` de `evaluate.py` por:

```python
if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--horizonte", type=int, default=None, help="paradas (ADR-023)")
    modo = a.add_mutually_exclusive_group()
    modo.add_argument(
        "--trafico", action="store_true", help="con menos sin tráfico (ADR-024)"
    )
    modo.add_argument(
        "--clasificador",
        action="store_true",
        help="más de 5 min tarde contra los listones (ADR-025)",
    )
    args = a.parse_args()
    if args.trafico:
        main_trafico(args.horizonte)
    elif args.clasificador:
        main_clasificador(args.horizonte)
    else:
        main(args.horizonte)
```

- [ ] **Step 4: stages.** Al final de `dvc.yaml`:

```yaml

  # Más de 5 min tarde (ADR-025): las variables y la configuración de la
  # regresión sin tráfico; solo cambia la pérdida. El umbral de decisión sale
  # de la validación y va dentro del modelo.
  train_clasificador:
    cmd: uv run python -m project.train --clasificador
    deps:
      - data/processed/train.parquet
      - src/project/train.py
      - src/project/features.py
      - src/project/predict.py
      - src/project/evaluate.py
    params:
      - train
      - features.umbral_retraso_s
    outs:
      - models/model_clasificador.pkl

  evaluate_clasificador:
    # Contra la persistencia, la del tramo y la regresión umbralizada sobre las
    # mismas filas de la población, con el titular en las bandas de más de 15
    # min (bitácora 038). Descriptivo. Sobre la prueba se ejecuta UNA vez.
    cmd: uv run python -m project.evaluate --clasificador
    deps:
      - data/processed/test.parquet
      - models/model.pkl
      - models/model_clasificador.pkl
      - data/raw/gtfs
      - src/project/evaluate.py
      - src/project/predict.py
      - src/project/features.py
      - src/project/gtfs.py
    params:
      - features.objetivo
      - features.umbral_retraso_s
      - features.test_desde
      - features.test_hasta
    metrics:
      - metrics/clasificador.json:
          cache: false

  train_clasificador_h:
    foreach: ${features.horizontes_barrido}
    do:
      cmd: uv run python -m project.train --horizonte ${item} --clasificador
      deps:
        - data/processed/h${item}
        - src/project/train.py
        - src/project/features.py
        - src/project/predict.py
        - src/project/evaluate.py
      params:
        - train
        - features.umbral_retraso_s
      outs:
        - models/h${item}/model_clasificador.pkl

  evaluate_clasificador_h:
    foreach: ${features.horizontes_barrido}
    do:
      cmd: uv run python -m project.evaluate --horizonte ${item} --clasificador
      deps:
        - data/processed/h${item}
        - models/h${item}/model.pkl
        - models/h${item}/model_clasificador.pkl
        - data/raw/gtfs
        - src/project/evaluate.py
        - src/project/predict.py
        - src/project/features.py
        - src/project/gtfs.py
      params:
        - features.objetivo
        - features.umbral_retraso_s
        - features.test_desde
        - features.test_hasta
      metrics:
        - metrics/horizontes/h${item}/clasificador.json:
            cache: false
```

- [ ] **Step 5: `CLAUDE.md`.** En «Pipeline ML», sustituir

```markdown
  `train_trafico`/`evaluate_trafico` y sus `_h`, para la capa 192, ADR-024)
```

por

```markdown
  `train_trafico`/`evaluate_trafico` y sus `_h`, para la capa 192, ADR-024;
  `train_clasificador`/`evaluate_clasificador` y sus `_h`, para más de 5 min
  tarde, ADR-025)
```

- [ ] **Step 6: plan de la fase 2.** En `docs/superpowers/plans/2026-10-11-fase2-trafico.md`:

Tarea 12, paso 4. Sustituir

```markdown
- [ ] **Step 4:** lanzar desacoplado `uv run dvc repro features features_h train train_h train_trafico train_trafico_h`.
```

por

```markdown
- [ ] **Step 4:** lanzar desacoplado `uv run dvc repro features features_h train train_h train_trafico train_trafico_h train_clasificador train_clasificador_h` (los clasificadores, ADR-025).
```

Tarea 12, paso 5. Sustituir

```markdown
  - En los diez modelos, `validacion.dias` = 28/09…04/10:
```

por

```markdown
  - En los quince modelos (regresión, con tráfico y clasificador, ADR-025), `validacion.dias` = 28/09…04/10:
```

Tarea 13, paso 1. Sustituir

```markdown
(evaluate, evaluate_h, evaluate_trafico, evaluate_trafico_h)
```

por

```markdown
(evaluate, evaluate_h, evaluate_trafico, evaluate_trafico_h, evaluate_clasificador, evaluate_clasificador_h)
```

Tarea 13, paso 2. Añadir al final de la línea:

```markdown
 El clasificador, descriptivo: `titular` en metrics/horizontes/h5/clasificador.json (ADR-025).
```

Tarea 13, paso 3. En el bloque del commit, sustituir `git add dvc.lock metrics/` por la línea siguiente. DVC añade allí `model_clasificador.pkl` la primera vez que ejecuta los stages:

```bash
git add dvc.lock metrics/ models/.gitignore models/h*/.gitignore
```

Tarea 14. Sustituir

```markdown
los cinco `trafico.json`,
```

por

```markdown
los cinco `trafico.json`, el ADR-025 y los cinco `clasificador.json`,
```

- [ ] **Step 7: comprobar**

Run: `uv run pytest .claude/tests -q`
Expected: todo PASS.

Run: `uv run python -m project.train --help` y `uv run python -m project.evaluate --help`
Expected: las dos ayudas muestran `[--trafico | --clasificador]`.

Run: `uv run python -m project.train --trafico --clasificador`
Expected: error de argparse «not allowed with argument».

- [ ] **Step 8: formato y commit**

```bash
uv run ruff format src/project
uv run ruff check --fix src/project
git add src/project/train.py src/project/evaluate.py dvc.yaml .claude/tests/test_memoria.py CLAUDE.md docs/superpowers/plans/2026-10-11-fase2-trafico.md
git commit -m "chore(dvc): stages del clasificador y su comparación (ADR-025)"
```

---

## Task 5: mutantes 163-174 (agente `pipeline-dvc`)

**Files:**
- Modify: `auditoria/catalogo.toml` (al final)

- [ ] **Step 1: añadir los doce mutantes**

```toml
[[mutante]]
id = "163"
nombre = "τ maximiza la sensibilidad y no F1: avisa a todos"
capa = "modelo"
fichero = "src/project/train.py"
buscar = '''    return float(umbrales[np.argmax(f1[:-1])])'''
reemplazar = '''    return float(umbrales[np.argmax(sensibilidad[:-1])])'''
detector = ["tests/test_modelo.py::test_el_umbral_de_decision_es_el_de_mejor_f1"]
sondas = []

[[mutante]]
id = "164"
nombre = "τ sale de los días de ajuste y no de la validación"
capa = "modelo"
fichero = "src/project/train.py"
buscar = '''    p_val = pd.Series(m.predict_proba(x(val))[:, 1], index=val.index)'''
reemplazar = '''    p_val, val = pd.Series(m.predict_proba(x(ajuste))[:, 1], index=ajuste.index), ajuste'''
detector = ["tests/test_modelo.py::test_el_umbral_de_decision_sale_de_la_validacion"]
sondas = []

[[mutante]]
id = "165"
nombre = "el clasificador ve la capa 192 si params.yaml la activa"
capa = "modelo"
# La aportación de la 192 la decide el ADR-024 con su primaria; aquí sería una
# segunda vía sin prerregistro.
fichero = "src/project/train.py"
buscar = '''    return columnas({**cfg, "incluir_trafico": False})'''
reemplazar = '''    return columnas(cfg)'''
detector = ["tests/test_modelo.py::test_el_clasificador_ve_las_variables_de_la_regresion_sin_la_192"]
sondas = []

[[mutante]]
id = "166"
nombre = "los listones avisan con 300 s justos"
capa = "modelo"
fichero = "src/project/evaluate.py"
buscar = '''        **{k: puntos[k] > umbral_s for k in LISTONES_BINARIOS},'''
reemplazar = '''        **{k: puntos[k] >= umbral_s for k in LISTONES_BINARIOS},'''
detector = ["tests/test_modelo.py::test_el_clasificador_se_compara_con_los_listones_en_los_estratos_del_adr_025"]
sondas = []

[[mutante]]
id = "167"
nombre = "el titular del clasificador incluye la banda de 8-15 min"
capa = "modelo"
# Con intervalos de 15 min o menos, la etiqueta pierde positivos (bitácora 038).
fichero = "src/project/evaluate.py"
buscar = '''BANDAS_LARGAS = ["15-30 min", "> 30 min"]'''
reemplazar = '''BANDAS_LARGAS = ["8-15 min", "15-30 min", "> 30 min"]'''
detector = ["tests/test_modelo.py::test_el_clasificador_se_compara_con_los_listones_en_los_estratos_del_adr_025"]
sondas = []

[[mutante]]
id = "168"
nombre = "la comparación del clasificador cuenta filas que ya no llegan a tiempo"
capa = "modelo"
fichero = "src/project/evaluate.py"
buscar = '''    p = t[features.poblacion(t)]'''
reemplazar = '''    p = t'''
detector = ["tests/test_modelo.py::test_el_clasificador_se_compara_con_los_listones_en_los_estratos_del_adr_025"]
sondas = []

[[mutante]]
id = "169"
nombre = "el intervalo de F1 remuestrea filas y no viajes"
capa = "modelo"
fichero = "src/project/evaluate.py"
buscar = '''        .groupby(grupo)'''
reemplazar = '''        .groupby(grupo.index)'''
detector = ["tests/test_modelo.py::test_la_diferencia_de_f1_remuestrea_viajes_y_no_filas"]
sondas = []

[[mutante]]
id = "170"
nombre = "la comparación acepta un clasificador y una regresión de entrenamientos distintos"
capa = "modelo"
fichero = "src/project/evaluate.py"
buscar = '''        raise ValueError(
            "el clasificador y la regresión no son la misma pareja (ADR-025)"
        )'''
reemplazar = '''        pass'''
detector = ["tests/test_modelo.py::test_la_pareja_del_clasificador_es_la_regresion_del_mismo_entrenamiento"]
sondas = []

[[mutante]]
id = "171"
nombre = "el clasificador se guarda encima de la regresión"
capa = "modelo"
fichero = "src/project/features.py"
buscar = '''            "clasificador": modelo.with_name(clasificador),'''
reemplazar = '''            "clasificador": modelo,'''
detector = ["tests/test_modelo.py::test_el_clasificador_no_pisa_a_la_regresion"]
sondas = []

[[mutante]]
id = "172"
nombre = "«ya tarde» incluye los 300 s justos"
capa = "modelo"
fichero = "src/project/evaluate.py"
buscar = '''    p = p.assign(_estado=np.where(p["retraso_s"] > umbral_s, YA_TARDE, AUN_NO))'''
reemplazar = '''    p = p.assign(_estado=np.where(p["retraso_s"] >= umbral_s, YA_TARDE, AUN_NO))'''
detector = ["tests/test_modelo.py::test_el_clasificador_se_compara_con_los_listones_en_los_estratos_del_adr_025"]
sondas = []

[[mutante]]
id = "173"
nombre = "el clasificador no avisa con P igual a τ"
capa = "modelo"
# τ se eligió con `precision_recall_curve`, que avisa con P ≥ τ.
fichero = "src/project/evaluate.py"
buscar = '''        "clasificador": prob >= umbral_decision,'''
reemplazar = '''        "clasificador": prob > umbral_decision,'''
detector = ["tests/test_modelo.py::test_el_clasificador_se_compara_con_los_listones_en_los_estratos_del_adr_025"]
sondas = []

[[mutante]]
id = "174"
nombre = "sin positivos en la validación sale un τ arbitrario"
capa = "modelo"
fichero = "src/project/train.py"
buscar = '''    if not y.astype(bool).any():'''
reemplazar = '''    if False:'''
detector = ["tests/test_modelo.py::test_sin_positivos_en_la_validacion_no_hay_umbral"]
sondas = []
```

Si `ruff format` dejó alguna línea de `buscar` distinta de la del fichero, copiar en `buscar` el texto exacto del fichero. Cada `buscar` debe aparecer **una sola vez** en su fichero. Comprobarlo antes del commit:

```powershell
@(
  @("src/project/train.py", '    return float(umbrales[np.argmax(f1[:-1])])'),
  @("src/project/train.py", '    p_val = pd.Series(m.predict_proba(x(val))[:, 1], index=val.index)'),
  @("src/project/train.py", '    return columnas({**cfg, "incluir_trafico": False})'),
  @("src/project/train.py", '    if not y.astype(bool).any():'),
  @("src/project/evaluate.py", '        **{k: puntos[k] > umbral_s for k in LISTONES_BINARIOS},'),
  @("src/project/evaluate.py", 'BANDAS_LARGAS = ["15-30 min", "> 30 min"]'),
  @("src/project/evaluate.py", '    p = t[features.poblacion(t)]'),
  @("src/project/evaluate.py", '        .groupby(grupo)'),
  @("src/project/evaluate.py", '            "el clasificador y la regresión no son la misma pareja (ADR-025)"'),
  @("src/project/evaluate.py", '    p = p.assign(_estado=np.where(p["retraso_s"] > umbral_s, YA_TARDE, AUN_NO))'),
  @("src/project/evaluate.py", '        "clasificador": prob >= umbral_decision,'),
  @("src/project/features.py", '            "clasificador": modelo.with_name(clasificador),')
) | ForEach-Object { "{0}  {1}" -f (Select-String -Path $_[0] -SimpleMatch -Pattern $_[1]).Count, $_[1] }
```

Expected: un `1` delante de cada línea.

- [ ] **Step 2: commit (`mutar.py` audita commits)**

```bash
git add auditoria/catalogo.toml
git commit -m "test(auditoria): mutantes 163-174 del clasificador (ADR-025)"
```

- [ ] **Step 3: ejecutar solo los nuevos**

Run: `uv run python auditoria/mutar.py --solo 163 164 165 166 167 168 169 170 171 172 173 174`
Expected: los doce «detectado». Resultados en `auditoria/resultados/mutantes_<hash>.json`. Si alguno sale «hueco» o «invalido», arreglar el test o el `buscar` antes de seguir.

- [ ] **Step 4: commit del resultado**

```bash
git add auditoria/resultados/
git commit -m "test(auditoria): mutantes 163-174 detectados"
```

---

## Task 6: ensayo sobre las tablas del corte antiguo (en línea, sin subagente)

`data/processed/` tiene todavía las tablas del corte antiguo: entrenamiento hasta el 20/09 y «prueba» del 21/09 al 04/10, que con el corte del ADR-024 ya es entrenamiento. `models/model.pkl` sale de ese mismo corte (validación del 14 al 20/09). El ensayo no toca la prueba del 07 al 19/10 ni ejecuta DVC. **No se ajusta nada del protocolo por lo que salga.** Si sale un fallo de código, se corrige; si el protocolo resulta inviable (por ejemplo, un titular sin filas), se para y se consulta al usuario antes del 21/10.

- [ ] **Step 1: entrenar, desacoplado.** Sustituir `<scratchpad>` por el directorio de scratchpad de la sesión:

```powershell
$env:PYTHONIOENCODING = "utf-8"
Start-Process -FilePath uv -ArgumentList "run","python","-m","project.train","--clasificador" -WorkingDirectory C:\Users\oppen\Code\TFM `
  -RedirectStandardOutput "<scratchpad>\ensayo_clf_train.log" -RedirectStandardError "<scratchpad>\ensayo_clf_train.err" -WindowStyle Hidden -PassThru
```

Vigilar con Monitor hasta que el proceso salga y apuntar cuánto ha tardado (hora de inicio y de fin). Si el `.err` tiene una traza, parar y diagnosticar.

- [ ] **Step 2: evaluar, desacoplado.** El mismo comando con `"project.evaluate","--clasificador"` y los logs `ensayo_clf_eval.*`. Vigilar hasta que salga.

- [ ] **Step 3: comprobar la forma, sin leer cifras**

```powershell
uv run python -c "
import json, pickle
a = pickle.load(open('models/model_clasificador.pkl', 'rb'))
r = pickle.load(open('models/model.pkl', 'rb'))
assert a['validacion']['dias'] == r['validacion']['dias'], 'otra validación'
assert a['columnas'] == r['columnas'] and 0 < a['umbral'] < 1
m = json.load(open('metrics/clasificador.json', encoding='utf-8'))
assert {'titular', 'conjunto', 'por_banda', 'por_estado_actual'} <= set(m)
assert m['titular']['filas'] > 0, 'titular sin filas'
assert set(m['titular']['metricas']) == {'clasificador', 'persistencia', 'persistencia_tramo', 'regresion', 'horario'}
print('forma ok; arboles =', a['n_arboles'])
"
```

Expected: `forma ok; arboles = N`.

- [ ] **Step 4: limpiar.** Borrar el run de MLflow del ensayo y lo que ha escrito:

```powershell
uv run python -c "import mlflow, pickle; mlflow.delete_run(pickle.load(open('models/model_clasificador.pkl','rb'))['mlflow_run_id'])"
Remove-Item models/model_clasificador.pkl, metrics/clasificador.json
git status --short
```

Expected: `git status` limpio. Guardar la duración del paso 1 para el cierre.

---

## Task 7: cierre (en línea)

- [ ] **Step 1:** `uv run pytest -q` y `uv run pytest .claude/tests -q`. Expected: todo PASS, salvo el `xfail` estricto conocido.
- [ ] **Step 2:** `uv run ruff format --check . ; uv run ruff check .`. Expected: sin cambios ni errores.
- [ ] **Step 3:** `uv run dvc status`. Expected: además de lo que ya mostraba antes de este plan, solo los cuatro stages `*_clasificador*`, sin ejecutar. **No lanzar `dvc repro`.**
- [ ] **Step 4:** `git status` limpio y `git log --oneline` con los commits de las tareas 1-5. Informar al usuario de la duración del entrenamiento del ensayo: por cinco horizontes, es lo que el `dvc repro` del 21/10 suma a la fase B.
