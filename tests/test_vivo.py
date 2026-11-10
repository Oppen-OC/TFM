"""El núcleo del ciclo en vivo contra pasos sintéticos hechos a mano.

Lo que se prueba es la frontera del «ahora»: un paso cuyo retraso aún no había
llegado (`t_disp_utc > ahora`) no existe para el ciclo (ADR-022, trampa 017), y
la parada del tutor se busca en el horario, no entre los pasos observados.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from project import features
from project.config import RAIZ
from project.services.vivo import (
    Marcador,
    Prediccion,
    candidatos,
    pendientes,
    separar,
    tabla,
)

T0 = pd.Timestamp("2026-11-10 09:00", tz="UTC")
AHORA = T0 + pd.Timedelta(minutes=30)
DIA = pd.Timestamp("2026-11-10")
OBJ = "retraso_siguiente_parada_s"
CFG = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]


def _paso(viaje, seq, retraso=10.0, t_disp="antes", linea="1"):
    """`t_disp`: «antes» del ahora, «despues» o None (sin disponibilidad)."""
    llega = {
        "antes": AHORA - pd.Timedelta(minutes=20 - seq),
        "despues": AHORA + pd.Timedelta(seconds=10),
        None: pd.NaT,
    }[t_disp]
    return {
        "fecha_servicio": DIA,
        "viaje_id": viaje,
        "vehicle_id": f"bus-{viaje}",
        "linea": linea,
        "trayecto": "Ida",
        "feed_version": "F1",
        "fuera_de_vigencia": False,
        "trip_id": f"trip-{viaje}",
        "shape_id": "S1",
        "desfase_s": 5.0,
        "margen_s": 300.0,
        "coste_s": 7.0,
        "stop_id": f"P{seq:02d}",
        "stop_sequence": seq,
        "abscisa_parada_m": 400.0 * (seq - 1),
        "t_prog_s": 32400.0 + 120.0 * seq,
        "t_obs_s": 32400.0 + 120.0 * seq + retraso,
        "retraso_s": retraso,
        "t_obs_utc": T0 + pd.Timedelta(minutes=seq),
        "t_disp_utc": llega,
    }


def paradas_de(feed_version, shape_id, trip_id):
    """El horario del trazado: 20 paradas consecutivas, P01..P20."""
    seq = np.arange(1, 21)
    return pd.DataFrame(
        {
            "stop_id": [f"P{s:02d}" for s in seq],
            "stop_sequence": seq,
            "abscisa_parada_m": 400.0 * (seq - 1),
            "t_prog_s": 32400.0 + 120.0 * seq,
        }
    )


def _sabidos(filas):
    return separar(pd.DataFrame(filas), AHORA)[0]


def _un_viaje_con_la_cola_pendiente():
    """V: pasos 1-3 sabidos y el 4 (retraso 999) llega 10 s después del ahora."""
    return pd.DataFrame(
        [_paso("V", s, retraso=10.0 * s) for s in (1, 2, 3)]
        + [_paso("V", 4, retraso=999.0, t_disp="despues")]
    )


def test_un_paso_que_aun_no_se_sabe_queda_pendiente():
    pasos = _un_viaje_con_la_cola_pendiente()
    s, n = separar(pasos, AHORA)
    assert set(s["stop_sequence"]) == {1, 2, 3}
    assert set(n["stop_sequence"]) == {4}


def test_un_paso_sin_t_disp_no_se_sabe():
    pasos = pd.DataFrame([_paso("V", 1), _paso("V", 2, t_disp=None)])
    s, n = separar(pasos, AHORA)
    assert list(s["stop_sequence"]) == [1]
    assert list(n["stop_sequence"]) == [2]


def test_las_pendientes_son_las_paradas_que_quedan_con_el_viaje_copiado():
    s = _sabidos([_paso("V", q) for q in (1, 2, 4)])
    p = pendientes(s, paradas_de)
    assert list(p["stop_sequence"]) == list(range(5, 21))  # solo tras la última sabida
    assert (p["t_obs_utc"] == features.FUTURO).all()
    assert (p["t_disp_utc"] == features.FUTURO).all()
    assert p["retraso_s"].isna().all() and p["t_obs_s"].isna().all()
    for col in ("viaje_id", "vehicle_id", "linea", "trip_id", "feed_version"):
        assert p[col].nunique() == 1 and p[col].iloc[0] == s[col].iloc[0]
    assert p["t_prog_s"].iloc[0] == 32400.0 + 120.0 * 5  # el del horario


def test_la_fila_del_ciclo_no_ve_el_paso_que_no_se_sabe():
    """El 999 del paso 4 (llega después del ahora) no entra en ninguna fila.

    Con horizonte 2 la fila del paso 2 es la que tiene por objetivo el paso 4: si
    se filtrara, su objetivo valdría 999. La del paso 3, el último sabido, no ve
    el 999 en ninguna variable."""
    s, _ = separar(_un_viaje_con_la_cola_pendiente(), AHORA)
    t = tabla(pd.DataFrame(), s, pendientes(s, paradas_de), 2, CFG)
    v = t[t["viaje_id"] == "V"].set_index("stop_sequence")
    assert np.isnan(v.loc[2, OBJ])  # su objetivo es el paso 4, aún no sabido
    assert v.loc[3, "retraso_s"] == 30.0  # el del último sabido
    assert np.isnan(v.loc[3, OBJ])  # la parada objetivo (5) aún no ha pasado
    numericas = v.select_dtypes("number")
    assert not (numericas == 999.0).any().any()


def test_el_horizonte_se_cuenta_en_el_horario():
    """Último sabido: 4. Parada en 6. El 3 y el 5 nunca se observaron."""
    s = _sabidos([_paso("V", q) for q in (1, 2, 4)])
    c = candidatos(s, pendientes(s, paradas_de), "P06", [1, 2, 3, 5, 10])
    assert c.loc[0, "h"] == 2
    assert c.loc[0, "stop_sequence"] == 4


def test_a_una_distancia_sin_modelo_no_hay_prediccion():
    filas = [_paso("v2", q) for q in range(1, 11)]  # último 10: h = 2
    filas += [_paso("v4", q) for q in range(1, 9)]  # último 8: h = 4
    filas += [_paso("v11", 1)]  # último 1: h = 11
    s = _sabidos(filas)
    c = candidatos(s, pendientes(s, paradas_de), "P12", [1, 2, 3, 5, 10])
    c = c.set_index("viaje_id")
    assert c.loc["v2", "con_modelo"]
    assert not c.loc["v4", "con_modelo"]
    assert c.loc["v4", "h"] == 4
    assert "v11" not in set(c.index)
    assert list(c.columns) == [
        "fecha_servicio",
        "linea",
        "stop_sequence",
        "h",
        "retraso_s",
        "t_disp_utc",
        "con_modelo",
    ]


def test_una_parada_sin_buses_en_camino_da_tabla_vacia():
    s = _sabidos([_paso("V", q) for q in (1, 2, 3)])
    p = pendientes(s, paradas_de)
    assert candidatos(s, p, "parada_sin_nadie", [1, 2]).empty
    assert candidatos(s.iloc[0:0], p.iloc[0:0], "P05", [1, 2]).empty
    assert candidatos(s, p, "P01", [1, 2]).empty  # ya la pasó


def test_un_viaje_sin_pasos_sabidos_no_entra():
    filas = [_paso("V", q) for q in (1, 2)]
    filas += [_paso("W", q, t_disp="despues") for q in (1, 2)]
    s, n = separar(pd.DataFrame(filas), AHORA)
    p = pendientes(s, paradas_de)
    assert set(p["viaje_id"]) == {"V"}
    assert set(candidatos(s, p, "P04", [1, 2, 3]).viaje_id) == {"V"}
    assert set(n["viaje_id"]) == {"W"}


def test_si_la_parada_se_repite_cuenta_la_mas_cercana():
    """Una ruta circular pasa dos veces por la misma parada."""

    def circular(*args):
        h = paradas_de(*args)
        h.loc[h["stop_sequence"] == 9, "stop_id"] = "P03"
        return h

    s = _sabidos([_paso("V", 1)])
    c = candidatos(s, pendientes(s, circular), "P03", [1, 2, 3, 10])
    assert list(c["h"]) == [2]  # la del 3, no la del 9


def _pred(llega_tarde=True, regla=False, seq=5, p=0.7):
    return Prediccion(
        probabilidad=p,
        umbral=0.5,
        llega_tarde=llega_tarde,
        regla_llega_tarde=regla,
        h=2,
        t_utc=AHORA,
        stop_sequence=seq,
    )


def _pasos_sabidos(*filas):
    """(viaje, stop_id, stop_sequence, retraso_s) como pasos ya sabidos."""
    return pd.DataFrame(
        [
            {
                "fecha_servicio": DIA,
                "viaje_id": v,
                "stop_id": s,
                "stop_sequence": q,
                "retraso_s": r,
            }
            for v, s, q, r in filas
        ]
    )


K = (DIA, "V")
K2 = (DIA, "W")


def test_la_primera_prediccion_queda_congelada():
    m = Marcador()
    p1, p2 = _pred(p=0.7), _pred(p=0.2)
    assert m.congelar("S", K, p1) == p1
    assert m.congelar("S", K, p2) == p1
    assert m.entradas("S")[K]["congelada"] == p1


def test_se_verifica_con_el_paso_sabido_en_la_parada():
    m = Marcador()
    m.congelar("S", K, _pred(llega_tarde=True, regla=False))
    m.verificar("S", _pasos_sabidos(("V", "S", 5, 310.0)), 300)
    r = m.entradas("S")[K]["resultado"]
    assert r["llego_tarde"] is True and r["retraso_real_s"] == 310
    assert r["acierta_modelo"] is True and r["acierta_regla"] is False
    assert type(r["retraso_real_s"]) is float


def test_un_paso_aun_no_sabido_no_verifica():
    m = Marcador()
    m.congelar("S", K, _pred())
    m.verificar("S", _pasos_sabidos(("V", "OTRA", 5, 999.0), ("W", "S", 5, 999.0)), 300)
    assert m.entradas("S")[K]["resultado"] is None
    assert m.resumen("S")["verificados"] == 0


def test_un_paso_de_la_misma_parada_en_otra_visita_no_verifica():
    """Ruta circular: el mismo stop_id con menor stop_sequence ya es sabido."""
    m = Marcador()
    m.congelar("S", K, _pred(seq=9))
    m.verificar("S", _pasos_sabidos(("V", "S", 2, 400.0)), 300)
    assert m.entradas("S")[K]["resultado"] is None
    m.verificar("S", _pasos_sabidos(("V", "S", 2, 400.0), ("V", "S", 9, 20.0)), 300)
    assert m.entradas("S")[K]["resultado"]["retraso_real_s"] == 20.0


def test_el_marcador_cuenta_las_discrepancias():
    m = Marcador()
    m.congelar("S", K, _pred(llega_tarde=True, regla=False))
    m.congelar("S", K2, _pred(llega_tarde=False, regla=False))
    m.congelar("S", (DIA, "X"), _pred())  # sin verificar: no cuenta
    m.verificar("S", _pasos_sabidos(("V", "S", 5, 310.0), ("W", "S", 5, 10.0)), 300)
    assert m.resumen("S") == {
        "verificados": 2,
        "aciertos_modelo": 2,
        "aciertos_regla": 1,
        "discrepan": 1,
    }


def test_cambiar_de_parada_no_borra_lo_congelado():
    m = Marcador()
    p1, p3 = _pred(p=0.7), _pred(p=0.1)
    m.congelar("S", K, p1)
    m.congelar("T", K2, p3)
    assert m.entradas("S")[K]["congelada"] == p1
    assert m.entradas("T")[K2]["congelada"] == p3
    assert m.resumen("T")["verificados"] == 0
