"""¿Casa la captura real con los trazados del GTFS? Validación del map-matching.

    uv run python -m project.analysis.validar_mapmatching                  # 17 días
    uv run python -m project.analysis.validar_mapmatching --dias 2026-08-26 --procesos 1

Por jornada (filtrada por `ts_ingest_utc`, no por partición: entrada 011 de la
bitácora): `rastrear` + `mapmatching.emparejar`, y se mide

  por día      posiciones, % sin trazado, % sin trayecto, % fuera de ruta,
               % ambiguas, distancia al trazado p50/p90/p95/p99, segundos
  por grupo    (línea, trayecto): trazado elegido, distancia mediana, fracción
               de pasos que avanzan sobre él y sobre el mejor alternativo, y el
               margen de distancia frente al segundo candidato

La pregunta de fondo es doble. Si el método funciona: la distancia típica debe
estar en el orden del ruido GPS (1,8 m medidos en la línea 31, notebook 06) y
los vehículos deben AVANZAR sobre el trazado elegido. Y si el feed vale para
toda la captura: nueve de los diecisiete días son anteriores a su vigencia
declarada (24/08), así que la distancia se compara antes y después.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from project.config import settings
from project.gtfs import a_metros, cargar_trazados
from project.mapmatching import FUERA_DE_RUTA_M, emparejar, puntuar_candidatos
from project.tracking import rastrear

DIAS = [f"2026-08-{d:02d}" for d in range(15, 32)]


def cargar_dia(dia: str) -> pd.DataFrame:
    desde = pd.Timestamp(f"{dia}T00:00:00Z")
    hasta = desde + pd.Timedelta(days=1)
    patron = (settings.curated_dir / "source=emt_buses" / "*" / "*.parquet").as_posix()
    return duckdb.sql(
        f"""
        select snapshot_id, linea, trayecto, lat, lon, ts_utc
        from read_parquet('{patron}', hive_partitioning = false)
        where ts_ingest_utc >= '{desde.isoformat()}' and ts_ingest_utc < '{hasta.isoformat()}'
          and lat is not null and lon is not null
        """
    ).df()


def _grupos(out: pd.DataFrame, trazados: dict) -> list[dict]:
    """Diagnóstico por (línea, trayecto): cómo de clara fue la elección."""
    filas = []
    con = out[out["shape_id"].notna()]
    for (linea, trayecto), g in con.groupby(["linea", "trayecto"], sort=False):
        x, y = a_metros(g["lat"].to_numpy(), g["lon"].to_numpy())
        cand = puntuar_candidatos(g, x, y, trazados[str(linea)])
        elegido, otro = cand[0], (cand[1] if len(cand) > 1 else None)

        def r(v, nd=3):
            return None if v is None or np.isnan(v) else round(float(v), nd)

        filas.append(
            {
                "linea": linea,
                "trayecto": trayecto,
                "shape_id": elegido["trazado"].shape_id,
                "posiciones": len(g),
                "candidatos": len(cand),
                "cobertura": r(elegido["cobertura"]),
                "dist_mediana_m": r(elegido["dist_mediana_m"], 1),
                "avanza": r(elegido["avanza"]),
                "cobertura_otro": r(otro["cobertura"]) if otro else None,
                "avanza_otro": r(otro["avanza"]) if otro else None,
                "fuera_de_ruta": r(g["fuera_de_ruta"].astype(float).mean(), 4),
                "ambigua": r(g["ambigua"].astype(float).mean(), 4),
            }
        )
    return filas


def validar_dia(dia: str) -> dict:
    trazados = cargar_trazados()
    df = cargar_dia(dia)
    t0 = time.time()
    tr = rastrear(df)
    t1 = time.time()
    out = emparejar(tr, trazados)
    t2 = time.time()
    d = out["dist_trazado_m"].dropna()
    n = len(out)

    # ¿Dónde y cuándo está lo que queda fuera de ruta? Si se concentra en pocas
    # celdas de ~100 m (cocheras, cabeceras de regulación) y de madrugada, no es
    # error del map-matching: es el bus fuera de servicio publicando su línea.
    con = out[out["shape_id"].notna()]
    fuera = con[con["fuera_de_ruta"].astype(bool)]
    celdas = pd.Series(
        list(zip((fuera["lat"] * 1000).round(), (fuera["lon"] * 1000).round()))
    ).value_counts()
    hora = con["ts_utc"].dt.tz_convert(settings.tz_local).dt.hour
    fuera_por_hora = con["fuera_de_ruta"].astype(float).groupby(hora).mean()
    explicacion = {
        "fuera_en_top10_celdas": round(
            float(celdas.head(10).sum() / max(len(fuera), 1)), 3
        ),
        "top3_celdas": [
            (a / 1000, b / 1000, int(k)) for (a, b), k in celdas.head(3).items()
        ],
        "fuera_0_a_6h": round(float(fuera_por_hora.loc[0:6].mean()), 3),
        "fuera_7_a_22h": round(float(fuera_por_hora.loc[7:22].mean()), 3),
    }
    return {
        "dia": dia,
        "posiciones": n,
        "sin_trazado": round(float((out["motivo"] == "sin_trazado").mean()), 4),
        "sin_trayecto": round(float((out["motivo"] == "sin_trayecto").mean()), 5),
        "fuera_de_ruta": round(float(out["fuera_de_ruta"].astype(float).mean()), 4),
        "ambigua": round(float(out["ambigua"].astype(float).mean()), 4),
        "dist_p50_m": round(float(d.quantile(0.5)), 1),
        "dist_p90_m": round(float(d.quantile(0.9)), 1),
        "dist_p95_m": round(float(d.quantile(0.95)), 1),
        "dist_p99_m": round(float(d.quantile(0.99)), 1),
        "seg_rastrear": round(t1 - t0, 1),
        "seg_emparejar": round(t2 - t1, 1),
        **{k: v for k, v in explicacion.items() if k != "top3_celdas"},
        "top3_celdas": str(explicacion["top3_celdas"]),
        "grupos": _grupos(out, trazados),
    }


def main(dias: list[str], procesos: int, salida: Path | None) -> None:
    with ProcessPoolExecutor(max_workers=procesos) as ex:
        resultados = list(ex.map(validar_dia, dias))

    resumen = pd.DataFrame(
        [{k: v for k, v in r.items() if k != "grupos"} for r in resultados]
    )
    resumen["antes_de_vigencia"] = resumen["dia"] < "2026-08-24"
    grupos = pd.DataFrame(
        [{"dia": r["dia"], **g} for r in resultados for g in r["grupos"]]
    )
    with pd.option_context("display.width", 220, "display.max_rows", 400):
        print(resumen.to_string(index=False))
        print("\n  Antes y después de la vigencia del feed (24/08):")
        print(
            resumen.groupby("antes_de_vigencia")[
                ["fuera_de_ruta", "ambigua", "dist_p50_m", "dist_p95_m"]
            ]
            .mean()
            .round(4)
            .to_string()
        )
        estable = grupos.groupby(["linea", "trayecto"])["shape_id"].nunique()
        print(
            f"\n  Grupos con trazado distinto según el día: {int((estable > 1).sum())} de {len(estable)}"
        )
        agregado = grupos.groupby(["linea", "trayecto", "shape_id"]).agg(
            dias=("dia", "nunique"),
            posiciones=("posiciones", "sum"),
            cobertura=("cobertura", "median"),
            dist_mediana_m=("dist_mediana_m", "median"),
            avanza=("avanza", "median"),
            cobertura_otro=("cobertura_otro", "median"),
            avanza_otro=("avanza_otro", "median"),
            fuera_de_ruta=("fuera_de_ruta", "mean"),
        )
        grandes = agregado[agregado["posiciones"] >= 1000]
        print(
            f"\n  Grupos con >= 1.000 posiciones: {len(grandes)} de {len(agregado)}, "
            f"con el {grandes['posiciones'].sum() / agregado['posiciones'].sum():.2%} "
            "de las posiciones. Sospechosos (cobertura < 0,8, distancia > 10 m o "
            "avance < 0,8):"
        )
        sospechosos = grandes[
            (grandes["cobertura"] < 0.8)
            | (grandes["dist_mediana_m"] > 10)
            | (grandes["avanza"] < 0.8)
        ]
        print(sospechosos.round(3).to_string())
    if salida:
        salida.write_text(
            json.dumps(
                {
                    "fuera_de_ruta_m": FUERA_DE_RUTA_M,
                    "dias": resumen.to_dict(orient="records"),
                    "grupos": agregado.reset_index().to_dict(orient="records"),
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dias", nargs="*", default=DIAS)
    p.add_argument("--procesos", type=int, default=9)
    p.add_argument("--json", type=Path, default=None)
    a = p.parse_args()
    main(a.dias, a.procesos, a.json)
