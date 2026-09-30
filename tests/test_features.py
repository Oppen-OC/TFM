"""La tabla de entrenamiento contra pasos sintéticos de verdad conocida.

Una fila es el paso por la parada i de un viaje, en el instante t = t_obs(i), y el
objetivo es el retraso en el h-ésimo paso siguiente del mismo viaje. Cada
variable solo puede usar lo observado ANTES de t: un error aquí no lanza nada,
da un modelo que acierta en la prueba porque ve el futuro. Es la fuga que el
tribunal busca primero (ADR-007).
"""

from __future__ import annotations

import json

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
    t = features.construir(pasos, objetivo=OBJ, lags_min=(5,), ventanas_flota_min=(5,))
    # Por nombre, no con la constante: vaciarla no puede dejar el test en verde.
    assert not {"desfase_s", "margen_s", "coste_s"} & set(t.columns)
    assert set(features.variables((5,), (5,))) <= set(t.columns)
    assert OBJ not in features.variables((5,))


# --------------------------------------------------------------------------- #
# Fase 2: la flota como sensor del tramo aguas abajo (bitácora 032)
# --------------------------------------------------------------------------- #
def _tramo(viaje, t_ini, t_fin, ganado, linea="1"):
    """Un viaje que recorre P01 -> P02 empezando en hora y ganando `ganado` s."""
    return [
        _paso(viaje, 1, t_ini, 0, linea=linea),
        _paso(viaje, 2, t_fin, ganado, linea=linea),
    ]


def test_el_tramo_aguas_abajo_lo_miden_otros_buses_antes_de_t():
    """Mediana del retraso ganado en P01 -> P02 por los que ACABARON antes de t.

    Cuenta cualquier línea que comparta las dos paradas: la congestión es del
    viario, no de la línea. El que acaba el tramo en t o después ve el futuro.
    """
    filas = [
        _paso("A", 1, 10, 0),  # la fila evaluada: t = 10 min, objetivo P02
        _paso("A", 2, 12, 0),
        *_tramo("B", 4, 6, 60),  # acaba 4 min antes: cuenta
        *_tramo("C", 7, 9, 120),  # cuenta
        # otra línea, mismas paradas: cuenta; y es un extremo, que la mediana ignora
        *_tramo("F", 5, 7.5, 900, linea="2"),
        *_tramo("D", 8, 10, 999),  # acaba justo en t: no cuenta
        *_tramo("E", 1, 3, 500),  # acaba 7 min antes: fuera de la ventana de 5
        *_tramo("G", 9, 11, 999),  # acaba después de t: no cuenta
    ]
    t = _construir(filas, horizonte=1, ventanas_flota_min=(5,), soporte_min=2)
    f = _fila(t, "A", 1)
    # mediana de 60, 120 y 900; la media sería 360
    assert f["tramo_ganado_5min"] == 120.0
    assert f["tramo_soporte_5min"] == 3


def test_el_tramo_sin_soporte_suficiente_no_se_estima():
    """Un solo bus no es congestión: puede ser una avería. Nulo, no cero."""
    filas = [_paso("A", 1, 10, 0), _paso("A", 2, 12, 0), *_tramo("B", 6, 8, 300)]
    f = _fila(
        _construir(filas, horizonte=1, ventanas_flota_min=(5,), soporte_min=2), "A", 1
    )
    assert f["tramo_soporte_5min"] == 1
    assert np.isnan(f["tramo_ganado_5min"])


# --------------------------------------------------------------------------- #
# Soporte por línea (ADR-018)
# --------------------------------------------------------------------------- #
def _viajes(linea, n, dias):
    """`n` viajes de la línea en `dias` días, dos filas por viaje.

    Aquí el mismo `viaje_id` se repite de un día a otro a propósito. En la
    captura real ya no pasa, porque lleva la fecha dentro (bitácora 027), pero la
    clave de viaje del módulo es el par (día de servicio, `viaje_id`) y el
    recuento tiene que respetarla.
    """
    dia0 = pd.Timestamp("2026-09-14")
    return pd.DataFrame(
        [
            {
                "linea": linea,
                "viaje_id": f"v{i // dias}",
                "fecha_servicio": dia0 + pd.Timedelta(days=i % dias),
            }
            for i in range(n)
            for _ in range(2)
        ]
    )


def test_el_soporte_de_una_linea_se_cuenta_en_viajes_y_dias():
    """100 viajes en 3 días de prueba y 100 de entrenamiento: cifra propia."""
    # F solo está en entrenamiento: no aparece en el soporte.
    train = pd.concat([_viajes(x, 100, 5) for x in "ABCF"] + [_viajes("E", 99, 5)])
    test = pd.concat(
        [
            _viajes("A", 100, 3),  # justo en el umbral
            _viajes("B", 99, 3),  # un viaje menos; en filas serían 198
            _viajes("C", 100, 2),  # los viajes, pero en dos días
            _viajes("D", 500, 5),  # no está en entrenamiento
            _viajes("E", 100, 3),  # en entrenamiento no llega a 100
        ]
    )
    s = features.soporte_por_linea(train, test, min_viajes=100, min_dias=3)
    assert s["grupo"].to_dict() == {
        "A": "propia",
        "B": "poco_soporte",
        "C": "poco_soporte",
        "D": "sin_entrenamiento",
        "E": "poco_soporte",
    }
    assert s.at["B", "viajes"] == 99 and s.at["A", "dias"] == 3
    vacio = features.soporte_por_linea(train, test.iloc[:0])
    assert vacio.empty and "grupo" in vacio.columns


def test_los_baselines_traen_el_soporte_y_los_grupos():
    test = pd.DataFrame(
        {
            "linea": ["A", "A", "B"],
            "fecha_servicio": pd.Timestamp("2026-09-14"),
            "viaje_id": ["a", "a", "b"],
            "retraso_s": [10.0, 20.0, 0.0],
            OBJ: [20.0, 20.0, 100.0],
        }
    )
    s = features.soporte_por_linea(test[test["linea"] == "A"], test, 1, 1)
    b = features.baselines(test, OBJ, s)
    assert b["por_linea"]["A"]["grupo"] == "propia"
    assert b["por_linea"]["A"]["viajes"] == 1
    assert b["por_linea"]["B"]["grupo"] == "sin_entrenamiento"
    assert b["por_grupo"]["sin_entrenamiento"]["persistencia"]["mae_s"] == 100.0
    assert b["persistencia"]["mae_s"] == pytest.approx(36.67)  # (10 + 0 + 100) / 3
    json.dumps(b)  # va a metrics/features.json: tiene que ser serializable
