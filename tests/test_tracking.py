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
    _, acc_pred = predictivo
    _, acc_ing = ingenuo
    assert acc_pred >= acc_ing, f"{acc_pred:.1%} vs {acc_ing:.1%}"


def test_tasa_de_emparejamiento_por_encima_del_95(predictivo):
    r, _ = predictivo
    assert r["tasa_emparejamiento"] >= 0.95, f"tasa={r['tasa_emparejamiento']}"


def test_velocidades_dentro_del_rango_simulado(predictivo):
    """La simulación usa 3-30 km/h. Fuera de ahí el emparejamiento inventó saltos."""
    r, _ = predictivo
    assert 2.0 <= r["vel_kmh_p50"] <= 32.0, f"p50={r['vel_kmh_p50']}"
