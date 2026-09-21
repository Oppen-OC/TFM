"""Stage `prepare`: del curated de la EMT a los pasos por parada con su retraso.

    uv run python -m project.prepare                         # lo que ejecuta `dvc repro prepare`
    uv run python -m project.prepare --dias 2026-08-27 --salida DIR   # una prueba, fuera de DVC

Por jornada (día UTC de captura, filtrado por `ts_ingest_utc` sobre todas las
particiones: entrada 011):

1. Descarta las posiciones sin `trayecto` y las cuenta. No son etiquetables: en
   las ráfagas medidas son un único bus aparcado, fuera de todo trazado de su
   línea (bitácora 023).
2. `tracking.rastrear`, UNA pasada. La segunda con abscisa no mejora la
   identidad en jornada real y sube el indicador de intercambios (bitácora 023):
   la abscisa se usa para el paso por parada, no para rastrear.
3. `etiquetado.etiquetar` contra la versión del GTFS que manda cada día de
   servicio.

Escribe, particionado por día, `emt_tracked/` (posiciones con vehículo, viaje y
estado), `viajes/` (cada tramo observado y por qué se etiquetó o no) y `pasos/`
(una fila por parada con `retraso_s`); y `metrics/prepare.json` con los
recuentos, que es lo que se compara entre versiones del pipeline.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from project.config import RAIZ, settings
from project.etiquetado import Parametros, Resultado, etiquetar
from project.gtfs import Horario, cargar_horario, versiones
from project.tracking import rastrear

SALIDAS = ("emt_tracked", "viajes", "pasos")
COLUMNAS_POSICIONES = [
    "snapshot_id",
    "linea",
    "trayecto",
    "lat",
    "lon",
    "ts_utc",
    "vehicle_id",
    "fecha_servicio",
    "feed_version",
    "shape_id",
    "abscisa_m",
    "dist_trazado_m",
    "fiable",
    "viaje_id",
    "estado",
]


def etiquetar_dia(
    df: pd.DataFrame, horarios: list[Horario], p: Parametros
) -> Resultado:
    """Posiciones de un día (formato curated) a pasos por parada etiquetados."""
    sin_trayecto = df["trayecto"].isna()
    pos = rastrear(df.loc[~sin_trayecto])
    r = etiquetar(pos, horarios, p)
    r.descartadas_sin_trayecto = int(sin_trayecto.sum())
    return r


def cargar_parametros(ruta: Path = RAIZ / "params.yaml") -> Parametros:
    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))["prepare"]
    campos = {f.name for f in dataclasses.fields(Parametros)}
    cfg = {k: v for k, v in cfg.items() if k in campos}
    if "excluir_fechas" in cfg:  # YAML da listas; el dataclass es inmutable
        cfg["excluir_fechas"] = tuple(tuple(map(str, r)) for r in cfg["excluir_fechas"])
    return Parametros(**cfg)


def _patron() -> str:
    return (settings.curated_dir / "source=emt_buses" / "*" / "*.parquet").as_posix()


def dias_capturados() -> list[str]:
    duckdb.sql("set TimeZone = 'UTC'")
    filas = duckdb.sql(
        f"select distinct cast(ts_ingest_utc as date) as d "
        f"from read_parquet('{_patron()}', hive_partitioning = false) order by d"
    ).fetchall()
    return [str(f[0]) for f in filas]


def cargar_dia(dia: str) -> pd.DataFrame:
    desde = pd.Timestamp(f"{dia}T00:00:00Z")
    hasta = desde + pd.Timedelta(days=1)
    return duckdb.sql(
        f"""
        select snapshot_id, linea, trayecto, lat, lon, ts_utc
        from read_parquet('{_patron()}', hive_partitioning = false)
        where ts_ingest_utc >= '{desde.isoformat()}' and ts_ingest_utc < '{hasta.isoformat()}'
          and lat is not null and lon is not null
        """
    ).df()


_HORARIOS: list[Horario] = []


def _cargar_feeds(rutas: list[Path]) -> None:
    """Una vez por proceso: el horario de cada versión cuesta unos segundos."""
    _HORARIOS[:] = [cargar_horario(r) for r in rutas]


def procesar_dia(dia: str, p: Parametros, salida: Path) -> dict:
    t0 = time.time()
    r = etiquetar_dia(cargar_dia(dia), _HORARIOS, p)
    for nombre, df in (
        (
            "emt_tracked",
            r.posiciones[[c for c in COLUMNAS_POSICIONES if c in r.posiciones]],
        ),
        ("viajes", r.viajes),
        ("pasos", r.pasos),
    ):
        d = salida / nombre / f"date={dia}"
        d.mkdir(parents=True, exist_ok=True)
        df.to_parquet(d / "part.parquet", index=False, compression="zstd")
    motivos = r.viajes["motivo"].value_counts().to_dict() if len(r.viajes) else {}
    return {
        "dia": dia,
        "posiciones": int(len(r.posiciones)),
        "descartadas_sin_trayecto": r.descartadas_sin_trayecto,
        "viajes": int(len(r.viajes)),
        "viajes_por_motivo": {k: int(v) for k, v in motivos.items()},
        "pasos": int(len(r.pasos)),
        "segundos": round(time.time() - t0, 1),
    }


def main(dias: list[str] | None, procesos: int, salida: Path, metricas: Path) -> None:
    p = cargar_parametros()
    dias = dias or dias_capturados()
    rutas = versiones(settings.gtfs_dir)
    for nombre in SALIDAS:
        shutil.rmtree(salida / nombre, ignore_errors=True)
    with ProcessPoolExecutor(
        max_workers=procesos, initializer=_cargar_feeds, initargs=(rutas,)
    ) as ex:
        por_dia = list(ex.map(partial(procesar_dia, p=p, salida=salida), dias))

    total: dict = {"dias": len(por_dia), "feeds": [r.name for r in rutas]}
    for clave in ("posiciones", "descartadas_sin_trayecto", "viajes", "pasos"):
        total[clave] = sum(d[clave] for d in por_dia)
    motivos: dict[str, int] = {}
    for d in por_dia:
        for k, v in d["viajes_por_motivo"].items():
            motivos[k] = motivos.get(k, 0) + v
    total["viajes_por_motivo"] = motivos
    total["parametros"] = dataclasses.asdict(p)
    total["por_dia"] = por_dia
    metricas.parent.mkdir(parents=True, exist_ok=True)
    metricas.write_text(
        json.dumps(total, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in total.items() if k != "por_dia"},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--dias", nargs="*", default=None)
    a.add_argument("--procesos", type=int, default=8)
    a.add_argument("--salida", type=Path, default=settings.interim_dir)
    a.add_argument("--metricas", type=Path, default=RAIZ / "metrics" / "prepare.json")
    args = a.parse_args()
    main(args.dias, args.procesos, args.salida, args.metricas)
