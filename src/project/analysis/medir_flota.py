"""¿Cuánto cubre y cuánto dice la flota como sensor del tramo aguas abajo?

    uv run python -m project.analysis.medir_flota

Sobre `data/processed/{train,test}.parquet` (bitácora 032):

  COBERTURA   fracción de filas con la variable estimada (soporte >= soporte_min),
              en total, por hora local y por línea.
  FLOTA       parte de las filas cuyo tramo (par de paradas) lo recorren dos o más
              líneas: lo que la variable aporta de «red» y no de la propia línea.
  SEÑAL       correlación de Spearman con lo que la persistencia no explica
              (objetivo − retraso actual), junto a las variables de la fase 1.
              Sin modelo: es una comprobación de que hay algo que aprender.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import pandas as pd
import yaml

from project.config import RAIZ, settings


def main() -> None:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    obj = cfg["objetivo"]
    ventanas = cfg["ventanas_flota_min"]
    pd.set_option("display.width", 160)
    for nombre in ("train", "test"):
        t = pd.read_parquet(settings.processed_dir / f"{nombre}.parquet")
        resto = t[obj] - t["retraso_s"]
        print(f"\n=== {nombre}: {len(t):,} filas ===")
        for w in ventanas:
            est = t[f"tramo_ganado_{w}min"].notna()
            print(f"  cobertura {w} min: {est.mean():.1%}")
        w = max(ventanas)
        est = t[f"tramo_ganado_{w}min"].notna()
        hora = t["hora"].astype(int)
        print(f"  cobertura {w} min por hora:")
        print("   ", est.groupby(hora).mean().round(2).to_dict())
        por_linea = est.groupby(t["linea"]).agg(["mean", "size"])
        grandes = por_linea[por_linea["size"] > 5000].sort_values("mean")
        print(f"  cobertura {w} min por línea (> 5.000 filas), extremos:")
        print("   ", grandes["mean"].round(2).head(4).to_dict(), "…")
        print("   ", grandes["mean"].round(2).tail(4).to_dict())

        pares = t.groupby(["stop_id", "linea"]).size().reset_index()
        lineas_por_parada = pares.groupby("stop_id")["linea"].nunique()
        compartida = t["stop_id"].map(lineas_por_parada) >= 2
        print(f"  filas cuya parada la sirven 2+ líneas: {compartida.mean():.1%}")

        print("  Spearman con (objetivo − retraso actual):")
        candidatas = [
            *[f"tramo_ganado_{v}min" for v in ventanas],
            "retraso_delta_s",
            "linea_retraso_15min",
            "bus_anterior_retraso_s",
        ]
        for c in candidatas:
            ok = t[c].notna()
            rho = t.loc[ok, c].corr(resto[ok], method="spearman")
            print(f"    {c:28s} rho = {rho:+.3f}  (n = {ok.sum():,})")

        # ¿Congestión o sesgo del horario? Si el horario se queda corto en un par
        # de paradas, todos los buses ganan retraso ahí a cualquier hora y la
        # variable acierta sin medir tráfico. Quitada la media de cada tramo (y de
        # cada tramo por hora), lo que queda es la parte que varía en el tiempo.
        # Medias sobre el mismo conjunto: es una descomposición, no una variable.
        c = f"tramo_ganado_{w}min"
        ok = t[c].notna()
        d = t.loc[ok, ["stop_id", "stop_objetivo_id", c]].assign(
            resto=resto[ok], hora=hora[ok]
        )
        for claves, etiqueta in (
            (["stop_id", "stop_objetivo_id"], "tramo"),
            (["stop_id", "stop_objetivo_id", "hora"], "tramo × hora"),
        ):
            m_var = d.groupby(claves)[c].transform("mean")
            m_res = d.groupby(claves)["resto"].transform("mean")
            rho = (d[c] - m_var).corr(d["resto"] - m_res, method="spearman")
            print(f"    {c} sin la media por {etiqueta:14s} rho = {rho:+.3f}")


if __name__ == "__main__":
    main()
