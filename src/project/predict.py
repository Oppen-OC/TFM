"""Predicción con el modelo entrenado: la usan `evaluate.py` y, después, `services/`.

El modelo se guarda con sus columnas y con las categorías de `linea` del
entrenamiento (`train.py`). La entrada pasa por `features.matriz` con ESAS, no
con las que traiga la tabla: recalcularlas aquí numera las líneas de otra forma
y el modelo lee otra línea sin error alguno (ADR-019).
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
    """Retraso en la parada siguiente, en segundos, con el índice de `tabla`."""
    x = features.matriz(tabla, artefacto["columnas"], artefacto["categorias"])
    return pd.Series(artefacto["modelo"].predict(x), index=tabla.index)
