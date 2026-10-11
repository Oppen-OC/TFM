"""Diagnóstico de la capa 192 en la validación de la fase 2 (ADR-024, fase 1).

    uv run python -m project.analysis.trafico_validacion

Usa el mismo corte que tendrá la fase 2: todo lo capturado hasta el 04/10, con
ajuste hasta el 27/09 y validación del 28/09 al 04/10 (siete días, de lunes a
domingo, ADR-021). Las tablas de prueba de hoy (21/09-04/10) pasan aquí a ser
entrenamiento y validación: la prueba que decide es la del 07-19/10, que
todavía no existe.

Para cada horizonte del barrido, el mismo modelo (configuración del ADR-021)
con y sin las variables de tráfico, comparado sobre las mismas filas de la
población, con los intervalos por viajes y por días: en conjunto, según cuánto
del recorrido tiene sensor y según lo que la capa decía al predecir. Con esto
se fijó el estrato con sensor antes de mirar la prueba (bitácora 048). Solo
diagnostica: no fija nada del pipeline.

Los estratos y la comparación son los de `evaluate.py`: la fase 2 los usa tal cual.
"""

from __future__ import annotations

import json

import mlflow
import pandas as pd
import yaml

from project import evaluate, features, predict, train
from project.config import RAIZ

FIN_AJUSTE = pd.Timestamp("2026-09-28")  # validación: 28/09-04/10
FIN_DATOS = pd.Timestamp("2026-10-05")
HORIZONTES = (2, 3, 5, 10)


def _tabla(horizonte: int) -> pd.DataFrame:
    r = features.salidas(horizonte)
    t = pd.concat(
        [pd.read_parquet(r["tabla"] / f) for f in ("train.parquet", "test.parquet")],
        ignore_index=True,
    )
    t = t[(t["fecha_servicio"] < FIN_DATOS) & features.poblacion(t)]
    return evaluate.estratos_trafico(t).reset_index(drop=True)


def main() -> None:
    params = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    cfg, p = params["features"], params["train"]
    obj = cfg["objetivo"]
    sin = train.columnas({**cfg, "incluir_trafico": False})
    con = train.columnas({**cfg, "incluir_trafico": True})
    mlflow.set_experiment("trafico_validacion")
    resultado = {}
    for h in HORIZONTES:
        t = _tabla(h)
        ajuste, val = (
            t[t["fecha_servicio"] < FIN_AJUSTE],
            t[t["fecha_servicio"] >= FIN_AJUSTE],
        )
        categorias = features.categorias_linea(ajuste)
        errores = {}
        for nombre, columnas in (("sin", sin), ("con", con)):
            with mlflow.start_run(run_name=f"h{h}_{nombre}_trafico"):
                art = train.ajustar(ajuste, val, columnas, categorias, obj, p)
                errores[nombre] = predict.predecir(art, val) - val[obj]
                mlflow.log_params({**p, "horizonte": h, "variables": len(columnas)})
                mlflow.log_metric("val.mae_s", float(errores[nombre].abs().mean()))
        hay_congestion = lambda d: float((d["trafico_congestion_frac"] > 0).mean())  # noqa: E731
        resultado[f"h{h}"] = {
            "filas_ajuste": int(len(ajuste)),
            "filas_validacion": int(len(val)),
            "con_congestion_observada": {
                "ajuste": round(hay_congestion(ajuste), 4),
                "validacion": round(hay_congestion(val), 4),
            },
            "cobertura_validacion": val["_cobertura"]
            .value_counts(normalize=True)
            .round(4)
            .to_dict(),
            "global": evaluate.con_menos_sin(errores["con"], errores["sin"], val),
            "por_cobertura": {
                str(k): evaluate.con_menos_sin(
                    errores["con"][g.index], errores["sin"][g.index], g
                )
                for k, g in val.groupby("_cobertura", observed=True)
            },
            "por_estado_observado": {
                str(k): evaluate.con_menos_sin(
                    errores["con"][g.index], errores["sin"][g.index], g
                )
                for k, g in val.groupby("_estado")
            },
        }
        print(f"h{h}", json.dumps(resultado[f"h{h}"], ensure_ascii=False), flush=True)
    salida = RAIZ / "auditoria" / "resultados" / "trafico_validacion.json"
    salida.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"-> {salida}")


if __name__ == "__main__":
    main()
