"""Reconstruye `curated/` desde `raw/`. La razón de guardar el crudo.

    uv run python -m project.ingest.reprocesar                       # todas las fuentes
    uv run python -m project.ingest.reprocesar --sources emt_buses   # una concreta
    uv run python -m project.ingest.reprocesar --dry-run             # sin escribir nada

Las cuentas de cada fuente (payloads, repetidos, completados, errores) quedan en
`metrics/curar.json`: son el primer eslabón del ciclo de vida del dato.

Cuando descubres que el parser estaba mal (y descubrirás que lo estaba: el
16/08/2026 resultó que el servicio de la EMT alterna entre dos convenciones
horarias de un sondeo al siguiente), no hay que recapturar nada. Los payloads
crudos están en disco tal como llegaron: se vuelve a parsear y listo.

Es el argumento operativo de por qué la ingesta se separa del procesado
(ADR-002): capturar es irreversible, procesar es reintentable. Lo cumple el
crudo guardado antes de parsear, sin broker de por medio (ADR-016).

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
import gzip
import json
import shutil
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from project.config import RAIZ, settings
from project.ingest.sources import (
    COLS_GEOMETRIA,
    SOURCES,
    clave_sondeo,
    parse,
    read_raw,
)


@dataclass
class Capturas:
    """Lo que `elegir_capturas` saca de un conjunto de ficheros de crudo."""

    elegidos: dict[int | str, tuple[str, pd.DataFrame]]  # clave -> (día, df)
    payloads: int
    errores: int
    duplicados: int
    completados: set
    geo: pd.DataFrame | None
    ultimo_ok_utc: pd.Timestamp | None  # ts_ingest del último payload con filas
    # Último payload sin filas o que no parsea, solo si es posterior al último ok.
    ultimo_error: tuple[pd.Timestamp, str] | None


def _leer(fichero: Path, tolerar_cola: bool):
    """`read_raw`, y con `tolerar_cola` se para donde el fichero está cortado.

    El colector amplía el crudo mientras se lee: el último miembro gzip (o su
    última línea) puede estar a medias.
    """
    try:
        yield from read_raw(fichero)
    except (EOFError, gzip.BadGzipFile, json.JSONDecodeError):
        if not tolerar_cola:
            raise


def elegir_capturas(
    ficheros: Iterable[Path], source: str, tolerar_cola: bool = False
) -> Capturas:
    """Captura elegida de cada sondeo, en el orden en que apareció por primera vez.

    De las de un mismo sondeo, la que más filas trae (trampa 011). Un payload sin
    filas no es un sondeo (trampa 018): no entra, pero si es posterior al último
    ok queda como `ultimo_error`, y un ok posterior lo borra.
    """
    elegidos: dict[int | str, tuple[str, pd.DataFrame]] = {}
    completados: set[int | str] = set()
    geo: pd.DataFrame | None = None
    n_payloads = errores = duplicados = 0
    ultimo_ok: pd.Timestamp | None = None
    ultimo_error: tuple[pd.Timestamp, str] | None = None

    for fichero in ficheros:
        for ts_ingest, payload in _leer(fichero, tolerar_cola):
            n_payloads += 1
            try:
                df = parse(source, payload, ts_ingest)
            except Exception as e:  # noqa: BLE001
                errores += 1
                motivo = type(e).__name__
                df = None
            else:
                motivo = "payload sin filas"
            if df is None or df.empty:
                if isinstance(payload, dict) and "error" in payload:
                    motivo = str(payload["error"])[:200]
                if ultimo_ok is None or ts_ingest > ultimo_ok:
                    ultimo_error = (ts_ingest, motivo)
                continue
            if ultimo_ok is None or ts_ingest > ultimo_ok:
                ultimo_ok = ts_ingest
            if ultimo_error is not None and ultimo_error[0] <= ultimo_ok:
                ultimo_error = None
            if "geom_wkt" in df.columns:
                if geo is None:
                    cols = [c for c in COLS_GEOMETRIA if c in df.columns]
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

    return Capturas(
        elegidos,
        n_payloads,
        errores,
        duplicados,
        completados,
        geo,
        ultimo_ok,
        ultimo_error,
    )


def reprocesar(root: Path, source: str, dry: bool) -> dict:
    dir_raw = root / "raw" / f"source={source}"
    if not dir_raw.exists():
        return {"fuente": source, "estado": "sin crudo"}

    c = elegir_capturas(sorted(dir_raw.rglob("*.ndjson.gz")), source)
    elegidos, geo = c.elegidos, c.geo
    n_payloads, errores = c.payloads, c.errores
    duplicados, completados = c.duplicados, c.completados

    por_dia: dict[str, list[pd.DataFrame]] = defaultdict(list)
    for dia, df in elegidos.values():
        por_dia[dia].append(df)
    r = {
        "fuente": source,
        "payloads": n_payloads,
        "dias": len(por_dia),
        "filas": sum(len(d) for v in por_dia.values() for d in v),
        "errores": errores,
        "duplicados": duplicados,
        "completados": len(completados),
    }
    if dry:
        return {**r, "estado": "simulado"}

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

    return {**r, "estado": "reescrito"}


def main(data: Path, fuentes: list[str], dry: bool, metricas: Path) -> None:
    print(f"\n  Crudo en {data / 'raw'}\n")
    cuentas = {}
    for s in fuentes:
        r = cuentas[s] = reprocesar(data, s, dry)
        if r["estado"] == "sin crudo":
            print(f"  {s:22} sin datos crudos")
        else:
            print(
                f"  {s:22} {r['payloads']:6,} payloads -> {r['filas']:9,} filas "
                f"en {r['dias']} día(s), {r['duplicados']:,} repetidos "
                f"({r['completados']:,} completados), "
                f"{r['errores']} errores  [{r['estado']}]"
            )
    if not dry:
        metricas.parent.mkdir(parents=True, exist_ok=True)
        metricas.write_text(
            json.dumps(cuentas, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            f"\n  El curated anterior está en {data / '_curated_previo'} "
            f"(bórralo cuando compruebes que todo está bien).\n"
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=settings.data_root)
    # ponytail: el clima no entra en `curar` (issue #8, primer plan); si el
    # segundo plan lo mete, se añade su crudo a las deps del stage y sale de aquí.
    p.add_argument(
        "--sources",
        nargs="*",
        default=[k for k in SOURCES if k != "meteo_estaciones"],
    )
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--metricas", type=Path, default=RAIZ / "metrics" / "curar.json")
    a = p.parse_args()
    main(a.data, a.sources, a.dry_run, a.metricas)
