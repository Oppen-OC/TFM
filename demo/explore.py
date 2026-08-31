"""Exploración one-shot de los endpoints: esquema, muestra y salud de cada fuente.

    python explore.py            # todas las fuentes
    python explore.py emt_buses  # una concreta

No escribe nada. Es lo primero que debes ejecutar para comprobar que las
cinco fuentes siguen vivas desde tu red.
"""

from __future__ import annotations

import json
import sys

import httpx
import pandas as pd

from sources import SOURCES, now_utc, parse

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 40)

HEADERS = {"User-Agent": "TFM-UPV-BigData/0.1 (investigacion academica)"}


def fetch(url: str) -> dict:
    with httpx.Client(timeout=20, headers=HEADERS, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.json()


def explore(key: str) -> None:
    src = SOURCES[key]
    print("=" * 78)
    print(f"  {key}   ({', '.join(src.tags)})")
    print("=" * 78)
    print(f"URL       : {src.url[:110]}")
    print(f"Periodo   : cada {src.period_s} s")
    print(f"Nota      : {src.notes}")

    ts = now_utc()
    try:
        payload = fetch(src.url)
    except Exception as exc:  # noqa: BLE001
        print(f"\n  !! FALLO: {type(exc).__name__}: {exc}\n")
        return

    raw_bytes = len(json.dumps(payload))
    df = parse(key, payload, ts)

    print(f"\nPayload   : {raw_bytes / 1024:,.1f} KiB")
    print(f"Filas     : {len(df)}")
    if df.empty:
        print("  (sin filas: puede ser horario nocturno o servicio caído)\n")
        return

    print(f"Columnas  : {list(df.columns)}")

    if "latencia_s" in df:
        lat = df["latencia_s"].describe(percentiles=[0.5, 0.9])
        print(
            f"Latencia  : p50={lat['50%']:.0f}s  p90={lat['90%']:.0f}s  max={lat['max']:.0f}s"
        )
    elif "ts_utc" in df and df["ts_utc"].notna().any():
        lag = (ts - pd.to_datetime(df["ts_utc"], utc=True)).dt.total_seconds()
        print(f"Latencia  : p50={lag.median():.0f}s  max={lag.max():.0f}s")

    nulos = df.isna().mean().sort_values(ascending=False)
    nulos = nulos[nulos > 0]
    if len(nulos):
        print("Nulos     : " + ", ".join(f"{c}={v:.0%}" for c, v in nulos.items()))

    # Volumen proyectado si capturas a la cadencia recomendada
    por_dia = len(df) * (86400 / src.period_s)
    print(
        f"Volumen   : ~{por_dia:,.0f} filas/día  ->  ~{por_dia * 90 / 1e6:,.1f} M filas en 3 meses"
    )

    print("\nMuestra:")
    print(df.head(3).to_string(index=False, max_colwidth=26))
    print()


if __name__ == "__main__":
    claves = sys.argv[1:] or list(SOURCES)
    for k in claves:
        if k not in SOURCES:
            print(f"Fuente desconocida: {k}. Disponibles: {list(SOURCES)}")
            continue
        explore(k)
