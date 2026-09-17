"""Cuánto se equivoca el tracker, y en qué unidad hay que contarlo.

    uv run python -m project.analysis.medir_tracking
    uv run python -m project.analysis.medir_tracking --semillas 7,11,23 --snaps 20,80

Mide la reconstrucción de identidad sobre la flota simulada de
`project.analysis.simulacion`, la única entrada con verdad-terreno. Reporta
cuatro cifras, y la diferencia entre ellas es el hallazgo:

  err_ident     posiciones asignadas a un vehículo que no es el suyo, sobre el
                total de posiciones. Es la métrica intuitiva, y es la que
                engaña: se diluye al alargar la captura aunque los fallos sean
                exactamente los mismos.
  saltos        veces que una trayectoria reconstruida cambia de bus real. Es
                el número de fallos de verdad; no depende de la duración.
  contaminadas  trayectorias que contienen más de un bus real, sobre el total.
                Un salto no se corrige solo: a partir de ahí la trayectoria
                mezcla dos vehículos.
  cola          posiciones posteriores al primer salto de su trayectoria. Es lo
                que aguas abajo hereda una etiqueta de retraso de otro autobús.
  fragmentacion trayectorias reconstruidas por bus real. 1,0 es perfecto; 4,0
                significa que el bus medio sale partido en cuatro trozos.

Las cuatro primeras miden FUSIÓN y son ciegas a la fragmentación: parte un bus
en diez trozos y los diez salen puros, así que `err_ident`, `saltos`,
`contaminadas` y `cola` marcan cero. `fragmentacion` es el eje que faltaba, y es
ciega en el sentido contrario — un tracker que lo fusione todo en una trayectoria
la deja en 1,0. Sólo sirven juntas: mejorar una a costa de la otra no es mejorar.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd

from project.analysis.simulacion import simular_flota
from project.tracking import rastrear


def medir(sim: pd.DataFrame, predictivo: bool = True, tolerar_hueco: int = 2) -> dict:
    """Compara la identidad reconstruida contra la columna `verdad`."""
    out = rastrear(
        sim.drop(columns=["verdad"]),
        predictivo=predictivo,
        tolerar_hueco=tolerar_hueco,
    )
    out["verdad"] = sim["verdad"]

    # Precisión de identidad: por trayectoria, la fracción de sus posiciones que
    # pertenece al bus real mayoritario. Es la definición que usa test_tracking.
    aciertos = (
        out.groupby("vehicle_id")["verdad"]
        .agg(lambda s: s.value_counts().iloc[0])
        .sum()
    )

    orden = out.sort_values(["vehicle_id", "snapshot_id"], kind="stable")
    saltos, cola = 0, 0
    for _, g in orden.groupby("vehicle_id"):
        v = g["verdad"].to_numpy()
        cambios = np.flatnonzero(v[1:] != v[:-1])
        saltos += len(cambios)
        if len(cambios):
            cola += len(v) - (cambios[0] + 1)

    n = len(out)
    buses_reales = int(sim["verdad"].nunique())
    return {
        "n_snaps": int(sim["snapshot_id"].nunique()),
        "n_buses": int(sim.groupby("snapshot_id").size().max()),
        "posiciones": n,
        "trayectorias": int(out["vehicle_id"].nunique()),
        "err_ident": 1 - aciertos / n,
        "saltos": saltos,
        "contaminadas": float(
            (out.groupby("vehicle_id")["verdad"].nunique() > 1).mean()
        ),
        "cola": cola / n,
        "buses_reales": buses_reales,
        "fragmentacion": out["vehicle_id"].nunique() / buses_reales,
    }


CABECERA = (
    f"{'modo':<11}{'buses':>6}{'snaps':>7}{'pos':>7}{'trays':>7}"
    f"{'err_ident':>11}{'saltos':>8}{'contaminadas':>14}{'cola':>8}"
    f"{'fragmenta':>11}"
)


def linea(modo: str, m: dict) -> str:
    return (
        f"{modo:<11}{m['n_buses']:>6}{m['n_snaps']:>7}{m['posiciones']:>7}"
        f"{m['trayectorias']:>7}{m['err_ident']:>10.3%}{m['saltos']:>8}"
        f"{m['contaminadas']:>13.1%}{m['cola']:>8.2%}"
        f"{m['fragmentacion']:>11.2f}"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--snaps", default="20,40,80,160", help="longitudes de captura")
    p.add_argument("--semillas", default="7,11,23,42,101", help="semillas de flota")
    p.add_argument("--buses", default="60,120", help="tamaños de flota")
    p.add_argument("--dt", default="30,60", help="intervalos de refresco en s")
    a = p.parse_args()

    nums = lambda s: [int(x) for x in s.split(",")]  # noqa: E731

    print("\n=== La captura se alarga, los fallos son los mismos ===")
    print("(err_ident baja sin que nada mejore; saltos y contaminadas no se mueven)\n")
    print(CABECERA)
    for predictivo in (False, True):
        modo = "predictivo" if predictivo else "ingenuo"
        for n in nums(a.snaps):
            print(linea(modo, medir(simular_flota(n_snaps=n), predictivo)))

    print("\n=== Dispersión entre semillas (20 snapshots) ===\n")
    print(CABECERA + "  semilla")
    for predictivo in (False, True):
        modo = "predictivo" if predictivo else "ingenuo"
        for s in nums(a.semillas):
            m = medir(simular_flota(semilla=s), predictivo)
            print(linea(modo, m) + f"{s:>9}")

    print("\n=== Densidad y refresco: dónde deja de funcionar el predictivo ===\n")
    print(CABECERA + "     dt_s")
    for predictivo in (False, True):
        modo = "predictivo" if predictivo else "ingenuo"
        for nb in nums(a.buses):
            for dt in nums(a.dt):
                m = medir(simular_flota(n_buses=nb, dt=float(dt)), predictivo)
                print(linea(modo, m) + f"{dt:>9}")


if __name__ == "__main__":
    main()
