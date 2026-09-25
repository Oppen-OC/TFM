"""La tabla de entrenamiento contra pasos sintéticos de verdad conocida.

Una fila es el paso por la parada i de un viaje, en el instante t = t_obs(i), y el
objetivo es el retraso en el h-ésimo paso siguiente del mismo viaje. Cada
variable solo puede usar lo observado ANTES de t: un error aquí no lanza nada,
da un modelo que acierta en la prueba porque ve el futuro. Es la fuga que el
tribunal busca primero (ADR-007).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from project import features

T0 = pd.Timestamp("2026-09-16 08:00", tz="Europe/Madrid")
OBJ = "retraso_siguiente_parada_s"


def _paso(viaje, seq, t_min, retraso, linea="1", stop=None, dia="2026-09-16"):
    return {
        "viaje_id": viaje,
        "fecha_servicio": pd.Timestamp(dia),
        "linea": linea,
        "trayecto": "Ida",
        "stop_id": stop or f"P{seq:02d}",
        "stop_sequence": seq,
        "abscisa_parada_m": 400.0 * (seq - 1),
        "t_prog_s": 8 * 3600 + 60.0 * t_min,
        "retraso_s": float(retraso),
        "t_obs_utc": T0 + pd.Timedelta(minutes=t_min),
    }


def _construir(filas, **kw):
    return features.construir(pd.DataFrame(filas), objetivo=OBJ, **kw)


def _fila(tabla, viaje, seq):
    return tabla[(tabla["viaje_id"] == viaje) & (tabla["stop_sequence"] == seq)].iloc[0]


def test_el_objetivo_es_el_retraso_del_paso_siguiente_del_mismo_viaje():
    filas = [_paso("A", s, 2 * s, 10 * s) for s in range(1, 5)]
    filas += [_paso("B", s, 2 * s, 1000 + s) for s in range(1, 5)]
    t = _construir(filas, horizonte=1)
    assert _fila(t, "A", 2)[OBJ] == 30.0
    assert _fila(t, "B", 1)[OBJ] == 1002.0
    # el último paso de cada viaje no tiene objetivo y no entra
    assert set(t.loc[t["viaje_id"] == "A", "stop_sequence"]) == {1, 2, 3}
    t2 = _construir(filas, horizonte=2)
    assert _fila(t2, "A", 1)[OBJ] == 30.0
    assert _fila(t, "A", 2)["retraso_s"] == 20.0  # la persistencia


def test_el_objetivo_binario_usa_el_umbral():
    filas = [_paso("A", 1, 0, 0), _paso("A", 2, 2, 301), _paso("A", 3, 4, 300)]
    t = _construir(filas, horizonte=1, umbral_s=300)
    assert _fila(t, "A", 1)[OBJ + "_bin"] == 1
    assert _fila(t, "A", 2)[OBJ + "_bin"] == 0


def test_el_estado_de_la_linea_solo_ve_el_pasado_y_otros_viajes():
    """La fuga: lo que pasa en t o después, y el propio viaje, no cuentan."""
    filas = [
        _paso("A", 1, 8, 555),  # el propio viaje, dentro de la ventana: no cuenta
        _paso("A", 2, 10, 555),  # la fila evaluada: t = 10 min
        _paso("A", 3, 12, 0),
        _paso("B", 1, 7, 100),  # otro viaje, 3 min antes: cuenta
        _paso("C", 1, 10, 999),  # justo en t: no cuenta
        _paso("D", 1, 11, 999),  # después: no cuenta
        _paso("E", 1, 3, 777),  # 7 min antes: fuera de la ventana de 5
        _paso("F", 1, 8, 200, linea="2"),  # otra línea: no cuenta
    ]
    f = _fila(_construir(filas, horizonte=1, lags_min=(5,)), "A", 2)
    assert f["linea_retraso_5min"] == 100.0
    assert f["linea_pasos_5min"] == 1


def test_el_bus_anterior_es_el_ultimo_que_paso_por_la_parada_objetivo_antes_de_t():
    """Por la parada i+h, con t_obs estrictamente anterior al paso por i."""
    filas = [
        _paso("A", 1, 10, 0),  # t = 10 min; la parada objetivo es P02
        _paso("A", 2, 12, 0),
        _paso("B", 2, 8, 50),  # pasó por P02 2 min antes de t: este
        _paso("C", 2, 5, 70),  # antes aún: no es el último
        _paso("D", 2, 10, 999),  # justo en t: no cuenta
        _paso("E", 2, 10.5, 999),  # después: no cuenta
    ]
    f = _fila(_construir(filas, horizonte=1), "A", 1)
    assert f["bus_anterior_retraso_s"] == 50.0
    assert f["bus_anterior_edad_s"] == pytest.approx(120.0)


def test_los_retrasos_anteriores_del_viaje_son_lags():
    filas = [_paso("A", s, 2 * s, 10 * s) for s in range(1, 6)]
    f = _fila(_construir(filas, horizonte=1), "A", 3)
    assert (f["retraso_s"], f["retraso_lag1_s"], f["retraso_lag2_s"]) == (30, 20, 10)
    assert f["t_prog_hasta_objetivo_s"] == pytest.approx(120.0)
    assert f["dist_objetivo_m"] == pytest.approx(400.0)


def test_el_orden_de_las_filas_de_entrada_no_cambia_la_tabla():
    """Todo se une por clave, nunca por posición (trampa 012)."""
    rng = np.random.default_rng(0)
    filas = [
        _paso(v, s, 3 * s + i, rng.normal(0, 100))
        for i, v in enumerate("ABCDEF")
        for s in range(1, 7)
    ]
    a = _construir(filas, horizonte=1)
    b = features.construir(
        pd.DataFrame(filas).sample(frac=1, random_state=1), objetivo=OBJ, horizonte=1
    )
    clave = ["viaje_id", "stop_sequence"]
    pd.testing.assert_frame_equal(
        a.sort_values(clave).reset_index(drop=True),
        b.sort_values(clave).reset_index(drop=True),
    )


def test_el_split_es_por_dia_de_servicio_y_no_parte_viajes():
    filas = [_paso("A", s, 2 * s, 0, dia="2026-09-13") for s in range(1, 4)]
    filas += [_paso("B", s, 2 * s, 0, dia="2026-09-14") for s in range(1, 4)]
    # Como llega de `pasos`: fechas `date` en unas particiones y `datetime64` en otras.
    for f in filas[3:]:
        f["fecha_servicio"] = f["fecha_servicio"].date()
    train, test = features.partir(_construir(filas), "2026-09-14")
    assert set(train["viaje_id"]) == {"A"} and set(test["viaje_id"]) == {"B"}
    assert (train["fecha_servicio"] < "2026-09-14").all()
    assert (test["fecha_servicio"] >= "2026-09-14").all()


def test_la_tabla_no_lleva_diagnosticos_que_miran_el_futuro_y_trae_sus_variables():
    """`desfase_s` resume las primeras paradas del viaje: en la 1 incluye la 2 y la 3."""
    filas = [_paso("A", s, 2 * s, 10 * s) for s in range(1, 5)]
    pasos = pd.DataFrame(filas).assign(desfase_s=1.0, margen_s=1.0, coste_s=1.0)
    t = features.construir(pasos, objetivo=OBJ, lags_min=(5,))
    assert not set(features.FUERA_DE_LA_TABLA) & set(t.columns)
    assert set(features.variables((5,))) <= set(t.columns)
    assert OBJ not in features.variables((5,))
