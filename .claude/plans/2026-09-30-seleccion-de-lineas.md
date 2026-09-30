# Selección de líneas y soporte por línea — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sacar de la tabla de entrenamiento las líneas con etiqueta insuficiente (25, 63 y 73) e informar los baselines por línea solo donde hay soporte, dejándolo escrito en el ADR-018 y la bitácora 036.

**Architecture:** Todo el cambio de código vive en `src/project/features.py`: `construir` quita las líneas excluidas al final, cuando las variables ya están calculadas, y una función nueva `soporte_por_linea` clasifica cada línea de la prueba. `baselines` usa esa clasificación. Dos medidores en `src/project/analysis/` reproducen las cifras del criterio y del umbral. Solo se reejecuta el stage `features`.

**Tech Stack:** Python 3.10+, pandas, numpy, DuckDB (solo en los medidores), pytest, DVC, `uv`.

**Spec:** `docs/superpowers/specs/2026-09-30-seleccion-de-lineas-design.md`

Este plan vive en `.claude/plans/` y no en `docs/`: `.claude/tests/test_memoria.py` exige que toda ruta citada bajo `docs/` exista ya, y un plan cita ficheros que todavía no existen.

## Global Constraints

- Entorno Windows. Todo se lanza con `uv run …`; nunca `pip install`.
- Líneas excluidas: exactamente `["25", "63", "73"]`. Criterio: menos del **40 %** de las posiciones de la línea en viajes asignados, contando solo días no excluidos.
- Soporte: **100 viajes en 3 días de servicio distintos** en la prueba y **100 viajes** en entrenamiento. Un viaje es un par (`fecha_servicio`, `viaje_id`).
- Las filas de una línea excluida se quitan **al final** de `construir`: sus viajes siguen contando como sensor para las demás líneas.
- Nunca se excluye una línea por el error del modelo ni por su cobertura de sensores.
- `dvc.lock` no se edita a mano: lo actualiza `uv run dvc repro features`.
- Guardia nueva ⇒ mutante en `auditoria/catalogo.toml` que la ponga roja (ADR-011).
- Antes de cada commit: `uv run ruff format . && uv run ruff check .`, `uv run pytest` y `uv run pytest .claude/tests`, los tres en verde.
- Mensajes de commit en español, con prefijo convencional, y terminados en la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No se hace `git push`.

## Review Focus

Condiciones que el diseño implica y que ningún test cubriría si no se pide:

1. **La línea llega como número.** Un YAML sin comillas (`excluir_lineas: [25]`) o una columna `linea` entera harían que el filtro no quitara nada, sin error. Debe excluir igual. Test en la tarea 1.
2. **Una línea mal escrita en `excluir_lineas`** (`"C33"`). Sin comprobación, la exclusión no hace nada y nadie se entera. Debe fallar con un mensaje que nombre la línea. Test en la tarea 1.
3. **El mismo `viaje_id` en días distintos.** El tracker numera desde `v00000` cada día (bitácora 027). Contar por `viaje_id` solo daría menos viajes de los reales. Test en la tarea 2.
4. **Una línea que está en entrenamiento y no en la prueba.** No debe aparecer en el soporte ni romper nada. Test en la tarea 2.
5. **La prueba vacía** (un `test_desde` posterior al último día). `soporte_por_linea` debe devolver una tabla vacía con sus columnas, no lanzar. Test en la tarea 2.

---

### Task 1: Excluir líneas de la tabla

**Files:**
- Modify: `src/project/features.py` (docstring del módulo, `construir`, `main`)
- Modify: `params.yaml` (bloque `features`)
- Modify: `auditoria/catalogo.toml` (mutantes 088 y 089, al final)
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: nada de otras tareas.
- Produces: `features.construir(pasos, objetivo, horizonte=1, lags_min=(1, 5, 15), umbral_s=300.0, ventanas_flota_min=(), soporte_min=2, excluir_lineas=())`. `excluir_lineas` es una tupla de identificadores de línea (texto o número). Lanza `ValueError` si alguno no está en `pasos["linea"]`. Clave nueva `features.excluir_lineas` en `params.yaml`.

- [ ] **Step 1: Escribir los tests que fallan**

Añadir al final de `tests/test_features.py`:

```python
# --------------------------------------------------------------------------- #
# Selección de líneas y soporte por línea (ADR-018)
# --------------------------------------------------------------------------- #
def test_una_linea_excluida_no_tiene_filas_en_la_tabla():
    filas = [_paso("A", s, 2 * s, 0) for s in range(1, 4)]
    filas += [_paso("X", s, 2 * s, 0, linea="25") for s in range(1, 4)]
    assert set(_construir(filas)["linea"]) == {"1", "25"}
    assert set(_construir(filas, excluir_lineas=("25",))["linea"]) == {"1"}
    # La línea como número, en los pasos y en el parámetro: un YAML sin comillas.
    numerica = pd.DataFrame(filas).assign(linea=lambda d: d["linea"].astype(int))
    t = features.construir(numerica, objetivo=OBJ, excluir_lineas=(25,))
    assert set(t["linea"]) == {1}


def test_excluir_una_linea_que_no_existe_es_un_error():
    """Un nombre mal escrito no puede dejar la exclusión sin efecto y en silencio."""
    filas = [_paso("A", s, 2 * s, 0) for s in range(1, 4)]
    with pytest.raises(ValueError, match="C33"):
        _construir(filas, excluir_lineas=("C33",))


def test_una_linea_excluida_sigue_midiendo_el_tramo_para_las_demas():
    """Se excluye como objetivo, no como sensor: sus etiquetas son correctas.

    Lo que falla en una línea excluida es que se etiqueta poco de ella, no que lo
    etiquetado esté mal. Quitarla de la entrada dejaría a las demás sin sus
    medidas del tramo.
    """
    filas = [
        _paso("A", 1, 10, 0),  # la fila evaluada: t = 10 min, objetivo P02
        _paso("A", 2, 12, 0),
        *_tramo("B", 4, 6, 60, linea="25"),
        *_tramo("C", 7, 9, 120, linea="25"),
    ]
    t = _construir(
        filas,
        horizonte=1,
        ventanas_flota_min=(5,),
        soporte_min=2,
        excluir_lineas=("25",),
    )
    assert set(t["linea"]) == {"1"}
    f = _fila(t, "A", 1)
    assert f["tramo_soporte_5min"] == 2
    assert f["tramo_ganado_5min"] == 90.0  # mediana de 60 y 120
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_features.py -q -k "excluida or excluir"`
Expected: 3 failed, con `TypeError: construir() got an unexpected keyword argument 'excluir_lineas'`.

- [ ] **Step 3: Implementar en `construir`**

En `src/project/features.py`, la firma y el arranque de `construir` pasan de

```python
    ventanas_flota_min: tuple[int, ...] = (),
    soporte_min: int = 2,
) -> pd.DataFrame:
    """La tabla: una fila por paso con objetivo, sus variables y sus claves."""
```

a

```python
    ventanas_flota_min: tuple[int, ...] = (),
    soporte_min: int = 2,
    excluir_lineas: tuple[str, ...] = (),
) -> pd.DataFrame:
    """La tabla: una fila por paso con objetivo, sus variables y sus claves."""
    excluidas = {str(x) for x in excluir_lineas}
    faltan = excluidas - set(pasos["linea"].astype(str))
    if faltan:
        raise ValueError(
            f"excluir_lineas nombra líneas que no están en los pasos: {sorted(faltan)}"
        )
```

Y, más abajo en la misma función, la línea

```python
    p = p[p[objetivo].notna()].copy()
```

pasa a

```python
    # Las líneas excluidas salen AL FINAL, con las variables ya calculadas: sus
    # viajes siguen contando como sensor para las demás (ADR-018).
    p = p[p[objetivo].notna() & ~p["linea"].astype(str).isin(excluidas)].copy()
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_features.py -q`
Expected: 13 passed.

- [ ] **Step 5: Conectar `params.yaml` y `main`**

En `params.yaml`, dentro de `features:`, justo después de la línea `umbral_retraso_s: 300 …`:

```yaml
  # Líneas fuera de la tabla por calidad de la etiqueta: menos del 40 % de sus
  # posiciones en viajes asignados (ADR-018, bitácora 036). Lista explícita y no
  # regla automática: que una línea entre o salga es una decisión, no un efecto
  # de reejecutar. Se comprueba con `medir_rutas lineas`.
  excluir_lineas: ["25", "63", "73"]
```

En `main()` de `src/project/features.py`, la llamada a `construir` gana un argumento al final:

```python
        ventanas_flota_min=flota,
        soporte_min=cfg["soporte_min"],
        excluir_lineas=tuple(cfg["excluir_lineas"]),
    )
```

En el docstring del módulo, tras el párrafo que acaba en «La capa municipal 192 va después.», añadir:

```
Las líneas de `excluir_lineas` salen de la tabla, pero sus viajes siguen
contando como sensor para las demás (ADR-018).
```

- [ ] **Step 6: Añadir los mutantes al catálogo**

Al final de `auditoria/catalogo.toml` (el fichero usa finales de línea CRLF; conservarlos):

```toml

[[mutante]]
id = "088"
nombre = "las líneas excluidas se quedan en la tabla"
capa = "features"
# El filtro no hace nada: la 25, la 63 y la 73 vuelven a la muestra con el 14-29 %
# de sus posiciones etiquetadas (ADR-018).
fichero = "src/project/features.py"
buscar = '''    p = p[p[objetivo].notna() & ~p["linea"].astype(str).isin(excluidas)].copy()'''
reemplazar = '''    p = p[p[objetivo].notna()].copy()'''
detector = ["tests/test_features.py::test_una_linea_excluida_no_tiene_filas_en_la_tabla"]
sondas = []

[[mutante]]
id = "089"
nombre = "las líneas excluidas se quitan de la entrada y dejan de ser sensor"
capa = "features"
# La tabla sale sin ellas igual, pero las demás líneas pierden sus medidas del tramo.
fichero = "src/project/features.py"
buscar = '''    p = pasos.assign(fecha_servicio=pd.to_datetime(pasos["fecha_servicio"]))'''
reemplazar = '''    p = pasos.assign(fecha_servicio=pd.to_datetime(pasos["fecha_servicio"]))
    p = p[~p["linea"].astype(str).isin(excluidas)]'''
detector = ["tests/test_features.py::test_una_linea_excluida_sigue_midiendo_el_tramo_para_las_demas"]
sondas = []
```

Comprobar que el catálogo se lee y que cada `buscar` aparece una sola vez:

Run:
```bash
uv run python -c "import tomllib, pathlib; c = tomllib.load(open('auditoria/catalogo.toml', 'rb'))['mutante']; s = pathlib.Path('src/project/features.py').read_text(encoding='utf-8'); print([(m['id'], s.count(m['buscar'])) for m in c if m['id'] in ('088', '089')])"
```
Expected: `[('088', 1), ('089', 1)]`

- [ ] **Step 7: Verificar y hacer commit**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -q && uv run pytest .claude/tests -q`
Expected: `All checks passed!`, `190 passed, 5 xfailed` y la suite de andamiaje sin fallos.

```bash
git add src/project/features.py params.yaml tests/test_features.py auditoria/catalogo.toml
git commit -m "feat(features): las líneas con etiqueta insuficiente salen de la tabla" -m "excluir_lineas (25, 63 y 73) quita sus filas al final de construir: siguen contando como sensor para las demás. Una línea que no está en los pasos es un error. Mutantes 088 y 089 al catálogo. ADR-018." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Soporte por línea y baselines por grupo

**Files:**
- Modify: `src/project/features.py` (`soporte_por_linea` nueva, `baselines`, `main`)
- Modify: `params.yaml` (bloque `features`)
- Modify: `auditoria/catalogo.toml` (mutantes 090 y 091, al final)
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: `features.CLAVE_VIAJE == ["fecha_servicio", "viaje_id"]`, ya existente.
- Produces:
  - `features.soporte_por_linea(train, test, min_viajes=100, min_dias=3) -> pd.DataFrame`, con índice `linea` (las líneas de `test`) y columnas `viajes`, `dias`, `viajes_train`, `grupo`. `grupo` vale `"propia"`, `"poco_soporte"` o `"sin_entrenamiento"`.
  - `features.baselines(test, objetivo, soporte) -> dict`, con las claves `horario`, `persistencia`, `por_linea` y `por_grupo`. Cada entrada de `por_linea` trae `filas`, `horario`, `persistencia`, `viajes`, `dias` y `grupo`.
  - Claves nuevas `features.linea_min_viajes` y `features.linea_min_dias` en `params.yaml`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_features.py`, añadir `import json` a los imports del principio (antes de `import numpy as np`) y, al final del fichero:

```python
def _viajes(linea, n, dias):
    """`n` viajes de la línea en `dias` días, dos filas por viaje.

    El mismo `viaje_id` se repite de un día a otro, como en la captura real
    (bitácora 027): un viaje es el par (día de servicio, `viaje_id`).
    """
    dia0 = pd.Timestamp("2026-09-14")
    return pd.DataFrame(
        [
            {
                "linea": linea,
                "viaje_id": f"v{i // dias}",
                "fecha_servicio": dia0 + pd.Timedelta(days=i % dias),
            }
            for i in range(n)
            for _ in range(2)
        ]
    )


def test_el_soporte_de_una_linea_se_cuenta_en_viajes_y_dias():
    """100 viajes en 3 días de prueba y 100 de entrenamiento: cifra propia."""
    # F solo está en entrenamiento: no aparece en el soporte.
    train = pd.concat([_viajes(x, 100, 5) for x in "ABCF"] + [_viajes("E", 99, 5)])
    test = pd.concat(
        [
            _viajes("A", 100, 3),  # justo en el umbral
            _viajes("B", 99, 3),  # un viaje menos; en filas serían 198
            _viajes("C", 100, 2),  # los viajes, pero en dos días
            _viajes("D", 500, 5),  # no está en entrenamiento
            _viajes("E", 100, 3),  # en entrenamiento no llega a 100
        ]
    )
    s = features.soporte_por_linea(train, test, min_viajes=100, min_dias=3)
    assert s["grupo"].to_dict() == {
        "A": "propia",
        "B": "poco_soporte",
        "C": "poco_soporte",
        "D": "sin_entrenamiento",
        "E": "poco_soporte",
    }
    assert s.at["B", "viajes"] == 99 and s.at["A", "dias"] == 3
    vacio = features.soporte_por_linea(train, test.iloc[:0])
    assert vacio.empty and "grupo" in vacio.columns


def test_los_baselines_traen_el_soporte_y_los_grupos():
    test = pd.DataFrame(
        {
            "linea": ["A", "A", "B"],
            "fecha_servicio": pd.Timestamp("2026-09-14"),
            "viaje_id": ["a", "a", "b"],
            "retraso_s": [10.0, 20.0, 0.0],
            OBJ: [20.0, 20.0, 100.0],
        }
    )
    s = features.soporte_por_linea(test[test["linea"] == "A"], test, 1, 1)
    b = features.baselines(test, OBJ, s)
    assert b["por_linea"]["A"]["grupo"] == "propia"
    assert b["por_linea"]["A"]["viajes"] == 1
    assert b["por_linea"]["B"]["grupo"] == "sin_entrenamiento"
    assert b["por_grupo"]["sin_entrenamiento"]["persistencia"]["mae_s"] == 100.0
    assert b["persistencia"]["mae_s"] == pytest.approx(36.67)  # (10 + 0 + 100) / 3
    json.dumps(b)  # va a metrics/features.json: tiene que ser serializable
```

- [ ] **Step 2: Comprobar que fallan**

Run: `uv run pytest tests/test_features.py -q -k "soporte or baselines"`
Expected: 2 failed, 1 passed (el que pasa es el test ya existente `test_el_tramo_sin_soporte_suficiente_no_se_estima`). Los dos fallos, con `AttributeError: module 'project.features' has no attribute 'soporte_por_linea'`.

- [ ] **Step 3: Implementar `soporte_por_linea` y rehacer `baselines`**

En `src/project/features.py`, sustituir la función `baselines` entera (desde `def baselines(` hasta la línea anterior a `def main()`) por:

```python
def soporte_por_linea(
    train: pd.DataFrame, test: pd.DataFrame, min_viajes: int = 100, min_dias: int = 3
) -> pd.DataFrame:
    """Qué líneas de la prueba pueden informarse con cifra propia (ADR-018).

    Una fila por línea de `test`. Se cuenta en VIAJES y no en filas: las paradas
    de un mismo viaje están correlacionadas, y 200 filas de cinco viajes no son
    200 observaciones. Un viaje es un par (día de servicio, `viaje_id`), porque
    el `viaje_id` se repite de un día a otro.

    `propia`: al menos `min_viajes` en `min_dias` días de prueba y `min_viajes`
    en entrenamiento. `sin_entrenamiento`: el modelo no ha visto la línea.
    `poco_soporte`: el resto. Ninguna se tira: las dos últimas se informan
    agrupadas.
    """

    def viajes(t: pd.DataFrame) -> pd.Series:
        return t.drop_duplicates(["linea", *CLAVE_VIAJE]).groupby("linea").size()

    s = pd.DataFrame(
        {
            "viajes": viajes(test),
            "dias": test.groupby("linea")["fecha_servicio"].nunique(),
        }
    )
    s["viajes_train"] = viajes(train).reindex(s.index, fill_value=0)
    propia = (
        (s["viajes"] >= min_viajes)
        & (s["dias"] >= min_dias)
        & (s["viajes_train"] >= min_viajes)
    )
    s["grupo"] = np.where(
        s["viajes_train"] == 0,
        "sin_entrenamiento",
        np.where(propia, "propia", "poco_soporte"),
    )
    return s


def baselines(test: pd.DataFrame, objetivo: str, soporte: pd.DataFrame) -> dict:
    """MAE y RMSE de los baselines obligatorios: horario (0) y persistencia.

    Globales, por línea con su soporte, y por grupo de soporte
    (`soporte_por_linea`).
    """

    def errores(pred: pd.Series, real: pd.Series) -> dict:
        e = (pred - real).to_numpy()
        return {
            "mae_s": round(float(np.abs(e).mean()), 2),
            "rmse_s": round(float(np.sqrt((e**2).mean())), 2),
        }

    def los_dos(g: pd.DataFrame) -> dict:
        return {
            "filas": int(len(g)),
            "horario": errores(pd.Series(0.0, index=g.index), g[objetivo]),
            "persistencia": errores(g["retraso_s"], g[objetivo]),
        }

    fuera = {k: v for k, v in los_dos(test).items() if k != "filas"}
    fuera["por_linea"] = {
        str(linea): {
            **los_dos(g),
            "viajes": int(soporte.at[linea, "viajes"]),
            "dias": int(soporte.at[linea, "dias"]),
            "grupo": str(soporte.at[linea, "grupo"]),
        }
        for linea, g in test.groupby("linea")
    }
    grupo = test["linea"].map(soporte["grupo"])
    fuera["por_grupo"] = {str(k): los_dos(g) for k, g in test.groupby(grupo)}
    return fuera
```

- [ ] **Step 4: Comprobar que pasan**

Run: `uv run pytest tests/test_features.py -q`
Expected: 15 passed.

- [ ] **Step 5: Conectar `params.yaml` y `main`**

En `params.yaml`, dentro de `features:`, justo después de `excluir_lineas`:

```yaml
  # Soporte para informar una línea con cifra propia: viajes y días de servicio
  # en la prueba, y los mismos viajes en entrenamiento. Por debajo se informa
  # agrupada, no se tira (ADR-018).
  linea_min_viajes: 100
  linea_min_dias: 3
```

En `main()` de `src/project/features.py`, tras la línea `train, test = partir(tabla, cfg["test_desde"])`:

```python
    soporte = soporte_por_linea(
        train, test, cfg["linea_min_viajes"], cfg["linea_min_dias"]
    )
```

y en el diccionario `metricas`, la línea de los baselines pasa a:

```python
        "baselines_test": baselines(test, cfg["objetivo"], soporte),
```

- [ ] **Step 6: Añadir los mutantes al catálogo**

Al final de `auditoria/catalogo.toml` (CRLF):

```toml

[[mutante]]
id = "090"
nombre = "el soporte de una línea no exige días distintos"
capa = "features"
# Cien viajes de un solo día pasan por una línea bien observada.
fichero = "src/project/features.py"
buscar = '''        & (s["dias"] >= min_dias)'''
reemplazar = '''        & (s["dias"] >= 1)'''
detector = ["tests/test_features.py::test_el_soporte_de_una_linea_se_cuenta_en_viajes_y_dias"]
sondas = []

[[mutante]]
id = "091"
nombre = "el soporte de una línea se cuenta en filas y no en viajes"
capa = "features"
# Las paradas de un viaje están correlacionadas: contar filas infla el soporte
# unas veinte veces.
fichero = "src/project/features.py"
buscar = '''        return t.drop_duplicates(["linea", *CLAVE_VIAJE]).groupby("linea").size()'''
reemplazar = '''        return t.groupby("linea").size()'''
detector = ["tests/test_features.py::test_el_soporte_de_una_linea_se_cuenta_en_viajes_y_dias"]
sondas = []
```

Run:
```bash
uv run python -c "import tomllib, pathlib; c = tomllib.load(open('auditoria/catalogo.toml', 'rb'))['mutante']; s = pathlib.Path('src/project/features.py').read_text(encoding='utf-8'); print([(m['id'], s.count(m['buscar'])) for m in c if m['id'] in ('088', '089', '090', '091')])"
```
Expected: `[('088', 1), ('089', 1), ('090', 1), ('091', 1)]`

- [ ] **Step 7: Verificar y hacer commit**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -q && uv run pytest .claude/tests -q`
Expected: `All checks passed!`, `192 passed, 5 xfailed` y la suite de andamiaje sin fallos.

```bash
git add src/project/features.py params.yaml tests/test_features.py auditoria/catalogo.toml
git commit -m "feat(features): soporte por línea y baselines por grupo" -m "soporte_por_linea clasifica cada línea de la prueba: cifra propia con 100 viajes en 3 días y 100 de entrenamiento; si no, poco_soporte o sin_entrenamiento. Se cuenta en viajes, no en filas. baselines trae viajes, días y grupo por línea, y los baselines de cada grupo. Mutantes 090 y 091. ADR-018." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Reejecutar el stage `features`

**Files:**
- Regenerados por DVC: `data/processed/train.parquet`, `data/processed/test.parquet`
- Modify: `metrics/features.json`, `dvc.lock` (los escribe `dvc repro`)

**Interfaces:**
- Consumes: las claves de `params.yaml` y las funciones de las tareas 1 y 2.
- Produces: la tabla sin las líneas 25, 63 y 73, y `metrics/features.json` con `baselines_test.por_grupo`. Las tareas 4 y 5 leen de aquí.

- [ ] **Step 1: Reejecutar**

Run: `uv run dvc repro features`
Expected: solo se ejecuta `features` (`curar` y `prepare` dicen «didn't change, skipping»). Tarda unos minutos.

Si DVC quiere reejecutar `curar` o `prepare`, parar y avisar: alguien ha traído captura nueva a `data/raw/`, y las cifras esperadas de este plan son las de las 32 jornadas hasta el 18/09.

- [ ] **Step 2: Comprobar las cifras**

Run:
```bash
uv run python -c "import json; m = json.load(open('metrics/features.json', encoding='utf-8')); b = m['baselines_test']; print(m['filas'], m['positivos']); print(b['horario'], b['persistencia']); print(len(b['por_linea']), sorted(set(b['por_linea']) & {'25', '63', '73'})); print({k: v['filas'] for k, v in b['por_grupo'].items()}); import collections; print(collections.Counter(v['grupo'] for v in b['por_linea'].values()))"
```
Expected, exactamente:
```
{'train': 1229162, 'test': 266893} {'train': 0.0565, 'test': 0.0583}
{'mae_s': 139.73, 'rmse_s': 195.36} {'mae_s': 37.54, 'rmse_s': 72.49}
40 []
{'poco_soporte': 9055, 'propia': 252306, 'sin_entrenamiento': 5532}
Counter({'propia': 24, 'sin_entrenamiento': 8, 'poco_soporte': 8})
```

Si alguna cifra no coincide, parar y avisar: no seguir con las tareas 4 y 5, que citan estos números.

- [ ] **Step 3: Comprobar el estado de DVC**

Run: `uv run dvc status`
Expected: solo `train` y `evaluate` aparecen como cambiados (siguen vacíos; es lo esperado).

- [ ] **Step 4: Commit**

```bash
git add metrics/features.json dvc.lock
git commit -m "chore(dvc): features sin las líneas 25, 63 y 73" -m "dvc repro features. La tabla pasa de 1.236.585 a 1.229.162 filas de entrenamiento y de 269.493 a 266.893 de prueba. La persistencia, de 37,62 a 37,54 s de MAE. 40 líneas en la prueba: 24 con cifra propia, 8 con poco soporte y 8 sin entrenamiento." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Medidores del criterio y del umbral

**Files:**
- Modify: `src/project/analysis/medir_rutas.py` (función `lineas`)
- Create: `src/project/analysis/medir_soporte.py`

**Interfaces:**
- Consumes: `features.soporte_por_linea` y `features.CLAVE_VIAJE` (tarea 2); `data/processed/` ya reejecutado (tarea 3).
- Produces: dos comandos reproducibles que cita la bitácora 036 (tarea 5): `uv run python -m project.analysis.medir_rutas lineas` y `uv run python -m project.analysis.medir_soporte`.

- [ ] **Step 1: Añadir el indicador a `medir_rutas lineas`**

En `src/project/analysis/medir_rutas.py`, dentro de `lineas()`, el bloque `tra as (…)` de la consulta pasa de

```sql
        tra as (
            select linea, count(*) tramos,
                   sum((motivo = 'asignado')::int) asignados,
                   sum((motivo = 'corto')::int) cortos
            from {v} group by 1),
```

a

```sql
        tra as (
            select linea, count(*) tramos,
                   sum((motivo = 'asignado')::int) asignados,
                   sum((motivo = 'corto')::int) cortos,
                   coalesce(sum(posiciones) filter (where motivo = 'asignado'), 0)
                       / sum(posiciones) filter (where motivo <> 'excluido')
                       pos_asignadas
            from {v} group by 1),
```

Tras la línea `d["exito_con_cortos"] = (d["asignados"] / d["tramos"]).round(3)` añadir:

```python
    d["pos_asignadas"] = d["pos_asignadas"].round(3)
```

Y al final de la función, después del `print` de la 24 y la 25:

```python
    bajo = d[d["pos_asignadas"] < 0.40].sort_values("pos_asignadas")
    print(
        "\n  menos del 40 % de sus posiciones en viajes asignados (ADR-018): "
        + ", ".join(
            f"{a} ({b:.1%})" for a, b in zip(bajo["linea"], bajo["pos_asignadas"])
        )
    )
```

En el docstring del módulo, la descripción de `LINEAS` gana una frase al final:

```
                 `pos_asignadas` es la fracción de las posiciones de la línea,
                 en días no excluidos, que cae en un viaje asignado: el criterio
                 de `features.excluir_lineas` (ADR-018).
```

- [ ] **Step 2: Comprobar el indicador**

Run: `uv run python -m project.analysis.medir_rutas lineas`
Expected: la tabla trae la columna `pos_asignadas` (0.464 en la 24, 0.781 en la 93) y la última línea es:

```
  menos del 40 % de sus posiciones en viajes asignados (ADR-018): 96 (0.0%), 100 (0.0%), 8 (0.0%), 98E (0.0%), 73 (14.3%), 25 (17.7%), 63 (29.0%)
```

(El orden de las cuatro líneas al 0 % puede variar.)

- [ ] **Step 3: Crear `medir_soporte.py`**

Crear `src/project/analysis/medir_soporte.py`:

```python
"""¿Con cuántos viajes puede informarse una línea con cifra propia?

    uv run python -m project.analysis.medir_soporte

Por línea de la prueba: viajes, días, viajes de entrenamiento, grupo de soporte,
el MAE de la persistencia y el semiancho de su intervalo del 95 %. El intervalo
sale de remuestrear VIAJES enteros: las paradas de un viaje están
correlacionadas, y remuestrear filas daría un intervalo demasiado estrecho.

Es la tabla que fija `features.linea_min_viajes` (ADR-018, bitácora 036). Lee
`data/processed/`; nada del pipeline importa de aquí.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from project.config import RAIZ, settings
from project.features import CLAVE_VIAJE, soporte_por_linea

REMUESTRAS = 1000


def medir() -> pd.DataFrame:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    obj = cfg["objetivo"]
    cols = ["linea", *CLAVE_VIAJE, "retraso_s", obj]
    train = pd.read_parquet(settings.processed_dir / "train.parquet", columns=cols)
    test = pd.read_parquet(settings.processed_dir / "test.parquet", columns=cols)
    s = soporte_por_linea(train, test, cfg["linea_min_viajes"], cfg["linea_min_dias"])
    test = test.assign(e=(test["retraso_s"] - test[obj]).abs())
    rng = np.random.default_rng(0)
    for linea, g in test.groupby("linea"):
        v = g.groupby(CLAVE_VIAJE)["e"].agg(["sum", "count"]).to_numpy()
        i = rng.integers(0, len(v), size=(REMUESTRAS, len(v)))
        mae = v[i, 0].sum(axis=1) / v[i, 1].sum(axis=1)
        lo, hi = np.percentile(mae, [2.5, 97.5])
        s.at[linea, "mae_s"] = g["e"].mean()
        s.at[linea, "semi_ic_s"] = (hi - lo) / 2
    s["ic_pct"] = 100 * s["semi_ic_s"] / s["mae_s"]
    return s.sort_values("viajes")


if __name__ == "__main__":
    print(medir().round(1).to_string())
```

- [ ] **Step 4: Comprobar el medidor**

Run: `uv run python -m project.analysis.medir_soporte`
Expected: 40 líneas, ordenadas por `viajes`. Tres filas de control, que deben coincidir:

```
       viajes  dias  viajes_train              grupo  mae_s  semi_ic_s  ic_pct
98         16     2          1005       poco_soporte   44.5        6.3    14.2
24        172     5           730             propia   26.6        1.8     6.6
93        714     5          2830             propia   38.7        1.0     2.5
```

Y los rangos de `ic_pct`: de 4,0 a 25,4 en las 15 líneas con menos de 100 viajes; de 3,0 a 6,6 en las 6 que tienen entre 100 y 300; de 1,8 a 4,0 en las 19 con 300 o más, salvo la 67, con 10,5.

Si no coinciden, parar y avisar: la bitácora 036 cita estas cifras.

- [ ] **Step 5: Verificar y hacer commit**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -q && uv run pytest .claude/tests -q`
Expected: todo en verde; `192 passed, 5 xfailed`.

```bash
git add src/project/analysis/medir_rutas.py src/project/analysis/medir_soporte.py
git commit -m "feat(analysis): el indicador de reconstrucción por línea y el soporte con su intervalo" -m "medir_rutas lineas trae pos_asignadas, el criterio de excluir_lineas, y lista las líneas por debajo del 40 %. medir_soporte da, por línea de la prueba, viajes, días, grupo y el semiancho del IC 95 % del MAE de la persistencia remuestreando viajes." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: ADR-018, bitácora 036 y punteros

**Files:**
- Modify: `docs/07_decisiones.md` (ADR-018 nuevo; sección «Pendientes de decidir»)
- Create: `docs/bitacora/036-la-muestra-son-todas-las-lineas-menos-tres.md`
- Modify: `docs/bitacora/README.md` (fila 036 en el índice)
- Modify: `CLAUDE.md` (sección «Pipeline ML»)

**Interfaces:**
- Consumes: las cifras de las tareas 3 y 4.
- Produces: la fuente de verdad de la decisión, que leen todas las sesiones.

- [ ] **Step 1: ADR-018**

En `docs/07_decisiones.md`, insertar antes de `## Pendientes de decidir` (tras el separador `---` que cierra el ADR-017):

```markdown
## ADR-018 · La muestra son todas las líneas menos las de etiqueta insuficiente; la cobertura de sensores es un estrato · revisable

**Decisión.** Cuatro, que sustituyen a la propuesta de acotar a 4-6 corredores:

1. Se entrena y se evalúa con todas las líneas etiquetadas menos las que no
   pasan el criterio de calidad.
2. Queda fuera la línea con menos del **40 %** de sus posiciones en viajes
   asignados, en días no excluidos. Hoy son la **25** (17,7 %), la **63**
   (29,0 %) y la **73** (14,3 %): `params.yaml → features.excluir_lineas`. La 24
   se queda, con un 46,4 %, señalada como dudosa.
3. La cobertura de sensores de tráfico define un **estrato de evaluación**, no
   recorta la muestra. Lo que aporte la capa 192 se informa dentro del estrato.
4. Una línea se informa con cifra propia con al menos **100 viajes en 3 días de
   servicio** en la prueba y 100 viajes en entrenamiento
   (`features.soporte_por_linea`). Las demás cuentan en la métrica global y se
   informan agrupadas en `poco_soporte` y `sin_entrenamiento`.

**Por qué.** Los dos motivos para acotar eran el coste de etiquetar las 47
líneas y la cobertura de sensores. El primero desapareció: el pipeline etiqueta
todas. Los cinco corredores propuestos eran el 24,5 % de las filas. Y recortar
por cobertura deja fuera justo las líneas periféricas, lo que sesga la muestra a
favor de la hipótesis (bitácora 026).

**Consecuencias.** La tabla pierde 10.023 filas, el 0,67 %. Las líneas excluidas
siguen contando como sensor para las demás: sus etiquetas son correctas, lo que
falla es que son pocas. `excluir_lineas` es una lista explícita y no una regla
recalculada: que una línea entre o salga es una decisión.

**Lo que hay que declarar.** La 25 es también la línea peor cubierta por sensores
(27 %). Excluirla por la calidad de su etiqueta favorece de rebote a la
hipótesis. Con las tres líneas excluidas, la persistencia pasa de 37,62 a
37,54 s de MAE en la prueba.

**Nunca** se excluye una línea por el error del modelo ni por su cobertura de
sensores.

**Alternativas.** Acotar a corredores: descartada, por lo anterior. Excluir solo
la 25: descartada, porque la 63 y la 73 tienen peor indicador. Umbral del 50 %,
que sacaría también la 24: queda como opción si su indicador no mejora.

**Qué la reabriría.** Que el indicador de una línea excluida supere el 40 % o el
de una incluida baje de ahí, con más captura o con un tracker mejor. Que el
estrato de sensores, una vez medido, solo aporte ruido. Que con la captura
completa casi ninguna línea quede por debajo del soporte.

Reproducir: `uv run python -m project.analysis.medir_rutas lineas` (el criterio)
y `uv run python -m project.analysis.medir_soporte` (el umbral). Detalle en la
bitácora 036.

---
```

- [ ] **Step 2: «Pendientes de decidir»**

En la misma sección de `docs/07_decisiones.md`, sustituir el punto entero que empieza por `- **Selección de corredores.**` por:

```markdown
- **Cobertura de sensores por tramo.** El estrato de evaluación del ADR-018
  necesita saber qué tramos entre paradas tienen un sensor de la capa 192
  encima. Hoy la cobertura solo está medida por posición (69,4 % a menos de
  50 m, `docs/10`). Se mide al meter la capa 192 en `features.py`.
```

- [ ] **Step 3: Bitácora 036**

Crear `docs/bitacora/036-la-muestra-son-todas-las-lineas-menos-tres.md`:

```markdown
---
id: 036
titulo: La muestra son todas las líneas menos tres; la 25, la 63 y la 73 tienen menos del 30 % de sus posiciones en viajes asignados, y el resto, entre el 46 y el 92 %
fecha: 2026-09-30
tipo: limitacion
capa: pipeline
capitulo: metodologia
impacto: alto
estado: aceptado
evidencia: uv run python -m project.analysis.medir_rutas lineas; uv run python -m project.analysis.medir_soporte
trampa: —
---

## Qué se observó

**Cuánto de cada línea llega a la etiqueta.** Posiciones en tramos asignados a
un viaje programado, sobre las posiciones de la línea en días no excluidos:

| línea | posiciones válidas | en viajes asignados |
|---|---|---|
| 96, 98E, 100, 8 | 78.387 | 0 % (sin trazado u horario en el GTFS) |
| 73 | 15.396 | **14,3 %** |
| 25 | 206.710 | **17,7 %** |
| 63 | 35.823 | **29,0 %** |
| 24 | 140.297 | 46,4 % |
| 14 | 839 | 57,1 % |
| las otras 38 | | 70,0 - 92,4 % |

Hay un hueco entre el 29 % de la 63 y el 46 % de la 24. El umbral se pone en el
40 %: fuera la 25, la 63 y la 73. Salen 10.023 filas de la tabla (7.932, 1.524 y
567), el 0,67 %. La tabla queda en 1.229.162 filas de entrenamiento y 266.893 de
prueba, y la persistencia pasa de 37,62 a 37,54 s de MAE.

**Con cuántos viajes puede informarse una línea.** Semiancho del intervalo del
95 % del MAE de la persistencia, remuestreando viajes, en las 40 líneas de la
prueba:

| viajes de la línea en la prueba | líneas | semiancho, en % del MAE | en segundos |
|---|---|---|---|
| menos de 100 | 15 | 4,0 - 25,4 | 1,2 - 12,1 |
| de 100 a 300 | 6 | 3,0 - 6,6 | 0,9 - 1,8 |
| 300 o más | 19 | 1,8 - 4,0 (la 67: 10,5) | 0,7 - 1,5 (la 67: 4,5) |

Con el umbral en 100 viajes en 3 días de prueba y 100 de entrenamiento:

| grupo | líneas | filas de prueba | MAE de la persistencia |
|---|---|---|---|
| cifra propia | 24 | 252.306 | 37,56 s |
| poco soporte | 8 (71, 98, 62, 70, 28, 4, 40, 6) | 9.055 | 37,24 s |
| sin entrenamiento | 8 (60, 64, 9, 10, 11, 14, 59, C1) | 5.532 | 37,18 s |

## Cómo se midió

```bash
uv run python -m project.analysis.medir_rutas lineas    # columna pos_asignadas
uv run python -m project.analysis.medir_soporte         # viajes, días, grupo, intervalo
uv run dvc repro features                               # la tabla y metrics/features.json
```

El indicador sale de `data/interim/viajes`: suma de `posiciones` con
`motivo = 'asignado'` entre la suma con `motivo <> 'excluido'`. El intervalo
remuestrea viajes enteros 1.000 veces con semilla fija: las paradas de un viaje
están correlacionadas, y remuestrear filas lo estrecharía.

Las cifras por grupo están en `metrics/features.json`, en
`baselines_test.por_grupo`.

## Por qué importa

- **Acotar a corredores tiraba tres cuartas partes del dato.** Los cinco
  corredores propuestos en agosto (93, C3, 98, 99, 81) eran el 24,5 % de las
  filas, y la razón de acotar —que etiquetar todas las líneas no diera tiempo—
  ya no existe.
- **Lo poco que se etiqueta de una línea rota no es una muestra de ella.** De la
  25 llegan los viajes que sobrevivieron a la alternancia del sentido (trampa
  014), no una selección al azar.
- **La exclusión favorece a la hipótesis, y hay que decirlo.** La 25 es también
  la línea peor cubierta por sensores de tráfico (27 %). Se excluye por su
  etiqueta, no por eso, pero el efecto sobre la muestra es el mismo. En el
  baseline la diferencia es de 0,08 s.
- **Una cifra por línea con 16 viajes no distingue nada.** En la 98 el intervalo
  es de ±6,3 s sobre 44,5; un modelo que mejore 4 s a la persistencia no se
  vería.
- **Las ocho líneas sin entrenamiento son un resultado aparte:** miden cómo
  generaliza el modelo a líneas que no ha visto.

## Qué se hizo / qué queda abierto

Hecho: `features.excluir_lineas`, `features.soporte_por_linea`, los baselines
por grupo, los dos medidores, los mutantes 088-091 y el ADR-018.

Abierto:

- El estrato de sensores: falta medir la cobertura por tramo entre paradas.
- Repetir las dos tablas con la captura posterior al 18/09. La prueba son 5
  días: casi todas las líneas de «poco soporte» lo son por eso.
- La 24, al 46 %: si no mejora, el umbral del 50 % la sacaría.
- El error del modelo con y sin las líneas excluidas, cuando haya modelo.

## Para la memoria

> El conjunto de datos comprende todas las líneas para las que el procedimiento
> de etiquetado resulta fiable. Como indicador de fiabilidad se empleó la
> proporción de las posiciones de cada línea que quedan asociadas a un viaje
> programado. En 39 de las 47 líneas publicadas esa proporción se sitúa entre el
> 57 % y el 92 %, y en una más, la 24, en el 46 %. Cuatro líneas carecen de
> trazado u horario en el GTFS y no pueden etiquetarse. Las tres restantes —25,
> 63 y 73— quedan por debajo del 30 % y se excluyeron, lo que supone el 0,67 %
> de las observaciones. La exclusión atiende solo a la calidad de la etiqueta,
> pero debe señalarse que la línea 25 es también la peor cubierta por los
> sensores municipales de tráfico, de modo que su ausencia sesga la muestra
> hacia el viario mejor instrumentado. Para informar resultados por línea se
> exigió un mínimo de 100 viajes en tres días distintos del periodo de prueba y
> otros 100 en el de entrenamiento: por debajo de ese umbral, el intervalo de
> confianza del error alcanza hasta la cuarta parte de su valor. Cumplen el
> requisito 24 líneas; las 16 restantes se informan agrupadas, distinguiendo las
> que el modelo no ha visto durante el entrenamiento.
```

Antes de guardar, contrastar cada cifra con la salida de las tareas 3 y 4. Si alguna difiere, gana lo medido: corregir la entrada, no redondear.

- [ ] **Step 4: Fila en el índice de la bitácora**

En `docs/bitacora/README.md`, añadir tras la fila de la 035:

```markdown
| [036](036-la-muestra-son-todas-las-lineas-menos-tres.md) | 2026-09-30 | limitacion | metodologia | La muestra son todas las líneas menos tres: la 25, la 63 y la 73 tienen menos del **30 %** de sus posiciones en viajes asignados y salen (0,67 % de las filas); el resto, del 46 al 92 %. Cifra propia por línea con 100 viajes en 3 días: **24 líneas**; 8 con poco soporte y 8 sin entrenamiento se informan agrupadas |
```

- [ ] **Step 5: Puntero en `CLAUDE.md`**

En `CLAUDE.md`, sección «Pipeline ML», añadir tras el punto de los baselines obligatorios:

```markdown
- **La muestra son todas las líneas menos las de etiqueta insuficiente**
  (`features.excluir_lineas`: menos del 40 % de sus posiciones en viajes
  asignados). La cobertura de sensores de tráfico es un estrato de evaluación,
  nunca un recorte, y una línea se informa con cifra propia solo con soporte
  mínimo (`features.soporte_por_linea`). Nunca se excluye una línea por el error
  del modelo. ADR-018.
```

- [ ] **Step 6: Verificar y hacer commit**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -q && uv run pytest .claude/tests -q`
Expected: todo en verde. La suite de andamiaje comprueba el frontmatter de la 036, el índice sincronizado y que las rutas y funciones citadas existen.

```bash
git add docs/07_decisiones.md docs/bitacora/036-la-muestra-son-todas-las-lineas-menos-tres.md docs/bitacora/README.md CLAUDE.md
git commit -m "docs(decisiones): ADR-018, la muestra son todas las líneas menos tres; bitácora 036" -m "Cierra el pendiente de la selección de corredores: fuera la 25, la 63 y la 73 por calidad de la etiqueta, la cobertura de sensores como estrato y soporte mínimo por línea. Queda pendiente la cobertura por tramo. Puntero en CLAUDE.md." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Auditoría por mutación

**Files:**
- Create: `auditoria/resultados/mutantes_<hash corto de HEAD>.json` (lo escribe `mutar.py`)

**Interfaces:**
- Consumes: los mutantes 088-091 (tareas 1 y 2) y todos los commits anteriores. `mutar.py` exige `src/` y `tests/` limpios respecto a HEAD.
- Produces: la prueba de que los tests nuevos guardan.

- [ ] **Step 1: Árbol limpio**

Run: `git status --short`
Expected: sin salida.

- [ ] **Step 2: Lanzar los cuatro mutantes**

Run: `uv run python auditoria/mutar.py --solo 088 089 090 091`
Expected (unos 12 minutos): la referencia sin fallos, el mutante nulo `000` «equivalente», el positivo `002` «detectado», y:

```
  088 detectado
  089 detectado
  090 detectado
  091 detectado
```

Si alguno sale «no detectado», el test correspondiente no guarda: parar y avisar, no retocar el mutante para que pase.

- [ ] **Step 3: Commit**

```bash
git add auditoria/resultados/
git commit -m "test(auditoria): mutantes 088-091 de la selección de líneas detectados" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
