---
id: 060
titulo: Los huecos de la capa 192 del 22 y el 23/09 (6,4 h y 13,7 h) que la bitácora 048 dejó sin causa son errores del geoportal y no del colector; 235 respuestas «Failed to execute query.» solo en esa capa, con la EMT y Renfe llegando, y contar líneas del crudo daba esos días por completos (288 y 284 de 288)
fecha: 2026-10-23
tipo: anomalia
capa: fuentes
capitulo: calidad-dato
impacto: bajo
estado: aceptado
evidencia: uv run python -m project.analysis.medir_completitud --desde 2026-09-22 --hasta 2026-09-23 --fuentes trafico_estado --umbral-min 15 (tras bd4f036); grep de los payloads de error sobre el crudo; el código de «Cómo se midió»
trampa: 018
---

## Qué se observó

La 048 encontró dos huecos de la capa 192 con la EMT llegando y dejó abierto
«si es la fuente o el colector». El crudo lo responde: la fuente.

| hueco (UTC) | horas | errores de la 192 dentro | sondeos de la EMT dentro | hueco más largo de Renfe dentro |
|---|---|---|---|---|
| 22/09 11:02:13 → 17:27:29 | 6,42 | 76 | 754 | 31 s |
| 23/09 08:23:29 → 22:04:47 | 13,69 | 159 | 1.618 | 31 s |

- **236 payloads de error de la 192** en los dos días, todos
  `{"error": {"code": 400, "message": "Failed to execute query."}}`. 235 caen
  dentro de los huecos y el que queda (22/09, 18:02 UTC) va suelto.
- **El colector estaba vivo:** Renfe no deja de llegar ni 31 s seguidos dentro
  de ninguno de los dos huecos, y la EMT sigue entrando.
- **Contando líneas del crudo, los dos días estaban completos**: 288 y 284
  payloads de 288. Con la regla de la trampa 018 son **211 y 125** sondeos
  (73,3 % y 43,4 %). Antes de bd4f036 la serie de la 192 del dashboard los
  pintaba al 100 %; la foto definitiva (ea3f8be) ya enseña el bajón.
- **La EMT también recibió el error, pero poco:** 20 payloads con el mismo
  mensaje el 22/09 de 17:23 a 18:04 UTC, al final del hueco de la 192. No
  llegan a abrir un hueco de más de 15 min.
- **Cuadra con la 048:** mismos huecos (6,4 h y 13,7 h). La 048 contó 735 y
  1.580 sondeos de la EMT dentro de ellos sobre el curated, que deduplica las
  capturas repetidas; aquí son 754 y 1.618 sobre el crudo con filas.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_completitud --desde 2026-09-22 --hasta 2026-09-23 \
    --fuentes trafico_estado --umbral-min 15
for d in 22 23; do f=data/raw/source=trafico_estado/date=2026-09-$d/payloads.ndjson.gz
  echo "$d $(zcat $f | wc -l) $(zcat $f | grep -c '"payload":{"error"')"; done
```

Errores, EMT y Renfe dentro de cada hueco:

```python
import pandas as pd
from project.config import settings
from project.analysis.medir_completitud import instantes, huecos
from project.ingest.sources import read_raw
raw, dias = settings.raw_dir, ("2026-09-22", "2026-09-23")
hs = huecos(instantes(raw, "trafico_estado", *dias), pd.Timedelta(minutes=15))
leer = lambda f: [(t, p) for d in dias for t, p in read_raw(raw / f"source={f}" / f"date={d}" / "payloads.ndjson.gz")]
errores = [t for t, p in leer("trafico_estado") if "error" in p]
emt = instantes(raw, "emt_buses", *dias)
renfe = [t for t, _ in leer("renfe_cercanias")]
for a, b in hs:
    r = [a] + [t for t in renfe if a < t < b] + [b]
    print(a, b, sum(a < t < b for t in errores), sum(a < t < b for t in emt), max(y - x for x, y in zip(r, r[1:])))
```

`instantes` es el contador corregido de la trampa 018: un sondeo es un payload
que `parse` convierte en filas.

## Por qué importa

- **Cierra el abierto de la 048.** El fallo no es recuperable, pero ya se sabe
  de quién es. Es la fuente, no la captura: no hay nada que arreglar en el
  colector ni en la Pi.
- **Las capas del mismo geoportal fallan por separado.** El 10-14/09 (021)
  cayeron todas a la vez. Aquí la 192 pasa 20 h devolviendo error mientras la
  EMT, servida por el mismo geoportal, sigue respondiendo. El 13/10 (trampa 018)
  fallaron las dos, con otro error (499, `Token Required`). Que haya posiciones
  no garantiza que haya tráfico.
- **No cambia ningún resultado.** El curated nunca tuvo esos sondeos. Con el
  último sondeo bueno más viejo que `trafico_edad_max_s` (900 s,
  `params.yaml`), `trafico.en_ruta` deja nula la congestión y
  `trafico_edad_s` dice cuánto hace del último. Esas horas ya entraban como
  «sin observar», no como tráfico fluido: son el 37,7 % y el 73,0 % de las
  filas de esos dos días que la 048 contó sin un sondeo de menos de 15 min.
  Solo cambia la explicación.
- **Sin la regla de la trampa 018, el crudo lo escondía.** Contar líneas daba
  el 22/09 y el 23/09 por completos. El hueco solo se veía desde el curated, y
  ahí no se veía la causa.

## Qué se hizo / qué queda abierto

Hecho:
- Huecos, errores y vida del colector medidos sobre el crudo con el
  instrumento corregido. Cuadra con los huecos de la 048.

Abierto: nada que medir. Es una limitación aceptada de la fuente: la capa 192
puede faltar horas con la EMT llegando.

## Para la memoria

> La capa de estado del tráfico falló de forma independiente a la de
> posiciones de la flota. El 22 y el 23 de septiembre, el portal municipal
> respondió con un mensaje de error a 235 consultas de esa capa, repartidas en
> dos intervalos de 6,4 y 13,7 horas. Durante ese tiempo las posiciones de la
> flota siguieron llegando y el sistema de captura funcionó sin interrupción,
> según muestra la otra fuente capturada por el mismo programa. Como el
> programa de captura guarda cada respuesta, incluidas las de error, el fallo
> pudo atribuirse a la fuente y no a la captura. Contar las respuestas
> guardadas, sin distinguir las que traen datos, daba esos dos días por
> completos; contando solo las consultas con datos, la capa conservó el 73,3 %
> y el 43,4 % de las previstas. A partir de 15 minutos sin observación, las
> variables de congestión de esas horas quedan vacías y se acompañan de la
> antigüedad de la última observación, de modo que el modelo no las confunde
> con tráfico fluido y el fallo no altera los resultados. Muestra, sin embargo,
> que disponer de posiciones no garantiza disponer del estado del tráfico.
