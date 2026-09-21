"""Descarga versiones ARCHIVADAS del GTFS de la EMT desde Transitland.

    uv run python -m project.ingest.transitland c58040a67325... 058434992a85...

El editor (VLCi, NAP) sirve sólo la versión vigente del feed y la sustituye sin
avisar: una versión que no se descargó en su día sólo existe en archivos como
Transitland (`docs/09_gtfs_emt.md`, versiones archivadas). La descarga pide API
key (`settings.transitland_api_key`, en `.env`); va en cabecera, no en la URL,
para que no quede en ningún log.

Cada zip se comprueba contra su sha1 antes de guardarlo en
`settings.gtfs_dir / "versiones"`. Después hay que versionarlo con
`uv run dvc add`.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import httpx

from project.config import settings

API = "https://transit.land/api/v2/rest/feed_versions/{sha1}/download"


def descargar(sha1: str, destino: Path) -> Path:
    if not settings.transitland_api_key:
        raise SystemExit("Falta TRANSITLAND_API_KEY en .env")
    r = httpx.get(
        API.format(sha1=sha1),
        headers={"apikey": settings.transitland_api_key},
        timeout=120,
        follow_redirects=True,
    )
    r.raise_for_status()
    real = hashlib.sha1(r.content).hexdigest()
    if real != sha1:
        raise SystemExit(f"{sha1}: el zip descargado tiene sha1 {real}")
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"transitland_{sha1[:12]}.zip"
    ruta.write_bytes(r.content)
    return ruta


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("sha1", nargs="+", help="sha1 completo de cada versión")
    a = p.parse_args()
    for s in a.sha1:
        print(descargar(s, settings.gtfs_dir / "versiones"))
