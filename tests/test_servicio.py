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
