"""Stage `train`: XGBoost sobre la tabla de entrenamiento (ADR-005).

    uv run python -m project.train            # lo que ejecuta `dvc repro train`

Las variables son las de `features.variables()` y entran por `features.matriz`,
con las categorías de `linea` fijadas aquí y guardadas con el modelo (ADR-019).
Ninguna lista de columnas se escribe a mano: es el train/serve skew.

La parada temprana se mide en los últimos `dias_validacion` días del
entrenamiento, nunca en la prueba. Con los árboles que salen, el modelo se
reajusta con el entrenamiento ENTERO: esos días son 3 de sus 7 lectivos y los
más cercanos a la prueba, que tiene más retrasos (5,4 % frente a 7,1 % de más
de 5 min).

Guarda en `settings.model_path` el modelo, sus columnas, sus categorías, los
árboles y el run de MLflow donde `evaluate.py` añade las métricas de la prueba.
"""

from __future__ import annotations

import json
import pickle

import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
import yaml
from xgboost import XGBRegressor

from project import features
from project.config import RAIZ, settings

EXPERIMENTO = "retraso_siguiente_parada"


def columnas(cfg: dict) -> list[str]:
    """Las variables del modelo según `params.yaml → features`."""
    return features.variables(tuple(cfg["lags_min"]), features.ventanas_flota(cfg))


def separar_validacion(
    train: pd.DataFrame, dias: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(ajuste, validación): la validación son los últimos `dias` días de servicio."""
    corte = np.sort(train["fecha_servicio"].unique())[-dias]
    val = train["fecha_servicio"] >= corte
    return train[~val], train[val]


def entrenar(
    train: pd.DataFrame, variables: list[str], objetivo: str, params: dict
) -> dict:
    """Parada temprana con la validación y reajuste con todo `train`."""
    p = dict(params)
    dias = p.pop("dias_validacion")
    categorias = features.categorias_linea(train)

    def x(t: pd.DataFrame) -> pd.DataFrame:
        return features.matriz(t, variables, categorias)

    fijos = {"enable_categorical": True, "tree_method": "hist"}
    ajuste, val = separar_validacion(train, dias)
    m = XGBRegressor(**p, **fijos)
    m.fit(
        x(ajuste), ajuste[objetivo], eval_set=[(x(val), val[objetivo])], verbose=False
    )
    n = m.best_iteration + 1
    pred_val = pd.Series(m.predict(x(val)), index=val.index)

    final = XGBRegressor(
        **{**p, "n_estimators": n, "early_stopping_rounds": None}, **fijos
    )
    final.fit(x(train), train[objetivo], verbose=False)
    return {
        "modelo": final,
        "columnas": variables,
        "categorias": categorias,
        "n_arboles": n,
        "validacion": {
            "dias": sorted(val["fecha_servicio"].dt.strftime("%Y-%m-%d").unique()),
            "modelo": features.errores(pred_val, val[objetivo]),
            **{
                k: features.errores(v, val[objetivo])
                for k, v in features.predicciones_baseline(val).items()
            },
        },
    }


def main() -> None:
    params = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    cfg, p = params["features"], params["train"]
    train = pd.read_parquet(settings.processed_dir / "train.parquet")

    mlflow.set_experiment(EXPERIMENTO)
    with mlflow.start_run() as run:
        art = entrenar(train, columnas(cfg), cfg["objetivo"], p)
        art["mlflow_run_id"] = run.info.run_id
        mlflow.log_params(
            {**p, "n_arboles": art["n_arboles"], "test_desde": cfg["test_desde"]}
        )
        mlflow.log_dict(
            {"variables": art["columnas"], "categorias": art["categorias"]},
            "variables.json",
        )
        mlflow.log_metrics(
            {
                f"val.{k}.{m}": v
                for k, d in art["validacion"].items()
                if k != "dias"
                for m, v in d.items()
            }
        )
        mlflow.xgboost.log_model(art["modelo"], name="modelo")

    ruta = RAIZ / settings.model_path
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(pickle.dumps(art))
    print(json.dumps({k: art[k] for k in ("n_arboles", "validacion")}, indent=2))


if __name__ == "__main__":
    main()
