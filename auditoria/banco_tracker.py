"""Banco del tracker: compara versiones de `rastrear` con el mismo rasero.

    uv run python auditoria/banco_tracker.py --etiqueta base
    uv run python auditoria/banco_tracker.py --tracker ruta/tracking_candidato.py --etiqueta A
    uv run python auditoria/banco_tracker.py --real 2026-08-27 --etiqueta base
    uv run python auditoria/banco_tracker.py --reservadas --etiqueta final   # UNA vez

Dos bloques de medida:

SIMULACIÓN, con verdad-terreno. Escenarios de `simular_flota` con los fenómenos
calibrados sobre la captura real (bitácora 013), por semilla y longitud:
saltos, trayectorias contaminadas, cola y fragmentación. Las semillas se parten
en dos conjuntos: las de AJUSTE se miran cuanto haga falta al diseñar; las
RESERVADAS solo al final, una vez, para saber si el arreglo generaliza o se ha
ajustado a cinco semillas. `--reservadas` las activa y lo deja escrito en la
salida.

REAL, sin verdad-terreno. Por jornada completa, filtrada por `ts_ingest_utc`:
trayectorias, duración mediana, desplazamientos por encima de la puerta, y el
indicador `ida_vuelta`: un vehículo que en dos pasos consecutivos de más de 50 m
invierte el sentido y vuelve cerca de donde estaba. Es la huella de un
intercambio que se deshace en el sondeo siguiente —el bus parado "va" hasta el
que pasa y vuelve—. No cuenta los intercambios que no se deshacen, así que es
una cota inferior; su relación con los saltos verdaderos se comprueba en
simulación con `--validar-indicador` antes de usarlo.

`--tracker` carga un `tracking.py` alternativo desde fichero, para probar
candidatos sin tocar `src/project/tracking.py`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path
from types import ModuleType

import duckdb
import numpy as np
import pandas as pd

from project.analysis import medir_tracking
from project.analysis.simulacion import simular_flota
from project.config import settings

AQUI = Path(__file__).resolve().parent

SEMILLAS_AJUSTE = (7, 11, 23, 42, 101)
SEMILLAS_RESERVADAS = tuple(range(9001, 9021))
LONGITUDES = (20, 80)

ESCENARIOS: dict[str, dict] = {
    "ninguno": {},
    "paradas": {"p_parada": 0.17},
    "giros": {"p_giro": 0.10},
    "todos": {"p_parada": 0.17, "p_giro": 0.10, "ruido_gps_m": 2.0, "jitter_dt_s": 3.0},
    "estres": {
        "p_parada": 0.30,
        "p_giro": 0.20,
        "ruido_gps_m": 5.0,
        "jitter_dt_s": 6.0,
    },
    "hueco": {"huecos": (7,)},
    "hueco_paradas": {"huecos": (7,), "p_parada": 0.17},
}

IDA_VUELTA_MIN_M = 50.0
IDA_VUELTA_COS = -0.8
IDA_VUELTA_VUELVE = 0.5


def cargar_tracker(ruta: Path | None) -> ModuleType:
    if ruta is None:
        from project import tracking

        return tracking
    spec = importlib.util.spec_from_file_location(f"tracker_{ruta.stem}", ruta)
    assert spec and spec.loader
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def ida_vuelta(out: pd.DataFrame) -> int:
    """Pares de pasos que van y vuelven: la huella de un intercambio deshecho."""
    o = out.sort_values(["vehicle_id", "snapshot_id"], kind="stable")
    vid = o["vehicle_id"].to_numpy()
    lat, lon = o["lat"].to_numpy(), o["lon"].to_numpy()
    x = (lon - lon.mean()) * 111_320 * np.cos(np.radians(lat))
    y = (lat - lat.mean()) * 111_320
    mismo = (vid[2:] == vid[1:-1]) & (vid[1:-1] == vid[:-2])
    v1 = np.stack([x[1:-1] - x[:-2], y[1:-1] - y[:-2]])
    v2 = np.stack([x[2:] - x[1:-1], y[2:] - y[1:-1]])
    n1, n2 = np.hypot(*v1), np.hypot(*v2)
    con_paso = (n1 > IDA_VUELTA_MIN_M) & (n2 > IDA_VUELTA_MIN_M)
    cos = np.divide(
        (v1 * v2).sum(axis=0), n1 * n2, out=np.zeros_like(n1), where=con_paso
    )
    vuelve = np.hypot(x[2:] - x[:-2], y[2:] - y[:-2]) < IDA_VUELTA_VUELVE * np.maximum(
        n1, n2
    )
    return int((mismo & con_paso & (cos < IDA_VUELTA_COS) & vuelve).sum())


def medir_sim(tracker: ModuleType, semillas: tuple[int, ...]) -> pd.DataFrame:
    medir_tracking.rastrear = tracker.rastrear  # mismo rasero para todos
    filas = []
    for nombre, kw in ESCENARIOS.items():
        for n in LONGITUDES:
            for s in semillas:
                sim = simular_flota(n_snaps=n, semilla=s, **kw)
                m = medir_tracking.medir(sim, predictivo=True)
                out = tracker.rastrear(sim.drop(columns=["verdad"]))
                filas.append(
                    {
                        "escenario": nombre,
                        "snaps": n,
                        "semilla": s,
                        "saltos": m["saltos"],
                        "contaminadas": m["contaminadas"],
                        "cola": m["cola"],
                        "fragmentacion": m["fragmentacion"],
                        "ida_vuelta": ida_vuelta(out),
                    }
                )
    return pd.DataFrame(filas)


def resumir_sim(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("escenario", sort=False).agg(
        saltos=("saltos", "sum"),
        semillas_con_saltos=("saltos", lambda s: int((s > 0).sum())),
        contaminadas_max=("contaminadas", "max"),
        cola_media=("cola", "mean"),
        fragmentacion_max=("fragmentacion", "max"),
        ida_vuelta=("ida_vuelta", "sum"),
    )


def medir_real(tracker: ModuleType, dia: str) -> dict:
    desde = pd.Timestamp(f"{dia}T00:00:00Z")
    hasta = desde + pd.Timedelta(days=1)
    patron = (settings.curated_dir / "source=emt_buses" / "*" / "*.parquet").as_posix()
    df = duckdb.sql(
        f"""
        select snapshot_id, linea, trayecto, lat, lon, ts_utc, ts_ingest_utc
        from read_parquet('{patron}', hive_partitioning = false)
        where ts_ingest_utc >= '{desde.isoformat()}' and ts_ingest_utc < '{hasta.isoformat()}'
          and lat is not null and lon is not null
        """
    ).df()
    t = time.time()
    out = tracker.rastrear(df)
    segundos = time.time() - t
    dur = out.groupby("vehicle_id")["ts_utc"].agg(
        lambda s: (s.max() - s.min()).total_seconds() / 60
    )
    tr = out.dropna(subset=["dist_m", "dt_s"])
    tope = np.minimum(
        tracker.SALTO_MAX_M, tracker.VEL_MAX_KMH / 3.6 * np.maximum(tr["dt_s"], 1.0)
    )
    return {
        "dia": dia,
        "posiciones": len(out),
        "trayectorias": int(out["vehicle_id"].nunique()),
        "duracion_mediana_min": round(float(dur.median()), 2),
        "ida_vuelta": ida_vuelta(out),
        "sobre_puerta": int((tr["dist_m"] > tope + 1e-6).sum()),
        "segundos": round(segundos, 1),
    }


def validar_indicador(tracker: ModuleType) -> None:
    """¿Cuenta `ida_vuelta` intercambios de verdad y nada más?"""
    df = medir_sim(tracker, SEMILLAS_AJUSTE)
    print("\n  Validación de ida_vuelta contra saltos verdaderos (semillas de ajuste):")
    print(
        df.groupby("escenario", sort=False)[["saltos", "ida_vuelta"]].sum().to_string()
    )
    sin = df[df["saltos"] == 0]["ida_vuelta"]
    con = df[df["saltos"] > 0]
    print(
        f"\n  falsos positivos: {int(sin.sum())} eventos en {len(sin)} ejecuciones sin saltos"
        f"\n  detección: {int((con['ida_vuelta'] > 0).sum())} de {len(con)} ejecuciones con saltos"
        f"\n  correlación saltos~ida_vuelta: {df['saltos'].corr(df['ida_vuelta']):.2f}"
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tracker", type=Path, default=None)
    p.add_argument("--etiqueta", required=True)
    p.add_argument("--reservadas", action="store_true")
    p.add_argument("--real", nargs="*", default=[])
    p.add_argument("--sin-sim", action="store_true")
    p.add_argument("--validar-indicador", action="store_true")
    p.add_argument("--salida", type=Path, default=AQUI / "resultados")
    a = p.parse_args()

    tracker = cargar_tracker(a.tracker)
    if a.validar_indicador:
        validar_indicador(tracker)
        return

    salida: dict = {
        "etiqueta": a.etiqueta,
        "tracker": str(a.tracker or "src/project/tracking.py"),
        "semillas": "RESERVADAS" if a.reservadas else "ajuste",
    }
    if not a.sin_sim:
        semillas = SEMILLAS_RESERVADAS if a.reservadas else SEMILLAS_AJUSTE
        df = medir_sim(tracker, semillas)
        resumen = resumir_sim(df)
        with pd.option_context(
            "display.width", 160, "display.float_format", "{:.4f}".format
        ):
            print(f"\n  [{a.etiqueta}] simulación, semillas {salida['semillas']}")
            print(resumen.to_string())
        salida["simulacion"] = resumen.reset_index().to_dict(orient="records")
        salida["detalle"] = df.to_dict(orient="records")
    reales = []
    for dia in a.real:
        r = medir_real(tracker, dia)
        reales.append(r)
        print(f"  [{a.etiqueta}] real {r}", flush=True)
    if reales:
        salida["real"] = reales

    destino = a.salida / f"banco_{a.etiqueta}.json"
    destino.write_text(
        json.dumps(salida, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(f"  -> {destino}")


if __name__ == "__main__":
    main()
