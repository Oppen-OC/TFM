"""Qué tramos de la capa 192 cubren cada trozo de recorrido (ADR-024).

Geometría sintética de verdad conocida: un trazado recto de 1 km por el eje x y
tramos de tráfico paralelos, alejados, cortos, perpendiculares o con un desvío.
Un tramo cubre el recorrido si va a menos de `dist_max` metros DURANTE al menos
`largo_min` metros de recorrido: cruzarlo no es recorrerlo.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from project import trafico
from project.gtfs import Trazado, a_grados


def _recta(largo: float = 1000.0, shape_id: str = "S1") -> Trazado:
    x = np.arange(0.0, largo + 1, 100.0)
    return Trazado(shape_id, "R1", "1", x, np.zeros_like(x), x.copy())


def _cubre(xs, ys, trazado=None, **kw):
    kw = {"dist_max": 25.0, "largo_min": 50.0, **kw}
    return trafico.cubrir(
        np.array(xs, float), np.array(ys, float), trazado or _recta(), **kw
    )


def test_un_tramo_paralelo_cerca_cubre_su_intervalo_y_uno_lejos_no():
    ((lo, hi),) = _cubre([200, 500], [10, 10])
    assert lo == pytest.approx(200) and hi == pytest.approx(500)
    assert _cubre([200, 500], [40, 40]) == []


def test_un_tramo_corto_o_que_cruza_no_cubre():
    """30 m de tramo, o una calle perpendicular: menos de 50 m de recorrido."""
    assert _cubre([600, 630], [5, 5]) == []
    assert _cubre([800, 800], [-100, 100]) == []


def test_un_tramo_que_se_aparta_a_mitad_da_dos_intervalos():
    xs, ys = [0, 200, 220, 280, 300, 500], [10, 10, 60, 60, 10, 10]
    cubiertos = _cubre(xs, ys)
    assert len(cubiertos) == 2
    (a, b), (c, d) = cubiertos
    assert a == pytest.approx(0) and b == pytest.approx(200, abs=15)
    assert c == pytest.approx(300, abs=15) and d == pytest.approx(500)


def test_tramos_ruta_cruza_cada_tramo_con_cada_trazado_de_cada_version():
    """La geometría llega en WKT, lon lat; el resultado va por versión y trazado."""

    def wkt(xs, ys):
        lat, lon = a_grados(np.array(xs, float), np.array(ys, float))
        return "LINESTRING (" + ", ".join(f"{a} {b}" for a, b in zip(lon, lat)) + ")"

    tramos = pd.DataFrame(
        {
            "idtramo": [7.0, 8.0],
            "geom_wkt": [wkt([100, 400], [5, 5]), wkt([100, 400], [500, 500])],
        }
    )
    r = trafico.tramos_ruta(
        [("F1", _recta()), ("F2", _recta(shape_id="S2"))],
        tramos,
        dist_max=25.0,
        largo_min=50.0,
    )
    assert r[["feed_version", "shape_id", "idtramo"]].values.tolist() == [
        ["F1", "S1", 7],
        ["F2", "S2", 7],
    ]
    assert r["s_ini"].round().tolist() == [100, 100]
    assert r["s_fin"].round().tolist() == [400, 400]


# --------------------------------------------------------------------------- #
# El estado del tráfico en el recorrido que le queda al bus
# --------------------------------------------------------------------------- #
T0 = pd.Timestamp("2026-09-23 08:00", tz="UTC")


def _min(m: float) -> pd.Timestamp:
    return T0 + pd.Timedelta(minutes=m)


INTERVALOS = pd.DataFrame(
    {
        "feed_version": "F1",
        "shape_id": "S1",
        "idtramo": [7, 8, 9],
        "s_ini": [100.0, 300.0, 700.0],
        "s_fin": [400.0, 600.0, 800.0],
    }
)
# A los 0 min: el 7 denso, el 8 fluido, el 9 cortado (no observado).
# A los 5 min: el 7 fluido, el 8 congestionado, el 9 con fallo del servicio.
ESTADOS = pd.DataFrame(
    {
        "ts_ingest_utc": [_min(0)] * 3 + [_min(5)] * 3,
        "idtramo": [7, 8, 9, 7, 8, 9],
        "estado": [1, 0, 3, 0, 2, 4],
    }
)


def _en_ruta(filas, edad_max_s=900):
    filas = pd.DataFrame(
        filas, columns=["shape_id", "s_desde", "s_hasta", "t_disp_utc"]
    )
    return trafico.en_ruta(
        filas.assign(feed_version="F1"), INTERVALOS, ESTADOS, edad_max_s=edad_max_s
    )


def test_la_congestion_es_la_del_ultimo_sondeo_llegado_antes_del_ahora():
    r = _en_ruta(
        [
            ("S1", 200, 500, _min(2)),  # sondeo de los 0: 7 denso 200 m, 8 fluido 200 m
            ("S1", 350, 600, _min(6)),  # sondeo de los 5: 7 fluido 50 m, 8 cong. 250 m
            ("S1", 100, 300, _min(5)),  # justo a los 5: aún vale el de los 0 (7 denso)
        ]
    )
    assert r["trafico_cubierto_m"].tolist() == [400, 300, 200]
    assert r["trafico_congestion_frac"].round(3).tolist() == [0.5, 0.833, 1.0]
    assert r["trafico_edad_s"].tolist() == [120, 60, 300]


def test_cortado_y_fallo_del_servicio_no_son_observaciones():
    """El 9 tiene sensor (cuenta en lo cubierto) pero ningún estado válido."""
    r = _en_ruta([("S1", 650, 850, _min(2)), ("S1", 650, 850, _min(6))])
    assert r["trafico_cubierto_m"].tolist() == [100, 100]
    assert r["trafico_congestion_frac"].isna().all()


def test_sin_sondeo_reciente_o_sin_sensor_no_hay_congestion():
    r = _en_ruta(
        [
            ("S1", 200, 500, _min(-1)),  # antes del primer sondeo
            ("S1", 200, 500, _min(30)),  # el último tiene 25 min: más de 15
            ("S9", 0, 1000, _min(2)),  # trazado sin ningún tramo de tráfico
        ]
    )
    assert r["trafico_cubierto_m"].tolist() == [400, 400, 0]
    assert r["trafico_congestion_frac"].isna().all()
    assert np.isnan(r["trafico_edad_s"].iloc[0])
    assert r["trafico_edad_s"].iloc[1] == 25 * 60
