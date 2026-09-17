"""Map-matching: de posición GPS a abscisa sobre el trazado GTFS de su línea.

La abscisa —metros recorridos desde cabecera— es el eje sobre el que se
interpola el paso por parada, y por tanto el retraso. Es también la información
que no tiene el tracker: dos buses de la misma línea y sentido recorren la misma
calle en el mismo orden, y eso no se ve en las coordenadas sueltas
(`docs/bitacora/015-el-sondeo-siguiente-delata-el-intercambio.md`).

Dos decisiones que no son obvias:

**El sentido lo decide el movimiento, no la distancia.** La capa en vivo dice
`trayecto` con un texto que no casa con ningún campo del GTFS (`trips.txt` no
trae `direction_id`), y los trazados de ida y de vuelta van por las mismas calles
en buena parte del recorrido: a la misma distancia de las posiciones. Entre los
trazados candidatos de la línea se elige, para cada (línea, trayecto), el más
cercano de entre aquellos sobre los que los vehículos AVANZAN. Sobre el
contrario la abscisa correría hacia atrás.

**La ambigüedad se marca, no se resuelve en silencio.** Donde un trazado vuelve a
pasar por el mismo sitio —cierre de una circular, ida y vuelta por la misma calle
dentro de un recorrido— la proyección al punto más cercano puede caer en la
pasada equivocada. Esas posiciones se marcan `ambigua` y no cuentan para decidir
el sentido. Resolverlas con la trayectoria es trabajo del etiquetado.

El filtro de calidad es la distancia al trazado de SU línea. Nunca una caja
geográfica: borraría las líneas que salen del término municipal (trampa 006).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from project.gtfs import Trazado, a_metros

# Distancia al trazado por encima de la cual la posición no está en su ruta:
# desvío, cochera o trazado del GTFS que no corresponde a lo que circula.
FUERA_DE_RUTA_M = 60.0
# Una posición es ambigua si otra parte del trazado, a más de SEPARACION_AMBIGUA_M
# de abscisa, queda a menos de AMBIGUEDAD_M de distancia extra que la más cercana.
AMBIGUEDAD_M = 20.0
SEPARACION_AMBIGUA_M = 200.0
# Avance mínimo entre dos posiciones de un vehículo para contar como movimiento al
# decidir el sentido. Por debajo es ruido de un bus parado (p90 6,7 m, bitácora 013).
AVANCE_MIN_M = 20.0
_LOTE = 4000


def proyectar(x: np.ndarray, y: np.ndarray, trazado: Trazado) -> dict[str, np.ndarray]:
    """Abscisa, distancia y ambigüedad de cada punto (en metros) sobre `trazado`."""
    x0, y0 = trazado.x[:-1], trazado.y[:-1]
    dx, dy = np.diff(trazado.x), np.diff(trazado.y)
    seg2 = dx * dx + dy * dy
    seglen = np.sqrt(seg2)
    a0 = trazado.acum[:-1]
    n = len(x)
    abscisa, dist = np.empty(n), np.empty(n)
    ambigua = np.zeros(n, dtype=bool)

    for i in range(0, n, _LOTE):
        px, py = x[i : i + _LOTE, None], y[i : i + _LOTE, None]
        t = np.where(
            seg2 > 0,
            ((px - x0) * dx + (py - y0) * dy) / np.where(seg2 > 0, seg2, 1.0),
            0.0,
        )
        t = np.clip(t, 0.0, 1.0)
        d2 = (px - (x0 + t * dx)) ** 2 + (py - (y0 + t * dy)) ** 2
        s = a0 + t * seglen
        filas = np.arange(len(px))
        j = np.argmin(d2, axis=1)
        d1 = np.sqrt(d2[filas, j])
        s1 = s[filas, j]
        lejos = np.abs(s - s1[:, None]) > SEPARACION_AMBIGUA_M
        otra = np.sqrt(np.where(lejos, d2, np.inf).min(axis=1))
        abscisa[i : i + _LOTE] = s1
        dist[i : i + _LOTE] = d1
        ambigua[i : i + _LOTE] = otra - d1 < AMBIGUEDAD_M
    return {"abscisa_m": abscisa, "dist_m": dist, "ambigua": ambigua}


def _fraccion_que_avanza(
    g: pd.DataFrame, abscisa: np.ndarray, ambigua: np.ndarray
) -> float:
    """Fracción de pasos de un mismo vehículo en los que la abscisa crece."""
    orden = np.lexsort(
        (g["snapshot_id"].to_numpy(), g["vehicle_id"].astype(str).to_numpy())
    )
    vid = g["vehicle_id"].astype(str).to_numpy()[orden]
    s, amb = abscisa[orden], ambigua[orden]
    mismo = (vid[1:] == vid[:-1]) & ~amb[1:] & ~amb[:-1]
    paso = np.diff(s)[mismo]
    paso = paso[np.abs(paso) >= AVANCE_MIN_M]
    return float((paso > 0).mean()) if len(paso) else np.nan


def puntuar_candidatos(
    g: pd.DataFrame, x: np.ndarray, y: np.ndarray, candidatos: list[Trazado]
) -> list[dict]:
    """Cómo encaja un grupo de posiciones en cada trazado candidato, mejor primero.

    Solo cuentan las posiciones que están SOBRE el candidato (a menos de
    `FUERA_DE_RUTA_M`). Los buses aparcados en cochera siguen publicando línea y
    trayecto, son los primeros del día y los primeros `vehicle_id` del tracker:
    con ellos dentro, todos los candidatos quedan a kilómetros y el sentido se
    decide sobre ruido. Sobre la captura real eso asignó a la línea 24 un
    trazado a 4 km de mediana cuando sus buses circulan a 2 m del suyo.

    Orden: entre los candidatos que cubren al menos la mitad de lo que cubre el
    mejor, primero los que no van en sentido contrario, luego más cobertura, luego
    menos distancia. Así decide el sentido entre ida y vuelta por la misma calle
    (misma cobertura), y la geometría entre dos recorridos con el mismo nombre.
    """
    puntos = []
    for t in candidatos:
        p = proyectar(x, y, t)
        cerca = p["dist_m"] <= FUERA_DE_RUTA_M
        avanza = _fraccion_que_avanza(g, p["abscisa_m"], p["ambigua"] | ~cerca)
        puntos.append(
            {
                "trazado": t,
                "proyeccion": p,
                "cobertura": float(cerca.mean()),
                "dist_mediana_m": float(np.median(p["dist_m"][cerca]))
                if cerca.any()
                else float(np.median(p["dist_m"])),
                "avanza": avanza,
            }
        )
    mejor = max(c["cobertura"] for c in puntos)
    aptos = [c for c in puntos if mejor > 0 and c["cobertura"] >= 0.5 * mejor]
    resto = [c for c in puntos if c not in aptos]

    def clave(c: dict) -> tuple:
        contrario = not np.isnan(c["avanza"]) and c["avanza"] < 0.5
        return (
            contrario,
            -round(c["cobertura"], 2),
            c["dist_mediana_m"],
            c["trazado"].shape_id,
        )

    return sorted(aptos, key=clave) + sorted(resto, key=clave)


def emparejar(df: pd.DataFrame, trazados: dict[str, list[Trazado]]) -> pd.DataFrame:
    """Añade `shape_id`, `abscisa_m`, `dist_trazado_m`, `fuera_de_ruta`, `ambigua` y `motivo`.

    `df` debe traer: linea, trayecto, lat, lon, vehicle_id, snapshot_id (la salida
    de `tracking.rastrear`). No reordena ni descarta filas.
    """
    out = df.copy()
    out["shape_id"] = pd.Series(pd.NA, index=out.index, dtype="object")
    out["abscisa_m"] = np.nan
    out["dist_trazado_m"] = np.nan
    out["fuera_de_ruta"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out["ambigua"] = pd.Series(pd.NA, index=out.index, dtype="boolean")
    out["motivo"] = pd.Series(pd.NA, index=out.index, dtype="object")

    out.loc[out["trayecto"].isna(), "motivo"] = "sin_trayecto"
    for (linea, _trayecto), g in out[out["trayecto"].notna()].groupby(
        ["linea", "trayecto"], sort=False
    ):
        candidatos = trazados.get(str(linea), [])
        if not candidatos:
            out.loc[g.index, "motivo"] = "sin_trazado"
            continue
        x, y = a_metros(g["lat"].to_numpy(), g["lon"].to_numpy())
        elegido = puntuar_candidatos(g, x, y, candidatos)[0]
        p = elegido["proyeccion"]
        out.loc[g.index, "shape_id"] = elegido["trazado"].shape_id
        out.loc[g.index, "abscisa_m"] = p["abscisa_m"]
        out.loc[g.index, "dist_trazado_m"] = p["dist_m"]
        out.loc[g.index, "fuera_de_ruta"] = p["dist_m"] > FUERA_DE_RUTA_M
        out.loc[g.index, "ambigua"] = p["ambigua"]
    return out
