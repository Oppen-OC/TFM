"""El medidor del soporte por línea (`analysis/medir_soporte.py`).

Sus dos predictores son sustitutos de un modelo que aún no existe: acotan qué
mejora se distinguiría en una línea. Si uno de ellos coincide con la
persistencia, su diferencia es cero por construcción y el intervalo que se
publica es estrecho sin que nada lo delate.
"""

from __future__ import annotations

import pandas as pd

from project.analysis import medir_soporte

OBJ = "retraso_siguiente_parada_s"


def test_los_predictores_sustitutos_estan_definidos_en_todas_las_filas():
    """Sin otro viaje de la línea en la ventana, el «lejano» no es la persistencia.

    Era la media de la persistencia y el retraso medio de la línea en 5 min, con
    los huecos rellenados con la propia persistencia. En las líneas de menos de
    100 viajes faltaba en el 89 % de las filas: ahí la diferencia era cero y el
    semiancho de su intervalo salía en 6,9 s cuando eran más de 16.
    """
    test = pd.DataFrame(
        {
            "retraso_s": [100.0, -50.0, 200.0],
            OBJ: [120.0, -40.0, 160.0],
            "linea_retraso_5min": [float("nan")] * 3,
        }
    )
    e = medir_soporte.errores(test, OBJ)
    assert e["mae"].tolist() == [20.0, 10.0, 40.0]
    assert e["dif_cerca"].tolist() == [10.0, -5.0, -20.0]  # |0,9·r − y| − |r − y|
    assert e["dif_lejos"].tolist() == [50.0, 5.0, 20.0]  # |0,5·r − y| − |r − y|
