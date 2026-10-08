"""Con cuánta antelación se anticipa el retraso: el barrido de horizontes (ADR-023).

    uv run python -m project.analysis.antelacion

Junta lo que ya escribieron `features` y `evaluate` para cada horizonte
(`metrics/` y `metrics/horizontes/h<h>/`): por horizonte, la población, el
horizonte previsto mediano y el modelo frente a la persistencia más el sesgo
del tramo, con los dos intervalos. Debajo, lo mismo por horizonte previsto en
minutos dentro de cada horizonte. No entrena ni evalúa nada: solo lee.
"""

from __future__ import annotations

import json

import pandas as pd
import yaml

from project.config import RAIZ
from project.features import salidas


def _leer(horizonte: int | None) -> tuple[dict, dict]:
    m = salidas(horizonte)["metricas"]
    return (
        json.loads((m / "features.json").read_text(encoding="utf-8")),
        json.loads((m / "eval.json").read_text(encoding="utf-8")),
    )


def _fila(r: dict) -> dict:
    d = r["modelo_menos"]["persistencia_tramo"]
    dd = r["modelo_menos_remuestreando_dias"]["persistencia_tramo"]
    pt = r["persistencia_tramo"]["mae_s"]
    return {
        "filas": r["filas"],
        "horario_mae_s": r["horario"]["mae_s"],
        "persistencia_mae_s": r["persistencia"]["mae_s"],
        "modelo_mae_s": r["modelo"]["mae_s"],
        "pt_mae_s": pt,
        "dif_s": d["mae_s"],
        "ic_viajes": d["mae_ic95"],
        "ic_dias": dd["mae_ic95"],
        "relativa_%": round(100 * d["mae_s"] / pt, 1),
    }


def main() -> None:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    horizontes = [(cfg["horizonte_paradas"], None)] + [
        (h, h) for h in cfg["horizontes_barrido"]
    ]
    por_h, por_min = [], []
    for h, arg in horizontes:
        f, e = _leer(arg)
        disp = f["disponibilidad_test"]
        por_h.append(
            {
                "h": h,
                "horizonte_previsto_p50_s": disp["horizonte_previsto_s_p10_p50_p90"][1],
                "nowcast_%": round(100 * disp["fuera_de_la_poblacion"], 1),
                "arboles": e["modelo"]["n_arboles"],
                **_fila(e["global"]),
            }
        )
        for banda, r in e["por_horizonte"].items():
            por_min.append({"h": h, "horizonte_previsto": banda, **_fila(r)})
    resultado = {"por_horizonte": por_h, "por_horizonte_previsto": por_min}
    salida = RAIZ / "auditoria" / "resultados" / "antelacion.json"
    salida.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(pd.DataFrame(por_h).to_string(index=False))
        print()
        print(pd.DataFrame(por_min).to_string(index=False))
    print(f"\n-> {salida}")


if __name__ == "__main__":
    main()
