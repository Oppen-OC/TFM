"""Cota del error de asignación que no da la cara (bitácora 024, abierto 3).

    uv run python -m project.analysis.medir_asignacion

Un bus con retraso real δ sobre su viaje programado, con el siguiente a H
segundos, compite con él a δ − H. `_asignar_tramo` se queda el más cercano y
exige `margen_min_s` (m) de ventaja sobre el segundo, así que:

  δ ≤ (H − m)/2             se asigna bien;
  (H − m)/2 < δ < (H + m)/2 se rechaza por `margen` (se ve en `viajes`);
  δ ≥ (H + m)/2             se asigna AL SIGUIENTE, con margen de sobra y un
                            retraso δ − H creíble. Nada lo delata.

Igual hacia el anterior con el adelanto y el intervalo previo. Lo tercero no se
puede contar, pero se puede acotar: los viajes bien asignados son una muestra de
δ truncada en c = (H − m)/2, distinta en cada viaje. El estimador de Lynden-Bell
recupera la cola P(δ > x) de una muestra así sin suponer su forma, con un
supuesto: δ no depende de H. Con la cola, cada viaje bien asignado representa
1/P(bien | H) buses de su intervalo, de los que P(mal | H) acaban en el contiguo.

Da una cota SUPERIOR, no una estimación: el bus mal asignado al siguiente viaje
se ve como uno adelantado (δ − H), engorda la cola de adelantos y se cuenta otra
vez como posible mala asignación hacia el anterior. Desde fuera no se distinguen.
En la flota sintética la cota se pasa entre 1,1 y 2,2 veces, más cuanto más
gruesa la cola, y los rechazos por margen predichos se pasan en la misma
proporción. Los rechazos sí se ven en `viajes`: escalar por observados/predichos
devuelve la verdad sintética a ±15 % (`tests/test_medir_asignacion.py`). Esa es
la estimación; la bruta queda como techo. Si hay rechazos por otras causas
(variantes, dos patrones), la calibrada también se pasa: sigue siendo del lado
seguro.

H es el intervalo programado en la PRIMERA parada del viaje con los demás viajes
de la misma línea que pasan por ella ese día (el GTFS de la EMT no trae
`direction_id`). `_asignar_tramo` compara en las tres primeras paradas
observadas y también con variantes de otro trazado: H real ≤ este H, así que la
cota se queda corta si algo. Lee `data/interim/`; nada del pipeline importa de aquí.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from project.config import RAIZ, settings
from project.etiquetado import Parametros
from project.evaluate import intervalos
from project.gtfs import cargar_horario, elegir_horario, versiones
from project.prepare import cargar_parametros


def cola(d: np.ndarray, c: np.ndarray, x: np.ndarray) -> np.ndarray:
    """P(δ > x) de una muestra truncada por la derecha: cada δᵢ se ve solo si δᵢ ≤ cᵢ.

    Lynden-Bell: F(x) = Π_{δⱼ > x} (1 − 1/Rⱼ), con Rⱼ = #{i : δᵢ ≤ δⱼ ≤ cᵢ}.
    """
    d = np.asarray(d, float)
    c = np.maximum(np.asarray(c, float), d)  # H aproximado: no se ve δ > c
    t = np.sort(d)
    r = np.searchsorted(t, t, side="right") - np.searchsorted(np.sort(c), t)
    # Rⱼ = 1 deja F = 0 por debajo (arriba de la muestra, sin información): se salta.
    log_f = np.where(r > 1, np.log1p(-1.0 / np.maximum(r, 2.0)), 0.0)
    # F(x) = exp(Σ de log_f sobre los t > x)
    acum = np.concatenate([np.cumsum(log_f[::-1])[::-1], [0.0]])
    return 1.0 - np.exp(acum[np.searchsorted(t, np.asarray(x, float), side="right")])


def cota(v: pd.DataFrame, m: float) -> pd.DataFrame:
    """Por viaje bien asignado: P(bien), P(rechazo) y P(mal) según su intervalo.

    `v`: `desfase_s`, `h_ant_s`, `h_sig_s` de los viajes asignados.
    """
    d = v["desfase_s"].to_numpy(float)
    hs, ha = v["h_sig_s"].to_numpy(float), v["h_ant_s"].to_numpy(float)
    cs, us = (hs - m) / 2, (hs + m) / 2
    ca, ua = (ha - m) / 2, (ha + m) / 2
    tarde = lambda x: cola(d, cs, x)  # noqa: E731
    pronto = lambda x: cola(-d, ca, x)  # noqa: E731
    bien = 1 - tarde(cs) - pronto(ca)
    return v.assign(
        p_bien=bien,
        p_rechazo=(tarde(cs) - tarde(us)) + (pronto(ca) - pronto(ua)),
        p_mal=tarde(us) + pronto(ua),
        peso=1 / np.clip(bien, 0.05, None),
    )


def cargar() -> tuple[pd.DataFrame, Parametros]:
    p = cargar_parametros()
    viajes = pd.read_parquet(settings.interim_dir / "viajes")
    viajes = viajes[viajes["motivo"].isin(["asignado", "margen", "conflicto"])]
    pasos = (
        pd.read_parquet(settings.interim_dir / "pasos", columns=["viaje_id"])
        .value_counts()
        .rename("pasos")
        .reset_index()
    )
    horarios = [cargar_horario(r) for r in versiones(settings.gtfs_dir)]
    partes = []
    for dia, sub in viajes.groupby("fecha_servicio"):
        h, _ = elegir_horario(horarios, dia)
        partes.append(sub.merge(intervalos(h, dia), on="trip_id", how="left"))
    v = pd.concat(partes, ignore_index=True).merge(pasos, on="viaje_id", how="left")
    v["hora"] = (v["t_prog_s"] // 3600) % 24
    return v, p


def estimar(r: pd.DataFrame, rechazos_obs: int) -> tuple[float, float, float]:
    """(malas asignaciones: cota bruta, calibrada con los rechazos; rechazos predichos)."""
    mal = float((r["peso"] * r["p_mal"]).sum())
    rech = float((r["peso"] * r["p_rechazo"]).sum())
    return mal, mal * rechazos_obs / rech if rech else float("nan"), rech


def _resumen(asig: pd.DataFrame, rechazados: int) -> dict:
    bruta, calibrada, rech = estimar(asig, rechazados)
    pasos_viaje = asig["pasos"].mean()
    return {
        "asignados": len(asig),
        "rechazos_obs": rechazados,
        "rechazos_pred": round(rech),
        "pct_mal_cota": 100 * bruta / len(asig),
        "pct_mal_calibrada": 100 * calibrada / len(asig),
        "pasos_mal_calibrada": round(calibrada * pasos_viaje),
    }


def main() -> None:
    v, p = cargar()
    sin_h = v["h_sig_s"].isna() & v["h_ant_s"].isna()
    print(f"viajes sin intervalo (único de su línea en la parada): {sin_h.sum()}")
    v = v.fillna({"h_sig_s": np.inf, "h_ant_s": np.inf})
    asig = cota(v[v["motivo"] == "asignado"], p.margen_min_s)
    rech = v[v["motivo"] == "margen"]

    filas = {"todo": _resumen(asig, len(rech))}

    # Un pliegue que reclama un viaje cuyo bus sí está capturado pierde el
    # conflicto y da la cara. Firma: el perdedor parece adelantado. El exceso de
    # adelantados sobre los asignados estima cuántos pliegues se cazaron así.
    conf = v[v["motivo"] == "conflicto"]
    adel = lambda x: (x["desfase_s"] < -p.margen_min_s).mean()  # noqa: E731
    cazados = max(0.0, (adel(conf) - adel(asig))) * len(conf)
    _, calibrada, _ = estimar(asig, len(rech))
    print(
        f"pliegues: {calibrada:.0f} ({100 * calibrada / len(asig):.1f} %); "
        f"conflictos {len(conf)}, adelantados {100 * adel(conf):.1f} % frente a "
        f"{100 * adel(asig):.1f} % de los asignados: ~{cazados:.0f} cazados. "
        f"Sin delatar: ~{calibrada - cazados:.0f} "
        f"({100 * (calibrada - cazados) / len(asig):.1f} %), como mínimo "
        f"{max(0.0, calibrada - len(conf)):.0f} "
        f"({100 * max(0.0, calibrada - len(conf)) / len(asig):.1f} %)"
    )
    bandas = [0, 8 * 60, 15 * 60, 30 * 60, np.inf]
    nombres = ["H <= 8 min", "8-15 min", "15-30 min", "> 30 min"]
    for col, df in (("banda", asig), ("banda_r", rech)):
        df[col] = pd.cut(
            np.minimum(df["h_sig_s"], df["h_ant_s"]), bandas, labels=nombres
        )
    for b in nombres:
        filas[b] = _resumen(asig[asig["banda"] == b], int((rech["banda_r"] == b).sum()))
    for nombre, horas in (("punta 7-9 y 13-15", [7, 8, 13, 14]), ("resto", None)):
        sel = asig["hora"].isin(horas) if horas else ~asig["hora"].isin([7, 8, 13, 14])
        selr = rech["hora"].isin(horas) if horas else ~rech["hora"].isin([7, 8, 13, 14])
        filas[nombre] = _resumen(asig[sel], int(selr.sum()))
    t = pd.DataFrame(filas).T
    with pd.option_context(
        "display.float_format", "{:.2f}".format, "display.width", 140
    ):
        print(t.to_string())
    # Plegado, un retraso grande pasa por adelanto: la persistencia no lo nota
    # (el viaje entero se desplaza H), pero la variante binaria pierde el positivo.
    u = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"][
        "umbral_retraso_s"
    ]
    d, h = asig["desfase_s"], asig["h_sig_s"]
    tarde = lambda x: cola(d, (h - p.margen_min_s) / 2, x)  # noqa: E731
    w = asig["peso"]
    sobre = (w * tarde(np.full(len(asig), float(u)))).sum()
    pleg = (w * tarde(np.maximum(u, (h + p.margen_min_s) / 2))).sum()
    rech = (w * tarde(np.maximum(u, (h - p.margen_min_s) / 2))).sum() - pleg
    print(
        f"salen con más de {u} s de retraso: {100 * pleg / sobre:.1f} % plegados al "
        f"viaje siguiente, {100 * rech / sobre:.1f} % rechazados por margen"
    )
    x = np.array([60, 120, 180, 300, 420, 600])
    s = cola(asig["desfase_s"], (asig["h_sig_s"] - p.margen_min_s) / 2, x)
    print("\nP(retraso > x), Lynden-Bell:", dict(zip(x.tolist(), np.round(s, 4))))
    print(f"total de pasos asignados: {int(asig['pasos'].sum())}")


if __name__ == "__main__":
    main()
