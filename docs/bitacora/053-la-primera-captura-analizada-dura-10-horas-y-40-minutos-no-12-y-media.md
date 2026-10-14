---
id: 053
titulo: El análisis de la primera captura (documento 05, trampa 002) abarca 10 h 40 min y no 12,5 h, porque se cortó a las 08:55 locales mientras la captura siguió hasta las 10:57; recalculado sobre el crudo, la EMT alterna 342 veces en 1.236 sondeos (se publicó 338 en 1.224, con una tabla que suma 1.246), y la conclusión no cambia, con un 20,2 % de las filas que un desfase fijo desplazaría dos horas
fecha: 2026-10-14
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: bajo
estado: abierto
evidencia: fragmento de «Cómo se midió» sobre data/raw/source=emt_buses, 15-16/08
trampa: 002
---

## Qué se observó

El exportador del dashboard recalcula la alternancia horaria de la EMT (parada
P3) en la ventana del documento 05: «15/08/2026 22:15 → 16/08/2026 08:55 hora
local (12,5 h)». Las cifras se desvían un 1 % de las publicadas, y la duración no
cuadra con la ventana:

| | documento 05 y trampa 002 | crudo, 14/10 |
|---|---|---|
| ventana | 22:15 → 08:55 local, «12,5 h» | 20:15 → 06:55 UTC: **10 h 40 min** |
| sondeos distintos | 1.224 (la tabla suma 979 + 267 = 1.246) | **1.236** (1.264 capturas) |
| en hora local / en UTC | 979 / 267 | 971 / 265 |
| filas en hora local / en UTC | 51.854 / 13.199 | 49.770 / 12.598 |
| alternancias | 338 | **342** |
| racha mediana | 2 | 2 |
| filas que un desfase fijo desplazaría 2 h | 20,3 % | **20,2 %** |

- **La ventana analizada duró 10 h 40 min.** El propio documento 05 dice «1.284
  sondeos de EMT», que a 30 s son 10,7 h, no 12,5.
- **Las 12,5 h son lo que duró la captura, no el análisis.** El crudo no tiene
  ningún hueco a las 08:55 locales: la captura siguió sin cortes hasta las 08:57
  UTC (10:57 locales), donde aparece el primer hueco, de 16 min. De 22:14 a
  10:57 locales van 12 h 43 min.
- **El recuento se mueve un 1 %** (342 frente a 338, 1.236 frente a 1.224). La
  medición original no está guardada con su comando, y su tabla no suma el total
  que declara: no se puede atribuir la diferencia. El recálculo cuenta cada
  sondeo una vez, por su `snapshot_id` y en su primera captura, y deja fuera los
  DUDOSA (ninguno en la ventana).
- **La conclusión es la misma:** cambia de convención casi en cada sondeo (racha
  mediana 2) y un desfase fijo desplaza una de cada cinco filas.

## Cómo se midió

```python
import pandas as pd
from project.config import settings
from project.ingest.sources import parse_emt, read_raw
a, b = pd.Timestamp("2026-08-15T20:15Z"), pd.Timestamp("2026-08-16T06:55Z")
vistos, s = set(), []
for d in ("2026-08-15", "2026-08-16"):
    f = settings.raw_dir / "source=emt_buses" / f"date={d}" / "payloads.ndjson.gz"
    for ts, p in read_raw(f):
        if a <= ts <= b:
            df = parse_emt(p, ts)
            if df.empty or int(df.snapshot_id.iloc[0]) in vistos:
                continue
            vistos.add(int(df.snapshot_id.iloc[0]))
            s.append((df.tz_convencion.iloc[0], len(df)))
f = pd.DataFrame(s, columns=["conv", "filas"])
c = f[f.conv != "DUDOSA"].conv.reset_index(drop=True)
cambio = c != c.shift()
print(len(f), f.groupby("conv").filas.agg(["size", "sum"]), int(cambio.sum() - 1),
      c.groupby(cambio.cumsum()).size().median())
```

El hueco que cierra la captura: `medir_completitud.huecos` sobre
`medir_completitud.instantes(settings.raw_dir, "emt_buses", "2026-08-15",
"2026-08-16")` con umbral de 5 min. El primero es el 16/08 de 08:57:55 a
09:14:08 UTC.

## Por qué importa

- Las cifras de la trampa 002 están en el índice de trampas, que se carga en
  cada sesión, y en el documento 05, del que sale el capítulo de calidad del
  dato. La memoria habría citado 12,5 h para una ventana de 10 h 40 min.
- El error es el mismo que describe la trampa: una duración calculada con dos
  horas que no estaban en la misma convención.
- La extrapolación de disco del documento 05 («76,7 MB en 12,5 h → ~147 MB/día»,
  repetida en el ADR-003) usa la misma duración. **No se ha verificado**: el
  crudo de entonces traía la geometría del tráfico, que ya no se guarda, y el
  volumen real se midió después (bitácora 033).

## Qué se hizo / qué queda abierto

- La trampa 002 y el documento 05 citan ahora las cifras recalculadas y remiten
  aquí.
- La parada P3 del dashboard coteja contra 342 y 1.236 sin tolerancia.
- **Abierto:** el docstring de `resolver_convencion` y la cabecera de
  `src/project/ingest/sources.py` repiten «12,5 h» y «338 en 1.224». El fichero es
  dependencia de `curar`: se corrigen con su próximo cambio de código.
- **Abierto:** la extrapolación de 147 MB/día del ADR-003, sin verificar.

## Para la memoria

> En las primeras 10 horas y 40 minutos de captura, la capa de posiciones de la
> EMT cambió de convención horaria 342 veces en 1.236 sondeos: 971 sellaban la
> hora local de Madrid como si fuera UTC y 265 la hora UTC real, con rachas de
> mediana dos sondeos. Corregir la serie con un desfase fijo habría desplazado dos
> horas el 20,2 % de las posiciones sin producir ningún error. Por eso la
> convención se decide sondeo a sondeo, a partir de la latencia que produce cada
> interpretación respecto al instante de captura.
