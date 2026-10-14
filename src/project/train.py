"""Stage `train`: XGBoost sobre la tabla de entrenamiento (ADR-005).

    uv run python -m project.train            # lo que ejecuta `dvc repro train`

Las variables son las de `features.variables()` y entran por `features.matriz`,
con las categorías de `linea` fijadas aquí y guardadas con el modelo (ADR-019).
Ninguna lista de columnas se escribe a mano: es el train/serve skew.

La parada temprana se mide en los últimos `dias_validacion` días del
entrenamiento, nunca en la prueba: la última semana del entrenamiento
(28/09-04/10 con el corte del ADR-024), de lunes a domingo como la prueba
(ADR-021). Con los árboles que salen, el modelo se reajusta con el
entrenamiento ENTERO: esos días son los más cercanos a la prueba, que tiene
más retrasos (5,4 % frente a 7,1 % de más de 5 min).

Con `residuo`, el árbol aprende cuánto se aparta el objetivo de la persistencia
y `predict` le suma `retraso_s`: un árbol reconstruye a trozos la identidad
`retraso_s → objetivo`, y eso cuesta error (ADR-021). Qué brazo se usa lo elige
`analysis/elegir_brazo.py` en la validación.

Guarda en `settings.model_path` el modelo, sus columnas, sus categorías, si es
de residuo, los árboles y el run de MLflow donde `evaluate.py` añade las
métricas de la prueba.
"""

from __future__ import annotations

import argparse
import json
import pickle

import mlflow
import mlflow.xgboost
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import precision_recall_curve
from xgboost import XGBClassifier, XGBRegressor

from project import evaluate, features, predict
from project.config import RAIZ

EXPERIMENTO = "retraso_siguiente_parada"
EXPERIMENTO_CLASIFICADOR = "retraso_mas_de_5min"
# El clasificador cambia la pérdida y nada más (ADR-025).
CLASIFICADOR = {"objective": "binary:logistic", "eval_metric": "logloss"}


def columnas(cfg: dict) -> list[str]:
    """Las variables del modelo según `params.yaml → features`."""
    return features.variables(
        tuple(cfg["lags_min"]),
        features.ventanas_flota(cfg),
        trafico=cfg["incluir_trafico"],
    )


def columnas_clasificador(cfg: dict) -> list[str]:
    """Las de la regresión sin la capa 192, la active o no `params.yaml`: su
    aportación la decide el ADR-024, no este modelo (ADR-025)."""
    return columnas({**cfg, "incluir_trafico": False})


def separar_validacion(
    train: pd.DataFrame, dias: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(ajuste, validación): la validación son los últimos `dias` días de servicio."""
    corte = np.sort(train["fecha_servicio"].unique())[-dias]
    val = train["fecha_servicio"] >= corte
    return train[~val], train[val]


FIJOS = {"enable_categorical": True, "tree_method": "hist"}
# Claves de `params.yaml → train` que son de este módulo, no de XGBoost.
PROPIAS = ("dias_validacion", "residuo")


def _xgb(params: dict, clase: type = XGBRegressor, **cambios):
    p = {k: v for k, v in params.items() if k not in PROPIAS}
    return clase(**{**p, **cambios}, **FIJOS)


def _y(t: pd.DataFrame, objetivo: str, residuo: bool) -> pd.Series:
    """Lo que aprende el árbol: el objetivo, o cuánto se aparta de la persistencia."""
    return t[objetivo] - t["retraso_s"] if residuo else t[objetivo]


def ajustar(
    ajuste: pd.DataFrame,
    val: pd.DataFrame,
    variables: list[str],
    categorias: list[str],
    objetivo: str,
    params: dict,
) -> dict:
    """Ajusta con `ajuste` y para con `val` (parada temprana). Devuelve el artefacto."""

    def x(t: pd.DataFrame) -> pd.DataFrame:
        return features.matriz(t, variables, categorias)

    r = params["residuo"]
    m = _xgb(params)
    m.fit(
        x(ajuste),
        _y(ajuste, objetivo, r),
        eval_set=[(x(val), _y(val, objetivo, r))],
        verbose=False,
    )
    return {"modelo": m, "columnas": variables, "categorias": categorias, "residuo": r}


def validar(pred: pd.Series, val: pd.DataFrame, objetivo: str) -> dict:
    """Errores en la validación, y la diferencia con el listón por viajes (ADR-018)."""
    real = val[objetivo]
    base = features.predicciones_baseline(val)
    viaje = val.groupby(features.CLAVE_VIAJE, sort=False).ngroup()
    return {
        "dias": sorted(val["fecha_servicio"].dt.strftime("%Y-%m-%d").unique()),
        "modelo": features.errores(pred, real),
        **{k: features.errores(v, real) for k, v in base.items()},
        "modelo_menos_persistencia_tramo": evaluate.diferencia(
            pred - real, base["persistencia_tramo"] - real, viaje
        ),
    }


def entrenar(
    train: pd.DataFrame, variables: list[str], objetivo: str, params: dict
) -> dict:
    """Parada temprana con la validación y reajuste con todo `train`."""
    categorias = features.categorias_linea(train)
    ajuste, val = separar_validacion(train, params["dias_validacion"])
    art = ajustar(ajuste, val, variables, categorias, objetivo, params)
    n = art["modelo"].best_iteration + 1
    validacion = validar(predict.predecir(art, val), val, objetivo)

    final = _xgb(params, n_estimators=n, early_stopping_rounds=None)
    final.fit(
        features.matriz(train, variables, categorias),
        _y(train, objetivo, params["residuo"]),
        verbose=False,
    )
    return {**art, "modelo": final, "n_arboles": n, "validacion": validacion}


def umbral_f1(p: pd.Series, y: pd.Series) -> float:
    """El umbral de probabilidad con el mejor F1 (ADR-025): se avisa si P ≥ τ.

    `precision_recall_curve` devuelve un punto más que umbrales, el de
    sensibilidad cero, que no tiene umbral. Sin positivos no hay τ: se para.
    """
    if not y.astype(bool).any():
        raise ValueError("la validación no tiene positivos: no hay umbral (ADR-025)")
    precision, sensibilidad, umbrales = precision_recall_curve(y, p)
    f1 = 2 * precision * sensibilidad / np.maximum(precision + sensibilidad, 1e-12)
    return float(umbrales[np.argmax(f1[:-1])])


def validar_clasificador(
    p: pd.Series, val: pd.DataFrame, objetivo: str, umbral_s: float, umbral: float
) -> dict:
    """El clasificador y las dos persistencias en la validación (ADR-025). La
    regresión umbralizada se compara en `evaluate.py`, que carga los dos modelos."""
    real = val[f"{objetivo}_bin"].astype(bool)
    base = features.predicciones_baseline(val)
    return {
        "dias": sorted(val["fecha_servicio"].dt.strftime("%Y-%m-%d").unique()),
        "tasa_base": round(float(real.mean()), 4),
        "umbral": umbral,
        "clasificador": evaluate.metricas_binarias(p >= umbral, real, p),
        **{
            k: evaluate.metricas_binarias(base[k] > umbral_s, real, base[k])
            for k in ("persistencia", "persistencia_tramo")
        },
    }


def entrenar_clasificador(
    train: pd.DataFrame,
    variables: list[str],
    objetivo: str,
    umbral_s: float,
    params: dict,
) -> dict:
    """Más de `umbral_s` tarde (ADR-025): parada temprana y τ con la validación,
    y reajuste con todo `train`, como `entrenar`.

    τ se elige con el modelo de parada temprana y se aplica al reajustado: el
    mismo límite que `n_arboles` (declarado en el ADR-025).
    """
    etiqueta = f"{objetivo}_bin"
    categorias = features.categorias_linea(train)
    ajuste, val = separar_validacion(train, params["dias_validacion"])

    def x(t: pd.DataFrame) -> pd.DataFrame:
        return features.matriz(t, variables, categorias)

    m = _xgb(params, XGBClassifier, **CLASIFICADOR)
    m.fit(
        x(ajuste),
        ajuste[etiqueta],
        eval_set=[(x(val), val[etiqueta])],
        verbose=False,
    )
    n = m.best_iteration + 1
    p_val = pd.Series(m.predict_proba(x(val))[:, 1], index=val.index)
    umbral = umbral_f1(p_val, val[etiqueta])

    final = _xgb(
        params,
        XGBClassifier,
        **CLASIFICADOR,
        n_estimators=n,
        early_stopping_rounds=None,
    )
    final.fit(x(train), train[etiqueta], verbose=False)
    return {
        "modelo": final,
        "columnas": variables,
        "categorias": categorias,
        "umbral": umbral,
        "n_arboles": n,
        "validacion": validar_clasificador(p_val, val, objetivo, umbral_s, umbral),
    }


def main(horizonte: int | None = None, trafico: bool = False) -> None:
    """Sin horizonte, el de `params.yaml`; con él, el del barrido (ADR-023).

    Con `trafico`, el mismo modelo con las variables de la capa 192 (ADR-024):
    misma configuración y mismas filas; solo cambian las variables.
    """
    params = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    cfg, p = params["features"], params["train"]
    if trafico:
        cfg = {**cfg, "incluir_trafico": True}
    rutas = features.salidas(horizonte)
    train = pd.read_parquet(rutas["tabla"] / "train.parquet")
    # Se entrena con las filas en las que el modelo se va a usar (ADR-022).
    train = train[features.poblacion(train)].reset_index(drop=True)

    mlflow.set_experiment(EXPERIMENTO)
    with mlflow.start_run() as run:
        art = entrenar(train, columnas(cfg), cfg["objetivo"], p)
        art["mlflow_run_id"] = run.info.run_id
        mlflow.log_params(
            {
                **p,
                "n_arboles": art["n_arboles"],
                **{k: cfg[k] for k in ("train_hasta", "test_desde", "test_hasta")},
                "trafico": cfg["incluir_trafico"],
                "horizonte_paradas": horizonte or cfg["horizonte_paradas"],
            }
        )
        mlflow.log_dict(
            {"variables": art["columnas"], "categorias": art["categorias"]},
            "variables.json",
        )
        plano = pd.json_normalize(art["validacion"], sep=".").iloc[0]
        mlflow.log_metrics(
            {
                f"val.{k}": float(v)
                for k, v in plano.items()
                if isinstance(v, (int, float))
            }
        )
        mlflow.log_dict(art["validacion"], "validacion.json")
        mlflow.xgboost.log_model(art["modelo"], name="modelo")

    ruta = rutas["modelo_trafico" if trafico else "modelo"]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(pickle.dumps(art))
    print(json.dumps({k: art[k] for k in ("n_arboles", "validacion")}, indent=2))


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--horizonte", type=int, default=None, help="paradas (ADR-023)")
    a.add_argument("--trafico", action="store_true", help="con la capa 192 (ADR-024)")
    args = a.parse_args()
    main(args.horizonte, args.trafico)
