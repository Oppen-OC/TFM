"""Las paradas de tipo `serie`, en PDF para la memoria, de la misma foto que la página.

Se usa `Figure` y no `pyplot`: sin estado global ni backend de ventanas.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd
from matplotlib.figure import Figure

ACENTO, SOMBRA = "#1f5fa8", "#d9822b"


def figura_serie(prueba: dict, titulo: str, destino: Path) -> None:
    x = pd.to_datetime(prueba["x"])
    n = len(prueba["series"])
    fig = Figure(figsize=(8, 1.6 * n + 0.9))
    ejes = fig.subplots(n, 1, sharex=True, squeeze=False)[:, 0]
    for ax, s in zip(ejes, prueba["series"]):
        valores = [float("nan") if v is None else v for v in s["valores"]]
        ax.plot(x, valores, color=ACENTO, lw=1.4)
        ax.set_ylabel(s["nombre"].replace(" · ", "\n"), fontsize=8)
        ax.set_ylim(bottom=0)  # como en la página: sin eje truncado que exagere
        for sb in prueba["sombras"]:
            fin = pd.Timestamp(sb["hasta"]) + pd.Timedelta(days=1)
            ax.axvspan(pd.Timestamp(sb["desde"]), fin, color=SOMBRA, alpha=0.18, lw=0)
        for a in prueba["anotaciones"]:
            ax.axvline(pd.Timestamp(a["x"]), color="0.4", lw=0.8, ls="--")
        ax.spines[["top", "right"]].set_visible(False)
    for i, a in enumerate(prueba["anotaciones"]):
        ejes[0].annotate(
            a["texto"],
            (pd.Timestamp(a["x"]), 1),
            xycoords=("data", "axes fraction"),
            xytext=(3, 4 + 10 * (i % 2)),
            textcoords="offset points",
            fontsize=7,
        )
    ejes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    fig.suptitle(titulo, fontsize=11)
    fig.tight_layout()
    destino.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destino)
