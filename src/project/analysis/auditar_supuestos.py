"""¿Se parece la flota simulada a la EMT real en lo que importa al tracker?

    uv run python -m project.analysis.auditar_supuestos
    uv run python -m project.analysis.auditar_supuestos --dias 2026-08-27 --horas 8

Los tests de tracking y las cifras de la bitácora se miden sobre
`project.analysis.simulacion`, y el tracker se ajustó contra esa misma flota. Si
la simulación omite un fenómeno real que rompe el emparejamiento, los tests
salen verdes sin demostrar nada. Este script pone cada supuesto de la simulación
frente a la captura real, con el MISMO instrumento en los dos lados:

  vel_kmh        velocidad por refresco (`dist_m / dt_s`), p10 / p50 / p90
  parado         fracción de pasos por debajo de 1,2 km/h (10 m en 30 s)
  giro_deg       cambio de rumbo entre dos pasos consecutivos del mismo
                 vehículo, solo con ambos pasos por encima de 20 m
  vecino_m       distancia al vehículo más cercano de su (línea, trayecto)
  empate         fracción de posiciones con ese vecino más cerca que el propio
                 paso: la condición del empate exacto (trampa 007)
  grupo          vehículos por (sondeo, línea, trayecto), p50 / p90
  dt_s           duración del paso entre sondeos, p50 / p99, y fracción fuera
                 de 30 ± 5 s
  ruido_m        desplazamiento mediano de los pasos "parados": cota superior
                 del ruido de posición, que la simulación supone cero

Lo real se mide en ventanas de una hora dentro del horario de servicio (07-22
local), sobre los 13 días completos de captura, separando laborables de fin de
semana. Ventanas y no jornadas enteras: `rastrear` es un bucle por sondeo y una
jornada tarda minutos; cuatro horas repartidas por día cubren punta, valle y
tarde. Las magnitudes se leen del resultado de `rastrear`, así que heredan sus
errores de identidad: sobre la flota simulada esos errores son 0, y en real el
1,9 % de empates acota cuánto pueden mover una mediana.

Las ventanas se filtran por `ts_ingest_utc` sobre todas las particiones: la
partición `date=` no es fiable en los primeros 30 min UTC de cada día
(`auditar_persistencia`, columna `cruce_particion`).

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from project.analysis.simulacion import simular_flota
from project.config import settings
from project.ingest.sources import haversine_m
from project.tracking import rastrear

DIAS = [
    "2026-08-16",
    "2026-08-17",
    "2026-08-19",
    "2026-08-20",
    "2026-08-22",
    "2026-08-23",
    "2026-08-24",
    "2026-08-25",
    "2026-08-26",
    "2026-08-27",
    "2026-08-28",
    "2026-08-29",
    "2026-08-30",
]
HORAS_LOCALES = (8, 11, 14, 18)
PARADO_KMH = 1.2
GIRO_MIN_M = 20.0


def cargar_ventana(dia: str, hora_local: int) -> pd.DataFrame:
    desde = pd.Timestamp(f"{dia} {hora_local:02d}:00", tz=settings.tz_local).tz_convert(
        "UTC"
    )
    hasta = desde + pd.Timedelta(hours=1)
    patron = (settings.curated_dir / "source=emt_buses" / "*" / "*.parquet").as_posix()
    return duckdb.sql(
        f"""
        select snapshot_id, linea, trayecto, lat, lon, ts_utc, ts_ingest_utc
        from read_parquet('{patron}', hive_partitioning = false)
        where ts_ingest_utc >= '{desde.isoformat()}' and ts_ingest_utc < '{hasta.isoformat()}'
          and lat is not null and lon is not null
        """
    ).df()


def medidas(out: pd.DataFrame) -> dict[str, np.ndarray]:
    """Magnitudes crudas de una salida de `rastrear`."""
    tr = out.dropna(subset=["dist_m", "dt_s"]).copy()
    tr = tr[tr["dt_s"] > 0]
    vel = (tr["dist_m"] / tr["dt_s"] * 3.6).to_numpy()

    # Rumbo de cada paso, por vehículo y en orden de sondeo.
    o = out.sort_values(["vehicle_id", "snapshot_id"], kind="stable")
    lat, lon = o["lat"].to_numpy(), o["lon"].to_numpy()
    mismo = o["vehicle_id"].to_numpy()[1:] == o["vehicle_id"].to_numpy()[:-1]
    dy = (lat[1:] - lat[:-1]) * 111_320
    dx = (lon[1:] - lon[:-1]) * 111_320 * np.cos(np.radians(lat[1:]))
    largo = np.hypot(dx, dy)
    rumbo = np.degrees(np.arctan2(dy, dx))
    valido = mismo & (largo > GIRO_MIN_M)
    giro = np.abs((rumbo[1:] - rumbo[:-1] + 180) % 360 - 180)
    giro = giro[valido[1:] & valido[:-1]]

    # Vecino más cercano de la misma (línea, trayecto) en el mismo sondeo.
    vecino = np.full(len(out), np.nan)
    posiciones = {ix: k for k, ix in enumerate(out.index)}
    for _, g in out.groupby(["snapshot_id", "linea", "trayecto"], sort=False):
        if len(g) < 2:
            continue
        la, lo = g["lat"].to_numpy(), g["lon"].to_numpy()
        d = haversine_m(la[:, None], lo[:, None], la[None, :], lo[None, :])
        np.fill_diagonal(d, np.inf)
        vecino[[posiciones[i] for i in g.index]] = d.min(axis=1)
    paso = out["dist_m"].to_numpy()
    con_ambos = ~np.isnan(vecino) & ~np.isnan(paso)

    grupo = out.groupby(["snapshot_id", "linea", "trayecto"]).size().to_numpy()
    reloj = out.groupby("snapshot_id")["ts_utc"].max().sort_index()
    dt = reloj.diff().dt.total_seconds().dropna().to_numpy()

    parado = vel < PARADO_KMH
    return {
        "vel_kmh": vel,
        "parado": parado.astype(float),
        "ruido_m": tr["dist_m"].to_numpy()[parado],
        "giro_deg": giro,
        "vecino_m": vecino[~np.isnan(vecino)],
        "empate": (vecino[con_ambos] < paso[con_ambos]).astype(float),
        "grupo": grupo.astype(float),
        "dt_s": dt,
        "dt_fuera": (np.abs(dt - 30) > 5).astype(float),
    }


def resumir(m: dict[str, np.ndarray]) -> dict[str, float]:
    def q(x, p):
        return round(float(np.quantile(x, p)), 2) if len(x) else float("nan")

    return {
        "vel_kmh_p10": q(m["vel_kmh"], 0.1),
        "vel_kmh_p50": q(m["vel_kmh"], 0.5),
        "vel_kmh_p90": q(m["vel_kmh"], 0.9),
        "parado": round(float(m["parado"].mean()), 4),
        "ruido_m_p50": q(m["ruido_m"], 0.5),
        "ruido_m_p90": q(m["ruido_m"], 0.9),
        "giro_deg_p50": q(m["giro_deg"], 0.5),
        "giro_deg_p90": q(m["giro_deg"], 0.9),
        "vecino_m_p10": q(m["vecino_m"], 0.1),
        "vecino_m_p50": q(m["vecino_m"], 0.5),
        "empate": round(float(m["empate"].mean()), 4)
        if len(m["empate"])
        else float("nan"),
        "grupo_p50": q(m["grupo"], 0.5),
        "grupo_p90": q(m["grupo"], 0.9),
        "dt_s_p50": q(m["dt_s"], 0.5),
        "dt_s_p99": q(m["dt_s"], 0.99),
        "dt_fuera": round(float(m["dt_fuera"].mean()), 4)
        if len(m["dt_fuera"])
        else float("nan"),
        "n_pasos": int(len(m["vel_kmh"])),
    }


def _juntar(trozos: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    return {k: np.concatenate([t[k] for t in trozos]) for k in trozos[0]}


def filas_hueco_192(dias: list[str]) -> dict[str, float]:
    """Filas sin idtramo por payload de la capa 192, leídas del crudo."""
    from project.ingest.sources import read_raw

    huecos, totales = [], []
    for dia in dias:
        ruta = (
            settings.raw_dir
            / "source=trafico_estado"
            / f"date={dia}"
            / "payloads.ndjson.gz"
        )
        if not ruta.exists():
            continue
        for _, payload in read_raw(ruta):
            feats = payload.get("features") or []
            if not feats:
                continue
            totales.append(len(feats))
            huecos.append(
                sum(
                    1
                    for f in feats
                    if (f.get("attributes") or {}).get("idtramo") is None
                )
            )
    h, t = np.array(huecos), np.array(totales)
    return {
        "payloads": int(len(t)),
        "filas_p50": float(np.median(t)),
        "hueco_p50": float(np.median(h)),
        "hueco_min": int(h.min()),
        "hueco_max": int(h.max()),
        "utiles_p50": float(np.median(t - h)),
    }


def main(dias: list[str], horas: tuple[int, ...], salida: Path | None) -> None:
    informe: dict[str, object] = {"dias": dias, "horas_locales": list(horas)}

    sim = simular_flota()
    informe["simulacion"] = resumir(medidas(rastrear(sim.drop(columns=["verdad"]))))

    por_tipo: dict[str, list[dict[str, np.ndarray]]] = {
        "laborable": [],
        "fin_de_semana": [],
    }
    for dia in dias:
        tipo = "fin_de_semana" if pd.Timestamp(dia).dayofweek >= 5 else "laborable"
        for h in horas:
            df = cargar_ventana(dia, h)
            if df["snapshot_id"].nunique() < 10:
                print(f"  {dia} {h:02d}h: ventana vacía, se omite", flush=True)
                continue
            por_tipo[tipo].append(medidas(rastrear(df)))
            print(
                f"  {dia} {h:02d}h ({tipo}): {df['snapshot_id'].nunique()} sondeos",
                flush=True,
            )
    for tipo, trozos in por_tipo.items():
        if trozos:
            informe[tipo] = resumir(_juntar(trozos))

    informe["capa_192"] = filas_hueco_192(dias)

    tabla = pd.DataFrame(
        {
            k: informe[k]
            for k in ("simulacion", "laborable", "fin_de_semana")
            if k in informe
        }
    )
    with pd.option_context("display.width", 160):
        print("\n" + tabla.to_string())
    print(f"\n  capa 192: {informe['capa_192']}")
    if salida:
        salida.write_text(
            json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dias", nargs="*", default=DIAS)
    p.add_argument("--horas", nargs="*", type=int, default=list(HORAS_LOCALES))
    p.add_argument("--json", type=Path, default=None)
    a = p.parse_args()
    main(a.dias, tuple(a.horas), a.json)
