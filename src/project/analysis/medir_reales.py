"""Mide sobre la captura real lo que la flota simulada no puede decir.

    uv run python -m project.analysis.medir_reales
    uv run python -m project.analysis.medir_reales --fecha 2026-08-16 --snapshots 150
    uv run python -m project.analysis.medir_reales --rev 800b9e1   # tracker de esa revisión

Dos medidas, las dos sobre `data/curated/source=emt_buses`:

  VECINDAD  ¿con qué frecuencia un vehículo tiene otro de su misma
            (línea, trayecto) a menos de un paso de refresco? Es la condición
            que convierte el emparejamiento en un empate exacto, y decide si el
            caso difícil del tracker es raro o es el normal.
  PUERTA    ¿algún emparejamiento supera el techo físico de desplazamiento?
            La puerta se evalúa sobre la posición predicha, que con
            `predictivo=True` no es la real: si solo se filtra por la predicha,
            cuelan saltos que el tope prohíbe.

`--rev` carga `src/project/tracking.py` tal y como estaba en esa revisión de git
y mide con él. Es lo que permite citar la cifra de "antes" de un arreglo sin
tener que revertir nada ni duplicar el código viejo dentro del medidor.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd

from project.config import settings
from project.ingest.sources import haversine_m


def cargar_tracker(rev: str | None) -> ModuleType:
    """Devuelve el módulo `tracking` actual, o el de una revisión de git."""
    if rev is None:
        from project import tracking

        return tracking

    fuente = subprocess.run(
        ["git", "show", f"{rev}:src/project/tracking.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    destino = Path(tempfile.mkdtemp()) / f"tracking_{rev}.py"
    destino.write_text(fuente, encoding="utf-8")

    spec = importlib.util.spec_from_file_location(f"tracking_{rev}", destino)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def cargar(fecha: str, n_snapshots: int | None, hora_utc: int | None) -> pd.DataFrame:
    """Carga un día curado, opcionalmente recortado a una franja horaria.

    La hora importa: a las 00:00 la mitad de la flota está parada (paso mediano
    de 2 m por refresco) y un grupo (línea, trayecto) tiene un solo vehículo.
    Medir la dificultad del emparejamiento ahí no dice nada del servicio real.
    """
    ruta = settings.curated_dir / "source=emt_buses" / f"date={fecha}"
    df = pd.read_parquet(ruta)
    if hora_utc is not None:
        df = df[df["ts_utc"].dt.hour == hora_utc]
    if n_snapshots:
        primeros = sorted(df["snapshot_id"].unique())[:n_snapshots]
        df = df[df["snapshot_id"].isin(primeros)]
    return df.reset_index(drop=True)


def vecindad(df: pd.DataFrame, tracker: ModuleType) -> dict:
    """Distancia al vecino más próximo de la misma (línea, trayecto).

    El umbral no es una constante elegida a ojo: es el desplazamiento que ESE
    vehículo hace en ESE refresco, que lo aporta el propio tracker en `dist_m`.
    Un compañero más cerca que el propio paso significa que la posición futura
    del vecino es indistinguible de la propia, que es la definición del empate.
    """
    out = tracker.rastrear(df)
    vecino = np.full(len(out), np.nan)

    for _, g in out.groupby(["snapshot_id", "linea", "trayecto"], sort=False):
        if len(g) < 2:
            continue
        lat = g["lat"].to_numpy()
        lon = g["lon"].to_numpy()
        d = haversine_m(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
        np.fill_diagonal(d, np.inf)
        vecino[out.index.get_indexer(g.index)] = d.min(axis=1)

    out["vecino_m"] = vecino
    con_paso = out.dropna(subset=["dist_m", "vecino_m"])
    paso_mediano = float(con_paso["dist_m"].median())

    # Tres lecturas de "a menos de un paso de refresco". La primera es la
    # estricta (el paso propio de ese vehículo en ese refresco), la segunda usa
    # el paso típico de la franja, y la tercera el paso nominal de un bus urbano
    # a 15 km/h, que es la referencia con la que están escritos los escenarios
    # de `tests/test_tracking_identidad.py`.
    return {
        "posiciones": len(out),
        "con_vecino_de_grupo": int(out["vecino_m"].notna().sum()),
        "evaluables": len(con_paso),
        "empate_paso_propio": float((con_paso["vecino_m"] < con_paso["dist_m"]).mean()),
        "empate_paso_mediano": float((con_paso["vecino_m"] < paso_mediano).mean()),
        "empate_125m": float((con_paso["vecino_m"] < 125.0).mean()),
        "vecino_p10_m": round(float(con_paso["vecino_m"].quantile(0.10)), 1),
        "vecino_p50_m": round(float(con_paso["vecino_m"].median()), 1),
        "paso_p50_m": round(paso_mediano, 1),
        "buses_por_grupo_p50": float(
            out.groupby(["snapshot_id", "linea", "trayecto"]).size().median()
        ),
    }


def puerta(df: pd.DataFrame, tracker: ModuleType) -> dict:
    """Emparejamientos que superan el techo físico de desplazamiento."""
    out = tracker.rastrear(df)
    tr = out.dropna(subset=["dist_m"])
    fuera = tr[tr["dist_m"] > tracker.SALTO_MAX_M]
    return {
        "emparejamientos": len(tr),
        "sobre_salto_max": len(fuera),
        "dist_max_m": round(float(tr["dist_m"].max()), 1),
        "dist_p999_m": round(float(tr["dist_m"].quantile(0.999)), 1),
        "vel_max_kmh": round(float(tr["vel_kmh"].max()), 1),
        "sobre_vel_max": int((tr["vel_kmh"] > tracker.VEL_MAX_KMH).sum()),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fecha", default="2026-08-16")
    p.add_argument("--snapshots", type=int, default=150, help="0 = el día entero")
    p.add_argument("--hora", type=int, default=None, help="hora UTC a aislar (0-23)")
    p.add_argument("--rev", default=None, help="revisión de git del tracker a medir")
    a = p.parse_args()

    tracker = cargar_tracker(a.rev)
    df = cargar(a.fecha, a.snapshots or None, a.hora)
    print(
        f"tracker: {a.rev or 'árbol de trabajo'} · {a.fecha} · "
        f"{df['snapshot_id'].nunique()} snapshots · {len(df)} posiciones\n",
        file=sys.stderr,
    )

    print("=== VECINDAD: ¿el empate es raro o es lo normal? ===")
    for k, v in vecindad(df, tracker).items():
        print(f"  {k:24} {v:.3f}" if isinstance(v, float) else f"  {k:24} {v}")

    print("\n=== PUERTA: saltos por encima del techo físico ===")
    for k, v in puerta(df, tracker).items():
        print(f"  {k:24} {v}")


if __name__ == "__main__":
    main()
