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
from dataclasses import dataclass

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


@dataclass(frozen=True)
class Prediccion:
    """Lo que el modelo y la regla simple dijeron de un bus en una parada."""

    probabilidad: float
    umbral: float
    llega_tarde: bool
    regla_llega_tarde: bool  # retraso_s del último paso sabido > umbral_retraso_s
    h: int
    t_utc: pd.Timestamp
    stop_sequence: int  # posición de la parada objetivo en el horario del viaje


class Marcador:
    """La primera predicción de cada (viaje, parada), congelada y calificada.

    Vive en memoria, por parada y luego por `clave = (fecha_servicio, viaje_id)`:
    cambiar de parada no borra lo congelado en las demás.
    """

    def __init__(self) -> None:
        self._por_parada: dict[str, dict[tuple, dict]] = {}

    def congelar(self, stop_id: str, clave: tuple, p: Prediccion) -> Prediccion:
        """Devuelve la primera predicción de `clave`; las siguientes no la sustituyen."""
        entradas = self._por_parada.setdefault(stop_id, {})
        return entradas.setdefault(clave, {"congelada": p, "resultado": None})[
            "congelada"
        ]

    def verificar(self, stop_id: str, sabidos: pd.DataFrame, umbral_s: float) -> None:
        """Califica las congeladas cuyo paso por `stop_id` ya es sabido.

        Se casa por (`fecha_servicio`, `viaje_id`, `stop_sequence`), no por
        `stop_id`: en una ruta circular la parada sale dos veces y el primer paso,
        ya sabido, no es el de la predicción. `sabidos` solo trae pasos con
        `t_disp_utc <= ahora` (`separar`).
        """
        en_parada = sabidos[sabidos["stop_id"] == stop_id]
        real = {
            (r.fecha_servicio, r.viaje_id, int(r.stop_sequence)): float(r.retraso_s)
            for r in en_parada.itertuples()
        }
        for clave, e in self._por_parada.get(stop_id, {}).items():
            if e["resultado"] is not None:
                continue
            c = e["congelada"]
            retraso = real.get((*clave, c.stop_sequence))
            if retraso is None:
                continue
            tarde = bool(retraso > umbral_s)
            e["resultado"] = {
                "retraso_real_s": retraso,
                "llego_tarde": tarde,
                "acierta_modelo": bool(c.llega_tarde == tarde),
                "acierta_regla": bool(c.regla_llega_tarde == tarde),
            }

    def entradas(self, stop_id: str) -> dict[tuple, dict]:
        """`{clave: {"congelada": Prediccion, "resultado": dict | None}}`."""
        return self._por_parada.get(stop_id, {})

    def resumen(self, stop_id: str) -> dict:
        """El marcador de la parada, sobre las predicciones ya verificadas."""
        hechos = [
            (e["congelada"], e["resultado"])
            for e in self.entradas(stop_id).values()
            if e["resultado"] is not None
        ]
        return {
            "verificados": len(hechos),
            "aciertos_modelo": sum(r["acierta_modelo"] for _, r in hechos),
            "aciertos_regla": sum(r["acierta_regla"] for _, r in hechos),
            "discrepan": sum(c.llega_tarde != c.regla_llega_tarde for c, _ in hechos),
        }
