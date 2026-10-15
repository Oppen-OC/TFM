"""¿Cuánto publica al día cada fuente? Volumen del crudo, solo lectura.

    uv run python -m project.analysis.medir_volumen
    uv run python -m project.analysis.medir_volumen --dias 2026-09-16
    uv run python -m project.analysis.medir_volumen --filas

Por fuente y día de captura (UTC, la partición `date=` de `append_raw`): payloads
—una línea por sondeo— y bytes sin comprimir. Se lee con `gzip.open`, que salta
el relleno de ceros entre miembros donde `zcat` se para (bitácora 011). Por
fuente se da la MEDIANA entre días: los días partidos por una caída no la mueven.

Es la cifra que decide si la captura necesita un broker (ADR-016, bitácora 033).

`--filas` cuenta en su lugar las filas del curated —ya parseado, deduplicado y
con Renfe filtrada al núcleo 40— y su tamaño en disco: la cifra que mide el
volumen del pilar 3 frente a los ~145 M proyectados en `docs/01` (bitácora 056).
"""

from __future__ import annotations

import argparse
import gzip

import duckdb
import pandas as pd

from project.config import settings


def filas() -> pd.DataFrame:
    """Filas por fuente y día de captura (UTC) en el curated, y MB en disco."""
    partes = []
    for d in sorted(settings.curated_dir.glob("source=*")):
        pat = (d / "*" / "*.parquet").as_posix()
        n = duckdb.sql(
            f"select cast(ts_ingest_utc as date) dia, count(*) filas "
            f"from read_parquet('{pat}', hive_partitioning=false) group by 1"
        ).df()
        mb = sum(f.stat().st_size for f in d.rglob("*.parquet")) / 1e6
        partes.append(n.assign(fuente=d.name.removeprefix("source="), mb_fuente=mb))
    return pd.concat(partes)


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
    p.add_argument("--filas", action="store_true")
    a = p.parse_args()
    if a.filas:
        f = filas()
        r = f.groupby("fuente").agg(
            dias=("dia", "nunique"),
            desde=("dia", "min"),
            hasta=("dia", "max"),
            filas=("filas", "sum"),
            mediana_dia=("filas", "median"),
            mb_disco=("mb_fuente", "first"),
        )
        print(r.to_string())
        dia = r["mediana_dia"].sum()
        print(
            f"\n  total: {r['filas'].sum():,.0f} filas, {r['mb_disco'].sum():,.0f} MB"
            f" en disco; {dia:,.0f} filas/día (suma de medianas)"
            f" = {dia * 92 / 1e6:,.1f} M en 92 días"
        )
        raise SystemExit
    d = medir(a.dias)
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
