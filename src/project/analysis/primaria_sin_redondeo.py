"""La comparación con y sin la 192 sin redondear (ADR-024), solo lectura.

    uv run python -m project.analysis.primaria_sin_redondeo --horizonte 5

`evaluate.diferencia` guarda dos decimales, y con 12-13 días el extremo del
intervalo por días puede quedarse en `-0.0` o `0.0` (bitácora 057). Esto repite
`evaluate.comparacion_trafico` con la misma semilla y las mismas réplicas sobre
las mismas tablas y modelos, sin redondear: reproduce `trafico.json` y no es una
segunda evaluación. No escribe en `metrics/` ni en MLflow.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd
import yaml

from project import evaluate, features, predict
from project.config import RAIZ


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--horizonte", type=int, default=None)
    a = p.parse_args()

    # Sombrea el builtin dentro del módulo: el `round` de `diferencia` y de
    # `con_menos_sin` pasa a devolver el valor entero.
    evaluate.round = lambda v, n=None: float(v)
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    rutas = features.salidas(a.horizonte)
    con = predict.cargar(rutas["modelo_trafico"])
    sin = predict.cargar(rutas["modelo"])
    evaluate.comprobar_pareja(con, sin)
    test = pd.read_parquet(rutas["tabla"] / "test.parquet")
    m = evaluate.comparacion_trafico(
        test,
        predict.predecir(con, test),
        predict.predecir(sin, test),
        cfg["features"]["objetivo"],
    )
    claves = ("dias", "con_sensor", "sin_sensor", "con_congestion_observada")
    print(json.dumps({k: m[k] for k in claves}, indent=1))


if __name__ == "__main__":
    main()
