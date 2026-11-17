"""¿Califica el marcador de la demo cada predicción con el paso de su propio bus?

    uv run python -m project.analysis.medir_marcador_vivo --dia 2026-10-01 \\
        --stop 2277 --desde 07:00 --hasta 10:30

Reproduce la demo ciclo a ciclo sobre un día capturado: un `Vivo` de verdad, con
su `Marcador`, llamado con un `ahora` histórico cada `--cada-min`. La clave del
marcador es `(fecha_servicio, viaje_id)`, y cada ciclo reetiqueta el día desde el
principio: `rastrear` y la asignación del viaje programado pueden cambiar con lo
que llega después (puerta 014, trampa 014). Si cambian, una predicción congelada
se queda sin verificar o se verifica con el paso de otro bus, sin error.

La identidad física no es la clave: es el último paso sabido al congelar (línea,
`stop_sequence`, `t_obs_utc`). Un paso sabido ya no cambia (`provisionales`), así
que el etiquetado del día completo lo vuelve a tener, con el mismo `t_obs`, sea
cual sea su `viaje_id`. La verdad es el paso de ESE viaje por la parada en el día
completo; el paso con que el marcador verificó se anota en el ciclo en que lo hace.

Sin historial: las variables del modelo cambian, la identidad no, y el ciclo
cuesta un tercio. Solo lectura; el JSON sale por stdout. Fuera del grafo de DVC.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

import pandas as pd
import yaml

from project.analysis.medir_ciclo_vivo import hasta_utc
from project.config import RAIZ, settings
from project.gtfs import cargar_horario, versiones
from project.prepare import cargar_parametros, ventana_servicio
from project.services.model_service import Servicio
from project.services.vivo import Vivo, dia_de_servicio, separar

TOLERANCIA_S = 1.0  # mismo paso físico: el mismo t_obs, salvo redondeo


def _sabidos(pasos: pd.DataFrame, ahora: pd.Timestamp) -> pd.DataFrame:
    """Como en `Vivo._resultado`: separados y con la fecha que lleva la clave."""
    s = separar(pasos, ahora)[0]
    return s.assign(fecha_servicio=pd.to_datetime(s["fecha_servicio"]))


def ancla(sabidos: pd.DataFrame, clave: tuple) -> dict:
    """El último paso sabido del viaje `clave`: la fila que se predijo."""
    v = sabidos[
        (sabidos["fecha_servicio"] == clave[0]) & (sabidos["viaje_id"] == clave[1])
    ]
    u = v.sort_values("stop_sequence", kind="stable").iloc[-1]
    return {
        "linea": str(u["linea"]),
        "stop_sequence": int(u["stop_sequence"]),
        "t_obs_utc": u["t_obs_utc"],
        "trip_id": str(u["trip_id"]),
    }


def paso_verificador(sabidos: pd.DataFrame, clave: tuple, seq: int, stop: str):
    """El paso con que `Marcador.verificar` califica: misma casación que él."""
    m = sabidos[
        (sabidos["fecha_servicio"] == clave[0])
        & (sabidos["viaje_id"] == clave[1])
        & (sabidos["stop_sequence"] == seq)
        & (sabidos["stop_id"] == stop)
        & sabidos["retraso_s"].notna()
    ]
    if m.empty:
        return None
    r = m.iloc[0]
    return {"t_obs_utc": r["t_obs_utc"], "retraso_s": float(r["retraso_s"])}


def clasificar(
    congeladas: dict[tuple, dict], final: pd.DataFrame, stop: str, limite
) -> list[dict]:
    """Una fila por predicción congelada, con su clase.

    `congeladas[clave]` lleva el `ancla`, `objetivo_seq` y `verificado` (lo de
    `paso_verificador`, o None). `final` son los pasos del día completo con
    `t_disp_utc`. Solo cuentan las predicciones cuya verdad ya se sabía en
    `limite`: después, que no se haya verificado no dice nada.
    """
    filas = []
    for clave, c in congeladas.items():
        a, ver = c["ancla"], c["verificado"]
        fila = {
            "viaje_id": clave[1],
            "linea": a["linea"],
            "t_congelada": c["t_congelada"],
        }
        mismo = final[
            (final["linea"] == a["linea"])
            & (final["stop_sequence"] == a["stop_sequence"])
            & (
                (final["t_obs_utc"] - a["t_obs_utc"]).dt.total_seconds().abs()
                <= TOLERANCIA_S
            )
        ]
        if mismo.empty:
            filas.append(fila | {"clase": "ancla_perdida"})
            continue
        viaje = mismo.iloc[0]
        destino = final[
            (final["fecha_servicio"] == viaje["fecha_servicio"])
            & (final["viaje_id"] == viaje["viaje_id"])
            & (final["stop_id"] == stop)
            & (final["stop_sequence"] > a["stop_sequence"])
        ].sort_values("stop_sequence", kind="stable")
        fila |= {
            "viaje_id_final": viaje["viaje_id"],
            "trip_id_cambia": str(viaje["trip_id"]) != a["trip_id"],
        }
        if destino.empty:
            filas.append(fila | {"clase": "no_llega"})
            continue
        verdad = destino.iloc[0]
        if pd.isna(verdad["t_disp_utc"]) or verdad["t_disp_utc"] > limite:
            filas.append(fila | {"clase": "fuera_de_ventana"})
            continue
        if pd.isna(verdad["retraso_s"]):
            filas.append(fila | {"clase": "sin_retraso"})
            continue
        if ver is None:
            clase = "huerfana"
        elif abs((ver["t_obs_utc"] - verdad["t_obs_utc"]).total_seconds()) > (
            TOLERANCIA_S
        ):
            clase = "cruzada"  # el paso de otro bus
        elif abs(ver["retraso_s"] - float(verdad["retraso_s"])) > 0.5:
            clase = "otro_retraso"  # su paso, con otro viaje programado
        else:
            clase = "correcta"
        filas.append(fila | {"clase": clase})
    return filas


def main(dia: str, stop: str, desde: str, hasta: str, cada_min: int) -> dict:
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    horarios = [cargar_horario(r) for r in versiones(settings.gtfs_dir)]
    v = Vivo(Servicio.desde_disco(), horarios, pd.DataFrame(), cfg, cargar_parametros())
    visto: dict[str, pd.DataFrame] = {}
    etiquetar = v._etiquetar

    def anotar(frame, llegadas, lineas, ahora):
        visto["pasos"] = etiquetar(frame, llegadas, lineas, ahora)
        return visto["pasos"]

    v._etiquetar = anotar
    cortes = pd.date_range(
        hasta_utc(dia, desde), hasta_utc(dia, hasta), freq=f"{cada_min}min"
    )
    congeladas: dict[tuple, dict] = {}
    for ahora in cortes:
        visto["pasos"] = pd.DataFrame()
        v.parada(stop, ahora)
        if visto["pasos"].empty:
            continue
        sab = _sabidos(visto["pasos"], ahora)
        for clave, e in v.marcador.entradas(stop).items():
            if clave not in congeladas:
                congeladas[clave] = {
                    "ancla": ancla(sab, clave),
                    "objetivo_seq": e["congelada"].stop_sequence,
                    "t_congelada": ahora.isoformat(),
                    "verificado": None,
                }
            c = congeladas[clave]
            if e["resultado"] is not None and c["verificado"] is None:
                c["verificado"] = paso_verificador(sab, clave, c["objetivo_seq"], stop)

    # La verdad, el día completo. La ventana es [desde, fin): `fin` ya es del día
    # de servicio siguiente.
    servicio = dia_de_servicio(cortes[0])
    fin = ventana_servicio(servicio)[1] - pd.Timedelta(seconds=1)
    lineas = v._lineas_por_parada(v._horario_de(servicio), servicio)[stop]
    frame, llegadas, _, _ = v._leer_hoy(fin)
    final = etiquetar(frame, llegadas, lineas, fin)
    final = final.assign(fecha_servicio=pd.to_datetime(final["fecha_servicio"]))
    # Margen de dos ciclos: lo sabido justo antes del último corte aún no ha
    # tenido ciclo en que verificarse.
    limite = cortes[-1] - pd.Timedelta(minutes=2 * cada_min)
    filas = clasificar(congeladas, final, stop, limite)
    clases = Counter(f["clase"] for f in filas)
    evaluables = [
        f
        for f in filas
        if f["clase"] in {"correcta", "huerfana", "cruzada", "otro_retraso"}
    ]
    return {
        "dia": dia,
        "stop_id": stop,
        "lineas": lineas,
        "cortes": len(cortes),
        "cada_min": cada_min,
        "desde_utc": cortes[0].isoformat(),
        "hasta_utc": cortes[-1].isoformat(),
        "congeladas": len(filas),
        "clases": dict(sorted(clases.items())),
        "evaluables": len(evaluables),
        "mal_calificadas": sum(f["clase"] != "correcta" for f in evaluables),
        "viaje_id_cambia": sum(
            f.get("viaje_id_final") != f["viaje_id"] for f in evaluables
        ),
        "trip_id_cambia": sum(f.get("trip_id_cambia", False) for f in evaluables),
        "casos": [f for f in filas if f["clase"] != "correcta"],
    }


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--dia", required=True)
    a.add_argument("--stop", required=True)
    a.add_argument("--desde", required=True, help="HH:MM local")
    a.add_argument("--hasta", required=True, help="HH:MM local")
    a.add_argument("--cada-min", type=int, default=2)
    args = a.parse_args()
    r = main(args.dia, args.stop, args.desde, args.hasta, args.cada_min)
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
