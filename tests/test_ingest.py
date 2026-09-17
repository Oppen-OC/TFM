"""Parseo y corrección horaria de las fuentes. Corre sin red.

Guardia de las trampas 001, 002 y 003 del registro `.claude/trampas/`. Antes
vivía en `demo/selftest.py` con un `check()` casero; al portar `demo/` a
`src/project/` pasó a pytest sin cambiar ni un umbral.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from project.ingest.sources import (
    local_naive_epoch_to_utc,
    local_naive_iso_to_utc,
    now_utc,
    parse,
)

FUENTES = [
    "emt_buses",
    "trafico_estado",
    "trafico_intensidad",
    "valenbisi",
    "renfe_cercanias",
]


# --------------------------------------------------------------------------- #
# 1. Corrección de zona horaria
# --------------------------------------------------------------------------- #
def test_epoch_local_naive_a_utc_en_verano():
    """El campo `fecha` de la EMT es epoch-ms construido desde hora de pared local."""
    # fecha real observada: 1786828132000 -> hora de pared local 21:08:52 del 15/08/2026
    t = local_naive_epoch_to_utc(1786828132000)
    assert t == pd.Timestamp("2026-08-15T19:08:52Z"), f"obtenido {t}"


def test_epoch_local_naive_a_utc_en_invierno():
    """En invierno el desfase es 1 h, no 2. Aquí es donde se rompen las series."""
    t = local_naive_epoch_to_utc(pd.Timestamp("2026-01-15T09:00:00Z").value // 10**6)
    assert t == pd.Timestamp("2026-01-15T08:00:00Z"), f"obtenido {t}"


def test_iso_naive_de_renfe_a_utc():
    assert local_naive_iso_to_utc("2026-08-15T21:11:56") == pd.Timestamp(
        "2026-08-15T19:11:56Z"
    )


# --------------------------------------------------------------------------- #
# 1b. Resolución automática de la convención horaria  ·  TRAMPA 002
# --------------------------------------------------------------------------- #
def _payload_emt(fix: dict, instante_pared: str, convencion: str):
    """Fabrica un payload cuyo `fecha` sigue la convención indicada."""
    ingest = pd.Timestamp(instante_pared, tz="Europe/Madrid").tz_convert("UTC")
    real = ingest - pd.Timedelta(seconds=25)  # dato de hace 25 s
    if convencion == "YA_EN_UTC":
        epoch = int(real.timestamp() * 1000)
    else:  # hora de pared local
        pared = real.tz_convert("Europe/Madrid").tz_localize(None)
        epoch = int(pared.tz_localize("UTC").timestamp() * 1000)
    p = json.loads(json.dumps(fix["emt_buses"]))
    for f in p["features"]:
        f["attributes"]["fecha"] = epoch
    return p, ingest


@pytest.mark.parametrize(
    ("convencion", "momento", "estacion"),
    [
        ("LOCAL_NAIVE", "2026-08-16 09:00:00", "verano (CEST, +2 h)"),
        ("YA_EN_UTC", "2026-08-16 09:00:00", "verano (CEST, +2 h)"),
        ("LOCAL_NAIVE", "2026-01-16 09:00:00", "invierno (CET, +1 h)"),
        ("YA_EN_UTC", "2026-01-16 09:00:00", "invierno (CET, +1 h)"),
    ],
)
def test_detecta_la_convencion_horaria(fix, convencion, momento, estacion):
    pl, ing = _payload_emt(fix, momento, convencion)
    d = parse("emt_buses", pl, ing)
    detectada = d["tz_convencion"].iloc[0]
    lat = float(d["latencia_s"].median())
    assert detectada == convencion and 0 <= lat <= 120, (
        f"{estacion}: detectada={detectada}, latencia={lat:.0f}s"
    )


@pytest.mark.parametrize("antiguedad_s", [3_600, 86_400], ids=["1h", "1d"])
def test_dato_rancio_se_marca_dudosa_en_vez_de_adivinar(fix, antiguedad_s):
    """Un timestamp absurdo no debe elegir en silencio: se marca.

    La hora de antigüedad es la que discrimina: con un día cualquier horquilla
    lo rechaza, pero una horquilla ensanchada hasta el desfase de 2 h aceptaría
    un dato de hace una hora como UTC fresco (mutante 004 de la auditoría).
    """
    pl, ing = _payload_emt(fix, "2026-08-16 09:00:00", "YA_EN_UTC")
    for f in pl["features"]:
        f["attributes"]["fecha"] -= antiguedad_s * 1000
    d = parse("emt_buses", pl, ing)
    assert d["tz_convencion"].iloc[0] == "DUDOSA", d["tz_convencion"].iloc[0]


def test_serie_con_convenciones_alternas_ninguna_fila_desplazada(fix):
    """TRAMPA 002: la EMT alterna UTC y local naive de un sondeo al siguiente.

    Corregir con un desfase fijo deja el 20 % de las filas 2 h desplazadas, y
    eso destruye cualquier etiqueta de retraso sin lanzar una sola excepción.
    """
    lat_todas = []
    for i in range(12):
        conv = "YA_EN_UTC" if i % 4 == 0 else "LOCAL_NAIVE"
        pl, ing = _payload_emt(fix, f"2026-08-16 09:{i:02d}:00", conv)
        lat_todas += parse("emt_buses", pl, ing)["latencia_s"].tolist()
    peor = max(abs(x) for x in lat_todas)
    assert peor < 3600, f"máx |latencia| = {peor:.0f}s"


# --------------------------------------------------------------------------- #
# 2. Parsers sobre payloads con la forma real
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("clave", FUENTES)
def test_parser_devuelve_filas(fix, clave):
    df = parse(clave, fix[clave], now_utc())
    assert len(df) > 0, f"filas={len(df)}"


@pytest.mark.parametrize("clave", FUENTES)
def test_parser_tiene_ts_utc_y_ts_ingest_utc(fix, clave):
    """`ts_utc` es cuándo ocurrió el dato; `ts_ingest_utc`, cuándo lo capturamos.

    Sin esa separación no se puede medir la latencia de la fuente, y sin eso se
    le acaba dando al modelo información que en producción no tendría.
    """
    df = parse(clave, fix[clave], now_utc())
    assert {"ts_utc", "ts_ingest_utc"}.issubset(df.columns)


def test_renfe_filtra_solo_nucleo_40(fix):
    """TRAMPA 003: la raíz de Renfe es un objeto, no un array.

    Sin filtrar `nucleo == "40"` te llevas la flota nacional entera sin que nada
    falle: el DataFrame sale bien formado, solo que con trenes de toda España.
    """
    df = parse("renfe_cercanias", fix["renfe_cercanias"], now_utc())
    assert len(df) == 2, f"filas={len(df)}"


def test_renfe_retraso_min_es_numerico(fix):
    df = parse("renfe_cercanias", fix["renfe_cercanias"], now_utc())
    assert pd.api.types.is_numeric_dtype(df["retraso_min"])


def test_renfe_ts_utc_es_la_fecha_de_actualizacion_y_no_la_captura(fix):
    """`ts_utc` es cuándo publicó Renfe, no cuándo lo leímos.

    Con `fechaActualizacion` 21:11:56 local, `ts_utc` debe ser 19:11:56 UTC
    aunque la captura sea de otro día. Confundirlos borra la latencia de la
    fuente sin error alguno (mutante 008 de la auditoría).
    """
    captura = pd.Timestamp("2026-08-16T09:00:00Z")
    df = parse("renfe_cercanias", fix["renfe_cercanias"], captura)
    assert (df["ts_utc"] == pd.Timestamp("2026-08-15T19:11:56Z")).all(), df["ts_utc"]
    assert (df["ts_ingest_utc"] == captura).all()


@pytest.mark.parametrize("clave", ["trafico_estado", "trafico_intensidad"])
def test_filas_hueco_de_trafico_se_descartan(fix, clave):
    """TRAMPA 005: 34 de las 446 filas de la capa 192 no son tramos.

    Llegan sin `idtramo`, sin geometría y sin estado. El fixture real está
    recortado a tres filas y no trae ninguna, así que hasta la auditoría de
    09/2026 nada comprobaba que el parser las descartase: se inyectan aquí con la
    forma que tienen en el crudo (atributos a nulo, geometría nula).
    """
    limpio = parse(clave, fix[clave], now_utc())
    p = json.loads(json.dumps(fix[clave]))
    hueco = json.loads(json.dumps(p["features"][0]))
    hueco["attributes"] = dict.fromkeys(hueco["attributes"])
    hueco["geometry"] = None
    p["features"] += [hueco, json.loads(json.dumps(hueco))]

    df = parse(clave, p, now_utc())
    assert len(df) == len(limpio), f"{len(df)} filas, esperadas {len(limpio)}"
    assert df["idtramo"].notna().all()


def test_trafico_intensidad_lectura_menos_uno_es_nulo(fix):
    """-1 es el centinela de "sin lectura". Tratarlo como valor sesga la media."""
    df = parse("trafico_intensidad", fix["trafico_intensidad"], now_utc())
    assert df["lectura"].isna().sum() == 1, f"nulos={df['lectura'].isna().sum()}"


def test_emt_snapshot_id_es_el_gid_minimo_del_bloque(fix):
    df = parse("emt_buses", fix["emt_buses"], now_utc())
    assert int(df["snapshot_id"].iloc[0]) == 1659987635


# --------------------------------------------------------------------------- #
# 4. `gid` NO identifica al vehículo  ·  TRAMPA 001
# --------------------------------------------------------------------------- #
def test_gids_de_sondeos_consecutivos_son_disjuntos(fix):
    """TRAMPA 001: `gid` identifica al refresco, no al vehículo.

    La tabla se trunca y se reinserta entera en cada sondeo, así que la
    intersección de gids entre dos sondeos consecutivos es exactamente cero.
    Solo vale como `snapshot_id`; la identidad hay que inferirla.
    """
    b0, b1 = set(fix["bloques_gid"]["t0"]), set(fix["bloques_gid"]["t1"])
    assert len(b0 & b1) == 0, f"intersección={len(b0 & b1)}"


def test_los_bloques_de_gid_son_contiguos(fix):
    """Contiguos y disjuntos: la firma de un truncate + reinsert."""
    b0, b1 = set(fix["bloques_gid"]["t0"]), set(fix["bloques_gid"]["t1"])
    assert min(b1) - max(b0) == 1, f"salto={min(b1) - max(b0)}"
