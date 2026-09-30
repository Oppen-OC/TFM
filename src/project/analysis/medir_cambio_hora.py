"""¿Qué se habría etiquetado el día del cambio de hora midiendo desde la medianoche?

    uv run python -m project.analysis.medir_cambio_hora                  # 30/08, domingo
    uv run python -m project.analysis.medir_cambio_hora --dia 2026-08-27

Contrafactual sobre una jornada real (trampa 015, bitácora 034). El 25/10 la
medianoche local cae una hora antes que el origen de las horas del GTFS. Aquí
se etiqueta el mismo día dos veces sobre las MISMAS trayectorias, con el origen
bueno y con el origen una hora antes, y se cuenta qué le pasa a cada viaje que
estaba asignado. Cambia `etiquetado._medianoche` en memoria y lo restaura.
"""

from __future__ import annotations

import argparse

import pandas as pd

from project import etiquetado, prepare
from project.config import settings
from project.gtfs import cargar_horario, versiones
from project.tracking import rastrear


def medir(dia: str) -> None:
    df = prepare.cargar_dia(dia)
    pos = rastrear(df[df["trayecto"].notna()])
    horarios = [cargar_horario(r) for r in versiones(settings.gtfs_dir)]
    p = prepare.cargar_parametros()

    bueno = etiquetado.etiquetar(pos, horarios, p)
    original = etiquetado._medianoche
    etiquetado._medianoche = lambda d: original(d) - pd.Timedelta(hours=1)
    try:
        malo = etiquetado.etiquetar(pos, horarios, p)
    finally:
        etiquetado._medianoche = original

    v = bueno.viajes.merge(
        malo.viajes[["viaje_id", "motivo", "trip_id"]],
        on="viaje_id",
        suffixes=("", "_malo"),
    )
    asig = v[v["motivo"] == "asignado"]
    sigue = asig["motivo_malo"] == "asignado"
    otro = sigue & (asig["trip_id_malo"] != asig["trip_id"])
    print(f"\n  {dia}: {len(asig):,} viajes asignados con el origen bueno")
    print(f"    asignados a OTRO viaje programado  {otro.sum():6,} ({otro.mean():.1%})")
    print(f"    asignados al mismo                 {(sigue & ~otro).sum():6,}")
    for motivo, n in asig.loc[~sigue, "motivo_malo"].value_counts().items():
        print(f"    rechazados por {motivo:20}{n:6,} ({n / len(asig):.1%})")
    nuevos = (v["motivo"] != "asignado") & (v["motivo_malo"] == "asignado")
    print(f"    asignados que antes no lo estaban  {nuevos.sum():6,}")

    j = bueno.pasos.merge(
        malo.pasos[["viaje_id", "stop_id", "stop_sequence", "retraso_s", "t_prog_s"]],
        on=["viaje_id", "stop_id", "stop_sequence"],
        suffixes=("", "_malo"),
    )
    print(
        f"\n  pasos: {len(bueno.pasos):,} buenos, {len(malo.pasos):,} con el origen malo"
    )
    if len(j):
        d = (j["retraso_s_malo"] - j["retraso_s"]).abs()
        salto = (j["t_prog_s_malo"] - j["t_prog_s"]).median()
        print(
            f"    en los {len(j):,} comunes, el programado se va {salto:+.0f} s (mediana)"
        )
        print(
            f"    |error del retraso|: mediana {d.median():.0f} s, p90 "
            f"{d.quantile(0.9):.0f} s; a menos de 60 s, el {(d <= 60).mean():.1%}"
        )


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--dia", default="2026-08-30")
    medir(a.parse_args().dia)
