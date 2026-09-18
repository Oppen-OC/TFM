"""Reconstruye `curated/` desde `raw/`. La razón de guardar el crudo.

    uv run python -m project.ingest.reprocesar                       # todas las fuentes
    uv run python -m project.ingest.reprocesar --sources emt_buses   # una concreta
    uv run python -m project.ingest.reprocesar --dry-run             # sin escribir nada

Cuando descubres que el parser estaba mal (y descubrirás que lo estaba: el
16/08/2026 resultó que el servicio de la EMT alterna entre dos convenciones
horarias de un sondeo al siguiente), no hay que recapturar nada. Los payloads
crudos están en disco tal como llegaron: se vuelve a parsear y listo.

Es el argumento operativo de por qué la ingesta se separa del procesado, y el
mismo que justifica Kafka en la memoria: capturar es irreversible, procesar es
reintentable.

Reintentable siempre que no meta dos veces el mismo sondeo. El crudo guarda
TODAS las capturas, también las del sondeo que la fuente sirvió repetido; sin
descartarlas, el curated reconstruido del 27/08 daba un 53 % más de
trayectorias que el del colector (bitácora 019). La clave de sondeo es la misma
función que usa el colector, `clave_sondeo`.

De las capturas de un mismo sondeo se queda la que MÁS filas trae, y a igualdad
la primera. No es el criterio del colector, que se queda siempre la primera: la
EMT sirve a veces el bloque a medio reinsertar, y la captura siguiente trae el
mismo `snapshot_id` con el bloque entero. Del 15/08 al 18/09 fueron 1.200
sondeos (el 1,5 %) y 109.063 filas que el colector descartó y el crudo conserva.
Donde no hay sondeo a medias, el resultado es el del colector fila a fila.

La memoria de sondeos vistos no tiene aquí la cota de 20.000 del colector: esa
cota existe para que un proceso de meses no crezca sin fin, no porque la fuente
reutilice claves. En el crudo las repeticiones son siempre consecutivas (las
2.078 de la EMT y las 179 de Renfe, del 15/08 al 18/09).
"""

from __future__ import annotations

import argparse
import shutil
from collections import defaultdict
from pathlib import Path

import pandas as pd

from project.config import settings
from project.ingest.sources import SOURCES, clave_sondeo, parse, read_raw


def reprocesar(root: Path, source: str, dry: bool) -> dict:
    dir_raw = root / "raw" / f"source={source}"
    if not dir_raw.exists():
        return {"fuente": source, "estado": "sin crudo"}

    # Captura elegida de cada sondeo, en el orden en que apareció por primera vez.
    elegidos: dict[int | str, tuple[str, pd.DataFrame]] = {}
    completados: set[int | str] = set()
    geo: pd.DataFrame | None = None
    n_payloads = errores = duplicados = 0

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
            clave = clave_sondeo(df, ts_ingest)
            dia = ts_ingest.strftime("%Y-%m-%d")
            previo = elegidos.get(clave)
            if previo is not None:
                duplicados += 1
                if len(df) > len(previo[1]):
                    elegidos[clave] = (dia, df)
                    completados.add(clave)
                continue
            elegidos[clave] = (dia, df)

    por_dia: dict[str, list[pd.DataFrame]] = defaultdict(list)
    for dia, df in elegidos.values():
        por_dia[dia].append(df)
    filas = sum(len(d) for v in por_dia.values() for d in v)
    if dry:
        return {
            "fuente": source,
            "payloads": n_payloads,
            "dias": len(por_dia),
            "filas": filas,
            "errores": errores,
            "duplicados": duplicados,
            "completados": len(completados),
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
        "duplicados": duplicados,
        "completados": len(completados),
        "estado": "reescrito",
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=settings.data_root)
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
                f"en {r['dias']} día(s), {r['duplicados']:,} repetidos "
                f"({r['completados']:,} completados), "
                f"{r['errores']} errores  [{r['estado']}]"
            )
    if not a.dry_run:
        print(
            f"\n  El curated anterior está en {a.data / '_curated_previo'} "
            f"(bórralo cuando compruebes que todo está bien).\n"
        )
