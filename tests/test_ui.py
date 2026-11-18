"""Ayudantes puros de la página de la demo: sin red, sin datos, sin API."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pandas as pd

from project.ui import app
from project.ui.app import _gris, fila_tabla

CONGELADA = {
    "probabilidad": 0.4,
    "umbral": 0.3,
    "llega_tarde": True,
    "regla_llega_tarde": False,
    "h": 5,
    "t_utc": "2026-11-10T10:00:00+00:00",
    "stop_sequence": 1,
}


def _fila(**cambios) -> dict:
    base = {
        "linea": "92",
        "viaje_id": "a",
        "paradas": 4,
        "retraso_actual_s": 200.0,
        "edad_s": 45.0,
        "probabilidad": 0.12,
        "umbral": 0.3,
        "llega_tarde": False,
        "regla_llega_tarde": False,
        "congelada": None,
        "resultado": None,
    }
    return base | cambios


def _es_gris(fila: dict) -> bool:
    estilos = _gris(pd.Series(fila_tabla(fila)))
    return all(e == "color: gray" for e in estilos)


def test_fila_con_modelo_enseña_p_y_no_es_gris():
    t = fila_tabla(_fila())
    assert t["Modelo P(>5 min)"] == "12% · a tiempo"
    assert t["Regla simple"] == "a tiempo"
    assert t["Resultado"] == "⏳"
    assert not _es_gris(_fila())


def test_fila_sin_modelo_ni_congelada_sale_en_gris():
    f = _fila(probabilidad=None, umbral=None, llega_tarde=None)
    assert fila_tabla(f)["Modelo P(>5 min)"] == "sin modelo"
    assert _es_gris(f)


def test_sin_modelo_ahora_pero_congelada_enseña_lo_predicho_y_no_es_gris():
    f = _fila(probabilidad=None, umbral=None, llega_tarde=None, congelada=CONGELADA)
    modelo = fila_tabla(f)["Modelo P(>5 min)"]
    assert "40%" in modelo and "tarde" in modelo
    assert not _es_gris(f)


def test_congelada_distinta_de_la_actual_enseña_las_dos():
    f = _fila(congelada=CONGELADA)
    assert (
        fila_tabla(f)["Modelo P(>5 min)"] == "12% · a tiempo (congelada: 40% · tarde)"
    )


def test_retraso_actual_nulo_sale_sin_dato():
    f = fila_tabla(_fila(retraso_actual_s=None, regla_llega_tarde=None))
    assert f["Va ahora"] == "sin dato"
    assert f["Regla simple"] == "sin dato"  # no «a tiempo»: no hay dato


def test_la_regla_es_la_de_la_congelada_que_puntua_el_marcador():
    # Ahora el bus va tarde (regla True) pero se congeló a tiempo (regla False).
    f = _fila(regla_llega_tarde=True, congelada=CONGELADA)
    assert fila_tabla(f)["Regla simple"] == "a tiempo (ahora: tarde)"
    # Si coinciden se enseña una sola.
    f = _fila(regla_llega_tarde=False, congelada=CONGELADA)
    assert fila_tabla(f)["Regla simple"] == "a tiempo"
    # Sin retraso ahora, la congelada sigue siendo la que puntúa.
    f = _fila(regla_llega_tarde=None, congelada=CONGELADA)
    assert fila_tabla(f)["Regla simple"] == "a tiempo"


def _error_al_pedir(monkeypatch, excepcion) -> str:
    def get(*a, **k):
        raise excepcion

    mensajes = []
    monkeypatch.setattr(app.requests, "get", get)
    monkeypatch.setattr(app.st, "error", mensajes.append)
    assert app.pedir("/vivo/parada/1", 1) is None
    (mensaje,) = mensajes
    return mensaje


def test_un_timeout_dice_que_la_api_esta_ocupada(monkeypatch):
    mensaje = _error_al_pedir(monkeypatch, app.requests.Timeout())
    assert "ocupada" in mensaje and "no disponible" not in mensaje


def test_sin_conexion_dice_que_la_api_no_esta_disponible(monkeypatch):
    mensaje = _error_al_pedir(monkeypatch, app.requests.ConnectionError())
    assert "no disponible" in mensaje


def _pintar(monkeypatch, estado) -> dict[str, list[str]]:
    """Pinta una parada con `st` y la API falseados y devuelve lo que se escribió."""
    escrito = {"warning": [], "caption": []}
    monkeypatch.setattr(app, "pedir", lambda ruta, timeout: estado)
    monkeypatch.setattr(app.st, "spinner", lambda texto: nullcontext())
    for nombre in ("warning", "caption", "dataframe", "info", "markdown"):
        monkeypatch.setattr(
            app.st,
            nombre,
            lambda t=None, *a, _n=nombre, **k: escrito.get(_n, []).append(t),
        )
    app.pintar_parada("1")
    return escrito


def _estado(**cambios) -> dict:
    base = {
        "stop_id": "1",
        "nombre": "Colón",
        "ahora_utc": "2026-11-10T10:00:05+00:00",
        "datos_hasta_utc": None,
        "error": None,
        "filas": [],
        "marcador": {
            "verificados": 0,
            "aciertos_modelo": 0,
            "aciertos_regla": 0,
            "discrepan": 0,
        },
    }
    return base | cambios


def test_el_error_enseña_la_hora_local_del_ultimo_sondeo_bueno(monkeypatch):
    # 08:58 UTC del 10/11 son las 09:58 en Valencia (CET).
    estado = _estado(
        error={"mensaje": "Sin datos nuevos de la EMT desde 09:58", "desde_utc": "x"},
        datos_hasta_utc="2026-11-10T08:58:00+00:00",
    )
    (aviso,) = _pintar(monkeypatch, estado)["warning"]
    assert "Sin datos nuevos" in aviso and "último sondeo bueno a las 09:58" in aviso


def test_la_edad_del_dato_se_mide_contra_el_reloj_no_contra_el_ciclo(monkeypatch):
    """Con la respuesta en caché `ahora_utc` es del ciclo, hasta 40 s atrás."""
    hace_100_s = datetime.now(timezone.utc) - timedelta(seconds=100)
    estado = _estado(
        datos_hasta_utc=hace_100_s.isoformat(),
        ahora_utc=(hace_100_s + timedelta(seconds=5)).isoformat(),
    )
    (texto,) = _pintar(monkeypatch, estado)["caption"][:1]
    assert 99 <= float(texto.split()[3]) <= 105  # «Dato de hace N s»
