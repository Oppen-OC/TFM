"""Flota simulada sobre los trazados REALES del GTFS, con verdad-terreno.

`simulacion.simular_flota` mueve cada bus con rumbo propio: dos buses de la
misma línea no comparten calle. Eso invalidó la medición del residuo del
suavizado de intercambios —la asignación equivocada salía cinemáticamente más
suave que la verdadera— y dejó sin árbitro la pregunta de si la abscisa a lo
largo de la ruta resuelve esos casos
(`docs/bitacora/015-el-sondeo-siguiente-delata-el-intercambio.md`).

Aquí los buses de un mismo (línea, trayecto) recorren **la misma polilínea del
GTFS**, que es donde de verdad se encuentran: se alcanzan, se paran en la misma
parada y giran en las mismas esquinas. Cada fila conserva `verdad` (el bus que
la generó) y `abscisa_verdad` (su avance real sobre el trazado), así que se
puede medir tanto la identidad como el error del map-matching.

Calibrado con la captura (`docs/bitacora/013-la-flota-simulada-no-para-ni-gira.md`
y `016-el-map-matching-casa-con-el-gtfs.md`), columna laborable. Con los valores
por defecto, medido con el mismo instrumento en los dos lados:

  magnitud                     simulado   real
  pasos parado                    28 %    29 %
  vecino del mismo grupo p10     593 m   611 m
  vecino del mismo grupo p50   1.545 m  1.719 m
  vehículos por grupo p50 / p90    3/4     3/6
  cambio de rumbo p90             47°     57°
  paso entre sondeos p99        32,4 s    33 s
  velocidad p50               10,4 km/h  7,5 km/h

La geometría no se calibra: es la real, y con ella el giro sale solo. La
velocidad queda alta porque cada bus lleva un ritmo constante más paradas, y la
realidad añade tramos lentos por tráfico. Es conservador para lo que se mide
aquí: pasos más largos con la misma separación son más ocasiones de confundir
dos buses, no menos.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from project.gtfs import Trazado, a_grados, cargar_trazados

# Valores por defecto: los que reproducen la captura en horario de servicio.
N_LINEAS = 8
BUSES_POR_TRAYECTO = 4  # con SEPARACION_M da 3 vehículos por grupo, como en real
N_SNAPS = 40
DT_S = 30.0
SEMILLA = 7
P_PARADA = 0.17
RUIDO_GPS_M = 2.0
JITTER_DT_S = 3.0
SEPARACION_M = 2500.0  # deja el vecino del grupo en p10 593 m (real 611 m)
# Velocidad comercial de la línea. Todos sus buses llevan la misma salvo un
# pequeño factor propio: en la calle, dos buses de una línea no circulan a 6 y a
# 26 km/h, y darles velocidades muy distintas fabrica adelantamientos continuos
# que en real son raros. Lo que sí varía es el tráfico, paso a paso.
VEL_LINEA_KMH = (11.0, 19.0)
DISPERSION_BUS = 0.08
DISPERSION_TRAFICO = 0.35


def _posicion(t: Trazado, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    s = np.clip(s, 0.0, t.acum[-1])
    return np.interp(s, t.acum, t.x), np.interp(s, t.acum, t.y)


def simular_sobre_gtfs(
    n_lineas: int = N_LINEAS,
    buses_por_trayecto: int = BUSES_POR_TRAYECTO,
    n_snaps: int = N_SNAPS,
    dt: float = DT_S,
    semilla: int = SEMILLA,
    p_parada: float = P_PARADA,
    ruido_gps_m: float = RUIDO_GPS_M,
    jitter_dt_s: float = JITTER_DT_S,
    separacion_m: float = SEPARACION_M,
    trazados: dict[str, list[Trazado]] | None = None,
) -> pd.DataFrame:
    """Posiciones con la forma de la capa de la EMT, más `verdad` y `abscisa_verdad`.

    Se eligen `n_lineas` líneas con dos trazados (uno por sentido) y se colocan
    `buses_por_trayecto` vehículos por trazado, separados `separacion_m` de
    media. Cada uno avanza por la polilínea a velocidad propia, con paradas de
    1-3 sondeos, ruido de posición y cadencia irregular. Al llegar al final de la
    ruta el vehículo deja de emitir: en la calle sale de servicio o cambia de
    trayecto, y encadenar ida y vuelta es un fenómeno distinto (el giro en
    cabecera) que aquí no se mezcla.
    """
    tz = trazados if trazados is not None else cargar_trazados()
    elegibles = sorted(
        (linea for linea, t in tz.items() if len(t) == 2),
        key=lambda linea: (-min(x.largo for x in tz[linea]), linea),
    )[:n_lineas]
    if not elegibles:
        raise ValueError("el GTFS no trae ninguna línea con dos trazados")

    rng = np.random.default_rng(semilla)
    extra = np.random.default_rng(semilla + 10_000)
    buses = []
    for linea in elegibles:
        vel_linea = rng.uniform(*VEL_LINEA_KMH) / 3.6
        for sentido, t in enumerate(sorted(tz[linea], key=lambda x: x.shape_id)):
            for k in range(buses_por_trayecto):
                buses.append(
                    {
                        "trazado": t,
                        "linea": linea,
                        "trayecto": f"S{sentido}",
                        "s": max(t.largo - separacion_m * (k + rng.random()), 0.0),
                        "vel": vel_linea * rng.normal(1.0, DISPERSION_BUS),
                    }
                )

    n = len(buses)
    s = np.array([b["s"] for b in buses])
    vel = np.array([b["vel"] for b in buses])
    largo = np.array([b["trazado"].largo for b in buses])
    parado = np.zeros(n, dtype=int)

    filas = []
    t0 = pd.Timestamp("2026-08-26T08:00:00Z")
    reloj = 0.0
    for k in range(n_snaps):
        if p_parada:
            empieza = (parado == 0) & (extra.random(n) < p_parada)
            parado[empieza] = extra.integers(1, 4, empieza.sum())
        # El tráfico frena a todos los del mismo tramo por igual: un factor por
        # sondeo, no uno por bus.
        trafico = float(extra.lognormal(0.0, DISPERSION_TRAFICO))
        s = s + vel * trafico * dt * (parado == 0)
        parado = np.maximum(parado - 1, 0)

        instante = k * dt
        if jitter_dt_s:
            reloj = max(reloj + 1.0, instante + extra.uniform(0, jitter_dt_s))
            instante = reloj

        vivos = s <= largo
        for i in np.flatnonzero(vivos):
            b = buses[i]
            x, y = _posicion(b["trazado"], np.array([s[i]]))
            if ruido_gps_m:
                x = x + extra.normal(0, ruido_gps_m)
                y = y + extra.normal(0, ruido_gps_m)
            lat, lon = a_grados(x[0], y[0])
            filas.append(
                {
                    "snapshot_id": 1000 + k,
                    "gid": 1000 + k * n + i,
                    "linea": b["linea"],
                    "trayecto": b["trayecto"],
                    "lat": float(lat),
                    "lon": float(lon),
                    "ts_utc": t0 + pd.Timedelta(seconds=float(instante)),
                    "verdad": f"bus{i:03d}",
                    "abscisa_verdad": float(s[i]),
                    "shape_verdad": b["trazado"].shape_id,
                }
            )
    sim = pd.DataFrame(filas)
    # Orden de llegada barajado dentro del sondeo, como en la fuente real.
    sim = sim.sample(frac=1, random_state=3).sort_values("snapshot_id", kind="stable")
    return sim.reset_index(drop=True)
