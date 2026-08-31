"""Reconstruye `curated/` desde `raw/`. La razón de guardar el crudo.

    python demo/reprocesar.py                       # todas las fuentes
    python demo/reprocesar.py --sources emt_buses   # una concreta
    python demo/reprocesar.py --dry-run             # sin escribir nada

Cuando descubres que el parser estaba mal (y descubrirás que lo estaba: el
16/08/2026 resultó que el servicio de la EMT alterna entre dos convenciones
horarias de un sondeo al siguiente), no hay que recapturar nada. Los payloads
crudos están en disco tal como llegaron: se vuelve a parsear y listo.

Es el argumento operativo de por qué la ingesta se separa del procesado, y el
mismo que justifica Kafka en la memoria: capturar es irreversible, procesar es
reintentable.
"""

from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from pathlib import Path

import pandas as pd

from sources import SOURCES, parse, read_raw


def reprocesar(root: Path, source: str, dry: bool) -> dict:
    dir_raw = root / "raw" / f"source={source}"
    if not dir_raw.exists():
        return {"fuente": source, "estado": "sin crudo"}

    por_dia: dict[str, list[pd.DataFrame]] = defaultdict(list)
    geo: pd.DataFrame | None = None
    n_payloads = errores = 0

    for fichero in sorted(dir_raw.rglob("*.ndjson.gz")):
        for ts_ingest, payload in read_raw(fichero):
            n_payloads += 1
            try:
                df = parse(source, payload, ts_ingest)
            except Exception:  # noqa: BLE001
                errores += 1
                continue
            if df.empty:
                continue
            if "geom_wkt" in df.columns:
                if geo is None:
                    cols = [
                        c
                        for c in (
                            "idtramo",
                            "denominacion",
                            "des_tramo",
                            "fiwareid",
                            "lat",
                            "lon",
                            "geom_wkt",
                        )
                        if c in df.columns
                    ]
                    geo = df[cols].drop_duplicates(subset=["idtramo"])
                df = df.drop(columns=["geom_wkt"])
            por_dia[ts_ingest.strftime("%Y-%m-%d")].append(df)

    filas = sum(len(d) for v in por_dia.values() for d in v)
    if dry:
        return {
            "fuente": source,
            "payloads": n_payloads,
            "dias": len(por_dia),
            "filas": filas,
            "errores": errores,
            "estado": "simulado",
        }

    destino = root / "curated" / f"source={source}"
    if destino.exists():
        respaldo = root / "_curated_previo" / f"source={source}"
        respaldo.parent.mkdir(parents=True, exist_ok=True)
        if respaldo.exists():
            shutil.rmtree(respaldo)
        shutil.move(str(destino), str(respaldo))

    for dia, trozos in por_dia.items():
        d = destino / f"date={dia}"
        d.mkdir(parents=True, exist_ok=True)
        pd.concat(trozos, ignore_index=True).to_parquet(
            d / "part-reprocesado.parquet", index=False, compression="zstd"
        )

    if geo is not None:
        ref = root / "reference" / f"{source}_geometria.parquet"
        ref.parent.mkdir(parents=True, exist_ok=True)
        geo.to_parquet(ref, index=False, compression="zstd")

    return {
        "fuente": source,
        "payloads": n_payloads,
        "dias": len(por_dia),
        "filas": filas,
        "errores": errores,
        "estado": "reescrito",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data"))
    p.add_argument("--sources", nargs="*", default=list(SOURCES))
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    print(f"\n  Crudo en {a.data / 'raw'}\n")
    for s in a.sources:
        r = reprocesar(a.data, s, a.dry_run)
        if r["estado"] == "sin crudo":
            print(f"  {s:22} sin datos crudos")
        else:
            print(
                f"  {s:22} {r['payloads']:6,} payloads -> {r['filas']:9,} filas "
                f"en {r['dias']} día(s), {r['errores']} errores  [{r['estado']}]"
            )
    if not a.dry_run:
        print(
            f"\n  El curated anterior está en {a.data / '_curated_previo'} "
            f"(bórralo cuando compruebes que todo está bien).\n"
        )
