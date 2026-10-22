---
id: 059
titulo: Con el instrumento corregido de la trampa 018, la EMT guarda del 07 al 12/10 17.109 sondeos y no 17.119 (99,0 %), y su hueco más largo es de 2 min 31 s y no de 2 min, porque diez payloads sin filas (4 errores del geoportal y 6 tablas vacías) contaban como sondeos; no cae ningún día, y esos diez explican los 8 de más que la 050 no cuadraba con el colector
fecha: 2026-10-22
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: bajo
estado: resuelto
evidencia: uv run python -m project.analysis.medir_completitud --desde 2026-10-07 --hasta 2026-10-12 --fuentes emt_buses trafico_estado --umbral-min 1.5 (tras bd4f036); contraste con el crudo sin filtrar por grep sobre los payloads.ndjson.gz del 07-12/10
trampa: 018
---

## Qué se observó

La 050 contó líneas del crudo. Desde bd4f036, un sondeo es un payload que
`parse` convierte en filas (trampa 018). Recontada con esa regla, la captura
del 07 al 12/10, la que publicó la 050, queda así:

| día (UTC) | EMT | 050 | capa 192 | 050 |
|---|---|---|---|---|
| 07/10 | 2.854 | 2.855 | 286 | 286 |
| 08/10 | 2.849 | 2.851 | 287 | 287 |
| 09/10 | 2.853 | 2.855 | 288 | 288 |
| 10/10 | 2.849 | 2.854 | 287 | 288 |
| 11/10 | 2.854 | 2.854 | 287 | 287 |
| 12/10 | 2.850 | 2.850 | 288 | 288 |

- **EMT:** 17.109 de 17.280 sondeos posibles (99,0 %), frente a los 17.119
  (99,1 %) que publicó la 050. Sobraban diez payloads sin filas:
  - 4 `{"error": …}` del geoportal, seguidos, el 10/10 a las 22:03 UTC;
  - 6 con `features: []`, la tabla leída vacía (07/10, uno; 08/10, dos;
    09/10, dos; 10/10, uno).
- **El hueco más largo de la EMT es de 151 s** (2 min 31 s), el 10/10 de
  22:03:16 a 22:05:47 UTC: son los cuatro errores. Los dos de 2 min de la 050
  siguen ahí, con 110 s cada uno: el 08/10 a las 08:10 y el 12/10 a las 13:38
  UTC.
- **Capa 192:** 1.723 de 1.728 (99,7 %), no 1.724 (99,8 %). Se mantiene el
  hueco de 15 min del 07/10 a las 16:33 UTC. Aparece otro de **10 min**, el
  10/10 de 21:58 a 22:08 UTC, por un `{"error"}` del mismo parpadeo del
  geoportal que dejó sin datos a la EMT.
- **El cuadre con el colector mejora.** Hasta las 07:29:59 UTC del 13/10, el
  crudo tiene 19.207 líneas de la EMT, y 19.197 son sondeos con filas. Los
  contadores `ok + dup + err` del journal sumaban 19.199. La diferencia pasa de
  +8 a −2 (0,01 %). En la 192, 1.935 sondeos con filas frente a 1.935.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_completitud --desde 2026-10-07 --hasta 2026-10-12 \
    --fuentes emt_buses trafico_estado --umbral-min 1.5
uv run python -m project.analysis.medir_completitud --desde 2026-10-07 --hasta 2026-10-12 \
    --fuentes trafico_estado --umbral-min 6       # los dos huecos de la 192
```

Las duraciones en segundos salen de `instantes` sobre la misma ventana. El
contraste con un instrumento independiente se hizo con grep sobre el crudo,
sin parsear:

```bash
f=data/raw/source=emt_buses/date=2026-10-10/payloads.ndjson.gz
zcat $f | wc -l; zcat $f | grep -c '"payload":{"error"'; zcat $f | grep -c '"features":\[\]'
```

En los seis días: 17.119 líneas, 4 errores y 6 tablas vacías. 17.119 − 10 =
17.109, lo mismo que da `medir_completitud`.

El cuadre con el colector compara `instantes` hasta las 07:29:59 UTC del 13/10
con la línea `ESTADO` del journal que citó la 050. `collect.py`
(líneas 230-254) guarda el payload antes de parsear y, si `parse` no da filas,
no suma ni a `ok` ni a `dup` ni a `err`.

## Por qué importa

- **La conclusión de la 050 no cambia.** El criterio de día útil del ADR-024
  descarta un día si la EMT tiene un hueco de más de una hora. El más largo del
  07-12/10 es de 151 s, así que ningún día de los seis cae.
- **Lo que sí cambia son las cifras.** La 050 es inmutable y su párrafo para la
  memoria dice 17.119, 99,1 %, 2 min y 99,8 %. El que vale es el de abajo. Lo
  que sí descartó un día es el 13/10, con 3 h 45 min de errores seguidos, que
  queda fuera de esta ventana (trampa 018, bitácora 057).
- **Una tabla leída vacía tampoco es un sondeo.** Es el mismo mecanismo de la
  trampa 001: la EMT trunca y reinserta la tabla entera, y a veces se lee entre
  las dos operaciones. Ni el colector ni `reprocesar` la cuentan; contar líneas
  sí lo hacía.
- **El dashboard de la defensa coteja contra esta entrada.** P10 recalcula los
  sondeos del 07-12/10 y se para si no dan 17.109.

## Qué se hizo / qué queda abierto

Hecho:
- Recuento por día y huecos de la EMT y de la 192 con el instrumento corregido.
- Contraste con grep sobre el crudo sin parsear.
- P10 del dashboard pasa a citar esta entrada.

Abierto:
- **Los 2 sondeos que faltan frente al colector, sin verificar.** Lo más
  probable es que sean errores de red: el colector los cuenta en `err` y no los
  guarda, porque fallan antes de `append_raw`. El journal del 13/10 solo se
  conserva como la suma que pegó la sesión, sin el reparto entre `ok`, `dup` y
  `err`, así que no se puede comprobar. Son el 0,01 %.

## Para la memoria

> La completitud de la captura de los días de prueba se verificó contando las
> consultas guardadas que contenían datos, y no todas las respuestas
> registradas. El portal municipal devuelve a veces un mensaje de error, y otras
> la tabla de posiciones vacía mientras se recarga. El programa de captura
> guarda ambas respuestas antes de interpretarlas, de modo que contarlas como
> consultas válidas sobrestima la completitud. Con el criterio corregido, entre
> el 7 y el 12 de octubre se conservaron 17.109 de las 17.280 consultas de
> posiciones de la flota que corresponden a una cadencia de 30 s (99,0 %). El
> intervalo más largo entre consultas consecutivas fue de 2 min 31 s, frente al
> umbral de una hora fijado de antemano para descartar un día de servicio. La
> capa de estado del tráfico conservó 1.723 de 1.728 consultas (99,7 %), con
> interrupciones de 15 y 10 minutos. El recuento coincide con los contadores
> del programa de captura con una discrepancia del 0,01 %. Ningún día de esta
> ventana se descartó por falta de datos.
