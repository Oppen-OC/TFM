# Servicio de predicción por API — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** servir la regresión v2 y el clasificador del ADR-025, de todos los horizontes, desde FastAPI, con `services/` como única capa que carga modelos y con «Try it out» de Swagger funcionando sin teclear nada.

**Architecture:** `services/model_service.Servicio` carga los artefactos al arrancar (`lifespan`), valida el vector de 25 variables contra las columnas del artefacto, lo convierte a los tipos del entrenamiento y llama a `predict.predecir` o `predict.probabilidad`. api/routers/prediccion.py valida el JSON con Pydantic, delega y traduce las excepciones del servicio a 422 y 503. `api/schemas.py` lleva un ejemplo real de entrenamiento para Swagger.

**Tech Stack:** Python 3.11, FastAPI 0.139, Pydantic 2.13, pandas, XGBoost 3.2, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-10-15-servicio-api-design.md`, aprobada el 15/10.

**Validado:** el código de este plan se probó el 15/10 en un worktree desechable:
- 20 tests en verde;
- los 5 mutantes, detectados;
- ruff limpio;
- `uvicorn` contra el `models/model.pkl` real: h = 1 da 200, h = 4 da 422 y el clasificador da 503;
- «Try it out» → «Execute» en `/docs` da 200 con el ejemplo.

## Global Constraints

- **Prohibido `dvc repro`, `project.train` y `project.evaluate`.** La prueba del 07-19/10 no se toca hasta el 21/10. Este plan no ejecuta stages ni entrena nada fuera de los tests.
- `api/` no importa pandas, numpy, sklearn ni xgboost (`.claude/commands/check-fronteras.md`, comprobación 2). `services/` no importa nada de `api/`. `ui/` no se toca.
- `services/` es la única capa que carga modelos, una vez al arrancar y no por petición. Lo hace con `predict.cargar` y las rutas de `features.salidas`.
- Se sirven la regresión (`features.salidas(h)["modelo"]`) y el clasificador (`["clasificador"]`). **No** se sirven los modelos con la capa 192 (`["modelo_trafico"]`).
- Horizontes: `features.horizonte_paradas` (1, por defecto) y `features.horizontes_barrido` (2, 3, 5, 10), leídos de `params.yaml`.
- `llega_tarde` es `probabilidad >= umbral` (ADR-025). La tasa base de la validación va siempre al lado (ADR-006).
- El ejemplo de Swagger es una fila de **entrenamiento** (línea 92, 18/09/2026), nunca de la prueba.
- Errores: una variable que falta o sobra, un tipo mal, o `retraso_s` nulo, da 422; un horizonte fuera de la lista, 422; un modelo no cargado, 503.
- Ningún `os.getenv`. Siempre `uv`, nunca `pip`. No leer `.env`.
- Commits en `develop`, sin push, terminados en `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Subagentes en Sonnet, con el agente `serving` en las tareas 1-3. La tarea 4 va en línea.
- `uv run pytest` en verde, salvo el `xfail` estricto conocido de `tests/test_tracking_realismo.py` y el warning de `TestClient` que ya existía.

## Review Focus

1. **Enteros donde el entrenamiento vio decimales.** El ejemplo de Swagger manda `"stop_sequence": 31`. Debe predecir lo mismo que con `31.0`. Lo guarda `test_enteros_y_decimales_dan_lo_mismo` (tarea 1).
2. **`linea` como número** (`92` en vez de `"92"`). Debe dar 422, no una línea desconocida que se predice en silencio como dato faltante. Lo guarda `test_el_vector_trae_exactamente_las_variables` (tarea 1).
3. **Un clon sin `dvc pull`.** La API arranca, `/modelos` devuelve `[]` y cada predicción da 503. Lo guarda `test_sin_ningun_modelo_la_api_arranca` (tarea 1).
4. **`?horizonte=cinco`.** Debe dar 422 sin llegar al servicio. Lo guarda `test_un_cuerpo_mal_formado_no_llega_al_servicio` (tarea 2).
5. **Un vector con nulos** (`bus_anterior_retraso_s`: null). Debe predecir, no un 500 de XGBoost por columnas `object`. Lo guardan `test_un_vector_con_nulos_y_una_linea_no_vista_predice` (tarea 1) y el mutante 177. **Salvo `retraso_s` nulo**: el modelo de residuo daría NaN, y FastAPI lo serializa como `null` con un 200, comprobado el 15/10. Debe dar 422. Lo guardan `test_sin_retraso_actual_no_hay_prediccion` (tarea 1) y el mutante 179.

---

## Task 1: `services/model_service.py` y los esquemas (agente `serving`)

**Files:**
- Modify: `src/project/services/model_service.py` (está vacío)
- Modify: `src/project/api/schemas.py` (se sustituye entero)
- Create: tests/test_servicio.py

**Interfaces:**
- Consumes: `predict.cargar(ruta) -> dict`, `predict.predecir(art, tabla) -> pd.Series`, `predict.probabilidad(art, tabla) -> pd.Series`, `features.salidas(h) -> dict[str, Path]` (claves `"modelo"` y `"clasificador"`), `train.entrenar` y `train.entrenar_clasificador` (en los tests). Todo existe ya.
- Produces:
  - `model_service.REGRESION = "regresion"` y `model_service.CLASIFICADOR = "clasificador"`;
  - las excepciones `VariablesInvalidas(ValueError)`, `HorizonteInvalido(ValueError)` y `ModeloNoDisponible(LookupError)`. Las dos primeras llevan un `dict` en `args[0]`;
  - `horizontes() -> list[int]`;
  - `fila(columnas: list[str], variables: dict) -> pd.DataFrame`;
  - `Servicio(modelos: dict[tuple[str, int], dict], horizontes: list[int])`, con `Servicio.desde_disco()`, `.modelos() -> list[dict]`, `.retraso(variables, horizonte=None) -> dict` y `.mas_de_5min(variables, horizonte=None) -> dict`;
  - `schemas.EJEMPLO`, y los modelos `Vector`, `Retraso`, `MasDe5Min`, `Modelo` y `HealthResponse`.

- [ ] **Step 1: tests que fallan.** Crear tests/test_servicio.py:

```python
"""El servicio de predicción: lo que no da la cara si se rompe.

Un vector con una variable de más o de menos predeciría igual, con el hueco
como dato faltante. Una fila construida desde JSON con un nulo la rechaza
XGBoost. Y un modelo que falta no puede tumbar al otro. Se prueba con modelos
sintéticos diminutos, entrenados aquí, con las variables de `params.yaml`.
"""

from __future__ import annotations

import pickle

import numpy as np
import pandas as pd
import pytest
import yaml

from project import predict, train
from project.api.schemas import EJEMPLO
from project.config import RAIZ
from project.services import model_service
from project.services.model_service import (
    HorizonteInvalido,
    ModeloNoDisponible,
    Servicio,
    VariablesInvalidas,
)

OBJ = "retraso_siguiente_parada_s"
CFG = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
COLS = train.columnas_clasificador(CFG)
PARAMS = {
    "objective": "reg:absoluteerror",
    "eval_metric": "mae",
    "n_estimators": 30,
    "max_depth": 3,
    "learning_rate": 0.3,
    "early_stopping_rounds": 5,
    "n_jobs": 1,
    "random_state": 0,
    "dias_validacion": 1,
    "residuo": True,
}


def _tabla(dias=4, filas_por_dia=200):
    rng = np.random.default_rng(0)
    n = dias * filas_por_dia
    t = pd.DataFrame({c: rng.normal(size=n) * 100 for c in COLS if c != "linea"})
    t["linea"] = rng.choice(["92", "19", "35"], n)
    t["fecha_servicio"] = pd.Timestamp("2026-09-01") + pd.to_timedelta(
        np.repeat(np.arange(dias), filas_por_dia), unit="D"
    )
    t["viaje_id"] = np.arange(n) // 10
    t[OBJ] = t["retraso_s"] + 50 * (t["linea"] == "92")
    t[f"{OBJ}_bin"] = (t["retraso_s"] > 0).astype(int)
    return t


@pytest.fixture(scope="module")
def arts():
    t = _tabla()
    reg = train.entrenar(t, COLS, OBJ, PARAMS)
    clf = train.entrenar_clasificador(t, COLS, OBJ, 300, PARAMS)
    return t, {**reg, "mlflow_run_id": "r"}, {**clf, "mlflow_run_id": "c"}


def _vector(t: pd.DataFrame, i: int = 0) -> dict:
    """Una fila como llegaría en JSON: tipos de Python y nulos como None."""
    return {
        c: (None if pd.isna(v) else (v if c == "linea" else float(v)))
        for c, v in t[COLS].iloc[i].items()
    }


def test_el_ejemplo_de_swagger_son_las_variables_del_modelo():
    """Si `params.yaml` cambia las variables, el ejemplo deja de servir: falla
    aquí y no en la cara de quien prueba la API."""
    assert list(EJEMPLO) == COLS


def test_la_prediccion_es_la_de_predict_sobre_la_misma_fila(arts):
    t, reg, clf = arts
    s = Servicio({("regresion", 1): reg, ("clasificador", 1): clf}, [1, 5])
    for i in range(20):
        r = s.retraso(_vector(t, i))
        assert r["horizonte_paradas"] == 1
        assert r["retraso_s"] == pytest.approx(
            predict.predecir(reg, t.iloc[[i]]).iloc[0], abs=1e-4
        )
        m = s.mas_de_5min(_vector(t, i))
        assert m["probabilidad"] == pytest.approx(
            predict.probabilidad(clf, t.iloc[[i]]).iloc[0], abs=1e-6
        )


def test_un_vector_con_nulos_y_una_linea_no_vista_predice(arts):
    """Desde JSON, una columna con un nulo queda como `object` y XGBoost la
    rechaza. La línea que el modelo no vio queda como faltante (bitácora 040)."""
    t, reg, _ = arts
    s = Servicio({("regresion", 1): reg}, [1])
    v = _vector(t) | {"bus_anterior_retraso_s": None, "tramo_ganado_5min": None}
    assert np.isfinite(s.retraso(v)["retraso_s"])
    assert np.isfinite(s.retraso(v | {"linea": "8"})["retraso_s"])


def test_enteros_y_decimales_dan_lo_mismo(arts):
    """Swagger manda `31` donde el entrenamiento vio `31.0`."""
    _, reg, _ = arts
    s = Servicio({("regresion", 1): reg}, [1])
    decimales = {k: v if k == "linea" else float(v) for k, v in EJEMPLO.items()}
    assert s.retraso(EJEMPLO) == s.retraso(decimales)


def test_p_igual_a_tau_llega_tarde(arts):
    """τ se eligió con `precision_recall_curve`, que avisa con P ≥ τ (ADR-025)."""
    t, _, clf = arts
    p = float(predict.probabilidad(clf, t.iloc[[0]]).iloc[0])
    s = Servicio({("clasificador", 1): {**clf, "umbral": p}}, [1])
    assert s.mas_de_5min(_vector(t))["llega_tarde"] is True


def test_el_vector_trae_exactamente_las_variables(arts):
    t, reg, _ = arts
    s = Servicio({("regresion", 1): reg}, [1])
    v = _vector(t)
    sin_hora = {k: x for k, x in v.items() if k != "hora"}
    with pytest.raises(VariablesInvalidas) as e:
        s.retraso(sin_hora)
    assert e.value.args[0]["faltan"] == ["hora"]
    with pytest.raises(VariablesInvalidas) as e:
        s.retraso(v | {"trafico_congestion_frac": 0.5})
    assert e.value.args[0]["sobran"] == ["trafico_congestion_frac"]
    for mal in ({"linea": 92.0}, {"hora": "12"}):
        with pytest.raises(VariablesInvalidas):
            s.retraso(v | mal)


def test_horizonte_invalido_y_modelo_no_disponible(arts):
    _, reg, _ = arts
    s = Servicio({("regresion", 1): reg}, [1, 5])
    with pytest.raises(HorizonteInvalido):
        s.retraso(EJEMPLO, 4)
    with pytest.raises(ModeloNoDisponible):
        s.retraso(EJEMPLO, 5)
    with pytest.raises(ModeloNoDisponible):
        s.mas_de_5min(EJEMPLO, 1)


def test_un_modelo_que_falta_no_tumba_el_arranque(arts, tmp_path, monkeypatch):
    """Hasta el 21/10 no hay clasificador: la regresión se sirve igual."""
    _, reg, _ = arts

    def salidas(h=None):
        d = tmp_path / (f"h{h}" if h else "")
        return {"modelo": d / "model.pkl", "clasificador": d / "model_clasificador.pkl"}

    for h in (None, 5):
        salidas(h)["modelo"].parent.mkdir(parents=True, exist_ok=True)
        salidas(h)["modelo"].write_bytes(pickle.dumps(reg))
    monkeypatch.setattr(model_service.features, "salidas", salidas)
    monkeypatch.setattr(model_service, "horizontes", lambda: [1, 5, 10])
    s = Servicio.desde_disco()
    assert sorted(s.modelos_cargados) == [("regresion", 1), ("regresion", 5)]
    assert s.retraso(EJEMPLO, 5)["horizonte_paradas"] == 5
    with pytest.raises(ModeloNoDisponible):
        s.retraso(EJEMPLO, 10)
    assert [m["modelo"] for m in s.modelos()] == ["regresion", "regresion"]


def test_sin_ningun_modelo_la_api_arranca(tmp_path, monkeypatch):
    """Un clon sin `dvc pull`: arranca, `/modelos` vacío y cada predicción, 503."""
    monkeypatch.setattr(
        model_service.features,
        "salidas",
        lambda h=None: {"modelo": tmp_path / "no", "clasificador": tmp_path / "no"},
    )
    s = Servicio.desde_disco()
    assert s.modelos() == []
    with pytest.raises(ModeloNoDisponible):
        s.retraso(EJEMPLO)


def test_los_horizontes_son_los_de_params():
    assert model_service.horizontes() == [
        CFG["horizonte_paradas"],
        *CFG["horizontes_barrido"],
    ]


def test_sin_retraso_actual_no_hay_prediccion(arts):
    """`retraso_s` es el retraso de ahora, y el modelo de residuo le suma su
    corrección. Nulo, la predicción sería NaN, y FastAPI la serializa como
    `null` con un 200: una respuesta que parece válida."""
    t, reg, _ = arts
    s = Servicio({("regresion", 1): reg}, [1])
    with pytest.raises(VariablesInvalidas) as e:
        s.retraso(_vector(t) | {"retraso_s": None})
    assert e.value.args[0]["nulas"] == ["retraso_s"]
```

- [ ] **Step 2: comprobar que fallan**

Run: uv run pytest tests/test_servicio.py -q
Expected: error de colección, `ImportError: cannot import name 'EJEMPLO' from 'project.api.schemas'`.

- [ ] **Step 3: `api/schemas.py`.** Sustituir el fichero entero por:

```python
"""Contratos de entrada y salida de la API.

Los modelos Pydantic viven aquí, no en los routers: los routers validan y
delegan, y `services/` no importa nada de `api/`. La lista de variables no se
copia: la conoce el artefacto, y `services/` comprueba el vector contra ella.
La única copia es el ejemplo de Swagger, y un test la ata a
`features.variables()`.
"""

from pydantic import BaseModel, Field

# Una fila real de ENTRENAMIENTO (línea 92, 18/09/2026), nunca de la prueba:
# mirar predicciones de la prueba antes de su evaluación única la gastaría.
EJEMPLO = {
    "retraso_s": 228.42,
    "retraso_lag1_s": 290.85,
    "retraso_lag2_s": 296.0,
    "retraso_delta_s": -62.43,
    "t_prog_hasta_objetivo_s": 76.0,
    "dist_objetivo_m": 271.25,
    "stop_sequence": 31,
    "abscisa_parada_m": 9050.76,
    "linea_retraso_1min": -132.53,
    "linea_pasos_1min": 5,
    "linea_retraso_5min": -115.85,
    "linea_pasos_5min": 41,
    "linea_retraso_15min": -101.14,
    "linea_pasos_15min": 111,
    "bus_anterior_retraso_s": -419.46,
    "bus_anterior_edad_s": 115.25,
    "tramo_ganado_5min": 5.48,
    "tramo_soporte_5min": 2,
    "tramo_ganado_15min": 5.48,
    "tramo_soporte_15min": 2,
    "tramo_sesgo_s": -7.62,
    "hora": 12.98,
    "dia_semana": 4,
    "fin_de_semana": 0,
    "linea": "92",
}


class Vector(BaseModel):
    """Las variables del modelo, ya calculadas: exactamente las de `GET /modelos`."""

    variables: dict[str, float | str | None] = Field(
        ...,
        description="Nombre → valor. `linea` es texto; el resto, números o null.",
        examples=[EJEMPLO],
    )


class Retraso(BaseModel):
    horizonte_paradas: int
    retraso_s: float = Field(
        ..., description="Segundos de retraso en la parada stop_sequence + h"
    )


class MasDe5Min(BaseModel):
    horizonte_paradas: int
    probabilidad: float = Field(..., ge=0.0, le=1.0)
    umbral: float = Field(..., description="τ, elegido en la validación (ADR-025)")
    llega_tarde: bool = Field(..., description="probabilidad ≥ umbral")
    tasa_base_validacion: float = Field(
        ..., description="Fracción de más de 5 min en la validación (ADR-006)"
    )


class Modelo(BaseModel):
    modelo: str
    horizonte_paradas: int
    columnas: list[str]
    n_arboles: int
    mlflow_run_id: str | None
    dias_validacion: list[str]
    umbral: float | None = None
    tasa_base_validacion: float | None = None


class HealthResponse(BaseModel):
    status: str
```

- [ ] **Step 4: `services/model_service.py`.** Escribir:

```python
"""Los modelos en memoria y la predicción de un vector de variables.

Es la única capa que carga modelos (CLAUDE.md): una vez, al arrancar la API, no
por petición. La API valida el JSON y delega aquí; aquí no se importa nada de
`api/`. La transformación de la entrada es la del entrenamiento, porque pasa por
`predict.predecir` y `predict.probabilidad`, que pasan por `features.matriz`.
"""

from __future__ import annotations

import pandas as pd
import yaml

from project import features, predict
from project.config import RAIZ

REGRESION, CLASIFICADOR = "regresion", "clasificador"
# La clave de `features.salidas` de cada modelo servido. Los de la capa 192 no
# se sirven: su aportación la decide el ADR-024.
SALIDA = {REGRESION: "modelo", CLASIFICADOR: "clasificador"}


class VariablesInvalidas(ValueError):
    """El vector no trae exactamente las variables del modelo, o con su tipo."""


class HorizonteInvalido(ValueError):
    """Un horizonte para el que no se entrena ningún modelo."""


class ModeloNoDisponible(LookupError):
    """El horizonte es válido, pero su modelo no está cargado."""


def horizontes() -> list[int]:
    """El de `params.yaml` y los del barrido (ADR-023), en ese orden."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    f = cfg["features"]
    return [f["horizonte_paradas"], *f["horizontes_barrido"]]


def fila(columnas: list[str], variables: dict) -> pd.DataFrame:
    """El vector como tabla de una fila, con los tipos del entrenamiento.

    Las claves tienen que ser exactamente `columnas`. Los nulos valen, porque
    hay variables nulas de verdad, como `bus_anterior_retraso_s`; en
    `retraso_s` no, porque sin el retraso de ahora no hay predicción. Las
    numéricas van a `float64`: desde JSON, una columna con un nulo queda como
    `object` y XGBoost la rechaza.
    """
    faltan = [c for c in columnas if c not in variables]
    sobran = sorted(set(variables) - set(columnas))
    if faltan or sobran:
        raise VariablesInvalidas({"faltan": faltan, "sobran": sobran})
    if variables["retraso_s"] is None:
        raise VariablesInvalidas(
            {"nulas": ["retraso_s"], "motivo": "es el retraso de ahora"}
        )
    mal_tipo = [
        c
        for c in columnas
        if variables[c] is not None and isinstance(variables[c], str) != (c == "linea")
    ]
    if mal_tipo:
        raise VariablesInvalidas(
            {"tipo": mal_tipo, "esperado": "linea es texto; el resto, números o nulos"}
        )
    t = pd.DataFrame([variables], columns=columnas)
    numericas = [c for c in columnas if c != "linea"]
    t[numericas] = t[numericas].astype("float64")
    return t


class Servicio:
    """Los artefactos cargados, por (modelo, horizonte)."""

    def __init__(self, modelos: dict[tuple[str, int], dict], horizontes: list[int]):
        self.modelos_cargados = modelos
        self.horizontes = horizontes

    @classmethod
    def desde_disco(cls) -> Servicio:
        """Todo artefacto que exista en `features.salidas`. Uno que falta no
        tumba el arranque: su endpoint responde que no está disponible."""
        hs = horizontes()
        modelos = {}
        for h in hs:
            rutas = features.salidas(None if h == hs[0] else h)
            for nombre, clave in SALIDA.items():
                if rutas[clave].exists():
                    modelos[nombre, h] = predict.cargar(rutas[clave])
        return cls(modelos, hs)

    def _artefacto(self, nombre: str, horizonte: int | None) -> tuple[int, dict]:
        h = self.horizontes[0] if horizonte is None else horizonte
        if h not in self.horizontes:
            raise HorizonteInvalido({"horizonte": h, "validos": self.horizontes})
        if (nombre, h) not in self.modelos_cargados:
            raise ModeloNoDisponible(f"no hay modelo de {nombre} para h = {h}")
        return h, self.modelos_cargados[nombre, h]

    def modelos(self) -> list[dict]:
        """Lo que hay cargado, para `GET /modelos`."""
        salida = []
        for (nombre, h), a in sorted(self.modelos_cargados.items()):
            m = {
                "modelo": nombre,
                "horizonte_paradas": h,
                "columnas": a["columnas"],
                "n_arboles": int(a["n_arboles"]),
                "mlflow_run_id": a.get("mlflow_run_id"),
                "dias_validacion": a["validacion"]["dias"],
            }
            if nombre == CLASIFICADOR:
                m["umbral"] = float(a["umbral"])
                m["tasa_base_validacion"] = float(a["validacion"]["tasa_base"])
            salida.append(m)
        return salida

    def retraso(self, variables: dict, horizonte: int | None = None) -> dict:
        """Segundos de retraso en la parada `stop_sequence + h` (ADR-006)."""
        h, a = self._artefacto(REGRESION, horizonte)
        y = predict.predecir(a, fila(a["columnas"], variables)).iloc[0]
        return {"horizonte_paradas": h, "retraso_s": float(y)}

    def mas_de_5min(self, variables: dict, horizonte: int | None = None) -> dict:
        """P(más de 5 min tarde) y la decisión con el τ del artefacto (ADR-025):
        se avisa si P ≥ τ, la convención con la que se eligió."""
        h, a = self._artefacto(CLASIFICADOR, horizonte)
        p = float(predict.probabilidad(a, fila(a["columnas"], variables)).iloc[0])
        return {
            "horizonte_paradas": h,
            "probabilidad": p,
            "umbral": float(a["umbral"]),
            "llega_tarde": p >= a["umbral"],
            "tasa_base_validacion": float(a["validacion"]["tasa_base"]),
        }
```

- [ ] **Step 5: comprobar que pasan**

Run: uv run pytest tests/test_servicio.py tests/test_api.py -q
Expected: 11 passed en `test_servicio.py`, y `test_api.py::test_health_ok` sigue en verde.

- [ ] **Step 6: formato y commit**

```bash
uv run ruff format src/project/services src/project/api tests/test_servicio.py
uv run ruff check --fix src/project/services src/project/api tests/test_servicio.py
git add src/project/services/model_service.py src/project/api/schemas.py tests/test_servicio.py
git commit -m "feat(services): los modelos en memoria y la predicción de un vector de variables"
```

---

## Task 2: el router, `main.py` y los tests de la API (agente `serving`)

**Files:**
- Create: src/project/api/routers/prediccion.py
- Delete: src/project/api/routers/predict.py (vacío)
- Modify: `src/project/api/main.py` (se sustituye entero)
- Modify: `tests/test_api.py` (se sustituye entero)
- Modify: `CLAUDE.md` («Estado» y «Tests»)

**Interfaces:**
- Consumes: todo lo que produce la tarea 1.
- Produces: `GET /modelos`, `POST /prediccion/retraso` y `POST /prediccion/mas-de-5min`, con `?horizonte=` opcional. La dependencia `prediccion.servicio(request) -> Servicio`, que los tests sustituyen con `app.dependency_overrides`. `app.state.servicio`, que crea el `lifespan`.

- [ ] **Step 1: tests que fallan.** Sustituir `tests/test_api.py` entero por:

```python
"""La API valida, delega en `services/` y traduce sus errores. El servicio se
mockea: aquí no se carga ningún modelo (CLAUDE.md)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from project.api.main import app
from project.api.routers.prediccion import servicio
from project.api.schemas import EJEMPLO
from project.services.model_service import (
    HorizonteInvalido,
    ModeloNoDisponible,
    VariablesInvalidas,
)

# Sin `with`: no corre el `lifespan`, así que no se carga ningún modelo.
client = TestClient(app)


@pytest.fixture
def falso():
    s = MagicMock()
    app.dependency_overrides[servicio] = lambda: s
    yield s
    app.dependency_overrides.clear()


def test_health_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_retraso_delega_en_el_servicio(falso):
    falso.retraso.return_value = {"horizonte_paradas": 5, "retraso_s": 212.4}
    r = client.post("/prediccion/retraso?horizonte=5", json={"variables": EJEMPLO})
    assert r.status_code == 200
    assert r.json() == {"horizonte_paradas": 5, "retraso_s": 212.4}
    variables, h = falso.retraso.call_args.args
    assert h == 5
    assert variables == EJEMPLO


def test_sin_horizonte_decide_el_servicio(falso):
    falso.retraso.return_value = {"horizonte_paradas": 1, "retraso_s": 0.0}
    client.post("/prediccion/retraso", json={"variables": EJEMPLO})
    assert falso.retraso.call_args.args[1] is None


def test_mas_de_5min(falso):
    falso.mas_de_5min.return_value = {
        "horizonte_paradas": 1,
        "probabilidad": 0.31,
        "umbral": 0.42,
        "llega_tarde": False,
        "tasa_base_validacion": 0.061,
    }
    r = client.post("/prediccion/mas-de-5min", json={"variables": EJEMPLO})
    assert r.status_code == 200
    assert r.json()["llega_tarde"] is False


def test_variables_y_horizonte_invalidos_son_422(falso):
    falso.retraso.side_effect = VariablesInvalidas({"faltan": ["hora"], "sobran": []})
    r = client.post("/prediccion/retraso", json={"variables": EJEMPLO})
    assert r.status_code == 422
    assert r.json()["detail"] == {"faltan": ["hora"], "sobran": []}
    falso.retraso.side_effect = HorizonteInvalido({"horizonte": 4, "validos": [1, 5]})
    r = client.post("/prediccion/retraso?horizonte=4", json={"variables": EJEMPLO})
    assert r.status_code == 422


def test_un_modelo_que_falta_es_503(falso):
    falso.mas_de_5min.side_effect = ModeloNoDisponible(
        "no hay modelo de clasificador para h = 1"
    )
    r = client.post("/prediccion/mas-de-5min", json={"variables": EJEMPLO})
    assert r.status_code == 503
    assert "clasificador" in r.json()["detail"]


def test_un_cuerpo_mal_formado_no_llega_al_servicio(falso):
    assert client.post("/prediccion/retraso", json={}).status_code == 422
    r = client.post("/prediccion/retraso", json={"variables": {"hora": [1]}})
    assert r.status_code == 422
    r = client.post("/prediccion/retraso?horizonte=cinco", json={"variables": EJEMPLO})
    assert r.status_code == 422
    falso.retraso.assert_not_called()


def test_modelos(falso):
    falso.modelos.return_value = [
        {
            "modelo": "clasificador",
            "horizonte_paradas": 1,
            "columnas": list(EJEMPLO),
            "n_arboles": 148,
            "mlflow_run_id": "abc",
            "dias_validacion": ["2026-09-28"],
            "umbral": 0.42,
            "tasa_base_validacion": 0.061,
        }
    ]
    r = client.get("/modelos")
    assert r.status_code == 200
    assert r.json()[0]["umbral"] == 0.42


def test_swagger_lleva_el_ejemplo():
    """«Try it out» en /docs funciona sin teclear las 25 variables."""
    esquema = client.get("/openapi.json").json()
    vector = esquema["components"]["schemas"]["Vector"]["properties"]["variables"]
    assert vector["examples"] == [EJEMPLO]
```

- [ ] **Step 2: comprobar que fallan**

Run: `uv run pytest tests/test_api.py -q`
Expected: error de colección, `ModuleNotFoundError: No module named 'project.api.routers.prediccion'`.

- [ ] **Step 3: el router.** Borrar src/project/api/routers/predict.py (`git rm`) y crear src/project/api/routers/prediccion.py:

```python
"""Predicción: valida el JSON, delega en `services/` y traduce sus errores a
HTTP. Sin lógica de negocio (CLAUDE.md)."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from project.api.schemas import MasDe5Min, Modelo, Retraso, Vector
from project.services.model_service import (
    HorizonteInvalido,
    ModeloNoDisponible,
    Servicio,
    VariablesInvalidas,
)

router = APIRouter(tags=["predicción"])


def servicio(request: Request) -> Servicio:
    """El servicio que `main.py` cargó al arrancar. Los tests lo sustituyen."""
    return request.app.state.servicio


def _llamar(f: Callable[..., dict], *args) -> dict:
    try:
        return f(*args)
    except (VariablesInvalidas, HorizonteInvalido) as e:
        raise HTTPException(status_code=422, detail=e.args[0]) from e
    except ModeloNoDisponible as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/modelos", response_model=list[Modelo])
def modelos(s: Servicio = Depends(servicio)) -> list[dict]:
    """Modelos cargados por horizonte, con las variables que espera cada uno."""
    return s.modelos()


@router.post("/prediccion/retraso", response_model=Retraso)
def retraso(
    cuerpo: Vector, horizonte: int | None = None, s: Servicio = Depends(servicio)
) -> dict:
    """Segundos de retraso en la parada `stop_sequence + horizonte` (ADR-006).
    Sin horizonte, el de `params.yaml`."""
    return _llamar(s.retraso, cuerpo.variables, horizonte)


@router.post("/prediccion/mas-de-5min", response_model=MasDe5Min)
def mas_de_5min(
    cuerpo: Vector, horizonte: int | None = None, s: Servicio = Depends(servicio)
) -> dict:
    """Probabilidad de llegar con más de 5 min de retraso y decisión con el τ
    del modelo (ADR-025). Sin horizonte, el de `params.yaml`."""
    return _llamar(s.mas_de_5min, cuerpo.variables, horizonte)
```

- [ ] **Step 4: `main.py`.** Sustituir `src/project/api/main.py` entero por:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from project.api.routers import prediccion
from project.services.model_service import Servicio


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Carga única al arrancar, no por petición (CLAUDE.md).
    app.state.servicio = Servicio.desde_disco()
    yield


app = FastAPI(title="TFM API", lifespan=lifespan)
app.include_router(prediccion.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: comprobar que pasan**

Run: uv run pytest tests/test_api.py tests/test_servicio.py -q
Expected: 20 passed, con el warning de `TestClient` que ya existía.

- [ ] **Step 6: fronteras**

Run: `git grep -nE "^\s*(from|import)\s+(sklearn|pandas|numpy|xgboost|joblib)" -- src/project/api/`
Expected: sin salida.

- [ ] **Step 7: `CLAUDE.md`.** En «Estado», sustituir la línea

```markdown
Vacío, 0 líneas: `services/model_service.py`.
```

por

```markdown
Servido por API (spec del 15/10): `services/model_service.py` carga al
arrancar la regresión y el clasificador de cada horizonte, y `api/` los
expone en `/modelos`, `/prediccion/retraso` y `/prediccion/mas-de-5min`, con
Swagger en `/docs`. La entrada es el vector de variables ya calculado: el
servido en tiempo real sigue pendiente (ADR-016).
```

En «Tests», después del punto de `tests/test_api.py` (el que termina en «Endpoint nuevo ⇒ test nuevo.»), añadir el punto de abajo. En CLAUDE.md la ruta del principio va entre comillas invertidas, como en el resto de la lista; aquí va sin ellas porque `.claude/tests/test_memoria.py` exige que toda ruta citada así exista, y este plan se commitea antes de crear el fichero:

```markdown
- tests/test_servicio.py prueba `services/` con modelos sintéticos entrenados
  en el propio test: la predicción es la de `predict` sobre la misma fila, el
  vector trae exactamente las variables, los nulos y la línea no vista
  predicen, `retraso_s` nulo se rechaza, P = τ avisa y un modelo que falta no
  tumba el arranque. Mutantes 175-179.
```

Run: `uv run pytest .claude/tests -q`
Expected: todo PASS.

- [ ] **Step 8: formato y commit**

```bash
uv run ruff format src/project/api tests/test_api.py
uv run ruff check --fix src/project/api tests/test_api.py
git add src/project/api tests/test_api.py CLAUDE.md
git commit -m "feat(api): endpoints de predicción de retraso y de más de 5 min, con Swagger"
```

---

## Task 3: mutantes 175-179 (agente `serving`)

**Files:**
- Modify: `auditoria/catalogo.toml` (al final)

Si el 175 ya estuviera ocupado cuando se ejecute el plan, usar los cinco siguientes libres y cambiar los números en `CLAUDE.md` (tarea 2, paso 7).

- [ ] **Step 1: añadir los cinco mutantes**

```toml
[[mutante]]
id = "175"
nombre = "el servicio acepta variables de más"
capa = "serving"
# Una variable de más (p. ej. una de la 192 en el modelo sin tráfico) se
# ignoraría en silencio: quien llama cree que el modelo la usa.
fichero = "src/project/services/model_service.py"
buscar = '''    sobran = sorted(set(variables) - set(columnas))'''
reemplazar = '''    sobran = []'''
detector = ["tests/test_servicio.py::test_el_vector_trae_exactamente_las_variables"]
sondas = []

[[mutante]]
id = "176"
nombre = "la API no avisa con P igual a τ"
capa = "serving"
# τ se eligió con `precision_recall_curve`, que avisa con P ≥ τ (ADR-025).
fichero = "src/project/services/model_service.py"
buscar = '''            "llega_tarde": p >= a["umbral"],'''
reemplazar = '''            "llega_tarde": p > a["umbral"],'''
detector = ["tests/test_servicio.py::test_p_igual_a_tau_llega_tarde"]
sondas = []

[[mutante]]
id = "177"
nombre = "el vector llega a XGBoost con columnas object"
capa = "serving"
# Desde JSON, una columna con un nulo queda como `object` y XGBoost la rechaza.
fichero = "src/project/services/model_service.py"
buscar = '''    t[numericas] = t[numericas].astype("float64")'''
reemplazar = '''    t[numericas] = t[numericas]'''
detector = ["tests/test_servicio.py::test_un_vector_con_nulos_y_una_linea_no_vista_predice"]
sondas = []

[[mutante]]
id = "178"
nombre = "un modelo que falta tumba el arranque de la API"
capa = "serving"
# Hasta el 21/10 no hay clasificador: la regresión tiene que servirse igual.
fichero = "src/project/services/model_service.py"
buscar = '''                if rutas[clave].exists():'''
reemplazar = '''                if True:'''
detector = ["tests/test_servicio.py::test_un_modelo_que_falta_no_tumba_el_arranque"]
sondas = []

[[mutante]]
id = "179"
nombre = "la API predice sin el retraso de ahora"
capa = "serving"
# Con `retraso_s` nulo, el modelo de residuo da NaN y FastAPI responde `null`
# con un 200.
fichero = "src/project/services/model_service.py"
buscar = '''    if variables["retraso_s"] is None:'''
reemplazar = '''    if False:'''
detector = ["tests/test_servicio.py::test_sin_retraso_actual_no_hay_prediccion"]
sondas = []
```

Cada `buscar` debe aparecer una sola vez en el fichero. Comprobarlo:

```bash
for s in '    sobran = sorted(set(variables) - set(columnas))' \
         '            "llega_tarde": p >= a["umbral"],' \
         '    t[numericas] = t[numericas].astype("float64")' \
         '                if rutas[clave].exists():' \
         '    if variables["retraso_s"] is None:'; do
  echo "$(grep -cF -- "$s" src/project/services/model_service.py)  $s"
done
```

Expected: un `1` delante de cada línea.

- [ ] **Step 2: commit (`mutar.py` audita commits)**

```bash
git add auditoria/catalogo.toml
git commit -m "test(auditoria): mutantes 175-179 del servicio de predicción"
```

- [ ] **Step 3: ejecutar solo los nuevos.** Con `PYTHONUTF8=1`, por el issue #3:

```powershell
$env:PYTHONUTF8 = "1"; uv run python auditoria/mutar.py --solo 175 176 177 178 179
```

Expected: los cinco «detectado», y los controles 000 y 002 bien. Si alguno sale «hueco» o «invalido», arreglar el `buscar` o el test antes de seguir; nunca el código de producción.

- [ ] **Step 4: commit del resultado**

```bash
git add auditoria/resultados/
git commit -m "test(auditoria): mutantes 175-179 detectados"
```

---

## Task 4: comprobación a mano y cierre (en línea)

- [ ] **Step 1: arrancar la API**, en una terminal aparte o desacoplada:

```powershell
uv run uvicorn project.api.main:app --port 8000
```

- [ ] **Step 2: peticiones**, con el ejemplo que publica la propia API:

```bash
B=http://127.0.0.1:8000
EX=$(curl -s $B/openapi.json | uv run python -c "import json,sys; print(json.dumps({'variables': json.load(sys.stdin)['components']['schemas']['Vector']['properties']['variables']['examples'][0]}))")
for q in "" "?horizonte=5" "?horizonte=4"; do curl -s -w " [%{http_code}]\n" -X POST "$B/prediccion/retraso$q" -H 'content-type: application/json' -d "$EX"; done
curl -s -w " [%{http_code}]\n" -X POST $B/prediccion/mas-de-5min -H 'content-type: application/json' -d "$EX"
curl -s -o /dev/null -w "docs [%{http_code}]\n" $B/docs
```

Expected:
- retraso sin horizonte y con h = 5: 200, con `retraso_s`. Los modelos del barrido existen en `models/h*/`;
- h = 4: 422, con `validos: [1, 2, 3, 5, 10]`;
- más de 5 min: 503 hasta el `dvc repro` del 21/10;
- `/docs`: 200.

- [ ] **Step 3: Swagger.** Abrir `http://127.0.0.1:8000/docs`. En `POST /prediccion/retraso`: «Try it out», «Execute». Expected: 200 sin haber tecleado nada. Parar `uvicorn` y comprobar que no queda ningún proceso escuchando en el puerto 8000.

- [ ] **Step 4: suite completa**

Run: `uv run pytest -q` y `uv run pytest .claude/tests -q`
Expected: todo PASS, salvo el `xfail` estricto conocido.

Run: `uv run ruff format --check . ; uv run ruff check .`
Expected: sin cambios ni errores.

- [ ] **Step 5:** `git status` limpio, salvo `graphify-out/`, que es de otro trabajo y no se toca. `git log --oneline` muestra los commits de las tareas 1-3.
