"""Qué usa cada modelo: SHAP sobre la prueba, después de su evaluación única.

Es descriptivo: no cambia ninguna cifra prerregistrada (spec del 15/10). Explica
tres modelos por horizonte, la regresión sin tráfico, la regresión con la capa
192 (ADR-024) y el clasificador del ADR-025, con `predict.contribuciones`, que
es el TreeSHAP exacto de XGBoost. La librería `shap` solo dibuja.

La regresión v2 es de residuo (ADR-021): sus contribuciones explican cuánto se
aparta el retraso de la persistencia, no el retraso entero. El clasificador se
explica en log-odds, que es la escala en la que suman.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shap  # noqa: E402
import yaml  # noqa: E402

from project import evaluate, features, predict  # noqa: E402
from project.config import RAIZ  # noqa: E402

# Cada variable, en un solo grupo. Un nombre que acaba en `_` es un prefijo,
# para las ventanas que fije `params.yaml`; el resto son nombres exactos.
GRUPOS = {
    "persistencia": (
        "retraso_s",
        "retraso_lag1_s",
        "retraso_lag2_s",
        "retraso_delta_s",
    ),
    "recorrido": (
        "t_prog_hasta_objetivo_s",
        "dist_objetivo_m",
        "stop_sequence",
        "abscisa_parada_m",
    ),
    "linea_en_servicio": (
        "linea_retraso_",
        "linea_pasos_",
        "bus_anterior_retraso_s",
        "bus_anterior_edad_s",
    ),
    "flota_en_el_tramo": ("tramo_ganado_", "tramo_soporte_"),
    "sesgo_del_horario": ("tramo_sesgo_s",),
    "calendario": ("hora", "dia_semana", "fin_de_semana"),
    "identidad_de_la_linea": ("linea",),
    "trafico_192": tuple(features.TRAFICO),
}
# Nombre en el JSON → clave de `features.salidas`.
MODELOS = {
    "regresion": "modelo",
    "regresion_trafico": "modelo_trafico",
    "clasificador": "clasificador",
}
# TreeSHAP con 700 árboles de profundidad 8 va a unas 300 filas/s: la
# población entera de un horizonte (unas 450.000 filas) serían 25 min por
# modelo. Las medias de |SHAP| se estabilizan mucho antes.
MUESTRA = 20_000
DEPENDENCIAS = ("tramo_sesgo_s", "tramo_ganado_15min", "trafico_congestion_frac")


def grupo(variable: str) -> str:
    """El grupo de `variable`. Si no cae en exactamente uno, error: una variable
    nueva no puede quedarse fuera del resumen sin que nadie se entere."""
    g = [
        k
        for k, nombres in GRUPOS.items()
        if any(
            variable == n or (n.endswith("_") and variable.startswith(n))
            for n in nombres
        )
    ]
    if len(g) != 1:
        raise KeyError(f"{variable} cae en {g}: tiene que caer en un solo grupo")
    return g[0]


def _orden(s: pd.Series) -> dict:
    return {k: round(float(v), 4) for k, v in s.sort_values(ascending=False).items()}


def muestra(t: pd.DataFrame) -> pd.DataFrame:
    """Una muestra fija de la población (ADR-022): la misma en cada ejecución."""
    p = t[features.poblacion(t)]
    return p.sample(min(MUESTRA, len(p)), random_state=evaluate.SEMILLA)


def resumen(contrib: pd.DataFrame, t: pd.DataFrame) -> dict:
    """Media de |SHAP| por variable y por grupo, en la población (ADR-022) y en
    el estrato con sensor (ADR-024), que es donde la capa 192 tiene algo que
    decir. El SHAP de un grupo es la suma de las de sus variables: es aditivo.
    """
    t = t.loc[contrib.index]
    p = features.poblacion(t)
    con_sensor = evaluate.estratos_trafico(t)["_cobertura"] == evaluate.CON_SENSOR
    variables = [c for c in contrib.columns if c != "sesgo"]
    de = {v: grupo(v) for v in variables}

    def en(m: pd.Series) -> dict:
        c = contrib[m]
        if c.empty:
            return {"filas": 0}
        por_grupo = pd.DataFrame(
            {
                g: c[[v for v in variables if de[v] == g]].sum(axis=1)
                for g in sorted(set(de.values()))
            }
        )
        return {
            "filas": int(len(c)),
            "sesgo": round(float(c["sesgo"].mean()), 4),
            "media_abs": _orden(c[variables].abs().mean()),
            "grupos": _orden(por_grupo.abs().mean()),
        }

    return {"poblacion": en(p), "con_sensor": en(p & con_sensor)}


def figuras(
    contrib: pd.DataFrame, t: pd.DataFrame, nombre: str, destino: Path, unidad: str
) -> list[Path]:
    """El resumen (beeswarm) y la dependencia de las variables de tráfico, de
    flota y del sesgo del horario, en las filas de la población de `contrib`,
    con `unidad` en el eje del SHAP. Devuelve los ficheros que ha escrito, y
    solo esos."""
    # shap baraja los puntos con el `np.random` global: sin semilla, cada repro
    # reescribiría los PNG.
    np.random.seed(evaluate.SEMILLA)
    t = t.loc[contrib.index]
    m = t.index[features.poblacion(t)]
    variables = [c for c in contrib.columns if c != "sesgo"]
    x = t.loc[m, variables].copy()
    # El color del beeswarm necesita números; la línea es categórica, sin orden:
    # NaN, que shap pinta en gris.
    x["linea"] = np.nan
    e = shap.Explanation(
        values=contrib.loc[m, variables].to_numpy(),
        base_values=contrib.loc[m, "sesgo"].to_numpy(),
        data=x.to_numpy(dtype=float),
        feature_names=variables,
    )
    destino.mkdir(parents=True, exist_ok=True)
    shap.plots.beeswarm(e, max_display=15, show=False)
    plt.title(nombre)
    plt.xlabel(f"SHAP ({unidad})")
    plt.tight_layout()
    escritas = [destino / f"{nombre}_resumen.png"]
    plt.savefig(escritas[0], dpi=150)
    plt.close("all")
    for v in DEPENDENCIAS:
        if v in variables:
            shap.plots.scatter(e[:, v], show=False)
            plt.title(f"{nombre}: {v}")
            plt.ylabel(f"SHAP de {v} ({unidad})")
            plt.tight_layout()
            escritas.append(destino / f"{nombre}_dependencia_{v}.png")
            plt.savefig(escritas[-1], dpi=150)
            plt.close("all")
    return escritas


def main(horizonte: int | None = None) -> None:
    """Stage `explicar`: los tres modelos del horizonte sobre la prueba. Sin
    horizonte, el de `params.yaml`; con él, el del barrido (ADR-023)."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    h = horizonte or cfg["horizonte_paradas"]
    rutas = features.salidas(horizonte)
    test = pd.read_parquet(rutas["tabla"] / "test.parquet")
    m = muestra(test)
    destino = RAIZ / "figuras" / "shap" / f"h{h}"
    salida = {
        "horizonte_paradas": h,
        "prueba": [cfg["test_desde"], cfg["test_hasta"]],
        "muestra": {
            "filas": len(m),
            "poblacion": int(features.poblacion(test).sum()),
            "semilla": evaluate.SEMILLA,
        },
        "modelos": {},
    }
    for nombre, clave in MODELOS.items():
        art = predict.cargar(rutas[clave])
        c = predict.contribuciones(art, m)
        salida["modelos"][nombre] = {
            "unidad": predict.unidad(art),
            "mlflow_run_id": art["mlflow_run_id"],
            **resumen(c, m),
        }
        escritas = figuras(c, m, nombre, destino, predict.unidad(art))
        with mlflow.start_run(run_id=art["mlflow_run_id"]):
            mlflow.log_dict(salida["modelos"][nombre], "explicacion.json")
            for f in escritas:
                mlflow.log_artifact(str(f), artifact_path="shap")
    rutas["metricas"].mkdir(parents=True, exist_ok=True)
    (rutas["metricas"] / "explicacion.json").write_text(
        json.dumps(salida, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {n: x["poblacion"]["grupos"] for n, x in salida["modelos"].items()},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--horizonte", type=int, default=None, help="paradas (ADR-023)")
    main(a.parse_args().horizonte)
