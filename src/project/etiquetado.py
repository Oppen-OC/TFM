"""Del autobús rastreado al retraso en cada parada: la cascada del etiquetado.

    retraso(parada) = t_paso_observado − t_llegada_programada

La EMT no publica ninguno de los dos términos. Este módulo los reconstruye a
partir de la salida de `tracking.rastrear` y de una versión del GTFS
(`gtfs.Horario`), en cinco pasos:

1. **Día de servicio y feed.** Cada trayectoria pertenece al día de servicio de
   su primera posición, o al anterior si empieza antes de las `HORA_CORTE` h
   locales: el GTFS escribe la madrugada como 25:10. El feed es el que manda ese
   día (`gtfs.elegir_horario`).
2. **Viajes.** Una trayectoria no es un viaje: contiene la espera en cabecera, a
   veces más de un recorrido. Se corta donde la abscisa retrocede más de
   `retroceso_nuevo_viaje_m`, y se descartan los tramos cortos.
3. **Trazado por viaje.** Los candidatos son los trazados de la línea sobre los
   que el tramo AVANZA (`mapmatching.puntuar_candidatos`). Las variantes de un
   mismo trayecto (la 24, la 73) se deciden aquí, viaje a viaje, y no por grupo:
   la 73 se separa un kilómetro en mitad del recorrido (bitácora 022).
4. **Paso por parada.** Las paradas se proyectan sobre el trazado EN ORDEN de
   `stop_sequence`; el paso se interpola sobre el máximo acumulado de la
   abscisa —un bus en servicio no desanda la ruta—, a la SALIDA de la parada, y
   nunca a través de un hueco de más de `max_hueco_cruce_s` ni de un tramo fuera
   de ruta. `shape_dist_traveled` no se usa: es el horario reescalado (trampa
   010).
5. **Viaje programado.** Entre los viajes activos de esos trazados, el que
   programa el paso por las primeras `paradas_referencia` paradas más cerca de
   lo observado. Se exige que el segundo mejor quede al menos `margen_min_s`
   más lejos: en punta, con intervalos de 4 min, un bus a medio intervalo de su
   horario es igual de compatible con dos viajes, y asignarlo daría un retraso
   falso con aspecto de bueno. Un viaje programado se asigna a un solo tramo.

Sesgo que queda y hay que declarar: un bus que va más de medio intervalo fuera
de su horario se asigna al viaje contiguo y su retraso sale con el signo y la
magnitud equivocados, sin que nada lo delate. El margen sólo descarta los que
quedan cerca de la mitad.

Todo se une por el índice de las filas o por identificador, NUNCA por posición:
`rastrear` reordena y reinicia el índice, y una columna pegada por posición se
cruza entre filas sin error (bitácora 023).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from project.config import settings
from project.gtfs import Horario, Trazado, a_metros, elegir_horario
from project.mapmatching import FUERA_DE_RUTA_M, emparejar, puntuar_candidatos

# Antes de esta hora local, una trayectoria es del día de servicio anterior. El
# feed de la EMT llega hasta 28:03 (docs/09_gtfs_emt.md): los pocos viajes que
# empiezan entre las 04:00 y las 04:03 quedan sin asignar, y se cuentan.
HORA_CORTE = 4


@dataclass(frozen=True)
class Parametros:
    """Los umbrales del etiquetado. Salen de `params.yaml → prepare`."""

    min_posiciones_viaje: int = 10
    min_fraccion_recorrido: float = 0.3
    retroceso_nuevo_viaje_m: float = 500.0
    max_hueco_cruce_s: float = 120.0
    margen_cruce_m: float = 15.0
    paradas_referencia: int = 3
    max_desfase_s: float = 1200.0
    margen_min_s: float = 120.0
    min_avance: float = 0.8
    # Días de servicio [desde, hasta] que no se etiquetan porque ningún horario
    # publicado describe lo que circuló (bitácora 024). Se cuentan como
    # `excluido`, no desaparecen.
    excluir_fechas: tuple[tuple[str, str], ...] = ()

    def excluido(self, dia: date) -> bool:
        return any(
            date.fromisoformat(a) <= dia <= date.fromisoformat(b)
            for a, b in self.excluir_fechas
        )


@dataclass
class Resultado:
    pasos: pd.DataFrame
    viajes: pd.DataFrame
    posiciones: pd.DataFrame
    descartadas_sin_trayecto: int = 0
    contadores: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Geometría y tiempo
# --------------------------------------------------------------------------- #
def abscisas_paradas(
    t: Trazado, lat: np.ndarray, lon: np.ndarray, tolerancia_m: float = 30.0
) -> np.ndarray:
    """Abscisa de cada parada sobre el trazado, creciente con `stop_sequence`.

    Al punto más cercano no vale: en un recorrido circular o de ida y vuelta por
    la misma calle, una parada del final está junto a la salida y caería en s≈0.
    Cada parada se proyecta sobre la parte del trazado que queda por delante de
    la anterior (con `tolerancia_m` de holgura para el ruido).
    """
    x, y = a_metros(lat, lon)
    ax, ay = t.x[:-1], t.y[:-1]
    dx, dy = np.diff(t.x), np.diff(t.y)
    l2 = dx * dx + dy * dy
    l2 = np.where(l2 > 0, l2, 1.0)
    largo = np.sqrt(l2)
    out = np.empty(len(x))
    previa = -np.inf
    for i, (xi, yi) in enumerate(zip(x, y)):
        u = np.clip(((xi - ax) * dx + (yi - ay) * dy) / l2, 0.0, 1.0)
        d = np.hypot(xi - (ax + u * dx), yi - (ay + u * dy))
        s = t.acum[:-1] + u * largo
        d = np.where(s >= previa - tolerancia_m, d, np.inf)
        k = int(np.argmin(d))
        previa = s[k] if not np.isfinite(previa) else max(s[k], previa)
        out[i] = previa
    return out


def cruces(
    t: np.ndarray,
    s: np.ndarray,
    fiable: np.ndarray,
    s_paradas: np.ndarray,
    max_hueco_s: float,
    margen_m: float,
    s_fin: float = np.inf,
) -> np.ndarray:
    """Instante de paso por cada parada, o NaN si no se puede afirmar.

    Se toma la SALIDA de la parada: el primer momento en que el máximo acumulado
    de la abscisa supera la parada en `margen_m` (el ruido de un bus detenido no
    la cruza), llevado hacia atrás hasta la parada con la velocidad del tramo, o
    con la del siguiente si es mayor. Así, un bus que espera en cabecera sale
    cuando arranca, no cuando llega; con la velocidad del tramo que contiene la
    espera, la salida se adelantaría hasta 30 s.

    La parada terminal no se puede abandonar: la abscisa no pasa de `s_fin`, la
    longitud del trazado. Para ella se toma la LLEGADA, extrapolando hacia
    delante desde la última posición en marcha.

    NaN si el bus ya estaba más allá al aparecer (no se inventa la parada), si no
    llega a ella, o si las dos posiciones que la encierran distan más de
    `max_hueco_s`: un hueco de sondeos o un tramo fuera de ruta.
    """
    out = np.full(len(s_paradas), np.nan)
    m = fiable & np.isfinite(s) & np.isfinite(t)
    t, s = t[m], s[m]
    if len(t) < 2:
        return out
    orden = np.argsort(t, kind="stable")
    t, s = t[orden], s[orden]
    acc = np.maximum.accumulate(s)
    for i, sp in enumerate(s_paradas):
        if sp + margen_m >= s_fin:
            out[i] = _llegada(t, acc, sp, margen_m, max_hueco_s)
            continue
        k1 = int(np.searchsorted(acc, sp + margen_m, side="right"))
        if k1 == 0 or k1 >= len(acc):
            continue
        k0 = k1 - 1
        dt = t[k1] - t[k0]
        if dt > max_hueco_s or dt <= 0:
            continue
        v = (acc[k1] - acc[k0]) / dt
        if k1 + 1 < len(acc):
            dt2 = t[k1 + 1] - t[k1]
            if 0 < dt2 <= max_hueco_s:
                v = max(v, (acc[k1 + 1] - acc[k1]) / dt2)
        if v <= 0:
            continue
        out[i] = max(t[k1] - (acc[k1] - sp) / v, t[k0])
    return out


def _llegada(
    t: np.ndarray, acc: np.ndarray, sp: float, margen_m: float, max_hueco_s: float
) -> float:
    """Llegada a una parada que no se puede rebasar (la del final del trazado)."""
    k1 = int(np.searchsorted(acc, sp - margen_m, side="right"))
    if k1 == 0 or k1 >= len(acc):
        return np.nan
    k0 = k1 - 1
    dt = t[k1] - t[k0]
    if dt > max_hueco_s or dt <= 0:
        return np.nan
    v = (acc[k1] - acc[k0]) / dt
    if k0 >= 1:
        dt0 = t[k0] - t[k0 - 1]
        if 0 < dt0 <= max_hueco_s:
            v = max(v, (acc[k0] - acc[k0 - 1]) / dt0)
    if v <= 0:
        return np.nan
    return float(min(t[k0] + (sp - acc[k0]) / v, t[k1]))


def _medianoche(dia: date) -> pd.Timestamp:
    """Medianoche local del día de servicio.

    El GTFS la define como «mediodía menos 12 h», que difiere de la medianoche
    sólo los dos días de cambio de hora. Ninguno cae en la captura (el próximo es
    el 25/10), pero un etiquetado que los cruce tendría que tenerlo en cuenta.
    """
    return pd.Timestamp(datetime(dia.year, dia.month, dia.day), tz=settings.tz_local)


def _dia_de_servicio(primera_local: pd.Timestamp) -> date:
    d = primera_local.date()
    return d - timedelta(days=1) if primera_local.hour < HORA_CORTE else d


# --------------------------------------------------------------------------- #
# Horario por trazado, cacheado por feed
# --------------------------------------------------------------------------- #
@dataclass
class _Patron:
    """Viajes de un trazado que paran en la misma secuencia de paradas."""

    stop_ids: np.ndarray
    stop_sequence: np.ndarray  # la numeración del feed, no la posición
    s_paradas: np.ndarray
    trips: np.ndarray
    service: np.ndarray
    prog: np.ndarray  # viajes × paradas, segundos del día de servicio


class _Programacion:
    def __init__(self, h: Horario) -> None:
        self.h = h
        self._cache: dict[str, list[_Patron]] = {}

    def patrones(self, shape_id: str) -> list[_Patron]:
        if shape_id in self._cache:
            return self._cache[shape_id]
        h = self.h
        vj = h.viajes[h.viajes["shape_id"] == shape_id].set_index("trip_id")
        pv = h.paradas_de_viaje[h.paradas_de_viaje["trip_id"].isin(vj.index)]
        trazado = h.trazado(shape_id)
        patrones = []
        por_viaje = pv.groupby("trip_id", sort=True).agg(
            stops=("stop_id", tuple), t=("t_prog_s", list), seq=("stop_sequence", list)
        )
        for secuencia, grupo in por_viaje.groupby("stops", sort=False):
            trips_ids = grupo.index.to_numpy()
            stops = np.array(secuencia)
            p = h.paradas.loc[stops]
            patrones.append(
                _Patron(
                    stop_ids=stops,
                    stop_sequence=np.asarray(grupo["seq"].iloc[0]),
                    s_paradas=abscisas_paradas(
                        trazado, p["lat"].to_numpy(), p["lon"].to_numpy()
                    ),
                    trips=trips_ids,
                    service=vj.loc[trips_ids, "service_id"].to_numpy(),
                    prog=np.array(grupo["t"].tolist(), dtype=float),
                )
            )
        self._cache[shape_id] = patrones
        return patrones


# --------------------------------------------------------------------------- #
# La cascada
# --------------------------------------------------------------------------- #
def _segmentar(s: np.ndarray, fiable: np.ndarray, retroceso_m: float) -> np.ndarray:
    """Número de viaje de cada fila de UNA trayectoria ordenada en el tiempo.

    Se abre viaje nuevo cuando la abscisa fiable cae más de `retroceso_m` por
    debajo del máximo alcanzado: el bus ha vuelto a cabecera. Las filas no
    fiables heredan el viaje de la fila fiable anterior.
    """
    viaje = np.zeros(len(s), dtype=int)
    k, maximo = 0, -np.inf
    for i in range(len(s)):
        if fiable[i]:
            if s[i] < maximo - retroceso_m:
                k += 1
                maximo = -np.inf
            maximo = max(maximo, s[i])
        viaje[i] = k
    return viaje


def _asignar_tramo(
    g: pd.DataFrame,
    t_s: np.ndarray,
    trazados: list[Trazado],
    prog: _Programacion,
    activos: set[str],
    p: Parametros,
) -> tuple[dict, pd.DataFrame | None]:
    """Mejor viaje programado para un tramo observado, con su margen y sus pasos."""
    x, y = a_metros(g["lat"].to_numpy(), g["lon"].to_numpy())
    cand = puntuar_candidatos(g, x, y, trazados)
    mejor_cob = max((c["cobertura"] for c in cand), default=0.0)
    aptos = [
        c
        for c in cand
        if mejor_cob > 0
        and c["cobertura"] >= 0.5 * mejor_cob
        and not np.isnan(c["avanza"])
        and c["avanza"] >= p.min_avance
    ]
    if not aptos:
        return {"motivo": "sin_sentido"}, None

    opciones = []  # (coste, desfase, trip_id, shape_id, patron, tc)
    for c in aptos:
        pr = c["proyeccion"]
        fiable = (pr["dist_m"] <= FUERA_DE_RUTA_M) & ~pr["ambigua"]
        sid = c["trazado"].shape_id
        for pat in prog.patrones(sid):
            vivos = np.isin(pat.service, list(activos))
            if not vivos.any():
                continue
            tc = cruces(
                t_s,
                pr["abscisa_m"],
                fiable,
                pat.s_paradas,
                p.max_hueco_cruce_s,
                p.margen_cruce_m,
                s_fin=c["trazado"].largo,
            )
            ref = np.flatnonzero(np.isfinite(tc))[: p.paradas_referencia]
            if len(ref) == 0:
                continue
            desf = np.nanmedian(tc[ref][None, :] - pat.prog[vivos][:, ref], axis=1)
            for trip, d in zip(pat.trips[vivos], desf):
                if np.isfinite(d):
                    opciones.append((abs(d), d, trip, sid, pat, tc))
    if not opciones:
        return {"motivo": "sin_candidato"}, None

    opciones.sort(key=lambda o: o[0])
    coste, desfase, trip, sid, pat, tc = opciones[0]
    margen = opciones[1][0] - coste if len(opciones) > 1 else np.inf
    info = {
        "trip_id": trip,
        "shape_id": sid,
        "coste_s": coste,
        "desfase_s": desfase,
        "margen_s": margen,
    }
    if coste > p.max_desfase_s:
        return {**info, "motivo": "desfase"}, None
    if margen < p.margen_min_s:
        return {**info, "motivo": "margen"}, None
    fila = int(np.flatnonzero(pat.trips == trip)[0])
    ok = np.isfinite(tc)
    pasos = pd.DataFrame(
        {
            "stop_id": pat.stop_ids[ok],
            "stop_sequence": pat.stop_sequence[ok],
            "abscisa_parada_m": pat.s_paradas[ok],
            "t_obs_s": tc[ok],
            "t_prog_s": pat.prog[fila, ok],
        }
    )
    pasos["retraso_s"] = pasos["t_obs_s"] - pasos["t_prog_s"]
    return {**info, "motivo": "asignado"}, pasos


def etiquetar(pos: pd.DataFrame, horarios: list[Horario], p: Parametros) -> Resultado:
    """Pasos por parada con su retraso, a partir de la salida de `rastrear`.

    `pos` no debe traer filas sin `trayecto`: `prepare.etiquetar_dia` las
    descarta y las cuenta antes de rastrear.
    """
    pos = pos.copy()
    pos["linea"] = pos["linea"].astype(str)
    local = pos["ts_utc"].dt.tz_convert(settings.tz_local)
    primera = local.groupby(pos["vehicle_id"]).transform("min")
    pos["fecha_servicio"] = [_dia_de_servicio(v) for v in primera]

    partes, filas_viaje, filas_pasos = [], [], []
    programaciones: dict[str, _Programacion] = {}
    for dia, sub in pos.groupby("fecha_servicio", sort=True):
        if p.excluido(dia):
            partes.append(sub.assign(fiable=False, viaje_id=pd.NA, feed_version=pd.NA))
            for vid, g in sub.groupby("vehicle_id", sort=False):
                filas_viaje.append(
                    {
                        "viaje_id": f"{vid}_{dia:%Y%m%d}_x",
                        "vehicle_id": vid,
                        "fecha_servicio": dia,
                        "linea": g["linea"].iloc[0],
                        "trayecto": g["trayecto"].iloc[0],
                        "posiciones": len(g),
                        "t_inicio": g["ts_utc"].min(),
                        "t_fin": g["ts_utc"].max(),
                        "motivo": "excluido",
                    }
                )
            continue
        h, dentro = elegir_horario(horarios, dia)
        if h is None:
            partes.append(sub.assign(fiable=False, viaje_id=pd.NA, feed_version=pd.NA))
            continue
        prog = programaciones.setdefault(h.version, _Programacion(h))
        activos = h.servicios(dia)
        casada = emparejar(sub, h.trazados)
        casada["fiable"] = (
            casada["shape_id"].notna()
            & ~casada["fuera_de_ruta"].fillna(True).astype(bool)
            & ~casada["ambigua"].fillna(True).astype(bool)
        )
        casada["viaje_id"] = pd.Series(pd.NA, index=casada.index, dtype="object")
        casada["feed_version"] = h.version
        medianoche = _medianoche(dia)
        for vid, g in casada.sort_values(
            ["vehicle_id", "ts_utc"], kind="stable"
        ).groupby("vehicle_id", sort=False):
            s = g["abscisa_m"].to_numpy(dtype=float)
            fiable = g["fiable"].to_numpy(dtype=bool)
            tramo = _segmentar(s, fiable, p.retroceso_nuevo_viaje_m)
            for k in np.unique(tramo):
                gg = g[tramo == k]
                viaje_id = f"{vid}_{dia:%Y%m%d}_{k}"
                casada.loc[gg.index, "viaje_id"] = viaje_id
                base = {
                    "viaje_id": viaje_id,
                    "vehicle_id": vid,
                    "fecha_servicio": dia,
                    "linea": gg["linea"].iloc[0],
                    "trayecto": gg["trayecto"].iloc[0],
                    "feed_version": h.version,
                    "fuera_de_vigencia": not dentro,
                    "posiciones": len(gg),
                    "t_inicio": gg["ts_utc"].min(),
                    "t_fin": gg["ts_utc"].max(),
                }
                fs = gg["fiable"].to_numpy(dtype=bool)
                trazados = h.trazados.get(gg["linea"].iloc[0], [])
                if not trazados:
                    filas_viaje.append({**base, "motivo": "sin_trazado"})
                    continue
                largo = max(t.largo for t in trazados)
                recorrido = np.ptp(gg["abscisa_m"].to_numpy()[fs]) if fs.any() else 0.0
                if (
                    fs.sum() < p.min_posiciones_viaje
                    or recorrido < p.min_fraccion_recorrido * largo
                ):
                    filas_viaje.append({**base, "motivo": "corto"})
                    continue
                t_s = (gg["ts_utc"] - medianoche).dt.total_seconds().to_numpy()
                info, pasos = _asignar_tramo(gg, t_s, trazados, prog, activos, p)
                filas_viaje.append({**base, **info})
                if pasos is not None:
                    filas_pasos.append(
                        pasos.assign(
                            **{
                                c: base[c]
                                for c in (
                                    "viaje_id",
                                    "vehicle_id",
                                    "fecha_servicio",
                                    "linea",
                                    "trayecto",
                                    "feed_version",
                                    "fuera_de_vigencia",
                                )
                            },
                            trip_id=info["trip_id"],
                            shape_id=info["shape_id"],
                            desfase_s=info["desfase_s"],
                            margen_s=info["margen_s"],
                            coste_s=info["coste_s"],
                        )
                    )
        partes.append(casada)

    viajes = pd.DataFrame(filas_viaje)
    pasos = (
        pd.concat(filas_pasos, ignore_index=True) if filas_pasos else _pasos_vacios()
    )

    # Un viaje programado, un tramo observado: si dos lo reclaman, se lo queda el
    # que menos se desvía y el otro no se etiqueta.
    if len(viajes) and (viajes["motivo"] == "asignado").any():
        asig = viajes[viajes["motivo"] == "asignado"].sort_values(
            "coste_s", kind="stable"
        )
        repetido = asig.duplicated(["fecha_servicio", "trip_id"], keep="first")
        perdedores = set(asig.loc[repetido, "viaje_id"])
        viajes.loc[viajes["viaje_id"].isin(perdedores), "motivo"] = "conflicto"
        pasos = pasos[~pasos["viaje_id"].isin(perdedores)].reset_index(drop=True)

    if len(pasos):
        medianoche = pd.Series(
            [_medianoche(d) for d in pasos["fecha_servicio"]], index=pasos.index
        )
        pasos["t_obs_utc"] = (
            medianoche + pd.to_timedelta(pasos["t_obs_s"], unit="s")
        ).dt.tz_convert("UTC")

    posiciones = pd.concat(partes).sort_index() if partes else pos
    posiciones = _estado(posiciones, viajes, pasos)
    fuera = posiciones["fecha_servicio"].map(p.excluido).astype(bool)
    posiciones.loc[fuera, "estado"] = "excluido"
    return Resultado(pasos=pasos, viajes=viajes, posiciones=posiciones)


def _estado(
    pos: pd.DataFrame, viajes: pd.DataFrame, pasos: pd.DataFrame
) -> pd.DataFrame:
    """fuera_de_ruta · sin_viaje · regulacion (antes de salir o tras llegar) · servicio."""
    pos = pos.copy()
    estado = np.where(
        pos["fiable"].fillna(False).astype(bool), "sin_viaje", "fuera_de_ruta"
    )
    pos["estado"] = estado
    if len(pasos):
        franja = pasos.groupby("viaje_id")["t_obs_utc"].agg(["min", "max"])
        v = pos["viaje_id"].map(franja["min"])
        w = pos["viaje_id"].map(franja["max"])
        en_viaje = v.notna() & (pos["estado"] == "sin_viaje")
        dentro = en_viaje & (pos["ts_utc"] >= v) & (pos["ts_utc"] <= w)
        pos.loc[en_viaje, "estado"] = "regulacion"
        pos.loc[dentro, "estado"] = "servicio"
    return pos


def _pasos_vacios() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "stop_id",
            "stop_sequence",
            "abscisa_parada_m",
            "t_obs_s",
            "t_prog_s",
            "retraso_s",
            "viaje_id",
            "vehicle_id",
            "fecha_servicio",
            "linea",
            "trayecto",
            "feed_version",
            "fuera_de_vigencia",
            "trip_id",
            "shape_id",
            "desfase_s",
            "margen_s",
            "coste_s",
            "t_obs_utc",
        ]
    )
