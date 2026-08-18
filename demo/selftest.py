"""Autotest sin red: valida parsers, corrección horaria y tracker.

Usa fixtures con la forma EXACTA de los payloads reales capturados el
15/08/2026, más una simulación de flota con verdad-terreno conocida para
medir si el tracker recupera bien las identidades.

    python selftest.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from sources import local_naive_epoch_to_utc, local_naive_iso_to_utc, now_utc, parse
from track import rastrear, resumen

AQUI = Path(__file__).resolve().parent
FIX = json.loads((AQUI / "fixtures.json").read_text(encoding="utf-8"))
OK, FALLOS = 0, []


def check(nombre: str, cond: bool, detalle: str = "") -> None:
    global OK
    if cond:
        OK += 1
        print(f"  [ok]   {nombre}")
    else:
        FALLOS.append(nombre)
        print(f"  [FALLO] {nombre}  {detalle}")


print("\n1. Corrección de zona horaria")
print("-" * 70)
# fecha real observada: 1786828132000 -> hora de pared local 21:08:52 del 15/08/2026
t = local_naive_epoch_to_utc(1786828132000)
check("epoch local naive -> UTC en verano (CEST, -2h)",
      t == pd.Timestamp("2026-08-15T19:08:52Z"), f"obtenido {t}")
# invierno: el desfase debe ser 1 h, no 2. Aquí es donde se rompen las series.
t_inv = local_naive_epoch_to_utc(pd.Timestamp("2026-01-15T09:00:00Z").value // 10**6)
check("mismo campo en invierno (CET, -1h)",
      t_inv == pd.Timestamp("2026-01-15T08:00:00Z"), f"obtenido {t_inv}")
check("ISO naive de Renfe -> UTC",
      local_naive_iso_to_utc("2026-08-15T21:11:56") == pd.Timestamp("2026-08-15T19:11:56Z"))

print("\n1b. Resolución automática de la convención horaria")
print("-" * 70)
print("     (el servicio de la EMT alterna entre UTC y hora local naive)")


def payload_emt(instante_pared: str, convencion: str) -> tuple[dict, pd.Timestamp]:
    """Fabrica un payload cuyo `fecha` sigue la convención indicada."""
    ingest = pd.Timestamp(instante_pared, tz="Europe/Madrid").tz_convert("UTC")
    real = ingest - pd.Timedelta(seconds=25)          # dato de hace 25 s
    if convencion == "YA_EN_UTC":
        epoch = int(real.timestamp() * 1000)
    else:                                              # hora de pared local
        pared = real.tz_convert("Europe/Madrid").tz_localize(None)
        epoch = int(pared.tz_localize("UTC").timestamp() * 1000)
    p = json.loads(json.dumps(FIX["emt_buses"]))
    for f in p["features"]:
        f["attributes"]["fecha"] = epoch
    return p, ingest


for etiqueta, momento, estacion in [
    ("LOCAL_NAIVE", "2026-08-16 09:00:00", "verano (CEST, +2 h)"),
    ("YA_EN_UTC", "2026-08-16 09:00:00", "verano (CEST, +2 h)"),
    ("LOCAL_NAIVE", "2026-01-16 09:00:00", "invierno (CET, +1 h)"),
    ("YA_EN_UTC", "2026-01-16 09:00:00", "invierno (CET, +1 h)"),
]:
    pl, ing = payload_emt(momento, etiqueta)
    d = parse("emt_buses", pl, ing)
    detectada = d["tz_convencion"].iloc[0]
    lat = float(d["latencia_s"].median())
    check(f"{estacion}: detecta {etiqueta}",
          detectada == etiqueta and 0 <= lat <= 120,
          f"detectada={detectada}, latencia={lat:.0f}s")

# Un timestamp absurdo no debe elegir en silencio: se marca.
pl, ing = payload_emt("2026-08-16 09:00:00", "YA_EN_UTC")
for f in pl["features"]:
    f["attributes"]["fecha"] -= 86_400_000            # un día de antigüedad
d = parse("emt_buses", pl, ing)
check("dato rancio -> se marca DUDOSA en vez de adivinar",
      d["tz_convencion"].iloc[0] == "DUDOSA", d["tz_convencion"].iloc[0])

# Regresión del bug real: mezclar convenciones no debe desplazar nada 2 h.
lat_todas = []
for i in range(12):
    conv = "YA_EN_UTC" if i % 4 == 0 else "LOCAL_NAIVE"
    pl, ing = payload_emt(f"2026-08-16 09:{i:02d}:00", conv)
    lat_todas += parse("emt_buses", pl, ing)["latencia_s"].tolist()
check("serie con convenciones alternas: ninguna fila desplazada >1 h",
      max(abs(x) for x in lat_todas) < 3600,
      f"máx |latencia| = {max(abs(x) for x in lat_todas):.0f}s")

print("\n2. Parsers sobre payloads con la forma real")
print("-" * 70)
ts = now_utc()
for clave in ["emt_buses", "trafico_estado", "trafico_intensidad", "valenbisi", "renfe_cercanias"]:
    df = parse(clave, FIX[clave], ts)
    check(f"{clave}: parsea y devuelve filas", len(df) > 0, f"filas={len(df)}")
    check(f"{clave}: tiene ts_utc y ts_ingest_utc",
          {"ts_utc", "ts_ingest_utc"}.issubset(df.columns))

df_renfe = parse("renfe_cercanias", FIX["renfe_cercanias"], ts)
check("renfe: filtra sólo núcleo 40 (València)", len(df_renfe) == 2, f"filas={len(df_renfe)}")
check("renfe: retraso_min es numérico",
      pd.api.types.is_numeric_dtype(df_renfe["retraso_min"]))

df_int = parse("trafico_intensidad", FIX["trafico_intensidad"], ts)
check("trafico_intensidad: lectura=-1 se convierte en nulo",
      df_int["lectura"].isna().sum() == 1, f"nulos={df_int['lectura'].isna().sum()}")

df_emt = parse("emt_buses", FIX["emt_buses"], ts)
check("emt: snapshot_id = gid mínimo del bloque",
      int(df_emt["snapshot_id"].iloc[0]) == 1659987635)

print("\n3. Tracker sobre flota simulada con verdad-terreno")
print("-" * 70)
rng = np.random.default_rng(7)
N_BUSES, N_SNAPS, DT = 60, 20, 30.0
lineas = [(f"L{i%8}", "Ida" if i % 2 else "Vuelta") for i in range(N_BUSES)]
lat = 39.46 + rng.normal(0, 0.02, N_BUSES)
lon = -0.37 + rng.normal(0, 0.02, N_BUSES)
rumbo = rng.uniform(0, 2 * np.pi, N_BUSES)
vel = rng.uniform(3, 30, N_BUSES)  # km/h realistas para bus urbano

filas = []
t0 = pd.Timestamp("2026-08-15T19:00:00Z")
for s in range(N_SNAPS):
    paso = vel / 3.6 * DT
    lat = lat + np.cos(rumbo) * paso / 111_320
    lon = lon + np.sin(rumbo) * paso / (111_320 * np.cos(np.radians(lat)))
    rumbo += rng.normal(0, 0.15, N_BUSES)
    for i in range(N_BUSES):
        filas.append({
            "snapshot_id": 1000 + s, "gid": 1000 + s * N_BUSES + i,
            "linea": lineas[i][0], "trayecto": lineas[i][1],
            "lat": lat[i], "lon": lon[i],
            "ts_utc": t0 + pd.Timedelta(seconds=s * DT),
            "verdad": f"bus{i:03d}",
        })
sim = pd.DataFrame(filas)
# El orden de llegada se baraja dentro de cada snapshot, como en la fuente real
sim = sim.sample(frac=1, random_state=3).sort_values("snapshot_id").reset_index(drop=True)

def evaluar(sim: pd.DataFrame, predictivo: bool) -> tuple[dict, float]:
    out = rastrear(sim.drop(columns=["verdad"]), predictivo=predictivo)
    out["verdad"] = sim["verdad"]
    # Precisión de identidad: para cada trayectoria reconstruida, qué fracción
    # de sus posiciones pertenece al bus real mayoritario.
    aciertos = out.groupby("vehicle_id")["verdad"].agg(lambda s: s.value_counts().iloc[0]).sum()
    return resumen(out), aciertos / len(out)


r_ing, acc_ing = evaluar(sim, predictivo=False)
r_pred, acc_pred = evaluar(sim, predictivo=True)

print(f"     ingenuo    : identidad correcta {acc_ing:.1%}  | {r_ing['trayectorias']} trayectorias  "
      f"| vel p50 {r_ing['vel_kmh_p50']} km/h")
print(f"     predictivo : identidad correcta {acc_pred:.1%}  | {r_pred['trayectorias']} trayectorias  "
      f"| vel p50 {r_pred['vel_kmh_p50']} km/h")

check("tracker: 60 buses simulados -> 60 trayectorias reconstruidas",
      r_pred["trayectorias"] == 60, f"obtenidas {r_pred['trayectorias']}")
check("tracker predictivo: identidad correcta >= 99 %", acc_pred >= 0.99, f"{acc_pred:.1%}")
check("tracker predictivo mejora al ingenuo", acc_pred >= acc_ing,
      f"{acc_pred:.1%} vs {acc_ing:.1%}")
check("tracker: emparejamiento por encima del 95 %",
      r_pred["tasa_emparejamiento"] >= 0.95, f"tasa={r_pred['tasa_emparejamiento']}")
check("tracker: velocidades reconstruidas dentro del rango simulado (3-30 km/h)",
      2.0 <= r_pred["vel_kmh_p50"] <= 32.0, f"p50={r_pred['vel_kmh_p50']}")

print("\n4. Comprobación de que gid NO identifica al vehículo")
print("-" * 70)
b0 = set(FIX["bloques_gid"]["t0"])
b1 = set(FIX["bloques_gid"]["t1"])
check("gids de dos sondeos consecutivos son disjuntos", len(b0 & b1) == 0,
      f"intersección={len(b0 & b1)}")
check("los bloques son contiguos (truncate + reinsert)",
      min(b1) - max(b0) == 1, f"salto={min(b1)-max(b0)}")

print("\n" + "=" * 70)
print(f"  {OK} comprobaciones OK, {len(FALLOS)} fallos")
if FALLOS:
    print("  Fallos: " + ", ".join(FALLOS))
    raise SystemExit(1)
print("=" * 70 + "\n")
