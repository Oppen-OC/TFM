"""Diagnóstico go/no-go de la hipótesis central del TFM.

    python demo/diagnose.py                 # sobre data/ capturado por collect.py
    python demo/diagnose.py --data mi_data --umbral-m 50

Responde a cuatro preguntas, en orden creciente de importancia. Si la cuarta
sale plana, la fusión bus-tráfico no tiene señal y hay que cambiar de enfoque.
Mejor saberlo en septiembre que en febrero.

  1. COBERTURA   ¿Qué fracción de posiciones de bus cae cerca de un tramo con
                 dato de tráfico? Si es baja, la fusión solo aplica a parte de
                 la red y hay que reformular el alcance.
  2. VARIANZA    ¿El `estado` varía de verdad por hora del día, o está casi
                 siempre en la misma clase? Una variable sin varianza no predice.
  3. DINÁMICA    ¿Cada tramo cambia de estado a lo largo del día, o hay tramos
                 congelados? Distingue "la ciudad está fluida" de "el sensor
                 no reporta".
  4. SEÑAL       ¿Los buses van más lentos en los tramos declarados
                 congestionados? Es el test directo de si la variable significa
                 algo para un autobús. NO necesita GTFS, ni map-matching, ni
                 etiquetas de retraso: solo lo que ya captura el colector.

No usa geopandas ni shapely: la distancia punto-polilínea va en numpy sobre una
proyección equirectangular local, con error muy por debajo del metro a escala de
ciudad.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from track import rastrear  # noqa: E402

LAT0, LON0 = 39.47, -0.376  # centro de València, origen de la proyección local


# --------------------------------------------------------------------------- #
# Geometría
# --------------------------------------------------------------------------- #
def a_metros(lat, lon):
    """Equirectangular local. Exacta a nivel de centímetros a escala de ciudad."""
    x = (np.asarray(lon) - LON0) * 111_320.0 * np.cos(np.radians(LAT0))
    y = (np.asarray(lat) - LAT0) * 110_540.0
    return x, y


def wkt_a_segmentos(wkt: str) -> np.ndarray:
    """WKT LINESTRING/MULTILINESTRING -> array (n, 2, 2) de sub-segmentos en metros."""
    if not isinstance(wkt, str) or "(" not in wkt:
        return np.empty((0, 2, 2))
    cuerpo = wkt[wkt.find("(") :].strip()
    partes = [p for p in cuerpo.replace("(", " ").replace(")", " ").split(",")]
    pts = []
    for p in partes:
        t = p.split()
        if len(t) >= 2:
            try:
                pts.append((float(t[-2]), float(t[-1])))
            except ValueError:
                continue
    if len(pts) < 2:
        return np.empty((0, 2, 2))
    lon = np.array([p[0] for p in pts])
    lat = np.array([p[1] for p in pts])
    x, y = a_metros(lat, lon)
    P = np.stack([x, y], axis=1)
    return np.stack([P[:-1], P[1:]], axis=1)


def dist_puntos_a_segmentos(px, py, segs) -> np.ndarray:
    """Distancia mínima de cada punto al conjunto de sub-segmentos. Vectorizado."""
    if len(segs) == 0:
        return np.full(len(px), np.inf)
    a = segs[:, 0, :]
    b = segs[:, 1, :]
    ab = b - a
    L2 = (ab**2).sum(axis=1)
    L2[L2 == 0] = 1e-9
    ap_x = px[:, None] - a[None, :, 0]
    ap_y = py[:, None] - a[None, :, 1]
    t = np.clip((ap_x * ab[None, :, 0] + ap_y * ab[None, :, 1]) / L2[None, :], 0.0, 1.0)
    dx = ap_x - t * ab[None, :, 0]
    dy = ap_y - t * ab[None, :, 1]
    return np.sqrt(dx**2 + dy**2).min(axis=1)


def _densificar(segs: np.ndarray, paso: float = 40.0) -> np.ndarray:
    """Parte los sub-segmentos largos para que ninguno supere `paso` metros.

    Permite indexar por punto medio sin perder precisión: si un sub-segmento
    mide como mucho `paso`, su punto medio nunca está a más de `paso/2` de
    cualquiera de sus puntos.
    """
    salida = []
    for a, b in segs:
        L = float(np.hypot(*(b - a)))
        n = max(1, int(np.ceil(L / paso)))
        t = np.linspace(0.0, 1.0, n + 1)[:, None]
        pts = a + t * (b - a)
        salida.append(np.stack([pts[:-1], pts[1:]], axis=1))
    return np.concatenate(salida) if salida else np.empty((0, 2, 2))


DIST_MAX_M = 500.0  # más allá de esto da igual el valor exacto


def asignar_tramo(buses: pd.DataFrame, tramos: pd.DataFrame) -> pd.DataFrame:
    """Añade `idtramo_cercano` y `dist_tramo_m` a cada posición de bus.

    Índice KD sobre los puntos medios de los sub-segmentos densificados. Sin
    esto, 65.000 posiciones contra 446 tramos no termina en un tiempo razonable.
    """
    from scipy.spatial import cKDTree

    trozos, duenos = [], []
    for _, tr in tramos.iterrows():
        segs = wkt_a_segmentos(tr["geom_wkt"])
        if len(segs) == 0:
            continue
        segs = _densificar(segs)
        trozos.append(segs)
        duenos.append(np.full(len(segs), tr["idtramo"], dtype=object))
    if not trozos:
        out = buses.copy()
        out["dist_tramo_m"] = np.inf
        out["idtramo_cercano"] = None
        return out

    S = np.concatenate(trozos)
    D = np.concatenate(duenos)
    medios = S.mean(axis=1)
    arbol = cKDTree(medios)

    px, py = a_metros(buses["lat"].to_numpy(), buses["lon"].to_numpy())
    P = np.stack([px, py], axis=1)

    a = S[:, 0, :]
    ab = S[:, 1, :] - a
    L2 = np.maximum((ab**2).sum(axis=1), 1e-9)
    HOLGURA = 21.0  # media longitud del sub-segmento densificado (40 m) + margen

    def exacta(i: int, j: np.ndarray) -> tuple[float, object]:
        apx = P[i, 0] - a[j, 0]
        apy = P[i, 1] - a[j, 1]
        t = np.clip((apx * ab[j, 0] + apy * ab[j, 1]) / L2[j], 0.0, 1.0)
        d = np.hypot(apx - t * ab[j, 0], apy - t * ab[j, 1])
        k = int(d.argmin())
        return float(d[k]), D[j[k]]

    # K vecinos más próximos por punto: trabajo acotado, a diferencia de un
    # radio fijo (que se dispara cuando los tramos están apiñados).
    K = min(48, len(S))
    d_mid, idx = arbol.query(P, k=K)
    if K == 1:
        d_mid, idx = d_mid[:, None], idx[:, None]

    mejor_d = np.full(len(buses), np.inf)
    mejor_i = np.empty(len(buses), dtype=object)
    for i in range(len(buses)):
        j = idx[i]
        j = j[j < len(S)]
        if not len(j):
            continue
        dist, dueno = exacta(i, j)
        # Garantía de exactitud: ningún sub-segmento cuyo punto medio esté más
        # lejos que dist+HOLGURA puede mejorar el resultado. Si el K-ésimo no
        # llega a ese umbral, hay que ampliar la búsqueda para ese punto.
        if d_mid[i, -1] < dist + HOLGURA:
            j2 = np.asarray(arbol.query_ball_point(P[i], r=dist + HOLGURA))
            if len(j2):
                dist, dueno = exacta(i, j2)
        mejor_d[i] = dist
        mejor_i[i] = dueno

    out = buses.copy()
    out["dist_tramo_m"] = mejor_d
    out["idtramo_cercano"] = mejor_i
    return out


# --------------------------------------------------------------------------- #
# Carga
# --------------------------------------------------------------------------- #
def cargar(root: Path, source: str) -> pd.DataFrame:
    d = root / "curated" / f"source={source}"
    if not d.exists():
        return pd.DataFrame()
    ficheros = sorted(d.rglob("*.parquet"))
    if not ficheros:
        return pd.DataFrame()
    return pd.concat([pd.read_parquet(f) for f in ficheros], ignore_index=True)


def barra(frac: float, ancho: int = 30) -> str:
    n = int(round(max(0.0, min(1.0, frac)) * ancho))
    return "█" * n + "·" * (ancho - n)


def h(titulo: str) -> None:
    print("\n" + "=" * 74)
    print("  " + titulo)
    print("=" * 74)


# --------------------------------------------------------------------------- #
def main(root: Path, umbral_m: float) -> int:
    buses = cargar(root, "emt_buses")
    trafico = cargar(root, "trafico_estado")
    intens = cargar(root, "trafico_intensidad")
    ref = root / "reference" / "trafico_estado_geometria.parquet"

    if buses.empty:
        print(
            "No hay datos de emt_buses. Lanza antes:  python demo/collect.py --minutes 1440"
        )
        return 1
    if trafico.empty or not ref.exists():
        print("Faltan datos de trafico_estado o su fichero de geometría.")
        print("Asegúrate de incluir trafico_estado en --sources al capturar.")
        return 1

    tramos = pd.read_parquet(ref)
    buses["ts_utc"] = pd.to_datetime(buses["ts_utc"], utc=True)
    trafico["ts_utc"] = pd.to_datetime(trafico["ts_utc"], utc=True)

    horas = (buses["ts_utc"].max() - buses["ts_utc"].min()).total_seconds() / 3600
    print(
        f"\nCaptura: {horas:.1f} h  |  {len(buses):,} posiciones de bus  "
        f"|  {len(trafico):,} lecturas de tráfico  |  {len(tramos)} tramos"
    )
    if horas < 12:
        print(
            "  AVISO: menos de 12 h capturadas. Sin hora punta de laborable los\n"
            "  resultados 2 y 4 no son concluyentes. Repite con --minutes 1440."
        )

    veredictos = {}

    # ---------------------------------------------------------------- 1
    h("1. COBERTURA — ¿los buses circulan por donde hay dato de tráfico?")
    b = asignar_tramo(buses, tramos)
    for u in (25, 50, 100, 200):
        frac = float((b["dist_tramo_m"] <= u).mean())
        print(f"  ≤ {u:4d} m   {barra(frac)}  {frac:6.1%}")
    cob = float((b["dist_tramo_m"] <= umbral_m).mean())
    lineas_cub = b[b["dist_tramo_m"] <= umbral_m].groupby("linea").size()
    lineas_tot = b.groupby("linea").size()
    frac_linea = (lineas_cub / lineas_tot).dropna().sort_values()
    print(f"\n  Cobertura a {umbral_m:.0f} m: {cob:.1%} de las posiciones")
    print(
        f"  Líneas con >50 % de cobertura: {(frac_linea > 0.5).sum()} de {len(lineas_tot)}"
    )
    if len(frac_linea):
        peor = ", ".join(f"{i}({v:.0%})" for i, v in frac_linea.head(5).items())
        mejor = ", ".join(f"{i}({v:.0%})" for i, v in frac_linea.tail(5).items())
        print(f"  Peor cubiertas : {peor}")
        print(f"  Mejor cubiertas: {mejor}")
    veredictos["cobertura"] = (
        "OK" if cob >= 0.6 else "PARCIAL" if cob >= 0.3 else "MALA"
    )
    print(
        f"\n  --> {veredictos['cobertura']}"
        + ("" if cob >= 0.6 else "  (limita el alcance a los corredores cubiertos)")
    )

    # ---------------------------------------------------------------- 2
    h("2. VARIANZA — ¿el `estado` varía o está congelado?")
    tr = trafico.dropna(subset=["estado"]).copy()
    tr["hora_local"] = tr["ts_utc"].dt.tz_convert("Europe/Madrid").dt.hour
    glob = tr["estado"].value_counts(normalize=True).sort_index()
    print("  Distribución global de `estado`:")
    for e, f in glob.items():
        print(f"    estado {int(e)}   {barra(f)}  {f:6.1%}")
    nulos = float(trafico["estado"].isna().mean())
    print(f"  Nulos: {nulos:.1%} de las lecturas")

    print("\n  Fracción NO fluida (estado != 0) por hora local:")
    por_hora = tr.groupby("hora_local")["estado"].apply(
        lambda s: float((s != 0).mean())
    )
    for hh, f in por_hora.items():
        marca = "  <-- punta" if f == por_hora.max() and f > 0 else ""
        print(f"    {hh:02d}h  {barra(f, 24)}  {f:6.1%}{marca}")
    pico = float(por_hora.max()) if len(por_hora) else 0.0
    veredictos["varianza"] = (
        "OK" if pico >= 0.15 else "DEBIL" if pico >= 0.05 else "SIN VARIANZA"
    )
    print(
        f"\n  Máximo horario de congestión: {pico:.1%}  -->  {veredictos['varianza']}"
    )

    # ---------------------------------------------------------------- 3
    h("3. DINÁMICA — ¿hay tramos congelados que finjan ser dato?")
    tr = tr.sort_values("ts_utc")
    cambios = tr.groupby("idtramo")["estado"].apply(
        lambda s: int((s.diff() != 0).sum() - 1)
    )
    congelados = int((cambios <= 0).sum())
    print(
        f"  Tramos que nunca cambian de estado : {congelados} de {len(cambios)} "
        f"({congelados / max(len(cambios), 1):.0%})"
    )
    print(
        f"  Cambios por tramo: mediana {cambios.median():.0f}, "
        f"p90 {cambios.quantile(0.9):.0f}, máx {cambios.max():.0f}"
    )
    veredictos["dinamica"] = (
        "OK" if congelados / max(len(cambios), 1) < 0.5 else "SOSPECHOSA"
    )
    print(f"\n  --> {veredictos['dinamica']}")

    # ---------------------------------------------------------------- 4
    h("4. SEÑAL — ¿los buses van más lentos donde el tráfico está peor?")
    print("  (el test decisivo: no necesita GTFS ni etiquetas)\n")
    b = rastrear(b)
    b = b.dropna(subset=["vel_kmh"])
    b = b[(b["dist_tramo_m"] <= umbral_m) & (b["vel_kmh"] <= 70)]
    if b.empty:
        print("  Sin posiciones emparejadas con velocidad. Captura más tiempo.")
        return 1

    izq = (
        b[["ts_utc", "idtramo_cercano", "vel_kmh"]]
        .rename(columns={"idtramo_cercano": "idtramo"})
        .sort_values("ts_utc")
    )
    der = tr[["ts_utc", "idtramo", "estado"]].sort_values("ts_utc")
    izq["idtramo"] = izq["idtramo"].astype(str)
    der["idtramo"] = der["idtramo"].astype(str)
    m = pd.merge_asof(
        izq,
        der,
        on="ts_utc",
        by="idtramo",
        tolerance=pd.Timedelta("3min"),
        direction="nearest",
    ).dropna(subset=["estado"])

    print(f"  Posiciones bus emparejadas con estado de tramo: {len(m):,}\n")
    if len(m) < 200:
        print("  Muestra insuficiente para concluir. Captura más tiempo.")
        veredictos["senal"] = "INSUFICIENTE"
    else:
        g = m.groupby("estado")["vel_kmh"].agg(["count", "median", "mean"])
        print("  Velocidad de los buses según el estado del tramo que pisan:")
        print("    estado      n    mediana    media")
        for e, r in g.iterrows():
            print(
                f"      {int(e)}   {int(r['count']):7,}   {r['median']:6.1f}   {r['mean']:6.1f} km/h"
            )

        base = g.loc[g.index.min(), "median"]
        peor = g.loc[g.index.max(), "median"]
        caida = (base - peor) / base if base else 0.0
        print(f"\n  Caída de velocidad del mejor al peor estado: {caida:+.1%}")

        try:
            from scipy import stats

            grupos = [
                v["vel_kmh"].to_numpy() for _, v in m.groupby("estado") if len(v) > 20
            ]
            if len(grupos) >= 2:
                kw = stats.kruskal(*grupos)
                rho = stats.spearmanr(m["estado"], m["vel_kmh"])
                print(f"  Kruskal-Wallis  H={kw.statistic:.1f}  p={kw.pvalue:.2e}")
                print(
                    f"  Spearman estado vs velocidad  rho={rho.statistic:+.3f}  "
                    f"p={rho.pvalue:.2e}"
                )
        except ImportError:
            print("  (instala scipy para los contrastes estadísticos)")

        veredictos["senal"] = (
            "SEÑAL CLARA"
            if caida >= 0.20
            else "SEÑAL DEBIL"
            if caida >= 0.08
            else "SIN SEÑAL"
        )
        print(f"\n  --> {veredictos['senal']}")

    # ------------------------------------------------ 4b: intensidad continua
    if not intens.empty:
        h("4b. PLAN B — intensidad medida (veh/h) en vez del estado categórico")
        intens["ts_utc"] = pd.to_datetime(intens["ts_utc"], utc=True)
        di = intens.dropna(subset=["lectura"])[["ts_utc", "idtramo", "lectura"]].copy()
        di["idtramo"] = di["idtramo"].astype(str)
        mi = pd.merge_asof(
            izq,
            di.sort_values("ts_utc"),
            on="ts_utc",
            by="idtramo",
            tolerance=pd.Timedelta("6min"),
            direction="nearest",
        ).dropna(subset=["lectura"])
        if len(mi) >= 200:
            try:
                from scipy import stats

                r = stats.spearmanr(mi["lectura"], mi["vel_kmh"])
                print(
                    f"  n={len(mi):,}   Spearman intensidad vs velocidad  "
                    f"rho={r.statistic:+.3f}  p={r.pvalue:.2e}"
                )
                print(
                    "  (una rho negativa y significativa es exactamente lo que buscas)"
                )
            except ImportError:
                print(f"  n={len(mi):,}  (instala scipy para la correlación)")
        else:
            print(f"  Solo {len(mi)} emparejamientos: los tramos de la capa 188 no")
            print("  coinciden con los de la 192, o falta captura.")

    # ---------------------------------------------------------------- fin
    h("VEREDICTO")
    for k, v in veredictos.items():
        print(f"  {k:12} {v}")
    senal = veredictos.get("senal", "")
    print()
    if senal == "SEÑAL CLARA":
        print("  Adelante. La hipótesis central se sostiene: hay relación medible")
        print("  entre el estado del tráfico y la velocidad de los buses.")
    elif senal == "SEÑAL DEBIL":
        print("  Continúa, pero baja las expectativas y prepara el argumento: la")
        print("  aportación pasa a ser cuantificar una señal pequeña, no explotarla.")
        print("  Mira si 4b (intensidad continua) se comporta mejor.")
    elif senal == "SIN SEÑAL":
        print("  Para y replantea. Antes de abandonar el tema, comprueba 4b: si la")
        print("  intensidad continua sí correlaciona, cambia de variable y sigue.")
        print("  Si tampoco, el retraso se predice sin tráfico y el trabajo pasa a")
        print("  ser sobre la reconstrucción del dataset, que sigue siendo válido.")
    else:
        print("  Sin datos suficientes. Repite tras una captura de 24 h que incluya")
        print("  una hora punta de día laborable.")
    print()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--data", type=Path, default=Path("data"))
    p.add_argument("--umbral-m", type=float, default=50.0)
    a = p.parse_args()
    raise SystemExit(main(a.data, a.umbral_m))
