"""Persistencia del corpus: lo único que no se puede arreglar después.

Ninguna fuente guarda histórico. Si el colector parsea antes de guardar el crudo,
sobrescribe en vez de añadir o deduplica mal, el daño no da la cara —el proceso
sigue vivo y el Parquet sale bien formado— y lo perdido no vuelve. Hasta la
auditoría de 09/2026 no había un solo test sobre esta capa: sus nueve mutantes
pasaban la suite en verde (`docs/11_auditoria_tests.md`). Cada test de aquí
detecta al menos uno de ellos.

Todo corre sin red y en `tmp_path`. El colector guarda estado en globales de
módulo (`BUFFER`, `VISTOS`, `PARAR`...); la fixture `colector` los aísla.
"""

from __future__ import annotations

import asyncio
import gzip
import json
from collections import defaultdict, deque
from pathlib import Path

import httpx
import pandas as pd
import pytest

from project.ingest import collect, reprocesar, sources

T0 = pd.Timestamp("2026-08-16T10:00:00Z")


@pytest.fixture
def colector(monkeypatch):
    """El módulo `collect` con su estado global vacío y aislado del resto."""
    monkeypatch.setattr(collect, "BUFFER", defaultdict(list))
    monkeypatch.setattr(
        collect, "VISTOS", defaultdict(lambda: deque(maxlen=collect.MAX_VISTOS))
    )
    monkeypatch.setattr(collect, "VISTOS_SET", defaultdict(set))
    monkeypatch.setattr(collect, "STATS", defaultdict(collect.STATS.default_factory))
    monkeypatch.setattr(collect, "ULTIMO_FLUSH", {})
    monkeypatch.setattr(collect, "PARAR", asyncio.Event())
    return collect


def _lineas(ruta: Path) -> list[dict]:
    with gzip.open(ruta, "rt", encoding="utf-8") as fh:
        return [json.loads(x) for x in fh]


# --------------------------------------------------------------------------- #
# Crudo
# --------------------------------------------------------------------------- #
def test_el_crudo_se_guarda_aunque_el_parser_falle(tmp_path, colector):
    """El orden importa: primero el crudo, después el parseo.

    Si el esquema de la fuente cambia y el parser revienta, el payload tiene que
    estar ya en disco para reprocesarlo cuando se arregle. Con el orden invertido
    se pierde exactamente el dato que habría explicado el fallo.
    """
    roto = {
        "features": [
            {"attributes": {"gid": 1, "linea": "1"}, "geometry": {"x": 0, "y": 0}}
        ]
    }

    def responder(request: httpx.Request) -> httpx.Response:
        colector.PARAR.set()  # una sola vuelta del bucle
        return httpx.Response(200, json=roto)

    async def una_vuelta() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as c:
            await colector.sondear(c, "emt_buses", tmp_path)

    asyncio.run(una_vuelta())

    crudos = list((tmp_path / "raw").rglob("*.ndjson.gz"))
    assert len(crudos) == 1, "el payload que no parsea no llegó al crudo"
    assert [x["payload"] for x in _lineas(crudos[0])] == [roto]
    assert colector.STATS["emt_buses"]["err"] >= 1, "el fallo de parseo no se contó"


def test_append_raw_anade_y_read_raw_devuelve_todo(tmp_path):
    """Tres sondeos del mismo día: tres payloads, en orden, idénticos."""
    payloads = [{"n": i, "texto": "ñ"} for i in range(3)]
    for i, p in enumerate(payloads):
        sources.append_raw(tmp_path, "valenbisi", p, T0 + pd.Timedelta(minutes=5 * i))

    (fichero,) = list((tmp_path / "raw").rglob("*.ndjson.gz"))
    leido = list(sources.read_raw(fichero))
    assert [p for _, p in leido] == payloads
    assert [t for t, _ in leido] == [T0 + pd.Timedelta(minutes=5 * i) for i in range(3)]


def test_el_crudo_se_particiona_por_instante_de_captura(tmp_path):
    """La partición es el día UTC de `ts_ingest`, no el del reloj de pared.

    Reprocesar un día tiene que encontrar sus payloads en su partición aunque se
    haya escrito otro día, y un sondeo a las 23:59:50 no puede acabar en la del
    día siguiente porque el disco tardó en escribir.
    """
    sources.append_raw(
        tmp_path, "renfe_cercanias", {"n": 0}, pd.Timestamp("2026-08-16T23:59:50Z")
    )
    sources.append_raw(
        tmp_path, "renfe_cercanias", {"n": 1}, pd.Timestamp("2026-08-17T00:00:10Z")
    )

    dias = sorted(p.parent.name for p in (tmp_path / "raw").rglob("*.ndjson.gz"))
    assert dias == ["date=2026-08-16", "date=2026-08-17"]


def test_read_raw_salta_el_relleno_de_ceros_entre_miembros(tmp_path):
    """Un corte de corriente deja un bloque a ceros entre dos miembros gzip.

    Es lo que hay en siete ficheros reales de agosto. `zcat` se para ahí y cuenta
    menos de lo que hay; `read_raw` debe seguir leyendo, porque de eso depende que
    `reprocesar` no mutile esos días (`docs/bitacora/011-el-crudo-esta-integro-y-ningun-test-lo-guarda.md`).
    Sin mutante en el catálogo: fija un comportamiento de la biblioteca estándar
    del que el corpus depende, para que un cambio de lector no lo rompa en silencio.
    """
    for i in range(2):
        sources.append_raw(tmp_path, "emt_buses", {"n": i}, T0)
    (fichero,) = list((tmp_path / "raw").rglob("*.ndjson.gz"))
    with open(fichero, "ab") as fh:
        fh.write(b"\x00" * 2028)
    sources.append_raw(tmp_path, "emt_buses", {"n": 2}, T0)

    assert [p["n"] for _, p in sources.read_raw(fichero)] == [0, 1, 2]


# --------------------------------------------------------------------------- #
# Deduplicación
# --------------------------------------------------------------------------- #
def test_recordar_descarta_el_snapshot_repetido(colector):
    assert colector.recordar("emt_buses", 1659987635) is True
    assert colector.recordar("emt_buses", 1659987635) is False
    assert colector.recordar("renfe_cercanias", 1659987635) is True, "fuentes mezcladas"


def test_recordar_olvida_lo_que_desaloja(colector, monkeypatch):
    """La memoria está acotada: lo que sale de la cola deja de estar en el set.

    Si el set no olvidase, crecería sin límite durante meses, y un `snapshot_id`
    reutilizado tras el desalojo se descartaría como duplicado sin serlo.
    """
    monkeypatch.setattr(colector, "MAX_VISTOS", 3)
    for sid in (1, 2, 3, 4):  # el 1 sale de la cola al entrar el 4
        assert colector.recordar("x", sid) is True
    assert colector.recordar("x", 4) is False
    assert colector.recordar("x", 1) is True, "el set no olvidó lo desalojado"
    assert len(colector.VISTOS_SET["x"]) == 3


# --------------------------------------------------------------------------- #
# Volcado y reprocesado
# --------------------------------------------------------------------------- #
def test_flush_guarda_la_geometria_una_vez_por_tramo(tmp_path, colector, fix):
    """La geometría es estática: va a `reference/` una vez y sale de la serie."""
    df = sources.parse("trafico_estado", fix["trafico_estado"], T0)
    colector.BUFFER["trafico_estado"] = [df, df.copy()]  # dos sondeos, mismos tramos
    colector.flush(tmp_path, "trafico_estado")

    ref = pd.read_parquet(tmp_path / "reference" / "trafico_estado_geometria.parquet")
    assert ref["idtramo"].is_unique, "tramos repetidos en la referencia"
    assert len(ref) == df["idtramo"].nunique()

    (parte,) = list((tmp_path / "curated").rglob("*.parquet"))
    curado = pd.read_parquet(parte)
    assert "geom_wkt" not in curado.columns
    assert len(curado) == 2 * len(df)


@pytest.fixture
def crudo_de_dos_dias(tmp_path, fix) -> Path:
    """Dos días de crudo de tráfico con un payload que no parsea en medio."""
    bueno = fix["trafico_estado"]
    roto = {"features": [{"attributes": {"x": 1}}]}
    sources.append_raw(
        tmp_path, "trafico_estado", bueno, pd.Timestamp("2026-08-16T10:00:00Z")
    )
    sources.append_raw(
        tmp_path, "trafico_estado", roto, pd.Timestamp("2026-08-16T10:05:00Z")
    )
    sources.append_raw(
        tmp_path, "trafico_estado", bueno, pd.Timestamp("2026-08-17T10:00:00Z")
    )
    return tmp_path


def test_reprocesar_reconstruye_todos_los_dias(crudo_de_dos_dias, fix):
    r = reprocesar.reprocesar(crudo_de_dos_dias, "trafico_estado", dry=False)
    n = len(sources.parse("trafico_estado", fix["trafico_estado"], T0))

    assert r["dias"] == 2 and r["payloads"] == 3 and r["filas"] == 2 * n, r
    dias = sorted(
        p.name
        for p in (crudo_de_dos_dias / "curated" / "source=trafico_estado").iterdir()
    )
    assert dias == ["date=2026-08-16", "date=2026-08-17"]


def test_reprocesar_cuenta_los_payloads_que_no_parsean(crudo_de_dos_dias):
    """Un payload que no parsea se salta, pero se cuenta: si no, no se ve."""
    r = reprocesar.reprocesar(crudo_de_dos_dias, "trafico_estado", dry=True)
    assert r["errores"] == 1, r
