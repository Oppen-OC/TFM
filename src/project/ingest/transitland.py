"""Consulta las versiones ARCHIVADAS del GTFS de la EMT en Transitland.

    uv run python -m project.ingest.transitland --desde 2026-08-31 --hasta 2026-09-07
    uv run python -m project.ingest.transitland --descargar c58040a67325...

El editor (VLCi, NAP) sirve sólo la versión vigente del feed y la sustituye sin
avisar: una versión que no se descargó en su día sólo existe en archivos como
Transitland (`docs/09_gtfs_emt.md`, versiones archivadas). Transitland registra
una versión nueva cada vez que el zip cambia, así que su historial es también el
registro de lo que el editor publicó y cuándo.

Los metadatos (sha1, fecha de captura, rango de calendario) se leen con la API
key gratuita. **Descargar el zip no**: exige plan professional o enterprise y que
la licencia del feed permita redistribuirlo; con la key gratuita devuelve 401
(21/09/2026). La key (`settings.transitland_api_key`, en `.env`) va en cabecera,
no en la URL, para que no quede en ningún log.

El listado marca qué versiones ya están en `settings.gtfs_dir` comparando sha1.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import date
from pathlib import Path

import httpx

from project.config import settings

API = "https://transit.land/api/v2/rest"
FEED = "f-ezp8-emtvalencia"


def _cabecera() -> dict[str, str]:
    if not settings.transitland_api_key:
        raise SystemExit("Falta TRANSITLAND_API_KEY en .env")
    return {"apikey": settings.transitland_api_key}


def versiones(limite: int = 100) -> list[dict]:
    """Las `limite` versiones más recientes del feed, tal como las da la API."""
    r = httpx.get(
        f"{API}/feeds/{FEED}/feed_versions",
        params={"limit": limite},
        headers=_cabecera(),
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["feed_versions"]


def sha1_locales(raiz: Path) -> dict[str, Path]:
    """sha1 de cada zip bajo `raiz`, para reconocer versiones ya descargadas."""
    return {hashlib.sha1(p.read_bytes()).hexdigest(): p for p in raiz.rglob("*.zip")}


def resumir(
    fvs: list[dict], locales: dict[str, Path], desde: date, hasta: date
) -> list[dict]:
    """Una fila por versión, ordenada por captura, con su relación con [desde, hasta].

    `cobertura` es `total` si el calendario abarca el intervalo entero, `parcial` si
    lo toca y vacía si no. Es cobertura **por calendario**: no dice qué servicio
    describe el feed esos días (bitácora 024).
    """
    filas = {}
    for fv in fvs:  # la API repite versiones entre páginas
        ini = date.fromisoformat(fv["earliest_calendar_date"])
        fin = date.fromisoformat(fv["latest_calendar_date"])
        if ini <= desde and fin >= hasta:
            cobertura = "total"
        elif ini <= hasta and fin >= desde:
            cobertura = "parcial"
        else:
            cobertura = ""
        local = locales.get(fv["sha1"])
        filas[fv["sha1"]] = {
            "sha1": fv["sha1"],
            "capturada": fv["fetched_at"][:10],
            "calendario": (ini, fin),
            "cobertura": cobertura,
            "local": local.name if local else "",
        }
    return sorted(filas.values(), key=lambda f: f["capturada"])


def descargar(sha1: str, destino: Path) -> Path:
    """Sólo con plan de pago; con la key gratuita, 401 (ver docstring del módulo)."""
    r = httpx.get(
        f"{API}/feed_versions/{sha1}/download",
        headers=_cabecera(),
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
    p.add_argument("--desde", type=date.fromisoformat, default=date(2026, 8, 31))
    p.add_argument("--hasta", type=date.fromisoformat, default=date(2026, 9, 7))
    p.add_argument("--descargar", nargs="+", metavar="SHA1", help="plan de pago")
    a = p.parse_args()
    if a.descargar:
        for s in a.descargar:
            print(descargar(s, settings.gtfs_dir / "versiones"))
    else:
        for f in resumir(
            versiones(), sha1_locales(settings.gtfs_dir), a.desde, a.hasta
        ):
            ini, fin = f["calendario"]
            print(
                f"{f['sha1'][:12]}  {f['capturada']}  {ini} - {fin}  "
                f"{f['cobertura']:8}{f['local']}"
            )
