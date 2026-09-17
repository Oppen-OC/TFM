"""Sondas de equivalencia: ¿cambia el mutante alguna salida observable?

    python auditoria/sondas.py parsers        # imprime un hash por sonda

Un mutante que ninguna prueba detecta puede ser un hueco de los tests o un
mutante que no cambia nada. Sin distinguirlos, la auditoría se inventa huecos.
Cada sonda ejecuta el código mutado sobre entradas FIJAS —fixtures reales,
flota simulada con semilla, directorios temporales— y resume la salida en un
hash. `mutar.py` compara ese hash con y sin el mutante: igual es equivalente,
distinto es hueco.

Las entradas están elegidas para ejercitar las ramas que el catálogo muta, no
para parecerse a la realidad: filas hueco en las capas de tráfico, latencias de
Valenbisi entre 900 y 2400 s, dos sondeos con el mismo instante, un salto de
700 m en 30 s, un convoy en fila india, un payload que no parsea.

Todo lo que dependa del reloj o de rutas temporales queda fuera del hash.
Nada importa de aquí salvo `mutar.py`, que la invoca por subprocess.
"""

from __future__ import annotations

import asyncio
import copy
import gzip
import hashlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
FIXTURES = AQUI.parent / "tests" / "fixtures.json"
INGEST = pd.Timestamp("2026-08-16 09:00:00", tz="Europe/Madrid").tz_convert("UTC")


def _h(*partes) -> str:
    m = hashlib.sha256()
    for p in partes:
        if isinstance(p, pd.DataFrame):
            p = p.to_csv(index=False, float_format="%.6f")
        m.update(repr(p).encode("utf-8"))
    return m.hexdigest()[:16]


def _fix() -> dict:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
def sonda_parsers() -> str:
    from project.ingest.sources import parse

    fix = _fix()
    salidas = []

    # EMT con las dos convenciones y con dato rancio.
    for conv, rancio in (("UTC", 0), ("LOCAL", 0), ("UTC", 86_400_000)):
        p = copy.deepcopy(fix["emt_buses"])
        real = INGEST - pd.Timedelta(seconds=25)
        if conv == "UTC":
            epoch = int(real.timestamp() * 1000)
        else:
            pared = real.tz_convert("Europe/Madrid").tz_localize(None)
            epoch = int(pared.tz_localize("UTC").timestamp() * 1000)
        for f in p["features"]:
            f["attributes"]["fecha"] = epoch - rancio
        salidas.append(parse("emt_buses", p, INGEST))

    # Tráfico con filas hueco: sin idtramo, sin geometría, sin estado.
    for clave in ("trafico_estado", "trafico_intensidad"):
        p = copy.deepcopy(fix[clave])
        hueco = copy.deepcopy(p["features"][0])
        hueco["attributes"] = dict.fromkeys(hueco["attributes"])
        hueco["geometry"] = None
        p["features"] += [hueco, copy.deepcopy(hueco)]
        salidas.append(parse(clave, p, INGEST))

    # Valenbisi con latencias a ambos lados de 900 s y por debajo de 2400 s.
    for lat_s in (60, 1500, 2300):
        p = copy.deepcopy(fix["valenbisi"])
        for f in p["features"]:
            f["attributes"]["update_jcd"] = int(
                (INGEST - pd.Timedelta(seconds=lat_s)).timestamp() * 1000
            )
        salidas.append(parse("valenbisi", p, INGEST))

    # Renfe con fechaActualizacion distinta del instante de captura.
    p = copy.deepcopy(fix["renfe_cercanias"])
    p["fechaActualizacion"] = "2026-08-16T08:59:10"
    salidas.append(parse("renfe_cercanias", p, INGEST))

    return _h(*salidas)


def sonda_tiempo() -> str:
    from project.ingest.sources import (
        local_naive_epoch_to_utc,
        local_naive_iso_to_utc,
        resolver_convencion,
    )

    epochs = [1786828132000, 1768467600000, 1774746000000]  # verano, invierno, cambio
    salidas = [str(local_naive_epoch_to_utc(e)) for e in epochs]
    salidas.append(str(local_naive_iso_to_utc("2026-01-15T09:00:00")))
    for lat_s in (-100, 25, 800, 3600, 7200, 9000):
        real = INGEST - pd.Timedelta(seconds=lat_s)
        for conv in ("UTC", "LOCAL"):
            if conv == "UTC":
                e = int(real.timestamp() * 1000)
            else:
                e = int(
                    real.tz_convert("Europe/Madrid")
                    .tz_localize(None)
                    .tz_localize("UTC")
                    .timestamp()
                    * 1000
                )
            serie, etiqueta = resolver_convencion(pd.Series([e, e]), INGEST)
            salidas.append((lat_s, conv, etiqueta, str(serie.iloc[0])))
    return _h(*salidas)


def sonda_haversine() -> str:
    from project.ingest.sources import haversine_m

    pares = [
        (39.47, -0.37, 39.48, -0.37),
        (39.47, -0.37, 39.47, -0.36),
        (39.3, -0.3, 39.5, -0.4),
    ]
    return _h([round(float(haversine_m(*p)), 3) for p in pares])


# --------------------------------------------------------------------------- #
def _convoy(n: int = 4, separacion_m: float = 120.0, snaps: int = 10) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    filas = []
    t0 = pd.Timestamp("2026-08-16T08:00:00Z")
    for s in range(snaps):
        for i in range(n):
            avance = (15 / 3.6) * 30 * s + i * separacion_m
            filas.append(
                {
                    "snapshot_id": 500 + s,
                    "linea": "L1",
                    "trayecto": "Ida",
                    "lat": 39.46 + avance / 111_320,
                    "lon": -0.37,
                    "ts_utc": t0 + pd.Timedelta(seconds=30 * s),
                    "verdad": f"c{i}",
                }
            )
    df = pd.DataFrame(filas).sample(frac=1, random_state=int(rng.integers(100)))
    return df.sort_values("snapshot_id", kind="stable").reset_index(drop=True)


def _escenarios() -> dict[str, pd.DataFrame]:
    from project.analysis.simulacion import simular_flota

    esc = {
        "base": simular_flota(),
        "hueco": simular_flota(huecos=(7,)),
        "parcial": simular_flota(parciales={5: 0.6}),
        "flip": simular_flota(flip_en=5),
        "denso": simular_flota(n_buses=16, n_snaps=40),
        "convoy": _convoy(),
    }
    # Dos sondeos con el mismo instante: dt = 0.
    mismo = simular_flota(n_snaps=8)
    t3 = mismo.loc[mismo["snapshot_id"] == 1002, "ts_utc"].iloc[0]
    mismo.loc[mismo["snapshot_id"] == 1003, "ts_utc"] = t3
    esc["dt_cero"] = mismo
    # Salto de 700 m en 30 s a partir del sondeo 10: por encima de 70 km/h.
    salto = simular_flota()
    m = (salto["verdad"] == "bus000") & (salto["snapshot_id"] >= 1010)
    salto.loc[m, "lat"] += 700 / 111_320
    esc["salto"] = salto
    # Dos sondeos perdidos a cadencia de 60 s: dentro de `tolerar_hueco`, pero
    # el puente dura 180 s y supera `HUECO_MAX_S`.
    esc["pausa"] = simular_flota(dt=60.0, huecos=(6, 7))
    # Paradas y giros al ritmo real: lo único que ejercita el suavizado de
    # intercambios. Sin ellos, todo mutante del suavizado sale "equivalente".
    esc["paradas"] = simular_flota(semilla=42, p_parada=0.17, n_snaps=40)
    esc["giros"] = simular_flota(semilla=7, p_giro=0.10, n_snaps=40)
    esc["estres"] = simular_flota(
        semilla=11, p_parada=0.30, p_giro=0.20, ruido_gps_m=5.0, jitter_dt_s=6.0
    )
    return esc


def sonda_tracking() -> str:
    from project.tracking import rastrear

    salidas = []
    for nombre, sim in _escenarios().items():
        for predictivo in (True, False):
            out = rastrear(sim.drop(columns=["verdad"]), predictivo=predictivo)
            cols = [
                "snapshot_id",
                "lat",
                "lon",
                "vehicle_id",
                "dist_m",
                "dt_s",
                "vel_kmh",
            ]
            salidas.append(
                (
                    nombre,
                    predictivo,
                    out[[c for c in cols if c in out.columns]].round(4),
                )
            )
    return _h(*[(n, p) for n, p, _ in salidas], *[d for _, _, d in salidas])


# --------------------------------------------------------------------------- #
def sonda_persistencia() -> str:
    from project.ingest import collect, reprocesar, sources

    fix = _fix()
    salidas = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # append_raw / read_raw, cruzando medianoche UTC.
        instantes = [
            pd.Timestamp("2026-08-16T23:59:30Z"),
            pd.Timestamp("2026-08-16T23:59:50Z"),
            pd.Timestamp("2026-08-17T00:00:10Z"),
        ]
        for i, ts in enumerate(instantes):
            sources.append_raw(root, "renfe_cercanias", {"n": i}, ts)
        for f in sorted((root / "raw").rglob("*.gz")):
            leido = [(str(t), p) for t, p in sources.read_raw(f)]
            salidas.append((f.relative_to(root).as_posix(), leido))

        # reprocesar: dos días de crudo y un payload que no parsea.
        r2 = root / "rep"
        p_ok = fix["trafico_estado"]
        sources.append_raw(
            r2, "trafico_estado", p_ok, pd.Timestamp("2026-08-16T10:00:00Z")
        )
        sources.append_raw(
            r2,
            "trafico_estado",
            {"features": [{"attributes": {"x": 1}}]},
            pd.Timestamp("2026-08-16T10:05:00Z"),
        )
        sources.append_raw(
            r2, "trafico_estado", p_ok, pd.Timestamp("2026-08-17T10:00:00Z")
        )
        salidas.append(
            sorted(reprocesar.reprocesar(r2, "trafico_estado", dry=False).items())
        )
        for f in sorted((r2 / "curated").rglob("*.parquet")):
            salidas.append((f.parent.name, pd.read_parquet(f)))

        # recordar: desalojo con memoria de 3.
        collect.MAX_VISTOS = 3
        collect.VISTOS.clear()
        collect.VISTOS_SET.clear()
        salidas.append([collect.recordar("x", s) for s in (1, 2, 3, 1, 4, 5, 1, 2)])

        # flush: la referencia de geometría con un tramo repetido entre snapshots.
        r3 = root / "flush"
        df = sources.parse("trafico_estado", p_ok, pd.Timestamp("2026-08-16T10:00:00Z"))
        collect.BUFFER["trafico_estado"] = [df, df.copy()]
        collect.flush(r3, "trafico_estado")
        salidas.append(
            pd.read_parquet(r3 / "reference" / "trafico_estado_geometria.parquet")
        )
        salidas.append(
            [pd.read_parquet(f) for f in sorted((r3 / "curated").rglob("*.parquet"))]
        )

        # sondear: un payload que no parsea tiene que dejar su crudo en disco.
        import httpx

        r4 = root / "sondeo"
        malo = {
            "features": [
                {"attributes": {"gid": 1, "linea": "1"}, "geometry": {"x": 0, "y": 0}}
            ]
        }

        def responder(request: httpx.Request) -> httpx.Response:
            collect.PARAR.set()
            return httpx.Response(200, json=malo)

        async def una_vuelta() -> None:
            collect.PARAR.clear()
            async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as c:
                await collect.sondear(c, "emt_buses", r4)

        asyncio.run(una_vuelta())
        crudos = sorted((r4 / "raw").rglob("*.gz")) if (r4 / "raw").exists() else []
        n_lineas = sum(
            len(gzip.open(f, "rt", encoding="utf-8").readlines()) for f in crudos
        )
        salidas.append(("crudo_tras_fallo_de_parseo", len(crudos), n_lineas))
    return _h(*salidas)


SONDAS = {
    "parsers": sonda_parsers,
    "tiempo": sonda_tiempo,
    "haversine": sonda_haversine,
    "tracking": sonda_tracking,
    "persistencia": sonda_persistencia,
}

if __name__ == "__main__":
    for nombre in sys.argv[1:]:
        try:
            print(f"{nombre}={SONDAS[nombre]()}")
        except Exception as exc:  # noqa: BLE001
            # Que el mutante haga reventar la sonda también es salida distinta.
            print(f"{nombre}=EXCEPCION:{type(exc).__name__}")
