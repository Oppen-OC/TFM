"""Definición y parseo de las fuentes en tiempo real de València.

Todas las fuentes se normalizan a un DataFrame con una columna `ts_utc`
(instante real del dato, en UTC) y `ts_ingest_utc` (cuándo lo capturamos
nosotros). Esa separación es la que permite luego medir la latencia de la
fuente, y es imprescindible para no mentirle al modelo.

TRAMPA DOCUMENTADA (medida empíricamente el 15/08/2026):
El campo `fecha` de la capa de buses de la EMT viene en epoch-ms, pero está
construido a partir de la hora LOCAL de Madrid tratada como si fuera UTC.
Es decir, en agosto (CEST, UTC+2) el timestamp va 2 horas adelantado. En
invierno (CET, UTC+1) irá 1 hora. Hay que corregirlo con la zona horaria
real de cada fecha o la serie se te parte en el cambio de hora de octubre.
Lo mismo ocurre con `fechaActualizacion` de Renfe, que es un ISO naive local.
"""

from __future__ import annotations

import gzip
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

TZ_LOCAL = ZoneInfo("Europe/Madrid")

ARCGIS = "https://geoportal.valencia.es/server/rest/services"
EMT_LAYER = f"{ARCGIS}/EMT/Seguimiento_EMT/MapServer/384"
TRAFICO = f"{ARCGIS}/OPENDATA/Trafico/MapServer"
RENFE = "https://tiempo-real.renfe.com/renfe-visor/flota.json"

QUERY_ARGS = "where=1%3D1&outFields=*&outSR=4326&f=json"


# --------------------------------------------------------------------------- #
# Utilidades de tiempo
# --------------------------------------------------------------------------- #
def local_naive_epoch_to_utc(epoch_ms: float | None) -> pd.Timestamp | None:
    """Convierte un epoch-ms que en realidad codifica hora local naive a UTC real."""
    if epoch_ms is None or (isinstance(epoch_ms, float) and math.isnan(epoch_ms)):
        return None
    # El valor, leído como UTC, ES la hora de pared local.
    wall = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
    # Se reinterpreta esa hora de pared en Europe/Madrid y se pasa a UTC.
    return pd.Timestamp(wall.replace(tzinfo=TZ_LOCAL).astimezone(timezone.utc))


def local_naive_iso_to_utc(s: str | None) -> pd.Timestamp | None:
    if not s:
        return None
    wall = datetime.fromisoformat(s)
    return pd.Timestamp(wall.replace(tzinfo=TZ_LOCAL).astimezone(timezone.utc))


def now_utc() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


# Latencia plausible de una fuente que refresca cada ~30 s. Fuera de esta
# horquilla, la interpretación horaria elegida es la equivocada.
LAT_MIN_S, LAT_MAX_S = -180.0, 900.0


def resolver_convencion(
    epoch_ms: pd.Series, ts_ingest: pd.Timestamp, lat_max: float = LAT_MAX_S
) -> tuple[pd.Series, str]:
    """Decide, POR SNAPSHOT, si el timestamp viene en UTC o en local naive.

    Medido el 16/08/2026 sobre 12,5 h de captura real: el servicio de la EMT
    **alterna entre las dos convenciones de un sondeo al siguiente** (338
    cambios en 1.224 snapshots, con rachas de mediana 2). La explicación más
    probable es un balanceador con varios nodos detrás mal configurados: unos
    sellan en hora de Madrid y otros en UTC.

    Fijar la conversión a una de las dos deja el 20 % de los datos desplazados
    dos horas, lo que destruye cualquier etiqueta de retraso. La solución es
    no asumir: probar las dos interpretaciones y quedarse con la que produce
    una latencia plausible. Se autocalibra además en el cambio de hora.
    """
    crudo = pd.to_datetime(epoch_ms, unit="ms", utc=True)  # leído tal cual
    # Reinterpretar esa hora de pared en Europe/Madrid y volver a UTC.
    naive = crudo.dt.tz_localize(None)
    local = naive.dt.tz_localize(
        TZ_LOCAL, ambiguous=True, nonexistent="shift_forward"
    ).dt.tz_convert("UTC")

    med_utc = float((ts_ingest - crudo).dt.total_seconds().median())
    med_loc = float((ts_ingest - local).dt.total_seconds().median())

    ok_utc = LAT_MIN_S <= med_utc <= lat_max
    ok_loc = LAT_MIN_S <= med_loc <= lat_max

    if ok_loc and not ok_utc:
        return local, "LOCAL_NAIVE"
    if ok_utc and not ok_loc:
        return crudo, "YA_EN_UTC"
    if ok_utc and ok_loc:  # sólo si el desfase fuese 0
        return (
            (crudo, "YA_EN_UTC")
            if abs(med_utc) <= abs(med_loc)
            else (local, "LOCAL_NAIVE")
        )
    # Ninguna cuadra: dato rancio o reloj desajustado. Se marca y no se descarta.
    return (local, "DUDOSA") if abs(med_loc) < abs(med_utc) else (crudo, "DUDOSA")


# --------------------------------------------------------------------------- #
# Definición de fuentes
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Source:
    name: str
    url: str
    period_s: int
    notes: str
    parser: str
    layer_id: int | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    # Capas cuya geometría no cambia nunca: se descarga una vez a reference/ y
    # a partir de ahí se piden sin geometría. En la capa 192 eso es el 90 % del
    # payload, y era el 74 % del disco de toda la captura.
    geometria_estatica: bool = False

    @property
    def url_sin_geometria(self) -> str:
        if not self.geometria_estatica:
            return self.url
        return self.url.replace("&outSR=4326", "&outSR=4326&returnGeometry=false")


SOURCES: dict[str, Source] = {
    "emt_buses": Source(
        name="emt_buses",
        url=f"{EMT_LAYER}/query?{QUERY_ARGS}",
        period_s=30,
        notes="Posición GPS de la flota EMT. Refresco medido ~29 s. Sin id de vehículo.",
        parser="parse_emt",
        layer_id=384,
        tags=("tiempo_real", "nucleo"),
    ),
    "trafico_estado": Source(
        name="trafico_estado",
        url=f"{TRAFICO}/192/query?{QUERY_ARGS}",
        # 60 s era la cadencia inicial. Medido: en 2.033 sondeos sólo 8 tramos
        # cambiaron de estado. Muestrear cada 5 min basta de sobra para
        # documentar esa quietud y divide el volumen por cinco.
        period_s=300,
        notes="Estado de congestión por tramo (410 útiles). Sin timestamp propio. Prácticamente estático.",
        parser="parse_trafico_estado",
        layer_id=192,
        geometria_estatica=True,
        tags=("tiempo_real", "nucleo"),
    ),
    "trafico_intensidad": Source(
        name="trafico_intensidad",
        url=f"{TRAFICO}/188/query?{QUERY_ARGS}",
        # Medido: 1 solo cambio del agregado en 294 sondeos a lo largo de 42 h.
        period_s=900,
        notes="Intensidad por tramo (354 con lectura). lectura=-1 = sin dato. Prácticamente estática.",
        parser="parse_trafico_intensidad",
        layer_id=188,
        geometria_estatica=True,
        tags=("tiempo_real",),
    ),
    "valenbisi": Source(
        name="valenbisi",
        url=f"{TRAFICO}/228/query?{QUERY_ARGS}",
        period_s=300,
        notes="273 estaciones. La fuente sólo refresca cada ~10 min: no pollear a 30 s.",
        parser="parse_valenbisi",
        layer_id=228,
        tags=("tiempo_real",),
    ),
    "renfe_cercanias": Source(
        name="renfe_cercanias",
        url=RENFE,
        period_s=30,
        notes="Flota nacional; filtrar nucleo=='40' para València. Trae retrasoMin YA calculado.",
        parser="parse_renfe",
        tags=("tiempo_real", "etiqueta_gratis"),
    ),
}


# --------------------------------------------------------------------------- #
# Parsers  (payload crudo -> DataFrame normalizado)
# --------------------------------------------------------------------------- #
def _wkt_paths(paths: list) -> str:
    """Polilínea de ArcGIS -> WKT. Necesario para el join espacial punto-tramo."""
    partes = [
        ", ".join(f"{p[0]:.6f} {p[1]:.6f}" for p in path) for path in paths if path
    ]
    if not partes:
        return ""
    if len(partes) == 1:
        return f"LINESTRING ({partes[0]})"
    return "MULTILINESTRING (" + ", ".join(f"({p})" for p in partes) + ")"


def _solo_existentes(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df[[c for c in cols if c in df.columns]]


def _arcgis_rows(payload: dict) -> list[dict]:
    out = []
    for f in payload.get("features", []) or []:
        row = dict(f.get("attributes") or {})
        geom = f.get("geometry") or {}
        if "x" in geom:
            row["lon"], row["lat"] = geom["x"], geom["y"]
        elif "paths" in geom and geom["paths"]:
            path = geom["paths"][0]
            row["lon"], row["lat"] = path[0][0], path[0][1]
            row["n_vertices"] = sum(len(p) for p in geom["paths"])
            # La geometría de los tramos es ESTÁTICA: el colector la separa a un
            # fichero de referencia y no la repite en cada snapshot.
            row["geom_wkt"] = _wkt_paths(geom["paths"])
        out.append(row)
    return out


def parse_emt(payload: dict, ts_ingest: pd.Timestamp) -> pd.DataFrame:
    df = pd.DataFrame(_arcgis_rows(payload))
    if df.empty:
        return df
    df["ts_utc"], convencion = resolver_convencion(df["fecha"], ts_ingest)
    df["tz_convencion"] = convencion
    df["ts_ingest_utc"] = ts_ingest
    # gid NO identifica al vehículo: es un autoincrement de la tabla, que se
    # trunca y reinserta entera en cada refresco. Sí identifica el refresco.
    df["snapshot_id"] = int(df["gid"].min())
    df["latencia_s"] = (df["ts_ingest_utc"] - df["ts_utc"]).dt.total_seconds()
    return df[
        [
            "snapshot_id",
            "gid",
            "linea",
            "trayecto",
            "lat",
            "lon",
            "ts_utc",
            "ts_ingest_utc",
            "latencia_s",
            "tz_convencion",
        ]
    ]


def parse_trafico_estado(payload: dict, ts_ingest: pd.Timestamp) -> pd.DataFrame:
    df = pd.DataFrame(_arcgis_rows(payload))
    if df.empty:
        return df
    df["ts_ingest_utc"] = ts_ingest
    df["ts_utc"] = ts_ingest  # la capa no publica timestamp propio
    # Medido el 16/08: ~35 de las 446 filas por snapshot son huecos sin
    # idtramo, sin geometría y sin estado. No son tramos con estado
    # desconocido: no son tramos. Contarlos como nulos falsea el % de datos
    # que faltan.
    df = df[df["idtramo"].notna()]
    # Tras el primer sondeo se pide sin geometría: lat/lon/geom_wkt no vienen.
    return _solo_existentes(
        df,
        [
            "idtramo",
            "denominacion",
            "estado",
            "fiwareid",
            "lat",
            "lon",
            "n_vertices",
            "geom_wkt",
            "ts_utc",
            "ts_ingest_utc",
        ],
    )


def parse_trafico_intensidad(payload: dict, ts_ingest: pd.Timestamp) -> pd.DataFrame:
    df = pd.DataFrame(_arcgis_rows(payload))
    if df.empty:
        return df
    df["ts_ingest_utc"] = ts_ingest
    df["ts_utc"] = ts_ingest
    df["lectura"] = pd.to_numeric(df["lectura"], errors="coerce")
    df.loc[df["lectura"] < 0, "lectura"] = pd.NA  # -1 = sin dato
    df = df[df["idtramo"].notna()]  # filas hueco, ver capa 192
    return _solo_existentes(
        df,
        [
            "idtramo",
            "des_tramo",
            "lectura",
            "tipo_vehiculo",
            "fiwareid",
            "lat",
            "lon",
            "geom_wkt",
            "ts_utc",
            "ts_ingest_utc",
        ],
    )


def parse_valenbisi(payload: dict, ts_ingest: pd.Timestamp) -> pd.DataFrame:
    df = pd.DataFrame(_arcgis_rows(payload))
    if df.empty:
        return df
    # Valenbisi sólo refresca cada ~10 min: su latencia legítima llega a
    # varios cientos de segundos, así que la horquilla se ensancha.
    df["ts_utc"], _ = resolver_convencion(df["update_jcd"], ts_ingest, lat_max=2400)
    df["ts_ingest_utc"] = ts_ingest
    df["abierta"] = df["open"].eq("T")
    return df[
        [
            "number",
            "name",
            "address",
            "abierta",
            "available",
            "free",
            "total",
            "lat",
            "lon",
            "ts_utc",
            "ts_ingest_utc",
        ]
    ]


def parse_renfe(
    payload: dict, ts_ingest: pd.Timestamp, nucleo: str = "40"
) -> pd.DataFrame:
    # OJO: la raíz es un objeto {fechaActualizacion, trenes:[...]}, no un array.
    trenes = payload.get("trenes", []) if isinstance(payload, dict) else payload
    df = pd.DataFrame(trenes)
    if df.empty:
        return df
    if nucleo:
        df = df[df["nucleo"] == nucleo].copy()
    df["ts_utc"] = (
        local_naive_iso_to_utc(payload.get("fechaActualizacion"))
        if isinstance(payload, dict)
        else ts_ingest
    )
    df["ts_ingest_utc"] = ts_ingest
    df["retraso_min"] = pd.to_numeric(df["retrasoMin"], errors="coerce")
    df["eta_sig_est_utc"] = df["horaLlegadaSigEst"].map(local_naive_iso_to_utc)
    df = df.rename(columns={"latitud": "lat", "longitud": "lon"})
    return df[
        [
            "tripId",
            "codTren",
            "codLinea",
            "retraso_min",
            "codEstAct",
            "codEstSig",
            "eta_sig_est_utc",
            "codEstOrig",
            "codEstDest",
            "porAvanc",
            "via",
            "lat",
            "lon",
            "ts_utc",
            "ts_ingest_utc",
        ]
    ]


PARSERS = {
    "parse_emt": parse_emt,
    "parse_trafico_estado": parse_trafico_estado,
    "parse_trafico_intensidad": parse_trafico_intensidad,
    "parse_valenbisi": parse_valenbisi,
    "parse_renfe": parse_renfe,
}


def parse(source: str, payload: dict, ts_ingest: pd.Timestamp) -> pd.DataFrame:
    return PARSERS[SOURCES[source].parser](payload, ts_ingest)


# --------------------------------------------------------------------------- #
# Geodesia mínima (sin dependencias pesadas)
# --------------------------------------------------------------------------- #
def haversine_m(lat1, lon1, lat2, lon2):
    """Distancia en metros. Acepta escalares o arrays de numpy/pandas."""
    import numpy as np

    r = 6371008.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = p2 - p1
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


# --------------------------------------------------------------------------- #
# Persistencia cruda: NDJSON gzip, particionado por fuente y día
# --------------------------------------------------------------------------- #
def append_raw(root: Path, source: str, payload: dict, ts_ingest: pd.Timestamp) -> Path:
    """Guarda SIEMPRE el payload crudo. Si mañana descubres que parseabas mal,
    puedes reprocesar; lo que no puedes es volver a capturar el pasado."""
    day = ts_ingest.strftime("%Y-%m-%d")
    path = root / "raw" / f"source={source}" / f"date={day}" / "payloads.ndjson.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"ts_ingest_utc": ts_ingest.isoformat(), "payload": payload},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    with gzip.open(path, "at", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return path


def read_raw(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            yield pd.Timestamp(rec["ts_ingest_utc"]), rec["payload"]
