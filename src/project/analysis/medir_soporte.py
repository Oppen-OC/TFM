"""¿Qué mejora se distingue en una línea, según los viajes que tiene en la prueba?

    uv run python -m project.analysis.medir_soporte

Por línea de la prueba: viajes, días, grupo de soporte, el MAE de la persistencia
y tres semianchos de intervalo del 95 %, remuestreando VIAJES enteros (las
paradas de un viaje están correlacionadas: remuestrear filas daría un intervalo
demasiado estrecho):

  semi_ic_mae_s        del MAE de la persistencia.
  semi_ic_dif_cerca_s  de la diferencia de error, sobre los mismos viajes, entre
                       la persistencia y un predictor parecido: ella misma
                       encogida un 10 %.
  semi_ic_dif_lejos_s  lo mismo con uno muy distinto: la persistencia encogida a
                       la mitad.

Los dos predictores son sustitutos del modelo, que aún no existe: acotan cuánto
tendría que mejorar para que se viera en una línea. Tienen que estar definidos en
TODAS las filas: el primer «lejano» usaba el retraso medio de la línea, que falta
donde no hay otro viaje en la ventana, y rellenado con la persistencia daba una
diferencia de cero en el 89 % de las filas de las líneas pequeñas. Es la tabla que fija
`features.linea_min_viajes` y el criterio de mejora (ADR-018, bitácora 036). Lee
`data/processed/`; nada del pipeline importa de aquí.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from project.config import RAIZ, settings
from project.features import CLAVE_VIAJE, soporte_por_linea

REMUESTRAS = 1000
MEDIDAS = ["mae", "dif_cerca", "dif_lejos"]


def errores(test: pd.DataFrame, obj: str) -> pd.DataFrame:
    """`test` con el error de la persistencia y su diferencia con los dos sustitutos."""
    r, y = test["retraso_s"], test[obj]
    return test.assign(
        mae=(r - y).abs(),
        dif_cerca=(0.9 * r - y).abs() - (r - y).abs(),
        dif_lejos=(0.5 * r - y).abs() - (r - y).abs(),
    )


def medir() -> pd.DataFrame:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    obj = cfg["objetivo"]
    claves = ["linea", *CLAVE_VIAJE]
    train = pd.read_parquet(settings.processed_dir / "train.parquet", columns=claves)
    test = pd.read_parquet(
        settings.processed_dir / "test.parquet",
        columns=[*claves, "retraso_s", obj],
    )
    s = soporte_por_linea(train, test, cfg["linea_min_viajes"], cfg["linea_min_dias"])
    test = errores(test, obj)
    rng = np.random.default_rng(0)
    for linea, g in test.groupby("linea"):
        por_viaje = g.groupby(CLAVE_VIAJE)
        v = por_viaje[MEDIDAS].sum().to_numpy()
        n = por_viaje.size().to_numpy()
        i = rng.integers(0, len(v), size=(REMUESTRAS, len(v)))
        filas = n[i].sum(axis=1)
        s.at[linea, "mae_s"] = g["mae"].mean()
        for k, medida in enumerate(MEDIDAS):
            lo, hi = np.percentile(v[i, k].sum(axis=1) / filas, [2.5, 97.5])
            s.at[linea, f"semi_ic_{medida}_s"] = (hi - lo) / 2
    return s.sort_values("viajes")


if __name__ == "__main__":
    s = medir()
    print(s.round(2).to_string())
    banda = pd.cut(
        s["viajes"], [0, 99, 299, np.inf], labels=["<100", "100-299", ">=300"]
    )
    cols = [f"semi_ic_{m}_s" for m in MEDIDAS]
    print(
        "\n  mediana del semiancho del IC 95 %, en segundos, por viajes en la prueba:"
    )
    print(
        s.groupby(banda, observed=True)[cols]
        .median()
        .round(2)
        .assign(lineas=banda.value_counts())
        .to_string()
    )
