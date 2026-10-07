"""Stage `prepare`: del curated de la EMT a los pasos por parada con su retraso.

    uv run python -m project.prepare                         # lo que ejecuta `dvc repro prepare`
    uv run python -m project.prepare --dias 2026-08-27 --salida DIR   # una prueba, fuera de DVC

Por día de servicio: de las `HORA_CORTE` a las `HORA_CORTE` locales del día
siguiente, filtrado por `ts_utc` sobre todas las particiones (entrada 011). No
por día UTC: ese corte cae a las 02:00 locales, parte los nocturnos y numera
`v00000` dos veces para el mismo día de servicio (bitácora 027). A las 04:00 no
hay en servicio ni un bus por sondeo.

1. Descarta las posiciones sin `trayecto` y las cuenta. No son etiquetables: en
   las ráfagas medidas son un único bus aparcado, fuera de todo trazado de su
   línea (bitácora 023).
2. `tracking.rastrear`, UNA pasada. La segunda con abscisa no mejora la
   identidad en jornada real y sube el indicador de intercambios (bitácora 023):
   la abscisa se usa para el paso por parada, no para rastrear.
3. `etiquetado.etiquetar` contra la versión del GTFS que manda cada día de
   servicio.

Escribe, particionado por día de servicio, `emt_tracked/` (posiciones con vehículo, viaje y
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
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta
from functools import partial
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from project.config import RAIZ, settings
from project.etiquetado import HORA_CORTE, Parametros, Resultado, etiquetar
from project.gtfs import Horario, cargar_horario, versiones
from project.tracking import rastrear

SALIDAS = ("emt_tracked", "viajes", "pasos")

# Un esquema por tabla, el mismo todos los días. Un día excluido o sin horario no
# pasa por el map-matching ni por la asignación, y escrito tal cual sale sin
# columnas o con tipo `null`: DuckDB falla al leer el glob y pandas cambia el
# dtype según qué partición entre primero (issue #2). Lo que falte va nulo.
_TS = pa.timestamp("ns", tz=settings.tz_local)
ESQUEMAS = {
    "emt_tracked": pa.schema(
        [
            ("snapshot_id", pa.int64()),
            ("linea", pa.string()),
            ("trayecto", pa.string()),
            ("trayecto_publicado", pa.string()),
            ("lat", pa.float64()),
            ("lon", pa.float64()),
            ("ts_utc", pa.timestamp("us", tz=settings.tz_local)),
            ("vehicle_id", pa.string()),
            ("fecha_servicio", pa.date32()),
            ("feed_version", pa.string()),
            ("shape_id", pa.string()),
            ("abscisa_m", pa.float64()),
            ("dist_trazado_m", pa.float64()),
            ("fiable", pa.bool_()),
            ("viaje_id", pa.string()),
            ("estado", pa.string()),
        ]
    ),
    "viajes": pa.schema(
        [
            ("viaje_id", pa.string()),
            ("vehicle_id", pa.string()),
            ("fecha_servicio", pa.date32()),
            ("linea", pa.string()),
            ("trayecto", pa.string()),
            ("feed_version", pa.string()),
            ("fuera_de_vigencia", pa.bool_()),
            ("posiciones", pa.int64()),
            ("t_inicio", _TS),
            ("t_fin", _TS),
            ("motivo", pa.string()),
            ("trip_id", pa.string()),
            ("shape_id", pa.string()),
            ("coste_s", pa.float64()),
            ("desfase_s", pa.float64()),
            ("margen_s", pa.float64()),
        ]
    ),
    "pasos": pa.schema(
        [
            ("stop_id", pa.string()),
            ("stop_sequence", pa.int64()),
            ("abscisa_parada_m", pa.float64()),
            ("t_obs_s", pa.float64()),
            ("t_prog_s", pa.float64()),
            ("retraso_s", pa.float64()),
            ("viaje_id", pa.string()),
            ("vehicle_id", pa.string()),
            ("fecha_servicio", pa.date32()),
            ("linea", pa.string()),
            ("trayecto", pa.string()),
            ("feed_version", pa.string()),
            ("fuera_de_vigencia", pa.bool_()),
            ("trip_id", pa.string()),
            ("shape_id", pa.string()),
            ("desfase_s", pa.float64()),
            ("margen_s", pa.float64()),
            ("coste_s", pa.float64()),
            ("t_obs_utc", pa.timestamp("ns", tz="UTC")),
        ]
    ),
}


def con_esquema(nombre: str, df: pd.DataFrame) -> pa.Table:
    """`df` con el esquema fijo de la tabla: las columnas que falten, nulas."""
    esquema = ESQUEMAS[nombre]
    df = df.copy()
    for c in esquema.names:
        if c not in df:
            df[c] = pd.Series(None, index=df.index, dtype="object")
    return pa.Table.from_pandas(df[esquema.names], schema=esquema, preserve_index=False)


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
    # Sin filtrar claves: una que `Parametros` no conoce es un umbral que nadie
    # lee, y debe fallar aquí (así sobrevivieron las copias del tracker).
    cfg = yaml.safe_load(ruta.read_text(encoding="utf-8"))["prepare"]
    if "excluir_fechas" in cfg:  # YAML da listas; el dataclass es inmutable
        cfg["excluir_fechas"] = tuple(tuple(map(str, r)) for r in cfg["excluir_fechas"])
    return Parametros(**cfg)


def _patron() -> str:
    return (settings.curated_dir / "source=emt_buses" / "*" / "*.parquet").as_posix()


def ventana_servicio(dia: date | str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[desde, hasta) en UTC del día de servicio: de corte a corte en hora local.

    Es la misma regla que `etiquetado._dia_de_servicio`, así que toda trayectoria
    que empiece dentro de la ventana es de ese día de servicio. Dura 23 o 25 h los
    días de cambio de hora.
    """
    d = date.fromisoformat(str(dia))
    siguiente = d + timedelta(days=1)
    desde, hasta = (
        pd.Timestamp(datetime(x.year, x.month, x.day, HORA_CORTE), tz=settings.tz_local)
        for x in (d, siguiente)
    )
    return desde.tz_convert("UTC"), hasta.tz_convert("UTC")


def dias_capturados() -> list[str]:
    """Días de servicio con alguna posición: la fecha local menos `HORA_CORTE` h."""
    duckdb.sql("set TimeZone = 'UTC'")
    filas = duckdb.sql(
        f"select distinct cast(timezone('{settings.tz_local}', ts_utc) "
        f"- interval {HORA_CORTE} hour as date) as d "
        f"from read_parquet('{_patron()}', hive_partitioning = false) order by d"
    ).fetchall()
    return [str(f[0]) for f in filas]


def cargar_dia(dia: str) -> pd.DataFrame:
    """Las posiciones de un día de servicio (`ventana_servicio`), formato curated."""
    desde, hasta = ventana_servicio(dia)
    return duckdb.sql(
        f"""
        select snapshot_id, linea, trayecto, lat, lon, ts_utc
        from read_parquet('{_patron()}', hive_partitioning = false)
        where ts_utc >= '{desde.isoformat()}' and ts_utc < '{hasta.isoformat()}'
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
    # Si la ventana y el día de servicio dejan de coincidir, las claves vuelven a
    # chocar entre días sin ningún error (bitácora 027): que lo haya.
    otros = set(r.posiciones["fecha_servicio"]) - {date.fromisoformat(dia)}
    if otros:
        raise ValueError(
            f"{dia}: la ventana de servicio trae posiciones de {sorted(otros)}; "
            "ventana_servicio y etiquetado.HORA_CORTE no coinciden"
        )
    for nombre, df in (
        ("emt_tracked", r.posiciones),
        ("viajes", r.viajes),
        ("pasos", r.pasos),
    ):
        d = salida / nombre / f"date={dia}"
        d.mkdir(parents=True, exist_ok=True)
        pq.write_table(con_esquema(nombre, df), d / "part.parquet", compression="zstd")
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
    total["viajes_por_motivo"] = dict(
        sum((Counter(d["viajes_por_motivo"]) for d in por_dia), Counter())
    )
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
