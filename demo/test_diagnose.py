"""Valida que diagnose.py DISCRIMINA: detecta señal cuando la hay y no la
inventa cuando no la hay.

Genera dos capturas sintéticas con la misma forma que produce collect.py:

  escenario A — los buses van lentos en los tramos congestionados
  escenario B — la velocidad del bus es independiente del estado del tramo

El diagnóstico debe decir "SEÑAL CLARA" en A y "SIN SEÑAL" en B. Si dice lo
mismo en los dos, la herramienta no vale y no puedes fiarte de su veredicto
sobre los datos reales.

    python demo/test_diagnose.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent

N_TRAMOS = 40
N_LINEAS = 12
HORAS = 24
DT = 90           # s entre snapshots (más grueso que el real: basta
                  # para discriminar y mantiene el test por debajo del minuto)
DT_TRAFICO = 60   # s entre snapshots de tráfico
LAT0, LON0 = 39.47, -0.376


def construir(root: Path, con_senal: bool, semilla: int) -> None:
    rng = np.random.default_rng(semilla)
    shutil.rmtree(root, ignore_errors=True)
    t0 = pd.Timestamp("2026-09-14T04:00:00Z")  # lunes

    # --- tramos: segmentos rectos repartidos por una malla ------------------
    tramos = []
    for i in range(N_TRAMOS):
        lat = LAT0 + (i // 8) * 0.006 - 0.015
        lon = LON0 + (i % 8) * 0.008 - 0.030
        largo = 0.004
        wkt = (f"LINESTRING ({lon:.6f} {lat:.6f}, "
               f"{lon+largo:.6f} {lat:.6f}, {lon+2*largo:.6f} {lat+0.0005:.6f})")
        tramos.append({"idtramo": i, "denominacion": f"TRAMO_{i}",
                       "fiwareid": f"EstadoTrafico_{i}", "lat": lat, "lon": lon,
                       "geom_wkt": wkt, "_lat": lat, "_lon": lon, "_largo": largo})
    tr_ref = pd.DataFrame(tramos)
    (root / "reference").mkdir(parents=True, exist_ok=True)
    tr_ref.drop(columns=["_lat", "_lon", "_largo"]).to_parquet(
        root / "reference" / "trafico_estado_geometria.parquet", index=False)

    # --- serie de estado de tráfico ----------------------------------------
    n_tf = int(HORAS * 3600 / DT_TRAFICO)
    filas_tf = []
    estado_por_tramo_t = {}
    for k in range(n_tf):
        ts = t0 + pd.Timedelta(seconds=k * DT_TRAFICO)
        hora_local = (ts.tz_convert("Europe/Madrid")).hour
        # perfil diario: punta a las 8 y a las 19
        p = 0.05 + 0.45 * np.exp(-((hora_local - 8) ** 2) / 3) \
                 + 0.40 * np.exp(-((hora_local - 19) ** 2) / 4)
        for i in range(N_TRAMOS):
            prop = p * (0.4 + 1.2 * ((i * 37) % 10) / 10)  # unos tramos peores
            e = int(rng.random() < prop) * int(rng.choice([1, 2, 3]))
            estado_por_tramo_t[(k, i)] = e
            filas_tf.append({"idtramo": i, "denominacion": f"TRAMO_{i}", "estado": e,
                             "fiwareid": f"EstadoTrafico_{i}",
                             "lat": tramos[i]["lat"], "lon": tramos[i]["lon"],
                             "n_vertices": 3, "ts_utc": ts, "ts_ingest_utc": ts})
    df_tf = pd.DataFrame(filas_tf)
    d = root / "curated" / "source=trafico_estado" / "date=2026-09-14"
    d.mkdir(parents=True, exist_ok=True)
    df_tf.to_parquet(d / "part-000000.parquet", index=False)

    # --- buses: cada línea recorre un tramo de ida y vuelta -----------------
    n_bus = int(HORAS * 3600 / DT)
    filas_b = []
    # cada línea se asocia a un tramo y avanza sobre él
    asign = {ln: ln % N_TRAMOS for ln in range(N_LINEAS)}
    pos = {ln: rng.random() for ln in range(N_LINEAS)}
    for k in range(n_bus):
        ts = t0 + pd.Timedelta(seconds=k * DT)
        k_tf = min(int(k * DT / DT_TRAFICO), n_tf - 1)
        for ln in range(N_LINEAS):
            i = asign[ln]
            e = estado_por_tramo_t[(k_tf, i)]
            if con_senal:
                v = {0: 26.0, 1: 17.0, 2: 11.0, 3: 6.0}[e] * rng.uniform(0.75, 1.25)
            else:
                v = 18.0 * rng.uniform(0.4, 1.6)   # independiente del estado
            avance = v / 3.6 * DT / 900.0           # fracción del tramo por paso
            pos[ln] = (pos[ln] + avance) % 1.0
            t = pos[ln]
            lat = tramos[i]["_lat"] + (0.0005 if t > 0.5 else 0.0)
            lon = tramos[i]["_lon"] + t * 2 * tramos[i]["_largo"]
            filas_b.append({
                "snapshot_id": 1_000_000 + k, "gid": 1_000_000 + k * N_LINEAS + ln,
                "linea": f"L{ln}", "trayecto": f"L{ln}-Ida",
                "lat": lat + rng.normal(0, 8e-6), "lon": lon + rng.normal(0, 8e-6),
                "ts_utc": ts, "ts_ingest_utc": ts, "latencia_s": 30.0})
    df_b = pd.DataFrame(filas_b)
    d = root / "curated" / "source=emt_buses" / "date=2026-09-14"
    d.mkdir(parents=True, exist_ok=True)
    df_b.to_parquet(d / "part-000000.parquet", index=False)


def ejecutar(root: Path) -> str:
    r = subprocess.run([sys.executable, str(AQUI / "diagnose.py"), "--data", str(root)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise SystemExit(f"diagnose.py falló con código {r.returncode}")
    return r.stdout


def veredicto(salida: str) -> str:
    for etiqueta in ("SEÑAL CLARA", "SEÑAL DEBIL", "SIN SEÑAL", "INSUFICIENTE"):
        if f"--> {etiqueta}" in salida:
            return etiqueta
    return "?"


if __name__ == "__main__":
    fallos = []
    for nombre, con_senal, esperado in [("A (con señal)", True, "SEÑAL CLARA"),
                                        ("B (sin señal)", False, "SIN SEÑAL")]:
        root = AQUI / f"_tmp_diag_{'a' if con_senal else 'b'}"
        construir(root, con_senal, semilla=11 if con_senal else 22)
        salida = ejecutar(root)
        v = veredicto(salida)
        ok = v == esperado
        print(f"  [{'ok' if ok else 'FALLO'}]  escenario {nombre}: "
              f"esperado {esperado}, obtenido {v}")
        if not ok:
            fallos.append(nombre)
            print(salida[salida.find("4. SEÑAL"):][:1400])
        # extracto útil aunque pase
        for linea in salida.splitlines():
            if "Cobertura a" in linea or "Máximo horario" in linea \
               or "Caída de velocidad" in linea or "Spearman estado" in linea:
                print("        " + linea.strip())
        shutil.rmtree(root, ignore_errors=True)

    print()
    if fallos:
        print(f"  {len(fallos)} escenario(s) mal clasificados: {fallos}")
        raise SystemExit(1)
    print("  diagnose.py discrimina correctamente entre señal y ruido.")
