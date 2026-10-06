"""Stage `evaluate`: el modelo contra los tres baselines, en la prueba (ADR-018).

    uv run python -m project.evaluate            # lo que ejecuta `dvc repro evaluate`

Una mejora es una diferencia de error sobre los MISMOS viajes, con su intervalo
del 95 % remuestreando VIAJES: las paradas de un viaje están correlacionadas, y
remuestrear filas da un intervalo estrecho que declara mejoras que no lo son.
Hay mejora si el intervalo no contiene el cero. Se compara con la persistencia
y, sobre todo, con la persistencia más el sesgo del tramo: el listón del
tráfico (ADR-019).

Se informa en conjunto, por grupo de soporte de la línea, por banda de
intervalo programado y por línea con soporte propio. La banda separa dos
calidades de etiqueta: con 8 min o menos, la asignación pliega al viaje
siguiente el 11 % de los viajes y se lleva la mitad de los retrasos de más de
5 min; con más de 15, menos del 2 % (bitácora 038). Las bandas largas son la
referencia limpia.

El intervalo da por buenos los días de la prueba: es un suelo de la
incertidumbre, no su medida (ADR-018, límite conocido).
"""

from __future__ import annotations

import json
from datetime import date

import mlflow
import numpy as np
import pandas as pd
import yaml

from project import features, gtfs, predict
from project.config import RAIZ, settings

REPLICAS = 1000
SEMILLA = 0
BANDAS = [-np.inf, 8 * 60, 15 * 60, 30 * 60, np.inf]
NOMBRES = ["<= 8 min", "8-15 min", "15-30 min", "> 30 min"]
SIN_INTERVALO = "sin_intervalo"


def intervalos(h: gtfs.Horario, dia: date) -> pd.DataFrame:
    """trip_id → intervalo con el anterior y el siguiente de su línea en su 1.ª parada.

    Es el intervalo con el que un bus compite por su viaje programado: con más de
    medio intervalo de retraso, la asignación lo pliega al siguiente (bitácora
    038). Se mide entre los viajes de la misma línea que pasan por esa parada ese
    día; el GTFS de la EMT no trae `direction_id`. Vive aquí y no en `gtfs.py`
    porque aquel es dependencia de `prepare`.
    """
    vj = h.viajes[h.viajes["service_id"].isin(h.servicios(dia))][["trip_id", "linea"]]
    pv = h.paradas_de_viaje.merge(vj, on="trip_id").drop_duplicates(
        ["trip_id", "stop_id"]
    )
    primera = pv.loc[pv.groupby("trip_id")["stop_sequence"].idxmin()]
    # Toda cabecera es también el final de los viajes del otro sentido: contadas
    # sus llegadas, el intervalo sale por la mitad (en el 92 % de los viajes,
    # ≤ 8 min). Compiten los que salen o pasan, no los que terminan.
    ultima = pv.groupby("trip_id")["stop_sequence"].transform("max")
    pv = pv[pv["stop_sequence"] < ultima]
    pv = pv.sort_values(["linea", "stop_id", "t_prog_s"], kind="stable")
    g = pv.groupby(["linea", "stop_id"])["t_prog_s"]
    pv["h_ant_s"] = pv["t_prog_s"] - g.shift(1)
    pv["h_sig_s"] = g.shift(-1) - pv["t_prog_s"]
    return primera[["trip_id", "stop_id", "t_prog_s"]].merge(
        pv[["trip_id", "stop_id", "h_ant_s", "h_sig_s"]], on=["trip_id", "stop_id"]
    )


def banda_intervalo(tabla: pd.DataFrame, horarios: list[gtfs.Horario]) -> pd.Series:
    """Banda del intervalo de cada fila: el menor con el viaje anterior y el
    siguiente, en el horario que manda ese día (`gtfs.elegir_horario`).

    Se une por (día de servicio, `trip_id`), nunca por posición (trampa 012). Sin
    intervalo —viaje único en su parada, o que no está en el horario— la fila va
    a `sin_intervalo`: se informa aparte, no se tira.
    """
    partes = []
    for dia in pd.to_datetime(tabla["fecha_servicio"].unique()):
        h, _ = gtfs.elegir_horario(horarios, dia.date())
        if h is not None:
            partes.append(intervalos(h, dia.date()).assign(fecha_servicio=dia))
    iv = pd.concat(partes).set_index(["fecha_servicio", "trip_id"])
    h = iv[["h_ant_s", "h_sig_s"]].min(axis=1)
    h = h.reindex(pd.MultiIndex.from_frame(tabla[["fecha_servicio", "trip_id"]]))
    banda = pd.cut(h.to_numpy(), BANDAS, labels=NOMBRES).astype(object)
    return pd.Series(banda, index=tabla.index).fillna(SIN_INTERVALO)


def diferencia(
    e_a: pd.Series, e_b: pd.Series, viaje: pd.Series, replicas: int = REPLICAS
) -> dict:
    """MAE y RMSE de `e_a` menos los de `e_b` (negativo: `a` acierta más), con
    el intervalo del 95 % remuestreando VIAJES, no filas (ADR-018).

    Los tres van alineados por índice. Se remuestrean las sumas por viaje, así
    que un viaje largo pesa por sus filas, como en la cifra puntual.
    """
    sumas = (
        pd.DataFrame(
            {
                "abs_a": e_a.abs(),
                "abs_b": e_b.abs(),
                "cuad_a": e_a**2,
                "cuad_b": e_b**2,
                "n": 1.0,
            }
        )
        .groupby(viaje)
        .sum()
        .to_numpy()
    )

    def medidas(s: np.ndarray) -> np.ndarray:
        abs_a, abs_b, cuad_a, cuad_b, n = s.T
        return np.array(
            [(abs_a - abs_b) / n, np.sqrt(cuad_a / n) - np.sqrt(cuad_b / n)]
        )

    rng = np.random.default_rng(SEMILLA)
    k = len(sumas)
    rep = np.array(
        [medidas(sumas[rng.integers(0, k, k)].sum(0)) for _ in range(replicas)]
    )
    lo, hi = np.percentile(rep, [2.5, 97.5], axis=0)
    punto = medidas(sumas.sum(0))
    r = lambda v: round(float(v), 2)  # noqa: E731
    return {
        "mae_s": r(punto[0]),
        "mae_ic95": [r(lo[0]), r(hi[0])],
        "rmse_s": r(punto[1]),
        "rmse_ic95": [r(lo[1]), r(hi[1])],
    }


def resumen(t: pd.DataFrame, objetivo: str) -> dict:
    """Errores del modelo y de los baselines, y lo que el modelo gana a las dos
    persistencias. `t` trae `_prediccion` y `_viaje`."""
    real = t[objetivo]
    base = features.predicciones_baseline(t)
    e_modelo = t["_prediccion"] - real
    return {
        "filas": int(len(t)),
        "viajes": int(t["_viaje"].nunique()),
        "modelo": features.errores(t["_prediccion"], real),
        **{k: features.errores(v, real) for k, v in base.items()},
        "modelo_menos": {
            k: diferencia(e_modelo, base[k] - real, t["_viaje"])
            for k in ("persistencia", "persistencia_tramo")
        },
    }


def main() -> None:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    obj = cfg["objetivo"]
    test = pd.read_parquet(settings.processed_dir / "test.parquet")
    train = pd.read_parquet(
        settings.processed_dir / "train.parquet",
        columns=["linea", *features.CLAVE_VIAJE],
    )
    soporte = features.soporte_por_linea(
        train, test, cfg["linea_min_viajes"], cfg["linea_min_dias"]
    )
    art = predict.cargar()
    horarios = [gtfs.cargar_horario(r) for r in gtfs.versiones(settings.gtfs_dir)]
    t = test.assign(
        _prediccion=predict.predecir(art, test),
        _viaje=test.groupby(features.CLAVE_VIAJE, sort=False).ngroup(),
        _grupo=test["linea"].map(soporte["grupo"]),
        _banda=pd.Categorical(
            banda_intervalo(test, horarios), categories=[*NOMBRES, SIN_INTERVALO]
        ),
    )

    def por(t: pd.DataFrame, col: str) -> dict:
        return {str(k): resumen(g, obj) for k, g in t.groupby(col, observed=True)}

    metricas = {
        "modelo": {k: art[k] for k in ("n_arboles", "mlflow_run_id")},
        "remuestreo": {"unidad": "viaje", "replicas": REPLICAS, "semilla": SEMILLA},
        "global": resumen(t, obj),
        "por_grupo": por(t, "_grupo"),
        "por_banda": por(t, "_banda"),
        "por_linea": por(t[t["_grupo"] == "propia"], "linea"),
    }
    salida = RAIZ / "metrics" / "eval.json"
    salida.write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    plano = pd.json_normalize(metricas["global"], sep=".").iloc[0]
    with mlflow.start_run(run_id=art["mlflow_run_id"]):
        mlflow.log_metrics(
            {
                f"test.{k}": float(v)
                for k, v in plano.items()
                if isinstance(v, (int, float))
            }
        )
        mlflow.log_dict(metricas, "eval.json")
    print(json.dumps(metricas["global"], indent=2))
    print({k: v["modelo_menos"] for k, v in metricas["por_banda"].items()})


if __name__ == "__main__":
    main()
