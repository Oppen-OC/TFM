"""Con cuánta antelación se anticipa el retraso: el barrido de horizontes (ADR-023).

    uv run python -m project.analysis.antelacion

Tres tablas:

1. **Por horizonte**, tal como las escribió `evaluate`: la población de cada
   horizonte, su horizonte previsto mediano y el modelo frente a la
   persistencia más el sesgo del tramo, con los dos intervalos. Las poblaciones
   no son las mismas: cambia la composición de un horizonte a otro.
2. **Cohorte común**: los mismos orígenes (día, viaje, parada) en todos los
   horizontes, con sus modelos. Es la curva de antelación sin cambios de
   composición.
3. **Por horizonte previsto en minutos** dentro de cada horizonte, solo con los
   estratos de al menos `SOPORTE_MIN_FILAS` filas: las colas pequeñas son
   artefactos (regulación en cabecera, revisión del 08/10).

No entrena: lee las tablas y los modelos que dejó DVC. No mira nada que no haya
mirado ya `evaluate`.
"""

from __future__ import annotations

import json
from functools import reduce

import pandas as pd
import yaml

from project import evaluate, features, predict
from project.config import RAIZ
from project.features import salidas

SOPORTE_MIN_FILAS = 2000


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


def _poblacion(horizonte: int | None, objetivo: str) -> pd.DataFrame:
    """La población de prueba de un horizonte con la predicción de su modelo."""
    rutas = salidas(horizonte)
    art = predict.cargar(rutas["modelo"])
    cols = {
        *art["columnas"],
        *features.CLAVE_PASO,
        objetivo,
        "retraso_s",
        "tramo_sesgo_s",
        "horizonte_previsto_s",
        "ultimo_conocido",
    }
    t = pd.read_parquet(rutas["tabla"] / "test.parquet", columns=sorted(cols))
    t = t[features.poblacion(t)]
    return t.assign(_pred=predict.predecir(art, t)).set_index(features.CLAVE_PASO)


def _cohorte(horizontes: list[tuple[int, int | None]], objetivo: str) -> list[dict]:
    datos = {h: _poblacion(arg, objetivo) for h, arg in horizontes}
    comunes = reduce(lambda a, b: a.intersection(b), (d.index for d in datos.values()))
    filas = []
    for h, d in datos.items():
        d = d.loc[comunes]
        real = d[objetivo]
        pt = features.predicciones_baseline(d)["persistencia_tramo"]
        e_m, e_b = d["_pred"] - real, pt - real
        viaje = d.groupby(level=features.CLAVE_VIAJE, sort=False).ngroup()
        dia = pd.Series(d.index.get_level_values("fecha_servicio"), index=d.index)
        pv = evaluate.diferencia(e_m, e_b, viaje)
        pd_ = evaluate.diferencia(e_m, e_b, dia)
        filas.append(
            {
                "h": h,
                "origenes": len(d),
                "horizonte_previsto_p50_s": round(
                    float(d["horizonte_previsto_s"].median()), 1
                ),
                "modelo_mae_s": round(float(e_m.abs().mean()), 2),
                "pt_mae_s": round(float(e_b.abs().mean()), 2),
                "dif_s": pv["mae_s"],
                "ic_viajes": pv["mae_ic95"],
                "ic_dias": pd_["mae_ic95"],
                "relativa_%": round(100 * pv["mae_s"] / float(e_b.abs().mean()), 1),
            }
        )
    return filas


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
            if r["filas"] >= SOPORTE_MIN_FILAS:
                por_min.append({"h": h, "horizonte_previsto": banda, **_fila(r)})
    cohorte = _cohorte(horizontes, cfg["objetivo"])
    resultado = {
        "por_horizonte": por_h,
        "cohorte_comun": cohorte,
        "por_horizonte_previsto": por_min,
        "soporte_min_filas": SOPORTE_MIN_FILAS,
    }
    salida = RAIZ / "auditoria" / "resultados" / "antelacion.json"
    salida.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    with pd.option_context("display.width", 220, "display.max_columns", 20):
        for titulo, filas in (
            ("por horizonte", por_h),
            ("cohorte común", cohorte),
            (f"por horizonte previsto (≥ {SOPORTE_MIN_FILAS} filas)", por_min),
        ):
            print(f"\n{titulo}\n{pd.DataFrame(filas).to_string(index=False)}")
    print(f"\n-> {salida}")


if __name__ == "__main__":
    main()
