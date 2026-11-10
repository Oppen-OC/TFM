"""El núcleo del ciclo en vivo: lo sabido, lo pendiente y los buses de la parada.

Función pura sobre los pasos etiquetados de HOY. El «ahora» del ciclo parte los
pasos en sabidos (su retraso ya había llegado, `t_disp_utc <= ahora`) y no
sabidos, que no existen para nadie (trampa 017). Cada viaje en curso completa lo
que le falta con las paradas que aún no ha pasado, y `features.construir` busca
la parada objetivo de cada bus por clave, igual que al entrenar. Ninguna variable
del modelo se calcula aquí.
"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from project import features
from project.features import CLAVE_VIAJE

# (feed_version, shape_id, trip_id) -> salida de `etiquetado.paradas_del_viaje`.
ParadasDe = Callable[[str, str, str], pd.DataFrame]

# Constantes de un viaje: las pendientes las copian de su último paso sabido.
# Cualquier otra columna de `pasos` que no sea de horario queda nula.
COLUMNAS_DE_VIAJE = [
    *CLAVE_VIAJE,
    "vehicle_id",
    "linea",
    "trayecto",
    "feed_version",
    "fuera_de_vigencia",
    "trip_id",
    "shape_id",
    "desfase_s",
    "margen_s",
    "coste_s",
]


def separar(
    pasos: pd.DataFrame, ahora: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(sabidos, no_sabidos). Sabido: `t_disp_utc` no nulo y no posterior a `ahora`."""
    sabido = pasos["t_disp_utc"].notna() & (pasos["t_disp_utc"] <= ahora)
    return pasos[sabido], pasos[~sabido]


def pendientes(sabidos: pd.DataFrame, paradas_de: ParadasDe) -> pd.DataFrame:
    """Las paradas que cada viaje con algún paso sabido aún no ha pasado.

    Una fila por parada con `stop_sequence` mayor que la del último sabido, con
    las columnas de horario y las de viaje, `retraso_s` nulo y
    `t_obs_utc = t_disp_utc = FUTURO`: el contrato de `features.construir`.
    """
    ultimos = sabidos.sort_values("stop_sequence", kind="stable").groupby(
        CLAVE_VIAJE, sort=False
    )
    partes = []
    for _, u in ultimos.tail(1).iterrows():
        paradas = paradas_de(u["feed_version"], u["shape_id"], u["trip_id"])
        paradas = paradas[paradas["stop_sequence"] > u["stop_sequence"]]
        partes.append(
            paradas.assign(**{c: u[c] for c in COLUMNAS_DE_VIAJE if c in sabidos})
        )
    p = pd.concat(partes, ignore_index=True) if partes else sabidos.iloc[0:0]
    p = p.reindex(columns=sabidos.columns)
    p["t_obs_utc"] = features.FUTURO
    p["t_disp_utc"] = features.FUTURO
    return p


def candidatos(
    sabidos: pd.DataFrame, pend: pd.DataFrame, stop_id: str, horizontes: list[int]
) -> pd.DataFrame:
    """Los buses que van a `stop_id`, con su horizonte `h` en posiciones del horario.

    `h` = `stop_sequence` de la parada − la del último paso sabido; si la parada
    sale más de una vez (ruta circular) cuenta la más cercana. Entran los de
    `1 <= h <= max(horizontes)`; `con_modelo` dice si hay modelo a esa distancia.
    `stop_sequence` es la del último sabido, la fila que se predice.
    """
    ultimo = (
        sabidos.sort_values("stop_sequence", kind="stable")
        .groupby(CLAVE_VIAJE, sort=False)
        .agg(
            linea=("linea", "last"),
            seq_ultimo=("stop_sequence", "max"),
            retraso_s=("retraso_s", "last"),
            t_disp_utc=("t_disp_utc", "last"),
        )
        .reset_index()
    )
    destino = pend.loc[pend["stop_id"] == stop_id, [*CLAVE_VIAJE, "stop_sequence"]]
    c = ultimo.merge(destino, on=CLAVE_VIAJE, how="inner", validate="one_to_many")
    c["h"] = c["stop_sequence"] - c["seq_ultimo"]
    c = c[(c["h"] >= 1) & (c["h"] <= max(horizontes))]
    c = c.sort_values("h", kind="stable").drop_duplicates(CLAVE_VIAJE)
    c = c.assign(stop_sequence=c["seq_ultimo"], con_modelo=c["h"].isin(horizontes))
    return c[
        [
            *CLAVE_VIAJE,
            "linea",
            "stop_sequence",
            "h",
            "retraso_s",
            "t_disp_utc",
            "con_modelo",
        ]
    ].reset_index(drop=True)


def tabla(
    historial: pd.DataFrame,
    sabidos: pd.DataFrame,
    pend: pd.DataFrame,
    horizonte: int,
    cfg: dict,
) -> pd.DataFrame:
    """Las variables de la fila de cada bus: `construir` sobre historial + hoy.

    `cfg` es `params.yaml → features`. Sin tráfico: la capa 192 no aporta
    (ADR-024). Devuelve también las filas pendientes; quien llama elige la suya
    por clave.
    """
    pasos = pd.concat(
        [x for x in (historial, sabidos, pend) if not x.empty], ignore_index=True
    )
    return features.construir(
        pasos,
        objetivo=cfg["objetivo"],
        horizonte=horizonte,
        lags_min=tuple(cfg["lags_min"]),
        umbral_s=cfg["umbral_retraso_s"],
        ventanas_flota_min=features.ventanas_flota(cfg),
        soporte_min=cfg["soporte_min"],
        solo_con_objetivo=False,
    )
