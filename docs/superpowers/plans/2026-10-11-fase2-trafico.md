# Fase 2 del ADR-024 — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dejar construida, probada y commiteada la evaluación única de la capa 192 (con tráfico menos sin tráfico, ADR-024) **antes de traer ningún dato posterior al 04/10**, y ejecutarla una vez a partir del 21/10.

**Architecture:** el modelo con tráfico es el mismo `train.entrenar` con `features.variables(..., trafico=True)`, guardado junto al modelo sin tráfico de cada horizonte. La comparación vive en `evaluate.py` (los estratos se mueven ahí desde `analysis/trafico_validacion.py`) y corre en stages nuevos de DVC. `features.partir` pasa de un corte a tres para excluir el 05-06/10 y todo lo posterior al 19/10.

**Tech Stack:** Python 3.11, pandas, XGBoost, DVC, MLflow, pytest, `uv`.

**Spec:** ADR-024 de `docs/07_decisiones.md`, con su enmienda del 10/10 y la nota del 11/10 que escribe la tarea 1. El encargo se aprobó en la sesión del 11/10: horario `19-09-2026` y prueba del 07 al 19/10.

## Global Constraints

- Prueba: días de servicio del 07 al 19/10. Entrenamiento: hasta el 04/10. Validación: 28/09-04/10 (`train.dias_validacion: 7`). El 05/10 y el 06/10 no entran en ninguna tabla.
- Horario: `19-09-2026`. No se copia ninguna versión nueva a `data/raw/gtfs/`.
- Primaria: h = 5, filas con `trafico_cubierto_m / dist_objetivo_m > 0,75`, MAE con tráfico menos MAE sin él sobre las mismas filas de `features.poblacion`. Hay aportación si ni el IC 95 % por viajes ni el IC por días contienen el cero.
- Los dos modelos usan la misma configuración (`params.yaml → train`) y solo cambian las variables. Las variables de tráfico están congeladas: no se tocan `trafico.py` ni `features.construir`.
- Las comparaciones sobre la prueba se ejecutan **una vez**. Lo que se haga después es exploratorio y se declara como tal.
- `src/project/` no importa de `analysis/`; al revés, sí. Ningún `os.getenv`; las rutas salen de `settings` y `features.salidas`.
- Toda evaluación es un stage de DVC.
- Los datos se traen solo con `deploy_pi/pull_data.sh`, desde WSL, con ORIGEN en la SD, primero con `--verificar`, y nunca antes del 21/10. Nada de rsync a mano (trampa 016).
- En la Pi, solo lectura. Nada de `fsck`, `mkfs`, `parted`, `preparar_disco.sh`, escribir en `/dev/sda*`, borrar en `/srv/tfm-data` o `/srv/tfm-sd`, ni reiniciar.
- Lo largo se lanza con `Start-Process`, desacoplado, con `PYTHONIOENCODING=utf-8`, los logs en el scratchpad y vigilado con Monitor.
- No leer `.env`. Commits en `develop`, sin push. `uv`, nunca `pip`.
- Subagentes en Sonnet, salvo el tribunal de la tarea 14, que va en Opus.
- Los `.md` de `docs/` pasan por `.claude/tests/test_memoria.py`: toda ruta citada entre comillas invertidas debe existir, y toda función citada con paréntesis también.

## Review Focus

1. **Modelos cruzados o de entrenamientos distintos.** Si el modelo «sin» lleva la capa 192, o los dos no salen del mismo entrenamiento, la primaria cambia de signo sin ningún error. Lo esperable: la evaluación se niega a correr. Lo guarda la prueba de la pareja (tarea 4).
2. **Días posteriores al 19/10 en la prueba.** Lo esperable es que `pull_data.sh` los traiga y que no entren. Lo guarda la prueba del corte (tarea 2).
3. **Un día parcial al final del entrenamiento.** Desplazaría la validación. Lo esperable: el 05-06/10 queda fuera. Lo guardan la prueba del corte (tarea 2) y la comprobación de `validacion.dias` (tarea 12).
4. **Filas fuera de la población en la comparación.** Lo esperable es que no cuenten. Lo guarda el grupo E de la prueba de estratos (tarea 4).
5. **Una fila con exactamente el 75 % cubierto.** No es «con sensor». Lo guarda el grupo F de la prueba de estratos (tarea 4).

---

## Fase A — desde ya, sin datos nuevos

### Task 1: nota del 11/10 al ADR-024 (prerregistro antes de mirar la Pi)

**Files:**
- Modify: `docs/07_decisiones.md` (final del ADR-024, tras la enmienda del 10/10; y el ADR-007, tras «Corte (05/10)»)

**Interfaces:** la nota es la fuente de verdad de las tareas 2-15.

- [ ] **Step 1: añadir la nota al final del ADR-024**, justo antes del `---` que precede a «Pendientes de decidir»:

```markdown
**Nota del 11/10**, antes de construir la fase 2 y de traer la prueba:
- **Ventana de prueba: del 07 al 19/10**, 13 días de servicio. El 06/10 queda
  fuera: la captura volvió a las 13:22 UTC (15:22 locales) y le falta la punta
  de mañana, y el punto 1 pide días completos. El 05/10 no tiene captura
  (bitácora 044).
- **Tres cortes en `features.partir`:** entrenamiento hasta el 04/10 y prueba
  del 07 al 19/10. Lo que cae en medio o después no entra en ninguna tabla,
  aunque sí cuenta como historia para las ventanas y el sesgo del tramo. Sin
  el corte del entrenamiento, el 06/10 movería la validación al 30/09-06/10; sin
  el de la prueba, `pull_data.sh` metería en ella el 20/10 y lo posterior.
- **Horario: la `19-09-2026`**, vigente del 12/09 al 19/10, con los festivos
  del 09 y el 12/10 en su `calendar_dates`. Las versiones que guarda la Pi no
  entran en `gtfs_dir`: la `05-10-2026` es vigente desde el 28/09 y, por la
  regla del ADR-014, reetiquetaría la validación con la que se fijó el estrato,
  además de quitar la 13. Se contrastan con `analysis/comparar_gtfs` después de
  `prepare` y antes de las comparaciones, y se declaran como límite.
- **Día útil.** Un día de prueba se descarta solo si la captura de la EMT tiene
  un hueco de más de 1 h dentro de su día de servicio, porque sin posiciones no
  hay etiqueta. Los huecos de la 192 no descartan días: dejan filas sin tráfico
  observado, que se informan, como el 22 y el 23/09 en la validación (bitácora
  048). Si se descarta alguno, se dice cuál y por qué antes de evaluar.
- **Composición.** La prueba tiene dos festivos, el 09/10 (viernes) y el 12/10
  (lunes), y la validación ninguno. La comparación es sobre las mismas filas y
  eso no la sesga, pero la cifra hereda esos días (ADR-007).
- **Ejecución.** Stages `train_trafico` y `evaluate_trafico`, y sus versiones
  `_h`, en todos los horizontes del barrido. El modelo sin tráfico es el de
  `train`/`train_h`. Antes de las comparaciones se comprueban las etiquetas de
  la prueba y que la validación de los diez modelos sea el 28/09-04/10. Las
  comparaciones se ejecutan una vez.
```

- [ ] **Step 2: añadir al ADR-007**, después del párrafo «Corte (05/10)»:

```markdown
**Corte (11/10).** Tres fechas en vez de una (`features.train_hasta`,
`test_desde` y `test_hasta`): entrenamiento hasta el 04/10 y prueba del 07 al
19/10 (ADR-024, nota del 11/10).
```

- [ ] **Step 3: la documentación sigue en verde**

Run: `uv run pytest .claude/tests -q`
Expected: PASS

- [ ] **Step 4: commit**

```bash
git add docs/07_decisiones.md
git commit -m "docs(decisiones): ADR-024, prueba del 07 al 19/10 con la 19-09-2026, antes de construir la fase 2"
```

---

### Task 2: `features.partir` con tres cortes (agente `etl-labeler`)

**Files:**
- Modify: `src/project/features.py:439-442` (`partir`) y `:659` (llamada en `main`)
- Modify: `src/project/train.py:152` (parámetros que se registran en MLflow)
- Modify: `params.yaml` (bloque `features`, comentario del split y `test_desde`)
- Test: `tests/test_features.py:139-148`

**Interfaces:**
- Produces: `features.partir(tabla, train_hasta: str, test_desde: str, test_hasta: str) -> tuple[pd.DataFrame, pd.DataFrame]` y las claves `features.train_hasta`, `features.test_desde` y `features.test_hasta` en `params.yaml`.

- [ ] **Step 1: test que falla.** Cambiar la llamada del test existente y añadir el nuevo:

```python
def test_el_split_es_por_dia_de_servicio_y_no_parte_viajes():
    filas = [_paso("A", s, 2 * s, 0, dia="2026-09-13") for s in range(1, 4)]
    filas += [_paso("B", s, 2 * s, 0, dia="2026-09-14") for s in range(1, 4)]
    # Como llega de `pasos`: fechas `date` en unas particiones y `datetime64` en otras.
    for f in filas[3:]:
        f["fecha_servicio"] = f["fecha_servicio"].date()
    train, test = features.partir(
        _construir(filas), "2026-09-13", "2026-09-14", "2026-09-14"
    )
    assert set(train["viaje_id"]) == {"A"} and set(test["viaje_id"]) == {"B"}
    assert (train["fecha_servicio"] < "2026-09-14").all()
    assert (test["fecha_servicio"] >= "2026-09-14").all()


def test_el_split_deja_fuera_los_dias_partidos_y_lo_posterior_a_la_prueba():
    """ADR-024: entrenamiento hasta el 04/10 y prueba del 07 al 19/10.

    El 05 y el 06/10 no van a ningún lado: el 06/10 es parcial y, dentro del
    entrenamiento, movería la validación al 30/09-06/10. El 20/10 lo trae
    `pull_data.sh` y caería en la prueba.
    """
    dias = [
        "2026-10-04",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
        "2026-10-19",
        "2026-10-20",
    ]
    filas = [
        _paso(f"V{i}", s, 2 * s, 0, dia=d)
        for i, d in enumerate(dias)
        for s in range(1, 4)
    ]
    tabla = _construir(filas)
    train, test = features.partir(tabla, "2026-10-04", "2026-10-07", "2026-10-19")
    assert set(train["viaje_id"]) == {"V0"}
    assert set(test["viaje_id"]) == {"V3", "V4"}
    with pytest.raises(ValueError):
        features.partir(tabla, "2026-10-07", "2026-10-07", "2026-10-19")
```

- [ ] **Step 2: comprobar que falla**

Run: `uv run pytest tests/test_features.py -k split -v`
Expected: FAIL con `TypeError: partir() takes 2 positional arguments but 4 were given`

- [ ] **Step 3: implementación.** Sustituir `partir`:

```python
def partir(
    tabla: pd.DataFrame, train_hasta: str, test_desde: str, test_hasta: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split TEMPORAL por día de servicio (ADR-007): ningún viaje a los dos lados.

    Los tres cortes son días de servicio, inclusivos. Lo que cae entre
    `train_hasta` y `test_desde`, o después de `test_hasta`, no entra en ninguna
    tabla: un día parcial al final del entrenamiento movería la validación, y
    `pull_data.sh` trae también los días posteriores a la prueba (ADR-024). Sí
    cuentan como historia: las ventanas y el sesgo del tramo se calculan antes de
    partir.
    """
    if pd.Timestamp(train_hasta) >= pd.Timestamp(test_desde):
        raise ValueError(
            f"el entrenamiento ({train_hasta}) pisa la prueba ({test_desde})"
        )
    dia = tabla["fecha_servicio"]
    train = dia <= pd.Timestamp(train_hasta)
    prueba = (dia >= pd.Timestamp(test_desde)) & (dia <= pd.Timestamp(test_hasta))
    return tabla[train].reset_index(drop=True), tabla[prueba].reset_index(drop=True)
```

En `features.main`, la llamada:

```python
    train, test = partir(
        tabla, cfg["train_hasta"], cfg["test_desde"], cfg["test_hasta"]
    )
```

En `train.main`, la línea `"test_desde": cfg["test_desde"],` de `mlflow.log_params` pasa a ser:

```python
                **{k: cfg[k] for k in ("train_hasta", "test_desde", "test_hasta")},
```

En `params.yaml`, el comentario del split y `test_desde` se sustituyen por:

```yaml
  # Split TEMPORAL, nunca aleatorio: con series de posiciones, un split
  # aleatorio filtra el futuro en el entrenamiento y te da métricas falsas.
  # Tres cortes, días de servicio inclusivos (ADR-024, nota del 11/10). El
  # entrenamiento es todo hasta el 04/10, y su última semana (28/09-04/10) es
  # la validación (`train.dias_validacion`). Quedan fuera de toda tabla:
  #   - el 05/10, sin captura (bitácora 044);
  #   - el 06/10, parcial: la captura volvió a las 15:22 locales, sin la punta
  #     de mañana, y en el entrenamiento movería la validación al 30/09-06/10;
  #   - lo posterior al 19/10, último día del horario 19-09-2026, que
  #     `pull_data.sh` trae igual.
  # La prueba, del 07 al 19/10, no la ha visto nadie.
  train_hasta: "2026-10-04"
  test_desde: "2026-10-07"
  test_hasta: "2026-10-19"
```

- [ ] **Step 4: comprobar que pasa**

Run: `uv run pytest tests/test_features.py tests/test_modelo.py -q && uv run ruff format . && uv run ruff check --fix .`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add src/project/features.py src/project/train.py params.yaml tests/test_features.py
git commit -m "feat(features): tres cortes en el split; el 05-06/10 y lo posterior al 19/10 fuera (ADR-024)"
```

---

### Task 3: el modelo con tráfico junto al de sin tráfico (agente `pipeline-dvc`)

**Files:**
- Modify: `src/project/features.py:561-579` (`salidas`)
- Modify: `src/project/train.py:135-180` (`main` y argparse)
- Test: `tests/test_modelo.py`

**Interfaces:**
- Consumes: `features.salidas(horizonte)`, `train.columnas(cfg)`.
- Produces: la clave `"modelo_trafico"` en `features.salidas(h)`: `models/model_trafico.pkl` sin horizonte y `models/h<h>/model_trafico.pkl` con él. También `train.main(horizonte: int | None = None, trafico: bool = False)` y el flag de CLI `--trafico`.

- [ ] **Step 1: test que falla** (en `tests/test_modelo.py`):

```python
def test_el_modelo_con_trafico_no_pisa_al_de_sin_trafico():
    """Los dos modelos del ADR-024 van juntos y en ficheros distintos: si
    compartieran ruta, la comparación enfrentaría un modelo consigo mismo."""
    for h in (None, 5):
        r = features.salidas(h)
        assert r["modelo_trafico"] != r["modelo"]
        assert r["modelo_trafico"].parent == r["modelo"].parent
```

- [ ] **Step 2: comprobar que falla**

Run: `uv run pytest tests/test_modelo.py::test_el_modelo_con_trafico_no_pisa_al_de_sin_trafico -v`
Expected: FAIL con `KeyError: 'modelo_trafico'`

- [ ] **Step 3: implementación.** `salidas`:

```python
def salidas(horizonte: int | None = None) -> dict[str, Path]:
    """Dónde escriben `features`, `train` y `evaluate`.

    Sin horizonte, las rutas de siempre: es el de `params.yaml` y la bitácora las
    cita. Con él, una carpeta por horizonte del barrido (ADR-023). El modelo con
    la capa 192 va junto al de sin ella (ADR-024).
    """
    modelo = RAIZ / settings.model_path
    con_trafico = f"{modelo.stem}_trafico{modelo.suffix}"
    if horizonte is None:
        return {
            "tabla": settings.processed_dir,
            "modelo": modelo,
            "modelo_trafico": modelo.with_name(con_trafico),
            "metricas": RAIZ / "metrics",
        }
    h = f"h{horizonte}"
    return {
        "tabla": settings.processed_dir / h,
        "modelo": modelo.parent / h / modelo.name,
        "modelo_trafico": modelo.parent / h / con_trafico,
        "metricas": RAIZ / "metrics" / "horizontes" / h,
    }
```

En `train.main`:

```python
def main(horizonte: int | None = None, trafico: bool = False) -> None:
    """Sin horizonte, el de `params.yaml`; con él, el del barrido (ADR-023).

    Con `trafico`, el mismo modelo con las variables de la capa 192 (ADR-024):
    misma configuración y mismas filas; solo cambian las variables.
    """
    params = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    cfg, p = params["features"], params["train"]
    if trafico:
        cfg = {**cfg, "incluir_trafico": True}
```

En `mlflow.log_params`, añadir `"trafico": cfg["incluir_trafico"],`. La ruta de guardado pasa a ser:

```python
    ruta = rutas["modelo_trafico" if trafico else "modelo"]
```

Y la CLI:

```python
if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--horizonte", type=int, default=None, help="paradas (ADR-023)")
    a.add_argument("--trafico", action="store_true", help="con la capa 192 (ADR-024)")
    args = a.parse_args()
    main(args.horizonte, args.trafico)
```

No tocar la línea `trafico=cfg["incluir_trafico"],` de `train.columnas`: la busca el mutante 136.

- [ ] **Step 4: comprobar que pasa**

Run: `uv run pytest tests/test_modelo.py -q && uv run ruff format . && uv run ruff check --fix .`
Expected: PASS

- [ ] **Step 5: commit**

```bash
git add src/project/features.py src/project/train.py tests/test_modelo.py
git commit -m "feat(train): el modelo con la capa 192 junto al de sin ella (ADR-024)"
```

---

### Task 4: la comparación en `evaluate.py`, con los estratos de la validación (agente `pipeline-dvc`)

**Files:**
- Modify: `src/project/evaluate.py` (constantes tras `NOMBRES_HORIZONTE`, funciones nuevas antes de `main`, una función de stage y argparse)
- Modify: `src/project/analysis/trafico_validacion.py` (importa los estratos en vez de definirlos)
- Test: `tests/test_modelo.py`

**Interfaces:**
- Consumes: `features.salidas(h)["modelo_trafico"]` (tarea 3), `evaluate.diferencia`, `features.poblacion`, `predict.cargar` y `predict.predecir`.
- Produces:
  - `evaluate.estratos_trafico(t) -> pd.DataFrame` (añade `_cobertura` y `_estado`);
  - `evaluate.con_menos_sin(e_con, e_sin, t) -> dict` con las claves `filas`, `mae_sin_s`, `mae_con_s`, `con_menos_sin_s`, `relativa`, `ic_viajes` e `ic_dias`;
  - `evaluate.comprobar_pareja(con: dict, sin: dict) -> None` (lanza `ValueError`);
  - `evaluate.comparacion_trafico(t, pred_con, pred_sin, objetivo) -> dict` con las claves `dias`, `con_sensor`, `conjunto`, `con_congestion_observada`, `sin_sensor`, `por_cobertura` y `por_estado_observado`;
  - `evaluate.main_trafico(horizonte)` y el flag `--trafico`, que escriben `trafico.json` en `features.salidas(h)["metricas"]`.

- [ ] **Step 1: tests que fallan** (en `tests/test_modelo.py`; añadir `import pytest` a los imports):

```python
def _con_y_sin():
    """Seis grupos de 4 viajes × 3 filas en dos días. Sin tráfico se yerra 50 s en
    todas las filas; con tráfico, 50 + `cambio`. Cada grupo pone a prueba una
    frontera del ADR-024."""
    grupos = {
        # grupo: (metros con sensor de 100, congestión, horizonte previsto, cambio)
        "A": (90.0, 0.0, 60.0, -1.0),  # > 75 %, fluido
        "B": (90.0, 0.5, 60.0, -5.0),  # > 75 %, con congestión
        "C": (0.0, np.nan, 60.0, 0.0),  # sin sensor
        "D": (60.0, 0.0, 60.0, 1.0),  # 50-75 %
        "F": (75.0, 0.0, 60.0, 3.0),  # 75 % justo: no es «> 75 %»
        "E": (90.0, 0.0, -10.0, -30.0),  # ya no llega a tiempo: fuera de la población
    }
    filas = [
        {
            "fecha_servicio": pd.Timestamp("2026-10-07") + pd.Timedelta(days=v % 2),
            "viaje_id": f"{g}{v}",
            "trafico_cubierto_m": cubierto,
            "dist_objetivo_m": 100.0,
            "trafico_congestion_frac": frac,
            "horizonte_previsto_s": previsto,
            "ultimo_conocido": True,
            OBJ: 0.0,
            "_cambio": cambio,
        }
        for g, (cubierto, frac, previsto, cambio) in grupos.items()
        for v in range(4)
        for _ in range(3)
    ]
    t = pd.DataFrame(filas)
    return t, t[OBJ] + 50.0 + t["_cambio"], t[OBJ] + 50.0


def test_la_comparacion_del_trafico_separa_los_estratos_del_adr_024():
    t, con, sin = _con_y_sin()
    r = evaluate.comparacion_trafico(t, con, sin, OBJ)
    assert r["con_sensor"]["filas"] == 24
    assert r["con_sensor"]["con_menos_sin_s"] == -3.0
    assert r["con_sensor"]["relativa"] == -0.06
    assert r["con_congestion_observada"]["con_menos_sin_s"] == -5.0
    assert r["sin_sensor"]["con_menos_sin_s"] == 0.0
    # Con el 75 % justo dentro, el estrato con sensor bajaría a −1,0.
    assert r["por_cobertura"]["50-75 %"]["con_menos_sin_s"] == 2.0
    # Sin la población entraría el grupo E, y el conjunto bajaría a −5,33.
    assert r["conjunto"]["filas"] == 60
    assert r["conjunto"]["con_menos_sin_s"] == -0.4
    # Un estrato vacío no tira la única evaluación de la prueba.
    sin_b = t["viaje_id"].str[0] != "B"
    r = evaluate.comparacion_trafico(t[sin_b], con[sin_b], sin[sin_b], OBJ)
    assert r["con_congestion_observada"] == {"filas": 0}


def test_la_pareja_del_trafico_es_el_mismo_modelo_salvo_la_capa_192():
    """Cruzar los dos modelos invierte el signo de la primaria sin ningún error."""
    sin = {
        "columnas": train.columnas(CFG),
        "categorias": ["A", "B"],
        "residuo": True,
        "validacion": {"dias": ["2026-09-28"]},
    }
    con = {**sin, "columnas": train.columnas({**CFG, "incluir_trafico": True})}
    evaluate.comprobar_pareja(con, sin)
    for mal in (
        (sin, con),  # cruzados
        ({**con, "columnas": [*con["columnas"], "otra"]}, sin),  # otra variable
        ({**con, "categorias": ["A"]}, sin),  # otro entrenamiento
        ({**con, "residuo": False}, sin),  # otra configuración
        ({**con, "validacion": {"dias": ["2026-09-27"]}}, sin),  # otra validación
    ):
        with pytest.raises(ValueError):
            evaluate.comprobar_pareja(*mal)
```

- [ ] **Step 2: comprobar que fallan**

Run: `uv run pytest tests/test_modelo.py -k "trafico or pareja" -v`
Expected: FAIL con `AttributeError: module 'project.evaluate' has no attribute 'comparacion_trafico'`

- [ ] **Step 3: implementación en `evaluate.py`.** Constantes, tras `NOMBRES_HORIZONTE`:

```python
# Fracción del recorrido i -> i + h bajo la 192 (ADR-024, enmienda del 10/10).
# Es geométrica y se sabe antes de predecir. La primaria mide el último estrato.
COBERTURA = [-np.inf, 0, 0.25, 0.5, 0.75, np.inf]
NOMBRES_COBERTURA = ["0", "0-25 %", "25-50 %", "50-75 %", "> 75 %"]
SIN_SENSOR, CON_SENSOR = NOMBRES_COBERTURA[0], NOMBRES_COBERTURA[-1]
CONGESTION = "con congestión"
```

Funciones, antes de `main`:

```python
def estratos_trafico(t: pd.DataFrame) -> pd.DataFrame:
    """`t` con `_cobertura`, la fracción del recorrido con sensor, y `_estado`, lo
    que decía la capa al predecir. Las dos se saben antes de predecir:
    estratificar por ellas no es condicionar por el resultado (ADR-024)."""
    cobertura = (t["trafico_cubierto_m"] / t["dist_objetivo_m"]).clip(upper=1)
    frac = t["trafico_congestion_frac"]
    estado = np.select(
        [frac.isna(), frac == 0], ["sin dato", "fluido"], default=CONGESTION
    )
    return t.assign(
        _cobertura=pd.cut(cobertura, COBERTURA, labels=NOMBRES_COBERTURA),
        _estado=estado,
    )


def con_menos_sin(e_con: pd.Series, e_sin: pd.Series, t: pd.DataFrame) -> dict:
    """MAE con tráfico menos MAE sin él sobre las filas de `t`, con los intervalos
    por viajes y por días (ADR-018), y el efecto relativo al MAE sin tráfico."""
    viaje = t.groupby(features.CLAVE_VIAJE, sort=False).ngroup()
    v = diferencia(e_con, e_sin, viaje)
    d = diferencia(e_con, e_sin, t["fecha_servicio"])
    mae_sin, mae_con = float(e_sin.abs().mean()), float(e_con.abs().mean())
    return {
        "filas": int(len(t)),
        "mae_sin_s": round(mae_sin, 2),
        "mae_con_s": round(mae_con, 2),
        "con_menos_sin_s": v["mae_s"],
        "relativa": round((mae_con - mae_sin) / mae_sin, 4),
        "ic_viajes": v["mae_ic95"],
        "ic_dias": d["mae_ic95"],
    }


def comprobar_pareja(con: dict, sin: dict) -> None:
    """El mismo modelo salvo las variables de la 192 (ADR-024, punto 3).

    Cruzarlos, o compararlos tras entrenar uno con otros datos, invierte o
    falsea la primaria sin ningún error.
    """
    trafico = set(features.TRAFICO)
    if not (
        set(con["columnas"]) == set(sin["columnas"]) | trafico
        and not trafico & set(sin["columnas"])
        and con["categorias"] == sin["categorias"]
        and con["residuo"] == sin["residuo"]
        and con["validacion"]["dias"] == sin["validacion"]["dias"]
    ):
        raise ValueError(
            "los modelos con y sin tráfico no son la misma pareja (ADR-024)"
        )


def comparacion_trafico(
    t: pd.DataFrame, pred_con: pd.Series, pred_sin: pd.Series, objetivo: str
) -> dict:
    """El modelo con la capa 192 contra el mismo modelo sin ella, sobre las mismas
    filas de la población (ADR-022 y ADR-024).

    `con_sensor` es la primaria con h = 5. El resto es descriptivo: el conjunto,
    las filas en las que la capa veía congestión al predecir (el secundario) y las
    que no tienen ningún sensor en el recorrido (el control: lo que la primaria no
    supere a este no se atribuye a la congestión).
    """
    e_con, e_sin = pred_con - t[objetivo], pred_sin - t[objetivo]
    t = estratos_trafico(t[features.poblacion(t)])

    def en(g: pd.DataFrame) -> dict:
        if g.empty:
            return {"filas": 0}
        return con_menos_sin(e_con[g.index], e_sin[g.index], g)

    def por(col: str) -> dict:
        return {str(k): en(g) for k, g in t.groupby(col, observed=True)}

    return {
        "dias": int(t["fecha_servicio"].nunique()),
        "con_sensor": en(t[t["_cobertura"] == CON_SENSOR]),
        "conjunto": en(t),
        "con_congestion_observada": en(t[t["_estado"] == CONGESTION]),
        "sin_sensor": en(t[t["_cobertura"] == SIN_SENSOR]),
        "por_cobertura": por("_cobertura"),
        "por_estado_observado": por("_estado"),
    }
```

La función del stage, después de `main`:

```python
def main_trafico(horizonte: int | None = None) -> None:
    """Stage `evaluate_trafico`: el modelo con tráfico menos el de sin tráfico en
    la prueba (ADR-024). Sin horizonte, el de `params.yaml`; con él, el del
    barrido."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    rutas = features.salidas(horizonte)
    con = predict.cargar(rutas["modelo_trafico"])
    sin = predict.cargar(rutas["modelo"])
    comprobar_pareja(con, sin)
    test = pd.read_parquet(rutas["tabla"] / "test.parquet")
    metricas = {
        "horizonte_paradas": horizonte or cfg["horizonte_paradas"],
        "prueba": [cfg["test_desde"], cfg["test_hasta"]],
        "modelos": {
            nombre: {
                "n_arboles": a["n_arboles"],
                "mlflow_run_id": a["mlflow_run_id"],
                "validacion": a["validacion"]["dias"],
            }
            for nombre, a in (("con", con), ("sin", sin))
        },
        "remuestreo": {
            "unidad": "viaje y día",
            "replicas": REPLICAS,
            "semilla": SEMILLA,
        },
        **comparacion_trafico(
            test,
            predict.predecir(con, test),
            predict.predecir(sin, test),
            cfg["objetivo"],
        ),
    }
    rutas["metricas"].mkdir(parents=True, exist_ok=True)
    (rutas["metricas"] / "trafico.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    plano = pd.json_normalize(
        {k: metricas[k] for k in ("con_sensor", "conjunto")}, sep="."
    ).iloc[0]
    with mlflow.start_run(run_id=con["mlflow_run_id"]):
        mlflow.log_metrics(
            {
                f"trafico.{k}": float(v)
                for k, v in plano.items()
                if isinstance(v, (int, float))
            }
        )
        mlflow.log_dict(metricas, "trafico.json")
    print(
        json.dumps(
            {k: metricas[k] for k in ("dias", "con_sensor", "conjunto")},
            indent=2,
            ensure_ascii=False,
        )
    )
```

Y la CLI:

```python
if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--horizonte", type=int, default=None, help="paradas (ADR-023)")
    a.add_argument("--trafico", action="store_true", help="con menos sin tráfico (ADR-024)")
    args = a.parse_args()
    (main_trafico if args.trafico else main)(args.horizonte)
```

- [ ] **Step 4: `analysis/trafico_validacion.py` importa los estratos y no los define.**
  - Borrar `COBERTURA`, `NOMBRES_COBERTURA`, `_comparar` y el import de `numpy`.
  - El final de `_tabla` queda así:

```python
    t = t[(t["fecha_servicio"] < FIN_DATOS) & features.poblacion(t)]
    return evaluate.estratos_trafico(t).reset_index(drop=True)
```

  - Cambiar las tres llamadas `_comparar(` por `evaluate.con_menos_sin(`.
  - Añadir al docstring: «Los estratos y la comparación son los de `evaluate.py`: la fase 2 los usa tal cual.»

- [ ] **Step 5: comprobar que pasa**

Run: `uv run pytest tests/test_modelo.py -q && uv run python -c "import project.analysis.trafico_validacion" && uv run ruff format . && uv run ruff check --fix .`
Expected: PASS y el import sin error

- [ ] **Step 6: commit**

```bash
git add src/project/evaluate.py src/project/analysis/trafico_validacion.py tests/test_modelo.py
git commit -m "feat(evaluate): con tráfico menos sin tráfico, con los estratos de la validación (ADR-024)"
```

---

### Task 5: stages de DVC (agente `pipeline-dvc`)

**Files:**
- Modify: `dvc.yaml` (cuatro stages nuevos)
- Modify: `.claude/tests/test_memoria.py:95-106` (stages documentados)
- Modify: `CLAUDE.md` (la línea de stages de «Pipeline ML»)

**Interfaces:**
- Consumes: `python -m project.train [--horizonte h] --trafico` y `python -m project.evaluate [--horizonte h] --trafico` (tareas 3 y 4).
- Produces: los stages `train_trafico`, `evaluate_trafico`, `train_trafico_h@<h>` y `evaluate_trafico_h@<h>`.

- [ ] **Step 1: test que falla.** Añadir al conjunto `documentados` de `test_los_stages_de_dvc_son_los_documentados`:

```python
        # la capa 192 (ADR-024): el mismo modelo con tráfico y la comparación
        "train_trafico",
        "evaluate_trafico",
        "train_trafico_h",
        "evaluate_trafico_h",
```

Run: `uv run pytest .claude/tests/test_memoria.py -k stages -v`
Expected: FAIL («dvc.yaml declara … la documentación describe …»)

- [ ] **Step 2: stages.** Después del stage `evaluate`:

```yaml
  # El mismo modelo con la capa 192 (ADR-024): misma configuración y mismas
  # filas, solo cambian las variables. El de sin tráfico es el de `train`.
  train_trafico:
    cmd: uv run python -m project.train --trafico
    deps:
      - data/processed/train.parquet
      - src/project/train.py
      - src/project/features.py
      - src/project/predict.py
      - src/project/evaluate.py
    params:
      - train
    outs:
      - models/model_trafico.pkl

  evaluate_trafico:
    # Con tráfico menos sin tráfico sobre las mismas filas de la población, con
    # los intervalos por viajes y por días: en el estrato con sensor (la
    # primaria con h = 5), en conjunto, donde la capa veía congestión y sin
    # sensor (ADR-024, enmienda del 10/10). Sobre la prueba se ejecuta UNA vez.
    cmd: uv run python -m project.evaluate --trafico
    deps:
      - data/processed/test.parquet
      - models/model.pkl
      - models/model_trafico.pkl
      - src/project/evaluate.py
      - src/project/predict.py
      - src/project/features.py
    params:
      - features.objetivo
      - features.test_desde
      - features.test_hasta
    metrics:
      - metrics/trafico.json:
          cache: false
```

Y al final del fichero, después de `evaluate_h`:

```yaml
  train_trafico_h:
    foreach: ${features.horizontes_barrido}
    do:
      cmd: uv run python -m project.train --horizonte ${item} --trafico
      deps:
        - data/processed/h${item}
        - src/project/train.py
        - src/project/features.py
        - src/project/predict.py
        - src/project/evaluate.py
      params:
        - train
      outs:
        - models/h${item}/model_trafico.pkl

  evaluate_trafico_h:
    foreach: ${features.horizontes_barrido}
    do:
      cmd: uv run python -m project.evaluate --horizonte ${item} --trafico
      deps:
        - data/processed/h${item}
        - models/h${item}/model.pkl
        - models/h${item}/model_trafico.pkl
        - src/project/evaluate.py
        - src/project/predict.py
        - src/project/features.py
      params:
        - features.objetivo
        - features.test_desde
        - features.test_hasta
      metrics:
        - metrics/horizontes/h${item}/trafico.json:
            cache: false
```

Añadir al diagrama de la cabecera de `dvc.yaml`, bajo la línea de los stages:

```yaml
#                                        └──> train_trafico ──> evaluate_trafico   (ADR-024)
```

- [ ] **Step 3: `CLAUDE.md`.** En «Pipeline ML», la frase de los stages queda así: «(curar → prepare → disponibilidad → tramos_ruta → features → train → evaluate, y `features_h`/`train_h`/`evaluate_h` para el barrido de horizontes, ADR-023; `train_trafico`/`evaluate_trafico` y sus `_h`, para la capa 192, ADR-024)».

- [ ] **Step 4: comprobar**

Run: `uv run pytest .claude/tests -q && uv run dvc stage list | Select-String trafico && uv run dvc dag --dot | Select-String "trafico" | Measure-Object`
Expected: PASS; diez stages con `trafico` (dos sueltos y cuatro por cada `foreach`); el DAG sin errores

- [ ] **Step 5: commit**

```bash
git add dvc.yaml .claude/tests/test_memoria.py CLAUDE.md
git commit -m "chore(dvc): stages del modelo con la capa 192 y de la comparación (ADR-024)"
```

---

### Task 6: mutantes 137-142 (agente `pipeline-dvc`)

**Files:**
- Modify: `auditoria/catalogo.toml` (al final)

- [ ] **Step 1: añadir los seis mutantes**

```toml
[[mutante]]
id = "137"
nombre = "la prueba no tiene tope: entra lo que traiga pull_data.sh después del 19/10"
capa = "features"
fichero = "src/project/features.py"
buscar = '''    prueba = (dia >= pd.Timestamp(test_desde)) & (dia <= pd.Timestamp(test_hasta))'''
reemplazar = '''    prueba = dia >= pd.Timestamp(test_desde)'''
detector = ["tests/test_features.py::test_el_split_deja_fuera_los_dias_partidos_y_lo_posterior_a_la_prueba"]
sondas = []

[[mutante]]
id = "138"
nombre = "el entrenamiento llega hasta la prueba: el 06/10 parcial mueve la validación"
capa = "features"
fichero = "src/project/features.py"
buscar = '''    train = dia <= pd.Timestamp(train_hasta)'''
reemplazar = '''    train = dia < pd.Timestamp(test_desde)'''
detector = ["tests/test_features.py::test_el_split_deja_fuera_los_dias_partidos_y_lo_posterior_a_la_prueba"]
sondas = []

[[mutante]]
id = "139"
nombre = "el estrato con sensor admite el 75 % justo"
capa = "modelo"
# La primaria se fijó con «más del 75 %» antes de ver la prueba (ADR-024).
fichero = "src/project/evaluate.py"
buscar = '''COBERTURA = [-np.inf, 0, 0.25, 0.5, 0.75, np.inf]'''
reemplazar = '''COBERTURA = [-np.inf, 0, 0.25, 0.5, 0.7, np.inf]'''
detector = ["tests/test_modelo.py::test_la_comparacion_del_trafico_separa_los_estratos_del_adr_024"]
sondas = []

[[mutante]]
id = "140"
nombre = "la comparación del tráfico cuenta filas que ya no llegan a tiempo"
capa = "modelo"
fichero = "src/project/evaluate.py"
buscar = '''    t = estratos_trafico(t[features.poblacion(t)])'''
reemplazar = '''    t = estratos_trafico(t)'''
detector = ["tests/test_modelo.py::test_la_comparacion_del_trafico_separa_los_estratos_del_adr_024"]
sondas = []

[[mutante]]
id = "141"
nombre = "la comparación acepta dos modelos cruzados o de entrenamientos distintos"
capa = "modelo"
# Cruzados, la primaria cambia de signo sin ningún error.
fichero = "src/project/evaluate.py"
buscar = '''        raise ValueError(
            "los modelos con y sin tráfico no son la misma pareja (ADR-024)"
        )'''
reemplazar = '''        pass'''
detector = ["tests/test_modelo.py::test_la_pareja_del_trafico_es_el_mismo_modelo_salvo_la_capa_192"]
sondas = []

[[mutante]]
id = "142"
nombre = "el modelo con tráfico se guarda encima del de sin tráfico"
capa = "modelo"
fichero = "src/project/features.py"
buscar = '''            "modelo_trafico": modelo.with_name(con_trafico),'''
reemplazar = '''            "modelo_trafico": modelo,'''
detector = ["tests/test_modelo.py::test_el_modelo_con_trafico_no_pisa_al_de_sin_trafico"]
sondas = []
```

Si `ruff format` dejó alguna línea de `buscar` distinta de la del fichero, copiar en `buscar` el texto exacto del fichero. Cada `buscar` debe aparecer **una sola vez**: comprobarlo con `Select-String -SimpleMatch` antes del commit.

- [ ] **Step 2: commit (`mutar.py` audita commits)**

```bash
git add auditoria/catalogo.toml
git commit -m "test(auditoria): mutantes 137-142 del corte y de la comparación del tráfico"
```

- [ ] **Step 3: ejecutar solo los nuevos**

Run: `uv run python auditoria/mutar.py --solo 137 138 139 140 141 142`
Expected: los seis «detectado»; resultados en `auditoria/resultados/mutantes_<hash>.json`

- [ ] **Step 4: commit del resultado** (como en a28d36d)

```bash
git add auditoria/resultados/
git commit -m "test(auditoria): mutantes 137-142 detectados"
```

---

### Task 7: ensayo de punta a punta con el corte antiguo (en línea, sin subagente)

Ninguna cifra de esta ejecución cuenta, y no se commitea: es la prueba ya contaminada (21/09-04/10).

- [ ] **Step 1: guardar el estado.** Ejecutar `uv run dvc status` y copiar `dvc.lock` a `<scratchpad>/dvc.lock.antes`.
- [ ] **Step 2: corte equivalente al actual, sin commitear.** En `params.yaml`: `train_hasta: "2026-09-20"`, `test_desde: "2026-09-21"` y `test_hasta: "2026-10-04"`.
- [ ] **Step 3: lanzar desacoplado**

```powershell
$env:PYTHONIOENCODING = "utf-8"
Start-Process -FilePath uv -ArgumentList "run","dvc","repro" -WorkingDirectory C:\Users\oppen\Code\TFM `
  -RedirectStandardOutput "<scratchpad>\ensayo.log" -RedirectStandardError "<scratchpad>\ensayo.err" -WindowStyle Hidden -PassThru
```

Vigilar con Monitor hasta que el proceso salga. Se rehacen `features` y `features_h`, porque cambió su bloque de params; después corren los cinco `train_trafico*` y los cinco `evaluate_trafico*`.

- [ ] **Step 4: comprobar sin leer resultados**
  - Las tablas son idénticas: en `dvc.lock`, los `md5` de los outs de `features` y `features_h@*` coinciden con los de `dvc.lock.antes`, y `train`, `train_h`, `evaluate` y `evaluate_h` no se han vuelto a ejecutar. Si algún md5 difiere, parar y diagnosticar antes de seguir.
  - Existen los cinco ficheros `trafico.json` (metrics/trafico.json y metrics/horizontes/h{2,3,5,10}/trafico.json), con las claves de la tarea 4. En los dos modelos, `modelos.*.validacion` es 14-20/09.
  - Solo plausibilidad, no resultado: `conjunto.con_menos_sin_s` está entre −2 y +2 s en los cinco.
- [ ] **Step 5: restaurar.** Ejecutar `git checkout params.yaml dvc.lock` y borrar los cinco `trafico.json` del ensayo. Se quedan los `.gitignore` que DVC añade en `models/` para `model_trafico.pkl`, que se commitean en la tarea 10.

---

### Task 8: el traslado de los estratos no cambia la bitácora 048 (en línea)

- [ ] **Step 1: lanzar desacoplado** `uv run python -m project.analysis.trafico_validacion` (unas 2 h), con el log en el scratchpad.
- [ ] **Step 2: comparar con el JSON commiteado**, sin la clave nueva:

```python
import json, subprocess
nuevo = json.load(open("auditoria/resultados/trafico_validacion.json", encoding="utf-8"))
viejo = json.loads(subprocess.run(
    ["git", "show", "HEAD:auditoria/resultados/trafico_validacion.json"],
    capture_output=True, text=True, encoding="utf-8", check=True).stdout)
def sin_relativa(x):
    return {k: sin_relativa(v) for k, v in x.items() if k != "relativa"} if isinstance(x, dict) else x
assert sin_relativa(nuevo) == viejo, "el traslado cambió la 048"
print("idéntico")
```

Expected: `idéntico`. Si no lo es, parar: el estrato del pipeline no sería el prerregistrado.

- [ ] **Step 3: commit**

```bash
git add auditoria/resultados/trafico_validacion.json
git commit -m "chore(analysis): trafico_validacion con los estratos de evaluate; cifras idénticas a la 048"
```

---

### Task 9: completitud de la captura en la Pi (en línea; solo lectura)

El criterio de día útil quedó fijado en la tarea 1, antes de mirar esto.

- [ ] **Step 1: acceso.** Probar `ssh -o BatchMode=yes -o ConnectTimeout=5 oppen@192.168.1.219 true`. Si falla (aún no hay clave), pasar al usuario los comandos del paso 2 para que los pegue en la Pi.
- [ ] **Step 2: en la Pi**

```bash
cd /opt/tfm && .venv/bin/python -m project.ingest.collect --status --out /srv/tfm-sd
df -h /srv/tfm-sd
python3 - /srv/tfm-sd/raw 2026-10-06 <<'EOF'
import datetime as dt, gzip, json, pathlib, sys
raiz, desde = pathlib.Path(sys.argv[1]), sys.argv[2]
for fuente in ("emt_buses", "trafico_estado"):
    ts = []
    for f in sorted((raiz / f"source={fuente}").glob("date=*/*.ndjson.gz")):
        if f.parent.name[5:] < desde:
            continue
        with gzip.open(f, "rt", encoding="utf-8") as g:
            ts += [dt.datetime.fromisoformat(json.loads(l)["ts_ingest_utc"]) for l in g]
    ts.sort()
    print(fuente, len(ts), ts[0] if ts else "-", ts[-1] if ts else "-")
    for a, b in zip(ts, ts[1:]):
        if b - a > dt.timedelta(minutes=15):
            print(f"  hueco {a:%m-%d %H:%M} -> {b:%m-%d %H:%M} UTC  {(b - a).total_seconds() / 3600:.1f} h")
EOF
```

- [ ] **Step 3: leer contra el criterio de la tarea 1.**
  - El latido del colector es reciente.
  - Hay sitio en la SD para llegar al 21/10, a unos 40 MB al día.
  - Ningún hueco de la EMT de más de 1 h en un día de servicio de los ya transcurridos (07/10 en adelante, de 02:00 a 02:00 UTC).
  - Si algún día ya cae, avisar al usuario: el ADR-024 se reabre si la prueba se queda sin días útiles.
- [ ] **Step 4: anotar** el recuento de sondeos y los huecos, con su fecha, al final de la nota del 11/10 en `docs/07_decisiones.md`. Ofrecer `/bitacora` con la cifra de completitud.

### Task 10: cierre de la fase A

- [ ] **Step 1:** ejecutar `uv run pytest -q` y `uv run pytest .claude/tests -q`. Expected: todo PASS, salvo el `xfail` estricto ya conocido.
- [ ] **Step 2:** `uv run dvc status` debe mostrar solo lo esperado (params de `features` cambiados y stages nuevos sin ejecutar), y `git status` solo los `.gitignore` de `models/`.
- [ ] **Step 3: commit**

```bash
git add models/h*/.gitignore docs/07_decisiones.md
git commit -m "chore(dvc): fase 2 del ADR-024 lista antes de traer la prueba"
```

---

## Fase B — desde el 21/10 (UTC)

### Task 11: traer la prueba

- [ ] **Step 1 (WSL):** `ORIGEN=oppen@192.168.1.219:/srv/tfm-sd/raw bash deploy_pi/pull_data.sh --verificar`. Expected: `>f+++++++++` solo en días de `date=2026-10-06` en adelante, más la línea habitual del 18/08. Ningún `>fc` en días que ya están en el repo.
- [ ] **Step 2 (WSL):** el mismo comando sin `--verificar`.
- [ ] **Step 3:** el script de la tarea 9 sobre `data/raw` local, desde el 06/10, aplicando el criterio de día útil a los días 07-19/10. Si cae un día, se escribe en la nota del ADR-024 **antes** de seguir.

### Task 12: `dvc repro` por tramos y comprobaciones antes de evaluar

- [ ] **Step 1:** lanzar desacoplado `uv run dvc repro prepare` (curar y prepare).
- [ ] **Step 2: etiquetas de la prueba** (calidad del dato, no resultados).
  - En `metrics/prepare.json`, `feeds` sigue siendo el de antes, sin versiones nuevas.
  - En `por_dia` del 07 al 19/10: pasos y viajes asignados por día. Marcar cualquier día por debajo de la mitad de la mediana de la semana 28/09-04/10.
- [ ] **Step 3: contraste del GTFS**, uno por versión de octubre capturada:

```powershell
Get-ChildItem data/raw/source=gtfs_emt -Recurse -Filter *.zip | ForEach-Object { uv run python -m project.analysis.comparar_gtfs $_.FullName }
```

Anotar, para los días 07-19/10, el porcentaje de pasos contradichos y las líneas que lo concentran. Es el límite declarado.
- [ ] **Step 4:** lanzar desacoplado `uv run dvc repro features features_h train train_h train_trafico train_trafico_h train_clasificador train_clasificador_h` (los clasificadores, ADR-025).
- [ ] **Step 5: comprobar la partición y la validación**
  - En `metrics/features.json`, `dias.test` = 13 (o menos, si la tarea 11 descartó alguno).
  - En los quince modelos (regresión, con tráfico y clasificador, ADR-025), `validacion.dias` = 28/09…04/10:

```powershell
uv run python -c "import pickle,glob; [print(p, pickle.load(open(p,'rb'))['validacion']['dias']) for p in sorted(glob.glob('models/**/*.pkl', recursive=True))]"
```

Si algo no cuadra, parar **antes** de evaluar.

### Task 13: la evaluación, una vez

- [ ] **Step 1:** `uv run dvc repro` (evaluate, evaluate_h, evaluate_trafico, evaluate_trafico_h, evaluate_clasificador, evaluate_clasificador_h). Una sola ejecución.
- [ ] **Step 2:** la primaria es `con_sensor` en metrics/horizontes/h5/trafico.json; la confirmación de la v2, `global` en `metrics/horizontes/h5/eval.json`. El clasificador, descriptivo: `titular` en metrics/horizontes/h5/clasificador.json (ADR-025).
- [ ] **Step 3: commit**

```bash
git add dvc.lock metrics/ models/.gitignore models/h*/.gitignore
git commit -m "chore(dvc): fase 2 del ADR-024, prueba del 07 al 19/10"
```

### Task 14: tribunal

- [ ] Agente `tribunal`, en Opus, con: el ADR-024 completo (enmienda y nota), los cinco `trafico.json`, el ADR-025 y los cinco `clasificador.json`, `eval.json` de h = 5, `metrics/features.json`, `metrics/prepare.json` y el diff de la fase. Pregunta: ¿se ajusta la cifra al protocolo prerregistrado? ¿Hay fuga, filas o días elegidos después o alguna desviación sin declarar? Resolver lo que encuentre antes de dar la cifra por buena.

### Task 15: entrega

- [ ] `/bitacora` con la primaria, el secundario, el control, los horizontes, la confirmación de la v2, el tamaño relativo y los límites (GTFS, festivos, huecos de la 192).
- [ ] Cerrar el ADR-024 con un párrafo de «Resultado» y la fecha.
- [ ] Actualizar «Estado» en `CLAUDE.md`.
- [ ] Commit. El push, solo si el usuario lo pide.
