"""¿Qué claves omite Renfe, y cuándo? La causa del issue #4 (trampa 019).

    uv run python -m project.analysis.medir_claves_renfe
    uv run python -m project.analysis.medir_claves_renfe --raw C:/Users/oppen/Code/TFM/data/raw

Renfe no manda a null la clave que no tiene valor: la omite del tren. Si ningún
tren de la flota la trae, `pd.DataFrame(trenes)` no tiene la columna, y hasta el
issue #4 `parse_renfe` lanzaba KeyError y `reprocesar` contaba un error. Aquí se
cuenta sobre el JSON crudo, sin pasar por el parser:

    claves     por clave, trenes sin ella y trenes con ella a null, en toda la
               flota y en el núcleo 40
    ausentes   payloads en que una clave falta en toda la flota, que son los
               que fallaban: hora local, trenes de la flota y del núcleo 40
    episodios  esos payloads, juntos si los separan menos de 30 min
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from project.config import settings
from project.ingest.sources import CLAVES_RENFE, TZ_LOCAL, read_raw

CLAVES = [*CLAVES_RENFE, "nucleo"]
HUECO = pd.Timedelta(minutes=30)


def contar(raw: Path, desde: str, hasta: str | None):
    trenes = Counter()  # es40 -> trenes
    sin, nulo = Counter(), Counter()  # (clave, es40) -> trenes
    ausentes = []
    n_payloads = 0
    for f in sorted((raw / "source=renfe_cercanias").glob("date=*/payloads.ndjson.gz")):
        dia = f.parent.name.removeprefix("date=")
        if dia < desde or (hasta and dia > hasta):
            continue
        for ts, p in read_raw(f):
            n_payloads += 1
            flota = (p.get("trenes") or []) if isinstance(p, dict) else p
            presentes, n40 = set(), 0
            for t in flota:
                es40 = t.get("nucleo") == "40"
                n40 += es40
                trenes[es40] += 1
                presentes.update(t)
                for k in CLAVES:
                    if k not in t:
                        sin[k, es40] += 1
                    elif t[k] is None:
                        nulo[k, es40] += 1
            ausentes += [
                (ts, k, len(flota), n40) for k in CLAVES if flota and k not in presentes
            ]
    df = pd.DataFrame(ausentes, columns=["ts", "clave", "flota", "n40"])
    df["local"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(TZ_LOCAL)
    return n_payloads, trenes, sin, nulo, df


def episodios(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("local", kind="stable")
    ep = (df["local"].diff() > HUECO).cumsum()
    return df.groupby(ep).agg(
        desde=("local", "min"),
        hasta=("local", "max"),
        payloads=("ts", "nunique"),
        flota=("flota", "max"),
        n40=("n40", "max"),
        claves=("clave", lambda s: ",".join(sorted(set(s)))),
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--raw", type=Path, default=settings.raw_dir)
    p.add_argument("--desde", default="0000-00-00")
    p.add_argument("--hasta", default=None)
    a = p.parse_args()

    n, trenes, sin, nulo, df = contar(a.raw, a.desde, a.hasta)
    total, t40 = trenes[False] + trenes[True], trenes[True]
    print(f"\n  {n:,} payloads, {total:,} trenes ({t40:,} del núcleo 40)\n")
    print(
        f"  {'clave':18} {'sin ella':>10} {'del 40':>8} {'% del 40':>9} {'a null':>7}"
    )
    for k in CLAVES:
        s40 = sin[k, True]
        print(
            f"  {k:18} {sin[k, False] + s40:10,} {s40:8,} "
            f"{100 * s40 / max(t40, 1):8.2f}% {nulo[k, False] + nulo[k, True]:7,}"
        )

    print(
        f"\n  Payloads con una clave ausente en toda la flota: {df['ts'].nunique():,}"
    )
    if df.empty:
        return
    df["franja"] = df["local"].dt.hour.map(lambda h: "0-6 h" if h < 7 else "7-23 h")
    print(
        f"  en {df['local'].dt.date.nunique()} días; trenes del núcleo 40: {df['n40'].sum()}"
    )
    print(
        f"  trenes en la flota: {dict(sorted(Counter(df.drop_duplicates('ts')['flota']).items()))}"
    )
    print()
    print(pd.crosstab(df["clave"], df["franja"], margins=True).to_string())
    print("\n  Episodios (menos de 30 min entre uno y el siguiente), hora local:")
    e = episodios(df)
    e["desde"] = e["desde"].dt.strftime("%d/%m %H:%M")
    e["hasta"] = e["hasta"].dt.strftime("%H:%M")
    print(e.to_string(index=False))


if __name__ == "__main__":
    main()
