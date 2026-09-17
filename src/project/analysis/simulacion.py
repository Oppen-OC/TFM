"""Flota simulada con verdad-terreno conocida.

La capa de la EMT no publica identificador de vehículo: la identidad la infiere
`tracking.rastrear()`. Sobre datos reales no hay nada contra lo que medir ese
resultado, así que "60 trayectorias reconstruidas" parecería un éxito aunque
cada trayectoria mezclase tres buses distintos. Por eso la evaluación del
tracker se hace sobre una flota generada aquí, donde cada fila sabe qué bus la
produjo (columna `verdad`).

Vive en `analysis/` y no en `tests/` porque la usan dos consumidores: la fixture
`flota_simulada` de `tests/conftest.py` y el medidor
`project.analysis.medir_tracking`. Tenerla duplicada haría que las cifras de la
bitácora dejasen de corresponder a lo que guardan los tests en cuanto una de las
dos copias cambiase.

Nada del pipeline importa de `analysis/`: esto no produce entradas de `train`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Valores por defecto: los de la fixture histórica de los tests. Cambiarlos
# invalida los umbrales de `tests/test_tracking.py` y las cifras de
# `docs/bitacora/`, que se midieron con estos.
N_BUSES = 60
N_SNAPS = 20
DT_S = 30.0
SEMILLA = 7
SEMILLA_BARAJADO = 3


def simular_flota(
    n_buses: int = N_BUSES,
    n_snaps: int = N_SNAPS,
    dt: float = DT_S,
    semilla: int = SEMILLA,
    semilla_barajado: int = SEMILLA_BARAJADO,
    flip_en: int | None = None,
    parciales: dict[int, float] | None = None,
    huecos: tuple[int, ...] = (),
    p_parada: float = 0.0,
    p_giro: float = 0.0,
    ruido_gps_m: float = 0.0,
    jitter_dt_s: float = 0.0,
) -> pd.DataFrame:
    """Devuelve posiciones con la forma de la capa de buses, más la columna `verdad`.

    Los buses van en línea casi recta con rumbo perturbado y velocidades de 3 a
    30 km/h, que es el rango realista de un bus urbano. Las líneas y trayectos se
    reparten en `n_buses % 8` grupos: cuantos menos grupos, más vehículos
    compiten por el mismo emparejamiento y más difícil es el problema.

    Escenarios opcionales, apagados por defecto para no mover las cifras ya
    publicadas. Todos conservan `verdad`: el bus sigue siendo el mismo, lo que
    cambia es lo que la fuente cuenta de él, o cómo se mueve.

    `flip_en`  A partir de ese snapshot cada bus invierte su `trayecto`, como al
        llegar a cabecera. El desfase `(3*i) % 7` evita que la línea entera gire
        a la vez, que sería un caso degenerado: en la realidad los buses llegan a
        cabecera de uno en uno y el grupo encoge de uno en uno. El 7 es
        deliberado — es coprimo con el `i % 8` que reparte las líneas. Con un
        desfase `i % 4` los ocho buses de una línea comparten resto y giran en el
        mismo snapshot, que es el caso que se quería evitar. El movimiento NO
        se invierte, sólo la etiqueta. Es deliberado: aísla el defecto de
        agrupación del de predicción. Un tracker que falle aquí falla con la
        versión fácil del problema.

    `parciales`  Índice de snapshot -> fracción de filas que sobrevive. Modela el
        payload truncado a media escritura (`data/raw/_TRUNCADOS.txt`): el
        colector guarda menos filas de las que había y no se entera. Se recorta
        después del barajado, así que las filas que faltan son un subconjunto
        arbitrario, como en el fichero real.

    `huecos`  Índices de snapshot que desaparecen ENTEROS, como cuando el
        colector se para un rato. A diferencia de `parciales`, aquí no falta
        parte de un sondeo: falta el sondeo, y con él la regularidad de la
        cadencia. Los `ts_utc` de los que quedan siguen siendo los reales, así
        que el paso que salta el hueco dura el doble. Es el único escenario que
        destapa la trampa 009 — el resto tiene todos los pasos iguales, y con
        pasos iguales el defecto es invisible.

    Cuatro fenómenos cinemáticos, medidos sobre 52 ventanas reales en las que la
    flota por defecto se queda corta (`docs/bitacora/013-la-flota-simulada-no-para-ni-gira.md`).
    Sin ellos el movimiento es rectilíneo y uniforme, que es exactamente lo que
    supone el predictor: el tracker sale perfecto por construcción. Usan un
    generador aleatorio aparte (`semilla + 10_000`) para que, apagados, la flota
    sea idéntica bit a bit a la de siempre.

    `p_parada`  Probabilidad por paso de que un bus en marcha se detenga 1-3
        sondeos (semáforo, parada). Con 0,17 queda parado el ~29 % de los pasos,
        la cifra real; la flota por defecto, 0 %.
    `p_giro`  Probabilidad por paso de un giro de 90°, como en una esquina. El
        p90 real del cambio de rumbo es 57°; por defecto, 14°.
    `ruido_gps_m`  Error gaussiano de posición, en metros, sobre lo OBSERVADO; el
        movimiento verdadero sigue limpio.
    `jitter_dt_s`  El sondeo llega entre 0 y este número de segundos tarde. El
        p99 real de la duración del paso es 33 s.
    """
    rng = np.random.default_rng(semilla)
    lineas = [(f"L{i % 8}", "Ida" if i % 2 else "Vuelta") for i in range(n_buses)]
    lat = 39.46 + rng.normal(0, 0.02, n_buses)
    lon = -0.37 + rng.normal(0, 0.02, n_buses)
    rumbo = rng.uniform(0, 2 * np.pi, n_buses)
    vel = rng.uniform(3, 30, n_buses)  # km/h realistas para bus urbano
    extra = np.random.default_rng(semilla + 10_000)
    parado_resta = np.zeros(n_buses, dtype=int)

    filas = []
    t0 = pd.Timestamp("2026-08-15T19:00:00Z")
    reloj = 0.0
    for s in range(n_snaps):
        paso = vel / 3.6 * dt
        if p_parada:
            empieza = (parado_resta == 0) & (extra.random(n_buses) < p_parada)
            parado_resta[empieza] = extra.integers(1, 4, empieza.sum())
            paso = paso * (parado_resta == 0)
        lat = lat + np.cos(rumbo) * paso / 111_320
        lon = lon + np.sin(rumbo) * paso / (111_320 * np.cos(np.radians(lat)))
        rumbo += rng.normal(0, 0.15, n_buses)
        if p_giro:
            gira = extra.random(n_buses) < p_giro
            rumbo[gira] += extra.choice([-np.pi / 2, np.pi / 2], gira.sum())
        if p_parada:
            parado_resta = np.maximum(parado_resta - 1, 0)
        obs_lat, obs_lon = lat, lon
        if ruido_gps_m:
            obs_lat = lat + extra.normal(0, ruido_gps_m, n_buses) / 111_320
            obs_lon = lon + extra.normal(0, ruido_gps_m, n_buses) / (
                111_320 * np.cos(np.radians(lat))
            )
        instante = s * dt
        if jitter_dt_s:
            reloj = max(reloj + 1.0, instante + extra.uniform(0, jitter_dt_s))
            instante = reloj
        for i in range(n_buses):
            trayecto = lineas[i][1]
            if flip_en is not None and s >= flip_en + (3 * i) % 7:
                trayecto = "Ida" if trayecto == "Vuelta" else "Vuelta"
            filas.append(
                {
                    "snapshot_id": 1000 + s,
                    "gid": 1000 + s * n_buses + i,
                    "linea": lineas[i][0],
                    "trayecto": trayecto,
                    "lat": obs_lat[i],
                    "lon": obs_lon[i],
                    "ts_utc": t0 + pd.Timedelta(seconds=instante),
                    "verdad": f"bus{i:03d}",
                }
            )
    sim = pd.DataFrame(filas)
    if huecos:
        sim = sim[~sim["snapshot_id"].isin([1000 + h for h in huecos])]
    # El orden de llegada se baraja dentro de cada snapshot, como en la fuente
    # real. Barajar es deliberado: es lo que destapa un reenganche por posición
    # de fila en vez de por identidad (trampa 004).
    sim = sim.sample(frac=1, random_state=semilla_barajado).sort_values("snapshot_id")
    if parciales:
        sim = _truncar(sim, parciales, semilla)
    return sim.reset_index(drop=True)


def _truncar(
    sim: pd.DataFrame, parciales: dict[int, float], semilla: int
) -> pd.DataFrame:
    """Recorta los snapshots indicados a una fracción de sus filas.

    El corte es aleatorio y no por cabeza de tabla: las filas ya vienen
    barajadas, así que quedarse con las primeras equivaldría a quedarse con una
    muestra arbitraria de todos modos, pero dejarlo explícito evita que un
    cambio futuro en el barajado convierta esto en un corte por posición.
    """
    rng = np.random.default_rng(semilla)
    fuera: list[int] = []
    for s, frac in parciales.items():
        idx = sim.index[sim["snapshot_id"] == 1000 + s].to_numpy()
        if not len(idx):
            raise ValueError(f"snapshot {s} fuera de la captura simulada")
        n_queda = max(1, int(round(len(idx) * frac)))
        fuera.extend(rng.permutation(idx)[n_queda:].tolist())
    return sim.drop(index=fuera)
