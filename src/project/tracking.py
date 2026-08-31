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

La asignación necesita una predicción de dónde estará cada vehículo, y la
predicción necesita una velocidad que en la PRIMERA transición de cada
trayectoria todavía no existe. Ese arranque en frío es el punto débil del
método, no el cruce de dos buses: ver `_sembrar_por_centroide`. Sobre la
captura del 16/08/2026, el 55 % de los vehículos tiene un compañero de su
misma (línea, trayecto) a menos de un paso de refresco, así que la
configuración degenerada que lo rompe es el caso normal, no el raro.

Límite conocido, no resoluble con posiciones: si los vehículos de un grupo
están equiespaciados sobre una ruta en anillo, permutar sus identidades es una
simetría de lo observado. Ningún método que sólo mire posiciones lo distingue.

Esto es ETL de verdad, no un `pd.read_csv`. Es el capítulo de la memoria que
convierte el trabajo en un TFM.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from project.ingest.sources import haversine_m

VEL_MAX_KMH = 70.0  # un bus urbano por encima de esto es un error de asignación
SALTO_MAX_M = 800.0  # techo duro de desplazamiento entre snapshots


def _emparejar_grupo(
    a: pd.DataFrame, b: pd.DataFrame, dt_s: float
) -> list[tuple[int, int, float]]:
    """Asignación óptima entre los vehículos de a y los de b (misma línea/trayecto)."""
    if a.empty or b.empty:
        return []

    blat = b["lat"].to_numpy()[None, :]
    blon = b["lon"].to_numpy()[None, :]

    # Se empareja contra la posición PREDICHA de a (si el llamante la aportó)
    d = haversine_m(
        a.get("lat_pred", a["lat"]).to_numpy()[:, None],
        a.get("lon_pred", a["lon"]).to_numpy()[:, None],
        blat,
        blon,
    )
    # ...pero la puerta física se mide sobre el desplazamiento REAL. Aplicarla
    # sobre `d` deja pasar saltos que el tope prohíbe en cuanto la predicción
    # está lejos: sobre 150 snapshots reales colaban 10 por encima de
    # SALTO_MAX_M, el mayor de 957 m, con `vel_kmh` de hasta 100.
    d_real = haversine_m(
        a["lat"].to_numpy()[:, None], a["lon"].to_numpy()[:, None], blat, blon
    )

    tope = min(SALTO_MAX_M, VEL_MAX_KMH / 3.6 * max(dt_s, 1.0))
    coste = np.where((d <= tope) & (d_real <= tope), d, 1e9)

    fi, ci = linear_sum_assignment(coste)
    return [
        (int(a.index[i]), int(b.index[j]), float(d[i, j]))
        for i, j in zip(fi, ci)
        if coste[i, j] < 1e9
    ]


def _sembrar_por_centroide(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Predice las filas de `a` que todavía no tienen velocidad propia.

    En su primera transición un vehículo no tiene paso anterior, así que la
    predicción cae a su posición actual y el emparejamiento vuelve a ser vecino
    más cercano puro. Con buses colineales a velocidad parecida eso no es un
    caso difícil: es un EMPATE EXACTO. Convoy a 15 km/h separado 120 m, paso de
    125 m -> correcto 125+125 = 250, intercambio 5+245 = 250. Hungarian
    desempata por orden de fila, y el error no se queda ahí: escribe un `_plat`
    equivocado que envenena la predicción del paso siguiente.

    El desplazamiento del centroide estima el movimiento de conjunto del grupo
    SIN conocer la correspondencia, que es justo lo que rompe el empate. Solo se
    aplica cuando el grupo no cambia de tamaño: si entran o salen vehículos, el
    centroide se mueve por el censo y no por el tráfico.
    """
    if a.empty or len(a) != len(b):
        return a
    sin_velocidad = a["_plat"].isna()
    if not sin_velocidad.any():
        return a
    a = a.copy()
    a.loc[sin_velocidad, "lat_pred"] = a.loc[sin_velocidad, "lat"] + (
        b["lat"].mean() - a["lat"].mean()
    )
    a.loc[sin_velocidad, "lon_pred"] = a.loc[sin_velocidad, "lon"] + (
        b["lon"].mean() - a["lon"].mean()
    )
    return a


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
            prev.loc[tiene, "lat_pred"] = (
                2 * prev.loc[tiene, "lat"] - prev.loc[tiene, "_plat"]
            )
            prev.loc[tiene, "lon_pred"] = (
                2 * prev.loc[tiene, "lon"] - prev.loc[tiene, "_plon"]
            )
        else:
            prev["lat_pred"] = prev["lat"]
            prev["lon_pred"] = prev["lon"]

        emparejados_b: set[int] = set()
        for clave, gb in cur.groupby(["linea", "trayecto"], sort=False):
            ga = prev[(prev["linea"] == clave[0]) & (prev["trayecto"] == clave[1])]
            if predictivo:
                ga = _sembrar_por_centroide(ga, gb)
            for ia, ib, _ in _emparejar_grupo(ga, gb, dt):
                df.at[ib, "vehicle_id"] = df.at[ia, "vehicle_id"]
                df.at[ib, "dist_m"] = float(
                    haversine_m(
                        df.at[ia, "lat"],
                        df.at[ia, "lon"],
                        df.at[ib, "lat"],
                        df.at[ib, "lon"],
                    )
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
        "tasa_emparejamiento": round(
            len(tr) / max(len(df) - df["snapshot_id"].nunique(), 1), 3
        ),
        "dist_m_p50": round(float(tr["dist_m"].median()), 1) if len(tr) else None,
        "dist_m_p90": round(float(tr["dist_m"].quantile(0.9)), 1) if len(tr) else None,
        "vel_kmh_p50": round(float(tr["vel_kmh"].median()), 1) if len(tr) else None,
        "vel_kmh_p90": round(float(tr["vel_kmh"].quantile(0.9)), 1)
        if len(tr)
        else None,
        "vel_kmh_max": round(float(tr["vel_kmh"].max()), 1) if len(tr) else None,
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    from project.config import settings

    ruta = Path(
        sys.argv[1] if len(sys.argv) > 1 else settings.curated_dir / "source=emt_buses"
    )
    df = pd.read_parquet(ruta)
    out = rastrear(df)
    for k, v in resumen(out).items():
        print(f"  {k:26} {v}")
    # Mismo nombre que el `outs` del stage `prepare` en dvc.yaml
    destino = settings.interim_dir / "emt_tracked.parquet"
    destino.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(destino, index=False)
    print(f"\n  -> {destino}")
