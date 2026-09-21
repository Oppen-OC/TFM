"""GTFS estático de la EMT: los trazados, en metros.

El feed trae el horario teórico y la geometría de cada recorrido. Este módulo
lee las dos cosas: la geometría, lista para proyectar posiciones encima, y el
horario de cada versión del feed (`Horario`), con su calendario y su vigencia. Qué contiene cada fichero y qué muerde de cada uno:
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
from datetime import date, datetime
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


# --------------------------------------------------------------------------- #
# Horario: el término programado de la etiqueta
# --------------------------------------------------------------------------- #
DIAS_SEMANA = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def a_segundos(horas: pd.Series) -> np.ndarray:
    """'HH:MM:SS' a segundos desde la medianoche del DÍA DE SERVICIO.

    El GTFS admite horas por encima de 24 —en este feed hasta 28:03—: son
    madrugada del día siguiente dentro del mismo día de servicio. Por eso no se
    puede usar `pd.to_datetime`, que las rechaza o las pliega al día equivocado.
    """
    partes = horas.astype(str).str.split(":", expand=True).astype(int)
    return (partes[0] * 3600 + partes[1] * 60 + partes[2]).to_numpy()


def _fecha(s: str) -> date:
    return datetime.strptime(str(s), "%Y%m%d").date()


@dataclass(frozen=True)
class Horario:
    """Una versión del feed: sus viajes, su horario, su calendario y sus trazados."""

    ruta: Path
    version: str
    vigencia: tuple[date, date]  # `feed_info`: lo que el editor declara
    calendario: tuple[date, date]  # lo que cubre `calendar.txt`
    viajes: pd.DataFrame  # trip_id, route_id, service_id, shape_id, linea
    paradas_de_viaje: pd.DataFrame  # trip_id, stop_sequence, stop_id, t_prog_s
    paradas: pd.DataFrame  # stop_id -> lat, lon
    calendar: pd.DataFrame
    calendar_dates: pd.DataFrame
    trazados: dict[str, list[Trazado]]

    def servicios(self, dia: date) -> set[str]:
        """`service_id` activos ese día: patrón semanal más excepciones."""
        c = self.calendar
        ymd = dia.strftime("%Y%m%d")
        activos = set(
            c[
                (c["start_date"] <= ymd)
                & (c["end_date"] >= ymd)
                & (c[DIAS_SEMANA[dia.weekday()]] == "1")
            ]["service_id"]
        )
        exc = self.calendar_dates[self.calendar_dates["date"] == ymd]
        activos |= set(exc[exc["exception_type"] == "1"]["service_id"])
        activos -= set(exc[exc["exception_type"] == "2"]["service_id"])
        return activos

    def trazado(self, shape_id: str) -> Trazado:
        for ts in self.trazados.values():
            for t in ts:
                if t.shape_id == shape_id:
                    return t
        raise KeyError(shape_id)


def cargar_horario(ruta: Path) -> Horario:
    """Lee una versión del feed. `shape_dist_traveled` no se lee (trampa 010)."""
    with zipfile.ZipFile(ruta) as z:
        routes = _leer(z, "routes.txt")
        trips = _leer(z, "trips.txt")
        stop_times = _leer(z, "stop_times.txt")
        stops = _leer(z, "stops.txt")
        calendar = _leer(z, "calendar.txt")
        calendar_dates = (
            _leer(z, "calendar_dates.txt")
            if "calendar_dates.txt" in z.namelist()
            else pd.DataFrame(columns=["service_id", "date", "exception_type"])
        )
        info = _leer(z, "feed_info.txt") if "feed_info.txt" in z.namelist() else None

    viajes = trips[["trip_id", "route_id", "service_id", "shape_id"]].merge(
        routes[["route_id", "route_short_name"]], on="route_id"
    )
    viajes = viajes.rename(columns={"route_short_name": "linea"})
    pv = stop_times[["trip_id", "stop_sequence", "stop_id", "arrival_time"]].copy()
    pv["stop_sequence"] = pd.to_numeric(pv["stop_sequence"])
    pv["t_prog_s"] = a_segundos(pv["arrival_time"])
    pv = pv.drop(columns="arrival_time").sort_values(
        ["trip_id", "stop_sequence"], kind="stable"
    )
    paradas = stops[["stop_id"]].assign(
        lat=pd.to_numeric(stops["stop_lat"]), lon=pd.to_numeric(stops["stop_lon"])
    )
    cal = (_fecha(calendar["start_date"].min()), _fecha(calendar["end_date"].max()))
    if info is not None and len(info):
        vig = (_fecha(info["feed_start_date"][0]), _fecha(info["feed_end_date"][0]))
        version = str(info["feed_version"][0])
    else:
        vig, version = cal, Path(ruta).stem
    return Horario(
        ruta=Path(ruta),
        version=version,
        vigencia=vig,
        calendario=cal,
        viajes=viajes,
        paradas_de_viaje=pv.reset_index(drop=True),
        paradas=paradas.set_index("stop_id"),
        calendar=calendar,
        calendar_dates=calendar_dates,
        trazados=cargar_trazados(ruta),
    )


def versiones(directorio: Path) -> list[Path]:
    """Todos los feeds guardados bajo `directorio`, cada versión en su zip."""
    return sorted(Path(directorio).rglob("*.zip"))


def elegir_horario(horarios: list[Horario], dia: date) -> tuple[Horario | None, bool]:
    """El feed que manda en un día de servicio, y si ese día está en su vigencia.

    Manda la versión más reciente —la de vigencia que empieza más tarde— entre
    las que declaran vigencia ese día: cada publicación sustituye a la anterior.
    Si ninguna la declara, la más reciente cuyo `calendar.txt` lo cubre, y se
    marca como fuera de vigencia: el feed 01-09-2026 declara desde el 24/08
    aunque su calendario diga 15/08 (`docs/09_gtfs_emt.md`, punto 6).
    """
    vigentes = [h for h in horarios if h.vigencia[0] <= dia <= h.vigencia[1]]
    if vigentes:
        return max(vigentes, key=lambda h: (h.vigencia[0], h.vigencia[1])), True
    cubren = [h for h in horarios if h.calendario[0] <= dia <= h.calendario[1]]
    if cubren:
        return max(cubren, key=lambda h: (h.vigencia[0], h.vigencia[1])), False
    return None, False
