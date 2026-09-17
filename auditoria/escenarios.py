"""Decisión 2c: ¿cambia el resultado del tracker si la flota simulada se parece
más a la real?

    uv run python auditoria/escenarios.py
    uv run python auditoria/escenarios.py --semillas 7,11 --snaps 40

`project.analysis.simulacion.simular_flota` no se toca: sus valores fijan los
umbrales de los tests y las cifras de la bitácora. Aquí se reimplementa el mismo
generador con fenómenos opcionales que la captura real muestra y la simulación
omite, medidos por `project.analysis.auditar_supuestos`:

  paradas     el bus se detiene 1-3 sondeos (semáforo, parada). Real: ~30 % de
              los pasos por debajo de 1,2 km/h; simulado: 0 %.
  ruido_gps   error de posición gaussiano, en metros, sobre lo OBSERVADO; el
              movimiento real sigue limpio. Real: pasos parados de 2 m (p50).
  giros       con probabilidad por paso, giro de 90° como en una esquina.
              Real: p90 del cambio de rumbo ~58°; simulado: ~14°.
  jitter_dt   el sondeo no llega cada 30 s exactos. Real: p99 ~34 s.

Con todo apagado, `generar()` es idéntico a `simular_flota()` fila a fila: es
el control que hace comparables los escenarios. Los fenómenos usan un generador
aleatorio aparte para no alterar la secuencia del original.

Criterio de la decisión 2c, por fenómeno y con varias semillas:
  inocuo    0 saltos, 0 trayectorias contaminadas y fragmentación 1,00
  hallazgo  cualquier otra cosa: los tests verdes no cubrían ese fenómeno
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from project.analysis.auditar_supuestos import medidas, resumir
from project.analysis.medir_tracking import medir
from project.analysis.simulacion import (
    DT_S,
    N_BUSES,
    N_SNAPS,
    SEMILLA,
    SEMILLA_BARAJADO,
    simular_flota,
)
from project.tracking import rastrear

AQUI = Path(__file__).resolve().parent


def generar(
    n_buses: int = N_BUSES,
    n_snaps: int = N_SNAPS,
    dt: float = DT_S,
    semilla: int = SEMILLA,
    semilla_barajado: int = SEMILLA_BARAJADO,
    p_parada: float = 0.0,
    ruido_gps_m: float = 0.0,
    p_giro: float = 0.0,
    jitter_dt_s: float = 0.0,
) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    extra = np.random.default_rng(semilla + 10_000)
    lineas = [(f"L{i % 8}", "Ida" if i % 2 else "Vuelta") for i in range(n_buses)]
    lat = 39.46 + rng.normal(0, 0.02, n_buses)
    lon = -0.37 + rng.normal(0, 0.02, n_buses)
    rumbo = rng.uniform(0, 2 * np.pi, n_buses)
    vel = rng.uniform(3, 30, n_buses)
    parado_resta = np.zeros(n_buses, dtype=int)

    filas = []
    t0 = pd.Timestamp("2026-08-15T19:00:00Z")
    reloj = 0.0
    for s in range(n_snaps):
        if p_parada:
            empieza = (parado_resta == 0) & (extra.random(n_buses) < p_parada)
            parado_resta[empieza] = extra.integers(1, 4, empieza.sum())
        moviendo = parado_resta == 0 if p_parada else np.ones(n_buses, bool)
        paso = vel / 3.6 * dt * moviendo
        lat = lat + np.cos(rumbo) * paso / 111_320
        lon = lon + np.sin(rumbo) * paso / (111_320 * np.cos(np.radians(lat)))
        rumbo += rng.normal(0, 0.15, n_buses)
        if p_giro:
            gira = extra.random(n_buses) < p_giro
            rumbo[gira] += extra.choice([-np.pi / 2, np.pi / 2], gira.sum())
        if p_parada:
            parado_resta = np.maximum(parado_resta - 1, 0)

        obs_lat, obs_lon = lat, lon
        if ruido_gps_m:
            obs_lat = lat + extra.normal(0, ruido_gps_m, n_buses) / 111_320
            obs_lon = lon + extra.normal(0, ruido_gps_m, n_buses) / (
                111_320 * np.cos(np.radians(lat))
            )
        instante = s * dt
        if jitter_dt_s:
            reloj = max(reloj + 1.0, instante + extra.uniform(0, jitter_dt_s))
            instante = reloj
        for i in range(n_buses):
            filas.append(
                {
                    "snapshot_id": 1000 + s,
                    "gid": 1000 + s * n_buses + i,
                    "linea": lineas[i][0],
                    "trayecto": lineas[i][1],
                    "lat": obs_lat[i],
                    "lon": obs_lon[i],
                    "ts_utc": t0 + pd.Timedelta(seconds=instante),
                    "verdad": f"bus{i:03d}",
                }
            )
    sim = pd.DataFrame(filas)
    sim = sim.sample(frac=1, random_state=semilla_barajado).sort_values("snapshot_id")
    return sim.reset_index(drop=True)


def control() -> None:
    a, b = generar(), simular_flota()
    if not a.equals(b):
        sys.exit(
            "CONTROL FALLIDO: generar() sin fenómenos no reproduce simular_flota()"
        )
    print("  control: generar() sin fenómenos == simular_flota()")


# Calibrado contra `auditoria/resultados/supuestos_fc5d15c.json` (laborables):
# parado 0,29 · ruido p50 2,0 m / p90 6,7 m · giro p90 57° · dt p99 33 s. Con
# estos valores, `todos` da parado 0,30 · ruido 3,3 / 6,0 m · dt p99 32 s. El
# giro p90 es muy sensible a `p_giro` (0,08 da 21°, 0,12 da 81°): 0,10 queda
# en medio. `estres` duplica cada fenómeno para ver si hay margen.
FENOMENOS = {
    "paradas": {"p_parada": 0.17},
    "ruido_gps": {"ruido_gps_m": 2.0},
    "giros": {"p_giro": 0.10},
    "jitter_dt": {"jitter_dt_s": 3.0},
}
FENOMENOS["todos"] = {k: v for d in FENOMENOS.values() for k, v in d.items()}
FENOMENOS["estres"] = {
    "p_parada": 0.30,
    "ruido_gps_m": 5.0,
    "p_giro": 0.20,
    "jitter_dt_s": 6.0,
}


def main(semillas: list[int], snaps: list[int], salida: Path | None) -> None:
    control()
    filas = []
    for nombre, kw in {"ninguno": {}, **FENOMENOS}.items():
        for n in snaps:
            for s in semillas:
                sim = generar(n_snaps=n, semilla=s, **kw)
                m = medir(sim, predictivo=True)
                cal = resumir(medidas(rastrear(sim.drop(columns=["verdad"]))))
                filas.append(
                    {
                        "escenario": nombre,
                        "snaps": n,
                        "semilla": s,
                        "saltos": m["saltos"],
                        "contaminadas": round(m["contaminadas"], 4),
                        "cola": round(m["cola"], 4),
                        "fragmentacion": round(m["fragmentacion"], 3),
                        "parado": cal["parado"],
                        "ruido_m_p50": cal["ruido_m_p50"],
                        "giro_deg_p90": cal["giro_deg_p90"],
                        "dt_s_p99": cal["dt_s_p99"],
                    }
                )
                print(
                    f"  {nombre:<10} snaps={n:<4} semilla={s:<4} "
                    f"saltos={m['saltos']:<3} contam={m['contaminadas']:.1%} "
                    f"frag={m['fragmentacion']:.2f}",
                    flush=True,
                )
    df = pd.DataFrame(filas)
    resumen = df.groupby("escenario").agg(
        saltos=("saltos", "sum"),
        contaminadas_max=("contaminadas", "max"),
        fragmentacion_max=("fragmentacion", "max"),
        parado=("parado", "mean"),
        ruido_m_p50=("ruido_m_p50", "mean"),
        giro_deg_p90=("giro_deg_p90", "mean"),
        dt_s_p99=("dt_s_p99", "mean"),
    )
    resumen["veredicto"] = np.where(
        (resumen["saltos"] == 0)
        & (resumen["contaminadas_max"] == 0)
        & (resumen["fragmentacion_max"] <= 1.0),
        "inocuo",
        "hallazgo",
    )
    with pd.option_context("display.width", 160):
        print("\n" + resumen.to_string())
    if salida:
        salida.write_text(
            json.dumps(
                {
                    "semillas": semillas,
                    "snaps": snaps,
                    "fenomenos": FENOMENOS,
                    "resumen": resumen.reset_index().to_dict(orient="records"),
                    "detalle": filas,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--semillas", default="7,11,23,42,101")
    p.add_argument("--snaps", default="20,80")
    p.add_argument("--json", type=Path, default=None)
    a = p.parse_args()
    main(
        [int(x) for x in a.semillas.split(",")],
        [int(x) for x in a.snaps.split(",")],
        a.json,
    )
