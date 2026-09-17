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

Casi siempre el error se delata en el sondeo siguiente, y `_suavizar_intercambios`
lo usa para deshacerlo: con las semillas de ajuste, paradas pasa de 20 a 6 saltos,
giros de 20 a 2 y los fenómenos combinados de 10 a 0
(`docs/bitacora/015-el-sondeo-siguiente-delata-el-intercambio.md`).

Las semillas son las que fallaban antes del suavizado; las que no fallaban no
están, porque no probarían nada. Dos siguen fallando y se fijan con
`xfail(strict=True)`: no son el defecto, son el límite de lo que se puede
deshacer mirando posiciones.
"""

from __future__ import annotations

import pytest

from project.analysis.auditar_supuestos import PARADO_KMH, medidas, resumir
from project.analysis.medir_tracking import medir
from project.analysis.simulacion import simular_flota
from project.tracking import rastrear

P_PARADA = 0.17  # ~29 % de pasos parados, la cifra real
P_GIRO = 0.10


@pytest.mark.parametrize(
    "semilla",
    [
        pytest.param(
            23,
            marks=pytest.mark.xfail(
                strict=True,
                reason="LÍMITE: dos buses parados a 59 m arrancan a la vez en el "
                "ÚLTIMO sondeo. Sin velocidad previa y sin sondeo siguiente, las "
                "dos asignaciones son igual de plausibles.",
            ),
        ),
        42,
        pytest.param(
            101,
            marks=pytest.mark.xfail(
                strict=True,
                reason="LÍMITE: un bus llega y se detiene a 37 m de otro parado que "
                "arranca, con rumbos no relacionados. El cambio de velocidad de las "
                "dos asignaciones empata dentro del ruido; ampliar la ventana a ±4 "
                "sondeos no lo resuelve. En la calle, los dos irían por la misma vía.",
            ),
        ),
    ],
)
def test_paradas_realistas_no_intercambian_identidad(semilla):
    m = medir(simular_flota(semilla=semilla, p_parada=P_PARADA), predictivo=True)
    assert m["saltos"] == 0, f"{m['saltos']} saltos con paradas"


@pytest.mark.parametrize("semilla", [7, 42])
def test_giros_realistas_no_intercambian_identidad(semilla):
    m = medir(simular_flota(semilla=semilla, p_giro=P_GIRO), predictivo=True)
    assert m["saltos"] == 0, f"{m['saltos']} saltos con giros"


@pytest.mark.parametrize("semilla", [7, 23, 42, 101])
def test_sin_paradas_ni_giros_las_mismas_semillas_no_fallan(semilla):
    """Discriminación: las semillas de arriba se eligieron por el fenómeno, no al revés."""
    m = medir(simular_flota(semilla=semilla), predictivo=True)
    assert m["saltos"] == 0 and m["contaminadas"] == 0.0, m


def test_las_paradas_simuladas_se_parecen_a_las_reales():
    """Calibración: si esto deja de dar ~29 %, los xfail miden otra cosa."""
    sim = simular_flota(n_snaps=80, p_parada=P_PARADA)
    r = resumir(medidas(rastrear(sim.drop(columns=["verdad"]))))
    assert 0.20 <= r["parado"] <= 0.38, (
        f"parado={r['parado']:.1%} (< {PARADO_KMH} km/h)"
    )
