"""El núcleo del ciclo en vivo contra pasos sintéticos hechos a mano.

Lo que se prueba es la frontera del «ahora»: un paso cuyo retraso aún no había
llegado (`t_disp_utc > ahora`) no existe para el ciclo (ADR-022, trampa 017), y
la parada del tutor se busca en el horario, no entre los pasos observados.
"""

from __future__ import annotations

import copy
import threading
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from test_etiquetado import IDA, PUNTA, Bus, feed_a, flota, horario_a  # noqa: F401

from project import etiquetado, features
from project.config import RAIZ, settings
from project.ingest import sources
from project.gtfs import Horario
from project.prepare import cargar_parametros, etiquetar_dia
from project.services.vivo import (
    DemoNoDisponible,
    Marcador,
    ParadaDesconocida,
    Prediccion,
    Vivo,
    candidatos,
    con_reloj_de_todas,
    ficheros_del_dia,
    pendientes,
    separar,
    tabla,
)

T0 = pd.Timestamp("2026-11-10 09:00", tz="UTC")
AHORA = T0 + pd.Timedelta(minutes=30)
# El minuto del último paso sabido en cada test de `candidatos`: ni un segundo viejo.
MIN1, MIN2, MIN3, MIN4, MIN10 = (pd.Timedelta(minutes=m) for m in (1, 2, 3, 4, 10))
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


def test_las_pendientes_se_concatenan_con_los_pasos_sin_perder_el_tipo():
    """Con `FUTURO` en segundos, historial + sabidos + pendientes dejaba los
    instantes en `object` y `construir` fallaba en el primer `.dt`."""
    s = _sabidos([_paso("V", q) for q in (1, 2, 3)])
    p = pendientes(s, paradas_de)
    todo = pd.concat([s, s, p], ignore_index=True)
    for col in ("t_obs_utc", "t_disp_utc"):
        assert p[col].dtype == s[col].dtype == todo[col].dtype


def test_el_horizonte_se_cuenta_en_el_horario():
    """Último sabido: 4. Parada en 6. El 3 y el 5 nunca se observaron."""
    s = _sabidos([_paso("V", q) for q in (1, 2, 4)])
    c = candidatos(s, pendientes(s, paradas_de), "P06", [1, 2, 3, 5, 10], T0 + MIN4)
    assert c.loc[0, "h"] == 2
    assert c.loc[0, "stop_sequence"] == 4


def test_a_una_distancia_sin_modelo_no_hay_prediccion():
    filas = [_paso("v2", q) for q in range(1, 11)]  # último 10: h = 2
    filas += [_paso("v4", q) for q in range(1, 9)]  # último 8: h = 4
    filas += [_paso("v11", 1)]  # último 1: h = 11
    s = _sabidos(filas)
    c = candidatos(s, pendientes(s, paradas_de), "P12", [1, 2, 3, 5, 10], T0 + MIN10)
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
    assert candidatos(s, p, "parada_sin_nadie", [1, 2], T0 + MIN3).empty
    assert candidatos(s.iloc[0:0], p.iloc[0:0], "P05", [1, 2], T0 + MIN3).empty
    assert candidatos(s, p, "P01", [1, 2], T0 + MIN3).empty  # ya la pasó


def test_un_viaje_sin_pasos_sabidos_no_entra():
    filas = [_paso("V", q) for q in (1, 2)]
    filas += [_paso("W", q, t_disp="despues") for q in (1, 2)]
    s, n = separar(pd.DataFrame(filas), AHORA)
    p = pendientes(s, paradas_de)
    assert set(p["viaje_id"]) == {"V"}
    assert set(candidatos(s, p, "P04", [1, 2, 3], T0 + MIN2).viaje_id) == {"V"}
    assert set(n["viaje_id"]) == {"W"}


def test_el_bus_que_por_horario_ya_debia_haber_llegado_no_va_en_camino():
    """Último sabido: el 3, a T0+3 min. El horario tarda 240 s hasta P05. Con 239 s
    desde el paso aún le quedan 1 s; con 241, ya debía estar y su paso siguiente no
    llegó nunca: fuera. Justo en 240 s tampoco (`> 0`)."""
    p = _pasos_del_viaje(3)

    def en_camino(segundos):
        ahora = T0 + MIN3 + pd.Timedelta(seconds=segundos)
        s = separar(p, ahora)[0]
        return candidatos(s, pendientes(s, paradas_de), "P05", [2], ahora)

    dentro = en_camino(239)
    assert list(dentro["viaje_id"]) == ["V"] and dentro.loc[0, "h"] == 2
    assert en_camino(240).empty
    assert en_camino(241).empty


def test_el_retraso_del_candidato_es_el_del_ultimo_paso_aunque_sea_nulo():
    p = _pasos_del_viaje(3, retraso=lambda s: np.nan if s == 3 else 10.0)
    ahora = T0 + MIN3
    s = separar(p, ahora)[0]
    c = candidatos(s, pendientes(s, paradas_de), "P05", [2], ahora)
    assert c["retraso_s"].isna().all()


def test_si_la_parada_se_repite_cuenta_la_mas_cercana():
    """Una ruta circular pasa dos veces por la misma parada."""

    def circular(*args):
        h = paradas_de(*args)
        h.loc[h["stop_sequence"] == 9, "stop_id"] = "P03"
        return h

    s = _sabidos([_paso("V", 1)])
    c = candidatos(s, pendientes(s, circular), "P03", [1, 2, 3, 10], T0 + MIN1)
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


def test_un_paso_sabido_sin_retraso_no_verifica():
    """El paso es sabido pero no se pudo etiquetar: ni NaN ni «no llegó tarde»."""
    m = Marcador()
    m.congelar("S", K, _pred(llega_tarde=True, regla=False))
    antes = m.resumen("S")
    m.verificar("S", _pasos_sabidos(("V", "S", 5, float("nan"))), 300)
    assert m.entradas("S")[K]["resultado"] is None
    assert m.resumen("S") == antes
    m.verificar("S", _pasos_sabidos(("V", "S", 5, 310.0)), 300)
    assert m.entradas("S")[K]["resultado"]["retraso_real_s"] == 310.0


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


# --------------------------------------------------------------------------- #
# El ciclo completo: `Vivo`
# --------------------------------------------------------------------------- #
PARAMS_TFM = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
COLUMNAS_FALSAS = ["linea", "retraso_s", "retraso_lag1_s", "hora"]


class ServicioFalso:
    """Un clasificador por horizonte que contesta lo mismo y anota qué vector vio."""

    def __init__(self, horizontes=(2,), p=0.8):
        self.horizontes, self.p, self.vistos = list(horizontes), p, []

    def modelos(self):
        return [
            {
                "modelo": "clasificador",
                "horizonte_paradas": h,
                "columnas": COLUMNAS_FALSAS,
            }
            for h in self.horizontes
        ]

    def mas_de_5min(self, variables, horizonte):
        self.vistos.append((horizonte, variables))
        return {"probabilidad": self.p, "umbral": 0.5, "llega_tarde": self.p >= 0.5}


def _horario(vigencia=(date(2026, 1, 1), date(2026, 12, 31))):
    """Un horario a mano: la línea 7 para en P01..P20 todos los días."""
    dias = "monday tuesday wednesday thursday friday saturday sunday".split()
    cal = pd.DataFrame(
        [
            {
                "service_id": "S",
                "start_date": f"{vigencia[0]:%Y%m%d}",
                "end_date": f"{vigencia[1]:%Y%m%d}",
                **dict.fromkeys(dias, "1"),
            }
        ]
    )
    return Horario(
        ruta=Path("falso.zip"),
        version="F1",
        vigencia=vigencia,
        calendario=vigencia,
        viajes=pd.DataFrame(
            {
                "trip_id": ["T"],
                "route_id": ["R"],
                "service_id": ["S"],
                "shape_id": ["S1"],
                "linea": ["7"],
            }
        ),
        paradas_de_viaje=pd.DataFrame(
            {
                "trip_id": "T",
                "stop_sequence": np.arange(1, 21),
                "stop_id": [f"P{s:02d}" for s in range(1, 21)],
                "t_prog_s": 32400.0 + 120.0 * np.arange(1, 21),
            }
        ),
        paradas=pd.DataFrame(
            {"lat": 39.0, "lon": -0.4, "nombre": "Nombre"},
            index=pd.Index([f"P{s:02d}" for s in range(1, 21)], name="stop_id"),
        ),
        calendar=cal,
        calendar_dates=pd.DataFrame(columns=["service_id", "date", "exception_type"]),
        trazados={},
    )


def _vivo(horario=None, servicio=None):
    return Vivo(
        servicio or ServicioFalso(),
        [horario or _horario()],
        pd.DataFrame(),
        PARAMS_TFM,
        cargar_parametros(),
    )


def test_sin_datos_la_demo_no_tumba_el_arranque(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_root", tmp_path / "vacio")
    monkeypatch.setattr(settings, "gtfs_dir", tmp_path / "sin_gtfs")
    v = Vivo.desde_disco(ServicioFalso())
    assert v.problema
    with pytest.raises(DemoNoDisponible):
        v.parada("123")
    with pytest.raises(DemoNoDisponible):
        v.paradas()


def test_sin_modelos_la_demo_no_tumba_el_arranque(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_root", tmp_path / "vacio")
    monkeypatch.setattr(settings, "gtfs_dir", tmp_path / "sin_gtfs")
    v = Vivo.desde_disco(ServicioFalso(horizontes=()))
    assert "modelo" in v.problema


def test_sin_horario_vigente_hoy_se_dice():
    v = _vivo(_horario(vigencia=(date(2020, 1, 1), date(2020, 12, 31))))
    with pytest.raises(DemoNoDisponible, match="horario"):
        v.parada("P05")
    with pytest.raises(DemoNoDisponible, match="horario"):
        v.paradas()


def test_de_madrugada_se_leen_dos_fechas(tmp_path):
    """02:30 locales del 11/11: el día de servicio es el 10/11."""
    for d in ("2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"):
        f = tmp_path / f"date={d}" / "payloads.ndjson.gz"
        f.parent.mkdir()
        f.touch()
    fs = ficheros_del_dia(tmp_path, pd.Timestamp("2026-11-11T01:30Z"))
    assert {f.parent.name for f in fs} == {"date=2026-11-10", "date=2026-11-11"}
    # A mediodía, la ventana de hoy solo ha entrado en una fecha UTC.
    fs = ficheros_del_dia(tmp_path, pd.Timestamp("2026-11-10T10:00Z"))
    assert {f.parent.name for f in fs} == {"date=2026-11-10"}


def test_una_parada_que_no_existe_es_desconocida():
    with pytest.raises(ParadaDesconocida):
        _vivo().parada("no_existe", pd.Timestamp("2026-11-10T10:00Z"))


def test_las_paradas_no_esperan_al_ciclo_en_curso():
    """Un ciclo tarda hasta 40 s con el cerrojo cogido; la lista de paradas no ha
    de quedarse esperándolo (la UI daría «API no disponible»)."""
    v = _vivo()
    resultado = []
    v._cerrojo.acquire()  # un ciclo de otra parada, en marcha
    try:
        hilo = threading.Thread(
            target=lambda: resultado.append(v.paradas()), daemon=True
        )
        hilo.start()
        hilo.join(timeout=10)
        assert not hilo.is_alive(), "paradas() espera al cerrojo del ciclo"
    finally:
        v._cerrojo.release()
    assert len(resultado[0]) == 20


def test_las_paradas_son_las_del_horario_con_sus_lineas():
    p = _vivo().paradas()
    assert p[0] == {"stop_id": "P01", "nombre": "Nombre", "lineas": ["7"]}
    assert len(p) == 20


# --- el reloj de todas las líneas (trampa 022) -----------------------------


def _frame_a_mano():
    """Tres sondeos. En cada uno manda una línea distinta; el 3 no trae la A."""
    ts = pd.Timestamp("2026-10-01T10:00:00Z")

    def f(snap, linea, seg, trayecto="Ida"):
        return {
            "snapshot_id": snap,
            "linea": linea,
            "trayecto": trayecto,
            "lat": 39.4,
            "lon": -0.4,
            "ts_utc": ts + pd.Timedelta(seconds=seg + 30 * snap),
            "gid": 0,  # una columna que el recorte no necesita, pero no debe romper
        }

    return pd.DataFrame(
        [
            f(1, "A", 5),
            f(1, "B", 9),
            f(1, "C", 20, trayecto=None),  # sin trayecto: no cuenta para el reloj
            f(2, "A", 35),
            f(2, "B", 31),
            f(3, "B", 7),
        ]
    )


def _reloj(df):
    return df[df["trayecto"].notna()].groupby("snapshot_id")["ts_utc"].max()


def test_el_recorte_conserva_el_reloj_y_los_sondeos_de_todas_las_lineas():
    frame = _frame_a_mano()
    recorte = con_reloj_de_todas(frame, ["A"])
    assert _reloj(recorte).equals(_reloj(frame))
    assert set(recorte["snapshot_id"]) == set(frame["snapshot_id"])
    assert len(recorte[recorte["linea"] == "A"]) == 2  # las suyas, enteras
    assert set(recorte["linea"]) == {"A", "__reloj__"}


def test_la_fila_fantasma_no_sale_en_los_pasos(horario_a):  # noqa: F811
    """Recortada a la línea 1 y con el reloj de todas, la etiqueta es la de todas."""
    buses = [
        Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 20, 4.0),
        Bus("1", "Oeste - Este", IDA, 7 * 3600 + 1200 - 40, 4.0),
        Bus("3", "Oeste - Este", PUNTA, 7 * 3600 + 240, 5.0),
    ]
    frame = flota(*buses)
    p = etiquetado.Parametros()
    todas = etiquetar_dia(frame, [horario_a], p)
    cortada = etiquetar_dia(con_reloj_de_todas(frame, ["1"]), [horario_a], p)
    assert set(cortada.pasos["linea"]) == {"1"}
    clave = ["trip_id", "stop_sequence", "retraso_s"]
    a = todas.pasos[todas.pasos["linea"] == "1"][clave]
    b = cortada.pasos[clave]
    assert len(a) > 20
    assert (
        a.sort_values(clave)
        .reset_index(drop=True)
        .equals(b.sort_values(clave).reset_index(drop=True))
    )


# --- congelar y verificar con las mismas claves ------------------------------


def _pasos_del_viaje(hasta, retraso=lambda s: 100.0 * s, viaje="V"):
    """Pasos 1..hasta de un viaje, sabido cada uno `s` minutos tras T0."""
    filas = []
    for s in range(1, hasta + 1):
        f = _paso(viaje, s, retraso=retraso(s))
        f["t_disp_utc"] = T0 + pd.Timedelta(minutes=s)
        filas.append(f)
    return pd.DataFrame(filas)


def _vivo_con_paradas(servicio=None):
    v = _vivo(servicio=servicio)
    v.paradas_de = paradas_de
    return v


def _ciclo(v, stop, ahora, pasos):
    return v._resultado(stop, ahora, pasos, pd.DataFrame())


def test_lo_congelado_se_verifica_cuando_llega_el_paso_sabido():
    """Dos ciclos: el primero congela (último sabido el 3, parada P05, h = 2); el
    segundo ve el paso 5 y lo califica. Si la clave de `congelar` y la de
    `verificar` no son la misma, no se califica nunca y no hay error."""
    v = _vivo_con_paradas(ServicioFalso(horizontes=(2,), p=0.8))
    pasos = _pasos_del_viaje(5)
    t1 = T0 + pd.Timedelta(minutes=3, seconds=30)
    r1 = _ciclo(v, "P05", t1, pasos)
    (fila,) = r1["filas"]
    assert fila["viaje_id"] == "V" and fila["paradas"] == 2
    assert fila["probabilidad"] == 0.8 and fila["llega_tarde"] is True
    assert fila["retraso_actual_s"] == 300.0
    assert fila["regla_llega_tarde"] is False  # 300 no supera 300
    assert fila["congelada"]["probabilidad"] == 0.8 and fila["resultado"] is None
    assert r1["marcador"]["verificados"] == 0

    r2 = _ciclo(v, "P05", T0 + pd.Timedelta(minutes=6), pasos)
    (fila,) = r2["filas"]  # ya no está en camino, pero sigue a la vista
    assert fila["resultado"]["retraso_real_s"] == 500.0
    assert fila["resultado"]["llego_tarde"] is True
    assert fila["congelada"]["t_utc"] == t1.isoformat()
    assert r2["marcador"] == {
        "verificados": 1,
        "aciertos_modelo": 1,
        "aciertos_regla": 0,
        "discrepan": 1,
    }


def test_el_vector_son_las_columnas_del_modelo_en_tipos_nativos():
    servicio = ServicioFalso(horizontes=(2,))
    v = _vivo_con_paradas(servicio)
    _ciclo(v, "P05", T0 + pd.Timedelta(minutes=3, seconds=30), _pasos_del_viaje(3))
    ((h, vector),) = servicio.vistos
    assert h == 2 and list(vector) == COLUMNAS_FALSAS
    assert vector["linea"] == "1" and type(vector["linea"]) is str
    assert vector["retraso_s"] == 300.0 and type(vector["retraso_s"]) is float
    assert vector["retraso_lag1_s"] == 200.0
    assert type(vector["hora"]) is float


def test_un_ultimo_paso_sin_retraso_sale_sin_modelo_y_no_tumba_la_parada():
    servicio = ServicioFalso(horizontes=(2,))
    v = _vivo_con_paradas(servicio)
    pasos = _pasos_del_viaje(3, retraso=lambda s: np.nan if s == 3 else 10.0)
    r = _ciclo(v, "P05", T0 + pd.Timedelta(minutes=3, seconds=30), pasos)
    (fila,) = r["filas"]
    assert fila["probabilidad"] is None and fila["llega_tarde"] is None
    assert fila["congelada"] is None and fila["regla_llega_tarde"] is None
    assert servicio.vistos == []


def test_una_parada_sin_buses_en_camino_no_es_un_error():
    vacios = _pasos_del_viaje(3).iloc[0:0]
    r = _ciclo(_vivo_con_paradas(), "P05", T0 + pd.Timedelta(minutes=3), vacios)
    assert r["filas"] == [] and r["error"] is None


def test_un_viaje_que_el_horario_no_conoce_se_salta():
    v = _vivo()
    v._por_version = {}  # la versión del viaje no está: KeyError dentro de `paradas_de`
    r = _ciclo(v, "P05", T0 + pd.Timedelta(minutes=3, seconds=30), _pasos_del_viaje(3))
    assert r["filas"] == []


# --- la fuga de futuro en lo que carga el ciclo ------------------------------


def test_el_historial_solo_trae_lo_que_ya_se_sabia():
    """Con `ahora` a las 04:30 del 01/10 (día de servicio 01/10) entran los días
    anteriores, de la misma versión y de las líneas de la parada, y de esos solo los
    pasos ya disponibles: un nocturno del 30/09 que se sabe a las 04:40 no."""
    ahora = pd.Timestamp("2026-10-01T02:30Z")
    dia = date(2026, 10, 1)

    def paso(nombre, dia_servicio, version="F1", linea="7", t_disp="02:00"):
        return {
            "paso": nombre,
            "fecha_servicio": pd.Timestamp(dia_servicio),
            "feed_version": version,
            "linea": linea,
            "t_disp_utc": pd.Timestamp(f"2026-10-01T{t_disp}Z"),
        }

    v = _vivo()
    v.historial = pd.DataFrame(
        [
            paso("anteayer", "2026-09-29"),
            paso("ayer", "2026-09-30"),
            paso("hoy", "2026-10-01"),
            paso("mañana", "2026-10-02"),
            paso("otra_version", "2026-09-30", version="F2"),
            paso("otra_linea", "2026-09-30", linea="9"),
            paso("llega_despues", "2026-09-30", t_disp="02:40"),
        ]
    )
    h = v._historial_de(_horario(), dia, ["7"], ahora)
    assert set(h["paso"]) == {"anteayer", "ayer"}


def _payload(base, k, ts_dato):
    """El payload real de la EMT como k-ésimo refresco, con el dato fechado en `ts_dato`."""
    p = copy.deepcopy(base)
    for f in p["features"]:
        f["attributes"]["gid"] += 1000 * k
        f["attributes"]["fecha"] = int(pd.Timestamp(ts_dato).timestamp() * 1000)
    return p


def test_el_crudo_posterior_a_ahora_no_entra_en_el_ciclo(tmp_path, monkeypatch, fix):
    """Tres sondeos que llegan a 10:00:00, 10:00:30 y 10:01:30. El tercero trae el
    dato fechado a 10:00:50: pasaría el filtro de `ts_utc <= ahora`: solo lo frena
    haber llegado después de `ahora` (10:01:00)."""
    monkeypatch.setattr(settings, "data_root", tmp_path)
    for k, (llega, dato) in enumerate(
        [
            ("2026-10-01T10:00:00Z", "2026-10-01T09:59:50Z"),
            ("2026-10-01T10:00:30Z", "2026-10-01T10:00:20Z"),
            ("2026-10-01T10:01:30Z", "2026-10-01T10:00:50Z"),
        ]
    ):
        sources.append_raw(
            tmp_path,
            "emt_buses",
            _payload(fix["emt_buses"], k, dato),
            pd.Timestamp(llega),
        )
    frame, llegadas, ultimo_ok, error = _vivo()._leer_hoy(
        pd.Timestamp("2026-10-01T10:01:00Z")
    )
    assert len(llegadas) == 2 and frame["snapshot_id"].nunique() == 2
    assert ultimo_ok == pd.Timestamp("2026-10-01T10:00:30Z")
    assert error is None


# --- el prefijo frente al día completo (ADR-022, trampa 017) ------------------


def test_un_paso_sabido_en_el_prefijo_lo_es_igual_con_el_dia_completo(horario_a):  # noqa: F811
    """El ciclo etiqueta un prefijo del día; el pipeline, el día entero. Todo paso
    que el ciclo da por sabido en `ahora` ha de tener, en el día completo, el mismo
    retraso y el mismo `t_obs_utc` y `t_disp_utc <= ahora`: con k1 la última
    posición fiable del viaje, k1+1 puede llegar y mover el paso y su `t_disp`."""
    frame = flota(Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 90, 4.0))
    latencia = pd.Timedelta(seconds=20)
    llegadas = frame.groupby("snapshot_id")["ts_utc"].max() + latencia
    v = Vivo(
        ServicioFalso(),
        [horario_a],
        pd.DataFrame(),
        PARAMS_TFM,
        etiquetado.Parametros(),
    )
    completo = v._etiquetar(
        frame, llegadas, ["1"], frame["ts_utc"].max() + pd.Timedelta(days=1)
    )
    assert completo["t_disp_utc"].notna().all() and len(completo) >= 11
    completo = completo.set_index("stop_sequence")
    cortes = sorted(frame["ts_utc"].unique())[8:-3]
    sabidos_en_algun_corte = 0
    for corte in cortes:
        ahora = pd.Timestamp(corte) + latencia
        prefijo = v._etiquetar(frame[frame["ts_utc"] <= corte], llegadas, ["1"], ahora)
        if prefijo.empty:
            continue
        sabidos = separar(prefijo, ahora)[0].set_index("stop_sequence")
        sabidos_en_algun_corte += len(sabidos)
        c = completo.loc[sabidos.index]
        assert (c["t_disp_utc"] <= ahora).all(), (
            f"corte {ahora}: sabido antes de tiempo"
        )
        assert np.allclose(c["retraso_s"], sabidos["retraso_s"], atol=1e-6)
        assert (c["t_obs_utc"] == sabidos["t_obs_utc"]).all()
    assert sabidos_en_algun_corte > 0
