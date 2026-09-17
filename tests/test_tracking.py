"""Reconstrucción de identidad de vehículo sobre flota simulada.

Guardia de la trampa 004 del registro `.claude/trampas/`. La capa de la EMT no
publica identificador de vehículo, así que la identidad se infiere: cualquier
error aquí contamina todas las etiquetas de retraso aguas abajo sin lanzar una
excepción.

Que la flota sea SIMULADA no es una comodidad, es el requisito. Sobre datos
reales no existe verdad-terreno contra la que medir, así que "60 trayectorias
reconstruidas" parecería un éxito aunque cada trayectoria mezclase tres buses
distintos. Eso es exactamente lo que pasó con la trampa 004: la métrica decía
11 % siendo 99 %, y solo se vio porque había verdad conocida.
"""

from __future__ import annotations

import pandas as pd
import pytest

from project import tracking
from project.analysis.medir_tracking import medir
from project.analysis.simulacion import simular_flota
from project.tracking import rastrear, resumen


def _evaluar(sim: pd.DataFrame, predictivo: bool) -> tuple[dict, float]:
    """Devuelve el resumen del tracker y la precisión de identidad.

    Precisión de identidad: para cada trayectoria reconstruida, qué fracción de
    sus posiciones pertenece al bus real mayoritario.
    """
    out = rastrear(sim.drop(columns=["verdad"]), predictivo=predictivo)
    out["verdad"] = sim["verdad"]
    aciertos = (
        out.groupby("vehicle_id")["verdad"]
        .agg(lambda s: s.value_counts().iloc[0])
        .sum()
    )
    return resumen(out), aciertos / len(out)


@pytest.fixture(scope="module")
def predictivo(flota_simulada) -> tuple[dict, float]:
    return _evaluar(flota_simulada, predictivo=True)


@pytest.fixture(scope="module")
def ingenuo(flota_simulada) -> tuple[dict, float]:
    return _evaluar(flota_simulada, predictivo=False)


def test_reconstruye_una_trayectoria_por_bus(predictivo):
    r, _ = predictivo
    assert r["trayectorias"] == 60, f"obtenidas {r['trayectorias']}"


def test_tracker_predictivo_identidad_correcta(predictivo):
    """TRAMPA 004: `sort_values` usa quicksort, que NO es estable.

    Reordena filas dentro del mismo snapshot y rompe todo lo que reenganche por
    posición de fila. Este umbral es la guardia: con el bug, cae al 11 %.
    """
    _, acc = predictivo
    assert acc >= 0.99, f"{acc:.1%}"


def test_predictivo_mejora_al_ingenuo(predictivo, ingenuo):
    """Estrictamente mejor: con `>=` pasaba aunque la predicción no hiciera nada.

    Sobre esta flota el predictivo acierta el 100 % y el ingenuo el 97,8 %. La
    auditoría de 09/2026 desactivó la predicción y este test seguía verde.
    """
    _, acc_pred = predictivo
    _, acc_ing = ingenuo
    assert acc_pred > acc_ing, f"{acc_pred:.1%} vs {acc_ing:.1%}"


def test_tasa_de_emparejamiento_por_encima_del_95(predictivo):
    r, _ = predictivo
    assert r["tasa_emparejamiento"] >= 0.95, f"tasa={r['tasa_emparejamiento']}"


def test_velocidades_dentro_del_rango_simulado(predictivo):
    """La simulación usa 3-30 km/h. Fuera de ahí el emparejamiento inventó saltos."""
    r, _ = predictivo
    assert 2.0 <= r["vel_kmh_p50"] <= 32.0, f"p50={r['vel_kmh_p50']}"


def test_sin_saltos_de_identidad(flota_simulada):
    """La guardia en la unidad que NO se diluye.

    `test_tracker_predictivo_identidad_correcta` cuenta posiciones mal asignadas
    sobre el total de posiciones, y ese denominador crece con la captura: a 80
    snapshots, cuatro saltos de identidad dan un 0,7 % de error y pasarían el
    umbral del 99 % sin haberse corregido ninguno (`docs/bitacora/001-...`).

    Un salto no se corrige solo: a partir de él la trayectoria mezcla dos buses.
    Por eso se cuentan saltos y trayectorias contaminadas, no posiciones.
    """
    m = medir(flota_simulada, predictivo=True)
    assert m["saltos"] == 0, f"{m['saltos']} saltos de identidad"
    assert m["contaminadas"] == 0.0, (
        f"{m['contaminadas']:.1%} de trayectorias con dos buses dentro"
    )


def test_captura_larga_no_esconde_saltos():
    """Ocho veces más snapshots: es donde la métrica por posición se diluye."""
    m = medir(simular_flota(n_snaps=160), predictivo=True)
    assert m["saltos"] == 0, f"{m['saltos']} saltos en 160 snapshots"


@pytest.mark.parametrize("suavizado", [True, False], ids=["con_suavizado", "predictor"])
def test_un_sondeo_que_falta_no_rompe_la_identidad(suavizado, monkeypatch):
    """TRAMPA 009: el predictor extrapolaba en pasos de snapshot, no en segundos.

    `2*lat - _plat` es el movimiento rectilíneo uniforme en diferencias finitas y
    es correcto mientras todos los pasos duren lo mismo. En cuanto falta un
    sondeo, `_plat` queda dos pasos atrás mientras la predicción sigue siendo de
    uno: el desplazamiento leído es el doble del real y la extrapolación se pasa
    de largo. Con el bug, este escenario da 4 saltos y 3,3 % de contaminadas.

    Los saltos NO caen en la transición que salta el hueco, sino en las una o dos
    siguientes. Esa distancia entre síntoma y causa es lo que hace que se le
    atribuya al cambio que lo destapó: `docs/bitacora/010-plat-sin-su-dt.md`.

    El caso `predictor` desactiva `_suavizar_intercambios`, y es el que guarda la
    trampa. El suavizado deshace después los intercambios que este bug provoca,
    así que con él activo el test seguía verde con el predictor roto: la segunda
    línea de defensa tapaba la regresión de la primera (auditoría de mutación,
    mutante 017 sobre 9269074).
    """
    if not suavizado:
        monkeypatch.setattr(tracking, "_suavizar_intercambios", lambda df: df)
    m = medir(simular_flota(huecos=(7,)), predictivo=True)
    assert m["saltos"] == 0, f"{m['saltos']} saltos tras el hueco"
    assert m["contaminadas"] == 0.0, f"{m['contaminadas']:.1%} contaminadas"


def test_el_hueco_discrimina_de_verdad():
    """Sin el arreglo este escenario falla; sin el hueco, ninguno de los dos.

    Fija que el escenario ejercita el defecto en vez de pasar por casualidad. La
    fragmentación se queda en 1,00 en los dos casos: la trampa 009 es fusión
    pura, y el eje que se añadió para medir la partición es ciego a ella.
    """
    con_hueco = medir(simular_flota(huecos=(7,)), predictivo=True)
    sin_hueco = medir(simular_flota(), predictivo=True)
    assert con_hueco["fragmentacion"] == sin_hueco["fragmentacion"] == 1.0, (
        "el hueco fragmenta: este escenario ya no aísla la fusión"
    )
    dt = (
        simular_flota(huecos=(7,))
        .groupby("snapshot_id")["ts_utc"]
        .max()
        .diff()
        .dt.total_seconds()
        .dropna()
    )
    assert dt.nunique() > 1, "la cadencia es uniforme: el escenario no ejercita nada"
    assert dt.max() == 2 * dt.min()


def test_la_metrica_por_posicion_no_delataria_el_fallo():
    """Test de discriminación: fija POR QUÉ existen los dos de arriba.

    El tracker ingenuo a 80 snapshots contamina el 5 % de las trayectorias y aun
    así saca un 99,3 % de precisión por posición. Si esta combinación deja de
    darse, la afirmación de la bitácora ha caducado y hay que volver a medirla,
    no borrar el test.
    """
    m = medir(simular_flota(n_snaps=80), predictivo=False)
    assert m["err_ident"] < 0.01, f"err por posición {m['err_ident']:.3%}"
    assert m["saltos"] > 0 and m["contaminadas"] > 0.0, (
        "el ingenuo ya no falla en esta configuración: remide la bitácora 001"
    )
