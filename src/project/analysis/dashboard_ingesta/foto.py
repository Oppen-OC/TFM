"""La foto de datos del dashboard de la defensa, fase 1 (ingesta).

    uv run python -m project.analysis.dashboard_ingesta

Escribe dashboard/datos/ingesta.js (`window.DATOS = {...}`: la página abre como
file://, sin servidor ni red) y las figuras de la memoria en dashboard/figuras/.
Cada cifra sale del dato y se coteja con la ficha que la publicó; si una no
cuadra, no se escribe nada.

No lee etiquetas, data/processed/ ni métricas del modelo: la prueba del ADR-024
no se mira desde aquí. Del 07-19/10 solo cuenta sondeos, como la bitácora 050.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from project.analysis import medir_fuentes, medir_volumen
from project.analysis.dashboard_ingesta import extraer, figuras
from project.analysis.dashboard_ingesta.paradas import (
    CAPITULOS,
    PARADAS,
    cotejar,
    es,
    escribir_foto,
    fecha_parada,
    ficha,
    redactar,
    validar_prueba,
)
from project.analysis.medir_completitud import instantes
from project.config import RAIZ, settings
from project.ingest.sources import SOURCES, read_raw

DESTINO = RAIZ / "dashboard"
INICIO = "2026-08-15"
# La primera captura de docs/05: 15/08 22:15 -> 16/08 08:55, hora local.
PRIMERA_CAPTURA = (
    pd.Timestamp("2026-08-15T20:15Z"),
    pd.Timestamp("2026-08-16T06:55Z"),
)
DIA_GID = "2026-08-16"  # el primer día entero de captura
CAPAS_CAIDAS = ("2026-09-01", "2026-09-20")  # alrededor del hueco de la bitácora 021
VOLUMEN = ("2026-08-15", "2026-09-18")  # las jornadas de la bitácora 033
LECTIVO = ("2026-09-08", "2026-09-18")  # el periodo lectivo medido en la bitácora 031
PRUEBA = ("2026-10-07", "2026-10-19")  # ADR-024
COTEJO_PRUEBA = ("2026-10-07", "2026-10-12")  # lo que contó la bitácora 050
INCIDENTES = [
    {"x": "2026-08-18", "texto": "la captura pasa del portátil a la Pi (035)"},
    {"x": "2026-09-10", "texto": "capas del geoportal caídas (021)"},
    {"x": "2026-10-05", "texto": "falla el disco de la Pi (044)"},
    {"x": "2026-10-06", "texto": "la Pi deja de guardar el GTFS (051)"},
]
FUENTES_P1 = {
    "emt_buses": ("EMT · posición de la flota", "si"),
    "trafico_estado": ("Tráfico · estado por tramo (capa 192)", "si"),
    "trafico_intensidad": ("Tráfico · intensidad por tramo (capa 188)", "si"),
    "valenbisi": ("Valenbisi · estaciones", "parcial"),
    "renfe_cercanias": ("Renfe Cercanías · núcleo de València", "si"),
}


def leer_curar(ruta: Path) -> dict:
    if not ruta.exists():
        raise FileNotFoundError(f"falta {ruta}: ejecuta `uv run dvc repro curar`")
    return json.loads(ruta.read_text(encoding="utf-8"))


def _dia(d: str) -> str:
    """'2026-10-07' -> '07/10'."""
    return f"{d[8:10]}/{d[5:7]}"


def _serie(x, series, sombras=(), anotaciones=()) -> dict:
    return {
        "tipo": "serie",
        "x": [str(d) for d in x],
        "series": [
            {
                "nombre": nombre,
                "valores": [None if pd.isna(v) else float(v) for v in valores],
            }
            for nombre, valores in series
        ],
        "sombras": list(sombras),
        "anotaciones": list(anotaciones),
    }


def _cadencia(segundos: int) -> str:
    return f"cada {segundos} s" if segundos < 60 else f"cada {segundos // 60} min"


def p1():
    elementos = [
        {"nombre": nombre, "veredicto": v, "detalle": _cadencia(SOURCES[f].period_s)}
        for f, (nombre, v) in FUENTES_P1.items()
    ]
    elementos.append(
        {
            "nombre": "Metrovalencia · FGV",
            "veredicto": "no",
            "detalle": "sin tiempo real",
        }
    )
    valores = {"candidatas": len(elementos), "capturadas": len(SOURCES)}
    return valores, {"tipo": "lista", "elementos": elementos}


def p2(raw: Path, vol: pd.DataFrame):
    primeros = [
        next(read_raw(sorted((raw / f"source={s}").glob("date=*/*.ndjson.gz"))[0]))[0]
        for s in SOURCES
    ]
    primero = min(primeros).tz_convert(settings.zona_horaria)
    por_fuente = vol.groupby("fuente")["payloads"].sum()
    total = int(por_fuente.sum())
    valores = {"primer_sondeo": f"{primero:%d/%m/%Y a las %H:%M}", "payloads": total}
    prueba = {
        "tipo": "cifra",
        "valor": total,
        "decimales": 0,
        "etiqueta": "payloads crudos guardados",
        "detalle": [{"nombre": f, "valor": es(int(n))} for f, n in por_fuente.items()],
    }
    return valores, prueba


def p3(raw: Path):
    a = extraer.alternancia(raw, *PRIMERA_CAPTURA)
    valores = {
        "horas": (PRIMERA_CAPTURA[1] - PRIMERA_CAPTURA[0]) / pd.Timedelta(hours=1),
        "sondeos": a["sondeos"],
        "alternancias": a["alternancias"],
        "desplazadas": a["desplazadas"],
    }
    return valores, {"tipo": "pares", "registros": a["par"], "resalta": "diferencia"}


def p4(raw: Path):
    g = extraer.gid_por_sondeo(raw, DIA_GID)
    valores = {"pares": g["pares"], "comun": g["con_comun"], "dia": _dia(DIA_GID)}
    prueba = {
        "tipo": "pares",
        "registros": g["par"],
        "resalta": "gid en común con el anterior",
    }
    return valores, prueba


def p5(raw: Path):
    desde, hasta = CAPAS_CAIDAS
    series, hueco = [], None
    for fuente, nombre, contar in [
        ("emt_buses", "EMT · sondeos al día", instantes),
        ("trafico_estado", "capa de estado · sondeos al día", instantes),
        # Renfe es el latido del colector: toda respuesta guardada, sondeo o no.
        ("renfe_cercanias", "Renfe · respuestas guardadas al día", extraer.capturas),
    ]:
        n, hs = extraer.completitud(raw, fuente, desde, hasta, contar)
        series.append((nombre, n.values))
        if fuente == "trafico_estado":
            if not hs:
                raise ValueError(
                    f"la capa de estado no tiene ningún hueco de más de una hora "
                    f"entre el {desde} y el {hasta}: ¿falta el crudo de la caída?"
                )
            hueco = max(hs, key=lambda h: h[1] - h[0])
    l71 = medir_fuentes.sql(
        "SELECT strftime(CAST(ts_ingest_utc AS DATE), '%Y-%m-%d') AS dia, "
        "count(*) AS n FROM {f} WHERE CAST(linea AS VARCHAR) = '71' GROUP BY 1",
        f="emt_buses",
    ).set_index("dia")["n"]
    series.append(("línea 71 · posiciones al día", l71.reindex(n.index, fill_value=0)))
    ini, fin = hueco
    # Renfe dentro del hueco de las capas: el colector seguía vivo.
    ts = [
        t
        for t in extraer.capturas(raw, "renfe_cercanias", desde, hasta)
        if ini <= t <= fin
    ]
    if len(ts) < 2:
        raise ValueError(
            f"Renfe tiene {len(ts)} sondeos entre {ini:%d/%m %H:%M} y "
            f"{fin:%d/%m %H:%M}: sin ellos no se puede decir que el colector seguía vivo"
        )
    renfe = max(b - a for a, b in zip(ts, ts[1:]))
    valores = {
        "desde": f"{ini:%d/%m %H:%M}",
        "hasta": f"{fin:%d/%m %H:%M}",
        "horas": (fin - ini) / pd.Timedelta(hours=1),
        "renfe_min": renfe / pd.Timedelta(minutes=1),
        "linea": "71",
    }
    sombra = {
        "desde": f"{ini:%Y-%m-%d}",
        "hasta": f"{fin:%Y-%m-%d}",
        "etiqueta": "las capas del geoportal no entregan nada",
    }
    return valores, _serie(n.index, series, [sombra])


def p6(raw: Path, curar: dict):
    b = extraer.bloque_a_medias(raw, extraer.dias_del_crudo(raw))
    valores = {
        "filas_a": b["filas"][0],
        "filas_b": b["filas"][1],
        "completados": curar["emt_buses"]["completados"],
    }
    return valores, {"tipo": "pares", "registros": b["par"], "resalta": "filas"}


def p7(hasta: str):
    medido = medir_fuentes.lectivo()
    est, inten = medido["estado"], medido["intensidad"]
    est["dia"] = est["dia"].astype(str)
    inten["dia"] = inten["dia"].astype(str)
    laborables = est[est["dia"].between(*LECTIVO) & est["dow"].between(1, 5)]
    v188 = inten.loc[inten["dia"] <= LECTIVO[1], "valores_distintos"]
    valores = {
        "tramos": float(laborables["tramos_congestion"].median()),
        "valores": int(v188.iloc[0]) if v188.nunique() == 1 else -1,
    }
    # De la prueba del ADR-024 solo se cuentan sondeos: la serie acaba antes.
    corte = min(hasta, str((pd.Timestamp(PRUEBA[0]) - pd.Timedelta(days=1)).date()))
    est = est[est["dia"] <= corte].set_index("dia")
    # Un día sin filas (las capas caídas, 11-13/09) es un hueco: no se une con una recta.
    dias = pd.date_range(est.index.min(), corte).strftime("%Y-%m-%d")
    est = est.reindex(dias)
    intensidad = inten.set_index("dia")["valores_distintos"].reindex(dias)
    prueba = _serie(
        dias,
        [
            (
                "capa de estado · tramos densos o congestionados",
                est["tramos_congestion"],
            ),
            ("capa de intensidad · valores distintos", intensidad),
        ],
        [{"desde": LECTIVO[0], "hasta": dias[-1], "etiqueta": "periodo lectivo"}],
    )
    return valores, prueba


def p8(vol: pd.DataFrame):
    v = vol[vol["dia"].between(*VOLUMEN)]
    r = v.groupby("fuente").agg(payloads=("payloads", "median"), mb=("mb", "median"))
    total, mb = float(r["payloads"].sum()), float(r["mb"].sum())
    valores = {"payloads": total, "por_segundo": total / 86400, "mb": mb}
    prueba = {
        "tipo": "cifra",
        "valor": total / 86400,
        "decimales": 3,
        "etiqueta": "payloads por segundo",
        "detalle": [
            {"nombre": f, "valor": f"{es(x['payloads'])} al día · {es(x['mb'])} MB"}
            for f, x in r.iterrows()
        ],
    }
    return valores, prueba


def p9(raw: Path, hasta: str):
    n, hs = extraer.completitud(raw, "emt_buses", INICIO, hasta)
    horas = [(b - a) / pd.Timedelta(hours=1) for a, b in hs]
    valores = {
        "dias": len(n),
        "cortes": len(hs),
        "horas": sum(horas),
        # El corte de la EMT dentro de la caída del geoportal que cuenta P5.
        "horas_fuente": sum(
            h
            for (a, b), h in zip(hs, horas)
            if CAPAS_CAIDAS[0] <= f"{a:%Y-%m-%d}" and f"{b:%Y-%m-%d}" <= CAPAS_CAIDAS[1]
        ),
    }
    sombras = [
        {
            "desde": f"{a:%Y-%m-%d}",
            "hasta": f"{b:%Y-%m-%d}",
            "etiqueta": f"sin sondeos de {a:%d/%m %H:%M} a {b:%d/%m %H:%M} UTC",
        }
        for a, b in hs
    ]
    anotaciones = [i for i in INCIDENTES if i["x"] <= hasta]
    serie = _serie(n.index, [("EMT · sondeos al día", n.values)], sombras, anotaciones)
    return valores, serie


def pct_franjas(ts, period_s: int, dias) -> pd.Series:
    """% de las franjas de la cadencia con algún sondeo, por día UTC.

    Contar sondeos pasa del 100 % donde la cadencia fue más rápida (la capa 192,
    16-17/08); contar franjas distintas, no.
    """
    franjas = pd.Series(
        [int(t.timestamp()) // period_s for t in ts], dtype="int64"
    ).drop_duplicates()
    dia = pd.to_datetime(franjas * period_s, unit="s").dt.strftime("%Y-%m-%d")
    n = dia.value_counts().reindex([str(d) for d in dias], fill_value=0)
    return 100 * n / (86400 // period_s)


def p10(raw: Path, hasta: str):
    emt_n, hs = extraer.completitud(raw, "emt_buses", INICIO, hasta)
    pct = {
        f: pct_franjas(
            instantes(raw, f, INICIO, hasta), SOURCES[f].period_s, emt_n.index
        )
        for f in ("emt_buses", "trafico_estado")
    }
    emt, e192 = pct["emt_buses"], pct["trafico_estado"]
    fin = min(PRUEBA[1], hasta)
    prueba = emt.loc[PRUEBA[0] : fin]
    tocados = {
        f"{d:%Y-%m-%d}"
        for a, b in hs
        for d in pd.date_range(a.normalize(), b.normalize())
    }
    valores = {
        "desde": _dia(PRUEBA[0]),
        "hasta": _dia(fin),
        "pct": float(prueba.mean()),
        "utiles": sum(d not in tocados for d in prueba.index),
        "dias": len(prueba),
        "caidos": ", ".join(_dia(d) for d in prueba.index if d in tocados),
        "minutos_caida": round(
            sum(
                (b - a) / pd.Timedelta(minutes=1)
                for a, b in hs
                if PRUEBA[0] <= f"{a:%Y-%m-%d}" <= fin
            )
        ),
        # El cotejo cuenta su propia ventana, no la serie recortada al último día.
        "sondeos_cotejo": int(
            extraer.completitud(raw, "emt_buses", *COTEJO_PRUEBA)[0].sum()
        ),
    }
    serie = _serie(
        emt.index,
        [
            ("EMT · % de los sondeos posibles", emt),
            ("capa de estado · % de los sondeos posibles", e192),
        ],
        [{"desde": PRUEBA[0], "hasta": fin, "etiqueta": "prueba del ADR-024"}],
    )
    return valores, serie


def origen(raw: Path) -> dict:
    def git(*args: str) -> str:
        r = subprocess.run(
            ["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True
        )
        return r.stdout.strip()

    dias = extraer.dias_del_crudo(raw)
    return {
        "commit": git("rev-parse", "--short", "HEAD"),
        "sucio": bool(git("status", "--porcelain", "--untracked-files=no")),
        "generado": datetime.now().astimezone().strftime("%d/%m/%Y %H:%M"),
        "crudo_desde": dias[0],
        "crudo_hasta": dias[-1],
    }


def construir() -> dict:
    raw = settings.raw_dir
    if not settings.curated_dir.exists():
        raise FileNotFoundError(
            f"falta {settings.curated_dir}: ejecuta `uv run dvc repro curar`"
        )
    curar = leer_curar(RAIZ / "metrics" / "curar.json")
    hasta = extraer.ultimo_dia_completo(raw)
    vol = medir_volumen.medir()
    medido = {
        "P1": p1(),
        "P2": p2(raw, vol),
        "P3": p3(raw),
        "P4": p4(raw),
        "P5": p5(raw),
        "P6": p6(raw, curar),
        "P7": p7(hasta),
        "P8": p8(vol),
        "P9": p9(raw, hasta),
        "P10": p10(raw, hasta),
    }
    informe, paradas = [], []
    for p in PARADAS:
        valores, prueba = medido[p["id"]]
        informe += cotejar(p["id"], valores, p["cotejo"])
        validar_prueba(prueba)
        paradas.append(
            {
                "id": p["id"],
                "capitulo": p["capitulo"],
                "apartado": p["apartado"],
                "fecha": fecha_parada(p),
                "titulo": p["titulo"],
                "texto": redactar(p["texto"], valores),
                "prueba": prueba,
                "remite": [ficha(r) for r in p["remite"]],
                "duracion_s": p.get("duracion_s", 12),
            }
        )
    print("\n  Cotejo con las fichas\n" + "\n".join(informe))
    return {"origen": origen(raw), "capitulos": CAPITULOS, "paradas": paradas}


def main() -> None:
    foto = construir()
    datos = DESTINO / "datos" / "ingesta.js"
    n = escribir_foto(foto, datos)
    for p in foto["paradas"]:
        if p["prueba"]["tipo"] == "serie":
            destino = DESTINO / "figuras" / f"{p['id']}.pdf"
            figuras.figura_serie(p["prueba"], p["titulo"], destino)
    print(f"\n  foto: {n:,} bytes en {datos}\n  figuras en {DESTINO / 'figuras'}\n")
