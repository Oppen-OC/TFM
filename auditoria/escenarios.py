"""Decisión 2c: ¿cambia el resultado del tracker si la flota simulada se parece
más a la real?

    uv run python auditoria/escenarios.py
    uv run python auditoria/escenarios.py --semillas 7,11 --snaps 40

Los fenómenos que la captura real muestra y la flota por defecto omite viven
como parámetros de `project.analysis.simulacion.simular_flota`, apagados por
defecto, medidos por `project.analysis.auditar_supuestos`:

  paradas     el bus se detiene 1-3 sondeos (semáforo, parada). Real: ~29 % de
              los pasos por debajo de 1,2 km/h; simulado: 0 %.
  ruido_gps   error de posición gaussiano, en metros, sobre lo OBSERVADO; el
              movimiento real sigue limpio. Real: pasos parados de 2 m (p50).
  giros       con probabilidad por paso, giro de 90° como en una esquina.
              Real: p90 del cambio de rumbo ~57°; simulado: ~14°.
  jitter_dt   el sondeo no llega cada 30 s exactos. Real: p99 ~33 s.

Hasta 32d78a1 el generador estaba duplicado aquí; al moverlo se comprobó que
ambos daban la misma flota fila a fila en todas las configuraciones de abajo, y
que la flota por defecto no cambiaba respecto a fc5d15c.

Criterio de la decisión 2c, por fenómeno y con varias semillas:
  inocuo    0 saltos, 0 trayectorias contaminadas y fragmentación 1,00
  hallazgo  cualquier otra cosa: los tests verdes no cubrían ese fenómeno
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from project.analysis.auditar_supuestos import medidas, resumir
from project.analysis.medir_tracking import medir
from project.analysis.simulacion import simular_flota
from project.tracking import rastrear

AQUI = Path(__file__).resolve().parent


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
    filas = []
    for nombre, kw in {"ninguno": {}, **FENOMENOS}.items():
        for n in snaps:
            for s in semillas:
                sim = simular_flota(n_snaps=n, semilla=s, **kw)
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
