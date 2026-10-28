"""Predicción con los modelos entrenados: la usan `evaluate.py` y, después, `services/`.

El modelo se guarda con sus columnas y con las categorías de `linea` del
entrenamiento (`train.py`). La entrada pasa por `features.matriz` con ESAS, no
con las que traiga la tabla: con las de la tabla, una línea que el
entrenamiento no vio hace que XGBoost rechace la petición entera con error;
con las guardadas queda nula y se predice como dato faltante (ADR-019).
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd
import xgboost as xgb

from project import features
from project.config import RAIZ, settings


def cargar(ruta: Path | None = None) -> dict:
    """El artefacto de `train.py`: modelo, columnas, categorías y run de MLflow."""
    return pickle.loads((RAIZ / (ruta or settings.model_path)).read_bytes())


def predecir(artefacto: dict, tabla: pd.DataFrame) -> pd.Series:
    """Retraso en la parada siguiente, en segundos, con el índice de `tabla`.

    Un modelo de residuo predice cuánto se aparta de la persistencia: se le suma
    `retraso_s` (ADR-021). El modo lo dice el artefacto, no quien llama.
    """
    x = features.matriz(tabla, artefacto["columnas"], artefacto["categorias"])
    pred = pd.Series(artefacto["modelo"].predict(x), index=tabla.index)
    return pred + tabla["retraso_s"] if artefacto["residuo"] else pred


def probabilidad(artefacto: dict, tabla: pd.DataFrame) -> pd.Series:
    """P(más de `umbral_retraso_s` tarde) en la parada objetivo, con el índice de
    `tabla` (ADR-025). Llegará tarde si es `>= artefacto["umbral"]`.

    Pasa por `features.matriz` con las categorías guardadas, como `predecir`.
    """
    x = features.matriz(tabla, artefacto["columnas"], artefacto["categorias"])
    return pd.Series(artefacto["modelo"].predict_proba(x)[:, 1], index=tabla.index)


def contribuciones(artefacto: dict, tabla: pd.DataFrame) -> pd.DataFrame:
    """SHAP exacto de XGBoost (TreeSHAP), una columna por variable más `sesgo`,
    con el índice de `tabla`.

    Suman la salida bruta del árbol: el residuo en un modelo de residuo (se le
    suma `retraso_s` para tener `predecir`), el retraso en uno que no lo es, y
    el log-odds en el clasificador. Pasa por `features.matriz` como `predecir`.
    """
    x = features.matriz(tabla, artefacto["columnas"], artefacto["categorias"])
    d = xgb.DMatrix(x, enable_categorical=True)
    c = artefacto["modelo"].get_booster().predict(d, pred_contribs=True)
    return pd.DataFrame(c, index=tabla.index, columns=[*artefacto["columnas"], "sesgo"])


def unidad(artefacto: dict) -> str:
    """En qué suman las `contribuciones` del artefacto."""
    if "umbral" in artefacto:
        return "log-odds"
    return "s del residuo" if artefacto["residuo"] else "s"
