"""Robustez del modelo v2 en la validación (bitácora 043, abiertos).

    uv run python -m project.analysis.robustez_v2

Sobre el brazo fijado en `params.yaml → train`, ajustado con agosto y con parada
temprana en la semana del 14-20/09 (`train.ajustar`), como en el selector:

1. **Ablación de la flota.** Sin `tramo_ganado_*`/`tramo_soporte_*` y, además,
   sin las ventanas de la línea (`linea_retraso_*`, `linea_pasos_*`). Cada
   modelo reducido se compara con el completo sobre los mismos viajes. Mide
   cuánto aporta cada bloque; no cambia el modelo.
2. **Líneas no vistas.** En las líneas de la validación que el ajuste (agosto)
   no tiene, el modelo frente a `persistencia_tramo`. Regla, fijada antes de
   ejecutarlo: si el modelo es peor con un intervalo que no toca el cero,
   `predict` usará `persistencia_tramo` para las líneas que el entrenamiento no
   vio. Si no, se queda como está.

Solo validación: no lee la prueba. Resultado en
`auditoria/resultados/robustez_v2.json` y un run de MLflow por modelo.
"""

from __future__ import annotations

import json

import mlflow
import pandas as pd
import yaml

from project import evaluate, features, predict, train
from project.config import RAIZ, settings

FLOTA = ("tramo_ganado_", "tramo_soporte_")
VENTANAS_LINEA = ("linea_retraso_", "linea_pasos_")


def sin(columnas: list[str], prefijos: tuple[str, ...]) -> list[str]:
    return [c for c in columnas if not c.startswith(prefijos)]


def main() -> None:
    params = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    cfg, p = params["features"], params["train"]
    obj = cfg["objetivo"]
    tabla = pd.read_parquet(settings.processed_dir / "train.parquet")
    completas = train.columnas(cfg)
    categorias = features.categorias_linea(tabla)
    ajuste, val = train.separar_validacion(tabla, p["dias_validacion"])
    real = val[obj]
    viaje = val.groupby(features.CLAVE_VIAJE, sort=False).ngroup()
    modelos = {
        "completo": completas,
        "sin_flota": sin(completas, FLOTA),
        "sin_flota_ni_ventanas_linea": sin(completas, FLOTA + VENTANAS_LINEA),
    }

    mlflow.set_experiment("robustez_v2")
    errores = {}
    for nombre, columnas in modelos.items():
        with mlflow.start_run(run_name=nombre):
            art = train.ajustar(ajuste, val, columnas, categorias, obj, p)
            pred = predict.predecir(art, val)
            mlflow.log_params({**p, "variables": len(columnas)})
            mlflow.log_metric("val.modelo.mae_s", features.errores(pred, real)["mae_s"])
        errores[nombre] = pred - real
        print(f"{nombre}: {art['modelo'].best_iteration + 1} árboles", flush=True)

    ablacion = {
        nombre: {
            "variables_quitadas": sorted(set(completas) - set(modelos[nombre])),
            "menos_completo": evaluate.diferencia(
                errores[nombre], errores["completo"], viaje
            ),
        }
        for nombre in modelos
        if nombre != "completo"
    }

    nuevas = sorted(set(val["linea"].astype(str)) - set(ajuste["linea"].astype(str)))
    m = val["linea"].astype(str).isin(nuevas)
    pt = features.predicciones_baseline(val)["persistencia_tramo"]
    no_vistas = {
        "lineas": nuevas,
        "filas": int(m.sum()),
        "viajes": int(viaje[m].nunique()),
        "modelo": features.errores(errores["completo"][m] + real[m], real[m]),
        "persistencia_tramo": features.errores(pt[m], real[m]),
        "modelo_menos_persistencia_tramo": evaluate.diferencia(
            errores["completo"][m], pt[m] - real[m], viaje[m]
        ),
    }
    lo = no_vistas["modelo_menos_persistencia_tramo"]["mae_ic95"][0]
    no_vistas["respaldo"] = bool(lo > 0)  # peor, y el intervalo no toca el cero

    resultado = {"ablacion": ablacion, "lineas_no_vistas": no_vistas}
    salida = RAIZ / "auditoria" / "resultados" / "robustez_v2.json"
    salida.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(resultado, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
