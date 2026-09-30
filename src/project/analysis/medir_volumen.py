"""¿Cuánto publica al día cada fuente? Volumen del crudo, solo lectura.

    uv run python -m project.analysis.medir_volumen
    uv run python -m project.analysis.medir_volumen --dias 2026-09-16

Por fuente y día de captura (UTC, la partición `date=` de `append_raw`): payloads
—una línea por sondeo— y bytes sin comprimir. Se lee con `gzip.open`, que salta
el relleno de ceros entre miembros donde `zcat` se para (bitácora 011). Por
fuente se da la MEDIANA entre días: los días partidos por una caída no la mueven.

Es la cifra que decide si la captura necesita un broker (ADR-016, bitácora 033).
"""

from __future__ import annotations

import argparse
import gzip

import pandas as pd

from project.config import settings


def medir(dias: list[str] | None = None) -> pd.DataFrame:
    filas = []
    for f in sorted(settings.raw_dir.glob("source=*/date=*/payloads.ndjson.gz")):
        dia = f.parent.name.removeprefix("date=")
        if dias and dia not in dias:
            continue
        with gzip.open(f, "rb") as fh:
            tam = [len(linea) for linea in fh]
        filas.append(
            {
                "fuente": f.parent.parent.name.removeprefix("source="),
                "dia": dia,
                "payloads": len(tam),
                "mb": sum(tam) / 1e6,
                "max_kb": max(tam, default=0) / 1e3,
            }
        )
    return pd.DataFrame(filas)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dias", nargs="*", default=None)
    d = medir(p.parse_args().dias)
    r = d.groupby("fuente").agg(
        dias=("dia", "nunique"),
        payloads_dia=("payloads", "median"),
        mb_dia=("mb", "median"),
        max_kb=("max_kb", "max"),
    )
    print(r.round(1).to_string())
    total = r["payloads_dia"].sum()
    print(
        f"\n  total: {total:,.0f} payloads/día = {total / 86400:.3f} por segundo, "
        f"{r['mb_dia'].sum():,.0f} MB/día sin comprimir"
    )
