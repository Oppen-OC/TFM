"""¿Está completa la captura? Sondeos por día y huecos del crudo, solo lectura.

    uv run python -m project.analysis.medir_completitud --desde 2026-10-06
    uv run python -m project.analysis.medir_completitud --raw C:/Users/oppen/copia-tfm/raw

Por fuente y día de captura (UTC, la partición `date=` de `append_raw`): sondeos
guardados frente a los que da la cadencia de `SOURCES`, y los huecos entre dos
sondeos seguidos por encima del umbral. Cuenta el crudo, no el curated: incluye
los sondeos repetidos, como los contadores `ok + dup` del colector.

Es la cifra que decide si un día de la prueba es útil (ADR-024, nota del 11/10).
Con `--raw` mide una copia fuera del repo sin traerla a `data/raw/`.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from project.config import settings
from project.ingest.sources import SOURCES, read_raw


def instantes(
    raw: Path, fuente: str, desde: str, hasta: str | None
) -> list[pd.Timestamp]:
    ts = []
    for f in sorted((raw / f"source={fuente}").glob("date=*/payloads.ndjson.gz")):
        dia = f.parent.name.removeprefix("date=")
        if dia < desde or (hasta and dia > hasta):
            continue
        ts += [t for t, _ in read_raw(f)]
    return sorted(ts)


def huecos(
    ts: list[pd.Timestamp], umbral: pd.Timedelta
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    return [(a, b) for a, b in zip(ts, ts[1:]) if b - a > umbral]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, default=settings.raw_dir)
    p.add_argument("--desde", default="0000-00-00")
    p.add_argument("--hasta", default=None)
    p.add_argument("--fuentes", nargs="*", default=["emt_buses", "trafico_estado"])
    p.add_argument("--umbral-min", type=float, default=15)
    a = p.parse_args()

    for fuente in a.fuentes:
        ts = instantes(a.raw, fuente, a.desde, a.hasta)
        if not ts:
            print(f"{fuente}: sin sondeos")
            continue
        posibles = 86400 // SOURCES[fuente].period_s
        print(
            f"{fuente}: {len(ts):,} sondeos, {ts[0]:%m-%d %H:%M:%S} -> {ts[-1]:%m-%d %H:%M:%S} UTC"
        )
        for dia, n in sorted(Counter(f"{t:%Y-%m-%d}" for t in ts).items()):
            print(f"  {dia}  {n:>5} de {posibles}")
        for x, y in huecos(ts, pd.Timedelta(minutes=a.umbral_min)):
            print(
                f"  hueco {x:%m-%d %H:%M} -> {y:%m-%d %H:%M} UTC  {(y - x).total_seconds() / 60:.0f} min"
            )


if __name__ == "__main__":
    main()
