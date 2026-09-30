"""¿Qué parte de cada línea llega a la etiqueta, y qué la pierde por el camino?

    uv run python -m project.analysis.medir_rutas lineas
    uv run python -m project.analysis.medir_rutas rupturas --dia 2026-08-20
    uv run python -m project.analysis.medir_rutas contrafactual --dia 2026-08-20
    uv run python -m project.analysis.medir_rutas alternancia --dia 2026-08-20
    uv run python -m project.analysis.medir_rutas colisiones

Cinco medidas, todas sobre la salida de `prepare` (`data/interim/`) salvo el
contrafactual y la alternancia, que leen `data/curated/`:

  LINEAS         por línea: posiciones, trayectorias, tramos, asignados y pasos.
                 La tasa de éxito de `medir_etiquetado` deja fuera los tramos
                 cortos; aquí van dentro, porque es donde acaba una línea
                 entera cuando el tracker la trocea (bitácora 026).
                 `pos_asignadas` es la fracción de las posiciones de la línea,
                 en días no excluidos, que cae en un viaje asignado (bitácora
                 036).
  RUPTURAS       para cada trayectoria que termina entre las 7 y las 21 h, la
                 sucesora más cercana del mismo (línea, trayecto) que empieza
                 en los dos sondeos siguientes: distancia, velocidad con el
                 reloj de sondeo (la que ve la puerta física del tracker) y con
                 el `ts_utc` del propio bus. Y dónde caen, por latitud.
  CONTRAFACTUAL  rastrea las líneas 24, 25 y 31 del día con la puerta de
                 `tracking.py` y con la puerta abierta a 100 km/h y 1.200 m. Si
                 las trayectorias se alargan al abrirla, la puerta es la causa.
  ALTERNANCIA    fracción de pasos de un mismo bus, lejos de cabecera, en los
                 que la fuente publica el trayecto contrario (bitácora 026).
  COLISIONES     `viaje_id` repetidos entre particiones diarias de `prepare`,
                 `trip_id` asignados dos veces el mismo día de servicio y pasos
                 duplicados (bitácora 027).

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse

import duckdb
import numpy as np
import pandas as pd

from project import tracking
from project.config import settings
from project.ingest.sources import haversine_m
from project.prepare import cargar_dia

FRANJAS_LAT = [39.20, 39.30, 39.36, 39.40, 39.43, 39.46, 39.50]


def _tabla(nombre: str) -> str:
    raiz = settings.interim_dir / nombre
    return (
        f"read_parquet('{(raiz / '*' / '*.parquet').as_posix()}', "
        # union_by_name: los días excluidos (bitácora 024) no traen trip_id.
        "filename = true, hive_partitioning = false, union_by_name = true)"
    )


def lineas() -> None:
    duckdb.sql("set TimeZone = 'UTC'")
    t, v, p = _tabla("emt_tracked"), _tabla("viajes"), _tabla("pasos")
    d = duckdb.sql(
        f"""
        with pos as (
            select linea, count(*) posiciones,
                   count(distinct filename || vehicle_id) trayectorias
            from {t} group by 1),
        tra as (
            select linea, count(*) tramos,
                   sum((motivo = 'asignado')::int) asignados,
                   sum((motivo = 'corto')::int) cortos,
                   coalesce(sum(posiciones) filter (where motivo = 'asignado'), 0)
                       / sum(posiciones) filter (where motivo <> 'excluido')
                       pos_asignadas
            from {v} group by 1),
        pas as (select linea, count(*) pasos from {p} group by 1)
        select * from pos left join tra using (linea) left join pas using (linea)
        """
    ).df()
    d["pasos"] = d["pasos"].fillna(0).astype(int)
    d["pos_por_trayectoria"] = (d["posiciones"] / d["trayectorias"]).round(1)
    d["exito_con_cortos"] = (d["asignados"] / d["tramos"]).round(3)
    d["pos_asignadas"] = d["pos_asignadas"].round(3)
    d["cuota_posiciones"] = (d["posiciones"] / d["posiciones"].sum()).round(4)
    d["cuota_pasos"] = (d["pasos"] / d["pasos"].sum()).round(4)
    print(d.sort_values("exito_con_cortos").to_string(index=False))
    costa = d[d["linea"].isin(["24", "25"])]
    print(
        f"\n  24 + 25: {costa['posiciones'].sum():,} de {d['posiciones'].sum():,} "
        f"posiciones ({costa['cuota_posiciones'].sum():.2%}) y "
        f"{costa['pasos'].sum():,} de {d['pasos'].sum():,} pasos "
        f"({costa['cuota_pasos'].sum():.2%})"
    )


def _rastreado(dia: str) -> pd.DataFrame:
    duckdb.sql("set TimeZone = 'UTC'")
    t = _tabla("emt_tracked").replace("/*/", f"/date={dia}/")
    return duckdb.sql(f"select * from {t}").df()


def rupturas(dia: str, lineas_: list[str]) -> None:
    df = _rastreado(dia)
    # El reloj de sondeo del tracker: el `ts_utc` más reciente de cada sondeo.
    reloj = df.groupby("snapshot_id")["ts_utc"].max()
    orden = {s: i for i, s in enumerate(sorted(reloj.index))}
    df["k"] = df["snapshot_id"].map(orden)
    df["hora"] = df["ts_utc"].dt.tz_convert(settings.tz_local).dt.hour
    for linea in lineas_:
        g = df[(df["linea"] == linea) & df["hora"].between(7, 21)].sort_values("k")
        fin = g.groupby("vehicle_id").tail(1)
        ini = g.groupby("vehicle_id").head(1)
        filas = []
        for _, f in fin.iterrows():
            c = ini[
                (ini["trayecto"] == f["trayecto"])
                & (ini["k"] > f["k"])
                & (ini["k"] <= f["k"] + 2)
            ]
            if c.empty:
                continue
            d = haversine_m(
                f["lat"], f["lon"], c["lat"].to_numpy(), c["lon"].to_numpy()
            )
            j = int(np.argmin(d))
            s = c.iloc[j]
            dt_reloj = (
                reloj[s["snapshot_id"]] - reloj[f["snapshot_id"]]
            ).total_seconds()
            dt_bus = (s["ts_utc"] - f["ts_utc"]).total_seconds()
            filas.append(
                (
                    d[j],
                    d[j] / dt_reloj * 3.6 if dt_reloj > 0 else np.nan,
                    d[j] / dt_bus * 3.6 if dt_bus > 0 else np.nan,
                )
            )
        r = pd.DataFrame(filas, columns=["d_m", "v_reloj", "v_bus"])
        print(
            f"\n  línea {linea}, {dia}, 7-21 h: {g['vehicle_id'].nunique()} trayectorias, "
            f"{len(r)} con sucesora en <= 2 sondeos"
        )
        if r.empty:
            continue
        print(
            f"    distancia p50 / p90: {r['d_m'].median():.0f} / "
            f"{r['d_m'].quantile(0.9):.0f} m · > {tracking.SALTO_MAX_M:.0f} m: "
            f"{(r['d_m'] > tracking.SALTO_MAX_M).mean():.0%}"
        )
        print(
            f"    velocidad con reloj de sondeo p50: {r['v_reloj'].median():.1f} km/h · "
            f"> {tracking.VEL_MAX_KMH:.0f}: {(r['v_reloj'] > tracking.VEL_MAX_KMH).mean():.0%}"
        )
        print(
            f"    velocidad con ts_utc del bus p50: {r['v_bus'].median():.1f} km/h · "
            f"<= 90: {(r['v_bus'] <= 90).mean():.0%}"
        )
        franja_fin = pd.cut(fin["lat"], FRANJAS_LAT).value_counts().sort_index()
        franja_pos = pd.cut(g["lat"], FRANJAS_LAT).value_counts().sort_index()
        tasa = (franja_fin / franja_pos).round(3)
        print("    rupturas por posición, por franja de latitud:")
        for iv in tasa.index:
            print(
                f"      {iv}: {franja_fin[iv]:>5} / {franja_pos[iv]:>6} = {tasa[iv]:.1%}"
            )


def _resumen_tracker(df: pd.DataFrame) -> dict:
    largo = df.groupby("vehicle_id").size()
    return {
        "trayectorias": len(largo),
        "pos_por_trayectoria_p50": float(largo.median()),
    }


def contrafactual(dia: str, lineas_: list[str]) -> None:
    df = cargar_dia(dia)
    base_vel, base_salto = tracking.VEL_MAX_KMH, tracking.SALTO_MAX_M
    for linea in lineas_:
        sub = df[(df["linea"].astype(str) == linea) & df["trayecto"].notna()]
        if sub.empty:
            print(f"  línea {linea}: sin posiciones el {dia}")
            continue
        try:
            actual = _resumen_tracker(tracking.rastrear(sub))
            tracking.VEL_MAX_KMH, tracking.SALTO_MAX_M = 100.0, 1200.0
            abierta = _resumen_tracker(tracking.rastrear(sub))
        finally:
            tracking.VEL_MAX_KMH, tracking.SALTO_MAX_M = base_vel, base_salto
        print(
            f"  línea {linea}, {dia}: {len(sub):,} posiciones · "
            f"puerta {base_vel:.0f} km/h, {base_salto:.0f} m: {actual['trayectorias']} "
            f"trayectorias, p50 {actual['pos_por_trayectoria_p50']:.0f} posiciones · "
            f"puerta 100 km/h, 1200 m: {abierta['trayectorias']} trayectorias, "
            f"p50 {abierta['pos_por_trayectoria_p50']:.0f} posiciones"
        )


def alternancia(dia: str, lineas_: list[str]) -> None:
    """¿Publica la fuente el `trayecto` contrario para el mismo bus a mitad de ruta?

    Empareja por distancia, sin mirar el trayecto, las posiciones de una línea en
    sondeos consecutivos (a menos de 700 m) y cuenta los pares que cambian de
    texto lejos de cabecera, a más de 1 km del extremo de cualquier trazado de la
    línea. Un cambio así puede ser también dos buses opuestos que se cruzan: se
    descuenta si en el sondeo siguiente hay un bus con el trayecto original a
    menos de 700 m. Lo que queda es la alternancia limpia, una cota inferior.
    """
    from scipy.optimize import linear_sum_assignment

    from project.gtfs import a_grados, cargar_horario, elegir_horario, versiones

    df = cargar_dia(dia)
    df = df[df["trayecto"].notna()]
    hora = df["ts_utc"].dt.tz_convert(settings.tz_local).dt.hour
    df = df[hora.between(7, 21)]
    horarios = [cargar_horario(r) for r in versiones(settings.gtfs_dir)]
    h, _ = elegir_horario(horarios, pd.Timestamp(dia).date())
    sondeos = np.sort(df["snapshot_id"].unique())
    for linea in lineas_:
        extremos = []
        for t in h.trazados.get(linea, []) if h is not None else []:
            for i in (0, -1):
                extremos.append(a_grados(t.x[i], t.y[i]))
        g = df[df["linea"].astype(str) == linea]
        por_sondeo = {s: x for s, x in g.groupby("snapshot_id")}
        pares = cambia = cruce = 0
        for sa, sb in zip(sondeos[:-1], sondeos[1:]):
            a, b = por_sondeo.get(sa), por_sondeo.get(sb)
            if a is None or b is None:
                continue
            d = np.array(
                [
                    haversine_m(r.lat, r.lon, b["lat"].to_numpy(), b["lon"].to_numpy())
                    for r in a.itertuples()
                ]
            )
            for i, j in zip(*linear_sum_assignment(d)):
                if d[i, j] > 700:
                    continue
                ra, rb = a.iloc[i], b.iloc[j]
                if (
                    extremos
                    and min(
                        haversine_m(ra["lat"], ra["lon"], la, lo) for la, lo in extremos
                    )
                    < 1000
                ):
                    continue
                pares += 1
                if ra["trayecto"] == rb["trayecto"]:
                    continue
                cambia += 1
                mismo = b[b["trayecto"] == ra["trayecto"]]
                if (
                    len(mismo)
                    and haversine_m(
                        ra["lat"],
                        ra["lon"],
                        mismo["lat"].to_numpy(),
                        mismo["lon"].to_numpy(),
                    ).min()
                    <= 700
                ):
                    cruce += 1
        if pares == 0:
            print(f"  línea {linea}, {dia}: sin pares lejos de cabecera")
            continue
        print(
            f"  línea {linea}, {dia}: {pares:,} pares a > 1 km de cabecera · cambia el "
            f"trayecto {cambia} ({cambia / pares:.1%}) · posible cruce {cruce} · "
            f"alternancia limpia {(cambia - cruce) / pares:.1%}"
        )


def colisiones() -> None:
    duckdb.sql(f"set TimeZone = '{settings.tz_local}'")
    v, p = _tabla("viajes"), _tabla("pasos")
    rep = duckdb.sql(
        f"""
        with r as (select viaje_id from {v} group by 1 having count(*) > 1)
        select v.viaje_id, v.filename, v.linea, v.t_inicio, v.motivo
        from {v} v join r using (viaje_id)
        """
    ).df()
    g = rep.groupby("viaje_id").agg(
        particiones=("filename", "nunique"), lineas=("linea", "nunique")
    )
    print(
        f"  viaje_id repetidos: {len(g)} ({len(rep)} filas), en particiones distintas: "
        f"{(g['particiones'] > 1).sum()}, con líneas distintas: {(g['lineas'] > 1).sum()}"
    )
    horas = rep["t_inicio"].dt.hour.value_counts().sort_index()
    print(f"  hora local de inicio de las filas repetidas: {horas.to_dict()}")
    print(f"  motivo de las filas repetidas: {rep['motivo'].value_counts().to_dict()}")
    dobles = duckdb.sql(
        f"""
        select count(*) from (
            select fecha_servicio, trip_id from {v} where motivo = 'asignado'
            group by 1, 2 having count(*) > 1)
        """
    ).fetchone()[0]
    pasos = duckdb.sql(
        f"""
        select count(*) from (
            select viaje_id, stop_sequence from {p} group by 1, 2 having count(*) > 1)
        """
    ).fetchone()[0]
    print(f"  trip_id asignados dos veces el mismo día de servicio: {dobles}")
    print(f"  pares (viaje_id, stop_sequence) repetidos en pasos: {pasos}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="medida", required=True)
    sub.add_parser("lineas")
    for nombre in ("rupturas", "contrafactual", "alternancia"):
        s = sub.add_parser(nombre)
        s.add_argument("--dia", default="2026-08-20")
        s.add_argument("--lineas", nargs="+", default=["24", "25", "31"])
    sub.add_parser("colisiones")
    a = ap.parse_args()
    if a.medida == "lineas":
        lineas()
    elif a.medida == "rupturas":
        rupturas(a.dia, a.lineas)
    elif a.medida == "contrafactual":
        contrafactual(a.dia, a.lineas)
    elif a.medida == "alternancia":
        alternancia(a.dia, a.lineas)
    else:
        colisiones()


if __name__ == "__main__":
    main()
