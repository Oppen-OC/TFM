"""¿En qué nivel vive lo que la persistencia no explica? (bitácora 039)

    uv run python -m project.analysis.medir_sesgo_tramo

Corrige la persistencia con la mediana de su error en el entrenamiento, agrupada
a distintos niveles, y mide el MAE en la prueba. Si una agrupación aprendida en
agosto y la semana del 14/09 mejora la prueba, el efecto es estable: es lo que
`linea` como categórica o el sesgo del tramo pueden aportar al modelo. La
variable que entra al modelo (`features._sesgo_tramo`) no congela el
entrenamiento: usa todo lo acabado antes de cada día, y su cifra está en
`metrics/features.json` (`persistencia_tramo`). Lee `data/processed/`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from project.config import RAIZ, settings

NIVELES = {
    "global": [],
    "linea": ["linea"],
    "linea y hora": ["linea", "hora_entera"],
    "linea y parada objetivo": ["linea", "stop_objetivo_id"],
    "horario, linea, parada y parada objetivo": [
        "feed_version",
        "linea",
        "stop_id",
        "stop_objetivo_id",
    ],
}


def corregida(train: pd.DataFrame, test: pd.DataFrame, claves: list[str]) -> np.ndarray:
    """Error de la persistencia en la prueba tras restar la mediana del grupo."""
    g = train["error"].median()
    if not claves:
        return (test["error"] - g).to_numpy()
    m = train.groupby(claves)["error"].median()
    # Con una sola clave el índice es simple: reindexado con un MultiIndex de un
    # nivel no casa ninguna fila y todo cae en la mediana global, sin error.
    idx = (
        pd.MultiIndex.from_frame(test[claves])
        if len(claves) > 1
        else pd.Index(test[claves[0]])
    )
    p = m.reindex(idx).fillna(g).to_numpy()
    return test["error"].to_numpy() - p


def main() -> None:
    obj = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))[
        "features"
    ]["objetivo"]
    cols = ["linea", "hora", "stop_id", "stop_objetivo_id", "feed_version"]
    t = {
        s: pd.read_parquet(
            settings.processed_dir / f"{s}.parquet", columns=[*cols, "retraso_s", obj]
        )
        for s in ("train", "test")
    }
    for d in t.values():
        d["error"] = d[obj] - d["retraso_s"]
        d["hora_entera"] = d["hora"].astype(int)
    print(f"persistencia: MAE {t['test']['error'].abs().mean():.2f} s")
    for nombre, claves in NIVELES.items():
        e = corregida(t["train"], t["test"], claves)
        print(f"+ mediana por {nombre}: MAE {np.abs(e).mean():.2f} s")
    a = t["train"].groupby("linea")["error"].mean()
    b = t["test"].groupby("linea")["error"].mean()
    n = t["test"].groupby("linea").size()
    k = a.index.intersection(b.index)
    c = np.cov(np.vstack([a[k], b[k]]), aweights=n[k])
    print(
        f"media por línea, entrenamiento frente a prueba: correlación "
        f"{c[0, 1] / np.sqrt(c[0, 0] * c[1, 1]):.3f}, rango {a.min():.1f} a "
        f"{a.max():.1f} s; líneas de la prueba sin entrenamiento: "
        f"{sorted(set(b.index) - set(a.index))}"
    )


if __name__ == "__main__":
    main()
