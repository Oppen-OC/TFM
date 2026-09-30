"""Stage `features`: de los pasos por parada a la tabla de entrenamiento y prueba.

    uv run python -m project.features            # lo que ejecuta `dvc repro features`

Una fila es el paso de un viaje por la parada i, en el instante t = t_obs(i); el
objetivo es el retraso en su h-ésimo paso siguiente observado (ADR-006), y la
variante binaria, si pasa de `umbral_retraso_s`. Toda variable usa solo lo
observado ANTES de t: con una ventana que incluye t, o un «bus anterior» que no
exige serlo, el modelo ve el futuro y la prueba sale mejor de lo que es.

Fase 1 (bitácora 030): variables del propio viaje, de la línea y del
calendario. Fase 2 (bitácora 032): la flota como sensor del tramo aguas abajo,
con lo que ganaron otros buses, de cualquier línea, al recorrerlo antes de t.
La capa municipal 192 va después.

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


def variables(
    lags_min: tuple[int, ...] = (1, 5, 15), ventanas_flota_min: tuple[int, ...] = ()
) -> list[str]:
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
        *[
            c
            for n in ventanas_flota_min
            for c in (f"tramo_ganado_{n}min", f"tramo_soporte_{n}min")
        ],
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


def _tramo_flota(
    p: pd.DataFrame, ganado: pd.Series, minutos: int, soporte_min: int
) -> tuple[pd.Series, pd.Series]:
    """Mediana del retraso ganado en el tramo por los viajes que lo ACABARON en [t − W, t).

    El tramo es el par (parada de la fila, parada objetivo). Lo comparten todas
    las líneas que paran en las dos, así que la mediana es de la flota, no de la
    línea (docs/10, §3: la congestión es la componente común de tramo × ventana).
    Mediana y no media: un bus averiado es un extremo y no debe fabricar
    congestión. Con menos de `soporte_min` viajes, nulo: no estimable no es cero.
    El propio viaje acaba el tramo después de t y no entra.
    """
    t = p["_t"].to_numpy()
    t_fin = p["_t_fin"].to_numpy()
    valor = ganado.to_numpy()
    mediana = np.full(len(p), np.nan)
    soporte = np.zeros(len(p))
    ancho = np.int64(minutos * 60 * 10**9)
    con_tramo = p["_stop_objetivo"].notna().to_numpy()
    for idx in (
        p[con_tramo].groupby(["stop_id", "_stop_objetivo"], sort=False).indices.values()
    ):
        idx = np.flatnonzero(con_tramo)[idx]
        orden = idx[np.argsort(t_fin[idx], kind="stable")]
        tf, v = t_fin[orden], valor[orden]
        lo = np.searchsorted(tf, t[idx] - ancho, side="left")
        hi = np.searchsorted(tf, t[idx], side="left")
        soporte[idx] = hi - lo
        for fila, a, b in zip(idx, lo, hi):
            if b - a >= soporte_min:
                mediana[fila] = np.median(v[a:b])
    return pd.Series(mediana, index=p.index), pd.Series(soporte, index=p.index)


def construir(
    pasos: pd.DataFrame,
    objetivo: str,
    horizonte: int = 1,
    lags_min: tuple[int, ...] = (1, 5, 15),
    umbral_s: float = 300.0,
    ventanas_flota_min: tuple[int, ...] = (),
    soporte_min: int = 2,
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
    p["_t_fin"] = g["_t"].shift(-horizonte)

    for n in lags_min:
        p[f"linea_retraso_{n}min"], p[f"linea_pasos_{n}min"] = _ventana_linea(p, n)
    for n in ventanas_flota_min:
        p[f"tramo_ganado_{n}min"], p[f"tramo_soporte_{n}min"] = _tramo_flota(
            p, p[objetivo] - p["retraso_s"], n, soporte_min
        )

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
    # Clave, no variable: el tramo (par de paradas) hace falta para separar el
    # sesgo estático del horario de la congestión (bitácora 032).
    p["stop_objetivo_id"] = p["_stop_objetivo"]
    p[objetivo + "_bin"] = (p[objetivo] > umbral_s).astype(int)
    fuera = [c for c in p.columns if c.startswith("_") or c in FUERA_DE_LA_TABLA]
    return p.drop(columns=fuera).reset_index(drop=True)


def partir(tabla: pd.DataFrame, test_desde: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split TEMPORAL por día de servicio (ADR-007): ningún viaje a los dos lados."""
    prueba = tabla["fecha_servicio"] >= pd.Timestamp(test_desde)
    return tabla[~prueba].reset_index(drop=True), tabla[prueba].reset_index(drop=True)


def soporte_por_linea(
    train: pd.DataFrame, test: pd.DataFrame, min_viajes: int = 100, min_dias: int = 3
) -> pd.DataFrame:
    """Qué líneas de la prueba pueden informarse con cifra propia (ADR-018).

    Una fila por línea de `test`. Se cuenta en VIAJES y no en filas: las paradas
    de un mismo viaje están correlacionadas, y 200 filas de cinco viajes no son
    200 observaciones. Un viaje es un par (día de servicio, `viaje_id`), porque
    el `viaje_id` se repite de un día a otro.

    `propia`: al menos `min_viajes` en `min_dias` días de prueba y `min_viajes`
    en entrenamiento. `sin_entrenamiento`: el modelo no ha visto la línea.
    `poco_soporte`: el resto. Ninguna se tira: las dos últimas se informan
    agrupadas.
    """

    def viajes(t: pd.DataFrame) -> pd.Series:
        return t.drop_duplicates(["linea", *CLAVE_VIAJE]).groupby("linea").size()

    s = pd.DataFrame(
        {
            "viajes": viajes(test),
            "dias": test.groupby("linea")["fecha_servicio"].nunique(),
        }
    )
    s["viajes_train"] = viajes(train).reindex(s.index, fill_value=0)
    propia = (
        (s["viajes"] >= min_viajes)
        & (s["dias"] >= min_dias)
        & (s["viajes_train"] >= min_viajes)
    )
    s["grupo"] = np.where(
        s["viajes_train"] == 0,
        "sin_entrenamiento",
        np.where(propia, "propia", "poco_soporte"),
    )
    return s


def baselines(test: pd.DataFrame, objetivo: str, soporte: pd.DataFrame) -> dict:
    """MAE y RMSE de los baselines obligatorios: horario (0) y persistencia.

    Globales, por línea con su soporte, y por grupo de soporte
    (`soporte_por_linea`).
    """

    def errores(pred: pd.Series, real: pd.Series) -> dict:
        e = (pred - real).to_numpy()
        return {
            "mae_s": round(float(np.abs(e).mean()), 2),
            "rmse_s": round(float(np.sqrt((e**2).mean())), 2),
        }

    def los_dos(g: pd.DataFrame) -> dict:
        return {
            "filas": int(len(g)),
            "horario": errores(pd.Series(0.0, index=g.index), g[objetivo]),
            "persistencia": errores(g["retraso_s"], g[objetivo]),
        }

    fuera = {k: v for k, v in los_dos(test).items() if k != "filas"}
    fuera["por_linea"] = {
        str(linea): {
            **los_dos(g),
            "viajes": int(soporte.at[linea, "viajes"]),
            "dias": int(soporte.at[linea, "dias"]),
            "grupo": str(soporte.at[linea, "grupo"]),
        }
        for linea, g in test.groupby("linea")
    }
    grupo = test["linea"].map(soporte["grupo"])
    fuera["por_grupo"] = {str(k): los_dos(g) for k, g in test.groupby(grupo)}
    return fuera


def main() -> None:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    if cfg["incluir_trafico"] or cfg["incluir_meteo"]:
        raise NotImplementedError("capa 192 y meteo: después de la fase 2")
    flota = tuple(cfg["ventanas_flota_min"]) if cfg["incluir_flota"] else ()
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
        ventanas_flota_min=flota,
        soporte_min=cfg["soporte_min"],
    )
    train, test = partir(tabla, cfg["test_desde"])
    soporte = soporte_por_linea(
        train, test, cfg["linea_min_viajes"], cfg["linea_min_dias"]
    )
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
        "baselines_test": baselines(test, cfg["objetivo"], soporte),
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
