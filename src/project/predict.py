"""Predicción con el modelo entrenado: la usan `evaluate.py` y, después, `services/`.

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
