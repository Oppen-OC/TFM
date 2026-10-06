"""El modelo y su evaluación: lo que no da la cara si se rompe.

Ninguno de estos fallos lanza nada. Un modelo que ve otras columnas que las de
`features.variables()`, o la línea con otro código en la prueba, predice
números plausibles. Una validación que mira días que no tocan sesga la parada
temprana. Un intervalo que remuestrea filas sale estrecho y declara mejoras que
no lo son (ADR-018). Todos se ven solo con verdad conocida.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from project import evaluate, features, gtfs, predict, train
from project.analysis import elegir_brazo

OBJ = "retraso_siguiente_parada_s"
CFG = {"lags_min": [1, 5], "incluir_flota": True, "ventanas_flota_min": [5]}
PARAMS = {
    "objective": "reg:squarederror",
    "eval_metric": "mae",
    "n_estimators": 80,
    "max_depth": 3,
    "learning_rate": 0.3,
    "early_stopping_rounds": 10,
    "n_jobs": 1,
    "random_state": 0,
    "dias_validacion": 2,
    "residuo": False,
}
NIVEL = {"A": 0.0, "B": 100.0, "C": 200.0, "D": 500.0}


def _tabla(dias=6, filas_por_dia=300, lineas=("A", "B", "C"), semilla=0):
    """Variables al azar; el objetivo es el nivel de la línea más la persistencia."""
    rng = np.random.default_rng(semilla)
    n = dias * filas_por_dia
    t = pd.DataFrame(
        {c: rng.normal(size=n) for c in train.columnas(CFG) if c != "linea"}
    )
    t["linea"] = rng.choice(lineas, n)
    t["fecha_servicio"] = pd.Timestamp("2026-09-01") + pd.to_timedelta(
        np.repeat(np.arange(dias), filas_por_dia), unit="D"
    )
    t["viaje_id"] = np.arange(n) // 10
    t[OBJ] = t["linea"].map(NIVEL) + t["retraso_s"]
    return t


def test_el_modelo_ve_exactamente_las_variables_de_features():
    """Las columnas salen de `features.variables()` con los params, no de una lista."""
    assert train.columnas(CFG) == features.variables((1, 5), (5,))
    sin_flota = {**CFG, "incluir_flota": False}
    assert train.columnas(sin_flota) == features.variables((1, 5), ())
    art = train.entrenar(_tabla(), train.columnas(CFG), OBJ, PARAMS)
    assert art["columnas"] == train.columnas(CFG)
    assert art["modelo"].get_booster().feature_names == art["columnas"]


def test_la_validacion_son_los_ultimos_dias_del_entrenamiento():
    t = _tabla(dias=6)
    ajuste, val = train.separar_validacion(t, 2)
    dias = sorted(t["fecha_servicio"].unique())
    assert set(val["fecha_servicio"]) == set(dias[-2:])
    assert ajuste["fecha_servicio"].max() < val["fecha_servicio"].min()
    assert len(ajuste) + len(val) == len(t)


def test_el_modelo_final_se_reajusta_con_los_dias_de_validacion():
    """La línea D solo circula en los dos últimos días: los de validación.

    Si el modelo guardado fuera el de la parada temprana, no la habría visto
    nunca y la predeciría como otra cualquiera.
    """
    t = _tabla(dias=6)
    ultimos = t["fecha_servicio"] >= t["fecha_servicio"].max() - pd.Timedelta(days=1)
    d = ultimos & (t["linea"] == "C")
    t.loc[d, "linea"] = "D"
    t.loc[d, OBJ] = NIVEL["D"] + t.loc[d, "retraso_s"]
    art = train.entrenar(t, train.columnas(CFG), OBJ, PARAMS)
    assert art["modelo"].n_estimators == art["n_arboles"]
    assert predict.predecir(art, t[d]).mean() > 400


def test_predict_reutiliza_las_categorias_guardadas_con_el_modelo():
    """Una tabla con la C y una línea que el entrenamiento no vio, la Z.

    XGBoost (≥ 3.1) guarda las categorías y recodifica por valor las que vio: la
    C se lee como C aunque la tabla la numere 0. La Z, con las categorías de la
    tabla, la rechaza con error y tira la evaluación entera (la prueba trae la
    línea 8, sin entrenamiento). Con las guardadas queda nula: dato faltante.
    """
    t = _tabla()
    art = train.entrenar(t, train.columnas(CFG), OBJ, PARAMS)
    solo_c = t[t["linea"] == "C"].head(50)
    nueva = t.tail(5).assign(linea="Z")
    pred = predict.predecir(art, pd.concat([solo_c, nueva], ignore_index=True))
    mezcla = predict.predecir(art, t).loc[solo_c.index]
    np.testing.assert_allclose(pred.iloc[:50], mezcla, rtol=1e-6)
    assert pred.iloc[:50].mean() > 150
    assert pred.iloc[50:].notna().all()


def test_el_intervalo_remuestrea_viajes_y_no_filas():
    """Cada viaje gana o pierde en bloque: 30 viajes son 30 observaciones, no 1.200.

    Remuestreando filas, el intervalo saldría √40 ≈ 6 veces más estrecho.
    """
    rng = np.random.default_rng(1)
    n_viajes, filas = 30, 40
    viaje = pd.Series(np.repeat(np.arange(n_viajes), filas))
    efecto = rng.normal(0, 10, n_viajes)
    e_b = pd.Series(np.full(len(viaje), 50.0))
    e_a = e_b - np.repeat(efecto, filas)  # |e_a| − |e_b| = −efecto
    r = evaluate.diferencia(e_a, e_b, viaje)
    assert abs(r["mae_s"] + efecto.mean()) < 0.01
    lo, hi = r["mae_ic95"]
    assert lo < r["mae_s"] < hi
    esperado = 2 * 1.96 * efecto.std(ddof=1) / np.sqrt(n_viajes)
    assert 0.7 * esperado < hi - lo < 1.3 * esperado


def _horario(viajes, pasos):
    cal = pd.DataFrame(
        [
            {
                "service_id": "S",
                "start_date": "20260101",
                "end_date": "20261231",
                **dict.fromkeys(gtfs.DIAS_SEMANA, "1"),
            }
        ]
    )
    anyo = (date(2026, 1, 1), date(2026, 12, 31))
    return gtfs.Horario(
        ruta=Path("sintetico.zip"),
        version="F1",
        vigencia=anyo,
        calendario=anyo,
        viajes=pd.DataFrame(viajes, columns=["trip_id", "linea"]).assign(
            service_id="S"
        ),
        paradas_de_viaje=pd.DataFrame(
            pasos, columns=["trip_id", "stop_sequence", "stop_id", "t_prog_s"]
        ),
        paradas=pd.DataFrame(),
        calendar=cal,
        calendar_dates=pd.DataFrame(columns=["service_id", "date", "exception_type"]),
        trazados={},
    )


def test_el_intervalo_de_paso_es_el_de_los_que_salen_de_la_cabecera():
    """La cabecera P1 es el final de R1, del otro sentido: su llegada no compite.

    Contarla parte en dos el intervalo de T1 y T2 (bitácora 038: el 92 % de los
    viajes salía en la banda de 8 min o menos).
    """
    h8 = 8 * 3600
    salidas = {"T1": h8, "T2": h8 + 360, "T3": h8 + 1200, "T4": h8 + 3600}
    viajes = [(v, "L") for v in salidas] + [("R1", "L"), ("M1", "M")]
    pasos = [
        p for v, t in salidas.items() for p in ((v, 1, "P1", t), (v, 2, "P2", t + 300))
    ]
    pasos += [("R1", 1, "P2", h8 - 300), ("R1", 2, "P1", h8 + 180)]
    pasos += [("M1", 1, "P1", h8 + 60), ("M1", 2, "P3", h8 + 400)]
    dia = date(2026, 9, 22)
    h = _horario(viajes, pasos)

    iv = evaluate.intervalos(h, dia).set_index("trip_id")
    assert iv.loc["T1", "h_sig_s"] == 360
    assert np.isnan(iv.loc["T1", "h_ant_s"])
    assert iv.loc["T2", "h_ant_s"] == 360 and iv.loc["T2", "h_sig_s"] == 840
    assert iv.loc["T4", "h_ant_s"] == 2400

    tabla = pd.DataFrame(
        {
            "fecha_servicio": pd.Timestamp(dia),
            "trip_id": ["T4", "T3", "T1", "X9", "T3"],
        },
        index=[10, 11, 12, 13, 14],
    )
    banda = evaluate.banda_intervalo(tabla, [h])
    assert banda.to_dict() == {
        10: "> 30 min",
        11: "8-15 min",
        12: "<= 8 min",
        13: "sin_intervalo",
        14: "8-15 min",
    }


def test_el_modelo_de_residuo_predice_el_retraso_y_no_el_residuo():
    """Con `residuo`, el árbol aprende `objetivo − retraso_s` y predict lo suma.

    La persistencia aquí mueve cientos de segundos: si predict devolviera el
    residuo, el error sería del orden de `retraso_s`, sin ningún aviso.
    """
    t = _tabla()
    t["retraso_s"] = np.random.default_rng(3).normal(0, 300, len(t))
    t[OBJ] = t["linea"].map(NIVEL) + t["retraso_s"]
    art = train.entrenar(t, train.columnas(CFG), OBJ, {**PARAMS, "residuo": True})
    assert art["residuo"] is True
    error = (predict.predecir(art, t) - t[OBJ]).abs().mean()
    assert error < 30, error
    v = art["validacion"]["modelo_menos_persistencia_tramo"]
    assert set(v) == {"mae_s", "mae_ic95", "rmse_s", "rmse_ic95"}


def _brazo(nombre, cambios, mae, ic):
    return {
        "nombre": nombre,
        "cambios": cambios,
        "mae_s": mae,
        "ic_frente_al_mejor": ic,
    }


def test_gana_el_brazo_de_menor_mae_si_se_distingue_de_los_mas_simples():
    brazos = [
        _brazo("nivel_cuadratica", 0, 25.4, [0.8, 1.2]),
        _brazo("nivel_absoluta", 1, 25.0, [0.3, 0.6]),
        _brazo("residuo_absoluta", 2, 24.4, [0.0, 0.0]),
    ]
    assert elegir_brazo.elegir(brazos)["nombre"] == "residuo_absoluta"


def test_si_no_se_distingue_gana_el_de_menos_cambios_y_entre_iguales_el_mae():
    """ADR-021: un brazo más simple que no se distingue del mejor gana."""
    brazos = [
        _brazo("nivel_cuadratica", 0, 25.4, [0.8, 1.2]),  # se distingue: pierde
        _brazo("nivel_absoluta", 1, 24.6, [-0.1, 0.4]),  # no se distingue
        _brazo("residuo_cuadratica", 1, 24.5, [-0.2, 0.3]),  # tampoco, menor MAE
        _brazo("residuo_absoluta", 2, 24.4, [0.0, 0.0]),  # el mejor
    ]
    assert elegir_brazo.elegir(brazos)["nombre"] == "residuo_cuadratica"
