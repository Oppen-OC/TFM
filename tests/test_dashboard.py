"""Guardias del dashboard de la defensa, fase 1 (ingesta).

La página enseña cifras al tribunal. Lo que se guarda aquí es que salgan del
dato y no de una plantilla, que cuadren con la ficha que las publicó y que los
extractores midan lo que dicen sobre un crudo de verdad conocida.
"""

from __future__ import annotations

import copy
import json
import re

import pandas as pd
import pytest

from project.analysis.dashboard_ingesta import extraer, figuras, foto
from project.ingest import sources
from project.analysis.dashboard_ingesta.paradas import (
    PARADAS,
    CotejoError,
    cotejar,
    escribir_foto,
    fecha_parada,
    redactar,
    validar_prueba,
)

SERIE = {
    "tipo": "serie",
    "x": ["2026-09-01", "2026-09-02", "2026-09-03"],
    "series": [{"nombre": "s", "valores": [1.0, None, 3.0]}],
    "sombras": [{"desde": "2026-09-02", "hasta": "2026-09-02", "etiqueta": "hueco"}],
    "anotaciones": [{"x": "2026-09-03", "texto": "algo"}],
}


def test_las_plantillas_no_llevan_cifras_escritas_a_mano():
    """Un número en la plantilla no sale del dato: es una cifra copiada a mano."""
    con_digitos = [p["id"] for p in PARADAS if re.search(r"\d", p["texto"])]
    assert not con_digitos, con_digitos


def test_un_hueco_sin_cifra_no_se_publica_vacio():
    assert redactar("{a} de {b}", {"a": 3, "b": 1234}) == "3 de 1.234"
    with pytest.raises(KeyError):
        redactar("{a} de {b}", {"a": 3})


def test_las_fechas_del_camino_no_retroceden():
    """El marcador avanza en tiempo de desarrollo: ninguna parada antes que la previa."""
    fechas = [fecha_parada(p) for p in PARADAS]
    assert fechas == sorted(fechas), list(zip([p["id"] for p in PARADAS], fechas))


def test_el_cotejo_para_si_la_cifra_no_cuadra_con_su_ficha():
    exacto = [{"cifra": "n", "esperado": 100, "ficha": "bitácora 999"}]
    tolerado = [{"cifra": "n", "esperado": 100, "tolerancia": 0.02, "ficha": "b"}]
    minimo = [{"cifra": "n", "minimo": 100, "ficha": "trampa 999"}]
    assert cotejar("P0", {"n": 100}, exacto)
    assert cotejar("P0", {"n": 101.5}, tolerado)
    assert cotejar("P0", {"n": 150}, minimo)
    for cotejo, valor in [(exacto, 101), (tolerado, 103), (minimo, 99)]:
        with pytest.raises(CotejoError):
            cotejar("P0", {"n": valor}, cotejo)


def test_la_prueba_cumple_el_contrato_de_la_pagina():
    validar_prueba(SERIE)
    validar_prueba(
        {"tipo": "cifra", "valor": 1.5, "decimales": 1, "etiqueta": "e", "detalle": []}
    )
    with pytest.raises(ValueError):
        validar_prueba({"tipo": "cifra", "valor": 1.5, "etiqueta": "e", "detalle": []})
    with pytest.raises(ValueError, match="exactamente dos"):
        validar_prueba({"tipo": "pares", "registros": [{}], "resalta": "k"})
    corta = copy.deepcopy(SERIE)
    corta["series"][0]["valores"] = [1.0]
    with pytest.raises(ValueError, match="no casan"):
        validar_prueba(corta)


def test_una_anotacion_fuera_de_la_serie_no_se_dibuja_en_el_vacio():
    fuera = copy.deepcopy(SERIE)
    fuera["anotaciones"] = [{"x": "2026-10-06", "texto": "fuera"}]
    with pytest.raises(ValueError, match="fuera de la serie"):
        validar_prueba(fuera)


def test_la_foto_es_un_script_y_no_pasa_del_limite(tmp_path):
    destino = tmp_path / "datos" / "ingesta.js"
    escribir_foto({"paradas": [], "n": 1}, destino)
    texto = destino.read_text(encoding="utf-8")
    assert texto.startswith("window.DATOS = ") and texto.rstrip().endswith(";")
    cuerpo = texto.removeprefix("window.DATOS = ").rstrip().removesuffix(";")
    assert json.loads(cuerpo) == {"paradas": [], "n": 1}
    with pytest.raises(ValueError, match="límite"):
        escribir_foto({"relleno": "x" * 2_100_000}, destino)


T = pd.Timestamp("2026-08-15T23:50:00Z")


def _emt(gids: range, ts: pd.Timestamp, local: bool) -> dict:
    """Un payload de la EMT con la forma real: la `fecha` de cada bus va 25 s por
    detrás de la captura, en UTC o en hora de Madrid leída como si fuera UTC."""
    fecha = ts - pd.Timedelta(seconds=25)
    if local:
        fecha = fecha.tz_convert("Europe/Madrid").tz_localize(None).tz_localize("UTC")
    ms = int(fecha.timestamp() * 1000)
    return {
        "features": [
            {
                "attributes": {
                    "gid": g,
                    "linea": "70",
                    "trayecto": "A - B",
                    "fecha": ms,
                },
                "geometry": {"x": -0.35, "y": 39.49},
            }
            for g in gids
        ]
    }


def _capturar(root, capturas, inicio=T):
    for gids, segundos, local in capturas:
        ts = inicio + pd.Timedelta(seconds=segundos)
        sources.append_raw(root, "emt_buses", _emt(gids, ts, local), ts)


def test_la_alternancia_se_cuenta_por_sondeo_y_cruza_el_cambio_de_dia(tmp_path):
    """Trampa 002. La EMT sirve a veces el mismo sondeo dos veces con la convención
    contraria, y esa repetición no es una alternancia. La ventana cruza la
    medianoche UTC, como la de la primera captura."""
    _capturar(
        tmp_path,
        [
            (range(100, 110), 0, False),
            (range(100, 110), 10, True),  # el mismo sondeo, otra convención
            (range(200, 210), 30, False),
            (range(300, 310), 900, True),  # 00:05 UTC del día siguiente
        ],
    )

    a = extraer.alternancia(
        tmp_path / "raw", T - pd.Timedelta(minutes=1), T + pd.Timedelta(hours=1)
    )

    assert a["sondeos"] == 3 and a["alternancias"] == 1, a
    # 10 filas en hora local de las 30 que suman los tres sondeos.
    assert a["desplazadas"] == pytest.approx(100 / 3)
    antes, despues = a["par"]
    assert antes["campos"]["diferencia"] == "+0 h"
    assert despues["campos"]["diferencia"] == "+2 h"
    assert despues["campos"]["convención"] == "hora local"


def test_dos_sondeos_distintos_no_comparten_gid_y_la_repeticion_no_cuenta(tmp_path):
    """Trampa 001. El bloque a medias y el completo son el MISMO sondeo y sí
    comparten gid (trampa 011): cada sondeo se compara con el anterior distinto."""
    _capturar(
        tmp_path,
        [
            (range(100, 110), 0, False),
            (range(200, 204), 30, False),  # a medias
            (range(200, 210), 40, False),  # el mismo, completo
            (range(300, 310), 60, False),
        ],
        inicio=pd.Timestamp("2026-08-16T08:00:00Z"),
    )

    g = extraer.gid_por_sondeo(tmp_path / "raw", "2026-08-16")

    assert g["pares"] == 2 and g["con_comun"] == 0, g
    assert g["par"][1]["campos"]["gid en común con el anterior"] == "0"


def test_el_bloque_a_medias_se_encuentra_y_la_copia_identica_no(tmp_path):
    """Trampa 011: la primera captura trae el prefijo de gid del bloque."""
    _capturar(
        tmp_path,
        [
            (range(100, 110), 0, False),
            (range(100, 110), 5, False),  # repetición idéntica: no es a medias
            (range(200, 205), 30, False),
            (range(200, 220), 40, False),
        ],
        inicio=pd.Timestamp("2026-08-16T08:00:00Z"),
    )

    b = extraer.bloque_a_medias(tmp_path / "raw", ["2026-08-15", "2026-08-16"])

    assert b["filas"] == (5, 20), b
    assert [r["campos"]["sondeo (gid mínimo)"] for r in b["par"]] == ["200", "200"]


def test_un_dia_sin_crudo_es_un_cero_y_no_desaparece(tmp_path, fix):
    """Bitácora 021: del 10 al 14/09 no hay ni directorio. Si el día falta de la
    serie en vez de valer 0, el hueco no se ve."""
    for ts in ["2026-09-01T10:00Z", "2026-09-01T10:05Z", "2026-09-04T09:00Z"]:
        sources.append_raw(
            tmp_path, "trafico_estado", fix["trafico_estado"], pd.Timestamp(ts)
        )

    n, huecos = extraer.completitud(
        tmp_path / "raw", "trafico_estado", "2026-09-01", "2026-09-04"
    )

    assert list(n.index) == ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"]
    assert list(n) == [2, 0, 0, 1]
    assert huecos == [
        (pd.Timestamp("2026-09-01T10:05Z"), pd.Timestamp("2026-09-04T09:00Z"))
    ]


def test_el_latido_del_colector_cuenta_toda_respuesta_guardada(tmp_path, fix):
    """P5, bitácora 021: Renfe prueba que el colector seguía vivo con las capas
    caídas. De madrugada no hay trenes de València, y a veces la flota nacional
    trae un tren sin `porAvanc`: `parse` no saca filas o falla, pero el colector
    respondió. Contar solo sondeos (trampa 018) pinta 5 h sin colector."""
    dia = copy.deepcopy(fix["renfe_cercanias"])
    noche = {**dia, "trenes": [t for t in dia["trenes"] if t["nucleo"] != "40"]}
    sin_avance = {
        **dia,
        "trenes": [{k: v for k, v in dia["trenes"][0].items() if k != "porAvanc"}],
    }
    inicio = pd.Timestamp("2026-09-12T01:00Z")
    ts = [inicio + pd.Timedelta(minutes=8 * i) for i in range(3)]
    for payload, t in zip([dia, noche, sin_avance], ts):
        sources.append_raw(tmp_path, "renfe_cercanias", payload, t)

    capturas = extraer.capturas(
        tmp_path / "raw", "renfe_cercanias", "2026-09-11", "2026-09-12"
    )

    assert capturas == ts


def test_un_dia_de_prueba_con_errores_del_geoportal_cae_y_se_dice_cual(
    tmp_path, monkeypatch
):
    """P10, trampa 018: el 13/10 el geoportal respondió `{"error"}` 3 h 45 min y,
    contando líneas, el día pasaba por completo. Aquí, tres días de prueba y el
    segundo con dos horas de errores seguidos."""
    monkeypatch.setattr(foto, "INICIO", "2026-10-07")
    monkeypatch.setattr(foto, "PRUEBA", ("2026-10-07", "2026-10-09"))
    monkeypatch.setattr(foto, "COTEJO_PRUEBA", ("2026-10-07", "2026-10-07"))
    error = {"error": {"code": 499, "message": "Token Required", "details": []}}
    inicio = pd.Timestamp("2026-10-07T00:00Z")
    caida = (pd.Timestamp("2026-10-08T10:00Z"), pd.Timestamp("2026-10-08T12:00Z"))
    for i in range(3 * 48):  # cada 30 min
        ts = inicio + pd.Timedelta(minutes=30 * i)
        payload = (
            error
            if caida[0] <= ts <= caida[1]
            else _emt(range(100 * i, 100 * i + 3), ts, False)
        )
        sources.append_raw(tmp_path, "emt_buses", payload, ts)

    valores, prueba = foto.p10(tmp_path / "raw", "2026-10-09")

    assert (valores["utiles"], valores["dias"]) == (2, 3), valores
    assert valores["caidos"] == "08/10"
    # Del último sondeo bueno (09:30) al siguiente (12:30).
    assert valores["horas_caida"] == pytest.approx(3)
    validar_prueba(prueba)


def test_el_ultimo_dia_del_crudo_se_da_por_incompleto(tmp_path):
    """El colector puede estar escribiendo el último día: dibujarlo pinta una
    caída que no existe."""
    for d in ["2026-10-10", "2026-10-11", "2026-10-12"]:
        (tmp_path / "source=emt_buses" / f"date={d}").mkdir(parents=True)
    assert extraer.ultimo_dia_completo(tmp_path) == "2026-10-11"


def test_sin_crudo_de_la_emt_el_exportador_dice_que_traer(tmp_path):
    with pytest.raises(FileNotFoundError, match="pull_data.sh"):
        extraer.ultimo_dia_completo(tmp_path)


def test_la_serie_de_tramos_deja_hueco_en_los_dias_sin_datos_y_acaba_antes_de_la_prueba(
    monkeypatch,
):
    """Con las capas caídas (11/09) `lectivo()` no devuelve fila: unir el 10 con el
    12 dibuja una congestión que nadie midió. Y del 07/10 en adelante, la prueba
    del ADR-024, solo se cuentan sondeos."""
    dias = [str(d.date()) for d in pd.date_range("2026-09-08", "2026-10-12")]
    dias.remove("2026-09-11")
    d = pd.DataFrame({"dia": dias})
    estado = d.assign(
        dow=(pd.to_datetime(d["dia"]).dt.dayofweek + 1) % 7,
        tramos_congestion=range(10, 10 + len(d)),
    )
    intensidad = d.assign(valores_distintos=243)
    monkeypatch.setattr(
        foto.medir_fuentes,
        "lectivo",
        lambda: {"estado": estado, "intensidad": intensidad},
    )

    _, prueba = foto.p7("2026-10-12")

    x = prueba["x"]
    assert x[-1] == "2026-10-06", x[-3:]
    i = x.index("2026-09-11")
    for s in prueba["series"]:
        assert s["valores"][i] is None
        assert s["valores"][i - 1] is not None and s["valores"][i + 1] is not None
    validar_prueba(prueba)


def test_la_figura_de_una_serie_es_un_pdf(tmp_path):
    destino = tmp_path / "figuras" / "P5.pdf"
    figuras.figura_serie(SERIE, "Una serie", destino)
    assert destino.read_bytes()[:5] == b"%PDF-"


def test_sin_las_cuentas_de_curar_el_exportador_dice_que_ejecutar(tmp_path):
    with pytest.raises(FileNotFoundError, match="dvc repro curar"):
        foto.leer_curar(tmp_path / "curar.json")


def test_el_porcentaje_de_sondeos_posibles_no_pasa_del_cien_por_cien():
    dia = pd.Timestamp("2026-08-16T00:00Z")
    # Cada 60 s para una fuente de 300 s: 1.440 sondeos, 288 franjas.
    ts = [dia + pd.Timedelta(seconds=60 * i) for i in range(1440)]
    pct = foto.pct_franjas(ts, 300, ["2026-08-16", "2026-08-17"])
    assert pct["2026-08-16"] == 100.0
    assert pct["2026-08-17"] == 0.0
