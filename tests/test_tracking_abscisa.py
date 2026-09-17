"""El tracker con la posición a lo largo de la ruta.

Dos buses de la misma línea y sentido recorren la MISMA calle en el mismo orden.
Eso no se ve en coordenadas sueltas: cuando uno se detiene y otro lo pasa, la
extrapolación de velocidad constante apunta al vecino y el emparejamiento los
intercambia (bitácora 015). Sobre el eje del recorrido el problema es de una
dimensión y el orden se conserva.

La abscisa la calcula quien llama (`mapmatching.emparejar`) y entra como columna
`abscisa_m`, con `NaN` donde no es fiable —fuera de ruta o ambigua, un 7 % de las
posiciones reales—. Así `tracking.py` no depende del GTFS y estos tests no
necesitan el feed: los recorridos se construyen a mano y la abscisa de cada
posición se conoce exactamente.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from project import tracking
from project.tracking import rastrear

DT = 30.0
LAT0, LON0 = 39.46, -0.37
M = 111_320.0


def _calle(puntos: list[tuple[float, float]], paso: float = 20.0) -> np.ndarray:
    """Polilínea en metros, densificada."""
    xy = [np.array(puntos[0], dtype=float)]
    for a, b in zip(puntos[:-1], puntos[1:]):
        a, b = np.array(a, dtype=float), np.array(b, dtype=float)
        n = max(int(np.ceil(np.hypot(*(b - a)) / paso)), 1)
        xy += [a + (b - a) * k / n for k in range(1, n + 1)]
    return np.array(xy)


def _en(xy: np.ndarray, s: float) -> tuple[float, float]:
    acum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    return float(np.interp(s, acum, xy[:, 0])), float(np.interp(s, acum, xy[:, 1]))


def _capturar(
    recorridos: dict[str, list[float]],
    calle: np.ndarray,
    ruido_m: float = 2.0,
    con_abscisa: bool = True,
    semilla: int = 0,
) -> pd.DataFrame:
    """`recorridos` mapea bus -> abscisa en cada sondeo. Devuelve la capa + verdad."""
    rng = np.random.default_rng(semilla)
    filas = []
    t0 = pd.Timestamp("2026-08-26T08:00:00Z")
    for bus, abscisas in recorridos.items():
        for k, s in enumerate(abscisas):
            x, y = _en(calle, s)
            x += rng.normal(0, ruido_m)
            y += rng.normal(0, ruido_m)
            filas.append(
                {
                    "snapshot_id": 1000 + k,
                    "linea": "L1",
                    "trayecto": "Ida",
                    "lat": LAT0 + y / M,
                    "lon": LON0 + x / (M * np.cos(np.radians(LAT0))),
                    "ts_utc": t0 + pd.Timedelta(seconds=DT * k),
                    "verdad": bus,
                    "abscisa_m": float(s) if con_abscisa else np.nan,
                }
            )
    df = pd.DataFrame(filas).sample(frac=1, random_state=3)
    return df.sort_values("snapshot_id", kind="stable").reset_index(drop=True)


def _precision(out: pd.DataFrame, sim: pd.DataFrame) -> float:
    out = out.assign(verdad=sim["verdad"])
    aciertos = (
        out.groupby("vehicle_id")["verdad"]
        .agg(lambda s: s.value_counts().iloc[0])
        .sum()
    )
    return aciertos / len(out)


# Horquilla: se sube por una calle y se vuelve por la paralela, a 30 m. Es la
# geometría que rompe el criterio del plano —dos buses separados 100 m DE
# RECORRIDO están a 30 m en línea recta— y la que aparece en los intercambios de
# la simulación sobre trazados reales del GTFS.
CALLE = _calle([(0, 0), (700, 0), (700, 30), (0, 30)])

# Un bus se detiene antes de la horquilla; el de detrás lo alcanza y lo pasa.
# Con el criterio del plano la precisión cae al 80 %.
PARADA_Y_ADELANTAMIENTO = {
    "para": [500.0, 650.0, 800.0, 800.0, 800.0, 950.0, 1100.0, 1250.0, 1400.0, 1550.0],
    "pasa": [
        440.0,
        590.0,
        740.0,
        890.0,
        1040.0,
        1190.0,
        1340.0,
        1490.0,
        1640.0,
        1790.0,
    ],
}


def test_la_abscisa_resuelve_el_encuentro_que_las_coordenadas_no():
    """Con el eje del recorrido, el orden de los dos buses no se puede invertir."""
    sim = _capturar(PARADA_Y_ADELANTAMIENTO, CALLE)
    out = rastrear(sim.drop(columns=["verdad"]))
    assert _precision(out, sim) == 1.0, f"{_precision(out, sim):.1%}"


def test_sin_abscisa_ese_mismo_encuentro_se_intercambia():
    """Discriminación: el escenario ejercita la abscisa, no pasa por otro motivo."""
    sim = _capturar(PARADA_Y_ADELANTAMIENTO, CALLE, con_abscisa=False)
    out = rastrear(sim.drop(columns=["verdad"]))
    assert _precision(out, sim) < 1.0, "el escenario ya no necesita la abscisa"


def test_una_columna_de_abscisa_toda_nula_no_cambia_nada():
    """Sin abscisa fiable, el tracker tiene que comportarse como siempre.

    Es el 7 % de las posiciones reales: fuera de ruta (4,8 % en horario de
    servicio) o ambiguas (2,4 %), donde el map-matching no da abscisa de fiar.
    """
    sim = _capturar(PARADA_Y_ADELANTAMIENTO, CALLE, con_abscisa=False)
    con_columna = rastrear(sim.drop(columns=["verdad"]))
    sin_columna = rastrear(sim.drop(columns=["verdad", "abscisa_m"]))
    cols = ["vehicle_id", "dist_m", "dt_s", "vel_kmh"]
    assert con_columna[cols].equals(sin_columna[cols])


def test_la_abscisa_de_unas_filas_y_no_de_otras_no_rompe_la_identidad():
    """Mezcla realista: un bus entra en un tramo sin abscisa fiable y vuelve."""
    sim = _capturar(PARADA_Y_ADELANTAMIENTO, CALLE)
    sin_fiar = sim["snapshot_id"].isin([1003, 1004]) & (sim["verdad"] == "pasa")
    sim.loc[sin_fiar, "abscisa_m"] = np.nan
    out = rastrear(sim.drop(columns=["verdad"]))
    assert _precision(out, sim) == 1.0, f"{_precision(out, sim):.1%}"


def test_la_puerta_fisica_sigue_mandando_con_abscisa():
    """TRAMPA 008: un salto imposible no se acepta por mucho que la abscisa cuadre.

    El bus salta 900 m en un sondeo —por encima de `SALTO_MAX_M`— y su abscisa
    salta con él, así que el coste sobre el eje del recorrido es pequeño. Solo la
    puerta, que mide el desplazamiento real, puede rechazarlo.
    """
    saltos = {
        "salton": [100.0 + 120.0 * s + (900.0 if s >= 5 else 0.0) for s in range(10)]
    }
    sim = _capturar(saltos, CALLE, ruido_m=0.0)
    out = rastrear(sim.drop(columns=["verdad"]))
    antes = set(out[out["snapshot_id"] < 1005]["vehicle_id"])
    despues = set(out[out["snapshot_id"] >= 1005]["vehicle_id"])
    assert not (antes & despues), "emparejó por encima de la puerta física"


# Caso real de la flota sobre trazados del GTFS (línea 25, semilla 7): un bus
# parado ARRANCA y avanza 187 m mientras el de detrás mantiene su ritmo de 88 m.
# La asignación correcta cuesta 188 m sobre el recorrido y la intercambiada 186:
# gana el error por 2 m. Lo que las distingue es que el intercambio pone al de
# delante detrás, es decir, inventa un adelantamiento.
ARRANQUE_TRAS_PARADA = {
    "arranca": [23157.0, 23344.0, 23344.0, 23531.0, 23531.0, 23718.0],
    "sigue": [23100.0, 23187.0, 23275.0, 23362.0, 23450.0, 23537.0],
}
RECTA = _calle([(0, 0), (30000, 0)], paso=50.0)


def test_un_bus_que_arranca_no_se_intercambia_con_el_que_lo_sigue():
    """El coste sobre el recorrido empata por 2 m; decide no inventar adelantamientos."""
    sim = _capturar(ARRANQUE_TRAS_PARADA, RECTA, ruido_m=1.0)
    out = rastrear(sim.drop(columns=["verdad"]))
    assert _precision(out, sim) == 1.0, f"{_precision(out, sim):.1%}"


def test_sin_penalizar_el_adelantamiento_ese_arranque_se_intercambia(monkeypatch):
    """Discriminación: es la penalización de cruce la que resuelve el caso."""
    monkeypatch.setattr(tracking, "PENALIZACION_CRUCE_M", 0.0)
    sim = _capturar(ARRANQUE_TRAS_PARADA, RECTA, ruido_m=1.0)
    out = rastrear(sim.drop(columns=["verdad"]))
    assert _precision(out, sim) < 1.0, "el escenario ya no necesita la penalización"


def test_el_adelantamiento_de_verdad_se_sigue_reconociendo():
    """El techo de la penalización: un bus parado al que otro pasa es corriente.

    Si `PENALIZACION_CRUCE_M` sube por encima del margen de este escenario
    (135 m), el tracker deja de reconocer adelantamientos reales y los cambia por
    intercambios de identidad. Medido: a 120 m ya falla.
    """
    assert tracking.PENALIZACION_CRUCE_M <= 110.0, (
        "por encima se pierden adelantamientos"
    )
    sim = _capturar(PARADA_Y_ADELANTAMIENTO, CALLE)
    out = rastrear(sim.drop(columns=["verdad"]))
    assert _precision(out, sim) == 1.0
