"""Las cifras del EDA, reejecutables desde la línea de comandos.

    uv run python -m project.analysis.medir_fuentes            # los cuatro bloques
    uv run python -m project.analysis.medir_fuentes --solape
    uv run python -m project.analysis.medir_fuentes --senal-192
    uv run python -m project.analysis.medir_fuentes --union-trafico
    uv run python -m project.analysis.medir_fuentes --valenbisi

Los notebooks de `notebooks/EDA/` son donde se descubrieron estas cifras, pero un
notebook no es una evidencia cómoda: hay que abrirlo, ejecutarlo entero y leer la
celda correcta. Las entradas de `docs/bitacora/` citan este módulo, que imprime
exactamente los números que ellas afirman y nada más.

Lee de `data/curated/` con DuckDB. Nada del pipeline importa de aquí: esto es
exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse

import duckdb
import numpy as np
import pandas as pd

from project.config import settings

# La geometría de las capas de tráfico no está en curated/: no cambia, así que el
# colector la baja una vez aquí y luego pide la capa sin ella.
REFERENCIA = {
    "trafico_estado": "trafico_estado_geometria.parquet",
    "trafico_intensidad": "trafico_intensidad_geometria.parquet",
}

_con: duckdb.DuckDBPyConnection | None = None


def con() -> duckdb.DuckDBPyConnection:
    """Conexión en memoria con la zona horaria clavada en UTC.

    Sin fijarla, DuckDB formatea con la del sistema y en Madrid eso desplaza dos
    horas en verano, que es la clase de error que ya costó la trampa 002.
    """
    global _con
    if _con is None:
        _con = duckdb.connect()
        _con.execute("SET TimeZone='UTC'")
    return _con


def sql(consulta: str, **fuentes: str) -> pd.DataFrame:
    """Ejecuta SQL sustituyendo `{X}` por la lectura de la fuente X.

    `union_by_name=1` es obligatorio: los ficheros de una misma fuente no tienen
    las mismas columnas —las capas de tráfico solo traen geometría en los
    reprocesados— y sin esa opción DuckDB aborta el glob entero.
    """
    sustituciones = {
        k: (
            "read_parquet('"
            f"{(settings.curated_dir / f'source={v}' / '**' / '*.parquet').as_posix()}"
            "', hive_partitioning=1, union_by_name=1)"
        )
        for k, v in fuentes.items()
    }
    return con().sql(consulta.format(**sustituciones)).df()


def geometria(fuente: str) -> pd.DataFrame:
    ruta = settings.reference_dir / REFERENCIA[fuente]
    return con().sql(f"SELECT * FROM read_parquet('{ruta.as_posix()}')").df()


# --- 1. ¿Se pueden fusionar buses y tráfico? -------------------------------


def solape_buses_trafico() -> pd.DataFrame:
    """Antigüedad de la última medida de tráfico en el instante de cada bus.

    Es la condición de viabilidad del TFM: si la serie de tráfico no coincide en
    el tiempo con la de posiciones, no hay fusión que hacer. Se mide con un ASOF
    JOIN, que para cada sondeo de buses busca el sondeo de tráfico más reciente
    que no sea posterior.

    Ojo con lo que NO mide: las capas de tráfico no publican timestamp propio
    —`parse_trafico_estado` escribe `ts_utc = ts_ingest_utc`—, así que esto es la
    antigüedad de la *captura*, no la de la *medida*. El desfase real es este más
    una cantidad desconocida.
    """
    return sql(
        """
        WITH b AS (SELECT DISTINCT ts_ingest_utc AS tb FROM {b}),
             t AS (SELECT DISTINCT ts_ingest_utc AS tt FROM {t}),
             j AS (
                SELECT tb, date_diff('second', tt, tb) AS edad_s
                FROM b ASOF LEFT JOIN t ON b.tb >= t.tt
             )
        SELECT count(*) AS sondeos_bus,
               sum(CASE WHEN edad_s IS NULL THEN 1 ELSE 0 END) AS sin_trafico_previo,
               median(edad_s) AS edad_mediana_s,
               quantile_cont(edad_s, 0.95) AS edad_p95_s,
               max(edad_s) AS edad_max_s,
               100.0 * sum(CASE WHEN edad_s <= 300 THEN 1 ELSE 0 END) / count(*)
                   AS pct_frescos_5min
        FROM j
        """,
        b="emt_buses",
        t="trafico_estado",
    )


# --- 2. ¿Cuánta señal tiene realmente la capa 192? -------------------------


def senal_192() -> dict[str, pd.DataFrame]:
    """Cuántos tramos informan, y qué parte del estado 3 es un cierre fijo.

    El censo de la capa dice 410 tramos. La pregunta que importa para el TFM es
    otra: cuántos llegan a estar congestionados alguna vez. La diferencia entre
    las dos cifras es el tamaño real de la variable explicativa.
    """
    reparto = sql(
        """
        SELECT estado, count(*) AS filas,
               100.0 * count(*) / sum(count(*)) OVER () AS pct
        FROM {f} GROUP BY 1 ORDER BY 2 DESC
        """,
        f="trafico_estado",
    )

    cobertura = sql(
        """
        WITH t AS (
            SELECT idtramo,
                   count(DISTINCT estado) AS estados,
                   sum(CASE WHEN estado IN (1, 2) THEN 1 ELSE 0 END) AS obs_congestion,
                   sum(CASE WHEN estado = 3 THEN 1 ELSE 0 END) AS obs_cortado
            FROM {f} WHERE idtramo IS NOT NULL AND estado IS NOT NULL GROUP BY 1
        )
        SELECT count(*) AS tramos,
               sum(CASE WHEN estados > 1 THEN 1 ELSE 0 END) AS varian_alguna_vez,
               sum(CASE WHEN obs_congestion > 0 THEN 1 ELSE 0 END) AS alcanzan_congestion,
               sum(CASE WHEN obs_cortado > 0 THEN 1 ELSE 0 END) AS alcanzan_cortado
        FROM t
        """,
        f="trafico_estado",
    )

    # Los tramos que están en 3 SIEMPRE (un único estado en todo el corpus) son
    # los que delatan que el 3 no es un fenómeno de tráfico sino una vía cerrada.
    permanentes = sql(
        """
        SELECT idtramo, any_value(denominacion) AS denominacion,
               count(*) AS obs,
               100.0 * sum(CASE WHEN estado = 3 THEN 1 ELSE 0 END) / count(*) AS pct_3,
               count(DISTINCT estado) AS estados
        FROM {f} WHERE estado IS NOT NULL GROUP BY 1
        HAVING sum(CASE WHEN estado = 3 THEN 1 ELSE 0 END) > 0
        ORDER BY pct_3 DESC
        """,
        f="trafico_estado",
    )

    # Un fenómeno de tráfico entra y sale muchas veces; un cierre, una.
    episodios = sql(
        """
        WITH s AS (
            SELECT idtramo, estado,
                   lag(estado) OVER (PARTITION BY idtramo ORDER BY ts_ingest_utc) AS previo
            FROM {f} WHERE estado IS NOT NULL AND idtramo IS NOT NULL
        )
        SELECT sum(CASE WHEN estado = 3 AND (previo IS NULL OR previo <> 3)
                        THEN 1 ELSE 0 END) AS entradas_a_cortado,
               sum(CASE WHEN estado IN (1, 2) AND (previo IS NULL OR previo NOT IN (1, 2))
                        THEN 1 ELSE 0 END) AS entradas_a_congestion,
               sum(CASE WHEN estado IN (1, 2) THEN 1 ELSE 0 END) AS filas_congestion
        FROM s
        """,
        f="trafico_estado",
    )

    return {
        "reparto": reparto,
        "cobertura": cobertura,
        "permanentes": permanentes,
        "episodios": episodios,
    }


# --- 3. ¿Se pueden unir las dos capas de tráfico? --------------------------


def union_trafico() -> dict[str, object]:
    """Por `idtramo` no; por proximidad, sí.

    La capa 188 da una medida continua de intensidad y la 192 un estado
    categórico. Si se pudieran unir, la 188 aportaría justo lo que a la 192 le
    falta. La unión barata sería por identificador; se comprueba primero esa.
    """
    i188 = sql(
        "SELECT DISTINCT idtramo FROM {f} WHERE idtramo IS NOT NULL",
        f="trafico_intensidad",
    )
    i192 = sql(
        "SELECT DISTINCT idtramo FROM {f} WHERE idtramo IS NOT NULL", f="trafico_estado"
    )
    comunes = set(i188["idtramo"].astype(str)) & set(i192["idtramo"].astype(str))

    g188, g192 = geometria("trafico_intensidad"), geometria("trafico_estado")

    # Haversine de todos contra todos: 389 × 410 cabe de sobra en memoria.
    # La distancia se mide entre los puntos INICIALES de cada tramo, que es lo
    # que guarda reference/. Acota por arriba; no resuelve el sentido de marcha.
    radio_m = 6_371_000.0
    a = np.radians(g188[["lat", "lon"]].to_numpy())
    b = np.radians(g192[["lat", "lon"]].to_numpy())
    dlat = a[:, None, 0] - b[None, :, 0]
    dlon = a[:, None, 1] - b[None, :, 1]
    h = (
        np.sin(dlat / 2) ** 2
        + np.cos(a[:, None, 0]) * np.cos(b[None, :, 0]) * np.sin(dlon / 2) ** 2
    )
    dist = 2 * radio_m * np.arcsin(np.sqrt(h))

    vecino = pd.DataFrame(
        {
            "idtramo_188": g188["idtramo"].to_numpy(),
            "idtramo_192": g192["idtramo"].to_numpy()[dist.argmin(axis=1)],
            "distancia_m": dist.min(axis=1),
        }
    )
    return {
        "n_188": len(i188),
        "n_192": len(i192),
        "tipo_188": str(i188["idtramo"].dtype),
        "tipo_192": str(i192["idtramo"].dtype),
        "comunes": len(comunes),
        "vecino": vecino,
        # Un mismo tramo de la 192 puede ser el vecino más cercano de varios de
        # la 188: la correspondencia no es uno a uno y un merge duplicaría filas.
        "destinos_unicos": int(vecino["idtramo_192"].nunique()),
    }


# --- 4. ¿Qué significa `total` en Valenbisi? -------------------------------


def coherencia_valenbisi() -> dict[str, pd.DataFrame]:
    """`available + free` contra `total`, y en qué dirección falla.

    Si el descuadre fuera simétrico sería ruido. Si es siempre por defecto,
    `total` no es la suma de anclajes operativos sino la capacidad instalada, y
    entonces el denominador de la ocupación está mal elegido.
    """
    global_ = sql(
        """
        SELECT count(*) AS filas,
               sum(CASE WHEN available + free = total THEN 1 ELSE 0 END) AS cuadra,
               100.0 * sum(CASE WHEN available + free <> total THEN 1 ELSE 0 END)
                   / count(*) AS pct_descuadre,
               sum(CASE WHEN available + free < total THEN 1 ELSE 0 END) AS por_defecto,
               sum(CASE WHEN available + free > total THEN 1 ELSE 0 END) AS por_exceso,
               min(available + free - total) AS desfase_min,
               max(available + free - total) AS desfase_max,
               count(DISTINCT number) AS estaciones
        FROM {f}
        """,
        f="valenbisi",
    )
    por_estacion = sql(
        """
        SELECT 100.0 * sum(CASE WHEN available + free <> total THEN 1 ELSE 0 END)
                   / count(*) AS pct_descuadre
        FROM {f} GROUP BY number
        """,
        f="valenbisi",
    )
    return {
        "global": global_,
        "por_estacion": por_estacion["pct_descuadre"].describe().to_frame().T,
    }


# --- Salida ----------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--solape", action="store_true")
    p.add_argument("--senal-192", action="store_true")
    p.add_argument("--union-trafico", action="store_true")
    p.add_argument("--valenbisi", action="store_true")
    a = p.parse_args()
    todo = not (a.solape or a.senal_192 or a.union_trafico or a.valenbisi)

    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 40)

    if todo or a.solape:
        print("\n=== 1. Solape temporal buses × tráfico (condición de fusión) ===")
        print("(edad de la última medida de tráfico en el instante de cada bus)\n")
        print(solape_buses_trafico().round(1).to_string(index=False))

    if todo or a.senal_192:
        s = senal_192()
        print("\n=== 2. Cuánta señal tiene la capa 192 ===\n")
        print(s["reparto"].round(3).to_string(index=False))
        print("\nCobertura por tramo:")
        print(s["cobertura"].to_string(index=False))
        print("\nTramos que alcanzan el estado 3 (ordenados por permanencia):")
        print(s["permanentes"].round(3).head(10).to_string(index=False))
        siempre = s["permanentes"].query("estados == 1")
        masa = int(s["reparto"].query("estado == 3")["filas"].iloc[0])
        print(
            f"\n{len(siempre)} tramos están en 3 el 100 % del corpus "
            f"({int(siempre['obs'].sum()):,} filas, "
            f"{100 * siempre['obs'].sum() / masa:.1f} % de todo el estado 3)"
        )
        print("\nEpisodios en todo el corpus:")
        print(s["episodios"].to_string(index=False))

    if todo or a.union_trafico:
        u = union_trafico()
        print("\n=== 3. ¿Se pueden unir las capas 188 y 192? ===\n")
        print(
            f"188: {u['n_188']} tramos, idtramo {u['tipo_188']} | "
            f"192: {u['n_192']} tramos, idtramo {u['tipo_192']}"
        )
        print(f"idtramo comunes tras castear a texto: {u['comunes']}")
        d = u["vecino"]["distancia_m"]
        print(
            f"\ndistancia al vecino más cercano (m): mediana {d.median():.1f}, "
            f"media {d.mean():.1f}, máx {d.max():.1f}"
        )
        for umbral in (50, 100, 250, 500):
            n = int((d <= umbral).sum())
            print(
                f"  a menos de {umbral:4d} m: {n:3d} de {len(d)} ({100 * n / len(d):.1f} %)"
            )
        print(
            f"\n{len(d)} tramos de la 188 apuntan a solo {u['destinos_unicos']} tramos "
            "distintos de la 192: la correspondencia no es uno a uno."
        )

    if todo or a.valenbisi:
        v = coherencia_valenbisi()
        print("\n=== 4. Coherencia de Valenbisi: available + free vs total ===\n")
        print(v["global"].round(2).to_string(index=False))
        print("\nDescuadre por estación (% de sus observaciones):")
        print(v["por_estacion"].round(1).to_string())


if __name__ == "__main__":
    main()
