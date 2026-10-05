"""La cota del error de asignación (`analysis/medir_asignacion.py`).

El error que acota no se ve en la captura: un bus que va más de medio intervalo
tarde se asigna al viaje siguiente con un retraso creíble. Aquí sí se ve, porque
la flota es sintética: se decide el retraso de cada bus, se pliega como lo pliega
`_asignar_tramo` y se exige que el estimador recupere lo que se plegó mirando
solo lo que la asignación deja ver.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from project.analysis.medir_asignacion import cola, cota, estimar

M = 120.0


def _flota(escala: float, n: int = 40_000, semilla: int = 3):
    rng = np.random.default_rng(semilla)
    h = rng.choice([300.0, 480.0, 600.0, 900.0, 1800.0, 3600.0], n)
    d = rng.exponential(escala, n) - 60.0  # casi todos tarde, alguno adelantado
    bien = (d <= (h - M) / 2) & (-d <= (h - M) / 2)
    mal = d >= (h + M) / 2  # al siguiente; adelantos de más de medio H no hay
    visto = pd.DataFrame(
        {
            "desfase_s": np.where(mal, d - h, d),  # el mal asignado parece pronto
            "h_sig_s": h,
            "h_ant_s": h,
        }
    )[bien | mal]
    return visto, int(mal.sum()), int((~bien & ~mal).sum())


def test_la_cola_truncada_recupera_la_distribucion():
    """Sin la corrección, la cola de una muestra truncada sale corta."""
    rng = np.random.default_rng(0)
    d = rng.exponential(150.0, 50_000)
    c = rng.choice([150.0, 300.0, 1000.0], d.size)
    s = cola(d[d <= c], c[d <= c], np.array([100.0, 200.0]))
    assert np.allclose(s, np.exp(-np.array([100.0, 200.0]) / 150.0), atol=0.02)
    ingenua = (d[d <= c] > 200).mean()
    assert ingenua < 0.75 * np.exp(-200 / 150)


@pytest.mark.parametrize("escala", [100.0, 150.0, 250.0])
def test_la_cota_acota_y_la_calibrada_recupera_lo_que_no_se_ve(escala):
    """La bruta nunca por debajo de la verdad; calibrada con los rechazos, a ±15 %.

    La bruta se pasa porque el mal asignado parece un adelanto y engorda la otra
    cola: con escala 250 lo doblaba. Los rechazos predichos se pasan igual.
    """
    visto, mal, rechazos = _flota(escala)
    bruta, calibrada, _ = estimar(cota(visto, M), rechazos)
    assert bruta >= mal, (bruta, mal)
    assert abs(calibrada - mal) / mal < 0.15, (calibrada, mal)


def test_con_intervalos_largos_no_hay_pliegue_y_la_cota_lo_dice():
    visto, _, _ = _flota(150.0)
    largos = visto[visto["h_sig_s"] >= 1800]
    bruta, _, _ = estimar(cota(largos, M), 0)
    assert bruta / len(largos) < 0.01
