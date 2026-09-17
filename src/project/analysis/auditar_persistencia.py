"""¿Cuenta `raw/` lo mismo que `curated/`? Auditoría de persistencia, solo lectura.

    uv run python -m project.analysis.auditar_persistencia
    uv run python -m project.analysis.auditar_persistencia --sources emt_buses --csv out.csv

`reprocesar` reconstruye `curated/` desde `raw/` con `read_raw`, que usa
`gzip.open`. `append_raw` escribe UN MIEMBRO GZIP POR SONDEO en modo append: si
un corte deja un miembro a medias, lo que `gzip.open` hace con los miembros
posteriores decide si reprocesar recupera el día o lo mutila en silencio
(`data/raw/_TRUNCADOS.txt`). Aquí se mide, por fuente y día:

  miembros_ok      miembros gzip íntegros (CRC válido), recorriendo el fichero
                   miembro a miembro y resincronizando tras uno roto. Es lo que
                   HAY en disco, independientemente de quién sepa leerlo.
  miembros_rotos   tramos que empiezan con cabecera gzip y no descomprimen.
  huecos_cero      bloques de bytes a cero entre miembros, y `bytes_basura`
                   los que no son cero. Un corte de corriente deja el bloque
                   asignado sin escribir: `zcat` lo toma por basura final y
                   para, pero `gzip.open` de Python salta el relleno de ceros
                   entre miembros y sigue. Por eso `_TRUNCADOS.txt`, medido con
                   `zcat`, sobrestimaba lo que pierde `read_raw`.
  legibles         payloads que devuelve `gzip.open` antes de parar, y cómo
                   para (`fin`: EOF limpio o el nombre de la excepción).
  curated          `ts_ingest_utc` distintos en `curated/` para ese día de
                   captura. Menor que `miembros_ok` es normal: el colector
                   deduplica snapshots y descarta payloads vacíos.
  perdida_reproc   sondeos que están en `curated/` y NO devolvería `gzip.open`:
                   lo que `reprocesar` borraría.
  recuperables     de esos, cuántos siguen íntegros en disco tras el corte.
  huerfanos_cur    sondeos en `curated/` que no están en `raw/` ni recuperando
                   miembro a miembro. Debería ser 0: el crudo se guarda antes.
  cruce_particion  filas de `curated/` cuyo día de captura no coincide con su
                   partición `date=`. `flush` fecha el volcado entero por su
                   primera fila.

Para no parsear cientos de megas de JSON, el instante se extrae del prefijo de
la línea, que `append_raw` escribe siempre como `{"ts_ingest_utc":"..."`. El
control `--control` comprueba que esa lectura rápida coincide con `read_raw`
sobre un fichero concreto: si no coincidiese, las cifras de arriba no valdrían.

Nada del pipeline importa de aquí: esto es exploración, no un stage de DVC.
"""

from __future__ import annotations

import argparse
import gzip
import zlib
from pathlib import Path

import duckdb
import pandas as pd

from project.config import settings
from project.ingest.sources import SOURCES, read_raw

CABECERA = b"\x1f\x8b\x08"
PREFIJO = '{"ts_ingest_utc":"'
BLOQUE = 1 << 16


def _instante(linea: str) -> int | None:
    """Microsegundos UTC desde el prefijo de una línea de `append_raw`."""
    if not linea.startswith(PREFIJO):
        return None
    fin = linea.find('"', len(PREFIJO))
    return pd.Timestamp(linea[len(PREFIJO) : fin]).value // 1000


def _un_miembro(datos: memoryview, pos: int) -> tuple[bytes, int] | None:
    """Descomprime el miembro que empieza en `pos`. None si está roto."""
    d = zlib.decompressobj(wbits=31)
    trozos, leido = [], 0
    try:
        while not d.eof and pos + leido < len(datos):
            trozo = datos[pos + leido : pos + leido + BLOQUE]
            trozos.append(d.decompress(trozo))
            leido += len(trozo)
    except zlib.error:
        return None
    if not d.eof:
        return None
    return b"".join(trozos), leido - len(d.unused_data)


def miembros(ruta: Path) -> tuple[list[int], int, int, int]:
    """Instantes de los miembros íntegros, miembros rotos, huecos de ceros y
    bytes de basura no nula entre miembros."""
    datos = memoryview(ruta.read_bytes())
    bruto = datos.obj
    instantes: list[int] = []
    rotos, huecos_cero, basura, pos = 0, 0, 0, 0
    while pos < len(datos):
        if bytes(datos[pos : pos + 3]) != CABECERA:
            siguiente = bruto.find(CABECERA, pos + 1)
            fin = len(bruto) if siguiente < 0 else siguiente
            ceros = bruto.count(0, pos, fin)
            huecos_cero += ceros == fin - pos
            basura += (fin - pos) - ceros
            if siguiente < 0:
                break
            pos = siguiente
            continue
        r = _un_miembro(datos, pos)
        if r is None:
            # `pos` siempre cae justo tras un miembro válido o tras un hueco, así
            # que esta cabecera es real y el miembro está roto. Para resincronizar
            # se descartan las falsas cabeceras que aparezcan dentro de sus bytes
            # comprimidos: solo vale la siguiente que descomprima con CRC válido.
            rotos += 1
            siguiente = bruto.find(CABECERA, pos + 1)
            while siguiente >= 0 and _un_miembro(datos, siguiente) is None:
                siguiente = bruto.find(CABECERA, siguiente + 1)
            if siguiente < 0:
                break
            pos = siguiente
            continue
        contenido, consumido = r
        for linea in contenido.decode("utf-8", errors="replace").splitlines():
            t = _instante(linea)
            if t is not None:
                instantes.append(t)
        pos += consumido
    return instantes, rotos, huecos_cero, basura


def legibles(ruta: Path) -> tuple[list[int], str]:
    """Lo que ve `gzip.open`, que es lo que ve `read_raw`, y cómo termina."""
    instantes: list[int] = []
    try:
        with gzip.open(ruta, "rt", encoding="utf-8") as fh:
            for linea in fh:
                t = _instante(linea)
                if t is not None:
                    instantes.append(t)
    except Exception as exc:  # noqa: BLE001
        return instantes, type(exc).__name__
    return instantes, "EOF"


def curados(source: str) -> pd.DataFrame:
    """Instante de captura y partición de cada sondeo curado."""
    patron = (settings.curated_dir / f"source={source}" / "*" / "*.parquet").as_posix()
    return duckdb.sql(
        f"""
        select distinct
            epoch_us(ts_ingest_utc)                          as t,
            cast(ts_ingest_utc at time zone 'UTC' as date)   as dia,
            regexp_extract(filename, 'date=([0-9-]+)', 1)    as particion
        from read_parquet('{patron}', filename = true, hive_partitioning = false,
                          union_by_name = true)
        """
    ).df()


def auditar(source: str) -> list[dict]:
    cur = curados(source)
    cur["dia"] = cur["dia"].astype(str)
    filas = []
    for fichero in sorted((settings.raw_dir / f"source={source}").rglob("*.gz")):
        dia = fichero.parent.name.removeprefix("date=")
        ok, rotos, huecos_cero, basura = miembros(fichero)
        leg, fin = legibles(fichero)
        c = cur[cur["dia"] == dia]
        set_ok, set_leg, set_cur = set(ok), set(leg), set(c["t"])
        perdida = set_cur - set_leg
        filas.append(
            {
                "fuente": source,
                "dia": dia,
                "miembros_ok": len(ok),
                "miembros_rotos": rotos,
                "huecos_cero": huecos_cero,
                "bytes_basura": basura,
                "legibles": len(leg),
                "fin": fin,
                "curated": len(set_cur),
                "perdida_reproc": len(perdida),
                "recuperables": len(perdida & set_ok),
                "huerfanos_cur": len(set_cur - set_ok),
                "cruce_particion": int((c["particion"] != dia).sum()),
            }
        )
    return filas


def control(ruta: Path) -> None:
    """La lectura rápida por prefijo tiene que coincidir con `read_raw`."""
    rapido, fin = legibles(ruta)
    real: list[int] = []
    fin_real = "EOF"
    try:
        for ts, _ in read_raw(ruta):
            real.append(ts.value // 1000)
    except Exception as exc:  # noqa: BLE001
        fin_real = type(exc).__name__
    print(f"  control {ruta}")
    print(f"    rápido:   {len(rapido):6d} payloads, fin={fin}")
    print(f"    read_raw: {len(real):6d} payloads, fin={fin_real}")
    print(f"    coinciden: {rapido == real}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sources", nargs="*", default=list(SOURCES))
    p.add_argument("--csv", type=Path, default=None)
    p.add_argument("--control", type=Path, default=None)
    a = p.parse_args()

    if a.control:
        control(a.control)
        raise SystemExit

    todas = []
    for s in a.sources:
        todas += auditar(s)
        print(f"  {s} auditada", flush=True)
    df = pd.DataFrame(todas)
    with pd.option_context("display.width", 200, "display.max_rows", 200):
        print(df.to_string(index=False))
        print("\n  Totales por fuente:")
        print(
            df.groupby("fuente")[
                [
                    "miembros_ok",
                    "miembros_rotos",
                    "huecos_cero",
                    "bytes_basura",
                    "legibles",
                    "curated",
                    "perdida_reproc",
                    "recuperables",
                    "huerfanos_cur",
                    "cruce_particion",
                ]
            ]
            .sum()
            .to_string()
        )
    if a.csv:
        df.to_csv(a.csv, index=False)
