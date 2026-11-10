"""El ciclo en vivo: lo sabido, lo pendiente y los buses de una parada.

El núcleo (`separar`, `pendientes`, `candidatos`, `tabla`) es función pura sobre
los pasos etiquetados de HOY. El «ahora» del ciclo parte los pasos en sabidos
(su retraso ya había llegado, `t_disp_utc <= ahora`) y no sabidos, que no existen
para nadie (trampa 017). Cada viaje en curso completa lo que le falta con las
paradas que aún no ha pasado, y `features.construir` busca la parada objetivo de
cada bus por clave, igual que al entrenar. Ninguna variable del modelo se
calcula aquí.

`Vivo` es el ciclo entero: relee el crudo de hoy, etiqueta con las funciones del
pipeline solo las líneas de la parada (más el reloj de todas, trampa 022),
calcula cuándo se supo cada paso, predice con el clasificador ya cargado y
congela y verifica con el `Marcador`. Es lo único que `api/` ve de todo esto.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from project import features
from project.config import RAIZ, settings
from project.etiquetado import HORA_CORTE, paradas_del_viaje
from project.features import CLAVE_VIAJE, con_disponibilidad, instante_disponible
from project.gtfs import Horario, cargar_horario, elegir_horario, versiones
from project.ingest.reprocesar import elegir_capturas
from project.prepare import cargar_parametros, etiquetar_dia, ventana_servicio

CICLO_S = 40  # el resultado de una parada se guarda tanto
SIN_DATOS_S = 120  # sin sondeo bueno durante más, se avisa aunque no haya error

# (feed_version, shape_id, trip_id) -> salida de `etiquetado.paradas_del_viaje`.
ParadasDe = Callable[[str, str, str], pd.DataFrame]

# Constantes de un viaje: las pendientes las copian de su último paso sabido.
# Cualquier otra columna de `pasos` que no sea de horario queda nula.
COLUMNAS_DE_VIAJE = [
    *CLAVE_VIAJE,
    "vehicle_id",
    "linea",
    "trayecto",
    "feed_version",
    "fuera_de_vigencia",
    "trip_id",
    "shape_id",
    "desfase_s",
    "margen_s",
    "coste_s",
]


def separar(
    pasos: pd.DataFrame, ahora: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(sabidos, no_sabidos). Sabido: `t_disp_utc` no nulo y no posterior a `ahora`."""
    sabido = pasos["t_disp_utc"].notna() & (pasos["t_disp_utc"] <= ahora)
    return pasos[sabido], pasos[~sabido]


def pendientes(sabidos: pd.DataFrame, paradas_de: ParadasDe) -> pd.DataFrame:
    """Las paradas que cada viaje con algún paso sabido aún no ha pasado.

    Una fila por parada con `stop_sequence` mayor que la del último sabido, con
    las columnas de horario y las de viaje, `retraso_s` nulo y
    `t_obs_utc = t_disp_utc = FUTURO`: el contrato de `features.construir`.
    """
    ultimos = sabidos.sort_values("stop_sequence", kind="stable").groupby(
        CLAVE_VIAJE, sort=False
    )
    partes = []
    for _, u in ultimos.tail(1).iterrows():
        paradas = paradas_de(u["feed_version"], u["shape_id"], u["trip_id"])
        paradas = paradas[paradas["stop_sequence"] > u["stop_sequence"]]
        partes.append(
            paradas.assign(**{c: u[c] for c in COLUMNAS_DE_VIAJE if c in sabidos})
        )
    p = pd.concat(partes, ignore_index=True) if partes else sabidos.iloc[0:0]
    p = p.reindex(columns=sabidos.columns)
    # En ns, como los pasos de verdad: `FUTURO` suelto da resolución de segundos
    # y, concatenado con el historial y los sabidos, la columna queda en `object`.
    futuro = pd.Series(features.FUTURO, index=p.index, dtype="datetime64[ns, UTC]")
    p["t_obs_utc"] = futuro
    p["t_disp_utc"] = futuro
    return p


def candidatos(
    sabidos: pd.DataFrame,
    pend: pd.DataFrame,
    stop_id: str,
    horizontes: list[int],
    ahora: pd.Timestamp,
) -> pd.DataFrame:
    """Los buses que van a `stop_id`, con su horizonte `h` en posiciones del horario.

    `h` = `stop_sequence` de la parada − la del último paso sabido; si la parada
    sale más de una vez (ruta circular) cuenta la más cercana que aún no toca.
    Entran los de `1 <= h <= max(horizontes)`; `con_modelo` dice si hay modelo a
    esa distancia. `stop_sequence` es la del último sabido, la fila que se predice.

    Solo van «en camino» los que por horario aún no han llegado: lo que el
    horario tarda del último paso sabido a la parada, menos lo que ha pasado desde
    ese paso hasta `ahora`, es positivo. Es `horizonte_previsto_s > 0` de
    `features.poblacion`, con el tiempo corriendo hasta `ahora`; sin esto, un
    viaje cuyo paso siguiente nunca se registra figuraría todo el día. Retraso y
    `t_disp_utc` son los de la fila del último paso, nulos incluidos.
    """
    ultimo = (
        sabidos.sort_values("stop_sequence", kind="stable")
        .groupby(CLAVE_VIAJE, sort=False)
        .tail(1)[
            [*CLAVE_VIAJE, "linea", "stop_sequence", "retraso_s", "t_disp_utc"]
            + ["t_obs_utc", "t_prog_s"]
        ]
        .rename(columns={"stop_sequence": "seq_ultimo", "t_prog_s": "prog_ultimo"})
    )
    destino = pend.loc[
        pend["stop_id"] == stop_id, [*CLAVE_VIAJE, "stop_sequence", "t_prog_s"]
    ].rename(columns={"t_prog_s": "prog_destino"})
    c = ultimo.merge(destino, on=CLAVE_VIAJE, how="inner", validate="one_to_many")
    c["h"] = c["stop_sequence"] - c["seq_ultimo"]
    desde_el_paso = (ahora - c["t_obs_utc"]).dt.total_seconds()
    quedan_s = (c["prog_destino"] - c["prog_ultimo"]) - desde_el_paso
    c = c[(c["h"] >= 1) & (c["h"] <= max(horizontes)) & (quedan_s > 0)]
    c = c.sort_values("h", kind="stable").drop_duplicates(CLAVE_VIAJE)
    c = c.assign(stop_sequence=c["seq_ultimo"], con_modelo=c["h"].isin(horizontes))
    return c[
        [
            *CLAVE_VIAJE,
            "linea",
            "stop_sequence",
            "h",
            "retraso_s",
            "t_disp_utc",
            "con_modelo",
        ]
    ].reset_index(drop=True)


def tabla(
    historial: pd.DataFrame,
    sabidos: pd.DataFrame,
    pend: pd.DataFrame,
    horizonte: int,
    cfg: dict,
) -> pd.DataFrame:
    """Las variables de la fila de cada bus: `construir` sobre historial + hoy.

    `cfg` es `params.yaml → features`. Sin tráfico: la capa 192 no aporta
    (ADR-024). Devuelve también las filas pendientes; quien llama elige la suya
    por clave.
    """
    pasos = pd.concat(
        [x for x in (historial, sabidos, pend) if not x.empty], ignore_index=True
    )
    return features.construir(
        pasos,
        objetivo=cfg["objetivo"],
        horizonte=horizonte,
        lags_min=tuple(cfg["lags_min"]),
        umbral_s=cfg["umbral_retraso_s"],
        ventanas_flota_min=features.ventanas_flota(cfg),
        soporte_min=cfg["soporte_min"],
        solo_con_objetivo=False,
    )


@dataclass(frozen=True)
class Prediccion:
    """Lo que el modelo y la regla simple dijeron de un bus en una parada."""

    probabilidad: float
    umbral: float
    llega_tarde: bool
    regla_llega_tarde: bool  # retraso_s del último paso sabido > umbral_retraso_s
    h: int
    t_utc: pd.Timestamp
    stop_sequence: int  # posición de la parada objetivo en el horario del viaje


class Marcador:
    """La primera predicción de cada (viaje, parada), congelada y calificada.

    Vive en memoria, por parada y luego por `clave = (fecha_servicio, viaje_id)`:
    cambiar de parada no borra lo congelado en las demás.
    """

    def __init__(self) -> None:
        self._por_parada: dict[str, dict[tuple, dict]] = {}

    def congelar(self, stop_id: str, clave: tuple, p: Prediccion) -> Prediccion:
        """Devuelve la primera predicción de `clave`; las siguientes no la sustituyen."""
        entradas = self._por_parada.setdefault(stop_id, {})
        return entradas.setdefault(clave, {"congelada": p, "resultado": None})[
            "congelada"
        ]

    def verificar(self, stop_id: str, sabidos: pd.DataFrame, umbral_s: float) -> None:
        """Califica las congeladas cuyo paso por `stop_id` ya es sabido.

        Se casa por (`fecha_servicio`, `viaje_id`, `stop_sequence`), no por
        `stop_id`: en una ruta circular la parada sale dos veces y el primer paso,
        ya sabido, no es el de la predicción. `sabidos` solo trae pasos con
        `t_disp_utc <= ahora` (`separar`).
        """
        en_parada = sabidos[sabidos["stop_id"] == stop_id]
        real = {
            (r.fecha_servicio, r.viaje_id, int(r.stop_sequence)): float(r.retraso_s)
            for r in en_parada.itertuples()
            if pd.notna(r.retraso_s)  # sabido pero sin etiquetar: no se califica
        }
        for clave, e in self._por_parada.get(stop_id, {}).items():
            if e["resultado"] is not None:
                continue
            c = e["congelada"]
            retraso = real.get((*clave, c.stop_sequence))
            if retraso is None:
                continue
            tarde = bool(retraso > umbral_s)
            e["resultado"] = {
                "retraso_real_s": retraso,
                "llego_tarde": tarde,
                "acierta_modelo": bool(c.llega_tarde == tarde),
                "acierta_regla": bool(c.regla_llega_tarde == tarde),
            }

    def entradas(self, stop_id: str) -> dict[tuple, dict]:
        """`{clave: {"congelada": Prediccion, "resultado": dict | None}}`."""
        return self._por_parada.get(stop_id, {})

    def resumen(self, stop_id: str) -> dict:
        """El marcador de la parada, sobre las predicciones ya verificadas."""
        hechos = [
            (e["congelada"], e["resultado"])
            for e in self.entradas(stop_id).values()
            if e["resultado"] is not None
        ]
        return {
            "verificados": len(hechos),
            "aciertos_modelo": sum(r["acierta_modelo"] for _, r in hechos),
            "aciertos_regla": sum(r["acierta_regla"] for _, r in hechos),
            "discrepan": sum(c.llega_tarde != c.regla_llega_tarde for c, _ in hechos),
        }


# --------------------------------------------------------------------------- #
# El ciclo completo
# --------------------------------------------------------------------------- #
class DemoNoDisponible(Exception):
    """La demo no puede responder ahora: la API la traduce a 503."""


class ParadaDesconocida(Exception):
    """Ninguna línea para en esa parada el día de hoy: la API la traduce a 404."""


# Lo que `paradas_de` devuelve de un viaje que el horario no conoce.
_SIN_PARADAS = pd.DataFrame(
    {
        "stop_id": pd.Series(dtype=object),
        "stop_sequence": pd.Series(dtype="int64"),
        "abscisa_parada_m": pd.Series(dtype="float64"),
        "t_prog_s": pd.Series(dtype="float64"),
    }
)
COLUMNAS_POSICION = ["snapshot_id", "linea", "trayecto", "lat", "lon", "ts_utc"]
RELOJ = "__reloj__"  # la línea de la fila fantasma: no está en ningún GTFS


def dia_de_servicio(ahora: pd.Timestamp) -> date:
    """La fecha local menos `HORA_CORTE` h, como `etiquetado._dia_de_servicio`."""
    local = ahora.tz_convert(settings.tz_local).tz_localize(None)
    return (local - pd.Timedelta(hours=HORA_CORTE)).date()


def ficheros_del_dia(raw_emt: Path, ahora: pd.Timestamp) -> list[Path]:
    """Los `payloads.ndjson.gz` de las fechas UTC que cubre el día de servicio hasta
    `ahora`. Antes de las 04:00 locales (o, en verano, tras las 02:00 UTC) son dos
    fechas, no una."""
    desde, fin = ventana_servicio(dia_de_servicio(ahora))
    fechas = pd.date_range(desde.normalize(), min(ahora, fin).normalize(), freq="D")
    ficheros = [raw_emt / f"date={f:%Y-%m-%d}" / "payloads.ndjson.gz" for f in fechas]
    return [f for f in ficheros if f.exists()]


def con_reloj_de_todas(frame: pd.DataFrame, lineas: list[str]) -> pd.DataFrame:
    """Las posiciones de `lineas` más una fila fantasma por sondeo que lleva el
    `ts_utc` máximo de todas las líneas, en una línea que no está en el GTFS.

    `rastrear` empareja dentro de (línea, trayecto), pero su reloj por sondeo es
    el máximo `ts_utc` de TODAS las filas del sondeo, y su contador de huecos,
    los sondeos que traen alguna fila: recortar líneas cambia los dos y, con
    ellos, algún empate casi exacto (trampa 022). La fantasma devuelve el
    etiquetado al del pipeline. Solo las filas con trayecto, que son las que
    `etiquetar_dia` pasa a `rastrear`.
    """
    con_trayecto = frame[frame["trayecto"].notna()].groupby("snapshot_id")
    reloj = con_trayecto["ts_utc"].max()
    # En la posición media del sondeo: `tracking._suavizar_intercambios` escala x
    # con la latitud media del frame, y un (0, 0) la desplazaría.
    centro = con_trayecto[["lat", "lon"]].mean().reindex(reloj.index)
    fantasma = pd.DataFrame(
        {
            "snapshot_id": reloj.index.to_numpy(),
            "linea": RELOJ,
            "trayecto": RELOJ,
            "lat": centro["lat"].to_numpy(),
            "lon": centro["lon"].to_numpy(),
            "ts_utc": reloj.reset_index(drop=True),
        }
    )
    recortado = frame[frame["linea"].isin(lineas)]
    return pd.concat(
        [recortado, fantasma.reindex(columns=recortado.columns)], ignore_index=True
    )


def provisionales(
    pasos: pd.DataFrame,
    posiciones: pd.DataFrame,
    ahora: pd.Timestamp,
    max_hueco_s: float,
) -> pd.Series:
    """Los pasos (con el índice de `pasos`) que todavía pueden cambiar de valor.

    `etiquetado.cruces` interpola el paso con k1, la primera posición fiable tras
    él, y corrige la velocidad con k1+1 si llega en `max_hueco_s`; `features.
    instante_disponible` fecha el paso con la llegada de esa k1+1. Si k1 es la
    última posición fiable del viaje, k1+1 puede estar por llegar y mover el paso
    y su `t_disp` (trampa 017): hasta que `ahora` rebase `ts_utc(k1) + max_hueco_s`
    no se sabe. Después, ninguna k1+1 futura entraría en el cálculo del pipeline.
    `posiciones` son las fiables con viaje, como las de `instante_disponible`.
    """
    po = posiciones.sort_values("ts_utc", kind="stable")[[*CLAVE_VIAJE, "ts_utc"]]
    po = po.assign(_penultima=po.groupby(CLAVE_VIAJE)["ts_utc"].shift(1))
    # La última de cada viaje, con la que la precede: si el paso es posterior a
    # ella, k1 es la última (o no hay otra).
    po = po.groupby(CLAVE_VIAJE).tail(1)
    po = po.rename(columns={"ts_utc": "_ultima"})
    r = pasos[[*CLAVE_VIAJE, "t_obs_utc"]].merge(po, on=CLAVE_VIAJE, how="left")
    k1_es_la_ultima = r["_penultima"].isna() | (r["t_obs_utc"] >= r["_penultima"])
    reciente = (ahora - r["_ultima"]).dt.total_seconds() <= max_hueco_s
    return pd.Series((k1_es_la_ultima & reciente).to_numpy(), index=pasos.index)


def _iso(t: pd.Timestamp | None) -> str | None:
    return None if t is None else t.tz_convert("UTC").isoformat()


def _nativo(columna: str, valor):
    """Un valor del vector tal como lo pide `model_service.fila`: NaN a None."""
    if pd.isna(valor):
        return None
    return str(valor) if columna == "linea" else float(valor)


def _cargar_historial() -> pd.DataFrame:
    """Los pasos etiquetados de todos los días ya procesados, con su `t_disp`.
    Sin carpeta de pasos (la de una demo sola) es un historial vacío, no un error."""
    ficheros = sorted((settings.interim_dir / "pasos").rglob("*.parquet"))
    if not ficheros:
        return pd.DataFrame()
    pasos = pd.concat((pd.read_parquet(f) for f in ficheros), ignore_index=True)
    return con_disponibilidad(
        pasos, pd.read_parquet(settings.interim_dir / "disponibilidad")
    )


class Vivo:
    """Lo que la demo carga una vez y el ciclo que corre por cada parada."""

    def __init__(
        self,
        servicio,
        horarios: list[Horario],
        historial: pd.DataFrame,
        cfg: dict,
        p,
        problema: str | None = None,
    ) -> None:
        self.servicio, self.horarios, self.historial = servicio, horarios, historial
        self.cfg, self.p, self.problema = cfg, p, problema
        # Los clasificadores cargados: horizonte -> columnas del artefacto.
        self._columnas = {
            m["horizonte_paradas"]: m["columnas"]
            for m in servicio.modelos()
            if m["modelo"] == "clasificador"
        }
        self._por_version = {h.version: h for h in horarios}
        self._lineas_de_parada: dict[tuple, dict[str, list[str]]] = {}
        self.marcador = Marcador()
        self.paradas_de: ParadasDe = self._paradas_de
        self._cache: dict[str, tuple[float, dict]] = {}
        # ponytail: un cerrojo global, uno por parada si hace falta.
        self._cerrojo = threading.Lock()

    @classmethod
    def desde_disco(cls, servicio) -> Vivo:
        """Nunca lanza: lo que falte (GTFS, historial, modelos) va a `problema`."""
        cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
        horarios, historial, p, problema = [], pd.DataFrame(), None, None
        try:
            if not any(m["modelo"] == "clasificador" for m in servicio.modelos()):
                raise DemoNoDisponible("sin modelo clasificador cargado")
            rutas = versiones(settings.gtfs_dir)
            if not rutas:
                raise DemoNoDisponible(f"no hay GTFS en {settings.gtfs_dir}")
            p = cargar_parametros()
            horarios = [cargar_horario(r) for r in rutas]
            historial = _cargar_historial()
        except DemoNoDisponible as e:
            problema = str(e)
        except Exception as e:  # noqa: BLE001
            problema = f"no se pudo cargar la demo: {type(e).__name__}: {e}"
        return cls(servicio, horarios, historial, cfg, p, problema)

    # --- el horario ------------------------------------------------------- #
    def _paradas_de(self, feed_version: str, shape_id: str, trip_id: str):
        try:
            return paradas_del_viaje(self._por_version[feed_version], shape_id, trip_id)
        except KeyError:  # un viaje que el horario no conoce no tumba la parada
            return _SIN_PARADAS

    def _horario_de(self, dia: date) -> Horario:
        horario, _ = elegir_horario(self.horarios, dia)
        if horario is None:
            raise DemoNoDisponible(
                f"No hay horario del GTFS que cubra el {dia:%d/%m/%Y}"
            )
        return horario

    def _lineas_por_parada(self, horario: Horario, dia: date) -> dict[str, list[str]]:
        clave = (horario.version, dia)
        if clave not in self._lineas_de_parada:
            viajes = horario.viajes[
                horario.viajes["service_id"].isin(horario.servicios(dia))
            ]
            pv = horario.paradas_de_viaje[["trip_id", "stop_id"]].merge(
                viajes[["trip_id", "linea"]], on="trip_id"
            )
            self._lineas_de_parada[clave] = (
                pv[["stop_id", "linea"]]
                .drop_duplicates()
                .groupby("stop_id")["linea"]
                .agg(sorted)
                .to_dict()
            )
        return self._lineas_de_parada[clave]

    def _comprobar(self) -> None:
        if self.problema:
            raise DemoNoDisponible(self.problema)

    def paradas(self) -> list[dict]:
        """Las paradas con servicio hoy, en el horario que manda hoy."""
        self._comprobar()
        dia = dia_de_servicio(pd.Timestamp.now(tz="UTC"))
        # Sin el cerrojo del ciclo: esperar a un ciclo de 40 s agotaba el timeout de
        # la UI. `_lineas_por_parada` es idempotente y guarda por clave: dos
        # llamadas a la vez recalculan lo mismo, sin daño.
        horario = self._horario_de(dia)
        lineas = self._lineas_por_parada(horario, dia)
        nombres = horario.paradas["nombre"].to_dict()
        return [
            {"stop_id": s, "nombre": str(nombres.get(s, "")), "lineas": ls}
            for s, ls in sorted(lineas.items())
        ]

    # --- el crudo de hoy -------------------------------------------------- #
    def _leer_hoy(self, ahora: pd.Timestamp):
        """(frame, llegadas, ultimo_ok, error): las posiciones de hoy hasta `ahora`.

        De cada sondeo, la captura con más filas (`elegir_capturas`, trampa 011);
        un payload sin filas no es un sondeo (trampa 018). El frame lleva el
        filtro de `prepare.cargar_dia` y `llegadas` es de esa misma población.
        """
        desde, fin = ventana_servicio(dia_de_servicio(ahora))
        raw = settings.raw_dir / "source=emt_buses"
        c = elegir_capturas(
            ficheros_del_dia(raw, ahora), "emt_buses", tolerar_cola=True
        )
        # ponytail: con `ahora` en el pasado (solo el humo), una captura completada
        # tras `ahora` descarta el sondeo entero en vez de volver a la primera.
        dfs = [d for _, d in c.elegidos.values()]
        ultimo_ok = None
        if dfs:
            frame = pd.concat(dfs, ignore_index=True)
            frame = frame[frame["ts_ingest_utc"] <= ahora]
            ultimo_ok = frame["ts_ingest_utc"].max() if len(frame) else None
            frame = frame[
                frame["lat"].notna()
                & frame["lon"].notna()
                & (frame["ts_utc"] >= desde)
                & (frame["ts_utc"] < fin)
                & (frame["ts_utc"] <= ahora)
            ]
        else:
            frame = pd.DataFrame(columns=["snapshot_id", "ts_ingest_utc"])
        g = frame.groupby("snapshot_id")["ts_ingest_utc"].min()
        llegadas = pd.Series(pd.to_datetime(g, utc=True).to_numpy(), index=g.index)
        frame = frame.reindex(columns=COLUMNAS_POSICION)
        return frame, llegadas, ultimo_ok, self._error(c, ultimo_ok, ahora)

    @staticmethod
    def _error(c, ultimo_ok, ahora: pd.Timestamp) -> dict | None:
        if c.ultimo_error is not None and c.ultimo_error[0] <= ahora:
            t, mensaje = c.ultimo_error
            if ultimo_ok is None or t > ultimo_ok:
                return {"mensaje": mensaje, "desde_utc": _iso(t)}
        if ultimo_ok is None:
            return {
                "mensaje": "Sin datos de la EMT en el día de servicio de hoy",
                "desde_utc": _iso(ahora),
            }
        if (ahora - ultimo_ok).total_seconds() > SIN_DATOS_S:
            hora = ultimo_ok.tz_convert(settings.tz_local).strftime("%H:%M")
            return {
                "mensaje": f"Sin datos nuevos de la EMT desde {hora}",
                "desde_utc": _iso(ultimo_ok),
            }
        return None

    def _etiquetar(
        self, frame, llegadas, lineas: list[str], ahora: pd.Timestamp
    ) -> pd.DataFrame:
        """Los pasos de `lineas` con su `t_disp_utc`; nulo es un paso aún no sabido."""
        if frame.empty or not frame["linea"].isin(lineas).any():
            return pd.DataFrame()
        r = etiquetar_dia(con_reloj_de_todas(frame, lineas), self.horarios, self.p)
        pasos = r.pasos.reset_index(drop=True)
        if pasos.empty:
            return pasos
        pos = r.posiciones[r.posiciones["viaje_id"].notna() & r.posiciones["fiable"]]
        prep = self.cfg["prepare"]
        pasos["t_disp_utc"] = instante_disponible(
            pasos,
            pos,
            llegadas,
            max_hueco_s=prep["max_hueco_cruce_s"],
            paradas_referencia=prep["paradas_referencia"],
        )
        # Un paso cuyo k1 es la última posición del viaje aún puede cambiar: ni
        # él ni su retraso existen todavía (el pipeline, con el día entero, lo
        # fecha con k1+1). `separar` lo deja fuera.
        pasos.loc[
            provisionales(pasos, pos, ahora, prep["max_hueco_cruce_s"]), "t_disp_utc"
        ] = pd.NaT
        return pasos

    def _historial_de(
        self, horario: Horario, dia: date, lineas: list[str], ahora: pd.Timestamp
    ):
        """Lo que ya se sabía: días ANTERIORES al de `ahora`, con la versión del feed
        que manda hoy y solo los pasos con `t_disp_utc <= ahora`. El historial no
        pasa por `separar`: un paso nocturno del día de servicio anterior puede
        llegar después de las 04:00 (trampa 017)."""
        h = self.historial
        if h.empty:
            return h
        return h[
            (h["fecha_servicio"] < pd.Timestamp(dia))
            & (h["feed_version"] == horario.version)
            & h["linea"].isin(lineas)
            & (h["t_disp_utc"] <= ahora)
        ]

    # --- la parada -------------------------------------------------------- #
    def parada(self, stop_id: str, ahora: pd.Timestamp | None = None) -> dict:
        """Un ciclo: los buses que van a `stop_id` y qué dice de cada uno el modelo.

        Sin `ahora`, el de verdad y con el resultado guardado `CICLO_S` s. Con
        `ahora` (solo el humo, en el pasado) no hay caché.
        """
        self._comprobar()
        real = ahora is None
        if real:
            ahora = pd.Timestamp.now(tz="UTC")
        else:
            ahora = pd.Timestamp(ahora)
            ahora = ahora.tz_localize("UTC") if ahora.tzinfo is None else ahora
        with self._cerrojo:
            guardado = self._cache.get(stop_id)
            if real and guardado and time.monotonic() - guardado[0] < CICLO_S:
                return guardado[1]
            dia = dia_de_servicio(ahora)
            horario = self._horario_de(dia)
            lineas = self._lineas_por_parada(horario, dia).get(stop_id)
            if not lineas:
                raise ParadaDesconocida(stop_id)
            frame, llegadas, ultimo_ok, error = self._leer_hoy(ahora)
            resultado = self._resultado(
                stop_id,
                ahora,
                self._etiquetar(frame, llegadas, lineas, ahora),
                self._historial_de(horario, dia, lineas, ahora),
                ultimo_ok,
                error,
            )
            if real:
                self._cache[stop_id] = (time.monotonic(), resultado)
            return resultado

    def _predecir(self, sabidos, pend, hist, cand) -> dict[tuple, dict]:
        """P(más de 5 min tarde) de cada candidato con modelo: la fila de `construir`
        cuya clave es la del último paso sabido, con las columnas del artefacto.
        Un último paso sin `retraso_s` no se predice (`fila` lo rechaza)."""
        salida = {}
        clave = [*CLAVE_VIAJE, "stop_sequence"]
        for h, grupo in cand[cand["con_modelo"]].groupby("h"):
            h = int(h)
            t = tabla(hist, sabidos, pend, h, self.cfg["features"])
            filas = grupo[clave].merge(t, on=clave, how="inner", validate="one_to_one")
            for r in filas.to_dict("records"):
                if pd.isna(r["retraso_s"]):
                    continue
                vector = {c: _nativo(c, r[c]) for c in self._columnas[h]}
                salida[r["fecha_servicio"], r["viaje_id"]] = self.servicio.mas_de_5min(
                    vector, h
                )
        return salida

    def _resultado(
        self,
        stop_id: str,
        ahora: pd.Timestamp,
        pasos: pd.DataFrame,
        hist: pd.DataFrame,
        datos_hasta: pd.Timestamp | None = None,
        error: dict | None = None,
    ) -> dict:
        """Del etiquetado de hoy (con `t_disp_utc`) al dict de la parada."""
        umbral_s = self.cfg["features"]["umbral_retraso_s"]
        sabidos = separar(pasos, ahora)[0] if len(pasos) else pasos
        filas: list[dict] = []
        if not sabidos.empty:
            # La clave del marcador es la misma en `congelar` y en `verificar`
            # (que la saca de estas filas): una fecha de otro tipo no casaría
            # nunca y no daría error.
            sabidos = sabidos.assign(
                fecha_servicio=pd.to_datetime(sabidos["fecha_servicio"])
            )
            pend = pendientes(sabidos, self.paradas_de)
            cand = candidatos(sabidos, pend, stop_id, list(self._columnas), ahora)
            modelo = self._predecir(sabidos, pend, hist, cand)
            # El último paso sabido de cada viaje, tal cual, nulos incluidos:
            # `candidatos` también lo toma con `tail(1)`.
            ultimos = sabidos.sort_values("stop_sequence", kind="stable").groupby(
                CLAVE_VIAJE, sort=False
            )
            ultimo = {
                (u.fecha_servicio, u.viaje_id): u for u in ultimos.tail(1).itertuples()
            }
            claves = [(c.fecha_servicio, c.viaje_id) for c in cand.itertuples()]
            for clave, c in zip(claves, cand.itertuples()):
                m = modelo.get(clave)
                if m is not None:
                    self.marcador.congelar(
                        stop_id,
                        clave,
                        Prediccion(
                            probabilidad=float(m["probabilidad"]),
                            umbral=float(m["umbral"]),
                            llega_tarde=bool(m["llega_tarde"]),
                            regla_llega_tarde=bool(ultimo[clave].retraso_s > umbral_s),
                            h=int(c.h),
                            t_utc=ahora,
                            # La parada objetivo; `c.stop_sequence` es la del
                            # último sabido, la fila que se predice.
                            stop_sequence=int(c.stop_sequence + c.h),
                        ),
                    )
            self.marcador.verificar(stop_id, sabidos, umbral_s)
            entradas = self.marcador.entradas(stop_id)
            for clave, c in zip(claves, cand.itertuples()):
                filas.append(
                    _fila(
                        ultimo[clave],
                        int(c.h),
                        ahora,
                        umbral_s,
                        modelo.get(clave),
                        entradas.get(clave),
                    )
                )
            # Lo ya congelado sigue a la vista, aunque el bus haya pasado.
            for clave, e in entradas.items():
                if clave in claves or clave not in ultimo:
                    continue
                f = e["congelada"]
                dicho = {
                    "probabilidad": f.probabilidad,
                    "umbral": f.umbral,
                    "llega_tarde": f.llega_tarde,
                }
                filas.append(_fila(ultimo[clave], f.h, ahora, umbral_s, dicho, e))
        return {
            "stop_id": stop_id,
            "nombre": self._nombre(stop_id),
            "ahora_utc": _iso(ahora),
            "datos_hasta_utc": _iso(datos_hasta),
            "error": error,
            "filas": filas,
            "marcador": self.marcador.resumen(stop_id),
        }

    def _nombre(self, stop_id: str) -> str:
        for h in self.horarios:
            if stop_id in h.paradas.index:
                return str(h.paradas.loc[stop_id, "nombre"])
        return ""


def _fila(u, h: int, ahora: pd.Timestamp, umbral_s: float, m, entrada) -> dict:
    """Una fila de la tabla de la parada. `u` es el último paso sabido del viaje,
    `h` las paradas que le faltan, `m` lo que dice el modelo y `entrada` lo congelado."""
    sin_retraso = pd.isna(u.retraso_s)
    congelada = None if entrada is None else asdict(entrada["congelada"])
    if congelada is not None:
        congelada["t_utc"] = _iso(congelada["t_utc"])
    return {
        "linea": str(u.linea),
        "viaje_id": str(u.viaje_id),
        "paradas": int(h),
        "retraso_actual_s": None if sin_retraso else float(u.retraso_s),
        "edad_s": float((ahora - u.t_disp_utc).total_seconds()),
        "probabilidad": None if m is None else float(m["probabilidad"]),
        "umbral": None if m is None else float(m["umbral"]),
        "llega_tarde": None if m is None else bool(m["llega_tarde"]),
        "regla_llega_tarde": None if sin_retraso else bool(u.retraso_s > umbral_s),
        "congelada": congelada,
        "resultado": None if entrada is None else entrada["resultado"],
    }
