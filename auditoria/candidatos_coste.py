"""Candidatos descartados para los intercambios del tracker, reproducibles.

    uv run python auditoria/candidatos_coste.py            # genera y mide todos
    uv run python auditoria/candidatos_coste.py --solo A_l40 E_l40_m40

Genera copias de `src/project/tracking.py` TAL COMO ESTABA EN `b1db54e` —antes
del suavizado de intercambios— con la matriz de coste de `_emparejar_grupo`, o
el factor de extrapolación, cambiados, y las mide con `banco_tracker.py` sobre
las semillas de ajuste. Es la evidencia de por qué se descartaron
(`docs/bitacora/015-el-sondeo-siguiente-delata-el-intercambio.md`):

  A(λ)      dos hipótesis, sigue o se ha parado:  min(d_pred, d_real + λ)
  E(λ, μ)   tres, además gira a la misma velocidad:
            min(d_pred, d_real + λ, |d_real - paso_esperado| + μ)
  B(σ0, k)  coste normalizado por la incertidumbre:  d_pred / (σ0 + k·paso)
  C(α)      predicción amortiguada: extrapola α veces el paso anterior

La puerta física sigue evaluándose sobre la posición predicha Y sobre la real
en todos (trampa 008). Ninguno baja de 8 saltos con paradas ni de 8 con giros,
y dos empeoran lo que la base hace bien.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
REV = "b1db54e"

COSTE = """    t = tope[:, None]
    coste = np.where((d <= t) & (d_real <= t), d, 1e9)"""
FACTOR = 'f = prev.loc[tiene, "_dt"] / prev.loc[tiene, "_pdt"]'
PASO = """    paso = haversine_m(
        a.get("lat_pred", a["lat"]).to_numpy(),
        a.get("lon_pred", a["lon"]).to_numpy(),
        a["lat"].to_numpy(),
        a["lon"].to_numpy(),
    )[:, None]
"""
PUERTA = "(d <= t) & (d_real <= t)"


def candidatos(base: str) -> dict[str, str]:
    assert base.count(COSTE) == 1 and base.count(FACTOR) == 1
    t = "    t = tope[:, None]\n"
    c: dict[str, str] = {}
    for lam in (0, 15, 40, 80):
        c[f"A_l{lam}"] = base.replace(
            COSTE,
            t + f"    coste = np.where({PUERTA}, np.minimum(d, d_real + {lam}.0), 1e9)",
        )
    for lam, mu in ((15, 40), (40, 40), (40, 80), (80, 80)):
        hip = f"np.minimum(np.minimum(d, d_real + {lam}.0), np.abs(d_real - paso) + {mu}.0)"
        c[f"E_l{lam}_m{mu}"] = base.replace(
            COSTE, PASO + t + f"    coste = np.where({PUERTA}, {hip}, 1e9)"
        )
    for s0, k in ((25, 0.5), (50, 1.0)):
        c[f"B_s{s0}_k{str(k).replace('.', '')}"] = base.replace(
            COSTE,
            PASO
            + t
            + f"    coste = np.where({PUERTA}, d / ({s0}.0 + {k} * paso), 1e9)",
        )
    for alfa in (0.5, 0.75):
        c[f"C_a{str(alfa).replace('.', '')}"] = base.replace(
            FACTOR, f"f = {alfa} * " + FACTOR[4:]
        )
    return c


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--solo", nargs="*", default=None)
    a = p.parse_args()

    base = subprocess.run(
        ["git", "show", f"{REV}:src/project/tracking.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.replace("\r\n", "\n")
    destino = Path(tempfile.mkdtemp(prefix="tfm-candidatos-"))
    for nombre, texto in candidatos(base).items():
        if a.solo and nombre not in a.solo:
            continue
        ruta = destino / f"{nombre}.py"
        ruta.write_text(texto, encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(AQUI / "banco_tracker.py"),
                "--tracker",
                str(ruta),
                "--etiqueta",
                nombre,
                "--salida",
                str(destino),
            ],
            check=True,
        )


if __name__ == "__main__":
    main()
