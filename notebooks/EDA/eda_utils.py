"""Utilidades compartidas por los notebooks de EDA.

Vive aquí y no en `src/project/` a propósito: los notebooks son exploración,
igual que `analysis/`. Nada del pipeline importa de este módulo, y este módulo
solo importa aguas arriba (`config.py`) para no hardcodear la ruta del corpus.

El motor es DuckDB sobre los parquet particionados. `emt_buses` son 5,1 M de
filas y 116 MB: cargarlos enteros en pandas para pintar un histograma es tirar
memoria. Se agrega en SQL y solo el resultado agregado pasa a pandas.

Todo lo que devuelve una hora la devuelve en **UTC**. La conexión fija
`TimeZone='UTC'` porque DuckDB, si no, formatea con la zona del sistema y en
Madrid eso desplaza dos horas en verano — justo la clase de error que la
trampa 002 ya metió una vez en este proyecto.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from project.config import settings

FUENTES = [
    "emt_buses",
    "trafico_estado",
    "trafico_intensidad",
    "valenbisi",
    "renfe_cercanias",
]

# Paleta única para los seis notebooks: que dos gráficos de fuentes distintas
# se puedan poner uno al lado del otro sin recolorear nada.
PALETA = {
    "emt_buses": "#1f77b4",
    "trafico_estado": "#d62728",
    "trafico_intensidad": "#ff7f0e",
    "valenbisi": "#2ca02c",
    "renfe_cercanias": "#9467bd",
}

# Qué significa cada columna del corpus. Lo consume `esquema()`, que añade la
# glosa junto al tipo: el nombre de un campo casi nunca dice lo que mide, y
# `gid`, `total` o `estado` significan cosas distintas de las que aparentan.
# Si una columna no está aquí, `esquema()` la marca con "—": es un aviso de que
# la fuente publicó un campo que nadie ha documentado todavía, no un adorno.
COLUMNAS_COMUNES = {
    "lat": "latitud WGS84 (`outSR=4326`, sin reproyectar)",
    "lon": "longitud WGS84",
    "ts_utc": "instante del dato **según la fuente**, normalizado a UTC",
    "ts_ingest_utc": "instante en que el colector recibió la respuesta (su propio reloj)",
    "geom_wkt": "geometría del tramo en WKT; estática, se separa a `data/reference/`",
    "fiwareid": "identificador FIWARE de la plataforma municipal (`ENTIDAD:id`)",
    "date": "columna de partición del parquet: día de captura (no es un campo de la fuente)",
    "source": "columna de partición del parquet: nombre de la fuente (no es un campo de la fuente)",
}

DICCIONARIO = {
    "emt_buses": {
        "snapshot_id": "identifica el sondeo: es el `gid` mínimo del bloque (trampa 001)",
        "gid": "OID de la tabla, único en el refresco pero **no identifica al vehículo**: la tabla se trunca y reinserta entera (trampa 001)",
        "linea": "número de línea tal como lo publica la EMT (`70`, `C3`)",
        "trayecto": "línea + sentido en texto (`Alboraia - La Fontsanta`); no casa por clave con el GTFS",
        "latencia_s": "`ts_ingest_utc − ts_utc`: antigüedad del dato al capturarlo",
        "tz_convencion": "convención horaria detectada en ese snapshot (`utc` / `local`); la EMT **alterna** entre sondeos (trampa 002)",
    },
    "trafico_estado": {
        "idtramo": "identificador del tramo viario en la capa 192; numérico, **sin intersección** con el de la 188",
        "denominacion": "nombre del tramo (`PÉREZ GALDÓS DE ... A PECHINA`)",
        "estado": "estado categórico: 0 fluido · 1 denso · 2 congestionado · 3 cortado (ver `ESTADO_TRAFICO`). El 3 son obras, no tráfico",
        "n_vertices": "número de vértices de la polilínea del tramo",
    },
    "trafico_intensidad": {
        "idtramo": "identificador del punto de medida en la capa 188; alfanumérico (`A302`), **sin intersección** con el de la 192",
        "des_tramo": "descripción del punto de medida",
        "lectura": "intensidad medida en veh/h; el `-1` de la fuente (sin dato) ya viene convertido a nulo",
        "tipo_vehiculo": "tipo de vehículo al que se refiere la lectura",
    },
    "valenbisi": {
        "number": "identificador de la estación",
        "name": "nombre de la estación",
        "address": "dirección postal",
        "abierta": "estación en servicio (`open == 'T'`); **constante `True`** en todo el corpus",
        "available": "bicicletas disponibles en ese instante",
        "free": "anclajes libres en ese instante",
        "total": "capacidad **instalada**, no anclajes operativos: no cuadra con `available + free` en el 24,9 % de las filas (bitácora 007)",
    },
    "renfe_cercanias": {
        "tripId": "identificador de circulación, **estable entre sondeos**: es la fuente que sí trae identidad",
        "codTren": "código del tren",
        "codLinea": "línea de Cercanías (núcleo 40 = València)",
        "retraso_min": "retraso en minutos **ya calculado por la fuente**: la etiqueta que la EMT no publica",
        "codEstAct": "código de la estación actual o última",
        "codEstSig": "código de la estación siguiente",
        "eta_sig_est_utc": "llegada prevista a la estación siguiente, convertida a UTC",
        "codEstOrig": "código de la estación de origen del servicio",
        "codEstDest": "código de la estación de destino",
        "porAvanc": "porcentaje de avance del recorrido declarado por la fuente",
        "via": "vía de estacionamiento, cuando la publica",
    },
}


def descripcion(fuente: str, columna: str) -> str:
    """Glosa de una columna: primero la específica de la fuente, luego la común."""
    return DICCIONARIO.get(fuente, {}).get(columna) or COLUMNAS_COMUNES.get(
        columna, "—"
    )


# Estados de la capa 192 de tráfico, tal como los publica el Ajuntament.
ESTADO_TRAFICO = {
    0: "fluido",
    1: "denso",
    2: "congestionado",
    3: "cortado",
    4: "sin datos",
    5: "paso inferior fluido",
    6: "paso inferior denso",
    7: "paso inferior congestionado",
    8: "paso inferior cortado",
    9: "sin datos (paso inferior)",
}

_con: duckdb.DuckDBPyConnection | None = None


def con() -> duckdb.DuckDBPyConnection:
    """Conexión única en memoria, con la zona horaria clavada en UTC."""
    global _con
    if _con is None:
        _con = duckdb.connect()
        _con.execute("SET TimeZone='UTC'")
    return _con


def dir_fuente(fuente: str) -> Path:
    return settings.curated_dir / f"source={fuente}"


def dataset(fuente: str) -> str:
    """Glob de parquet de una fuente, listo para `read_parquet`."""
    return (dir_fuente(fuente) / "**" / "*.parquet").as_posix()


def sql(consulta: str, **fuentes: str) -> pd.DataFrame:
    """Ejecuta SQL y devuelve un DataFrame.

    En la consulta, `{X}` se sustituye por la lectura de la fuente pasada como
    argumento X, así que `sql("SELECT count(*) FROM {b}", b="emt_buses")` basta
    para el caso normal.

    `union_by_name=1` no es decoración: el esquema de `trafico_intensidad`
    cambia dentro del propio corpus — los ficheros reprocesados traen `lat` y
    `lon` y los capturados en vivo no. Sin esta opción, DuckDB aborta el glob
    entero con un *schema mismatch*; con ella, las filas que no traen la
    columna la reciben como NULL, que es exactamente lo que son.
    """
    sustituciones = {
        k: f"read_parquet('{dataset(v)}', hive_partitioning=1, union_by_name=1)"
        for k, v in fuentes.items()
    }
    return con().sql(consulta.format(**sustituciones)).df()


def geometria(fuente: str) -> pd.DataFrame:
    """Geometría estática de una capa de tráfico, desde `data/reference/`.

    Las dos capas de tráfico llegan **sin** `lat`/`lon` en la captura en vivo:
    la geometría no cambia, así que el colector la baja una vez, la deja aquí y
    a partir de ahí pide la capa sin ella (es el 90 % del payload de la 192).
    Quien quiera situar un tramo en el mapa tiene que unir contra esta tabla;
    buscar la posición en `curated/` solo devuelve nulos.
    """
    ruta = settings.reference_dir / f"{fuente}_geometria.parquet"
    return con().sql(f"SELECT * FROM read_parquet('{ruta.as_posix()}')").df()


def estilo() -> None:
    """Estilo común. Se llama una vez por notebook, en la celda de imports."""
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams["figure.figsize"] = (11, 4)
    plt.rcParams["figure.dpi"] = 110
    plt.rcParams["axes.titlesize"] = 12
    plt.rcParams["axes.titleweight"] = "bold"
    plt.rcParams["axes.grid"] = True
    plt.rcParams["grid.alpha"] = 0.3
    pd.set_option("display.max_columns", 60)
    pd.set_option("display.width", 160)
    pd.set_option("display.float_format", lambda v: f"{v:,.3f}")


# --- Censo y esquema -------------------------------------------------------


def censo(fuente: str) -> pd.DataFrame:
    """Filas, ficheros, particiones y rango temporal de una fuente."""
    d = dir_fuente(fuente)
    ficheros = sorted(d.glob("**/*.parquet"))
    bytes_ = sum(f.stat().st_size for f in ficheros)
    r = sql(
        """
        SELECT count(*) AS filas,
               min(ts_utc) AS ts_min,
               max(ts_utc) AS ts_max,
               count(DISTINCT date) AS dias
        FROM {f}
        """,
        f=fuente,
    ).iloc[0]
    return pd.DataFrame(
        [
            ("fuente", fuente),
            ("filas", f"{int(r.filas):,}"),
            ("ficheros parquet", f"{len(ficheros):,}"),
            ("particiones (días)", f"{int(r.dias):,}"),
            ("tamaño en disco", f"{bytes_ / 1e6:,.1f} MB"),
            ("ts_utc mínimo", str(r.ts_min)),
            ("ts_utc máximo", str(r.ts_max)),
        ],
        columns=["métrica", "valor"],
    ).set_index("métrica")


def _envolver(df: pd.DataFrame, columna: str, ancho: str = "52em"):
    """DataFrame -> Styler con una columna de texto que hace salto de línea.

    El repr HTML de pandas trunca el texto largo a `display.max_colwidth` y lo
    corta con puntos suspensivos: una glosa de dos líneas se lee a medias. Subir
    ese límite tampoco vale, porque entonces la tabla se va de ancho y hay que
    leerla con scroll horizontal — y afectaría a cualquier `head()` con
    `geom_wkt`, que son miles de caracteres por celda. Lo que se necesita es
    envolver, y eso es CSS, no una opción de pandas.
    """
    return (
        df.style.hide(axis="index")
        .set_properties(**{"text-align": "left", "vertical-align": "top"})
        .set_properties(
            subset=[columna], **{"white-space": "normal", "max-width": ancho}
        )
        .set_table_styles([{"selector": "th", "props": [("text-align", "left")]}])
    )


def esquema(fuente: str, glosa: bool = True):
    """Columnas y tipos, tal como los ve DuckDB sobre el parquet.

    Con `glosa=True` (por defecto) añade la columna `descripcion` desde
    `DICCIONARIO` y devuelve un **Styler**, para que el texto se envuelva en vez
    de truncarse. Un nombre de campo no dice lo que mide —`gid`, `total` y
    `estado` significan los tres otra cosa de la que aparentan— y el sitio donde
    eso se lee es justo este, antes de escribir la primera consulta sobre la
    tabla.

    `glosa=False` devuelve el DataFrame pelado (columna, tipo), que es lo que
    quiere quien consume el esquema en código y no en pantalla.
    """
    df = sql("DESCRIBE SELECT * FROM {f}", f=fuente)
    out = df[["column_name", "column_type"]].rename(
        columns={"column_name": "columna", "column_type": "tipo"}
    )
    if glosa:
        out["descripcion"] = [descripcion(fuente, c) for c in out["columna"]]
        return _envolver(out, "descripcion")
    return out


# --- Calidad ---------------------------------------------------------------


def perfil_nulos(fuente: str) -> pd.DataFrame:
    """Nulos, cardinalidad y columnas constantes, columna a columna.

    Una columna constante no es un detalle estético: significa que la fuente
    publica un campo que no informa de nada, y meterla como feature es regalarle
    al modelo una columna de ruido con nombre respetable.
    """
    cols = esquema(fuente, glosa=False)["columna"].tolist()
    total = int(sql("SELECT count(*) AS n FROM {f}", f=fuente).n.iloc[0])
    piezas = [
        f'sum(CASE WHEN "{c}" IS NULL THEN 1 ELSE 0 END) AS "nulos__{c}", '
        f'count(DISTINCT "{c}") AS "distintos__{c}"'
        for c in cols
    ]
    fila = sql("SELECT " + ", ".join(piezas) + " FROM {f}", f=fuente).iloc[0]
    out = pd.DataFrame(
        {
            "columna": cols,
            "nulos": [int(fila[f"nulos__{c}"]) for c in cols],
            "distintos": [int(fila[f"distintos__{c}"]) for c in cols],
        }
    )
    out["pct_nulos"] = 100 * out["nulos"] / max(total, 1)
    out["constante"] = out["distintos"] <= 1
    return out[["columna", "nulos", "pct_nulos", "distintos", "constante"]].sort_values(
        "pct_nulos", ascending=False
    )


def duplicados(fuente: str, claves: list[str]) -> pd.DataFrame:
    """Cuántas filas repiten la clave que *debería* ser única."""
    k = ", ".join(f'"{c}"' for c in claves)
    return sql(
        f"""
        SELECT count(*) AS filas,
               count(DISTINCT ({k})) AS combinaciones_unicas,
               count(*) - count(DISTINCT ({k})) AS duplicadas
        FROM {{f}}
        """,
        f=fuente,
    )


# --- Univariante -----------------------------------------------------------


def resumen_numerico(fuente: str, columnas: list[str]) -> pd.DataFrame:
    """Media, mediana, moda, dispersión, percentiles y regla del IQR.

    La moda va aparte de un `describe()` normal porque en estas fuentes es la
    estadística que más dice: `lectura` y `estado` son distribuciones con una
    clase que se lo come todo, y ahí la media miente y la moda no.
    """
    filas = []
    for c in columnas:
        r = sql(
            f"""
            SELECT count("{c}") AS n,
                   avg("{c}") AS media,
                   median("{c}") AS mediana,
                   mode("{c}") AS moda,
                   stddev_samp("{c}") AS desv,
                   min("{c}") AS minimo,
                   quantile_cont("{c}", 0.01) AS p01,
                   quantile_cont("{c}", 0.25) AS p25,
                   quantile_cont("{c}", 0.75) AS p75,
                   quantile_cont("{c}", 0.99) AS p99,
                   max("{c}") AS maximo
            FROM {{f}}
            """,
            f=fuente,
        ).iloc[0]
        iqr = r.p75 - r.p25
        bajo, alto = r.p25 - 1.5 * iqr, r.p75 + 1.5 * iqr
        atipicos = int(
            sql(
                f'SELECT count(*) AS n FROM {{f}} WHERE "{c}" < {bajo} OR "{c}" > {alto}',
                f=fuente,
            ).n.iloc[0]
        )
        filas.append(
            dict(
                columna=c,
                n=int(r.n),
                media=r.media,
                mediana=r.mediana,
                moda=r.moda,
                desv=r.desv,
                min=r.minimo,
                p01=r.p01,
                p25=r.p25,
                p75=r.p75,
                p99=r.p99,
                max=r.maximo,
                iqr=iqr,
                atipicos_iqr=atipicos,
                pct_atipicos=100 * atipicos / max(int(r.n), 1),
            )
        )
    return pd.DataFrame(filas).set_index("columna")


def frecuencias(fuente: str, columna: str, top: int = 20) -> pd.DataFrame:
    """Top-N de una categórica, con porcentaje y acumulado."""
    df = sql(
        f"""
        SELECT "{columna}" AS valor, count(*) AS filas
        FROM {{f}} GROUP BY 1 ORDER BY 2 DESC
        """,
        f=fuente,
    )
    total = df["filas"].sum()
    df["pct"] = 100 * df["filas"] / total
    df["pct_acum"] = df["pct"].cumsum()
    return df.head(top)


# --- Tiempo ----------------------------------------------------------------


def filas_por_dia(fuente: str) -> pd.DataFrame:
    return sql(
        """
        SELECT date AS dia, count(*) AS filas,
               count(DISTINCT ts_ingest_utc) AS sondeos
        FROM {f} GROUP BY 1 ORDER BY 1
        """,
        f=fuente,
    )


def cadencia(fuente: str) -> pd.DataFrame:
    """Segundos entre sondeos consecutivos, medidos sobre `ts_ingest_utc`.

    `ts_ingest_utc` es el reloj del colector; `ts_utc` es el de la fuente, que
    en la EMT alterna de convención. Para medir *cada cuánto sondeamos* solo
    vale el reloj propio.

    El umbral de hueco es **relativo** (3 × la mediana), no un valor fijo. Las
    cinco fuentes se sondean a ritmos distintos —30 s los buses, 15 min la capa
    de intensidad—, así que un umbral fijo de 10 minutos declara "hueco" el
    funcionamiento normal de la intensidad y no ve una parada de dos minutos en
    los buses.
    """
    return sql(
        """
        WITH s AS (
            SELECT DISTINCT ts_ingest_utc FROM {f}
        ), d AS (
            SELECT date_diff('second',
                             lag(ts_ingest_utc) OVER (ORDER BY ts_ingest_utc),
                             ts_ingest_utc) AS delta_s
            FROM s
        ), m AS (
            SELECT median(delta_s) AS med FROM d WHERE delta_s IS NOT NULL
        )
        SELECT count(*) AS sondeos,
               any_value(m.med) AS mediana_s,
               avg(delta_s) AS media_s,
               min(delta_s) AS min_s,
               quantile_cont(delta_s, 0.95) AS p95_s,
               max(delta_s) AS max_s,
               sum(CASE WHEN delta_s > 3 * m.med THEN 1 ELSE 0 END) AS huecos,
               sum(CASE WHEN delta_s > 3 * m.med THEN delta_s ELSE 0 END) / 3600.0
                   AS horas_perdidas
        FROM d, m WHERE delta_s IS NOT NULL
        """,
        f=fuente,
    )


def huecos(fuente: str, factor: float = 3.0) -> pd.DataFrame:
    """Paradas del colector: saltos de más de `factor` × la cadencia mediana."""
    return sql(
        f"""
        WITH s AS (SELECT DISTINCT ts_ingest_utc FROM {{f}}),
        d AS (
            SELECT lag(ts_ingest_utc) OVER (ORDER BY ts_ingest_utc) AS desde,
                   ts_ingest_utc AS hasta,
                   date_diff('second',
                             lag(ts_ingest_utc) OVER (ORDER BY ts_ingest_utc),
                             ts_ingest_utc) AS delta_s
            FROM s
        ), m AS (
            SELECT median(delta_s) AS med FROM d WHERE delta_s IS NOT NULL
        )
        SELECT desde, hasta, delta_s / 60.0 AS minutos
        FROM d, m
        WHERE delta_s > {factor} * m.med
        ORDER BY minutos DESC
        """,
        f=fuente,
    )


def matriz_dia_hora(fuente: str) -> pd.DataFrame:
    """Filas por día × hora UTC, en formato pivotado para el heatmap."""
    df = sql(
        """
        SELECT date AS dia, hour(ts_ingest_utc) AS hora, count(*) AS filas
        FROM {f} GROUP BY 1, 2
        """,
        f=fuente,
    )
    return df.pivot(index="dia", columns="hora", values="filas").fillna(0)


def heatmap_cobertura(fuente: str, ax=None):
    """Heatmap día × hora. Los blancos son huecos del colector, no ceros reales."""
    m = matriz_dia_hora(fuente)
    if ax is None:
        _, ax = plt.subplots(figsize=(12, 4.5))
    sns.heatmap(m, cmap="mako", ax=ax, cbar_kws={"label": "filas"})
    ax.set_title(f"Cobertura de {fuente}: filas por día × hora (UTC)")
    ax.set_xlabel("hora UTC")
    ax.set_ylabel("")
    return ax


# --- Espacial --------------------------------------------------------------


def bbox(fuente: str) -> pd.DataFrame:
    """Caja envolvente de las posiciones.

    Ojo antes de usarla para filtrar: en `emt_buses` las posiciones al sur de
    39,36° no son error de GPS, son las líneas 24 y 25 bajando a El Perellonet
    (trampa 006). Recortar por caja sesga la muestra.
    """
    return sql(
        """
        SELECT count(*) AS con_posicion,
               min(lat) AS lat_min, max(lat) AS lat_max,
               min(lon) AS lon_min, max(lon) AS lon_max,
               sum(CASE WHEN lat IS NULL OR lon IS NULL THEN 1 ELSE 0 END)
                   AS sin_posicion
        FROM {f}
        """,
        f=fuente,
    )
