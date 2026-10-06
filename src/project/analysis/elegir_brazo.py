"""Elige el brazo del modelo v2 en la validación, con la regla del ADR-021.

    uv run python -m project.analysis.elegir_brazo

Cuatro brazos, pérdida cuadrática o absoluta × objetivo en nivel o residuo,
ajustados con agosto y con parada temprana en la semana del 14-20/09
(`train.ajustar`). Se comparan sobre los mismos viajes con
`evaluate.diferencia`, se elige con `elegir`, y al elegido se le quita `linea`
(ablación, ADR-019). Cada brazo queda en MLflow y el resultado en
`auditoria/resultados/elegir_brazo_v2.json`.

Solo elige: lo que entrena el pipeline es lo que se fije en
`params.yaml → train`. No mira la prueba.
"""

from __future__ import annotations

import json

import mlflow
import pandas as pd
import yaml

from project import evaluate, features, predict, train
from project.config import RAIZ, settings

# nombre: (objective, residuo, cambios respecto a la configuración base: nivel +
# cuadrática con parada por MAE y validación de 7 días; ADR-021, matices)
BRAZOS = {
    "nivel_cuadratica": ("reg:squarederror", False, 0),
    "nivel_absoluta": ("reg:absoluteerror", False, 1),
    "residuo_cuadratica": ("reg:squarederror", True, 1),
    "residuo_absoluta": ("reg:absoluteerror", True, 2),
}


def elegir(brazos: list[dict]) -> dict:
    """El de menor MAE, salvo que uno con menos cambios no se distinga de él.

    `ic_frente_al_mejor` es el intervalo de (MAE del brazo − MAE del mejor)
    sobre los mismos viajes. Entre los que no se distinguen gana el de menos
    cambios respecto a la v1, y a igualdad de cambios, el de menor MAE.
    """
    mejor = min(brazos, key=lambda b: b["mae_s"])
    empatan = [
        b
        for b in brazos
        if b["cambios"] < mejor["cambios"]
        and b["ic_frente_al_mejor"][0] <= 0 <= b["ic_frente_al_mejor"][1]
    ]
    return min([mejor, *empatan], key=lambda b: (b["cambios"], b["mae_s"]))


def main() -> None:
    params = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    cfg, base = params["features"], params["train"]
    obj = cfg["objetivo"]
    tabla = pd.read_parquet(settings.processed_dir / "train.parquet")
    variables = train.columnas(cfg)
    categorias = features.categorias_linea(tabla)
    ajuste, val = train.separar_validacion(tabla, base["dias_validacion"])
    real = val[obj]
    viaje = val.groupby(features.CLAVE_VIAJE, sort=False).ngroup()
    print(f"ajuste {len(ajuste)} filas, validación {len(val)} filas")

    mlflow.set_experiment("elegir_brazo_v2")

    def correr(nombre: str, columnas: list[str], p: dict) -> tuple[pd.Series, dict]:
        with mlflow.start_run(run_name=nombre):
            art = train.ajustar(ajuste, val, columnas, categorias, obj, p)
            pred = predict.predecir(art, val)
            v = train.validar(pred, val, obj)
            n = art["modelo"].best_iteration + 1
            mlflow.log_params({**p, "variables": len(columnas), "n_arboles": n})
            mlflow.log_metric("val.modelo.mae_s", v["modelo"]["mae_s"])
            mlflow.log_dict(v, "validacion.json")
        print(f"{nombre}: {n} árboles, {v}", flush=True)
        return pred - real, {"n_arboles": n, **v}

    errores, filas = {}, []
    for nombre, (objective, residuo, cambios) in BRAZOS.items():
        p = {**base, "objective": objective, "residuo": residuo}
        errores[nombre], v = correr(nombre, variables, p)
        filas.append(
            {
                "nombre": nombre,
                "objective": objective,
                "residuo": residuo,
                "cambios": cambios,
                "mae_s": v["modelo"]["mae_s"],
                "validacion": v,
            }
        )
    mejor = min(filas, key=lambda b: b["mae_s"])["nombre"]
    for f in filas:
        f["ic_frente_al_mejor"] = evaluate.diferencia(
            errores[f["nombre"]], errores[mejor], viaje
        )["mae_ic95"]
    elegido = elegir(filas)

    p = {**base, "objective": elegido["objective"], "residuo": elegido["residuo"]}
    sin_linea = [c for c in variables if c != "linea"]
    e_sin, _ = correr(f"{elegido['nombre']}_sin_linea", sin_linea, p)
    ablacion = evaluate.diferencia(e_sin, errores[elegido["nombre"]], viaje)
    # `linea` se queda solo si quitarla empeora con un intervalo que no toca el 0
    linea_sale = not ablacion["mae_ic95"][0] > 0

    resultado = {
        "brazos": filas,
        "mejor_mae": mejor,
        "elegido": elegido["nombre"],
        "sin_linea_menos_con_linea": ablacion,
        "linea_sale": linea_sale,
    }
    salida = RAIZ / "auditoria" / "resultados" / "elegir_brazo_v2.json"
    salida.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        pd.DataFrame(filas)[
            ["nombre", "cambios", "mae_s", "ic_frente_al_mejor"]
        ].to_string(index=False)
    )
    print(f"elegido: {elegido['nombre']}; sin linea − con linea: {ablacion}")
    print(f"linea sale: {linea_sale}  ->  {salida}")


if __name__ == "__main__":
    main()
