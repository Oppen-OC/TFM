"""Stage `features`: de los pasos por parada a la tabla de entrenamiento y prueba.

    uv run python -m project.features            # lo que ejecuta `dvc repro features`

Una fila es el paso de un viaje por la parada i; el objetivo es el retraso en
la parada `h` posiciones más allá en el horario, si se observó (ADR-006), y la
variante binaria, si pasa de `umbral_retraso_s`. El «ahora» de la fila no es `t_obs(i)`, cuando ocurrió
el paso, sino `t_disp(i)`, cuando se SUPO: la llegada del sondeo que lo
confirma, unos 37 s después de mediana (trampa 017). Toda variable usa solo lo
que había LLEGADO antes de ese instante. Con una ventana que incluye t, un «bus
anterior» que no exige serlo o un paso que ocurrió pero aún no había llegado,
el modelo ve el futuro y la prueba sale mejor de lo que es.

Fase 1 (bitácora 030): variables del propio viaje, de la línea y del
calendario. Fase 2 (bitácora 032): la flota como sensor del tramo aguas abajo,
con lo que ganaron otros buses, de cualquier línea, al recorrerlo antes de t.
Sesgo del tramo (bitácora 039): lo que el horario de cada línea se equivoca, de
forma fija, en cada par de paradas. La capa municipal 192 va después.

Esta transformación se comparte entre entrenamiento e inferencia: vive aquí y
solo aquí (train/serve skew).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

from project.config import RAIZ, settings

CLAVE_VIAJE = ["fecha_servicio", "viaje_id"]
CLAVE_PASO = [*CLAVE_VIAJE, "stop_sequence"]
# Diagnósticos de la asignación del viaje que trae `pasos`. `desfase_s` es la
# mediana del desfase en las primeras `paradas_referencia` paradas: en la parada
# 1 o 2 incluye el retraso de paradas FUTURAS. No entran en la tabla.
FUERA_DE_LA_TABLA = ["desfase_s", "margen_s", "coste_s"]
# El sesgo es del horario: de su versión, de la línea y del par de paradas.
CLAVE_TRAMO = ["feed_version", "linea", "stop_id", "_stop_objetivo"]


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
        # Sin `tramo_sesgo_soporte`: crece con el calendario y la prueba lo ve
        # fuera del rango del entrenamiento (bitácora 041, ADR-021).
        "tramo_sesgo_s",
        "hora",
        "dia_semana",
        "fin_de_semana",
        "linea",
    ]


def categorias_linea(train: pd.DataFrame) -> list[str]:
    """Las líneas del entrenamiento: se guardan con el modelo y no se recalculan."""
    return sorted(train["linea"].astype(str).unique())


def matriz(
    tabla: pd.DataFrame, columnas: list[str], categorias: list[str]
) -> pd.DataFrame:
    """Las variables del modelo, con `linea` categórica sobre `categorias`.

    pandas numera las categorías por las que ve en cada tabla: sin fijarlas, la
    misma línea tiene otro código en la prueba. XGBoost (≥ 3.1) guarda las del
    entrenamiento y recodifica por valor, así que una línea que vio se lee bien
    igual; la que no vio, en cambio, la rechaza con error. Fijadas, esa queda
    nula y se predice como dato faltante, y la matriz no depende de que la
    librería recodifique (bitácora 040).
    """
    x = tabla[columnas].copy()
    if "linea" in x:
        x["linea"] = pd.Categorical(x["linea"].astype(str), categories=categorias)
    return x


def _ventana_linea(p: pd.DataFrame, minutos: int) -> tuple[pd.Series, pd.Series]:
    """Retraso medio y número de pasos de OTROS viajes de la línea que LLEGARON en
    [ahora − N, ahora), con el ahora y las llegadas en `_td` (trampa 017)."""
    t = p["_td"].to_numpy()
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
    t = p["_td"].to_numpy()  # el ahora de la fila
    t_fin = p["_td_fin"].to_numpy()  # cuándo se supo que el otro acabó el tramo
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


def _sesgo_tramo(
    p: pd.DataFrame, ganado: pd.Series, soporte_min: int
) -> tuple[pd.Series, pd.Series]:
    """Mediana de lo que gana la persistencia en el tramo, con lo acabado antes del día.

    Es el sesgo estático del horario: el GTFS da mal el tiempo entre ciertas
    paradas, y siempre hacia el mismo lado (bitácora 032). Por día de servicio,
    solo cuenta lo que ACABÓ el tramo antes de la primera observación de ese día:
    ni el propio día, que en inferencia aún no tiene mediana, ni los nocturnos de
    la víspera que terminan ya dentro de él. Clave `CLAVE_TRAMO`: el sesgo de un
    horario no es el de la versión siguiente. Con menos de `soporte_min`, nulo.
    """
    mediana = np.full(len(p), np.nan)
    soporte = np.zeros(len(p))
    hecho = p["_stop_objetivo"].notna() & ganado.notna()
    for filas in p.groupby("fecha_servicio", sort=True).indices.values():
        antes = hecho & (p["_td_fin"] < p["_td"].iloc[filas].min())
        if not antes.any():
            continue
        st = (
            ganado[antes]
            .groupby([p.loc[antes, c] for c in CLAVE_TRAMO], sort=False)
            .agg(["median", "size"])
        )
        r = st.reindex(pd.MultiIndex.from_frame(p.iloc[filas][CLAVE_TRAMO]))
        n = r["size"].fillna(0).to_numpy()
        soporte[filas] = n
        mediana[filas] = np.where(n >= soporte_min, r["median"].to_numpy(), np.nan)
    return pd.Series(mediana, index=p.index), pd.Series(soporte, index=p.index)


def _ns(t: pd.Series) -> pd.Series:
    """Instantes en UTC con resolución de nanosegundos: los Parquet traen µs o ns."""
    return t.dt.tz_convert("UTC").astype("datetime64[ns, UTC]")


def instante_disponible(
    pasos: pd.DataFrame,
    posiciones: pd.DataFrame,
    llegadas: pd.Series,
    max_hueco_s: float,
    paradas_referencia: int,
) -> pd.Series:
    """Cuándo se SABE el retraso de cada paso (trampa 017), con el índice de `pasos`.

    Dos esperas, y manda la más larga:

    1. **El paso.** `etiquetado.cruces` interpola la salida de la parada con la
       primera posición tras el cruce (k1) y corrige la velocidad con la
       siguiente (k1+1) si llega en menos de `max_hueco_s`. Se sabe cuando llega
       a nuestro disco el sondeo de la última que usa (`llegadas`: `snapshot_id`
       → `ts_ingest_utc`, con la latencia de la fuente dentro). La parada final
       se extrapola tras la última posición: se sabe con ella, pero nunca antes
       de que ocurra.
    2. **La asignación.** El retraso necesita el viaje programado, que se elige
       con los `paradas_referencia` primeros pasos del viaje: ninguno se sabe
       antes que el último de ellos.

    `posiciones` son las fiables del viaje, las mismas que mira `cruces`. NaT si
    el viaje no tiene ninguna.
    """
    clave = ["_dia", "viaje_id"]

    def tabla(df: pd.DataFrame, t: str) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "_dia": pd.to_datetime(df["fecha_servicio"]).astype("datetime64[ns]"),
                "viaje_id": df["viaje_id"],
                "_t": _ns(df[t]),
            }
        ).reset_index(drop=True)

    pa = tabla(pasos, "t_obs_utc").assign(_seq=pasos["stop_sequence"].to_numpy())
    pa = pa.rename_axis("_fila").reset_index()
    po = tabla(posiciones, "ts_utc").assign(
        _llega=_ns(posiciones["snapshot_id"].map(llegadas)).to_numpy()
    )
    po = po.sort_values([*clave, "_t"], kind="stable")
    g = po.groupby(clave, sort=False)
    po["_tk"], po["_t2"], po["_llega2"] = (
        po["_t"],
        g["_t"].shift(-1),
        g["_llega"].shift(-1),
    )

    pa, po = pa.sort_values("_t", kind="stable"), po.sort_values("_t", kind="stable")
    tras = pd.merge_asof(
        pa, po, on="_t", by=clave, direction="forward", allow_exact_matches=False
    )
    ultima = pd.merge_asof(
        pa, po[[*clave, "_t", "_llega"]], on="_t", by=clave, direction="backward"
    )
    dt2 = (tras["_t2"] - tras["_tk"]).dt.total_seconds()
    usa_siguiente = (dt2 > 0) & (dt2 <= max_hueco_s)
    # La más tardía de las dos: una posición atrasada puede llegar en un sondeo
    # posterior al de la siguiente (trampa 013).
    llega2 = tras["_llega2"].where(usa_siguiente)
    llega = tras["_llega"].where(llega2.isna() | (tras["_llega"] >= llega2), llega2)
    llega = llega.fillna(ultima["_llega"])
    paso = llega.where(llega.isna() | (llega >= tras["_t"]), tras["_t"])

    r = tras[["_fila", *clave, "_seq"]].assign(_paso=paso)
    r = r.sort_values([*clave, "_seq"], kind="stable")
    vg = r.groupby(clave, sort=False)
    k = np.minimum(paradas_referencia, vg["_paso"].transform("size")) - 1
    # El más tardío de los primeros pasos, no el último: nada garantiza que se
    # sepan en orden.
    r["_ref"] = vg["_paso"].cummax()
    ref = r[vg.cumcount() == k][[*clave, "_ref"]]
    r = r.drop(columns="_ref")
    r = r.merge(ref, on=clave, how="left")
    t = r["_paso"].where(r["_paso"] >= r["_ref"], r["_ref"])
    # Se vuelve al orden de `pasos` por `_fila`: merge_asof y merge reordenan.
    return pd.Series(t.array, index=r["_fila"]).sort_index().set_axis(pasos.index)


def poblacion(tabla: pd.DataFrame) -> pd.Series:
    """Las filas en las que la predicción todavía puede servir (ADR-022).

    Con lo que se sabe al predecir, al bus le queda tiempo para llegar a la
    parada objetivo. Las demás son *nowcast*: se informan aparte.
    """
    return tabla["horizonte_previsto_s"] > 0


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
    p["_t"] = _ns(p["t_obs_utc"]).astype("int64")  # cuándo ocurrió
    p["_td"] = _ns(p["t_disp_utc"]).astype("int64")  # cuándo se supo: el «ahora»
    g = p.groupby(CLAVE_VIAJE, sort=False)

    # La parada objetivo es la que está `horizonte` posiciones más allá en el
    # horario, no el h-ésimo paso observado: si se saltara una, la fila sabría de
    # un hueco que aún no ha ocurrido. En el GTFS de la EMT `stop_sequence` es
    # consecutivo. Sin esa parada, la fila no tiene objetivo ni tramo.
    sigue = g["stop_sequence"].shift(-horizonte) == p["stop_sequence"] + horizonte

    def destino(col: str) -> pd.Series:
        return g[col].shift(-horizonte).where(sigue)

    p[objetivo] = destino("retraso_s")
    p["retraso_lag1_s"] = g["retraso_s"].shift(1)
    p["retraso_lag2_s"] = g["retraso_s"].shift(2)
    p["retraso_delta_s"] = p["retraso_s"] - p["retraso_lag1_s"]
    p["t_prog_hasta_objetivo_s"] = destino("t_prog_s") - p["t_prog_s"]
    p["dist_objetivo_m"] = destino("abscisa_parada_m") - p["abscisa_parada_m"]
    p["_stop_objetivo"] = destino("stop_id")
    p["_t_fin"] = destino("_t")
    p["_td_fin"] = destino("_td")
    # Claves, no variables. El útil mira el paso siguiente REAL: describe, no
    # estratifica. El previsto usa solo lo que se sabe al predecir: el horario
    # hasta la parada objetivo menos lo que ya se fue en saber el paso.
    p["horizonte_util_s"] = (p["_t_fin"] - p["_td"]) / 1e9
    p["horizonte_previsto_s"] = (
        p["t_prog_hasta_objetivo_s"] - (p["_td"] - p["_t"]) / 1e9
    )

    for n in lags_min:
        p[f"linea_retraso_{n}min"], p[f"linea_pasos_{n}min"] = _ventana_linea(p, n)
    for n in ventanas_flota_min:
        p[f"tramo_ganado_{n}min"], p[f"tramo_soporte_{n}min"] = _tramo_flota(
            p, p[objetivo] - p["retraso_s"], n, soporte_min
        )

    p["tramo_sesgo_s"], p["tramo_sesgo_soporte"] = _sesgo_tramo(
        p, p[objetivo] - p["retraso_s"], soporte_min
    )

    # El último viaje de la línea que se SABE que pasó por la parada objetivo
    # antes del ahora. El propio viaje no puede: su paso por ella llega después.
    previos = (
        p[["linea", "stop_id", "_td", "_t", "retraso_s"]]
        .rename(
            columns={
                "stop_id": "_stop_objetivo",
                "_td": "_td_prev",
                "_t": "_t_prev",
                "retraso_s": "_r_prev",
            }
        )
        .sort_values("_td_prev", kind="stable")
    )
    con_obj = p[p["_stop_objetivo"].notna()].sort_values("_td", kind="stable")
    bus = pd.merge_asof(
        con_obj[["_td", "linea", "_stop_objetivo"]].reset_index(),
        previos,
        left_on="_td",
        right_on="_td_prev",
        by=["linea", "_stop_objetivo"],
        direction="backward",
        allow_exact_matches=False,
    ).set_index("index")
    p["bus_anterior_retraso_s"] = bus["_r_prev"]
    # Edad del dato: desde que ocurrió el paso hasta el ahora.
    p["bus_anterior_edad_s"] = (bus["_td"] - bus["_t_prev"]) / 1e9

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
    200 observaciones. Un viaje es un par (día de servicio, `viaje_id`): la clave
    de viaje de todo el módulo (`CLAVE_VIAJE`).

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


def ventanas_flota(cfg: dict) -> tuple[int, ...]:
    """Las ventanas de la flota según `params.yaml → features`; ninguna si no entra."""
    return tuple(cfg["ventanas_flota_min"]) if cfg["incluir_flota"] else ()


def predicciones_baseline(t: pd.DataFrame) -> dict[str, pd.Series]:
    """Lo que predice cada baseline, fila a fila: horario (0), persistencia y
    persistencia más el sesgo del tramo (nulo = 0).

    El tercero es el listón del tráfico: batir la persistencia es, sobre todo,
    aprender el sesgo fijo del horario (bitácora 039). `evaluate.py` compara el
    modelo con estas mismas series: definirlas dos veces es medir contra otro
    listón sin saberlo.
    """
    return {
        "horario": pd.Series(0.0, index=t.index),
        "persistencia": t["retraso_s"],
        "persistencia_tramo": t["retraso_s"] + t["tramo_sesgo_s"].fillna(0.0),
    }


def errores(pred: pd.Series, real: pd.Series) -> dict:
    e = (pred - real).to_numpy()
    return {
        "mae_s": round(float(np.abs(e).mean()), 2),
        "rmse_s": round(float(np.sqrt((e**2).mean())), 2),
    }


def baselines(test: pd.DataFrame, objetivo: str, soporte: pd.DataFrame) -> dict:
    """MAE y RMSE de `predicciones_baseline`: globales, por línea con su soporte,
    y por grupo de soporte (`soporte_por_linea`)."""

    def los_dos(g: pd.DataFrame) -> dict:
        return {
            "filas": int(len(g)),
            **{k: errores(v, g[objetivo]) for k, v in predicciones_baseline(g).items()},
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


def con_disponibilidad(
    pasos: pd.DataFrame, disponibilidad: pd.DataFrame
) -> pd.DataFrame:
    """`pasos` con su `t_disp_utc`, unido por (día, viaje, parada), nunca por
    posición (trampa 012). Un paso sin `t_disp` es un error, no un nulo."""

    def clave(df: pd.DataFrame) -> pd.DataFrame:
        return df.assign(
            fecha_servicio=pd.to_datetime(df["fecha_servicio"]).astype("datetime64[ns]")
        )

    r = clave(pasos).merge(
        clave(disponibilidad)[[*CLAVE_PASO, "t_disp_utc"]],
        on=CLAVE_PASO,
        how="left",
        validate="many_to_one",
    )
    faltan = int(r["t_disp_utc"].isna().sum())
    if faltan:
        raise ValueError(f"{faltan} pasos sin t_disp")
    return r


def salidas(horizonte: int | None = None) -> dict[str, Path]:
    """Dónde escriben `features`, `train` y `evaluate`.

    Sin horizonte, las rutas de siempre: es el de `params.yaml` y la bitácora las
    cita. Con él, una carpeta por horizonte del barrido (ADR-023).
    """
    modelo = RAIZ / settings.model_path
    if horizonte is None:
        return {
            "tabla": settings.processed_dir,
            "modelo": modelo,
            "metricas": RAIZ / "metrics",
        }
    h = f"h{horizonte}"
    return {
        "tabla": settings.processed_dir / h,
        "modelo": modelo.parent / h / modelo.name,
        "metricas": RAIZ / "metrics" / "horizontes" / h,
    }


def _pasos() -> pd.DataFrame:
    return pd.concat(
        (
            pd.read_parquet(f)
            for f in sorted((settings.interim_dir / "pasos").rglob("*.parquet"))
        ),
        ignore_index=True,
    )


def main_disponibilidad() -> None:
    """Stage `disponibilidad`: `t_disp` de cada paso, una vez para todos los
    horizontes (ADR-022 y ADR-023)."""
    etiqueta = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))[
        "prepare"
    ]
    pasos = _pasos()
    posiciones = pd.read_parquet(
        settings.interim_dir / "emt_tracked",
        columns=["fecha_servicio", "viaje_id", "ts_utc", "snapshot_id", "fiable"],
    )
    # Las mismas que mira `cruces`: las fiables del viaje.
    posiciones = posiciones[posiciones["viaje_id"].notna() & posiciones["fiable"]]
    curado = (settings.curated_dir / "source=emt_buses").as_posix()
    llegadas = duckdb.sql(
        "select snapshot_id, min(ts_ingest_utc) as llega from read_parquet("
        f"'{curado}/*/*.parquet', hive_partitioning=false) group by 1"
    ).df()
    llegadas = pd.Series(
        pd.to_datetime(llegadas["llega"], utc=True).to_numpy(),
        index=llegadas["snapshot_id"],
    )
    pasos["t_disp_utc"] = instante_disponible(
        pasos,
        posiciones,
        llegadas,
        max_hueco_s=etiqueta["max_hueco_cruce_s"],
        paradas_referencia=etiqueta["paradas_referencia"],
    )
    sin_llegada = int(pasos["t_disp_utc"].isna().sum())
    if sin_llegada:
        raise ValueError(f"{sin_llegada} pasos sin posición que los confirme")
    destino = settings.interim_dir / "disponibilidad"
    destino.mkdir(parents=True, exist_ok=True)
    pasos[[*CLAVE_PASO, "t_disp_utc"]].to_parquet(
        destino / "disponibilidad.parquet", index=False, compression="zstd"
    )


def main(horizonte: int | None = None) -> None:
    """Stage `features`: la tabla de un horizonte, partida en entrenamiento y
    prueba, con sus baselines. Sin horizonte, el de `params.yaml`."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    if cfg["incluir_trafico"] or cfg["incluir_meteo"]:
        raise NotImplementedError("capa 192 y meteo: después de la fase 2")
    pasos = con_disponibilidad(
        _pasos(),
        pd.read_parquet(settings.interim_dir / "disponibilidad"),
    )
    tabla = construir(
        pasos,
        objetivo=cfg["objetivo"],
        horizonte=horizonte or cfg["horizonte_paradas"],
        lags_min=tuple(cfg["lags_min"]),
        umbral_s=cfg["umbral_retraso_s"],
        ventanas_flota_min=ventanas_flota(cfg),
        soporte_min=cfg["soporte_min"],
    )
    train, test = partir(tabla, cfg["test_desde"])
    soporte = soporte_por_linea(
        train, test, cfg["linea_min_viajes"], cfg["linea_min_dias"]
    )
    rutas = salidas(horizonte)
    rutas["tabla"].mkdir(parents=True, exist_ok=True)
    train.to_parquet(rutas["tabla"] / "train.parquet", index=False, compression="zstd")
    test.to_parquet(rutas["tabla"] / "test.parquet", index=False, compression="zstd")

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
        # Cuándo se sabe cada paso y cuánto horizonte queda entonces (trampa 017).
        "disponibilidad_test": {
            "retardo_s_p10_p50_p90": [
                round(float(x), 1)
                for x in (test["t_disp_utc"] - test["t_obs_utc"])
                .dt.total_seconds()
                .quantile([0.1, 0.5, 0.9])
            ],
            "horizonte_util_s_p10_p50_p90": [
                round(float(x), 1)
                for x in test["horizonte_util_s"].quantile([0.1, 0.5, 0.9])
            ],
            "horizonte_util_no_positivo": round(
                float((test["horizonte_util_s"] <= 0).mean()), 4
            ),
            "horizonte_previsto_s_p10_p50_p90": [
                round(float(x), 1)
                for x in test["horizonte_previsto_s"].quantile([0.1, 0.5, 0.9])
            ],
            "fuera_de_la_poblacion": round(float((~poblacion(test)).mean()), 4),
        },
        "baselines_test": baselines(test, cfg["objetivo"], soporte),
    }
    rutas["metricas"].mkdir(parents=True, exist_ok=True)
    salida = rutas["metricas"] / "features.json"
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
    a = argparse.ArgumentParser()
    a.add_argument("--disponibilidad", action="store_true", help="solo t_disp")
    a.add_argument("--horizonte", type=int, default=None, help="paradas (ADR-023)")
    args = a.parse_args()
    if args.disponibilidad:
        main_disponibilidad()
    else:
        main(args.horizonte)
