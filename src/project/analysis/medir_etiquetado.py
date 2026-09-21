"""¿Cuánto y qué tan bien etiqueta `prepare`? Medición sobre su salida.

    uv run python -m project.analysis.medir_etiquetado                 # data/interim
    uv run python -m project.analysis.medir_etiquetado --raiz DIR      # otra salida

Por día de servicio:

  cobertura    viajes programados de las líneas capturadas que quedan
               etiquetados, frente a los que el GTFS activa ese día. Mezcla dos
               cosas: lo que la fuente no publica (hay líneas que dejan de
               aparecer) y lo que el etiquetado no consigue asignar.
  éxito        tramos asignados sobre los tramos de SERVICIO: todos menos los
               cortos (esperas, cochera, fragmentos) y los de líneas sin
               trazado. Es la cifra del método, sin la de la fuente.
  posiciones   parte de las posiciones fiables que acaba en un viaje etiquetado;
               lo demás son tramos cortos, fragmentos del tracker incluidos.
  tramos       por motivo (asignado, corto, margen, conflicto, desfase...).
  retraso      distribución de `retraso_s` por paso y por hora local.
  margen       distribución del margen de asignación: cuánto más lejos quedaba el
               segundo viaje candidato.
  baselines    MAE de predecir el retraso de la parada siguiente con 0 (el
               horario) y con el de la parada actual (persistencia), sólo como
               comprobación de cordura de la etiqueta: el modelo va aparte.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from project.config import settings
from project.gtfs import cargar_horario, elegir_horario, versiones


def _leer(raiz: Path, nombre: str) -> pd.DataFrame:
    partes = sorted((raiz / nombre).rglob("*.parquet"))
    return pd.concat((pd.read_parquet(p) for p in partes), ignore_index=True)


def medir(raiz: Path) -> None:
    pasos = _leer(raiz, "pasos")
    viajes = _leer(raiz, "viajes")
    horarios = [cargar_horario(r) for r in versiones(settings.gtfs_dir)]

    print("\n  Tramos observados por motivo:")
    m = viajes.groupby(["fecha_servicio", "motivo"]).size().unstack(fill_value=0)
    print(m.to_string())

    # Cobertura: viajes programados activos de las líneas que se capturaron.
    filas = []
    for dia, v in viajes.groupby("fecha_servicio"):
        h, dentro = elegir_horario(horarios, dia)
        if h is None:
            continue
        lineas = set(v["linea"].astype(str))
        activos = h.servicios(dia)
        prog = h.viajes[
            h.viajes["service_id"].isin(activos) & h.viajes["linea"].isin(lineas)
        ]
        asignados = v[v["motivo"] == "asignado"]
        filas.append(
            {
                "dia": dia,
                "feed": h.version,
                "vigente": dentro,
                "programados": len(prog),
                "etiquetados": asignados["trip_id"].nunique(),
                "cobertura": asignados["trip_id"].nunique() / max(len(prog), 1),
                "pasos": int((pasos["fecha_servicio"] == dia).sum()),
            }
        )
    print("\n  Cobertura sobre los viajes programados (líneas capturadas):")
    print(pd.DataFrame(filas).round(3).to_string(index=False))

    servicio = viajes[~viajes["motivo"].isin(["corto", "sin_trazado"])]
    exito = (
        (servicio["motivo"] == "asignado").groupby(servicio["fecha_servicio"]).mean()
    )
    print("\n  Éxito sobre los tramos de servicio (asignados / no cortos con trazado):")
    print(exito.round(3).to_string())

    pos = _leer(raiz, "emt_tracked")
    fiables = pos[pos["fiable"].astype(bool)]
    asignados = set(viajes.loc[viajes["motivo"] == "asignado", "viaje_id"])
    en_asignado = fiables["viaje_id"].isin(asignados)
    print(
        f"\n  Posiciones fiables en viajes etiquetados: {en_asignado.mean():.1%} "
        f"de {len(fiables):,}; en servicio (entre la primera y la última parada "
        f"cruzada): {(fiables['estado'] == 'servicio').mean():.1%}"
    )

    r = pasos["retraso_s"]
    q = r.quantile([0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99])
    print(f"\n  Retraso por paso (s), {len(r):,} pasos:")
    print("   " + "  ".join(f"p{int(k * 100)} {v:6.0f}" for k, v in q.items()))
    print(f"   |retraso| > 20 min: {int((r.abs() > 1200).sum()):,}")
    hora = pasos["t_obs_utc"].dt.tz_convert(settings.tz_local).dt.hour
    print("  Mediana por hora local:")
    print(r.groupby(hora).median().round(0).to_string())

    mg = viajes.loc[viajes["motivo"] == "asignado", "margen_s"].replace(np.inf, np.nan)
    print("\n  Margen de asignación de los viajes asignados (s):")
    print(
        "   "
        + "  ".join(
            f"p{int(k * 100)} {v:6.0f}"
            for k, v in mg.quantile([0.05, 0.25, 0.5]).items()
        )
    )

    # Baselines de cordura: la parada siguiente de un mismo viaje.
    p = pasos.sort_values(["viaje_id", "stop_sequence"], kind="stable")
    sig = p.groupby("viaje_id")["retraso_s"].shift(-1)
    ok = sig.notna()
    print("\n  Predecir el retraso de la parada siguiente (MAE, s):")
    print(f"   horario (retraso = 0)        {sig[ok].abs().mean():7.1f}")
    print(
        f"   persistencia (el de ahora)   {(sig[ok] - p.loc[ok, 'retraso_s']).abs().mean():7.1f}"
    )


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--raiz", type=Path, default=settings.interim_dir)
    medir(a.parse_args().raiz)
