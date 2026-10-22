"""El instrumento del criterio de día útil (ADR-024): un payload de error no es
un sondeo. El 13/10 llegaron 447 `{"error": …}` seguidos y se contaron como
sondeos: 3 h 45 min sin posiciones pasaron por un día completo."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from project.analysis.medir_completitud import huecos, instantes
from project.ingest import sources

FIX = json.loads((Path(__file__).parent / "fixtures.json").read_text(encoding="utf-8"))
T0 = pd.Timestamp("2026-10-13T11:00:00Z")


def test_un_payload_de_error_no_cuenta_como_sondeo(tmp_path):
    error = {"error": {"code": 500, "message": "Error performing query operation"}}
    sources.append_raw(tmp_path, "emt_buses", FIX["emt_buses"], T0)
    for i in range(1, 240):
        sources.append_raw(
            tmp_path, "emt_buses", error, T0 + pd.Timedelta(seconds=30 * i)
        )
    sources.append_raw(
        tmp_path, "emt_buses", FIX["emt_buses"], T0 + pd.Timedelta(hours=2)
    )

    ts = instantes(tmp_path / "raw", "emt_buses", "2026-10-13", None)
    assert ts == [T0, T0 + pd.Timedelta(hours=2)]
    assert huecos(ts, pd.Timedelta(hours=1)) == [(T0, T0 + pd.Timedelta(hours=2))]
