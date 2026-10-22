"""Las pruebas del camino de la ingesta, medidas sobre el crudo. Solo lectura.

Cada función mide algo que una ficha ya contó en prosa, para que la página lo
enseñe con el dato delante y el exportador lo coteje con la ficha. Nada del
pipeline importa de aquí.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

from project.analysis.medir_completitud import huecos, instantes
from project.ingest.sources import parse_emt, read_raw

UNA_HORA = pd.Timedelta(hours=1)
CONVENCION = {"LOCAL_NAIVE": "hora local", "YA_EN_UTC": "UTC"}


def _crudo_emt(raw: Path, dia: str) -> Path:
    return raw / "source=emt_buses" / f"date={dia}" / "payloads.ndjson.gz"


def completitud(
    raw: Path, fuente: str, desde: str, hasta: str
) -> tuple[pd.Series, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    """Sondeos por día UTC de `desde` a `hasta` y huecos de más de una hora.

    Un día sin directorio es un día sin captura, no un día que no existe: vale 0.
    Si desapareciera de la serie, el hueco del 10-14/09 no se vería (bitácora 021).
    """
    ts = instantes(raw, fuente, desde, hasta)
    dias = pd.date_range(desde, hasta, freq="D").strftime("%Y-%m-%d")
    por_dia = pd.Series(Counter(f"{t:%Y-%m-%d}" for t in ts), dtype="int64")
    return por_dia.reindex(dias, fill_value=0), huecos(ts, UNA_HORA)


def capturas(raw: Path, fuente: str, desde: str, hasta: str) -> list[pd.Timestamp]:
    """Cada respuesta que el colector guardó, dé filas o no: su latido.

    No es `instantes`, que cuenta sondeos (trampa 018). Para decir que el
    colector seguía vivo vale cualquier respuesta, también la de Renfe de
    madrugada, sin trenes de València, o con un tren sin `porAvanc`.
    """
    dias = pd.date_range(desde, hasta, freq="D").strftime("%Y-%m-%d")
    ficheros = [
        raw / f"source={fuente}" / f"date={d}" / "payloads.ndjson.gz" for d in dias
    ]
    return sorted(t for f in ficheros if f.exists() for t, _ in read_raw(f))


def dias_del_crudo(raw: Path) -> list[str]:
    """Los días con directorio de la EMT, en orden. Sin ninguno no hay foto."""
    dias = sorted(
        p.name.removeprefix("date=") for p in (raw / "source=emt_buses").glob("date=*")
    )
    if not dias:
        raise FileNotFoundError(
            f"no hay crudo de la EMT en {raw / 'source=emt_buses'}: "
            "trae los datos con `deploy_pi/pull_data.sh`"
        )
    return dias


def ultimo_dia_completo(raw: Path) -> str:
    """El día anterior al último del crudo de la EMT.

    El colector puede estar escribiendo el último: dibujarlo pinta una caída que
    no existe.
    """
    # ponytail: si la copia acabó justo a medianoche se pierde un día entero de
    # la serie; basta con traer el día siguiente antes de generar la foto.
    return str((pd.Timestamp(dias_del_crudo(raw)[-1]) - pd.Timedelta(days=1)).date())


def alternancia(raw: Path, desde: pd.Timestamp, hasta: pd.Timestamp) -> dict:
    """Convención horaria de cada sondeo de la EMT entre `desde` y `hasta` (trampa 002).

    Se cuenta por sondeo, no por captura: la EMT sirve a veces el mismo sondeo
    dos veces, con la otra convención, y esa repetición no es una alternancia.
    Los sondeos DUDOSA no entran en la cuenta.
    """
    vistos: set[int] = set()
    sondeos: list[dict] = []
    for dia in pd.date_range(desde.normalize(), hasta.normalize(), freq="D"):
        fichero = _crudo_emt(raw, f"{dia:%Y-%m-%d}")
        if not fichero.exists():
            continue
        for ts, payload in read_raw(fichero):
            if not desde <= ts <= hasta:
                continue
            df = parse_emt(payload, ts)
            if df.empty:
                continue
            sid = int(df["snapshot_id"].iloc[0])
            if sid in vistos:
                continue
            vistos.add(sid)
            fechas = [f["attributes"]["fecha"] for f in payload["features"]]
            sondeos.append(
                {
                    "ts": ts,
                    "conv": df["tz_convencion"].iloc[0],
                    "filas": len(df),
                    "fecha": pd.to_datetime(max(fechas), unit="ms", utc=True),
                }
            )
    s = [v for v in sondeos if v["conv"] in CONVENCION]
    cambios = [i for i in range(1, len(s)) if s[i]["conv"] != s[i - 1]["conv"]]
    filas: Counter = Counter()
    for v in s:
        filas[v["conv"]] += v["filas"]
    total = sum(filas.values())
    return {
        "sondeos": len(sondeos),
        "alternancias": len(cambios),
        "desplazadas": 100 * min(filas.values()) / total if len(filas) == 2 else 0.0,
        "par": (
            [_convencion(s[cambios[0] - 1]), _convencion(s[cambios[0]])]
            if cambios
            else []
        ),
    }


def _convencion(v: dict) -> dict:
    horas = round((v["fecha"] - v["ts"]) / UNA_HORA)
    return {
        "titulo": f"Sondeo de las {v['ts']:%H:%M:%S} UTC",
        "campos": {
            "capturado (UTC)": f"{v['ts']:%H:%M:%S}",
            "fecha publicada, leída como UTC": f"{v['fecha']:%H:%M:%S}",
            "diferencia": f"{horas:+d} h",
            "convención": CONVENCION[v["conv"]],
        },
    }


def gid_por_sondeo(raw: Path, dia: str) -> dict:
    """¿Comparten `gid` dos sondeos distintos seguidos? (trampa 001).

    Dos capturas del mismo sondeo sí lo comparten —el bloque a medias y el
    completo, trampa 011—, así que cada sondeo se compara con el anterior
    DISTINTO, el de otro gid mínimo.
    """
    previo, primero = None, None
    pares = comun = 0
    for ts, payload in read_raw(_crudo_emt(raw, dia)):
        filas = [f["attributes"] for f in payload.get("features") or []]
        if not filas:
            continue
        actual = {
            "ts": ts,
            "gid": {a["gid"] for a in filas},
            "linea": filas[0]["linea"],
        }
        if previo is not None and min(actual["gid"]) != min(previo["gid"]):
            pares += 1
            comun += bool(actual["gid"] & previo["gid"])
            primero = primero or (previo, actual)
        previo = actual
    if primero is None:
        raise ValueError(f"el {dia} no tiene dos sondeos distintos de la EMT")
    a, b = primero
    return {"pares": pares, "con_comun": comun, "par": [_gid(a, None), _gid(b, a)]}


def _gid(v: dict, anterior: dict | None) -> dict:
    en_comun = "—" if anterior is None else str(len(v["gid"] & anterior["gid"]))
    return {
        "titulo": f"Sondeo de las {v['ts']:%H:%M:%S} UTC",
        "campos": {
            "buses": str(len(v["gid"])),
            "gid": f"{min(v['gid'])} … {max(v['gid'])}",
            "primer bus": f"línea {v['linea']}",
            "gid en común con el anterior": en_comun,
        },
    }


def bloque_a_medias(raw: Path, dias: list[str]) -> dict:
    """La primera captura a medio reinsertar y su repetición completa (trampa 011).

    Mismo sondeo —mismo gid mínimo— y los gid de la primera son el prefijo de los
    de la segunda: la tabla se leyó a mitad de recarga.
    """
    for dia in dias:
        fichero = _crudo_emt(raw, dia)
        if not fichero.exists():
            continue
        previo = None
        for ts, payload in read_raw(fichero):
            gids = sorted(f["attributes"]["gid"] for f in payload.get("features") or [])
            if not gids:
                continue
            n = len(previo["gid"]) if previo else 0
            if previo and len(gids) > n and gids[:n] == previo["gid"]:
                actual = {"ts": ts, "gid": gids}
                return {
                    "filas": (n, len(gids)),
                    "par": [_bloque(previo), _bloque(actual)],
                }
            previo = {"ts": ts, "gid": gids}
    raise ValueError(f"ningún bloque a medias entre el {dias[0]} y el {dias[-1]}")


def _bloque(v: dict) -> dict:
    return {
        "titulo": f"Captura de las {v['ts']:%H:%M:%S} UTC",
        "campos": {
            "sondeo (gid mínimo)": str(v["gid"][0]),
            "filas": str(len(v["gid"])),
            "gid": f"{v['gid'][0]} … {v['gid'][-1]}",
        },
    }
