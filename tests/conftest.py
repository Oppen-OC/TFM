"""Fixtures compartidas de los tests del TFM.

`fixtures.json` tiene la forma EXACTA de los payloads reales capturados el
15/08/2026. No son ejemplos inventados: se copiaron de la respuesta real de
cada servicio, con sus rarezas dentro. Esa es la razón de que estos tests
detecten regresiones que un mock limpio no vería.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from project.analysis.simulacion import simular_flota

AQUI = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def fix() -> dict:
    """Payloads reales de las cinco fuentes, más los bloques de gid."""
    return json.loads((AQUI / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def flota_simulada() -> pd.DataFrame:
    """60 buses con verdad-terreno conocida, 20 snapshots cada 30 s.

    Cada fila lleva la columna `verdad` con el bus real que la generó. Sin eso
    no se puede medir si el tracker recupera la identidad: es la única forma de
    distinguir "reconstruyó 60 trayectorias" de "reconstruyó 60 trayectorias
    CORRECTAS", que es lo que escondió la trampa 004.

    El generador vive en `project.analysis.simulacion` porque lo comparte con el
    medidor `project.analysis.medir_tracking`, del que salen las cifras de
    `docs/bitacora/001-error-identidad-se-mide-en-trayectorias.md`. Duplicarlo
    haría que esas cifras y estos umbrales dejasen de hablar de lo mismo.
    """
    return simular_flota()
