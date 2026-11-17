"""`medir_marcador_vivo.clasificar` distingue el paso propio del de otro bus.

Un instrumento que diera «correcta» a todo validaría el marcador por accidente
(trampa 004): cada clase sale de un caso construido para ella.
"""

import pandas as pd

from project.analysis.medir_marcador_vivo import ancla, clasificar, paso_verificador

T0 = pd.Timestamp("2026-10-01T06:00Z")
F = pd.Timestamp("2026-10-01")
STOP = "P9"


def _paso(viaje, seq, t_min, retraso=60.0, stop="X", linea="7", trip="T1"):
    t = T0 + pd.Timedelta(minutes=t_min)
    return {
        "fecha_servicio": F,
        "viaje_id": viaje,
        "linea": linea,
        "trip_id": trip,
        "stop_id": stop,
        "stop_sequence": seq,
        "t_obs_utc": t,
        "t_disp_utc": t + pd.Timedelta(seconds=80),
        "retraso_s": retraso,
    }


# El día completo: el bus físico del viaje A acaba llamándose «A2» (otro
# vehicle_id) y pasa por P9 en la parada 5; el B, otro bus, pasa antes.
FINAL = pd.DataFrame(
    [
        _paso("A2", 3, 10),
        _paso("A2", 5, 14, retraso=400.0, stop=STOP),
        _paso("B", 3, 8, linea="7"),
        _paso("B", 5, 12, retraso=100.0, stop=STOP),
        _paso("C", 3, 50),
        _paso("C", 5, 54, retraso=10.0, stop=STOP),
    ]
)
LIMITE = T0 + pd.Timedelta(minutes=30)


def _congelada(t_obs_min, verificado=None, seq=3, trip="T1"):
    return {
        "ancla": {
            "linea": "7",
            "stop_sequence": seq,
            "t_obs_utc": T0 + pd.Timedelta(minutes=t_obs_min),
            "trip_id": trip,
        },
        "objetivo_seq": 5,
        "t_congelada": "x",
        "verificado": verificado,
    }


def _ver(t_min, retraso):
    return {"t_obs_utc": T0 + pd.Timedelta(minutes=t_min), "retraso_s": retraso}


def _clases(congeladas):
    return {
        f["viaje_id"]: f["clase"] for f in clasificar(congeladas, FINAL, STOP, LIMITE)
    }


def test_cada_clase_sale_de_su_caso():
    c = _clases(
        {
            (F, "ok"): _congelada(10, _ver(14, 400.0)),
            (F, "huerfana"): _congelada(10),
            (F, "cruzada"): _congelada(10, _ver(12, 100.0)),  # el paso del B
            (F, "otro_retraso"): _congelada(10, _ver(14, 380.0)),
            (F, "perdida"): _congelada(11),  # ningún paso con ese t_obs
            (F, "tarde"): _congelada(50),  # su verdad llega tras el límite
        }
    )
    assert c == {
        "ok": "correcta",
        "huerfana": "huerfana",
        "cruzada": "cruzada",
        "otro_retraso": "otro_retraso",
        "perdida": "ancla_perdida",
        "tarde": "fuera_de_ventana",
    }


def test_el_cambio_de_viaje_id_y_de_trip_id_se_cuenta():
    (f,) = clasificar(
        {(F, "A"): _congelada(10, _ver(14, 400.0), trip="T0")}, FINAL, STOP, LIMITE
    )
    assert f["clase"] == "correcta"
    assert f["viaje_id_final"] == "A2" and f["trip_id_cambia"] is True


def test_un_bus_que_no_llega_a_la_parada_no_cuenta_como_huerfana():
    final = FINAL[~((FINAL["viaje_id"] == "A2") & (FINAL["stop_id"] == STOP))]
    (f,) = clasificar({(F, "A"): _congelada(10)}, final, STOP, LIMITE)
    assert f["clase"] == "no_llega"


def test_el_verificador_casa_igual_que_el_marcador():
    """`paso_verificador` replica `Marcador.verificar`: si este cambiara su
    casación, el medidor seguiría diciendo «0 de N» midiendo otra cosa."""
    from project.services.vivo import Marcador, Prediccion

    filas = [
        _paso("V", 2, 1, retraso=400.0, stop=STOP),  # ruta circular: otra visita
        _paso("V", 9, 20, retraso=20.0, stop=STOP),
        _paso("W", 9, 20, retraso=float("nan"), stop=STOP),  # sabido, sin etiquetar
        _paso("X", 9, 20, retraso=50.0, stop="OTRA"),
    ]
    sab = pd.DataFrame(filas)
    m = Marcador()
    for viaje in ("V", "W", "X"):
        m.congelar(STOP, (F, viaje), Prediccion(0.5, 0.5, False, False, 7, T0, 9))
    m.verificar(STOP, sab, 300)
    for clave, e in m.entradas(STOP).items():
        ver = paso_verificador(sab, clave, 9, STOP)
        esperado = e["resultado"] and e["resultado"]["retraso_real_s"]
        assert (ver and ver["retraso_s"]) == esperado, clave
    assert (
        paso_verificador(sab, (F, "V"), 9, STOP)["t_obs_utc"] == filas[1]["t_obs_utc"]
    )
    assert ancla(sab, (F, "V"))["stop_sequence"] == 9
