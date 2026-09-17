"""GTFS estático de la EMT: los trazados, en metros.

El feed trae el horario teórico y la geometría de cada recorrido. Este módulo
lee lo segundo y lo deja listo para proyectar posiciones encima; el horario lo
leerá el etiquetado. Qué contiene cada fichero y qué muerde de cada uno:
`docs/09_gtfs_emt.md`.

Tres cosas que parecen detalle y no lo son:

- `shape_pt_sequence` se ordena como NÚMERO. Leído como texto, "10" va antes que
  "2" y la polilínea sale en zigzag, con una longitud plausible y la abscisa
  falseada sin error alguno.
- `shape_dist_traveled` se IGNORA. En este feed no es distancia sino el horario
  reescalado (trampa 010): la abscisa se calcula sobre la geometría.
- `route_short_name` no es única (73, C2 y C3 tienen dos `route_id`). Los
  trazados se agrupan por nombre visible, que es lo que publica la capa en vivo,
  y cada uno conserva su `route_id`.

La proyección a metros es equirrectangular con una latitud de referencia fija en
València. Sobre un área de 25 km el error de escala es menor del 0,3 %, muy por
debajo del ruido de posición, y a cambio es exacta de ida y vuelta, que es lo
que permite construir tests con la abscisa verdadera conocida.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from project.config import settings

LAT_REF, LON_REF = 39.47, -0.376
M_POR_GRADO = 111_320.0
_COS_REF = float(np.cos(np.radians(LAT_REF)))


def a_metros(lat, lon):
    """Grados a metros sobre el plano local de València."""
    x = (np.asarray(lon, dtype=float) - LON_REF) * M_POR_GRADO * _COS_REF
    y = (np.asarray(lat, dtype=float) - LAT_REF) * M_POR_GRADO
    return x, y


def a_grados(x, y):
    """Metros del plano local a (lat, lon). Inversa exacta de `a_metros`."""
    lat = LAT_REF + np.asarray(y, dtype=float) / M_POR_GRADO
    lon = LON_REF + np.asarray(x, dtype=float) / (M_POR_GRADO * _COS_REF)
    return lat, lon


@dataclass(frozen=True)
class Trazado:
    """Un recorrido del GTFS como polilínea en metros, con su abscisa acumulada."""

    shape_id: str
    route_id: str
    linea: str
    x: np.ndarray
    y: np.ndarray
    acum: np.ndarray

    @property
    def largo(self) -> float:
        return float(self.acum[-1])


def _leer(z: zipfile.ZipFile, nombre: str) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(z.read(nombre)), dtype=str, encoding="utf-8")


def cargar_trazados(ruta: Path | None = None) -> dict[str, list[Trazado]]:
    """Trazados del feed agrupados por línea visible (`route_short_name`)."""
    with zipfile.ZipFile(ruta or settings.gtfs_zip) as z:
        routes = _leer(z, "routes.txt")
        trips = _leer(z, "trips.txt")
        shapes = _leer(z, "shapes.txt")

    ruta_de = (
        trips[["shape_id", "route_id"]]
        .dropna()
        .drop_duplicates("shape_id")
        .merge(routes[["route_id", "route_short_name"]], on="route_id")
        .set_index("shape_id")
    )
    shapes = shapes.assign(
        secuencia=pd.to_numeric(shapes["shape_pt_sequence"]),
        lat=pd.to_numeric(shapes["shape_pt_lat"]),
        lon=pd.to_numeric(shapes["shape_pt_lon"]),
    ).sort_values(["shape_id", "secuencia"], kind="stable")

    por_linea: dict[str, list[Trazado]] = {}
    for shape_id, g in shapes.groupby("shape_id", sort=True):
        if shape_id not in ruta_de.index:
            continue
        x, y = a_metros(g["lat"].to_numpy(), g["lon"].to_numpy())
        acum = np.concatenate([[0.0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))])
        route_id, linea = ruta_de.loc[shape_id, ["route_id", "route_short_name"]]
        por_linea.setdefault(linea, []).append(
            Trazado(str(shape_id), str(route_id), str(linea), x, y, acum)
        )
    return por_linea
