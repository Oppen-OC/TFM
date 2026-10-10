"""Stage `tramos_ruta`: qué tramos de la capa 192 cubren cada trozo de recorrido.

    uv run python -m project.trafico          # lo que ejecuta `dvc repro tramos_ruta`

Para cada versión del GTFS, cada trazado y cada tramo de tráfico, los intervalos
de abscisa del trazado que el tramo recorre: puntos del tramo, cada `PASO_M`, a
`dist_max` metros o menos del trazado, en tramos seguidos que abarcan al menos
`largo_min` metros de RECORRIDO. Cruzar la ruta no es recorrerla (ADR-024).

No distingue el sentido de la calle: un tramo de una calle de doble sentido
cubre el recorrido en los dos. Los puntos que `proyectar` marca como ambiguos,
porque el trazado vuelve a pasar cerca, no cuentan. La geometría es la de
`data/reference/` (ADR-017).
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd
import yaml

from project import gtfs
from project.config import RAIZ, settings
from project.gtfs import Trazado, a_metros
from project.mapmatching import proyectar

PASO_M = 10.0


def puntos(wkt: str) -> tuple[np.ndarray, np.ndarray]:
    """`LINESTRING (lon lat, …)` a metros del plano local."""
    lonlat = np.array(re.findall(r"(-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)", wkt), float)
    return a_metros(lonlat[:, 1], lonlat[:, 0])


def _densificar(x: np.ndarray, y: np.ndarray, paso: float) -> tuple[np.ndarray, ...]:
    d = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
    s = np.append(np.arange(0.0, d[-1], paso), d[-1])
    return np.interp(s, d, x), np.interp(s, d, y)


def cubrir(
    x: np.ndarray,
    y: np.ndarray,
    trazado: Trazado,
    dist_max: float,
    largo_min: float,
    paso: float = PASO_M,
) -> list[tuple[float, float]]:
    """Intervalos (s_ini, s_fin) de abscisa del trazado que recorre el tramo."""
    px, py = _densificar(x, y, paso)
    pr = proyectar(px, py, trazado)
    cerca = (pr["dist_m"] <= dist_max) & ~pr["ambigua"]
    intervalos = []
    # tramos de puntos seguidos cerca del trazado
    cambios = np.flatnonzero(np.diff(np.concatenate([[0], cerca.astype(int), [0]])))
    for ini, fin in zip(cambios[::2], cambios[1::2]):
        s = pr["abscisa_m"][ini:fin]
        lo, hi = float(s.min()), float(s.max())
        if hi - lo >= largo_min:
            intervalos.append((lo, hi))
    return intervalos


def tramos_ruta(
    trazados: list[tuple[str, Trazado]],
    tramos: pd.DataFrame,
    dist_max: float,
    largo_min: float,
) -> pd.DataFrame:
    """Una fila por (versión, trazado, tramo, intervalo cubierto)."""
    geometria = {int(t.idtramo): puntos(t.geom_wkt) for t in tramos.itertuples()}
    filas = []
    for version, tz in trazados:
        xmin, xmax = tz.x.min() - dist_max, tz.x.max() + dist_max
        ymin, ymax = tz.y.min() - dist_max, tz.y.max() + dist_max
        for idtramo, (x, y) in geometria.items():
            fuera = x.max() < xmin or x.min() > xmax or y.max() < ymin or y.min() > ymax
            if fuera:
                continue
            for lo, hi in cubrir(x, y, tz, dist_max, largo_min):
                filas.append((version, tz.shape_id, idtramo, lo, hi))
    return pd.DataFrame(
        filas, columns=["feed_version", "shape_id", "idtramo", "s_ini", "s_fin"]
    )


# Estados de la capa 192 (bitácoras 005 y 031): 0 fluido, 1 denso, 2 congestionado.
# El 3 (cortado) son casi siempre vías cerradas de forma permanente y el 4 es un
# fallo del servicio que aparece en toda la capa a la vez: no son observaciones.
CONGESTION = (1, 2)
FLUIDO = (0,)


def _ns(t: pd.Series) -> np.ndarray:
    return (
        t.dt.tz_convert("UTC").astype("datetime64[ns, UTC]").astype("int64").to_numpy()
    )


def en_ruta(
    filas: pd.DataFrame,
    intervalos: pd.DataFrame,
    estados: pd.DataFrame,
    edad_max_s: float,
) -> pd.DataFrame:
    """El tráfico en el recorrido [s_desde, s_hasta] de cada fila, con el índice de
    `filas` (`feed_version`, `shape_id`, `s_desde`, `s_hasta`, `t_disp_utc`).

    - `trafico_cubierto_m`: metros de recorrido bajo algún tramo de la 192.
      Geométrico: no depende del sondeo.
    - `trafico_congestion_frac`: de los metros con estado observado, la parte en
      estado 1-2, en el último sondeo llegado ESTRICTAMENTE antes de `t_disp`
      (trampa 017). Nula sin estado observado o con el sondeo más viejo que
      `edad_max_s`: la captura tiene huecos de horas.
    - `trafico_edad_s`: antigüedad de ese sondeo.

    Dos tramos que cubren el mismo trozo (una calle y su paralela, o los dos
    sentidos) cuentan los dos.
    """
    e = estados.drop_duplicates(["ts_ingest_utc", "idtramo"])  # trampa 014
    tiempos = np.unique(_ns(e["ts_ingest_utc"]))
    ids = np.unique(e["idtramo"].astype(int).to_numpy())
    matriz = np.full((len(tiempos), len(ids)), np.nan)
    valor = np.where(
        e["estado"].isin(CONGESTION),
        1.0,
        np.where(e["estado"].isin(FLUIDO), 0.0, np.nan),
    )
    matriz[
        np.searchsorted(tiempos, _ns(e["ts_ingest_utc"])),
        np.searchsorted(ids, e["idtramo"].astype(int).to_numpy()),
    ] = valor

    td = _ns(filas["t_disp_utc"])
    k = np.searchsorted(tiempos, td, side="left") - 1
    edad = np.where(k >= 0, (td - tiempos[np.maximum(k, 0)]) / 1e9, np.nan)
    vigente = (k >= 0) & (edad <= edad_max_s)

    n = len(filas)
    cubierto, observado, congestion = np.zeros(n), np.zeros(n), np.zeros(n)
    a = np.minimum(filas["s_desde"], filas["s_hasta"]).to_numpy()
    b = np.maximum(filas["s_desde"], filas["s_hasta"]).to_numpy()
    iv = intervalos[intervalos["idtramo"].astype(int).isin(ids)]
    grupos_iv = iv.groupby(["feed_version", "shape_id"], sort=False).indices
    for clave, idx in filas.groupby(
        ["feed_version", "shape_id"], sort=False
    ).indices.items():
        if clave not in grupos_iv:
            continue
        t = iv.iloc[grupos_iv[clave]]
        lo, hi = t["s_ini"].to_numpy(), t["s_fin"].to_numpy()
        col = np.searchsorted(ids, t["idtramo"].astype(int).to_numpy())
        solape = np.clip(
            np.minimum(hi, b[idx, None]) - np.maximum(lo, a[idx, None]), 0.0, None
        )
        estado = np.where(
            vigente[idx, None], matriz[np.maximum(k[idx], 0)][:, col], np.nan
        )
        cubierto[idx] = solape.sum(axis=1)
        observado[idx] = np.where(np.isnan(estado), 0.0, solape).sum(axis=1)
        congestion[idx] = (solape * np.nan_to_num(estado)).sum(axis=1)

    frac = np.divide(congestion, observado, out=np.full(n, np.nan), where=observado > 0)
    return pd.DataFrame(
        {
            "trafico_cubierto_m": cubierto,
            "trafico_congestion_frac": frac,
            "trafico_edad_s": edad,
        },
        index=filas.index,
    )


def main() -> None:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    trazados = []
    for ruta in gtfs.versiones(settings.gtfs_dir):
        h = gtfs.cargar_horario(ruta)
        trazados += [(h.version, t) for ts in h.trazados.values() for t in ts]
    tramos = pd.read_parquet(
        settings.reference_dir / "trafico_estado_geometria.parquet",
        columns=["idtramo", "geom_wkt"],
    )
    r = tramos_ruta(
        trazados,
        tramos,
        dist_max=cfg["trafico_dist_max_m"],
        largo_min=cfg["trafico_largo_min_m"],
    )
    destino = settings.interim_dir / "tramos_ruta"
    destino.mkdir(parents=True, exist_ok=True)
    r.to_parquet(destino / "tramos_ruta.parquet", index=False, compression="zstd")
    cubiertos = r.drop_duplicates(["feed_version", "shape_id"])
    print(
        f"{len(r)} intervalos, {r['idtramo'].nunique()} de {len(tramos)} tramos, "
        f"{len(cubiertos)} de {len(trazados)} trazados con algún tramo"
    )


if __name__ == "__main__":
    main()
