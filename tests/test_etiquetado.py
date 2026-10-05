"""La cascada del etiquetado contra una verdad-terreno que se conoce de antemano.

Un feed GTFS sintético (en `tmp_path`) y una flota que recorre sus viajes con un
retraso que decide el test. Si la cascada funciona, el retraso que sale en cada
parada es el que se metió; si algo se tuerce —la abscisa, el cruce, el viaje
asignado, el día de servicio, el feed—, sale OTRO retraso con aspecto normal, y
ese es exactamente el fallo que aquí se busca.

Geometría (metros sobre el plano local de `gtfs.a_metros`):

  línea 1   ida (0,0) → (4000,0), paradas cada 400 m, 4 m/s programados,
            salidas cada 600 s de 07:00 a 08:50, y un nocturno a las 25:10.
            Vuelta por la misma calle, 8 m al norte.
  línea 2   dos variantes del MISMO trayecto que comparten 3 km y se separan:
            V1 sigue al este hasta (4000,-2000); V2 gira al norte en x=3000.
  línea 3   punta: salidas cada 240 s.

La verdad de cada bus: sale de cabecera D segundos tarde y circula a velocidad
v; en la parada a abscisa s el retraso es D + s·(1/v − 1/v_programada).
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from project import etiquetado, gtfs, prepare
from project.gtfs import Trazado, a_grados

TZ = ZoneInfo("Europe/Madrid")
DIA = date(2026, 9, 16)  # miércoles
TOL_S = 5.0


# --------------------------------------------------------------------------- #
# Feed sintético
# --------------------------------------------------------------------------- #
def _hms(seg: float) -> str:
    seg = int(round(seg))
    h, r = divmod(seg, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _acum(pts: list[tuple[float, float]]) -> np.ndarray:
    p = np.asarray(pts, dtype=float)
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])


@dataclass
class Forma:
    shape_id: str
    puntos: list[tuple[float, float]]
    paradas: list[tuple[str, float]]  # (stop_id, abscisa) sobre la polilínea

    def xy(self, s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        a = _acum(self.puntos)
        p = np.asarray(self.puntos, dtype=float)
        return np.interp(s, a, p[:, 0]), np.interp(s, a, p[:, 1])

    @property
    def largo(self) -> float:
        return float(_acum(self.puntos)[-1])


@dataclass
class Viaje:
    trip_id: str
    forma: Forma
    salida_s: float  # segundos desde la medianoche del día de servicio
    v: float  # velocidad programada, m/s
    service_id: str = "LAB"

    def t_prog(self, s: float) -> float:
        return self.salida_s + s / self.v


@dataclass
class Linea:
    linea: str
    route_id: str
    viajes: list[Viaje] = field(default_factory=list)


def _recta(sid, x0, y0, x1, y1, cada, prefijo):
    largo = float(np.hypot(x1 - x0, y1 - y0))
    paradas = [
        (f"{prefijo}{i:02d}", s) for i, s in enumerate(np.arange(0, largo + 1, cada))
    ]
    return Forma(sid, [(x0, y0), (x1, y1)], paradas)


IDA = _recta("S1_ida", 0, 0, 4000, 0, 400, "P1i")
VUELTA = _recta("S1_vuelta", 4000, 8, 0, 8, 400, "P1v")
V1 = _recta("S2_v1", 0, -2000, 4000, -2000, 500, "P2_")
V2 = Forma(
    "S2_v2",
    [(0, -2000), (3000, -2000), (3000, -1000)],
    [(f"P2_{i:02d}", 500.0 * i) for i in range(7)]
    + [("P2n1", 3500.0), ("P2n2", 4000.0)],
)
PUNTA = _recta("S3", 0, 2000, 3000, 2000, 500, "P3_")


def _lineas(desfase_linea1: float = 0.0) -> list[Linea]:
    l1 = Linea("1", "R1")
    for k in range(12):
        l1.viajes.append(
            Viaje(f"1_{k:02d}", IDA, 7 * 3600 + 600 * k + desfase_linea1, 4.0)
        )
        l1.viajes.append(Viaje(f"1v_{k:02d}", VUELTA, 7 * 3600 + 300 + 600 * k, 4.0))
    l1.viajes.append(Viaje("1_noche", IDA, 25 * 3600 + 600 + desfase_linea1, 4.0))
    l2 = Linea("2", "R2")
    for k in range(5):
        l2.viajes.append(Viaje(f"2a_{k}", V1, 7 * 3600 + 1200 * k, 5.0))
        l2.viajes.append(Viaje(f"2b_{k}", V2, 7 * 3600 + 600 + 1200 * k, 5.0))
    l3 = Linea("3", "R3")
    for k in range(16):
        l3.viajes.append(Viaje(f"3_{k:02d}", PUNTA, 7 * 3600 + 240 * k, 5.0))
    return [l1, l2, l3]


def _csv(filas: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(filas[0]), lineterminator="\n")
    w.writeheader()
    w.writerows(filas)
    return buf.getvalue()


def escribir_feed(
    ruta: Path,
    *,
    version: str,
    vigencia: tuple[str, str],
    calendario: tuple[str, str],
    lineas: list[Linea],
    suprimidos: tuple[str, ...] = (),
    anadidos: tuple[str, ...] = (),
) -> Path:
    formas = {v.forma.shape_id: v.forma for ln in lineas for v in ln.viajes}
    routes = [
        {
            "route_id": ln.route_id,
            "route_short_name": ln.linea,
            "route_long_name": ln.linea,
            "route_type": 3,
        }
        for ln in lineas
    ]
    trips, stop_times, stops, shapes = [], [], {}, []
    for ln in lineas:
        for v in ln.viajes:
            trips.append(
                {
                    "route_id": ln.route_id,
                    "service_id": v.service_id,
                    "trip_id": v.trip_id,
                    "shape_id": v.forma.shape_id,
                }
            )
            for seq, (stop_id, s) in enumerate(v.forma.paradas, start=1):
                t = _hms(v.t_prog(s))
                # shape_dist_traveled a propósito basura: el horario reescalado,
                # como en el feed real (trampa 010). Si alguien lo usa, se nota.
                stop_times.append(
                    {
                        "trip_id": v.trip_id,
                        "arrival_time": t,
                        "departure_time": t,
                        "stop_id": stop_id,
                        "stop_sequence": seq,
                        "shape_dist_traveled": round(7.3 * v.t_prog(s), 1),
                    }
                )
                x, y = v.forma.xy(np.array([s]))
                # Las paradas en la acera: 4 m al lado del trazado.
                lat, lon = a_grados(x, y + 4.0)
                stops[stop_id] = {
                    "stop_id": stop_id,
                    "stop_name": stop_id,
                    "stop_lat": f"{lat[0]:.7f}",
                    "stop_lon": f"{lon[0]:.7f}",
                }
    for f in formas.values():
        lat, lon = a_grados(*np.asarray(f.puntos, dtype=float).T)
        for i, (la, lo) in enumerate(zip(lat, lon), start=1):
            shapes.append(
                {
                    "shape_id": f.shape_id,
                    "shape_pt_lat": f"{la:.7f}",
                    "shape_pt_lon": f"{lo:.7f}",
                    "shape_pt_sequence": i,
                    "shape_dist_traveled": 99999,
                }
            )
    calendar = [
        {
            "service_id": "LAB",
            "monday": 1,
            "tuesday": 1,
            "wednesday": 1,
            "thursday": 1,
            "friday": 1,
            "saturday": 0,
            "sunday": 0,
            "start_date": calendario[0],
            "end_date": calendario[1],
        }
    ]
    calendar_dates = [
        {"service_id": "LAB", "date": d, "exception_type": tipo}
        for tipo, dias in ((2, suprimidos), (1, anadidos))
        for d in dias
    ] or [{"service_id": "LAB", "date": "20260101", "exception_type": 2}]
    feed_info = [
        {
            "feed_publisher_name": "sintético",
            "feed_publisher_url": "x",
            "feed_lang": "es",
            "feed_start_date": vigencia[0],
            "feed_end_date": vigencia[1],
            "feed_version": version,
        }
    ]
    agency = [
        {
            "agency_id": "EMT",
            "agency_name": "EMT",
            "agency_url": "x",
            "agency_timezone": "Europe/Madrid",
        }
    ]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, filas in (
            ("agency.txt", agency),
            ("routes.txt", routes),
            ("trips.txt", trips),
            ("stop_times.txt", stop_times),
            ("stops.txt", list(stops.values())),
            ("shapes.txt", shapes),
            ("calendar.txt", calendar),
            ("calendar_dates.txt", calendar_dates),
            ("feed_info.txt", feed_info),
        ):
            z.writestr(nombre, _csv(filas))
    return ruta


@pytest.fixture(scope="module")
def feed_a(tmp_path_factory) -> Path:
    return escribir_feed(
        tmp_path_factory.mktemp("gtfs") / "a.zip",
        version="A",
        vigencia=("20260824", "20260930"),
        calendario=("20260815", "20260930"),
        lineas=_lineas(),
    )


@pytest.fixture(scope="module")
def horario_a(feed_a) -> gtfs.Horario:
    return gtfs.cargar_horario(feed_a)


# --------------------------------------------------------------------------- #
# Flota sintética
# --------------------------------------------------------------------------- #
T0_LOCAL = datetime(DIA.year, DIA.month, DIA.day, tzinfo=TZ)
CADENCIA_S = 30.0


@dataclass
class Bus:
    linea: str
    trayecto: str
    forma: Forma
    salida_s: float  # salida REAL, segundos desde la medianoche local de DIA
    v: float
    antes_s: float = 300.0  # regulación en cabecera antes de salir
    despues_s: float = 120.0
    ruido_m: float = 3.0
    hueco: tuple[float, float] | None = None  # [desde, hasta) sin posiciones
    desvio: tuple[float, float] | None = None  # tramo de abscisa desplazado 300 m
    parado_en_s: float = 0.0  # dónde espera antes de salir
    # [desde, hasta) en que la fuente publica `trayecto_alterno` (bitácora 026)
    alterna: tuple[float, float] | None = None
    trayecto_alterno: str = "Este - Oeste"

    def posiciones(
        self, rng: np.random.Generator, t0: datetime = T0_LOCAL
    ) -> pd.DataFrame:
        largo = self.forma.largo
        fin = self.salida_s + (largo - self.parado_en_s) / self.v
        k0 = int(np.ceil((self.salida_s - self.antes_s) / CADENCIA_S))
        k1 = int(np.floor((fin + self.despues_s) / CADENCIA_S))
        t = np.arange(k0, k1 + 1) * CADENCIA_S
        s = np.clip(
            self.parado_en_s + self.v * (t - self.salida_s), self.parado_en_s, largo
        )
        x, y = self.forma.xy(s)
        if self.desvio is not None:
            en = (s >= self.desvio[0]) & (s < self.desvio[1])
            y = np.where(en, y - 300.0, y)
        x = x + rng.normal(0, self.ruido_m, len(t))
        y = y + rng.normal(0, self.ruido_m, len(t))
        if self.hueco is not None:
            fuera = (t >= self.hueco[0]) & (t < self.hueco[1])
            t, x, y = t[~fuera], x[~fuera], y[~fuera]
        lat, lon = a_grados(x, y)
        # `datetime + timedelta` con zona suma sobre el reloj de la calle: las
        # 07:00 son las 07:00 también el día del cambio de hora.
        ts = pd.to_datetime([t0 + timedelta(seconds=float(v)) for v in t]).tz_convert(
            "UTC"
        )
        return pd.DataFrame(
            {
                "snapshot_id": (t // CADENCIA_S).astype(np.int64) + 1_000_000,
                "linea": self.linea,
                "trayecto": np.where(
                    (t >= self.alterna[0]) & (t < self.alterna[1]),
                    self.trayecto_alterno,
                    self.trayecto,
                )
                if self.alterna
                else self.trayecto,
                "lat": lat,
                "lon": lon,
                "ts_utc": ts,
            }
        )


def flota(*buses: Bus, semilla: int = 7, dia: date = DIA) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)
    t0 = datetime(dia.year, dia.month, dia.day, tzinfo=TZ)
    return (
        pd.concat([b.posiciones(rng, t0) for b in buses], ignore_index=True)
        .sort_values("snapshot_id", kind="stable")
        .reset_index(drop=True)
    )


def verdad(viaje: Viaje, bus: Bus) -> pd.Series:
    """Retraso verdadero por parada: salida real menos programada, más la deriva."""
    d = bus.salida_s - viaje.salida_s
    return pd.Series(
        {sid: d + s * (1 / bus.v - 1 / viaje.v) for sid, s in viaje.forma.paradas}
    )


def _viaje(trip_id: str) -> Viaje:
    return next(v for ln in _lineas() for v in ln.viajes if v.trip_id == trip_id)


def etiquetar(df: pd.DataFrame, horarios, **kw):
    return prepare.etiquetar_dia(df, horarios, etiquetado.Parametros(**kw))


def _comparar(r, trip_id: str, bus: Bus, tol: float = TOL_S) -> pd.DataFrame:
    p = r.pasos[r.pasos["trip_id"] == trip_id].set_index("stop_id")
    esperado = verdad(_viaje(trip_id), bus)
    comun = p.index.intersection(esperado.index)
    assert len(comun) > 0, f"ningún paso etiquetado para {trip_id}"
    err = (p.loc[comun, "retraso_s"] - esperado[comun]).abs()
    assert err.max() <= tol, f"{trip_id}: error máximo {err.max():.1f} s\n{err}"
    return p


# --------------------------------------------------------------------------- #
# El caso base: retraso constante y retraso que crece
# --------------------------------------------------------------------------- #
def test_el_retraso_de_salida_se_recupera_en_cada_parada(horario_a):
    buses = [
        Bus("1", "Oeste - Este", IDA, 7 * 3600 + 0, 4.0),  # viaje 1_00, en hora
        Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 90, 4.0),  # 1_01, +90 s
        Bus("1", "Oeste - Este", IDA, 7 * 3600 + 1200 - 60, 4.0),  # 1_02, -60 s
        Bus("1", "Oeste - Este", IDA, 7 * 3600 + 1800 + 200, 4.0),  # 1_03, +200 s
    ]
    r = etiquetar(flota(*buses), [horario_a])
    for trip, bus in zip(("1_00", "1_01", "1_02", "1_03"), buses):
        p = _comparar(r, trip, bus)
        # Todas, también la de cabecera (salida) y la terminal (llegada).
        assert len(p) == len(IDA.paradas), f"{trip}: sólo {len(p)} paradas con cruce"


def test_el_retraso_que_se_acumula_por_el_camino_se_recupera(horario_a):
    lento = Bus(
        "1", "Oeste - Este", IDA, 7 * 3600 + 600 + 30, 3.2
    )  # 1_01, pierde tiempo
    r = etiquetar(flota(lento), [horario_a])
    p = _comparar(r, "1_01", lento)
    assert p["retraso_s"].iloc[-1] > p["retraso_s"].iloc[0] + 200, "el retraso no crece"


# --------------------------------------------------------------------------- #
# Lo que NO es un paso por parada
# --------------------------------------------------------------------------- #
def test_la_regulacion_en_cabecera_no_es_retraso(horario_a):
    """Diez minutos esperando en la primera parada antes de salir en hora.

    La salida es cuando la abscisa ABANDONA la parada, no cuando el bus llega a
    ella: con el criterio de llegada, la espera entera saldría como adelanto.
    """
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600, 4.0, antes_s=600)
    r = etiquetar(flota(bus), [horario_a])
    p = _comparar(r, "1_01", bus)
    assert "P1i00" in p.index, "la parada de cabecera se quedó sin cruce"


def test_el_bus_que_espera_pasada_la_primera_parada_no_la_cruza(horario_a):
    """Aparcado 150 m más allá de cabecera: la primera parada no se inventa."""
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600, 4.0, parado_en_s=150.0)
    r = etiquetar(flota(bus), [horario_a])
    p = r.pasos[r.pasos["trip_id"] == "1_01"]
    assert "P1i00" not in set(p["stop_id"])
    esperado = verdad(_viaje("1_01"), bus)
    # Salió de s=150 a su hora: a partir de ahí el retraso es el de haber
    # empezado 150 m adelantado.
    assert (
        p.set_index("stop_id")["retraso_s"] - (esperado - 150 / 4.0)
    ).abs().max() <= TOL_S


def test_un_hueco_de_sondeos_no_se_interpola(horario_a):
    """Cinco minutos sin posiciones: las paradas del hueco quedan sin cruce."""
    salida = 7 * 3600 + 600
    bus = Bus("1", "Oeste - Este", IDA, salida, 4.0, hueco=(salida + 300, salida + 600))
    r = etiquetar(flota(bus), [horario_a])
    p = _comparar(r, "1_01", bus)
    # entre s = 1200 y 2400 m circula dentro del hueco
    for sid, s in IDA.paradas:
        if 1250 < s < 2350:
            assert sid not in p.index, (
                f"{sid} (s={s:.0f}) se interpoló a través del hueco"
            )


def test_la_alternancia_del_trayecto_no_corta_el_viaje(horario_a):
    """La fuente publica el sentido contrario tres sondeos a mitad de recorrido.

    La línea 25 lo hace en el 6,9-9,0 % de sus pasos (bitácora 026). Con dos
    sondeos basta `tolerar_hueco` para puentear; con tres, el viaje salía partido
    en dos tramos que se disputaban el mismo viaje programado.
    """
    salida = 7 * 3600 + 600 + 45
    bus = Bus(
        "1", "Oeste - Este", IDA, salida, 4.0, alterna=(salida + 480, salida + 570)
    )
    r = etiquetar(flota(bus), [horario_a])
    p = _comparar(r, "1_01", bus)
    assert set(p.index) == {sid for sid, _ in IDA.paradas}, "el viaje sale partido"
    assert r.viajes.query("motivo == 'asignado'")["viaje_id"].nunique() == 1


def test_un_desvio_deja_sin_cruce_las_paradas_que_se_salta(horario_a):
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600, 4.0, desvio=(1500.0, 2700.0))
    r = etiquetar(flota(bus), [horario_a])
    p = _comparar(r, "1_01", bus)
    for sid, s in IDA.paradas:
        if 1650 < s < 2550:
            assert sid not in p.index, f"{sid} (s={s:.0f}) se cruzó estando desviado"


# --------------------------------------------------------------------------- #
# Asignación de viaje
# --------------------------------------------------------------------------- #
def test_un_refuerzo_fuera_de_horario_no_se_asigna(horario_a):
    """Un bus que sale a las 06:00, cuando la línea 1 no tiene viajes."""
    bus = Bus("1", "Oeste - Este", IDA, 6 * 3600, 4.0)
    r = etiquetar(flota(bus), [horario_a])
    assert r.pasos.empty
    assert set(r.viajes["motivo"]) == {"desfase"}


def test_en_punta_el_viaje_dudoso_no_se_etiqueta(horario_a):
    """Intervalo de 240 s y bus 100 s tarde: el siguiente viaje queda a 140 s.

    Asignarlo es una lotería con aspecto de dato bueno. Se marca y no se
    etiqueta; si el margen se ignorase, la mitad de estos casos darían un
    retraso de -140 s perfectamente creíble.
    """
    bus = Bus("3", "Punta", PUNTA, 7 * 3600 + 240 * 5 + 100, 5.0)
    r = etiquetar(flota(bus), [horario_a])
    assert r.pasos.empty
    assert set(r.viajes["motivo"]) == {"margen"}
    claro = Bus("3", "Punta", PUNTA, 7 * 3600 + 240 * 5 + 10, 5.0)
    r = etiquetar(flota(claro), [horario_a])
    _comparar(r, "3_05", claro)


def test_la_variante_se_decide_por_viaje(horario_a):
    """Dos variantes del mismo trayecto: cada bus contra la suya.

    Comparten 3 km y el mismo nombre de trayecto. Si la variante se decidiese
    por grupo, el bus de V2 perdería las dos paradas de su ramal o las
    interpolaría sobre V1.
    """
    b1 = Bus("2", "Sur - Este", V1, 7 * 3600 + 1200 + 45, 5.0)  # 2a_1
    b2 = Bus("2", "Sur - Este", V2, 7 * 3600 + 600 + 1200 + 70, 5.0)  # 2b_1
    r = etiquetar(flota(b1, b2), [horario_a])
    _comparar(r, "2a_1", b1)
    p2 = _comparar(r, "2b_1", b2)
    assert {"P2n1", "P2n2"} <= set(p2.index), "el ramal de V2 se quedó sin cruces"


def test_un_viaje_programado_se_asigna_a_un_solo_bus(horario_a):
    """Dos buses sobre el mismo viaje: el segundo no hereda sus etiquetas."""
    bueno = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 20, 4.0)
    # Sin regulación: dos buses esperando en el mismo punto los confundiría el
    # tracker, y el test mediría el tracker en vez del etiquetado.
    duplicado = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 20 + 45, 4.0, antes_s=0)
    r = etiquetar(flota(bueno, duplicado), [horario_a])
    assert r.pasos.groupby("trip_id")["viaje_id"].nunique().max() == 1
    assert "conflicto" in set(r.viajes["motivo"])


# --------------------------------------------------------------------------- #
# Calendario, día de servicio y versión del feed
# --------------------------------------------------------------------------- #
def test_el_nocturno_pertenece_al_dia_de_servicio_anterior(horario_a):
    """25:10 del miércoles son las 01:10 del jueves, y el viaje es del miércoles."""
    bus = Bus("1", "Oeste - Este", IDA, 25 * 3600 + 600 + 60, 4.0)
    r = etiquetar(flota(bus), [horario_a])
    p = _comparar(r, "1_noche", bus)
    assert set(p["fecha_servicio"]) == {DIA}


def _del_dia(df: pd.DataFrame, dia: date) -> pd.DataFrame:
    """Lo que `prepare.cargar_dia` entrega para ese día de servicio."""
    desde, hasta = prepare.ventana_servicio(dia)
    return df[(df["ts_utc"] >= desde) & (df["ts_utc"] < hasta)]


def test_cada_dia_de_servicio_se_procesa_entero_y_sus_claves_no_chocan(horario_a):
    """`prepare` etiqueta por separado cada día; la unión tiene que valer igual.

    Hasta 09/2026 cortaba por día UTC —las 02:00 locales— y el día de servicio
    cambia a las 04:00: el nocturno que cruzaba las 02:00 se partía en dos
    llamadas, las dos mitades se quedaban el mismo `trip_id`, y la segunda
    numeraba `v00000` con el día de servicio anterior, chocando con el primer
    bus del día (bitácora 027: 932 `viaje_id` repetidos, 74 viajes dobles).
    """
    diurno = Bus("1", "Oeste - Este", IDA, 7 * 3600, 4.0)
    # 40 min tarde: 01:50-02:07 del jueves, a través del corte de día UTC.
    nocturno = Bus("1", "Oeste - Este", IDA, 25 * 3600 + 600 + 2400, 4.0)
    siguiente = Bus("1", "Oeste - Este", IDA, 24 * 3600 + 7 * 3600, 4.0)
    df = flota(diurno, nocturno, siguiente)
    dias = [DIA, DIA + timedelta(days=1)]
    partes = [etiquetar(_del_dia(df, d), [horario_a], max_desfase_s=3600) for d in dias]
    assert sum(len(_del_dia(df, d)) for d in dias) == len(df), "la ventana pierde filas"

    viajes = pd.concat([r.viajes for r in partes], ignore_index=True)
    pasos = pd.concat([r.pasos for r in partes], ignore_index=True)
    assert viajes["viaje_id"].is_unique, viajes[
        viajes["viaje_id"].duplicated(keep=False)
    ]
    asignados = viajes[viajes["motivo"] == "asignado"]
    assert not asignados.duplicated(["fecha_servicio", "trip_id"]).any()
    for r, d in zip(partes, dias):
        assert set(r.viajes["fecha_servicio"]) == {d}

    union = etiquetado.Resultado(pasos=pasos, viajes=viajes, posiciones=df)
    p = _comparar(union, "1_noche", nocturno)
    assert set(p.index) == {sid for sid, _ in IDA.paradas}, "el nocturno sale partido"


# El cambio de hora cae a las 02:00-03:00, ANTES del corte de las 04:00: el día
# de servicio que dura 25 h es el sábado 24/10, no el domingo del cambio.
@pytest.mark.parametrize(
    ("dia", "horas"),
    [
        (date(2026, 9, 16), 24),
        (date(2026, 10, 24), 25),
        (date(2026, 10, 25), 24),
        (date(2027, 3, 27), 23),
    ],
    ids=["normal", "vispera_invierno", "cambio_a_invierno", "vispera_verano"],
)
def test_la_ventana_de_servicio_va_de_corte_a_corte_en_hora_local(dia, horas):
    desde, hasta = prepare.ventana_servicio(dia)
    assert str(desde.tz) == "UTC" and str(hasta.tz) == "UTC"
    assert desde.tz_convert(TZ).hour == etiquetado.HORA_CORTE
    assert desde.tz_convert(TZ).date() == dia
    assert (hasta - desde) == pd.Timedelta(hours=horas)


# El GTFS no mide sus horas desde la medianoche sino desde «mediodía menos 12 h»,
# para que el horario coincida con el reloj de la calle también el día del cambio
# de hora. Ese día las dos referencias se separan una hora.
@pytest.mark.parametrize(
    ("dia", "utc_mas"),
    [(date(2026, 10, 25), 1), (date(2027, 3, 28), 2)],
    ids=["cambio_a_invierno", "cambio_a_verano"],
)
def test_el_dia_del_cambio_de_hora_el_horario_va_con_el_reloj_de_la_calle(
    tmp_path, dia, utc_mas
):
    """El viaje de las 07:10:00 sale a las 07:10:45 del reloj de la calle: +45 s.

    Medido desde la medianoche local, el horario entero de ese día se desplaza
    una hora. En octubre el bus casa con el viaje programado una hora después,
    con un retraso creíble y el `trip_id` equivocado; en marzo no casa con
    ninguno. Ninguno de los dos da error (trampa 015).
    """
    h = gtfs.cargar_horario(
        escribir_feed(
            tmp_path / "c.zip",
            version="C",
            vigencia=("20261001", "20270430"),
            calendario=("20261001", "20270430"),
            lineas=_lineas(),
            anadidos=("20261025", "20270328"),  # los dos caen en domingo
        )
    )
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 45, 4.0)  # 1_01, +45 s
    df = flota(bus, dia=dia)
    # La verdad, escrita a mano en UTC: las 07:10:45 de la calle de ese día. La
    # primera posición es de la regulación en cabecera, 285 s antes.
    salida = pd.Timestamp(f"{dia} 07:10:45", tz="UTC") - pd.Timedelta(hours=utc_mas)
    assert df["ts_utc"].min() == salida - pd.Timedelta(seconds=285), "escenario mal"

    r = etiquetar(df, [h])
    p = _comparar(r, "1_01", bus)
    assert set(p["fecha_servicio"]) == {dia}
    assert abs((p.loc["P1i00", "t_obs_utc"] - salida).total_seconds()) <= TOL_S


def test_un_dia_suprimido_en_calendar_dates_no_tiene_viajes(tmp_path):
    ruta = escribir_feed(
        tmp_path / "s.zip",
        version="S",
        vigencia=("20260824", "20260930"),
        calendario=("20260815", "20260930"),
        lineas=_lineas(),
        suprimidos=(DIA.strftime("%Y%m%d"),),
    )
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600, 4.0)
    r = etiquetar(flota(bus), [gtfs.cargar_horario(ruta)])
    assert r.pasos.empty


def test_el_feed_se_elige_por_fecha_de_servicio(tmp_path, horario_a):
    """Con dos versiones vigentes, manda la más reciente; su horario va 60 s más tarde."""
    nuevo = gtfs.cargar_horario(
        escribir_feed(
            tmp_path / "b.zip",
            version="B",
            vigencia=("20260912", "20261019"),
            calendario=("20260912", "20261019"),
            lineas=_lineas(desfase_linea1=60.0),
        )
    )
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 60, 4.0)  # en hora con B
    r = etiquetar(flota(bus), [horario_a, nuevo])
    p = r.pasos[r.pasos["trip_id"] == "1_01"]
    assert set(p["feed_version"]) == {"B"}
    assert p["retraso_s"].abs().max() <= TOL_S


def test_fuera_de_la_vigencia_declarada_se_marca(horario_a):
    h, dentro = gtfs.elegir_horario([horario_a], date(2026, 8, 18))
    assert h is horario_a and not dentro
    h, dentro = gtfs.elegir_horario([horario_a], date(2026, 8, 26))
    assert h is horario_a and dentro
    h, _ = gtfs.elegir_horario([horario_a], date(2026, 10, 5))
    assert h is None


def test_las_horas_de_servicio_pasan_de_24():
    assert list(gtfs.a_segundos(pd.Series(["07:00:00", "25:10:00", "28:03:30"]))) == [
        25200,
        90600,
        101010,
    ]


# --------------------------------------------------------------------------- #
# Robustez de la cascada
# --------------------------------------------------------------------------- #
def test_el_orden_de_las_filas_de_entrada_no_cambia_la_etiqueta(horario_a):
    """Barajar la entrada no puede mover un solo retraso.

    `rastrear` reordena por sondeo y reinicia el índice. Una columna pegada por
    POSICIÓN a la entrada original se cruza entre filas sin error: así se midió
    la mejora de la entrada 017, que era falsa (entrada 023).
    """
    buses = [
        Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 90, 4.0),
        Bus("1", "Oeste - Este", IDA, 7 * 3600 + 1200 - 40, 3.6),
        Bus("2", "Sur - Este", V2, 7 * 3600 + 600 + 1200 + 70, 5.0),
    ]
    df = flota(*buses)
    base = etiquetar(df, [horario_a]).pasos
    barajado = etiquetar(df.sample(frac=1, random_state=11), [horario_a]).pasos
    clave = ["trip_id", "stop_id"]
    a = base.set_index(clave)["retraso_s"].sort_index()
    b = barajado.set_index(clave)["retraso_s"].sort_index()
    pd.testing.assert_series_equal(a, b)


def test_las_posiciones_sin_trayecto_se_descartan_y_se_cuentan(horario_a):
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600, 4.0)
    df = flota(bus)
    aparcado = df.head(40).assign(trayecto=None, linea="1", lat=39.451, lon=-0.406)
    r = etiquetar(pd.concat([df, aparcado], ignore_index=True), [horario_a])
    assert r.descartadas_sin_trayecto == 40
    _comparar(r, "1_01", bus)
    assert r.posiciones["trayecto"].notna().all()


def test_la_etiqueta_no_depende_de_shape_dist_traveled(horario_a):
    """El feed sintético trae ese campo con el horario reescalado (trampa 010).

    Si la abscisa de las paradas saliera de ahí, caerían fuera del trazado y no
    habría ni un cruce; si saliera escalada, el retraso sería el horario contra
    sí mismo, pegado a cero. Aquí el bus va 150 s tarde y así debe salir.
    """
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600 + 150, 4.0)
    r = etiquetar(flota(bus), [horario_a])
    p = _comparar(r, "1_01", bus)
    assert (p["retraso_s"] > 140).all()


def test_las_paradas_de_un_bucle_se_proyectan_en_orden():
    """En un recorrido circular la última parada está junto a la primera.

    Proyectada al punto más cercano, caería al principio del trazado y el cruce
    del final se interpolaría en la salida. La abscisa de las paradas tiene que
    crecer con `stop_sequence`.
    """
    pts = np.array([(0, 0), (1000, 0), (1000, 1000), (0, 1000), (0, 30)], dtype=float)
    acum = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    t = Trazado("loop", "R", "L", pts[:, 0], pts[:, 1], acum)
    # La última, a 10 m del PRIMER tramo y a 36 m del final: la proyección al
    # punto más cercano la pondría en s = 30.
    xs = np.array([0.0, 1000.0, 500.0, 30.0])
    ys = np.array([4.0, 500.0, 1004.0, 10.0])
    lat, lon = a_grados(xs, ys)
    s = etiquetado.abscisas_paradas(t, lat, lon)
    assert np.all(np.diff(s) > 0), s
    assert s[-1] > 3900, f"la última parada cayó en s={s[-1]:.0f}"


def test_el_cruce_se_toma_a_la_salida_de_la_parada():
    """Bus parado en la parada de 0 a 100 s y luego a 5 m/s: sale a t=100."""
    t = np.arange(0, 301, 30, dtype=float)
    s = np.where(t < 100, 2.0 + np.sin(t) * 3.0, 5.0 * (t - 100))
    tc = etiquetado.cruces(
        t,
        s,
        np.ones_like(t, dtype=bool),
        np.array([0.0, 500.0]),
        max_hueco_s=120.0,
        margen_m=10.0,
    )
    assert abs(tc[0] - 100.0) <= 2.0, tc
    assert abs(tc[1] - 200.0) <= 1e-6, tc


def test_cada_clave_de_params_prepare_llega_al_etiquetado():
    """Hasta 09/2026 `params.yaml → prepare` traía claves que ningún código leía.

    DVC reejecuta el stage cuando cambian, así que una clave muerta hace creer
    que se ha cambiado un umbral cuando no se ha cambiado nada.
    """
    import dataclasses

    import yaml

    from project.config import RAIZ

    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["prepare"]
    campos = {f.name for f in dataclasses.fields(etiquetado.Parametros)}
    assert set(cfg) <= campos, f"claves que nadie lee: {set(cfg) - campos}"
    p = prepare.cargar_parametros()

    def plano(v):  # YAML da listas; el dataclass, tuplas
        return [plano(x) for x in v] if isinstance(v, (list, tuple)) else v

    assert all(plano(getattr(p, k)) == plano(v) for k, v in cfg.items())
    assert p.excluido(date(2026, 9, 3)) and not p.excluido(date(2026, 9, 8))


def test_un_dia_excluido_no_se_etiqueta_y_se_cuenta(horario_a):
    """Del 31/08 al 07/09 ningún horario publicado describe lo que circuló
    (bitácora 024): esos días se excluyen de forma declarada, no se etiquetan
    con un horario que no es, y cada tramo queda contado como `excluido`.
    """
    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600, 4.0)
    dia = DIA.isoformat()
    r = etiquetar(flota(bus), [horario_a], excluir_fechas=((dia, dia),))
    assert r.pasos.empty
    assert len(r.viajes) and set(r.viajes["motivo"]) == {"excluido"}
    assert set(r.posiciones["estado"]) == {"excluido"}
    otro = etiquetar(
        flota(bus), [horario_a], excluir_fechas=(("2026-08-31", "2026-09-07"),)
    )
    _comparar(otro, "1_01", bus)


def test_un_dia_excluido_se_escribe_con_el_mismo_esquema(horario_a, tmp_path):
    """Issue #2: el día excluido no pasa por el map-matching ni por la
    asignación, y escrito tal cual perdía `trip_id`, `shape_id`, `abscisa_m`...
    DuckDB falla al leer el glob; pandas rellena con NaN y el dtype depende de
    qué partición entre primero. Cada tabla se escribe con su esquema fijo.
    """
    import duckdb

    bus = Bus("1", "Oeste - Este", IDA, 7 * 3600 + 600, 4.0)
    dia = DIA.isoformat()
    normal = etiquetar(flota(bus), [horario_a])
    excluido = etiquetar(flota(bus), [horario_a], excluir_fechas=((dia, dia),))
    sin_horario = etiquetar(flota(bus), [])
    # El esquema no tira nada que el etiquetado produzca en un día normal.
    for nombre, df in (("viajes", normal.viajes), ("pasos", normal.pasos)):
        assert set(df.columns) == set(prepare.ESQUEMAS[nombre].names), nombre
    for nombre, attr in (
        ("emt_tracked", "posiciones"),
        ("viajes", "viajes"),
        ("pasos", "pasos"),
    ):
        for etiqueta, r in (("a", normal), ("b", excluido), ("c", sin_horario)):
            d = tmp_path / nombre / f"date={etiqueta}"
            d.mkdir(parents=True)
            t = prepare.con_esquema(nombre, getattr(r, attr))
            assert t.schema == prepare.ESQUEMAS[nombre], (nombre, etiqueta)
            prepare.pq.write_table(t, d / "part.parquet")
        # Sin union_by_name: es como falló medir_rutas.
        glob = (tmp_path / nombre / "*" / "*.parquet").as_posix()
        duckdb.sql(f"select * from read_parquet('{glob}')").fetchall()
