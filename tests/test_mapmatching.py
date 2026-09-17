"""Map-matching contra el GTFS, con verdad-terreno construida a mano.

Cada posición de la EMT se convierte en abscisa sobre su trazado (metros desde
cabecera), con el trazado asignado y la distancia a él. Es el eje del retraso
—el paso por parada se interpola sobre él— y la información que le falta al
tracker para distinguir dos buses de la misma línea (bitácora 015).

Los trazados se construyen en metros sobre un plano local y se convierten a
grados con la misma proyección que usa `project.gtfs`, así que la abscisa
esperada de cada posición se conoce exactamente. Los feeds sintéticos son ZIP
con la forma del de la EMT: `shape_pt_sequence` como texto y `shape_dist_traveled`
poblado y falso (trampa 010).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from project.gtfs import a_grados, cargar_trazados
from project.mapmatching import FUERA_DE_RUTA_M, emparejar, proyectar

T0 = pd.Timestamp("2026-08-26T10:00:00Z")


# --------------------------------------------------------------------------- #
# Constructores
# --------------------------------------------------------------------------- #
def _polilinea(vertices: list[tuple[float, float]], paso_m: float = 25.0) -> np.ndarray:
    """Densifica una polilínea en metros, como vienen los trazados del GTFS."""
    puntos = [np.array(vertices[0], dtype=float)]
    for a, b in zip(vertices[:-1], vertices[1:]):
        a, b = np.array(a, dtype=float), np.array(b, dtype=float)
        n = max(int(np.ceil(np.hypot(*(b - a)) / paso_m)), 1)
        puntos += [a + (b - a) * k / n for k in range(1, n + 1)]
    return np.array(puntos)


def _en_abscisa(xy: np.ndarray, s: float) -> tuple[float, float]:
    """Punto de la polilínea a `s` metros de su inicio."""
    acum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    return float(np.interp(s, acum, xy[:, 0])), float(np.interp(s, acum, xy[:, 1]))


def _feed(
    ruta: Path,
    trazados: dict[str, tuple[str, str, np.ndarray]],
    escala_sdt: float = 3.0,
) -> Path:
    """Escribe un GTFS mínimo: `trazados` mapea shape_id -> (route_id, linea, xy)."""
    rutas = {(rid, linea) for rid, linea, _ in trazados.values()}
    routes = pd.DataFrame(
        [{"route_id": rid, "route_short_name": linea} for rid, linea in sorted(rutas)]
    )
    trips = pd.DataFrame(
        [
            {"route_id": rid, "service_id": "S", "trip_id": f"t_{sid}", "shape_id": sid}
            for sid, (rid, _, _) in trazados.items()
        ]
    )
    filas = []
    for sid, (_, _, xy) in trazados.items():
        lat, lon = a_grados(xy[:, 0], xy[:, 1])
        orden = np.random.default_rng(0).permutation(len(xy))  # desordenado a propósito
        for i in orden:
            filas.append(
                {
                    "shape_id": sid,
                    "shape_pt_lat": f"{lat[i]:.7f}",
                    "shape_pt_lon": f"{lon[i]:.7f}",
                    "shape_pt_sequence": str(i + 1),  # texto: "10" < "2"
                    # Trampa 010: poblado, y NO es distancia.
                    "shape_dist_traveled": f"{i * 25.0 * escala_sdt:.1f}",
                }
            )
    shapes = pd.DataFrame(filas)
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, df in (
            ("routes.txt", routes),
            ("trips.txt", trips),
            ("shapes.txt", shapes),
        ):
            buf = io.StringIO()
            df.to_csv(buf, index=False)
            z.writestr(nombre, buf.getvalue())
    return ruta


def _posiciones(
    recorridos: dict[str, tuple[str, str, np.ndarray, list[float]]],
    ruido_m: float = 0.0,
    lateral_m: float = 0.0,
    semilla: int = 0,
) -> pd.DataFrame:
    """`recorridos` mapea vehicle_id -> (linea, trayecto, xy, [abscisa por sondeo])."""
    rng = np.random.default_rng(semilla)
    filas = []
    for vid, (linea, trayecto, xy, abscisas) in recorridos.items():
        for k, s in enumerate(abscisas):
            x, y = _en_abscisa(xy, s)
            x += rng.normal(0, ruido_m) if ruido_m else 0.0
            y += (rng.normal(0, ruido_m) if ruido_m else 0.0) + lateral_m
            lat, lon = a_grados(x, y)
            filas.append(
                {
                    "snapshot_id": 1000 + k,
                    "linea": linea,
                    "trayecto": trayecto,
                    "lat": float(lat),
                    "lon": float(lon),
                    "ts_utc": T0 + pd.Timedelta(seconds=30 * k),
                    "vehicle_id": vid,
                    "abscisa_verdad": s,
                }
            )
    return pd.DataFrame(filas)


RECTA_L = _polilinea([(0, 0), (2000, 0), (2000, 1500)])  # 3.500 m con un giro


# --------------------------------------------------------------------------- #
# Carga del feed
# --------------------------------------------------------------------------- #
def test_la_secuencia_del_trazado_se_ordena_como_numero(tmp_path):
    """`shape_pt_sequence` llega como texto: ordenado así, "10" va antes que "2"."""
    feed = _feed(tmp_path / "gtfs.zip", {"S1": ("R1", "1", RECTA_L)})
    (trazado,) = cargar_trazados(feed)["1"]
    assert trazado.largo == pytest.approx(3500.0, abs=1.0), trazado.largo


def test_la_abscisa_es_geometria_y_no_shape_dist_traveled(tmp_path):
    """TRAMPA 010: el campo del feed es el horario reescalado, no distancia.

    Aquí vale tres veces la longitud real. Si el trazado lo usara, el final de la
    ruta estaría a 10,5 km y no a 3,5.
    """
    feed = _feed(tmp_path / "gtfs.zip", {"S1": ("R1", "1", RECTA_L)}, escala_sdt=3.0)
    (trazado,) = cargar_trazados(feed)["1"]
    x, y = _en_abscisa(RECTA_L, 3000.0)
    r = proyectar(np.array([x]), np.array([y]), trazado)
    assert r["abscisa_m"][0] == pytest.approx(3000.0, abs=1.0)
    assert trazado.largo == pytest.approx(3500.0, abs=1.0)


def test_lineas_con_el_mismo_nombre_conservan_sus_trazados(tmp_path):
    """`route_short_name` no es única: 73, C2 y C3 tienen dos `route_id` cada una."""
    otra = _polilinea([(0, 3000), (3000, 3000)])
    feed = _feed(
        tmp_path / "gtfs.zip",
        {"S1": ("R1", "C2", RECTA_L), "S2": ("R2", "C2", otra)},
    )
    ids = {t.shape_id for t in cargar_trazados(feed)["C2"]}
    assert ids == {"S1", "S2"}


# --------------------------------------------------------------------------- #
# Proyección
# --------------------------------------------------------------------------- #
@pytest.fixture
def trazado_l(tmp_path):
    (t,) = cargar_trazados(_feed(tmp_path / "gtfs.zip", {"S1": ("R1", "1", RECTA_L)}))[
        "1"
    ]
    return t


def test_la_abscisa_recupera_la_verdad_con_ruido_gps(trazado_l):
    """Sin ruido la abscisa es exacta; con 2 m de ruido, el medido en real, el error
    es el propio ruido a lo largo del trazado y no más.

    No se exige un máximo: la componente longitudinal de un ruido N(0, 2 m) supera
    los 5 m en alguna de 200 muestras por puro azar. Lo que delataría una mala
    proyección es un error sistemático, y eso lo miden la media y el p90.
    """
    verdad = np.linspace(50, 3450, 200)
    xy = np.array([_en_abscisa(RECTA_L, s) for s in verdad])
    limpio = proyectar(xy[:, 0], xy[:, 1], trazado_l)
    assert np.abs(limpio["abscisa_m"] - verdad).max() <= 0.5

    xy += np.random.default_rng(1).normal(0, 2.0, xy.shape)
    error = np.abs(proyectar(xy[:, 0], xy[:, 1], trazado_l)["abscisa_m"] - verdad)
    assert error.mean() <= 2.0, f"error medio {error.mean():.2f} m"
    assert np.quantile(error, 0.9) <= 4.0, f"p90 {np.quantile(error, 0.9):.2f} m"


def test_la_distancia_al_trazado_es_la_lateral(trazado_l):
    x, y = _en_abscisa(RECTA_L, 1000.0)
    r = proyectar(np.array([x]), np.array([y + 40.0]), trazado_l)
    assert r["dist_m"][0] == pytest.approx(40.0, abs=0.5)
    assert r["abscisa_m"][0] == pytest.approx(1000.0, abs=0.5)


def test_el_cierre_de_una_circular_es_ambiguo(tmp_path):
    """En una circular, cabecera y final coinciden: la abscisa puede ser 0 o el total.

    Lo mismo pasa en cualquier trazado que vuelve a pasar por una calle. No se
    elige en silencio: se marca, y la decisión se toma con la trayectoria.
    """
    circular = _polilinea([(0, 0), (1000, 0), (1000, 800), (0, 800), (0, 0)])
    (t,) = cargar_trazados(_feed(tmp_path / "gtfs.zip", {"C": ("RC", "C3", circular)}))[
        "C3"
    ]
    cerca_del_cierre = _en_abscisa(circular, 5.0)
    lejos = _en_abscisa(circular, 1400.0)
    r = proyectar(
        np.array([cerca_del_cierre[0], lejos[0]]),
        np.array([cerca_del_cierre[1], lejos[1]]),
        t,
    )
    assert bool(r["ambigua"][0]) is True
    assert bool(r["ambigua"][1]) is False


# --------------------------------------------------------------------------- #
# Emparejamiento de un conjunto de posiciones
# --------------------------------------------------------------------------- #
def test_el_sentido_lo_decide_el_movimiento_y_no_la_distancia(tmp_path):
    """Ida y vuelta por la misma calle: los dos trazados están a la misma distancia.

    Solo el avance a lo largo del trazado distingue el sentido. Con la distancia
    sola, la mitad de los buses quedarían en el trazado contrario, con la abscisa
    corriendo hacia atrás.
    """
    ida = RECTA_L
    vuelta = RECTA_L[::-1].copy()
    feed = _feed(
        tmp_path / "gtfs.zip", {"IDA": ("R1", "1", ida), "VUELTA": ("R1", "1", vuelta)}
    )
    pos = _posiciones(
        {
            "v1": ("1", "A - B", ida, list(np.arange(100, 1300, 120.0))),
            "v2": ("1", "B - A", vuelta, list(np.arange(200, 1400, 120.0))),
        },
        ruido_m=2.0,
    )
    out = emparejar(pos, cargar_trazados(feed))
    asignado = out.groupby("trayecto")["shape_id"].agg(lambda s: s.mode().iloc[0])
    assert asignado.to_dict() == {"A - B": "IDA", "B - A": "VUELTA"}
    for tray, g in out.groupby("trayecto"):
        assert np.abs(g["abscisa_m"] - g["abscisa_verdad"]).max() <= 5.0, tray


def test_los_buses_fuera_de_la_ruta_no_deciden_el_trazado(tmp_path):
    """Un bus fuera de servicio sigue publicando su línea y su trayecto.

    Sobre la captura real son la mayoría de madrugada —45-66 % de las posiciones
    entre las 0 y las 6 h están fuera de ruta, la mitad de ellas en diez celdas de
    100 m—, y el tracker les da los primeros `vehicle_id` del día. Elegir el
    trazado con ellos asignó a la línea 24 uno a 4 km de mediana, cuando sus buses
    circulan a 2 m del suyo.

    Aquí maniobran en una explanada a 150 m de la calle, en el sentido CONTRARIO
    al de los que circulan, y son doce veces más. Si cuentan, ganan el voto del
    sentido y el trazado sale invertido: la abscisa correría hacia atrás para
    todos. Se apoyan además en el desempate alfabético, que favorece a "IDA".
    """
    ida = RECTA_L
    vuelta = RECTA_L[::-1].copy()
    feed = _feed(
        tmp_path / "gtfs.zip", {"IDA": ("R1", "1", ida), "VUELTA": ("R1", "1", vuelta)}
    )
    # Solo sobre el tramo horizontal: ahí el desplazamiento lateral saca de la
    # ruta de verdad. Sobre el tramo vertical, 150 m «al lado» es avanzar por ella.
    maniobrando = {
        f"a{i:03d}": (
            "1",
            "A - B",
            ida,
            list(np.arange(100 + 10 * i, 700 + 10 * i, 120.0)),
        )
        for i in range(60)
    }
    circulando = {
        f"z{i:03d}": (
            "1",
            "A - B",
            vuelta,
            list(np.arange(100 + 30 * i, 1300 + 30 * i, 120.0)),
        )
        for i in range(5)
    }
    fuera = _posiciones(maniobrando, ruido_m=2.0, lateral_m=150.0)
    dentro = _posiciones(circulando, ruido_m=2.0)
    out = emparejar(
        pd.concat([fuera, dentro], ignore_index=True), cargar_trazados(feed)
    )

    en_ruta = out[out["vehicle_id"].str.startswith("z")]
    assert set(out["shape_id"]) == {"VUELTA"}, "eligió con los que están fuera de ruta"
    assert np.abs(en_ruta["abscisa_m"] - en_ruta["abscisa_verdad"]).max() <= 6.0
    assert out.loc[out["vehicle_id"].str.startswith("a"), "fuera_de_ruta"].all()


def test_la_linea_duplicada_se_desempata_por_geometria(tmp_path):
    otra = _polilinea([(0, 3000), (3000, 3000)])
    feed = _feed(
        tmp_path / "gtfs.zip",
        {"S1": ("R1", "C2", RECTA_L), "S2": ("R2", "C2", otra)},
    )
    pos = _posiciones({"v": ("C2", "X - Y", otra, list(np.arange(100, 2000, 150.0)))})
    out = emparejar(pos, cargar_trazados(feed))
    assert set(out["shape_id"]) == {"S2"}


def test_linea_sin_trazado_queda_marcada_y_no_se_inventa(tmp_path):
    """96, 98E y 100 se capturan pero no están en el GTFS: 0,92 % de las posiciones."""
    feed = _feed(tmp_path / "gtfs.zip", {"S1": ("R1", "1", RECTA_L)})
    pos = _posiciones({"v": ("98E", "X - Y", RECTA_L, [100.0, 300.0, 500.0])})
    out = emparejar(pos, cargar_trazados(feed))
    assert out["shape_id"].isna().all()
    assert out["abscisa_m"].isna().all()
    assert (out["motivo"] == "sin_trazado").all()


def test_posicion_lejos_del_trazado_es_fuera_de_ruta(tmp_path):
    feed = _feed(tmp_path / "gtfs.zip", {"S1": ("R1", "1", RECTA_L)})
    pos = _posiciones(
        {"v": ("1", "A - B", RECTA_L, list(np.arange(100, 1300, 120.0)))},
        lateral_m=FUERA_DE_RUTA_M * 3,
    )
    out = emparejar(pos, cargar_trazados(feed))
    assert out["fuera_de_ruta"].all()


def test_lejos_del_centro_pero_sobre_la_ruta_no_se_descarta(tmp_path):
    """TRAMPA 006: las líneas 24 y 25 bajan a El Perellonet, 22 km al sur.

    El filtro es la distancia al trazado de SU línea, nunca una caja geográfica:
    una caja borraría dos líneas enteras, justo las peor cubiertas por tráfico.
    Las posiciones quedan a ~39,27°, bajo el corte de 39,36° que un saneamiento
    por caja usaría: si el test las dejara por encima, no guardaría nada.
    """
    perellonet = _polilinea([(0, 0), (0, -22000), (500, -23000)])
    feed = _feed(tmp_path / "gtfs.zip", {"S25": ("R25", "25", perellonet)})
    pos = _posiciones(
        {
            "v": (
                "25",
                "Valencia - El Perellonet",
                perellonet,
                [21000.0, 21200.0, 21400.0, 21600.0],
            )
        },
        ruido_m=2.0,
    )
    assert (pos["lat"] < 39.36).all(), "el escenario no baja del corte de la caja"
    out = emparejar(pos, cargar_trazados(feed))
    assert not out["fuera_de_ruta"].any()
    assert out["abscisa_m"].notna().all()


def test_posicion_sin_trayecto_queda_marcada(tmp_path):
    """0,04 % de las posiciones reales llegan sin `trayecto`: no hay sentido que asignar."""
    feed = _feed(tmp_path / "gtfs.zip", {"S1": ("R1", "1", RECTA_L)})
    pos = _posiciones({"v": ("1", "A - B", RECTA_L, [100.0, 300.0, 500.0])})
    pos.loc[1, "trayecto"] = None
    out = emparejar(pos, cargar_trazados(feed))
    assert out.loc[out["trayecto"].isna(), "motivo"].eq("sin_trayecto").all()
    assert out.loc[out["trayecto"].notna(), "shape_id"].eq("S1").all()


def test_emparejar_no_reordena_ni_pierde_filas(tmp_path):
    feed = _feed(tmp_path / "gtfs.zip", {"S1": ("R1", "1", RECTA_L)})
    pos = _posiciones({"v": ("1", "A - B", RECTA_L, list(np.arange(100, 1300, 120.0)))})
    pos = pos.sample(frac=1, random_state=4)
    out = emparejar(pos, cargar_trazados(feed))
    assert out.index.equals(pos.index)
    assert out["lat"].equals(pos["lat"])
