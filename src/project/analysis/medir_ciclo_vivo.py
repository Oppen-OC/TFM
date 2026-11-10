"""Cuánto tarda un ciclo de la demo en vivo, sobre un día capturado de verdad.

    uv run python -m project.analysis.medir_ciclo_vivo --dia 2026-10-01 \\
        --hasta 10:00 --comprobar-lineas

Cada ciclo de la demo relee el crudo del día, reetiqueta las posiciones con las
funciones del pipeline y construye las variables de la parada. Esto mide cada
paso sobre un día ya capturado, recortado a la hora local `--hasta`, para fijar
el periodo de refresco. Solo lectura: el JSON sale por stdout y nada se escribe
bajo `data/`, `metrics/` ni `models/`.

`segundos_total` suma solo los pasos de cada ciclo (lectura del crudo, etiquetado,
disponibilidad y construcción). Los costes de arranque (cargar el GTFS, cargar los
pasos históricos con su `t_disp`) van aparte: se pagan una vez.

`--comprobar-lineas` etiqueta el día con todas las líneas y con las de la parada
y compara los pasos de esas líneas. La clave no es `CLAVE_PASO`: `viaje_id` lleva
el `vehicle_id`, que se numera entre todas las líneas, así que recortar renumera
vehículos sin cambiar ningún paso. Se compara el multiconjunto de filas. Y se
repite recortando con el reloj por sondeo de todas las líneas
(`con_reloj_de_todas`): si así sale idéntico, la diferencia es solo ese reloj.

Con `--comprobar-lineas` se cronometra además la variante de etiquetar todas las
líneas cada ciclo (`etiquetar_dia_todas`, `segundos_total_todas`): `segundos` ya
refleja esos pasos, `segundos_total` no cambia de significado.

Comparte con la demo `con_reloj_de_todas`, `ficheros_del_dia` y `elegir_capturas`
(`analysis/` puede importar de `services/` e `ingest/`, no al revés). Está fuera
del grafo de DVC: nada del pipeline importa de aquí.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, datetime, time as hora_del_dia, timedelta

import pandas as pd
import yaml

from project.config import RAIZ, settings
from project.etiquetado import HORA_CORTE
from project.features import (
    con_disponibilidad,
    construir,
    instante_disponible,
    ventanas_flota,
)
from project.gtfs import cargar_horario, elegir_horario, versiones
from project.ingest.reprocesar import elegir_capturas
from project.prepare import (
    cargar_parametros,
    etiquetar_dia,
    ventana_servicio,
)
from project.services.vivo import con_reloj_de_todas, ficheros_del_dia

CLAVE_COMPARACION = [
    "fecha_servicio",
    "linea",
    "trayecto",
    "trip_id",
    "stop_sequence",
    "t_obs_utc",
    "retraso_s",
]


class Reloj:
    """Segundos de cada paso con nombre."""

    def __init__(self) -> None:
        self.s: dict[str, float] = {}

    def __call__(self, nombre: str):
        reloj = self

        class _Paso:
            def __enter__(self):
                self.t0 = time.perf_counter()

            def __exit__(self, *_):
                reloj.s[nombre] = round(time.perf_counter() - self.t0, 3)

        return _Paso()


def hasta_utc(dia: str, hasta: str) -> pd.Timestamp:
    """`hasta` es hora local del día de servicio: antes de `HORA_CORTE`, ya del
    día natural siguiente."""
    h = hora_del_dia.fromisoformat(hasta)
    d = date.fromisoformat(dia) + timedelta(days=int(h.hour < HORA_CORTE))
    return pd.Timestamp(datetime.combine(d, h), tz=settings.tz_local).tz_convert("UTC")


def parada_y_lineas(horario, dia: str, stop: str | None) -> tuple[str, list[str]]:
    """Las líneas que paran en `stop`; sin él, la parada con más líneas ese día."""
    viajes = horario.viajes[
        horario.viajes["service_id"].isin(horario.servicios(date.fromisoformat(dia)))
    ]
    pv = horario.paradas_de_viaje[["trip_id", "stop_id"]].merge(
        viajes[["trip_id", "linea"]], on="trip_id"
    )
    if stop is None:
        stop = str(pv.groupby("stop_id")["linea"].nunique().idxmax())
    lineas = sorted(pv.loc[pv["stop_id"] == stop, "linea"].unique())
    if not lineas:
        raise SystemExit(f"la parada {stop} no tiene viajes el {dia}")
    return stop, lineas


def leer_crudo(dia: str, hasta: pd.Timestamp) -> dict:
    """Lo que hace cada ciclo con el crudo: `elegir_capturas`, la captura más
    completa de cada sondeo (trampa 011) y solo payloads con filas (trampa 018),
    hasta `hasta`.

    Devuelve también el frame de posiciones con el filtro de `prepare.cargar_dia`
    (ventana de servicio, lat/lon no nulos, `ts_utc <= hasta`) y las `llegadas`
    de esa misma población: frame y llegadas no pueden desencontrarse."""
    desde, fin = ventana_servicio(dia)
    c = elegir_capturas(
        ficheros_del_dia(settings.raw_dir / "source=emt_buses", hasta),
        "emt_buses",
        tolerar_cola=True,
    )
    # ponytail: una captura completada tras `hasta` descarta el sondeo entero, no
    # vuelve a la primera (como `Vivo._leer_hoy`).
    frame = pd.concat([d for _, d in c.elegidos.values()], ignore_index=True)
    frame = frame[frame["ts_ingest_utc"] <= hasta]
    filas, sondeos = len(frame), int(frame["snapshot_id"].nunique())
    frame = frame[
        frame["lat"].notna()
        & frame["lon"].notna()
        & (frame["ts_utc"] >= desde)
        & (frame["ts_utc"] < fin)
        & (frame["ts_utc"] <= hasta)
    ]
    # `snapshot_id` -> cuándo llegó a nuestro disco, lo que pide `instante_disponible`.
    g = frame.groupby("snapshot_id")["ts_ingest_utc"].min()
    llegadas = pd.Series(pd.to_datetime(g, utc=True).to_numpy(), index=g.index)
    return {
        "payloads": c.payloads,
        "sondeos": sondeos,
        "filas": filas,
        "llegadas": llegadas,
        "frame": frame[["snapshot_id", "linea", "trayecto", "lat", "lon", "ts_utc"]],
    }


def historico(dia: str, version: str, lineas: list[str]) -> pd.DataFrame:
    """Pasos de las líneas, de los días anteriores con la misma versión del feed,
    con su `t_disp_utc` ya calculado por el pipeline."""
    carpeta = settings.interim_dir / "pasos"
    filtros = [("feed_version", "==", version), ("linea", "in", lineas)]
    trozos = [
        pd.read_parquet(f, filters=filtros)
        for d in sorted(carpeta.glob("date=*"))
        if d.name[5:] < dia
        for f in d.glob("*.parquet")
    ]
    pasos = pd.concat([t for t in trozos if len(t)], ignore_index=True)
    return con_disponibilidad(
        pasos, pd.read_parquet(settings.interim_dir / "disponibilidad")
    )


def con_t_disp(
    pasos: pd.DataFrame, posiciones, llegadas, cfg: dict, corte: pd.Timestamp
) -> tuple[pd.DataFrame, int]:
    """`pasos` con su `t_disp_utc`; error si falta alguno y se descartan los que
    solo se sabrían después del «ahora» (`corte`). Devuelve también cuántos."""
    pasos = pasos.reset_index(drop=True)
    pasos["t_disp_utc"] = instante_disponible(
        pasos,
        posiciones,
        llegadas,
        max_hueco_s=cfg["prepare"]["max_hueco_cruce_s"],
        paradas_referencia=cfg["prepare"]["paradas_referencia"],
    )
    sin = int(pasos["t_disp_utc"].isna().sum())
    if sin:
        raise ValueError(f"{sin} pasos sin t_disp: frame y llegadas no coinciden")
    futuros = pasos["t_disp_utc"] > corte
    return pasos[~futuros].reset_index(drop=True), int(futuros.sum())


def comparar(todas: pd.DataFrame, recortadas: pd.DataFrame, lineas: list[str]) -> dict:
    """Multiconjunto de filas de los pasos de `lineas`, etiquetando con todas las
    líneas contra etiquetando solo con ellas."""

    def f(df: pd.DataFrame) -> pd.DataFrame:
        df = df[df["linea"].isin(lineas)][CLAVE_COMPARACION].copy()
        df["fecha_servicio"] = pd.to_datetime(df["fecha_servicio"])
        df = df.sort_values(CLAVE_COMPARACION, kind="stable").reset_index(drop=True)
        return df.assign(_n=df.groupby(CLAVE_COMPARACION, dropna=False).cumcount())

    a, b = f(todas), f(recortadas)
    m = a.merge(b, how="outer", indicator=True, on=[*CLAVE_COMPARACION, "_n"])
    cuenta = m["_merge"].value_counts()
    difieren = m[m["_merge"] != "both"]
    return {
        "filas_con_todas": len(a),
        "filas_recortadas": len(b),
        "solo_con_todas": int(cuenta.get("left_only", 0)),
        "solo_recortadas": int(cuenta.get("right_only", 0)),
        "identico": bool(len(a) == len(b) and difieren.empty),
        "ejemplos": difieren.head(6).astype(str).to_dict("records"),
    }


def main(dia: str, hasta: str, stop: str | None, comprobar: bool) -> dict:
    t = Reloj()
    p = cargar_parametros()
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    corte = hasta_utc(dia, hasta)

    # --- arranque: se paga una vez --------------------------------------- #
    with t("cargar_gtfs"):
        horarios = [cargar_horario(r) for r in versiones(settings.gtfs_dir)]
    horario, _ = elegir_horario(horarios, date.fromisoformat(dia))
    stop, lineas = parada_y_lineas(horario, dia, stop)
    with t("cargar_historico"):
        hist = historico(dia, horario.version, lineas)

    # --- ciclo ------------------------------------------------------------ #
    with t("lectura_crudo"):
        crudo = leer_crudo(dia, corte)
    llegadas = crudo.pop("llegadas")
    frame = crudo.pop("frame")
    df = frame[frame["linea"].isin(lineas)]
    with t("etiquetar_dia"):
        r = etiquetar_dia(df, horarios, p)

    posiciones = r.posiciones[r.posiciones["viaje_id"].notna() & r.posiciones["fiable"]]
    with t("instante_disponible"):
        pasos, descartados = con_t_disp(r.pasos, posiciones, llegadas, cfg, corte)
    todos = pd.concat([hist, pasos], ignore_index=True)
    f = cfg["features"]
    with t("construir"):
        tabla = construir(
            todos,
            objetivo=f["objetivo"],
            horizonte=2,
            lags_min=tuple(f["lags_min"]),
            umbral_s=f["umbral_retraso_s"],
            ventanas_flota_min=ventanas_flota(f),
            soporte_min=f["soporte_min"],
        )

    ciclo = ["lectura_crudo", "etiquetar_dia", "instante_disponible", "construir"]
    out = {
        "dia": dia,
        "hasta_local": hasta,
        "hasta_utc": corte.isoformat(),
        "parada": stop,
        "lineas": lineas,
        "feed_version": horario.version,
        "dias_historico": int(hist["fecha_servicio"].nunique()),
        "pasos_descartados_t_disp_posterior": descartados,
        "segundos": t.s,
        "segundos_total": round(sum(t.s[k] for k in ciclo), 3),
        "pasos_del_ciclo": ciclo,
        "filas_entrada": {
            "lectura_crudo": crudo,
            "etiquetar_dia": len(df),
            "instante_disponible": len(pasos),
            "construir": len(todos),
            "construir_historico": len(hist),
            "tabla": len(tabla),
        },
    }
    if comprobar:
        # La variante «todas las líneas»: se etiqueta todo el día y se queda con
        # los pasos de la parada; disponibilidad y construcción, sobre esos pasos
        # (con todas las posiciones fiables, que es lo que habría a mano).
        with t("etiquetar_dia_todas"):
            completo = etiquetar_dia(frame, horarios, p)
        out["filas_entrada"]["etiquetar_dia_todas"] = len(frame)
        out["comprobacion_lineas"] = comparar(completo.pasos, r.pasos, lineas)
        out["recorte_lineas_identico"] = out["comprobacion_lineas"]["identico"]
        # ¿Es solo el reloj del sondeo? Recortado, con el de todas las líneas.
        con_reloj = con_reloj_de_todas(frame, lineas)
        with t("etiquetar_dia_con_reloj"):
            rr = etiquetar_dia(con_reloj, horarios, p)
        out["filas_entrada"]["etiquetar_dia_con_reloj"] = len(con_reloj)
        out["comprobacion_reloj"] = comparar(completo.pasos, rr.pasos, lineas)
        out["recorte_con_reloj_identico"] = out["comprobacion_reloj"]["identico"]

        pos = completo.posiciones
        pos = pos[pos["viaje_id"].notna() & pos["fiable"]]
        pa = completo.pasos[completo.pasos["linea"].isin(lineas)]
        with t("instante_disponible_todas"):
            pa, desc_todas = con_t_disp(pa, pos, llegadas, cfg, corte)
        out["pasos_descartados_t_disp_posterior_todas"] = desc_todas
        with t("construir_todas"):
            construir(
                pd.concat([hist, pa], ignore_index=True),
                objetivo=f["objetivo"],
                horizonte=2,
                lags_min=tuple(f["lags_min"]),
                umbral_s=f["umbral_retraso_s"],
                ventanas_flota_min=ventanas_flota(f),
                soporte_min=f["soporte_min"],
            )
        out["filas_entrada"]["instante_disponible_todas"] = len(pa)
        out["filas_entrada"]["construir_todas"] = len(hist) + len(pa)
        out["segundos_total_todas"] = round(
            t.s["lectura_crudo"]
            + t.s["etiquetar_dia_todas"]
            + t.s["instante_disponible_todas"]
            + t.s["construir_todas"],
            3,
        )
    return out


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--dia", required=True)
    a.add_argument(
        "--hasta", required=True, help="HH:MM, hora local del día de servicio"
    )
    a.add_argument("--stop", default=None)
    a.add_argument("--comprobar-lineas", action="store_true")
    args = a.parse_args()
    print(
        json.dumps(
            main(args.dia, args.hasta, args.stop, args.comprobar_lineas),
            indent=2,
            ensure_ascii=False,
        )
    )
