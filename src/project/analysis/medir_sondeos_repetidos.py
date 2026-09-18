"""¿Qué trae la segunda captura de un sondeo? Medición sobre el crudo, solo lectura.

    uv run python -m project.analysis.medir_sondeos_repetidos
    uv run python -m project.analysis.medir_sondeos_repetidos --sources emt_buses

Las fuentes sirven a veces el mismo sondeo en más de una captura. El colector se
queda la primera y `reprocesar` la que más filas trae (bitácora 019). Aquí se
mide, por fuente, cuántas capturas repiten la clave de sondeo de una anterior
(`sources.clave_sondeo`) y cuántas de ellas traen contenido distinto. En la EMT
se compara cada repetición distinta con la primera captura de su sondeo, gid a
gid:

  solo_fecha       mismos gid y misma posición; sólo cambia `fecha`, en ±2 h.
                   Es la alternancia de convención horaria (trampa 002), que el
                   parseo iguala.
  primera_parcial  los gid de la primera captura son un subconjunto estricto de
                   los de la repetición, con la misma posición en los comunes:
                   la primera captura era el bloque a medio reinsertar.
                   Además, son los gid más bajos del bloque y sin huecos.
  primera_subconjunto
                   subconjunto estricto que NO es ese prefijo.
  reordenado       mismo contenido en otro orden.
  otros            cualquier otra cosa. Si no es 0, la lectura de arriba no vale.

El efecto se cuenta en sondeos parciales: los que traen menos del
`--umbral` de la mediana de filas de sus `--vecinos` vecinos, eligiendo la
primera captura (colector) o la más completa (`reprocesar`).

El contenido se compara sobre el payload crudo: `features` en las capas ArcGIS,
y en Renfe sólo los trenes del núcleo 40 más `fechaActualizacion`, que es lo que
llega al curated.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from project.config import settings
from project.ingest.sources import SOURCES, clave_sondeo, parse, read_raw

DESFASE_CONVENCION_MS = 2 * 3600 * 1000


def _huella(source: str, payload) -> str:
    if source == "renfe_cercanias":
        trenes = payload.get("trenes", []) if isinstance(payload, dict) else payload
        rel = {
            "f": payload.get("fechaActualizacion")
            if isinstance(payload, dict)
            else None,
            "t": sorted(
                (t for t in trenes if t.get("nucleo") == "40"),
                key=lambda t: json.dumps(t, sort_keys=True),
            ),
        }
    else:
        rel = payload.get("features", [])
    s = json.dumps(rel, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.blake2b(s.encode(), digest_size=12).hexdigest()


def _capturas(tarea: tuple[str, str]) -> list[tuple]:
    """Una fila por captura no vacía: clave de sondeo, huella y filas."""
    source, fichero = tarea
    out = []
    for orden, (ts, payload) in enumerate(read_raw(Path(fichero))):
        try:
            df = parse(source, payload, ts)
        except Exception:  # noqa: BLE001
            continue
        if df.empty:
            continue
        clave = str(clave_sondeo(df, ts))
        out.append(
            (source, fichero, orden, ts, clave, _huella(source, payload), len(df))
        )
    return out


def _filas_emt(payload) -> dict:
    out = {}
    for f in payload.get("features", []) or []:
        a = f.get("attributes") or {}
        g = f.get("geometry") or {}
        out[a.get("gid")] = (
            a.get("linea"),
            a.get("trayecto"),
            a.get("fecha"),
            g.get("x"),
            g.get("y"),
        )
    return out


def _comparar(primera, repeticion) -> str:
    f1, f2 = _filas_emt(primera), _filas_emt(repeticion)
    g1, g2 = set(f1), set(f2)
    comunes = g1 & g2
    if any(f1[g][:2] != f2[g][:2] or f1[g][3:] != f2[g][3:] for g in comunes):
        return "otros"
    if g1 == g2:
        desfases = {f2[g][2] - f1[g][2] for g in comunes if f1[g][2] != f2[g][2]}
        if not desfases:
            return "reordenado"
        if desfases <= {DESFASE_CONVENCION_MS, -DESFASE_CONVENCION_MS}:
            return "solo_fecha"
        return "otros"
    if not g1 < g2:
        return "otros"
    # Prefijo: los gid de la primera son los más bajos del bloque y sin huecos,
    # que es lo que deja una lectura a mitad de una reinserción en orden.
    prefijo = max(g1) - min(g1) + 1 == len(g1) and min(g2 - g1) > max(g1)
    return "primera_parcial" if prefijo else "primera_subconjunto"


def _leer(fichero: str, ordenes: set[int]) -> dict[int, dict]:
    return {
        i: payload
        for i, (_, payload) in enumerate(read_raw(Path(fichero)))
        if i in ordenes
    }


def _clasificar(pares: list[tuple]) -> list[str]:
    """pares: (fichero_1, orden_1, fichero_rep, orden_rep), del mismo fichero_rep."""
    pedidos: dict[str, set[int]] = defaultdict(set)
    for f1, o1, fr, orr in pares:
        pedidos[f1].add(o1)
        pedidos[fr].add(orr)
    leidos = {f: _leer(f, o) for f, o in pedidos.items()}
    return [_comparar(leidos[f1][o1], leidos[fr][orr]) for f1, o1, fr, orr in pares]


def _parciales(n: pd.Series, vecinos: int, umbral: float) -> int:
    mediana = n.rolling(vecinos + 1, center=True, min_periods=1).median()
    return int((n < umbral * mediana).sum())


def medir(root: Path, fuentes: list[str], vecinos: int, umbral: float) -> None:
    tareas = [
        (s, str(f))
        for s in fuentes
        for f in sorted((root / "raw" / f"source={s}").rglob("*.ndjson.gz"))
    ]
    with Pool() as pool:
        filas = [x for bloque in pool.map(_capturas, tareas) for x in bloque]
    cap = pd.DataFrame(
        filas, columns=["fuente", "fichero", "orden", "ts", "clave", "huella", "n"]
    ).sort_values(["fuente", "ts", "orden"], kind="stable")

    print(
        f"\n  {'fuente':20} {'capturas':>9} {'sondeos':>9} {'repetidas':>10} "
        f"{'distintas':>10}"
    )
    for s, g in cap.groupby("fuente", sort=False):
        primera = g.drop_duplicates("clave").set_index("clave")
        rep = g[g.duplicated("clave")]
        distintas = rep[rep["huella"] != rep["clave"].map(primera["huella"])]
        print(
            f"  {s:20} {len(g):9,} {g['clave'].nunique():9,} {len(rep):10,} "
            f"{len(distintas):10,}"
        )

    g = cap[cap["fuente"] == "emt_buses"].reset_index(drop=True)
    if g.empty:
        return
    primera = g.drop_duplicates("clave").set_index("clave")
    rep = g[g.duplicated("clave")]
    distintas = rep[rep["huella"] != rep["clave"].map(primera["huella"])]

    por_fichero: dict[str, list[tuple]] = defaultdict(list)
    for _, r in distintas.iterrows():
        p = primera.loc[r["clave"]]
        por_fichero[r["fichero"]].append(
            (p["fichero"], int(p["orden"]), r["fichero"], int(r["orden"]))
        )
    with Pool() as pool:
        tipos = Counter(
            t for bloque in pool.map(_clasificar, por_fichero.values()) for t in bloque
        )

    # Cuántos sondeos nuevos se cuelan entre la primera captura y la repetición.
    vistos: dict[str, int] = {}
    nuevos = hueco_max = 0
    for clave in g["clave"]:
        if clave in vistos:
            hueco_max = max(hueco_max, nuevos - vistos[clave] - 1)
        else:
            vistos[clave] = nuevos
            nuevos += 1

    por_sondeo = g.groupby("clave", sort=False)["n"].agg(["first", "max"])
    completables = por_sondeo[por_sondeo["max"] > por_sondeo["first"]]
    frac = completables["first"] / completables["max"]

    print("\n  EMT, repeticiones con contenido distinto de la primera captura:")
    for t in (
        "solo_fecha",
        "reordenado",
        "primera_parcial",
        "primera_subconjunto",
        "otros",
    ):
        print(f"    {t:18} {tipos.get(t, 0):7,}")
    print(
        f"  sondeos con una captura posterior más completa: {len(completables):,} "
        f"de {len(por_sondeo):,} ({100 * len(completables) / len(por_sondeo):.2f} %)"
    )
    print(
        f"  filas que añade esa captura: "
        f"{int((completables['max'] - completables['first']).sum()):,}"
    )
    q = np.percentile(frac, [25, 50, 75]) if len(frac) else [np.nan] * 3
    print(
        f"  fracción del bloque en la primera captura: p25 {q[0]:.2f} · "
        f"p50 {q[1]:.2f} · p75 {q[2]:.2f}"
    )
    print(f"  máximo de sondeos nuevos entre primera captura y repetición: {hueco_max}")
    print(
        f"\n  Sondeos parciales (< {umbral:.0%} de la mediana de {vecinos} vecinos):"
        f"\n    primera captura (colector)      "
        f"{_parciales(por_sondeo['first'], vecinos, umbral):7,}"
        f"\n    captura más completa (reprocesar) "
        f"{_parciales(por_sondeo['max'], vecinos, umbral):5,}\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=settings.data_root)
    p.add_argument("--sources", nargs="*", default=list(SOURCES))
    p.add_argument("--vecinos", type=int, default=20)
    p.add_argument("--umbral", type=float, default=0.8)
    a = p.parse_args()
    medir(a.data, a.sources, a.vecinos, a.umbral)
