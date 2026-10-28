"""La explicación SHAP: lo que no da la cara si se rompe.

Unas contribuciones pegadas a otra fila, o que olvidan que el modelo v2 es de
residuo, siguen dando números plausibles. Un resumen que cuenta filas fuera de
la población describe un modelo que no se usa ahí. Y una variable nueva sin
grupo desaparecería del resumen por grupos. Se prueba con modelos sintéticos
diminutos, entrenados aquí.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from project import predict, train

OBJ = "retraso_siguiente_parada_s"
CFG = {
    "lags_min": [1, 5],
    "incluir_flota": True,
    "ventanas_flota_min": [5],
    "incluir_trafico": True,
}
COLS = train.columnas(CFG)
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


def _tabla(dias=4, filas_por_dia=300):
    rng = np.random.default_rng(0)
    n = dias * filas_por_dia
    t = pd.DataFrame({c: rng.normal(size=n) * 100 for c in COLS if c != "linea"})
    t["linea"] = rng.choice(["92", "19", "35"], n)
    t["fecha_servicio"] = pd.Timestamp("2026-09-01") + pd.to_timedelta(
        np.repeat(np.arange(dias), filas_por_dia), unit="D"
    )
    t["viaje_id"] = np.arange(n) // 10
    t["dist_objetivo_m"] = rng.uniform(100, 2000, n)
    t["trafico_cubierto_m"] = t["dist_objetivo_m"] * rng.uniform(0, 1, n)
    # Fuera de la población: sin tiempo para llegar, o no es el último paso.
    t["horizonte_previsto_s"] = rng.normal(30, 60, n)
    t["ultimo_conocido"] = rng.random(n) > 0.2
    t[OBJ] = t["retraso_s"] + 50 * (t["linea"] == "92") + 0.5 * t["tramo_sesgo_s"]
    t[f"{OBJ}_bin"] = (t[OBJ] > 0).astype(int)
    return t


@pytest.fixture(scope="module")
def modelos():
    t = _tabla()
    reg = train.entrenar(t, COLS, OBJ, PARAMS)
    clf = train.entrenar_clasificador(t, COLS, OBJ, 300, PARAMS)
    return t, reg, clf


def test_las_contribuciones_suman_la_salida_del_modelo(modelos):
    """La regresión v2 explica el residuo: sesgo + Σ = ŷ − retraso_s. El
    clasificador, el log-odds. Con la tabla al revés: cada fila, la suya
    (trampa 012)."""
    t, reg, clf = modelos
    al_reves = t.iloc[::-1]
    c = predict.contribuciones(reg, al_reves)
    assert c.index.equals(al_reves.index)
    assert list(c.columns) == [*COLS, "sesgo"]
    residuo = predict.predecir(reg, t) - t["retraso_s"]
    # pandas alinea por índice; np.allclose compararía por posición.
    assert (c.sum(axis=1) - residuo).abs().max() < 1e-3
    c = predict.contribuciones(clf, al_reves)
    p = predict.probabilidad(clf, t)
    assert (c.sum(axis=1) - np.log(p / (1 - p))).abs().max() < 1e-3


def test_la_unidad_la_dice_el_artefacto(modelos):
    _, reg, clf = modelos
    assert predict.unidad(reg) == "s del residuo"
    assert predict.unidad({**reg, "residuo": False}) == "s"
    assert predict.unidad(clf) == "log-odds"
