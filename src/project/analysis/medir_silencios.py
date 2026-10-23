"""¿Cuánto calla cada fuente sin estar caída? La base de `Source.silencio_max_s`.

    uv run python -m project.analysis.medir_silencios
    uv run python -m project.analysis.medir_silencios --data C:/Users/oppen/Code/TFM/data

Un sondeo bueno es el que mueve el `ultimo_ok` del colector: trae filas y su
clave es nueva. Se leen del curated, que `reprocesar` reconstruye del crudo con
el mismo `parse` y la misma `clave_sondeo`; de un sondeo repetido se queda la
captura más completa y no la primera, lo que mueve un instante como mucho un
periodo. Cada hueco entre dos sondeos buenos de más de 1,5 periodos y 30 s se
clasifica con el crudo que cae dentro:

    colector   las demás fuentes tampoco guardan nada durante más de 5 min y de
               la mitad del hueco: el proceso estaba parado o bloqueado
    error      la fuente devuelve `{"error": …}` (trampa 018) o pasa más de 1,5
               periodos y 30 s sin respuesta guardada: red, HTTP o el parser,
               que disparan el retroceso de `collect.sondear`
    legitimo   contesta a su cadencia, pero sin filas o con el sondeo repetido

Lo legítimo es lo que `collect --status` no debe dar por caído. Se saca su
máximo por fuente, la edad máxima de `ultimo_ok` por hora local, que es lo que
el diagnóstico compara con la tolerancia, y cuántos huecos de cada clase pasan
de ella: un legítimo que pasa es una falsa alarma (issue #1).
"""

from __future__ import annotations

import argparse
import gzip
import re
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from project.config import settings
from project.ingest.sources import SOURCES, TZ_LOCAL

# Solo el instante y el principio del payload: decodificar el JSON de Renfe, la
# flota nacional entera en cada línea, lo hace diez veces más lento.
LINEA = re.compile(r'^\{"ts_ingest_utc":"([^"]+)","payload":(.{0,10})')
SEG = np.timedelta64(1, "s")
HORA = pd.Timedelta(hours=1)


def crudo(raw: Path, fuente: str) -> pd.DataFrame:
    """Instante (UTC, sin zona) de cada payload guardado y si es un error."""
    filas = []
    for f in sorted((raw / f"source={fuente}").glob("date=*/payloads.ndjson.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for linea in fh:
                if m := LINEA.match(linea):
                    filas.append((m.group(1), m.group(2).startswith('{"error"')))
    df = pd.DataFrame(filas, columns=["ts", "error"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True, format="ISO8601").dt.tz_localize(None)
    return df.sort_values("ts", ignore_index=True)


def buenos(curated: Path, fuente: str) -> np.ndarray:
    """Instantes (UTC, sin zona) de los sondeos buenos, en orden."""
    t = duckdb.sql(
        f"""select distinct ts_ingest_utc t from read_parquet(
            '{curated.as_posix()}/source={fuente}/*/*.parquet', hive_partitioning=false)
            order by t"""
    ).df()["t"]
    return t.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()


def _max_silencio(t: np.ndarray, a: np.datetime64, b: np.datetime64) -> float:
    """Segundos del tramo más largo de (a, b) sin ningún instante de `t`."""
    dentro = t[(t > a) & (t < b)]
    return float(np.diff(np.concatenate([[a], dentro, [b]])).max() / SEG)


def clasificar(
    buenos: np.ndarray,
    propio: np.ndarray,
    errores: np.ndarray,
    otros: np.ndarray,
    periodo_s: int,
) -> pd.DataFrame:
    """Un hueco entre sondeos buenos por fila, con su clase (ver el módulo)."""
    corto = 1.5 * periodo_s + 30
    filas = []
    for a, b in zip(buenos[:-1], buenos[1:]):
        s = float((b - a) / SEG)
        if s <= corto:
            continue
        if _max_silencio(otros, a, b) > max(300, s / 2):
            clase = "colector"
        elif ((errores > a) & (errores < b)).any() or _max_silencio(
            propio, a, b
        ) > corto:
            clase = "error"
        else:
            clase = "legitimo"
        filas.append((a, b, s / 60, clase))
    df = pd.DataFrame(filas, columns=["desde", "hasta", "min", "clase"])
    for c in ("desde", "hasta"):
        df[c] = pd.to_datetime(df[c]).dt.tz_localize("UTC").dt.tz_convert(TZ_LOCAL)
    return df


def _tramos(desde: pd.Timestamp, hasta: pd.Timestamp):
    """(inicio, edad de `ultimo_ok` al final) de cada hora local del hueco.

    Dentro del hueco la edad en t es t - desde: en cada hora, la máxima es la
    del final de su tramo.
    """
    h = desde.floor("h")
    while h < hasta:
        yield h, (min(hasta, h + HORA) - desde).total_seconds()
        h += HORA


def edad_por_hora(huecos: pd.DataFrame) -> pd.Series:
    """Edad máxima de `ultimo_ok`, en minutos, en cada hora local."""
    filas = [
        (h.hour, s / 60)
        for g in huecos.itertuples()
        for h, s in _tramos(g.desde, g.hasta)
    ]
    return pd.DataFrame(filas, columns=["hora", "min"]).groupby("hora")["min"].max()


def avisa(desde: pd.Timestamp, hasta: pd.Timestamp, src) -> bool:
    """¿Habría dado `--status` la fuente por caída en algún momento del hueco?"""
    return any(s > src.silencio_tolerado(h) for h, s in _tramos(desde, hasta))


def franja(t: pd.Series) -> str:
    """La primera y la última hora del día de `t`, contadas desde el mediodía
    para que una noche no se parta en la medianoche."""
    m = (t.dt.hour * 60 + t.dt.minute + 720) % 1440
    return " a ".join(
        f"{(x + 720) % 1440 // 60:02d}:{x % 60:02d}" for x in (m.min(), m.max())
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=settings.data_root)
    a = p.parse_args()

    raw = {k: crudo(a.data / "raw", k) for k in SOURCES}
    for k, src in SOURCES.items():
        ok = buenos(a.data / "curated", k)
        otros = np.sort(
            np.concatenate([raw[o]["ts"].to_numpy() for o in raw if o != k])
        )
        h = clasificar(
            ok,
            raw[k]["ts"].to_numpy(),
            raw[k].loc[raw[k]["error"], "ts"].to_numpy(),
            otros,
            src.period_s,
        )
        print(
            f"\n{k}: {len(ok):,} sondeos buenos, {pd.Timestamp(ok[0]):%d/%m} -> "
            f"{pd.Timestamp(ok[-1]):%d/%m} UTC; cada {src.period_s} s, "
            f"tolera {src.silencio_max_s / 60:.0f} min"
        )
        for clase, x in h.groupby("clase"):
            peor = x.loc[x["min"].idxmax()]
            sobre = sum(avisa(g.desde, g.hasta, src) for g in x.itertuples())
            print(
                f"  {clase:9} {len(x):4} huecos, mediana {x['min'].median():6.1f} min, "
                f"máx {peor['min']:7.1f} min ({peor['desde']:%d/%m %H:%M} hora local); "
                f"{sobre} pasan de la tolerancia"
            )
        leg = h[h["clase"] == "legitimo"]
        if leg.empty:
            continue
        print("  legítimos más largos:")
        for g in leg.nlargest(5, "min").itertuples():
            print(
                f"    {g.desde:%d/%m %H:%M} -> {g.hasta:%d/%m %H:%M}  {g.min:6.1f} min"
            )
        largos = leg[leg["min"] > 120]
        if len(largos):
            print(
                f"  legítimos de más de 2 h: {len(largos)}; empiezan de "
                f"{franja(largos['desde'])} y acaban de {franja(largos['hasta'])}"
            )
        edad = edad_por_hora(leg)
        print(
            "  edad legítima máx por hora local (min): "
            + " ".join(f"{hora}h:{m:.0f}" for hora, m in edad.items())
        )


if __name__ == "__main__":
    main()
