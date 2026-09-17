"""El tracker contra una flota que se mueve como la real.

La flota por defecto de `simular_flota` va en línea casi recta a velocidad
constante: justo lo que supone el predictor, que sale perfecto por construcción.
Sobre 52 ventanas reales los buses están parados el 29 % de los pasos y giran
con un p90 de 57°; en la flota por defecto, 0 % y 14°
(`docs/bitacora/013-la-flota-simulada-no-para-ni-gira.md`).

Con paradas o giros calibrados sobre esas cifras, el tracker intercambia
identidades cuando dos buses del mismo grupo coinciden a menos de un paso en el
instante en que uno se detiene o gira: el predictor extrapola al parado hacia
delante y le asigna la posición del que pasa. Casi siempre se deshace en el
sondeo siguiente; en convoy, no.

Es un defecto conocido y no corregido, así que se fija con `xfail(strict=True)`
por semilla: si alguien lo arregla, los xfail pasan a XPASS y la suite se pone
roja para que se retire el marcador. Las semillas son las que fallan medidas; las
que no fallan no están, porque no probarían nada.
"""

from __future__ import annotations

import pytest

from project.analysis.auditar_supuestos import PARADO_KMH, medidas, resumir
from project.analysis.medir_tracking import medir
from project.analysis.simulacion import simular_flota
from project.tracking import rastrear

P_PARADA = 0.17  # ~29 % de pasos parados, la cifra real
P_GIRO = 0.10


@pytest.mark.xfail(
    strict=True,
    reason="DEFECTO CONOCIDO: con paradas al ritmo real el predictor de velocidad "
    "constante extrapola al bus detenido y lo intercambia con el que pasa. Medido: "
    "2-4 saltos y 3,3 % de trayectorias contaminadas por semilla, fragmentación 1,00. "
    "Al corregirlo, quitar este marcador.",
)
@pytest.mark.parametrize("semilla", [23, 42, 101])
def test_paradas_realistas_no_intercambian_identidad(semilla):
    m = medir(simular_flota(semilla=semilla, p_parada=P_PARADA), predictivo=True)
    assert m["saltos"] == 0, f"{m['saltos']} saltos con paradas"


@pytest.mark.xfail(
    strict=True,
    reason="DEFECTO CONOCIDO: un giro de 90° en un encuentro a menos de un paso "
    "invierte la extrapolación. Medido: 4 saltos y 3,3 % de trayectorias "
    "contaminadas por semilla. Los giros están SUBcalibrados (p90 24° frente a "
    "57° reales). Al corregirlo, quitar este marcador.",
)
@pytest.mark.parametrize("semilla", [7, 42])
def test_giros_realistas_no_intercambian_identidad(semilla):
    m = medir(simular_flota(semilla=semilla, p_giro=P_GIRO), predictivo=True)
    assert m["saltos"] == 0, f"{m['saltos']} saltos con giros"


@pytest.mark.parametrize("semilla", [7, 23, 42, 101])
def test_sin_paradas_ni_giros_las_mismas_semillas_no_fallan(semilla):
    """Discriminación: los xfail de arriba caen por el fenómeno, no por la semilla."""
    m = medir(simular_flota(semilla=semilla), predictivo=True)
    assert m["saltos"] == 0 and m["contaminadas"] == 0.0, m


def test_las_paradas_simuladas_se_parecen_a_las_reales():
    """Calibración: si esto deja de dar ~29 %, los xfail miden otra cosa."""
    sim = simular_flota(n_snaps=80, p_parada=P_PARADA)
    r = resumir(medidas(rastrear(sim.drop(columns=["verdad"]))))
    assert 0.20 <= r["parado"] <= 0.38, (
        f"parado={r['parado']:.1%} (< {PARADO_KMH} km/h)"
    )
