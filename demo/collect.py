"""Colector: sondea las fuentes a su cadencia y persiste crudo + Parquet.

    python demo/collect.py --minutes 1440       # captura acotada de 24 h
    python demo/collect.py --minutes 0          # indefinida (para meses)
    python demo/collect.py --status             # ¿sigue vivo? sin tocar el proceso

Diseño deliberado:

1. Se guarda SIEMPRE el payload crudo en NDJSON gzip antes de parsear nada.
   Si el esquema de la fuente cambia (Renfe es un endpoint no documentado),
   podrás reprocesar. El pasado no se puede recapturar.

2. Deduplicación por snapshot. La capa de la EMT se refresca cada ~29 s pero
   tú sondeas cada 30 s: sin deduplicar te comes un ~15 % de filas repetidas.
   El `snapshot_id` (gid mínimo del bloque) identifica el refresco.

3. Escritura a Parquet particionado por fuente y día, con volcado por tamaño
   Y por tiempo: si el proceso muere, como mucho pierdes el Parquet de los
   últimos minutos, nunca el crudo.

4. Latido en `<out>/_status.json` cada minuto. Corriendo desapegado del
   terminal es la única forma de saber si sigue vivo sin adivinar.

Este script es el prototipo. En el TFM su equivalente vive en
`src/project/ingest/` y publica a Kafka en vez de escribir a disco.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
from collections import defaultdict, deque
from datetime import timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpx
import pandas as pd

from sources import SOURCES, append_raw, now_utc, parse

log = logging.getLogger("collect")
HEADERS = {"User-Agent": "TFM-UPV-BigData/0.1 (investigacion academica)"}

FLUSH_FILAS = 50_000
FLUSH_SEG = 1800          # media hora
LATIDO_SEG = 60
MAX_VISTOS = 20_000       # cota del deduplicador, para no crecer sin fin en meses

BUFFER: dict[str, list[pd.DataFrame]] = defaultdict(list)
VISTOS: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_VISTOS))
VISTOS_SET: dict[str, set] = defaultdict(set)
STATS: dict[str, dict] = defaultdict(
    lambda: {"ok": 0, "dup": 0, "err": 0, "filas": 0, "ultimo_ok": None,
             "ultimo_error": None})
ULTIMO_FLUSH: dict[str, pd.Timestamp] = {}
PARAR = asyncio.Event()
INICIO = None


def recordar(source: str, sid) -> bool:
    """True si el snapshot es nuevo. Mantiene la memoria acotada."""
    s = VISTOS_SET[source]
    if sid in s:
        return False
    d = VISTOS[source]
    if len(d) == d.maxlen:
        s.discard(d[0])
    d.append(sid)
    s.add(sid)
    return True


def flush(root: Path, source: str) -> None:
    trozos = BUFFER.pop(source, [])
    ULTIMO_FLUSH[source] = now_utc()
    if not trozos:
        return
    df = pd.concat(trozos, ignore_index=True)

    # La geometría de los tramos de tráfico es ESTÁTICA. Repetirla en cada
    # snapshot multiplicaría el tamaño por nada: se guarda una vez en
    # reference/ y se saca de la serie temporal.
    if "geom_wkt" in df.columns:
        ref = root / "reference" / f"{source}_geometria.parquet"
        if not ref.exists():
            ref.parent.mkdir(parents=True, exist_ok=True)
            cols = [c for c in ("idtramo", "denominacion", "des_tramo",
                                "fiwareid", "lat", "lon", "geom_wkt")
                    if c in df.columns]
            geo = df[cols].drop_duplicates(subset=["idtramo"])
            geo.to_parquet(ref, index=False, compression="zstd")
            log.info("geometría de %s -> %s (%d tramos)", source, ref.name, len(geo))
        df = df.drop(columns=["geom_wkt"])

    day = pd.Timestamp(df["ts_ingest_utc"].iloc[0]).strftime("%Y-%m-%d")
    out = root / "curated" / f"source={source}" / f"date={day}"
    out.mkdir(parents=True, exist_ok=True)
    fname = out / f"part-{pd.Timestamp.now(tz='UTC').strftime('%H%M%S')}.parquet"
    df.to_parquet(fname, index=False, compression="zstd")
    log.info("flush %-20s %6d filas -> %s", source, len(df), fname.name)


def tamano_mb(root: Path) -> float:
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file()) / 1e6


def escribir_latido(root: Path) -> None:
    ahora = now_utc()
    estado = {
        "vivo_utc": ahora.isoformat(),
        "vivo_local": ahora.tz_convert("Europe/Madrid").isoformat(),
        "arrancado_utc": INICIO.isoformat() if INICIO else None,
        "horas_en_marcha": round((ahora - INICIO).total_seconds() / 3600, 2) if INICIO else 0,
        "disco_mb": round(tamano_mb(root), 1),
        "fuentes": {
            k: {**v, "ultimo_ok": v["ultimo_ok"].isoformat() if v["ultimo_ok"] else None}
            for k, v in STATS.items()
        },
    }
    tmp = root / "_status.json.tmp"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(estado, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(root / "_status.json")


def mostrar_estado(root: Path) -> int:
    p = root / "_status.json"
    if not p.exists():
        print(f"No hay {p}. ¿Has lanzado el colector con --out {root}?")
        return 1
    e = json.loads(p.read_text(encoding="utf-8"))
    vivo = pd.Timestamp(e["vivo_utc"])
    edad = (pd.Timestamp.now(tz="UTC") - vivo).total_seconds()
    salud = "VIVO" if edad < 180 else f"PARADO (sin latido desde hace {edad/60:.0f} min)"
    print(f"\n  Estado      : {salud}")
    print(f"  Último latido: {e['vivo_local'][:19]}")
    print(f"  En marcha   : {e['horas_en_marcha']} h")
    print(f"  En disco    : {e['disco_mb']} MB\n")
    print(f"  {'fuente':22} {'snapshots':>10} {'filas':>12} {'dup':>7} {'err':>6}  último ok")
    for k, v in e["fuentes"].items():
        ult = (v["ultimo_ok"] or "")[11:19]
        print(f"  {k:22} {v['ok']:>10,} {v['filas']:>12,} {v['dup']:>7} {v['err']:>6}  {ult}")
    print()
    return 0 if edad < 180 else 2


async def asegurar_geometria(client: httpx.AsyncClient, key: str, root: Path) -> None:
    """Descarga UNA vez la geometría de las capas cuya traza no cambia."""
    src = SOURCES[key]
    if not src.geometria_estatica:
        return
    ref = root / "reference" / f"{key}_geometria.parquet"
    if ref.exists():
        return
    try:
        r = await client.get(src.url)          # esta sí con geometría
        r.raise_for_status()
        ts = now_utc()
        append_raw(root, key, r.json(), ts)
        df = parse(key, r.json(), ts)
        if not df.empty and "geom_wkt" in df.columns:
            BUFFER[key].append(df)
            flush(root, key)                    # flush() ya separa la geometría
            log.info("geometría inicial de %s descargada", key)
    except Exception as exc:                    # noqa: BLE001
        log.warning("no pude descargar la geometría de %s: %s", key, exc)


async def sondear(client: httpx.AsyncClient, key: str, root: Path) -> None:
    src = SOURCES[key]
    ULTIMO_FLUSH.setdefault(key, now_utc())
    fallos = 0
    while not PARAR.is_set():
        ts = now_utc()
        # Con la geometría ya en reference/, se pide sin ella: en la capa 192
        # eso recorta ~90 % del payload.
        url = src.url_sin_geometria if (
            root / "reference" / f"{key}_geometria.parquet").exists() else src.url
        try:
            r = await client.get(url)
            r.raise_for_status()
            payload = r.json()
            append_raw(root, key, payload, ts)

            df = parse(key, payload, ts)
            if not df.empty:
                if "snapshot_id" in df.columns:
                    sid = int(df["snapshot_id"].iloc[0])
                elif "ts_utc" in df.columns and df["ts_utc"].notna().any():
                    sid = str(df["ts_utc"].max())
                else:
                    sid = str(ts)
                if not recordar(key, sid):
                    STATS[key]["dup"] += 1
                else:
                    BUFFER[key].append(df)
                    STATS[key]["ok"] += 1
                    STATS[key]["filas"] += len(df)
                    STATS[key]["ultimo_ok"] = ts
            fallos = 0

            filas_buf = sum(len(d) for d in BUFFER[key])
            viejo = (ts - ULTIMO_FLUSH[key]).total_seconds() > FLUSH_SEG
            if filas_buf >= FLUSH_FILAS or (viejo and filas_buf):
                flush(root, key)

        except Exception as exc:  # noqa: BLE001
            fallos += 1
            STATS[key]["err"] += 1
            STATS[key]["ultimo_error"] = f"{type(exc).__name__}: {exc}"[:200]
            log.warning("%s: %s: %s", key, type(exc).__name__, exc)

        # Retroceso exponencial acotado: si la fuente cae, no la martilleamos.
        espera = src.period_s * min(2**fallos, 16) if fallos else src.period_s
        try:
            await asyncio.wait_for(PARAR.wait(), timeout=espera)
        except asyncio.TimeoutError:
            pass


async def latir(root: Path) -> None:
    # Latido inmediato: si esperas al primer ciclo, durante un minuto entero
    # `--status` dice que no hay nada y parece que el colector no ha arrancado.
    try:
        escribir_latido(root)
    except Exception as exc:  # noqa: BLE001
        log.warning("latido inicial: %s", exc)
    while not PARAR.is_set():
        try:
            await asyncio.wait_for(PARAR.wait(), timeout=LATIDO_SEG)
        except asyncio.TimeoutError:
            pass
        try:
            escribir_latido(root)
        except Exception as exc:  # noqa: BLE001
            log.warning("latido: %s", exc)
        log.info("ESTADO  %s", " | ".join(
            f"{k}: {v['ok']}ok/{v['dup']}dup/{v['err']}err {v['filas']:,}f"
            for k, v in STATS.items()))


async def main(minutos: int, claves: list[str], root: Path) -> None:
    global INICIO
    INICIO = now_utc()
    root.mkdir(parents=True, exist_ok=True)
    limites = httpx.Limits(max_connections=8)
    async with httpx.AsyncClient(timeout=20, headers=HEADERS,
                                 limits=limites, follow_redirects=True) as client:
        for k in claves:
            await asegurar_geometria(client, k, root)
        tareas = [asyncio.create_task(sondear(client, k, root)) for k in claves]
        tareas.append(asyncio.create_task(latir(root)))
        try:
            if minutos > 0:
                await asyncio.wait_for(PARAR.wait(), timeout=minutos * 60)
            else:
                await PARAR.wait()          # indefinido
        except asyncio.TimeoutError:
            pass
        PARAR.set()
        for t in tareas:
            t.cancel()
        await asyncio.gather(*tareas, return_exceptions=True)

    for k in list(BUFFER):
        flush(root, k)
    escribir_latido(root)

    print("\n" + "=" * 70)
    print("RESUMEN DE LA CAPTURA")
    print("=" * 70)
    for k, v in STATS.items():
        total = v["ok"] + v["dup"]
        pct = 100 * v["dup"] / total if total else 0
        print(f"  {k:22} {v['ok']:6,} snapshots  {v['filas']:10,} filas  "
              f"{v['dup']:5} dup ({pct:.0f}%)  {v['err']} err")
    print(f"\n  {tamano_mb(root):,.1f} MB en {root.resolve()}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--minutes", type=int, default=1440,
                   help="0 = indefinido")
    p.add_argument("--sources", nargs="*", default=["emt_buses", "trafico_estado",
                                                    "trafico_intensidad",
                                                    "renfe_cercanias", "valenbisi"])
    p.add_argument("--out", type=Path, default=Path("data"))
    p.add_argument("--status", action="store_true",
                   help="mostrar el latido del colector y salir")
    p.add_argument("--log", type=Path, default=None,
                   help="además de consola, escribir el log a este fichero")
    a = p.parse_args()

    if a.status:
        raise SystemExit(mostrar_estado(a.out))

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if a.log:
        a.log.parent.mkdir(parents=True, exist_ok=True)
        # Rotación: en meses de captura un log sin límite acaba siendo el
        # fichero más grande del proyecto.
        handlers.append(RotatingFileHandler(
            a.log, maxBytes=10_000_000, backupCount=5, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s UTC %(levelname)-7s %(message)s")
    logging.Formatter.converter = lambda *args: pd.Timestamp.now(
        tz=timezone.utc).timetuple()

    # httpx registra una línea INFO por petición: 5 fuentes cada 30 s son
    # ~14.000 líneas al día sin una sola información útil.
    for ruidoso in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)

    signal.signal(signal.SIGINT, lambda *_: PARAR.set())
    try:
        signal.signal(signal.SIGTERM, lambda *_: PARAR.set())
    except (AttributeError, ValueError):
        pass  # SIGTERM no existe en Windows

    asyncio.run(main(a.minutes, a.sources, a.out))
