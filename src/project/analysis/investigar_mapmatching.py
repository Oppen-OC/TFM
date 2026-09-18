"""Los abiertos del map-matching, uno por uno, sobre la salida guardada.

    uv run python -m project.analysis.validar_mapmatching --dias ... --guardar DIR
    uv run python -m project.analysis.investigar_mapmatching DIR <pregunta>

Lee `DIR/<dia>.parquet` (la salida de `emparejar`, una fila por posición) y
responde a una pregunta abierta de la bitácora 016:

  linea40      ¿por qué un sentido de la 40 no casa con su trazado? Distancia de
               sus posiciones a TODOS los trazados del feed, no sólo a los suyos.
  c3           ¿dónde se sale de su trazado la C3 Campanar → C. Benlloch?
               Reparto del fuera de ruta por tramo de abscisa y por distancia.
  l24          variantes de la 24 que empatan: qué trazado gana vehículo a
               vehículo, no grupo a grupo.
  umbral       sensibilidad del fuera de ruta al umbral `FUERA_DE_RUTA_M`.
  ambiguas     dónde se concentran: por línea y por posición en el recorrido.
  fuera        el fuera de ruta en horario de servicio, separando las celdas de
               cochera del resto, día a día.
  sin_abscisa  de qué se compone lo que no tiene abscisa fiable.
  nulos        las posiciones sin `trayecto`: cuándo, dónde, y si el mismo bus
               aparece con trayecto en el sondeo anterior o el siguiente.
  sin_cobertura  grupos (línea, trayecto) que algún día no casan con ningún
               trazado suyo, y qué trazado del feed los cubre (líneas 40 y 6).
  variantes    trazados de la 24 que salen del mismo sitio: dónde se separan.
  resumen      métricas de la validación por periodo, sólo días completos.
  fuera_lineas qué líneas explican el fuera de ruta de servicio fuera de
               cochera, el pico del 27-30/08 y la banda de 60-200 m.

Un día es COMPLETO si tiene al menos el 90 % de los sondeos de un día normal
(2.784): las jornadas partidas por caídas del colector (18 y 21/08, entrada 021)
o por el hueco del geoportal (10 y 14/09) cambian el reparto horario y no entran
en los agregados. `horario` es 7-22 h locales, como en `validar_mapmatching`.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from project.config import settings
from project.gtfs import a_grados, a_metros, cargar_trazados
from project.mapmatching import FUERA_DE_RUTA_M, proyectar, puntuar_candidatos

SONDEOS_DIA = 2784
COMPLETO = 0.9
CELDA = 1000  # 1/1000 de grado: celdas de ~100 m, como `validar_mapmatching`


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #
def cargar(raiz: Path, lineas: list[str] | None = None) -> pd.DataFrame:
    trozos = []
    for f in sorted(raiz.glob("*.parquet")):
        d = pd.read_parquet(f)
        if lineas is not None:
            d = d[d["linea"].astype(str).isin(lineas)]
        trozos.append(d.assign(dia=f.stem))
    df = pd.concat(trozos, ignore_index=True)
    df["linea"] = df["linea"].astype(str)
    local = df["ts_utc"].dt.tz_convert(settings.tz_local)
    df["hora"] = local.dt.hour
    df["horario"] = df["hora"].between(7, 22)
    df["mes"] = df["dia"].str[:7]
    for c in ("fuera_de_ruta", "ambigua"):
        df[c] = df[c].astype("boolean")
    return df


def dias_completos(raiz: Path) -> set[str]:
    completos = set()
    for f in sorted(raiz.glob("*.parquet")):
        n = pd.read_parquet(f, columns=["snapshot_id"])["snapshot_id"].nunique()
        if n >= COMPLETO * SONDEOS_DIA:
            completos.add(f.stem)
    return completos


def _celda(df: pd.DataFrame) -> pd.Series:
    return list(zip((df["lat"] * CELDA).round(), (df["lon"] * CELDA).round()))


def _pct(x: float) -> str:
    return f"{100 * x:5.1f} %"


# --------------------------------------------------------------------------- #
# Preguntas
# --------------------------------------------------------------------------- #
def linea40(raiz: Path, completos: set[str]) -> None:
    trazados = cargar_trazados()
    df = cargar(raiz, ["40"])
    con = df[df["trayecto"].notna()]
    print("\n  Línea 40 por sentido:")
    resumen = con.groupby("trayecto").agg(
        posiciones=("lat", "size"),
        dias=("dia", "nunique"),
        trazado=("shape_id", lambda s: ",".join(sorted(s.dropna().unique()))),
        dist_p50_m=("dist_trazado_m", "median"),
        fuera=("fuera_de_ruta", "mean"),
    )
    print(resumen.round(3).to_string())
    print("\n  Trazados de la 40 en el feed:")
    for t in trazados.get("40", []):
        lat0, lon0 = _grados(t.x[0], t.y[0])
        lat1, lon1 = _grados(t.x[-1], t.y[-1])
        print(
            f"    {t.shape_id:18} {t.largo / 1000:5.1f} km  "
            f"({lat0:.4f}, {lon0:.4f}) -> ({lat1:.4f}, {lon1:.4f})"
        )

    malos = resumen[resumen["fuera"] > 0.5].index
    todos = [t for ts in trazados.values() for t in ts]
    for trayecto in malos:
        g = con[con["trayecto"] == trayecto]
        x, y = a_metros(g["lat"].to_numpy(), g["lon"].to_numpy())
        print(
            f"\n  '{trayecto}': {len(g):,} posiciones en {g['dia'].nunique()} días "
            f"({', '.join(sorted(g['dia'].unique()))})"
        )
        filas = []
        for t in todos:
            d = proyectar(x, y, t)["dist_m"]
            filas.append(
                {
                    "linea": t.linea,
                    "shape_id": t.shape_id,
                    "cobertura": float((d <= FUERA_DE_RUTA_M).mean()),
                    "dist_p50_m": float(np.median(d)),
                }
            )
        mejores = pd.DataFrame(filas).sort_values(
            ["cobertura", "dist_p50_m"], ascending=[False, True]
        )
        print("  Trazados del feed que mejor la cubren (todas las líneas):")
        print(mejores.head(8).round(3).to_string(index=False))


def _grados(x: float, y: float) -> tuple[float, float]:
    lat, lon = a_grados(np.array([x]), np.array([y]))
    return float(lat[0]), float(lon[0])


def c3(raiz: Path, completos: set[str]) -> None:
    trazados = {t.shape_id: t for t in cargar_trazados().get("C3", [])}
    df = cargar(raiz, ["C3"])
    df = df[df["dia"].isin(completos) & df["trayecto"].notna()]
    for trayecto, g in df.groupby("trayecto"):
        sid = g["shape_id"].mode().iloc[0]
        cob = 1 - g["fuera_de_ruta"].astype(float).mean()
        print(
            f"\n  C3 '{trayecto}': {len(g):,} posiciones, trazado {sid}, "
            f"cobertura {_pct(cob)}"
        )
        if cob > 0.8:
            continue
        h = g[g["horario"]]
        fuera = h[h["fuera_de_ruta"].astype(bool)]
        print(f"  En horario: {len(h):,} posiciones, {_pct(len(fuera) / len(h))} fuera")
        tramos = pd.cut(
            fuera["dist_trazado_m"],
            [60, 100, 200, 500, 1000, 5000, np.inf],
            right=False,
        )
        print("  Distancia al trazado de lo que queda fuera:")
        print((tramos.value_counts(normalize=True).sort_index()).round(3).to_string())
        largo = trazados[sid].largo
        # Los extremos aparte: lo que proyecta en la abscisa 0 o en el final está
        # ANTES o DESPUÉS del trazado, no sobre él.
        for nombre, m in (
            ("antes del inicio (abscisa < 1 m)", fuera["abscisa_m"] < 1),
            ("después del final", fuera["abscisa_m"] > largo - 1),
        ):
            e = fuera[m]
            print(
                f"  Fuera {nombre}: {len(e):,} ({_pct(len(e) / max(len(fuera), 1))} "
                f"del fuera), distancia p50 {e['dist_trazado_m'].median():.0f} m"
            )
            if len(e):
                print(
                    f"    celdas: {pd.Series(_celda(e)).value_counts().head(3).to_dict()}"
                )
        bins = np.arange(0, largo + 500, 500)
        por_tramo = pd.DataFrame(
            {
                "posiciones": pd.cut(
                    h["abscisa_m"], bins, include_lowest=True
                ).value_counts(sort=False),
                "fuera": pd.cut(
                    fuera["abscisa_m"], bins, include_lowest=True
                ).value_counts(sort=False),
            }
        )
        por_tramo["fraccion_fuera"] = por_tramo["fuera"] / por_tramo["posiciones"]
        print(f"  Fuera de ruta por tramo de 500 m de abscisa (largo {largo:.0f} m):")
        print(por_tramo.round(3).to_string())
        print("  Por día (horario):")
        print(
            h.groupby("dia")["fuera_de_ruta"].mean().astype(float).round(3).to_string()
        )


def l24(raiz: Path, completos: set[str]) -> None:
    trazados = cargar_trazados().get("24", [])
    for t in trazados:
        lat0, lon0 = _grados(t.x[0], t.y[0])
        lat1, lon1 = _grados(t.x[-1], t.y[-1])
        print(
            f"  {t.shape_id:18} {t.largo / 1000:5.1f} km  "
            f"({lat0:.4f}, {lon0:.4f}) -> ({lat1:.4f}, {lon1:.4f})"
        )
    df = cargar(raiz, ["24"])
    df = df[df["trayecto"].notna()]
    for trayecto, g in df.groupby("trayecto"):
        filas = []
        for (dia, vid), v in g.groupby(["dia", "vehicle_id"]):
            if len(v) < 30:
                continue
            x, y = a_metros(v["lat"].to_numpy(), v["lon"].to_numpy())
            cand = puntuar_candidatos(v, x, y, trazados)
            a, b = cand[0], cand[1] if len(cand) > 1 else None
            filas.append(
                {
                    "dia": dia,
                    "gana": a["trazado"].shape_id,
                    "cobertura": a["cobertura"],
                    "avanza": a["avanza"],
                    "empate": b is not None
                    and abs(a["cobertura"] - b["cobertura"]) < 0.05
                    and abs(np.nan_to_num(a["avanza"]) - np.nan_to_num(b["avanza"]))
                    < 0.05,
                }
            )
        r = pd.DataFrame(filas)
        print(f"\n  24 '{trayecto}': {len(r)} trayectorias de >= 30 posiciones")
        if r.empty:
            continue
        print(
            r.groupby("gana")
            .agg(
                trayectorias=("dia", "size"),
                dias=("dia", "nunique"),
                cobertura=("cobertura", "median"),
                avanza=("avanza", "median"),
                empates=("empate", "sum"),
            )
            .round(3)
            .to_string()
        )
        print("  Trazado elegido por el grupo, por día:")
        print(g.groupby("dia")["shape_id"].agg(lambda s: s.mode().iloc[0]).to_string())


def umbral(raiz: Path, completos: set[str]) -> None:
    cols = ["dist_trazado_m", "shape_id", "ts_utc", "linea", "lat", "lon"]
    trozos = []
    for f in sorted(raiz.glob("*.parquet")):
        if f.stem not in completos:
            continue
        d = pd.read_parquet(f, columns=cols)
        d = d[d["shape_id"].notna()]
        h = d["ts_utc"].dt.tz_convert(settings.tz_local).dt.hour
        trozos.append(
            pd.DataFrame(
                {
                    "dist": d["dist_trazado_m"],
                    "horario": h.between(7, 22),
                    "mes": f.stem[:7],
                }
            )
        )
    df = pd.concat(trozos, ignore_index=True)
    umbrales = [20, 30, 40, 50, 60, 80, 100, 150, 200, 500]
    for horario, nombre in ((True, "7-22 h"), (False, "0-6 h y 23 h")):
        s = df[df["horario"] == horario]
        print(f"\n  Fracción por encima del umbral, {nombre} ({len(s):,} posiciones):")
        tabla = pd.DataFrame(
            {
                mes: [(g["dist"] > u).mean() for u in umbrales]
                for mes, g in s.groupby("mes")
            },
            index=[f"> {u} m" for u in umbrales],
        )
        print((100 * tabla).round(2).to_string())
    s = df[df["horario"]]
    bordes = [0, 5, 10, 15, 20, 30, 40, 50, 60, 80, 100, 150, 200, 500, np.inf]
    print("\n  Densidad por tramo de distancia, 7-22 h (% de posiciones por metro):")
    c = pd.cut(s["dist"], bordes, right=False).value_counts(normalize=True, sort=False)
    anchos = np.diff(bordes)
    anchos[-1] = np.nan
    print(
        pd.DataFrame(
            {"%": 100 * c.values, "% por m": 100 * c.values / anchos}, index=c.index
        )
        .round(4)
        .to_string()
    )


def ambiguas(raiz: Path, completos: set[str]) -> None:
    largos = {t.shape_id: t.largo for ts in cargar_trazados().values() for t in ts}
    df = cargar(raiz)
    df = df[df["dia"].isin(completos) & df["shape_id"].notna()]
    amb = df[df["ambigua"].astype(bool)]
    print(f"\n  Ambiguas: {len(amb):,} de {len(df):,} ({_pct(len(amb) / len(df))})")
    por_linea = df.groupby("linea")["ambigua"].agg(["sum", "mean", "size"])
    por_linea["parte"] = por_linea["sum"] / len(amb)
    print("  Por línea (las 12 que más aportan):")
    print(por_linea.sort_values("sum", ascending=False).head(12).round(3).to_string())
    rel = amb["abscisa_m"] / amb["shape_id"].map(largos)
    print("  Posición relativa en el recorrido (0 = cabecera):")
    print(
        pd.cut(rel, np.linspace(0, 1, 11), include_lowest=True)
        .value_counts(normalize=True, sort=False)
        .round(3)
        .to_string()
    )
    print("  Por mes:")
    print(df.groupby("mes")["ambigua"].mean().astype(float).round(4).to_string())


def fuera(raiz: Path, completos: set[str]) -> None:
    df = cargar(raiz)
    df = df[df["shape_id"].notna()]
    noche = df[
        ~df["horario"] & df["fuera_de_ruta"].astype(bool) & df["dia"].isin(completos)
    ]
    cocheras = set(pd.Series(_celda(noche)).value_counts().head(10).index)
    df["en_cochera"] = pd.Series(_celda(df), index=df.index).isin(cocheras)
    h = df[df["horario"]]
    f = h["fuera_de_ruta"].astype(bool)
    por_dia = pd.DataFrame(
        {
            "completo": h.groupby("dia")["dia"].first().isin(completos),
            "fuera": f.groupby(h["dia"]).mean(),
            "en_cochera": (f & h["en_cochera"]).groupby(h["dia"]).mean(),
            "resto": (f & ~h["en_cochera"]).groupby(h["dia"]).mean(),
            "posiciones": h.groupby("dia").size(),
        }
    )
    print("\n  Fuera de ruta, 7-22 h, sobre las posiciones con trazado:")
    print("  (cochera = las 10 celdas de 100 m con más fuera de ruta de madrugada)")
    print(
        (
            por_dia.assign(
                **{c: 100 * por_dia[c] for c in ("fuera", "en_cochera", "resto")}
            )
        )
        .round(2)
        .to_string()
    )
    c = por_dia[por_dia["completo"]]
    periodo = np.where(
        c.index < "2026-08-24",
        "ago < 24",
        np.where(c.index < "2026-09-01", "ago >= 24", "sep"),
    )
    print("\n  Media de los días completos por periodo (%):")
    print(
        (100 * c.groupby(periodo)[["fuera", "en_cochera", "resto"]].mean())
        .round(2)
        .to_string()
    )


def sin_abscisa(raiz: Path, completos: set[str]) -> None:
    df = cargar(raiz)
    df = df[df["dia"].isin(completos)]
    motivo = pd.Series("fiable", index=df.index)
    con = df["shape_id"].notna()
    fr = df["fuera_de_ruta"].fillna(False).astype(bool)
    am = df["ambigua"].fillna(False).astype(bool)
    motivo[con & am & ~fr] = "ambigua"
    motivo[con & fr] = "fuera_de_ruta"
    motivo[df["motivo"] == "sin_trazado"] = "sin_trazado"
    motivo[df["motivo"] == "sin_trayecto"] = "sin_trayecto"
    tabla = pd.crosstab(motivo, [df["mes"], df["horario"]], normalize="columns")
    tabla.columns = [f"{m} {'7-22h' if h else 'noche'}" for m, h in tabla.columns]
    print("\n  Composición de las posiciones (días completos):")
    print((100 * tabla).round(2).to_string())
    total = motivo.value_counts(normalize=True)
    print("\n  Todas las horas, todos los días completos:")
    print((100 * total).round(2).to_string())


def nulos(raiz: Path, completos: set[str]) -> None:
    trazados = cargar_trazados()
    df = cargar(raiz)
    df = df[df["dia"].isin(completos)]
    nul = df[df["trayecto"].isna()]
    print(
        f"\n  Sin trayecto: {len(nul):,} de {len(df):,} ({100 * len(nul) / len(df):.3f} %),"
        f" {nul['linea'].nunique()} líneas"
    )
    print("  Por hora local:")
    print(nul["hora"].value_counts(normalize=True).sort_index().round(3).to_string())
    print("  Líneas que más aportan:")
    print(nul["linea"].value_counts().head(10).to_string())

    # ¿Sobre qué parte del recorrido? Contra todos los trazados de su línea.
    filas = []
    for linea, g in nul.groupby("linea"):
        ts = trazados.get(linea, [])
        if not ts:
            continue
        x, y = a_metros(g["lat"].to_numpy(), g["lon"].to_numpy())
        mejor_d = np.full(len(g), np.inf)
        mejor_rel = np.full(len(g), np.nan)
        for t in ts:
            p = proyectar(x, y, t)
            m = p["dist_m"] < mejor_d
            mejor_d[m] = p["dist_m"][m]
            mejor_rel[m] = p["abscisa_m"][m] / t.largo
        filas.append(pd.DataFrame({"dist": mejor_d, "rel": mejor_rel}, index=g.index))
    pos = pd.concat(filas)
    sobre = pos["dist"] <= FUERA_DE_RUTA_M
    print(
        f"  A <= {FUERA_DE_RUTA_M:.0f} m de algún trazado de su línea: {_pct(sobre.mean())}"
    )
    print("  De esas, posición relativa en el trazado más cercano (0 = cabecera):")
    print(
        pd.cut(
            pos.loc[sobre, "rel"], [0, 0.05, 0.25, 0.75, 0.95, 1], include_lowest=True
        )
        .value_counts(normalize=True, sort=False)
        .round(3)
        .to_string()
    )

    # ¿El mismo bus tiene trayecto en el sondeo de al lado? Posición de su línea
    # con trayecto, a menos de 300 m, en el sondeo anterior o el siguiente.
    orden = (
        df[["dia", "snapshot_id"]].drop_duplicates().sort_values(["dia", "snapshot_id"])
    )
    orden["k"] = orden.groupby("dia").cumcount()
    k = df[["dia", "snapshot_id"]].merge(orden, on=["dia", "snapshot_id"], how="left")[
        "k"
    ]
    df = df.assign(k=k.to_numpy())
    nul = df[df["trayecto"].isna()]
    con = df[df["trayecto"].notna()][["dia", "k", "linea", "trayecto", "lat", "lon"]]
    vecino = pd.Series(False, index=nul.index)
    for delta in (-1, 1):
        q = nul[["dia", "k", "linea", "lat", "lon"]].assign(k=nul["k"] + delta)
        m = q.reset_index().merge(con, on=["dia", "k", "linea"], suffixes=("", "_v"))
        xa, ya = a_metros(m["lat"].to_numpy(), m["lon"].to_numpy())
        xb, yb = a_metros(m["lat_v"].to_numpy(), m["lon_v"].to_numpy())
        m["d"] = np.hypot(xa - xb, ya - yb)
        cerca = m[m["d"] < 300].sort_values("d").drop_duplicates("index")
        vecino[cerca["index"]] = True
    print(
        f"  Con una posición de su línea con trayecto a < 300 m en el sondeo "
        f"anterior o el siguiente: {_pct(vecino.mean())}"
    )


def sin_cobertura(raiz: Path, completos: set[str]) -> None:
    """Grupos (línea, trayecto) que un día no casan con ningún trazado suyo."""
    trazados = cargar_trazados()
    todos = [t for ts in trazados.values() for t in ts]
    df = cargar(raiz)
    df = df[df["shape_id"].notna()]
    dia = df.groupby(["linea", "trayecto", "dia"]).agg(
        n=("lat", "size"),
        cobertura=("fuera_de_ruta", lambda f: 1 - f.astype(float).mean()),
        horario=("horario", "mean"),
    )
    malos = dia[(dia["n"] >= 50) & (dia["cobertura"] < 0.2)].reset_index()
    print(f"\n  Grupo-día con >= 50 posiciones y cobertura < 20 %: {len(malos)}")
    noche = df[~df["horario"] & df["fuera_de_ruta"].astype(bool)]
    cocheras = set(pd.Series(_celda(noche)).value_counts().head(10).index)
    clases = []
    for (linea, trayecto), g in malos.groupby(["linea", "trayecto"]):
        todos_dias = dia.loc[(linea, trayecto)]
        print(
            f"\n  {linea} '{trayecto}': {int(g['n'].sum()):,} posiciones en "
            f"{len(g)} de {len(todos_dias)} días; en horario de servicio el "
            f"{_pct(float((g['n'] * g['horario']).sum() / g['n'].sum()))}"
        )
        print(f"    días sin cobertura: {', '.join(g['dia'])}")
        buenos = todos_dias[todos_dias["cobertura"] >= 0.5]
        print(
            f"    días con cobertura >= 50 %: {len(buenos)}"
            + (
                f" ({buenos.index.min()} .. {buenos.index.max()})"
                if len(buenos)
                else ""
            )
        )
        m = (
            (df["linea"] == linea)
            & (df["trayecto"] == trayecto)
            & df["dia"].isin(set(g["dia"]))
        )
        pos = df[m]
        x, y = a_metros(pos["lat"].to_numpy(), pos["lon"].to_numpy())
        filas = []
        for t in todos:
            d = proyectar(x, y, t)["dist_m"]
            filas.append(
                {
                    "linea": t.linea,
                    "shape_id": t.shape_id,
                    "cobertura": float((d <= FUERA_DE_RUTA_M).mean()),
                    "dist_p50_m": float(np.median(d)),
                }
            )
        mejores = pd.DataFrame(filas).sort_values(
            ["cobertura", "dist_p50_m"], ascending=[False, True]
        )
        print("    trazados del feed que mejor cubren esas posiciones:")
        print(mejores.head(5).round(3).to_string(index=False))
        print(f"    celdas: {pd.Series(_celda(pos)).value_counts().head(3).to_dict()}")
        otra = mejores[mejores["linea"] != linea].iloc[0]
        en_cochera = float(pd.Series(_celda(pos)).isin(cocheras).mean())
        if otra["cobertura"] >= 0.8:
            clase = f"circula sobre la {otra['linea']}"
        elif en_cochera >= 0.5:
            clase = "aparcado en cochera"
        else:
            clase = "otro"
        clases.append({"clase": clase.split(" la ")[0], "posiciones": len(pos)})
        print(f"    => {clase} (en celdas de cochera: {_pct(en_cochera)})")
    r = pd.DataFrame(clases).groupby("clase")["posiciones"].agg(["size", "sum"])
    print("\n  Resumen: grupos (línea, trayecto) y posiciones por clase")
    print(r.rename(columns={"size": "grupos", "sum": "posiciones"}).to_string())


def variantes(raiz: Path, completos: set[str], linea: str = "24") -> None:
    """Pares de trazados de una línea que salen del mismo sitio: dónde se separan."""
    ts = cargar_trazados().get(linea, [])
    for a in ts:
        for b in ts:
            if a.shape_id >= b.shape_id:
                continue
            if np.hypot(a.x[0] - b.x[0], a.y[0] - b.y[0]) > 500:
                continue
            s_a = np.arange(0, a.largo, 25.0)
            xa, ya = np.interp(s_a, a.acum, a.x), np.interp(s_a, a.acum, a.y)
            d = proyectar(xa, ya, b)["dist_m"]
            fuera_b = s_a[d > 20]
            comun = float((d <= 20).mean())
            print(
                f"  {a.shape_id} ({a.largo:.0f} m) frente a {b.shape_id} "
                f"({b.largo:.0f} m): {_pct(comun)} de {a.shape_id} a <= 20 m del otro"
            )
            if len(fuera_b):
                # tramos contiguos de separación
                cortes = np.where(np.diff(fuera_b) > 25.0)[0]
                ini = np.r_[fuera_b[0], fuera_b[cortes + 1]]
                fin = np.r_[fuera_b[cortes], fuera_b[-1]]
                tramos = ", ".join(f"{i:.0f}-{f:.0f} m" for i, f in zip(ini, fin))
                print(f"    se separan en: {tramos}")


def fuera_lineas(raiz: Path, completos: set[str]) -> None:
    """Qué líneas explican el fuera de ruta de servicio fuera de cochera."""
    df = cargar(raiz)
    df = df[df["shape_id"].notna() & df["dia"].isin(completos)]
    noche = df[~df["horario"] & df["fuera_de_ruta"].astype(bool)]
    cocheras = set(pd.Series(_celda(noche)).value_counts().head(10).index)
    h = df[df["horario"]].copy()
    h["en_cochera"] = pd.Series(_celda(h), index=h.index).isin(cocheras)
    h["periodo"] = np.where(
        h["dia"] < "2026-08-24",
        "ago < 24",
        np.where(h["dia"] < "2026-09-01", "ago >= 24", "sep"),
    )
    resto = h[h["fuera_de_ruta"].astype(bool) & ~h["en_cochera"]]
    tasa = (
        resto.groupby(["periodo", "linea"]).size()
        / h.groupby(["periodo", "linea"]).size()
    ).unstack(0)
    aporte = (
        resto.groupby(["periodo", "linea"]).size() / h.groupby("periodo").size()
    ).unstack(0)
    top = aporte.sum(axis=1).sort_values(ascending=False).head(12).index
    print("\n  Fuera de ruta fuera de cochera, 7-22 h: aporte a la tasa global (pp)")
    print((100 * aporte.loc[top]).round(2).to_string())
    print("\n  ... y tasa dentro de cada línea (%)")
    print((100 * tasa.loc[top]).round(1).to_string())
    pico = resto[resto["dia"].between("2026-08-27", "2026-08-30")]
    base = resto[resto["dia"].between("2026-08-24", "2026-08-26")]
    print(
        "\n  Pico 27-30/08 frente a 24-26/08, posiciones por día, líneas que más suben:"
    )
    sube = (pico["linea"].value_counts() / 4).sub(
        base["linea"].value_counts() / 3, fill_value=0
    )
    print(sube.sort_values(ascending=False).head(8).round(0).to_string())
    banda = h[h["dist_trazado_m"].between(60, 200)]
    print(
        f"\n  Banda 60-200 m, 7-22 h: {len(banda):,} posiciones "
        f"({_pct(len(banda) / len(h))}); líneas que más aportan:"
    )
    print(
        (banda["linea"].value_counts(normalize=True).head(8) * 100).round(1).to_string()
    )


def resumen(raiz: Path, completos: set[str]) -> None:
    """Las métricas de la validación por periodo, sólo con días completos."""
    filas = []
    for f in sorted(raiz.glob("*.parquet")):
        if f.stem not in completos:
            continue
        d = pd.read_parquet(
            f,
            columns=[
                "dist_trazado_m",
                "shape_id",
                "motivo",
                "fuera_de_ruta",
                "ambigua",
                "ts_utc",
            ],
        )
        h = d["ts_utc"].dt.tz_convert(settings.tz_local).dt.hour.between(7, 22)
        con = d["shape_id"].notna()
        filas.append(
            {
                "dia": f.stem,
                "periodo": "ago < 24"
                if f.stem < "2026-08-24"
                else ("ago >= 24" if f.stem < "2026-09-01" else "sep"),
                "posiciones": len(d),
                "dist_p50_m": d.loc[con, "dist_trazado_m"].median(),
                "fuera_7_22": d.loc[con & h, "fuera_de_ruta"].astype(float).mean(),
                "ambigua": d.loc[con, "ambigua"].astype(float).mean(),
                "sin_trazado": (d["motivo"] == "sin_trazado").mean(),
            }
        )
    t = pd.DataFrame(filas)
    agg = t.groupby("periodo").agg(
        dias=("dia", "size"),
        posiciones=("posiciones", "sum"),
        p50_min=("dist_p50_m", "min"),
        p50_med=("dist_p50_m", "median"),
        p50_max=("dist_p50_m", "max"),
        fuera_7_22_med=("fuera_7_22", "median"),
        fuera_7_22_max=("fuera_7_22", "max"),
        ambigua_med=("ambigua", "median"),
        sin_trazado_med=("sin_trazado", "median"),
    )
    for c in ("fuera_7_22_med", "fuera_7_22_max", "ambigua_med", "sin_trazado_med"):
        agg[c] = 100 * agg[c]
    print("\n  Por periodo, días completos (fracciones en %):")
    print(agg.round(2).T.to_string())


PREGUNTAS = {
    "linea40": linea40,
    "c3": c3,
    "l24": l24,
    "umbral": umbral,
    "ambiguas": ambiguas,
    "fuera": fuera,
    "sin_abscisa": sin_abscisa,
    "nulos": nulos,
    "sin_cobertura": sin_cobertura,
    "variantes": variantes,
    "fuera_lineas": fuera_lineas,
    "resumen": resumen,
}

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("raiz", type=Path)
    p.add_argument("preguntas", nargs="+", choices=list(PREGUNTAS))
    a = p.parse_args()
    completos = dias_completos(a.raiz)
    print(f"  {len(completos)} días completos: {', '.join(sorted(completos))}")
    for q in a.preguntas:
        print(f"\n=== {q} ===")
        PREGUNTAS[q](a.raiz, completos)
