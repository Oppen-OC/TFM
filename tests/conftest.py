"""Fixtures compartidas de los tests del TFM.

`fixtures.json` tiene la forma EXACTA de los payloads reales capturados el
15/08/2026. No son ejemplos inventados: se copiaron de la respuesta real de
cada servicio, con sus rarezas dentro. Esa es la razón de que estos tests
detecten regresiones que un mock limpio no vería.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

AQUI = Path(__file__).resolve().parent


@pytest.fixture(scope="session")
def fix() -> dict:
    """Payloads reales de las cinco fuentes, más los bloques de gid."""
    return json.loads((AQUI / "fixtures.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def flota_simulada() -> pd.DataFrame:
    """60 buses con verdad-terreno conocida, 20 snapshots cada 30 s.

    Cada fila lleva la columna `verdad` con el bus real que la generó. Sin eso
    no se puede medir si el tracker recupera la identidad: es la única forma de
    distinguir "reconstruyó 60 trayectorias" de "reconstruyó 60 trayectorias
    CORRECTAS", que es lo que hundió la trampa 004.
    """
    rng = np.random.default_rng(7)
    n_buses, n_snaps, dt = 60, 20, 30.0
    lineas = [(f"L{i % 8}", "Ida" if i % 2 else "Vuelta") for i in range(n_buses)]
    lat = 39.46 + rng.normal(0, 0.02, n_buses)
    lon = -0.37 + rng.normal(0, 0.02, n_buses)
    rumbo = rng.uniform(0, 2 * np.pi, n_buses)
    vel = rng.uniform(3, 30, n_buses)  # km/h realistas para bus urbano

    filas = []
    t0 = pd.Timestamp("2026-08-15T19:00:00Z")
    for s in range(n_snaps):
        paso = vel / 3.6 * dt
        lat = lat + np.cos(rumbo) * paso / 111_320
        lon = lon + np.sin(rumbo) * paso / (111_320 * np.cos(np.radians(lat)))
        rumbo += rng.normal(0, 0.15, n_buses)
        for i in range(n_buses):
            filas.append(
                {
                    "snapshot_id": 1000 + s,
                    "gid": 1000 + s * n_buses + i,
                    "linea": lineas[i][0],
                    "trayecto": lineas[i][1],
                    "lat": lat[i],
                    "lon": lon[i],
                    "ts_utc": t0 + pd.Timedelta(seconds=s * dt),
                    "verdad": f"bus{i:03d}",
                }
            )
    sim = pd.DataFrame(filas)
    # El orden de llegada se baraja dentro de cada snapshot, como en la fuente
    # real. Barajar es deliberado: es lo que destapa un reenganche por posición
    # de fila en vez de por identidad (trampa 004).
    return (
        sim.sample(frac=1, random_state=3)
        .sort_values("snapshot_id")
        .reset_index(drop=True)
    )
