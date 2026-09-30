# Selección de líneas y soporte por línea — plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Informar los baselines por línea solo donde hay soporte, medir cuánto se distingue una mejora con ese soporte y dejar escritas en el ADR-018 y la bitácora 036 las cinco decisiones que cierran la selección de corredores.

**Architecture:** El único cambio de código del pipeline es una función nueva en `src/project/features.py`, `soporte_por_linea`, que `baselines` usa para clasificar cada línea de la prueba. La tabla de entrenamiento no cambia. Dos medidores en `src/project/analysis/` reproducen las cifras. Solo se reejecuta el stage `features`.

**Tech Stack:** Python 3.10+, pandas, numpy, DuckDB (solo en un medidor), pytest, DVC, `uv`.

**Spec:** `docs/superpowers/specs/2026-09-30-seleccion-de-lineas-design.md`

Revisado el 30/09/2026 tras `/grill-me`: **no se excluye ninguna línea**. La versión anterior de este plan sacaba la 25, la 63 y la 73; el porqué del descarte está en el diseño.

Este plan vive en `.claude/plans/` y no en `docs/`: `.claude/tests/test_memoria.py` exige que toda ruta citada bajo `docs/` exista ya, y un plan cita ficheros que todavía no existen.

## Global Constraints

- Entorno Windows. Todo se lanza con `uv run …`; nunca `pip install`.
- **La tabla de entrenamiento no cambia**: 1.236.585 filas de entrenamiento y 269.493 de prueba, antes y después.
- Soporte: **100 viajes en 3 días de servicio distintos** en la prueba y **100 viajes** en entrenamiento. Un viaje es un par (`fecha_servicio`, `viaje_id`).
- Nunca se excluye una línea por el error del modelo ni por su cobertura de sensores.
- `dvc.lock` no se edita a mano: lo actualiza `uv run dvc repro features`.
- Guardia nueva ⇒ mutante en `auditoria/catalogo.toml` que la ponga roja (ADR-011).
- Antes de cada commit: `uv run ruff format . && uv run ruff check .`, `uv run pytest` y `uv run pytest .claude/tests`, los tres en verde.
- Mensajes de commit en español, con prefijo convencional, y terminados en la línea `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No se hace `git push`.
- Las cifras son las de las 32 jornadas hasta el 18/09. Si DVC quiere reejecutar `curar` o `prepare`, alguien ha traído captura nueva: parar y avisar.

## Review Focus

1. **El mismo `viaje_id` en días distintos.** El tracker numera desde `v00000` cada día (bitácora 027). Contar por `viaje_id` solo daría menos viajes de los reales. Test en la tarea 1.
2. **Una línea que está en entrenamiento y no en la prueba.** No debe aparecer en el soporte ni romper nada. Test en la tarea 1.
3. **La prueba vacía** (un `test_desde` posterior al último día). `soporte_por_linea` debe devolver una tabla vacía con sus columnas, no lanzar. Test en la tarea 1.
4. **Una línea en entrenamiento por debajo del umbral.** Con 99 viajes de entrenamiento no es «sin entrenamiento»: es «poco soporte». Test en la tarea 1.
5. **Valores no serializables.** Los grupos salen de `np.where` y van a un JSON. Test en la tarea 1.

---

### Task 1: Soporte por línea y baselines por grupo

**Files:**
- Modify: `src/project/features.py` (`soporte_por_linea` nueva, `baselines`, `main`)
- Modify: `params.yaml` (bloque `features`)
- Modify: `auditoria/catalogo.toml` (mutantes 088 y 089, al final)
- Test: `tests/test_features.py`

**Interfaces:**
- Consumes: `features.CLAVE_VIAJE == ["fecha_servicio", "viaje_id"]`, ya existente.
- Produces:
  - `features.soporte_por_linea(train, test, min_viajes=100, min_dias=3) -> pd.DataFrame`, con índice `linea` (las líneas de `test`) y columnas `viajes`, `dias`, `viajes_train`, `grupo`. `grupo` vale `"propia"`, `"poco_soporte"` o `"sin_entrenamiento"`.
  - `features.baselines(test, objetivo, soporte) -> dict`, con las claves `horario`, `persistencia`, `por_linea` y `por_grupo`. Cada entrada de `por_linea` trae `filas`, `horario`, `persistencia`, `viajes`, `dias` y `grupo`.
  - Claves nuevas `features.linea_min_viajes` y `features.linea_min_dias` en `params.yaml`.

- [ ] **Step 1: Escribir los tests que fallan**

En `tests/test_features.py`, añadir `import json` al principio de los imports (antes de `import numpy as np`) y, al final del fichero:

```python
# --------------------------------------------------------------------------- #
# Soporte por línea (ADR-018)
# --------------------------------------------------------------------------- #
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
Expected: 12 passed.

- [ ] **Step 5: Conectar `params.yaml` y `main`**

En `params.yaml`, dentro de `features:`, justo después de la línea `umbral_retraso_s: 300 …`:

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

Al final de `auditoria/catalogo.toml` (el fichero usa finales de línea CRLF; conservarlos):

```toml

[[mutante]]
id = "088"
nombre = "el soporte de una línea no exige días distintos"
capa = "features"
# Cien viajes de un solo día pasan por una línea bien observada.
fichero = "src/project/features.py"
buscar = '''        & (s["dias"] >= min_dias)'''
reemplazar = '''        & (s["dias"] >= 1)'''
detector = ["tests/test_features.py::test_el_soporte_de_una_linea_se_cuenta_en_viajes_y_dias"]
sondas = []

[[mutante]]
id = "089"
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
uv run python -c "import tomllib, pathlib; c = tomllib.load(open('auditoria/catalogo.toml', 'rb'))['mutante']; s = pathlib.Path('src/project/features.py').read_text(encoding='utf-8'); print([(m['id'], s.count(m['buscar'])) for m in c if m['id'] in ('088', '089')])"
```
Expected: `[('088', 1), ('089', 1)]`

- [ ] **Step 7: Verificar y hacer commit**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -q && uv run pytest .claude/tests -q`
Expected: `All checks passed!`, `189 passed, 5 xfailed` y la suite de andamiaje sin fallos.

```bash
git add src/project/features.py params.yaml tests/test_features.py auditoria/catalogo.toml
git commit -m "feat(features): soporte por línea y baselines por grupo" -m "soporte_por_linea clasifica cada línea de la prueba: cifra propia con 100 viajes en 3 días y 100 de entrenamiento; si no, poco_soporte o sin_entrenamiento. Se cuenta en viajes, no en filas. baselines trae viajes, días y grupo por línea, y los baselines de cada grupo. Mutantes 088 y 089. ADR-018." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Reejecutar el stage `features`

**Files:**
- Modify: `metrics/features.json`, `dvc.lock` (los escribe `dvc repro`)

**Interfaces:**
- Consumes: las claves de `params.yaml` y las funciones de la tarea 1.
- Produces: `metrics/features.json` con `baselines_test.por_grupo`. Las tareas 3 y 4 leen de aquí.

- [ ] **Step 1: Anotar lo que hay antes**

Run: `uv run python -c "import json; m = json.load(open('metrics/features.json', encoding='utf-8')); b = m['baselines_test']; print(m['filas'], m['positivos'], b['horario'], b['persistencia'])"`
Expected: `{'train': 1236585, 'test': 269493} {'train': 0.057, 'test': 0.0585} {'mae_s': 139.92, 'rmse_s': 195.76} {'mae_s': 37.62, 'rmse_s': 72.58}`

- [ ] **Step 2: Reejecutar**

Run: `uv run dvc repro features`
Expected: solo se ejecuta `features` (`curar` y `prepare` dicen «didn't change, skipping»). Tarda unos minutos.

- [ ] **Step 3: Comprobar que la tabla no ha cambiado y que aparecen los grupos**

Run:
```bash
uv run python -c "import json, collections; m = json.load(open('metrics/features.json', encoding='utf-8')); b = m['baselines_test']; print(m['filas'], m['positivos'], b['horario'], b['persistencia']); print(len(b['por_linea']), {k: v['filas'] for k, v in b['por_grupo'].items()}); print(collections.Counter(v['grupo'] for v in b['por_linea'].values()))"
```
Expected: la primera línea, idéntica a la del paso 1. Después:
```
43 {'poco_soporte': 9564, 'propia': 252306, 'sin_entrenamiento': 7623}
Counter({'propia': 24, 'sin_entrenamiento': 10, 'poco_soporte': 9})
```

Si la primera línea cambia, el cambio ha tocado la muestra y no debía: parar y avisar.

- [ ] **Step 4: Comprobar el estado de DVC**

Run: `uv run dvc status`
Expected: solo `train` y `evaluate` aparecen como cambiados (siguen vacíos; es lo esperado).

- [ ] **Step 5: Commit**

```bash
git add metrics/features.json dvc.lock
git commit -m "chore(dvc): features con el soporte por línea en las métricas" -m "dvc repro features. La tabla no cambia: 1.236.585 filas de entrenamiento y 269.493 de prueba, persistencia en 37,62 s. metrics/features.json gana viajes, días y grupo por línea y los baselines por grupo: 24 líneas con cifra propia, 9 con poco soporte y 10 sin entrenamiento." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Medidores

**Files:**
- Modify: `src/project/analysis/medir_rutas.py` (función `lineas`)
- Create: `src/project/analysis/medir_soporte.py`

**Interfaces:**
- Consumes: `features.soporte_por_linea` y `features.CLAVE_VIAJE` (tarea 1); `data/processed/`.
- Produces: dos comandos que cita la bitácora 036 (tarea 4): `uv run python -m project.analysis.medir_rutas lineas` y `uv run python -m project.analysis.medir_soporte`.

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

En el docstring del módulo, la descripción de `LINEAS` gana una frase al final:

```
                 `pos_asignadas` es la fracción de las posiciones de la línea,
                 en días no excluidos, que cae en un viaje asignado (bitácora
                 036).
```

- [ ] **Step 2: Comprobar el indicador**

Run: `uv run python -m project.analysis.medir_rutas lineas`
Expected: la tabla trae la columna `pos_asignadas`, con 0.143 en la 73, 0.177 en la 25, 0.290 en la 63, 0.464 en la 24 y 0.781 en la 93.

- [ ] **Step 3: Crear `medir_soporte.py`**

Crear `src/project/analysis/medir_soporte.py`:

```python
"""¿Qué mejora se distingue en una línea, según los viajes que tiene en la prueba?

    uv run python -m project.analysis.medir_soporte

Por línea de la prueba: viajes, días, grupo de soporte, el MAE de la persistencia
y tres semianchos de intervalo del 95 %, remuestreando VIAJES enteros (las
paradas de un viaje están correlacionadas: remuestrear filas daría un intervalo
demasiado estrecho):

  semi_ic_mae_s        del MAE de la persistencia.
  semi_ic_dif_cerca_s  de la diferencia de error, sobre los mismos viajes, entre
                       la persistencia y un predictor parecido: ella misma
                       encogida un 10 %.
  semi_ic_dif_lejos_s  lo mismo con uno muy distinto: la media de la persistencia
                       y el retraso medio de la línea en los 5 min anteriores.

Los dos predictores son sustitutos del modelo, que aún no existe: acotan cuánto
tendría que mejorar para que se viera en una línea. Es la tabla que fija
`features.linea_min_viajes` y el criterio de mejora (ADR-018, bitácora 036). Lee
`data/processed/`; nada del pipeline importa de aquí.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from project.config import RAIZ, settings
from project.features import CLAVE_VIAJE, soporte_por_linea

REMUESTRAS = 1000
MEDIDAS = ["mae", "dif_cerca", "dif_lejos"]


def medir() -> pd.DataFrame:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    obj = cfg["objetivo"]
    claves = ["linea", *CLAVE_VIAJE]
    train = pd.read_parquet(settings.processed_dir / "train.parquet", columns=claves)
    test = pd.read_parquet(
        settings.processed_dir / "test.parquet",
        columns=[*claves, "retraso_s", obj, "linea_retraso_5min"],
    )
    s = soporte_por_linea(train, test, cfg["linea_min_viajes"], cfg["linea_min_dias"])
    r, y = test["retraso_s"], test[obj]
    mezcla = 0.5 * r + 0.5 * test["linea_retraso_5min"].fillna(r)
    test = test.assign(
        mae=(r - y).abs(),
        dif_cerca=(0.9 * r - y).abs() - (r - y).abs(),
        dif_lejos=(mezcla - y).abs() - (r - y).abs(),
    )
    rng = np.random.default_rng(0)
    for linea, g in test.groupby("linea"):
        por_viaje = g.groupby(CLAVE_VIAJE)
        v = por_viaje[MEDIDAS].sum().to_numpy()
        n = por_viaje.size().to_numpy()
        i = rng.integers(0, len(v), size=(REMUESTRAS, len(v)))
        filas = n[i].sum(axis=1)
        s.at[linea, "mae_s"] = g["mae"].mean()
        for k, medida in enumerate(MEDIDAS):
            lo, hi = np.percentile(v[i, k].sum(axis=1) / filas, [2.5, 97.5])
            s.at[linea, f"semi_ic_{medida}_s"] = (hi - lo) / 2
    return s.sort_values("viajes")


if __name__ == "__main__":
    s = medir()
    print(s.round(2).to_string())
    banda = pd.cut(
        s["viajes"], [0, 99, 299, np.inf], labels=["<100", "100-299", ">=300"]
    )
    cols = [f"semi_ic_{m}_s" for m in MEDIDAS]
    print("\n  mediana del semiancho del IC 95 %, en segundos, por viajes en la prueba:")
    print(
        s.groupby(banda, observed=True)[cols]
        .median()
        .round(2)
        .assign(lineas=banda.value_counts())
        .to_string()
    )
```

- [ ] **Step 4: Comprobar el medidor**

Run: `uv run python -m project.analysis.medir_soporte`
Expected: 43 líneas ordenadas por `viajes`, y al final:

```
         semi_ic_mae_s  semi_ic_dif_cerca_s  semi_ic_dif_lejos_s  lineas
viajes
<100              3.21                 2.70                 6.91      17
100-299           1.57                 0.86                 9.67       7
>=300             1.02                 0.58                 3.67      19
```

Filas de control: la 98 (16 viajes) con `mae_s` 44.52 y `semi_ic_mae_s` 6.19; la 24 (172) con 26.61 y 1.77; la 93 (714) con 38.66 y 1.02.

Si no coinciden, parar y avisar: la bitácora 036 cita estas cifras.

- [ ] **Step 5: Verificar y hacer commit**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -q && uv run pytest .claude/tests -q`
Expected: todo en verde; `189 passed, 5 xfailed`.

```bash
git add src/project/analysis/medir_rutas.py src/project/analysis/medir_soporte.py
git commit -m "feat(analysis): el indicador de reconstrucción por línea y lo que se distingue con cada soporte" -m "medir_rutas lineas trae pos_asignadas. medir_soporte da, por línea de la prueba, viajes, días, grupo y el semiancho del IC 95 % del MAE de la persistencia y de la diferencia con dos predictores sustitutos, remuestreando viajes." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: ADR-018, bitácora 036 y punteros

**Files:**
- Modify: `docs/07_decisiones.md` (ADR-018 nuevo; sección «Pendientes de decidir»)
- Create: `docs/bitacora/036-todas-las-lineas-entran-y-el-soporte-decide-cuales-se-informan.md`
- Modify: `docs/bitacora/README.md` (fila 036 en el índice)
- Modify: `CLAUDE.md` (sección «Pipeline ML»)

**Interfaces:**
- Consumes: las cifras de las tareas 2 y 3.
- Produces: la fuente de verdad de la decisión, que leen todas las sesiones.

- [ ] **Step 1: ADR-018**

En `docs/07_decisiones.md`, insertar antes de `## Pendientes de decidir` (tras el separador `---` que cierra el ADR-017):

```markdown
## ADR-018 · Todas las líneas entran en la muestra; la cobertura de sensores es un estrato y una mejora es una diferencia con intervalo · revisable

**Decisión.** Cinco, que sustituyen a la propuesta de acotar a 4-6 corredores:

1. Se entrena y se evalúa con **todas las líneas etiquetadas**. No se excluye
   ninguna.
2. La cobertura de sensores de tráfico define un **estrato de evaluación**, no
   recorta la muestra.
3. Una línea se informa con cifra propia con al menos **100 viajes en 3 días de
   servicio** en la prueba y 100 viajes en entrenamiento
   (`features.soporte_por_linea`). Las demás cuentan en la métrica global y se
   informan agrupadas en `poco_soporte` y `sin_entrenamiento`.
4. **Qué es una mejora.** Toda comparación —modelo contra persistencia, modelo
   con tráfico contra modelo sin él— se informa como diferencia sobre los mismos
   viajes, con su intervalo del 95 % remuestreando viajes. Hay mejora si el
   intervalo no contiene el cero; si lo contiene, el resultado es «no se
   distingue». No hay mínimo de magnitud: se informa el tamaño del efecto.
5. Lo que aporta el tráfico se juzga **en el conjunto y en el estrato con
   sensor**, no línea a línea.

**Nunca** se excluye una línea por el error del modelo ni por su cobertura de
sensores.

**Por qué.** Los dos motivos para acotar eran el coste de etiquetar las 47
líneas y la cobertura de sensores. El primero desapareció: el pipeline etiqueta
todas, y los cinco corredores propuestos eran el 24,5 % de las filas. Recortar
por cobertura deja fuera justo las líneas periféricas y sesga la muestra a favor
de la hipótesis (bitácora 026). El criterio de mejora no estaba escrito en
ningún sitio: «por un margen claro» no es un criterio.

**Consecuencias.** Con la prueba actual, de 5 días, 24 líneas tienen cifra
propia, 9 poco soporte y 10 no tienen entrenamiento. Por línea, con 100 a 300
viajes, solo se distinguen mejoras de 1 a 2 s o más; de ahí la decisión 5. La
evaluación del modelo tendrá que calcular el intervalo de la diferencia
remuestreando viajes, no filas.

**Alternativas.** Acotar a corredores: descartada, por lo anterior. Excluir las
líneas con menos del 40 % de sus posiciones en viajes asignados (25, 63 y 73):
descartada, porque la regla de soporte ya las aparta de las cifras por línea,
excluirlas movía el resultado global 0,08 s, lo que sí se etiqueta de ellas no es
peor que en el resto, y obligaba a defender un umbral elegido después de ver los
datos y un sesgo a favor de la hipótesis. Un mínimo de mejora en segundos:
descartado por arbitrario.

**Qué la reabriría.** Que el modelo, con y sin las líneas de indicador bajo, dé
resultados distintos más allá de su intervalo. Que el estrato de sensores, una
vez medido, solo aporte ruido. Que con la captura completa casi ninguna línea
quede por debajo del soporte. Que el tutor pida un mínimo de magnitud.

Reproducir: `uv run python -m project.analysis.medir_rutas lineas` y
`uv run python -m project.analysis.medir_soporte`. Detalle en la bitácora 036.

---
```

- [ ] **Step 2: «Pendientes de decidir»**

En la misma sección de `docs/07_decisiones.md`, sustituir el punto entero que empieza por `- **Selección de corredores.**` por:

```markdown
- **Cobertura de sensores por tramo.** El estrato de evaluación del ADR-018
  necesita saber qué tramos entre paradas tienen un sensor de la capa 192
  encima. Hoy la cobertura solo está medida por posición (69,4 % a menos de
  50 m, `docs/10`). Se mide al meter la capa 192 en `features.py`.
- **Cómo se codifica la línea.** Diez líneas de la prueba no tienen ni un viaje
  de entrenamiento. Que el modelo pueda predecirlas depende de cómo entre
  `linea` como variable. Se decide al escribir `train.py`.
```

- [ ] **Step 3: Bitácora 036**

Crear `docs/bitacora/036-todas-las-lineas-entran-y-el-soporte-decide-cuales-se-informan.md`:

```markdown
---
id: 036
titulo: Todas las líneas etiquetadas entran en la muestra; con 5 días de prueba, 24 tienen soporte para una cifra propia y, con 100-300 viajes, solo se distingue una mejora de 1 a 2 s
fecha: 2026-09-30
tipo: medicion
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
| 73 | 15.396 | 14,3 % |
| 25 | 206.710 | 17,7 % |
| 63 | 35.823 | 29,0 % |
| 24 | 140.297 | 46,4 % |
| 14 | 839 | 57,1 % |
| las otras 38 | | 70,0 - 92,4 % |

**Excluir las tres de menos del 30 % no cambia casi nada.** Son 10.023 filas, el
0,67 % de la tabla. Sin ellas, la persistencia pasa de 37,62 a 37,54 s de MAE en
la prueba. Y lo que sí se etiqueta de ellas no es más dudoso: el margen del
viaje asignado sobre el segundo candidato, en su percentil 10, es de 449 s en la
25 y 534 s en la 63, frente a 372 s de mediana en las demás.

**Qué se distingue con cada soporte.** Mediana, entre líneas, del semiancho del
intervalo del 95 %, remuestreando viajes:

| viajes de la línea en la prueba | líneas | del MAE de la persistencia | de la diferencia con un predictor parecido | con uno muy distinto |
|---|---|---|---|---|
| menos de 100 | 17 | 3,21 s | 2,70 s | 6,91 s |
| de 100 a 299 | 7 | 1,57 s | 0,86 s | 9,67 s |
| 300 o más | 19 | 1,02 s | 0,58 s | 3,67 s |

El predictor «parecido» es la persistencia encogida un 10 %; el «muy distinto»,
la media de la persistencia y el retraso medio de la línea en los 5 min
anteriores. Son sustitutos de un modelo que aún no existe.

**Los grupos**, con 100 viajes en 3 días de prueba y 100 de entrenamiento:

| grupo | líneas | filas de prueba | MAE de la persistencia |
|---|---|---|---|
| cifra propia | 24 | 252.306 | 37,56 s |
| poco soporte | 9 (25, 28, 4, 40, 6, 62, 70, 71, 98) | 9.564 | 36,69 s |
| sin entrenamiento | 10 (10, 11, 14, 59, 60, 63, 64, 73, 9, C1) | 7.623 | 40,96 s |

## Cómo se midió

```bash
uv run python -m project.analysis.medir_rutas lineas    # columna pos_asignadas
uv run python -m project.analysis.medir_soporte         # soporte e intervalos por línea
uv run dvc repro features                               # metrics/features.json
```

El indicador sale de `data/interim/viajes`: suma de `posiciones` con
`motivo = 'asignado'` entre la suma con `motivo <> 'excluido'`. Los intervalos
remuestrean viajes enteros 1.000 veces con semilla fija. Los grupos están en
`metrics/features.json`, en `baselines_test.por_grupo`.

El efecto de excluir y los márgenes de asignación se midieron una vez, sin
medidor propio:

```python
import duckdb, pandas as pd
from project.config import settings
te = pd.read_parquet(settings.processed_dir / "test.parquet")
sin = te[~te["linea"].isin(["25", "63", "73"])]
(sin["retraso_s"] - sin["retraso_siguiente_parada_s"]).abs().mean()   # 37,54
v = (settings.interim_dir / "viajes" / "*" / "*.parquet").as_posix()
duckdb.sql(f"""select linea, quantile_cont(margen_s, 0.1) from
    read_parquet('{v}', hive_partitioning=false, union_by_name=true)
    where motivo = 'asignado' group by 1""")
```

**El instrumento se corrigió antes de la cifra.** La primera justificación del
umbral de 100 viajes usaba solo el intervalo del MAE, y daba por hecho que el de
una diferencia sobre los mismos viajes sería siempre menor. Medido, solo lo es
si el predictor se parece a la persistencia: con uno muy distinto es varias
veces mayor.

## Por qué importa

- **Acotar a corredores tiraba tres cuartas partes del dato.** Los cinco
  propuestos en agosto (93, C3, 98, 99, 81) eran el 24,5 % de las filas.
- **Excluir líneas por su etiqueta costaba más de lo que daba.** Movía el
  resultado 0,08 s y obligaba a defender un umbral puesto después de ver los
  datos y un sesgo a favor de la hipótesis: la 25 es también la línea peor
  cubierta por sensores (27 %). La regla de soporte ya deja esas líneas fuera de
  las cifras por línea.
- **Una cifra por línea con pocos viajes no distingue nada.** En la 98, con 16
  viajes, el intervalo del MAE es de ±6,2 s sobre 44,5.
- **El tráfico no se verá línea a línea.** Con 100 a 300 viajes solo se
  distinguen mejoras de 1 a 2 s, y lo que la flota detecta por encima del sesgo
  del horario es pequeño (bitácora 032). Hay que juzgarlo en el conjunto y en el
  estrato con sensor.
- **Las diez líneas sin entrenamiento son un resultado aparte:** miden cómo
  generaliza el modelo a líneas que no ha visto.

## Qué se hizo / qué queda abierto

Hecho: `features.soporte_por_linea`, los baselines por grupo, los dos medidores,
los mutantes 088 y 089 y el ADR-018, con el criterio de mejora.

Abierto:

- El estrato de sensores: falta medir la cobertura por tramo entre paradas.
- Repetirlo todo con la captura posterior al 18/09 y el corte rehecho. Con 5
  días de prueba, casi todas las líneas de «poco soporte» lo son por eso.
- Cómo se codifica `linea` para que el modelo prediga líneas no vistas.
- El intervalo de la diferencia con el modelo de verdad, cuando exista.

## Para la memoria

> El conjunto de datos comprende todas las líneas para las que existe trazado y
> horario publicados. La proporción de posiciones que el procedimiento logra
> asociar a un viaje programado se sitúa entre el 57 % y el 92 % en 39 de ellas y
> en el 46 % en una más; tres líneas quedan por debajo del 30 %. Se valoró
> excluir estas últimas y se descartó: representan el 0,67 % de las
> observaciones, su exclusión modifica el error de referencia en 0,08 segundos y
> las asignaciones que sí se obtienen en ellas no son más ambiguas que en el
> resto. La proporción se informa por línea como limitación. Para presentar
> resultados desagregados se exige un mínimo de 100 viajes en tres días distintos
> del periodo de prueba y otros 100 en el de entrenamiento, requisito que cumplen
> 24 de las 43 líneas; las restantes se informan agrupadas, distinguiendo las que
> el modelo no ha visto durante el entrenamiento. Toda comparación entre modelos
> se expresa como diferencia de error sobre los mismos viajes, con un intervalo
> de confianza del 95 % obtenido remuestreando viajes completos, y se considera
> que existe mejora cuando el intervalo no contiene el cero. Con el soporte
> disponible, una diferencia inferior a uno o dos segundos no es distinguible
> línea a línea, por lo que la contribución de las variables de tráfico se evalúa
> sobre el conjunto y sobre el subconjunto de tramos con sensor.
```

Antes de guardar, contrastar cada cifra con la salida de las tareas 2 y 3. Si alguna difiere, gana lo medido: corregir la entrada, no redondear.

- [ ] **Step 4: Fila en el índice de la bitácora**

En `docs/bitacora/README.md`, añadir tras la fila de la 035:

```markdown
| [036](036-todas-las-lineas-entran-y-el-soporte-decide-cuales-se-informan.md) | 2026-09-30 | medicion | metodologia | Todas las líneas etiquetadas entran en la muestra: excluir la 25, la 63 y la 73 (menos del 30 % de sus posiciones en viajes asignados) movía la persistencia **0,08 s**. Con 5 días de prueba, **24 líneas** tienen soporte para una cifra propia, y con 100-300 viajes solo se distingue una mejora de **1 a 2 s**: el tráfico se juzga en el conjunto, no por línea |
```

- [ ] **Step 5: Puntero en `CLAUDE.md`**

En `CLAUDE.md`, sección «Pipeline ML», añadir tras el punto de los baselines obligatorios:

```markdown
- **La muestra son todas las líneas etiquetadas.** La cobertura de sensores de
  tráfico es un estrato de evaluación, nunca un recorte, y no se excluye una
  línea por el error del modelo. Una línea se informa con cifra propia solo con
  soporte mínimo (`features.soporte_por_linea`). **Una mejora es una diferencia
  sobre los mismos viajes cuyo intervalo del 95 %, remuestreando viajes, no
  contiene el cero.** ADR-018.
```

- [ ] **Step 6: Verificar y hacer commit**

Run: `uv run ruff format . && uv run ruff check . && uv run pytest -q && uv run pytest .claude/tests -q`
Expected: todo en verde.

```bash
git add docs/07_decisiones.md docs/bitacora/036-todas-las-lineas-entran-y-el-soporte-decide-cuales-se-informan.md docs/bitacora/README.md CLAUDE.md
git commit -m "docs(decisiones): ADR-018, todas las líneas entran y una mejora es una diferencia con intervalo; bitácora 036" -m "Cierra el pendiente de la selección de corredores con cinco decisiones: muestra completa, cobertura de sensores como estrato, soporte mínimo por línea, criterio de mejora y dónde se juzga el tráfico. La exclusión por etiqueta queda descartada con sus cifras. Puntero en CLAUDE.md." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Auditoría por mutación

**Files:**
- Create: `auditoria/resultados/mutantes_<hash corto de HEAD>.json` (lo escribe `mutar.py`)

**Interfaces:**
- Consumes: los mutantes 088 y 089 (tarea 1) y todos los commits anteriores. `mutar.py` exige `src/` y `tests/` limpios respecto a HEAD.
- Produces: la prueba de que el test nuevo guarda.

- [ ] **Step 1: Árbol limpio**

Run: `git status --short`
Expected: sin salida.

- [ ] **Step 2: Lanzar los dos mutantes**

Run: `uv run python auditoria/mutar.py --solo 088 089`
Expected (unos 8 minutos): la referencia sin fallos, el mutante nulo `000` «equivalente», el positivo `002` «detectado», y `088 detectado` y `089 detectado`.

Si alguno sale «no detectado», el test no guarda: parar y avisar, no retocar el mutante para que pase.

- [ ] **Step 3: Commit**

```bash
git add auditoria/resultados/
git commit -m "test(auditoria): mutantes 088 y 089 del soporte por línea detectados" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
