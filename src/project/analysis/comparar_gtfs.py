"""¿Cuánto de lo etiquetado contradice otra versión del GTFS? (bitácora 042)

    uv run python -m project.analysis.comparar_gtfs data/raw/gtfs_archivo/google_transit2026-10-04.zip

La EMT republica el feed casi a diario y una publicación posterior puede
cambiar el horario de días ya etiquetados. Para cada día de servicio que cubre
el calendario de la otra versión: viajes activos en la que manda
(`gtfs.elegir_horario`) y en la otra, y porcentaje de los pasos etiquetados cuyo
(línea, parada, hora programada) no existe en la otra, con las líneas que lo
concentran. Lee `data/interim/pasos`; nada del pipeline importa de aquí.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from project.config import settings
from project.gtfs import Horario, cargar_horario, elegir_horario, versiones


def _activos(h: Horario, dia) -> pd.DataFrame:
    vj = h.viajes[h.viajes["service_id"].isin(h.servicios(dia))][["trip_id", "linea"]]
    return h.paradas_de_viaje.merge(vj, on="trip_id")


def main(otra: Path) -> None:
    b = cargar_horario(otra)
    horarios = [cargar_horario(r) for r in versiones(settings.gtfs_dir)]
    pasos = pd.read_parquet(
        settings.interim_dir / "pasos",
        columns=["fecha_servicio", "linea", "stop_id", "t_prog_s"],
    )
    pasos["fecha_servicio"] = pd.to_datetime(pasos["fecha_servicio"])
    ini, fin = (pd.Timestamp(d) for d in b.calendario)
    pasos = pasos[pasos["fecha_servicio"].between(ini, fin)]
    print(f"otra: {b.version}, calendario {b.calendario[0]} - {b.calendario[1]}")

    filas = []
    for dia, g in pasos.groupby("fecha_servicio"):
        d = dia.date()
        a, _ = elegir_horario(horarios, d)
        pb = _activos(b, d)
        clave = set(zip(pb["linea"], pb["stop_id"], pb["t_prog_s"]))
        fuera = pd.Series(
            [k not in clave for k in zip(g["linea"], g["stop_id"], g["t_prog_s"])],
            index=g.index,
        )
        por_linea = fuera.groupby(g["linea"]).mean()
        filas.append(
            {
                "dia": f"{d:%Y-%m-%d %a}",
                "manda": a.version,
                "viajes": a.viajes["service_id"].isin(a.servicios(d)).sum(),
                "viajes_otra": pb["trip_id"].nunique(),
                "pasos": len(g),
                "fuera_%": round(100 * fuera.mean(), 1),
                "lineas > 5 %": ", ".join(
                    f"{k} ({v:.0%})"
                    for k, v in por_linea[por_linea > 0.05]
                    .sort_values(ascending=False)
                    .items()
                ),
            }
        )
    print(pd.DataFrame(filas).to_string(index=False))
    lineas = set().union(*(set(h.viajes["linea"]) for h in horarios))
    print(
        "líneas que la otra no tiene:", sorted(lineas - set(b.viajes["linea"]), key=str)
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
