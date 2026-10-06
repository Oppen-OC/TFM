"""Cuánto mueve la semilla la cifra del modelo v2 (bitácora 043, abiertos).

    uv run python -m project.analysis.semillas_v2

El brazo fijado en `params.yaml → train` se entrena entero con otras semillas
(`train.entrenar`: parada con la validación y reajuste con todo) y cada modelo
se evalúa en la prueba frente a `persistencia_tramo`, remuestreando viajes y
días. La semilla mueve `subsample` y `colsample_bytree` (0,8). La 42 es la de
`metrics/eval.json`.

No elige nada: se informa el rango, no el mejor. Resultado en
`auditoria/resultados/semillas_v2.json`.
"""

from __future__ import annotations

import json

import pandas as pd
import yaml

from project import evaluate, features, predict, train
from project.config import RAIZ, settings

SEMILLAS = (0, 1, 2, 3)


def main() -> None:
    params = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    cfg, p = params["features"], params["train"]
    obj = cfg["objetivo"]
    tabla = pd.read_parquet(settings.processed_dir / "train.parquet")
    prueba = pd.read_parquet(settings.processed_dir / "test.parquet")
    real = prueba[obj]
    pt = features.predicciones_baseline(prueba)["persistencia_tramo"]
    viaje = prueba.groupby(features.CLAVE_VIAJE, sort=False).ngroup()

    filas = []
    for s in SEMILLAS:
        art = train.entrenar(tabla, train.columnas(cfg), obj, {**p, "random_state": s})
        e = predict.predecir(art, prueba) - real
        filas.append(
            {
                "semilla": s,
                "n_arboles": art["n_arboles"],
                "mae_s": round(float(e.abs().mean()), 2),
                "por_viajes": evaluate.diferencia(e, pt - real, viaje),
                "por_dias": evaluate.diferencia(e, pt - real, prueba["fecha_servicio"]),
            }
        )
        print(filas[-1], flush=True)

    mae = [f["mae_s"] for f in filas]
    dif = [f["por_viajes"]["mae_s"] for f in filas]
    resultado = {
        "semillas": filas,
        "rango_mae_s": [min(mae), max(mae)],
        "rango_diferencia_s": [min(dif), max(dif)],
    }
    salida = RAIZ / "auditoria" / "resultados" / "semillas_v2.json"
    salida.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in resultado.items() if k != "semillas"}))


if __name__ == "__main__":
    main()
