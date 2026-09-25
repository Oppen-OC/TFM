"""Stage `features`: de los pasos por parada a la tabla de entrenamiento y prueba.

    uv run python -m project.features            # lo que ejecuta `dvc repro features`

Una fila es el paso de un viaje por la parada i, en el instante t = t_obs(i); el
objetivo es el retraso en su h-ésimo paso siguiente observado (ADR-006), y la
variante binaria, si pasa de `umbral_retraso_s`. Toda variable usa solo lo
observado ANTES de t: con una ventana que incluye t, o un «bus anterior» que no
exige serlo, el modelo ve el futuro y la prueba sale mejor de lo que es.

Fase 1, sin tráfico (bitácora 030): variables del propio viaje, de la línea y
del calendario. El tráfico aguas abajo, que es la pregunta del TFM, va aparte.

Esta transformación se comparte entre entrenamiento e inferencia: vive aquí y
solo aquí (train/serve skew).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import yaml

from project.config import RAIZ, settings

CLAVE_VIAJE = ["fecha_servicio", "viaje_id"]
# Diagnósticos de la asignación del viaje que trae `pasos`. `desfase_s` es la
# mediana del desfase en las primeras `paradas_referencia` paradas: en la parada
# 1 o 2 incluye el retraso de paradas FUTURAS. No entran en la tabla.
FUERA_DE_LA_TABLA = ["desfase_s", "margen_s", "coste_s"]


def variables(lags_min: tuple[int, ...] = (1, 5, 15)) -> list[str]:
    """Las columnas que ve el modelo, en entrenamiento y en inferencia.

    Solo estas: el resto de la tabla son claves y el objetivo. Que `train.py` y
    `predict.py` lean esta lista, y no la escriban, es lo que evita el train/serve
    skew.
    """
    return [
        "retraso_s",
        "retraso_lag1_s",
        "retraso_lag2_s",
        "retraso_delta_s",
        "t_prog_hasta_objetivo_s",
        "dist_objetivo_m",
        "stop_sequence",
        "abscisa_parada_m",
        *[
            c
            for n in lags_min
            for c in (f"linea_retraso_{n}min", f"linea_pasos_{n}min")
        ],
        "bus_anterior_retraso_s",
        "bus_anterior_edad_s",
        "hora",
        "dia_semana",
        "fin_de_semana",
        "linea",
    ]


def _ventana_linea(p: pd.DataFrame, minutos: int) -> tuple[pd.Series, pd.Series]:
    """Retraso medio y número de pasos de OTROS viajes de la línea en [t − N, t)."""
    t = p["_t"].to_numpy()
    r = p["retraso_s"].to_numpy()
    suma = np.zeros(len(p))
    cuenta = np.zeros(len(p))
    ancho = np.int64(minutos * 60 * 10**9)
    for claves, signo in ((["linea"], 1), (["linea", *CLAVE_VIAJE], -1)):
        for idx in p.groupby(claves, sort=False).indices.values():
            orden = idx[np.argsort(t[idx], kind="stable")]
            ts = t[orden]
            acum = np.concatenate([[0.0], np.cumsum(r[orden])])
            # [t − N, t): el paso en el mismo instante t ya no cuenta
            lo = np.searchsorted(ts, ts - ancho, side="left")
            hi = np.searchsorted(ts, ts, side="left")
            suma[orden] += signo * (acum[hi] - acum[lo])
            cuenta[orden] += signo * (hi - lo)
    media = np.divide(suma, cuenta, out=np.full(len(p), np.nan), where=cuenta > 0)
    return pd.Series(media, index=p.index), pd.Series(cuenta, index=p.index)


def construir(
    pasos: pd.DataFrame,
    objetivo: str,
    horizonte: int = 1,
    lags_min: tuple[int, ...] = (1, 5, 15),
    umbral_s: float = 300.0,
) -> pd.DataFrame:
    """La tabla: una fila por paso con objetivo, sus variables y sus claves."""
    # Las particiones de `pasos` no traen todas el mismo tipo de fecha (issue #2):
    # unas `datetime64`, otras `date`; concatenadas, ni siquiera se pueden ordenar.
    p = pasos.assign(fecha_servicio=pd.to_datetime(pasos["fecha_servicio"]))
    p = p.sort_values([*CLAVE_VIAJE, "stop_sequence"], kind="stable").reset_index(
        drop=True
    )
    p["_t"] = p["t_obs_utc"].dt.tz_convert("UTC").astype("int64")
    g = p.groupby(CLAVE_VIAJE, sort=False)

    p[objetivo] = g["retraso_s"].shift(-horizonte)
    p["retraso_lag1_s"] = g["retraso_s"].shift(1)
    p["retraso_lag2_s"] = g["retraso_s"].shift(2)
    p["retraso_delta_s"] = p["retraso_s"] - p["retraso_lag1_s"]
    p["t_prog_hasta_objetivo_s"] = g["t_prog_s"].shift(-horizonte) - p["t_prog_s"]
    p["dist_objetivo_m"] = (
        g["abscisa_parada_m"].shift(-horizonte) - p["abscisa_parada_m"]
    )
    p["_stop_objetivo"] = g["stop_id"].shift(-horizonte)

    for n in lags_min:
        p[f"linea_retraso_{n}min"], p[f"linea_pasos_{n}min"] = _ventana_linea(p, n)

    # El último viaje de la línea que pasó por la parada objetivo ANTES de t. El
    # propio viaje no puede: aún no ha llegado a ella.
    previos = (
        p[["linea", "stop_id", "_t", "retraso_s"]]
        .rename(
            columns={
                "stop_id": "_stop_objetivo",
                "_t": "_t_prev",
                "retraso_s": "_r_prev",
            }
        )
        .sort_values("_t_prev", kind="stable")
    )
    con_obj = p[p["_stop_objetivo"].notna()].sort_values("_t", kind="stable")
    bus = pd.merge_asof(
        con_obj[["_t", "linea", "_stop_objetivo"]].reset_index(),
        previos,
        left_on="_t",
        right_on="_t_prev",
        by=["linea", "_stop_objetivo"],
        direction="backward",
        allow_exact_matches=False,
    ).set_index("index")
    p["bus_anterior_retraso_s"] = bus["_r_prev"]
    p["bus_anterior_edad_s"] = (bus["_t"] - bus["_t_prev"]) / 1e9

    local = p["t_obs_utc"].dt.tz_convert(settings.tz_local)
    p["hora"] = local.dt.hour + local.dt.minute / 60
    p["dia_semana"] = local.dt.dayofweek
    p["fin_de_semana"] = (p["dia_semana"] >= 5).astype(int)

    p = p[p[objetivo].notna()].copy()
    p[objetivo + "_bin"] = (p[objetivo] > umbral_s).astype(int)
    fuera = [c for c in p.columns if c.startswith("_") or c in FUERA_DE_LA_TABLA]
    return p.drop(columns=fuera).reset_index(drop=True)


def partir(tabla: pd.DataFrame, test_desde: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split TEMPORAL por día de servicio (ADR-007): ningún viaje a los dos lados."""
    prueba = tabla["fecha_servicio"] >= pd.Timestamp(test_desde)
    return tabla[~prueba].reset_index(drop=True), tabla[prueba].reset_index(drop=True)


def baselines(test: pd.DataFrame, objetivo: str) -> dict:
    """MAE y RMSE de los baselines obligatorios: horario (0) y persistencia."""

    def errores(pred: pd.Series, real: pd.Series) -> dict:
        e = (pred - real).to_numpy()
        return {
            "mae_s": round(float(np.abs(e).mean()), 2),
            "rmse_s": round(float(np.sqrt((e**2).mean())), 2),
        }

    real = test[objetivo]
    fuera = {
        "horario": errores(pd.Series(0.0, index=test.index), real),
        "persistencia": errores(test["retraso_s"], real),
    }
    fuera["por_linea"] = {
        str(linea): {
            "filas": int(len(g)),
            "horario": errores(pd.Series(0.0, index=g.index), g[objetivo]),
            "persistencia": errores(g["retraso_s"], g[objetivo]),
        }
        for linea, g in test.groupby("linea")
    }
    return fuera


def main() -> None:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    if cfg["incluir_trafico"] or cfg["incluir_meteo"]:
        raise NotImplementedError("tráfico y meteo son la fase 2 (bitácora 030)")
    pasos = pd.concat(
        pd.read_parquet(f)
        for f in sorted((settings.interim_dir / "pasos").rglob("*.parquet"))
    )
    tabla = construir(
        pasos,
        objetivo=cfg["objetivo"],
        horizonte=cfg["horizonte_paradas"],
        lags_min=tuple(cfg["lags_min"]),
        umbral_s=cfg["umbral_retraso_s"],
    )
    train, test = partir(tabla, cfg["test_desde"])
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    train.to_parquet(
        settings.processed_dir / "train.parquet", index=False, compression="zstd"
    )
    test.to_parquet(
        settings.processed_dir / "test.parquet", index=False, compression="zstd"
    )

    metricas = {
        "filas": {"train": len(train), "test": len(test)},
        "dias": {
            "train": int(train["fecha_servicio"].nunique()),
            "test": int(test["fecha_servicio"].nunique()),
        },
        "positivos": {
            "train": round(float(train[cfg["objetivo"] + "_bin"].mean()), 4),
            "test": round(float(test[cfg["objetivo"] + "_bin"].mean()), 4),
        },
        "baselines_test": baselines(test, cfg["objetivo"]),
    }
    salida = RAIZ / "metrics" / "features.json"
    salida.write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in metricas.items() if k != "baselines_test"}, indent=2
        )
    )
    print({k: v for k, v in metricas["baselines_test"].items() if k != "por_linea"})


if __name__ == "__main__":
    main()
