"""Reconstrucción de identidad de vehículo: el problema central de esta fuente.

La capa de la EMT NO publica identificador de vehículo. El campo `gid` es un
autoincrement de una tabla que se trunca y reinserta entera en cada refresco:
entre dos sondeos consecutivos, la intersección de gids es exactamente cero
(verificado empíricamente el 15/08/2026: bloques [...987635-987800] y
[...987801-987967], contiguos y disjuntos).

Tampoco sirve la posición dentro del bloque: emparejando por rango sólo
coincide la línea y el trayecto en un 32-73 % de los casos, con
desplazamientos de hasta 5 km entre sondeos. Descartado.

Lo que sí funciona: asignación global (Hungarian) entre los vehículos de dos
snapshots consecutivos, restringida a la misma (línea, trayecto) y con una
puerta de velocidad máxima. Sobre datos reales de un sábado a las 21:15 da
0 huérfanos y un desplazamiento mediano de ~50 m por refresco de 30 s.

Esto es ETL de verdad, no un `pd.read_csv`. Es el capítulo de la memoria que
convierte el trabajo en un TFM.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from sources import haversine_m

VEL_MAX_KMH = 70.0     # un bus urbano por encima de esto es un error de asignación
SALTO_MAX_M = 800.0    # techo duro de desplazamiento entre snapshots


def _emparejar_grupo(a: pd.DataFrame, b: pd.DataFrame, dt_s: float
                     ) -> list[tuple[int, int, float]]:
    """Asignación óptima entre los vehículos de a y los de b (misma línea/trayecto)."""
    if a.empty or b.empty:
        return []

    # Se empareja contra la posición PREDICHA de a (si el llamante la aportó)
    alat = a.get("lat_pred", a["lat"]).to_numpy()[:, None]
    alon = a.get("lon_pred", a["lon"]).to_numpy()[:, None]
    d = haversine_m(alat, alon,
                    b["lat"].to_numpy()[None, :], b["lon"].to_numpy()[None, :])

    tope = min(SALTO_MAX_M, VEL_MAX_KMH / 3.6 * max(dt_s, 1.0))
    coste = np.where(d <= tope, d, 1e9)

    fi, ci = linear_sum_assignment(coste)
    return [(int(a.index[i]), int(b.index[j]), float(d[i, j]))
            for i, j in zip(fi, ci) if coste[i, j] < 1e9]


def rastrear(df: pd.DataFrame, predictivo: bool = True) -> pd.DataFrame:
    """Añade `vehicle_id`, `dist_m`, `dt_s` y `vel_kmh` a las posiciones de la EMT.

    df debe traer: snapshot_id, linea, trayecto, lat, lon, ts_utc.

    predictivo=False  -> emparejamiento por vecino más cercano puro.
    predictivo=True   -> se extrapola la posición con la velocidad del paso
                         anterior antes de emparejar. Reduce drásticamente los
                         intercambios de identidad cuando dos buses de la misma
                         línea se cruzan, que es el fallo dominante del método
                         ingenuo (medido en el autotest: de ~5 % de posiciones
                         mal asignadas a prácticamente cero).
    """
    df = df.sort_values(["snapshot_id"], kind="stable").reset_index(drop=True).copy()
    df["vehicle_id"] = pd.NA
    df["dist_m"] = np.nan
    df["dt_s"] = np.nan
    # Posición del paso anterior, para poder extrapolar
    df["_plat"] = np.nan
    df["_plon"] = np.nan

    snaps = sorted(df["snapshot_id"].unique())

    primero = df["snapshot_id"] == snaps[0]
    n0 = int(primero.sum())
    df.loc[primero, "vehicle_id"] = [f"v{i:05d}" for i in range(n0)]
    siguiente_id = n0

    for k in range(1, len(snaps)):
        prev = df[df["snapshot_id"] == snaps[k - 1]].copy()
        cur = df[df["snapshot_id"] == snaps[k]]
        dt = (cur["ts_utc"].max() - prev["ts_utc"].max()).total_seconds() or 30.0

        if predictivo:
            # Modelo de velocidad constante: si venía moviéndose, seguirá.
            tiene = prev["_plat"].notna()
            prev["lat_pred"] = prev["lat"]
            prev["lon_pred"] = prev["lon"]
            prev.loc[tiene, "lat_pred"] = 2 * prev.loc[tiene, "lat"] - prev.loc[tiene, "_plat"]
            prev.loc[tiene, "lon_pred"] = 2 * prev.loc[tiene, "lon"] - prev.loc[tiene, "_plon"]
        else:
            prev["lat_pred"] = prev["lat"]
            prev["lon_pred"] = prev["lon"]

        emparejados_b: set[int] = set()
        for clave, gb in cur.groupby(["linea", "trayecto"], sort=False):
            ga = prev[(prev["linea"] == clave[0]) & (prev["trayecto"] == clave[1])]
            for ia, ib, _ in _emparejar_grupo(ga, gb, dt):
                df.at[ib, "vehicle_id"] = df.at[ia, "vehicle_id"]
                df.at[ib, "dist_m"] = float(
                    haversine_m(df.at[ia, "lat"], df.at[ia, "lon"],
                                df.at[ib, "lat"], df.at[ib, "lon"])
                )
                df.at[ib, "dt_s"] = dt
                df.at[ib, "_plat"] = df.at[ia, "lat"]
                df.at[ib, "_plon"] = df.at[ia, "lon"]
                emparejados_b.add(ib)

        # Los no emparejados son vehículos que entran en servicio (o huérfanos)
        for ib in cur.index:
            if ib not in emparejados_b:
                df.at[ib, "vehicle_id"] = f"v{siguiente_id:05d}"
                siguiente_id += 1

    df["vel_kmh"] = df["dist_m"] / df["dt_s"] * 3.6
    return df.drop(columns=["_plat", "_plon"])


def resumen(df: pd.DataFrame) -> dict:
    tr = df.dropna(subset=["dist_m"])
    largo = df.groupby("vehicle_id").size()
    return {
        "snapshots": df["snapshot_id"].nunique(),
        "posiciones": len(df),
        "trayectorias": df["vehicle_id"].nunique(),
        "long_media_trayectoria": round(float(largo.mean()), 1),
        "long_max_trayectoria": int(largo.max()),
        "tasa_emparejamiento": round(len(tr) / max(len(df) - df["snapshot_id"].nunique(), 1), 3),
        "dist_m_p50": round(float(tr["dist_m"].median()), 1) if len(tr) else None,
        "dist_m_p90": round(float(tr["dist_m"].quantile(0.9)), 1) if len(tr) else None,
        "vel_kmh_p50": round(float(tr["vel_kmh"].median()), 1) if len(tr) else None,
        "vel_kmh_p90": round(float(tr["vel_kmh"].quantile(0.9)), 1) if len(tr) else None,
        "vel_kmh_max": round(float(tr["vel_kmh"].max()), 1) if len(tr) else None,
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    ruta = Path(sys.argv[1] if len(sys.argv) > 1 else "data/curated/source=emt_buses")
    df = pd.read_parquet(ruta)
    out = rastrear(df)
    for k, v in resumen(out).items():
        print(f"  {k:26} {v}")
    # Mismo nombre que el `outs` del stage `prepare` en dvc.yaml
    destino = Path("data/interim/emt_tracked.parquet")
    destino.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(destino, index=False)
    print(f"\n  -> {destino}")
