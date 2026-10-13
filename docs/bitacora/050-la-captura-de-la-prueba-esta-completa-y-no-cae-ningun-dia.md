---
id: 050
titulo: La captura de la prueba está completa del 07 al 12/10, porque la EMT guarda el 99,1 % de los sondeos que da su cadencia y su hueco más largo es de 2 min, así que no cae ningún día; la captura volvió el 06/10 a las 13:56 UTC, no a las 13:22
fecha: 2026-10-13
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: medio
estado: abierto
evidencia: uv run python -m project.analysis.medir_completitud --desde 2026-10-06 (sobre data/raw, con el 06-12/10 copiado de /srv/tfm-sd/raw el 13/10); contraste con la línea ESTADO del journal del colector del 13/10 a las 07:29:59 UTC, pegada en la sesión del 13/10
trampa: —
---

## Qué se observó

Antes de traer la prueba del ADR-024 se contó lo que la Pi había capturado
desde el incidente de la bitácora 044. Se usó una copia de `/srv/tfm-sd/raw`,
contando sondeos sin etiquetar nada:

| día (UTC) | EMT | de | capa 192 | de |
|---|---|---|---|---|
| 06/10 | 1.197 | (desde las 13:56) | 122 | (desde las 13:56) |
| 07/10 | 2.855 | 2.880 | 286 | 288 |
| 08/10 | 2.851 | 2.880 | 287 | 288 |
| 09/10 | 2.855 | 2.880 | 288 | 288 |
| 10/10 | 2.854 | 2.880 | 288 | 288 |
| 11/10 | 2.854 | 2.880 | 287 | 288 |
| 12/10 | 2.850 | 2.880 | 288 | 288 |

- **EMT:** 17.119 de 17.280 sondeos posibles a 30 s (99,1 %) en los seis días
  de prueba ya cerrados. El hueco más largo es de **2 min** y solo hay dos: el
  08/10 de 08:10 a 08:12 UTC y el 12/10 de 13:38 a 13:40 UTC. Por debajo de un
  minuto y medio, todos.
- **Capa 192:** 1.724 de 1.728 a 5 min (99,8 %), con **un hueco de 15 min**, el
  07/10 de 16:33 a 16:48 UTC.
- **El 06/10, la captura volvió a las 13:56:30 UTC.** systemd da el colector
  activo desde las 15:56:19 locales. La nota del 11/10 decía «volvió a las
  13:22 UTC», pero las 13:22 eran la cota de la bitácora 044 («después de las
  13:22»), no la hora de vuelta. No cambia nada: el 06/10 sigue fuera por no
  tener la punta de mañana.
- **El instrumento cuadra con el colector.** Hasta las 07:29:59 UTC del 13/10,
  el crudo tiene 19.207 sondeos de la EMT, y los contadores del colector
  (`ok + dup + err`) suman 19.199. En la 192, 1.936 frente a 1.935. Sobran 8
  sondeos en el crudo de la EMT (0,04 %) que no se han explicado. No mueven
  ningún día.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_completitud --desde 2026-10-06
uv run python -m project.analysis.medir_completitud --desde 2026-10-07 --hasta 2026-10-12 \
    --fuentes emt_buses --umbral-min 1.5        # los dos huecos de 2 min
```

`medir_completitud` lee `ts_ingest_utc` de cada línea del crudo con
`sources.read_raw`. Saca los sondeos posibles de `SOURCES[fuente].period_s` y
lista los huecos entre sondeos seguidos que pasan del umbral. Con `--raw` mide
una copia fuera del repo; así se midió primero, sobre
`C:/Users/oppen/copia-tfm/raw`, antes de copiar el 06-12/10 a `data/raw/`.

El contraste con el colector salió de la línea `ESTADO` de
`journalctl -u tfm-colector` de las 07:29:59 UTC del 13/10, comparada con el
crudo contado hasta ese instante.

## Por qué importa

- **Es el criterio de día útil de la prueba.** La nota del 11/10 al ADR-024
  descarta un día solo si la EMT tiene un hueco de más de 1 h dentro de su día
  de servicio, porque sin posiciones no hay etiqueta. El hueco más largo es de
  2 min: ningún día de los seis cae y la prueba conserva todos sus días hasta
  el 12/10.
- **El servicio activo no prueba nada.** En la 044, systemd dio el colector
  «active (running)» durante 27 h sin un solo sondeo. La única evidencia de que
  la captura está completa es contar el crudo.
- **El hueco de la 192 no descarta días.** Deja sin tráfico observado las
  predicciones de 15 min de la tarde del 07/10, como el 22 y el 23/09 en la
  validación (bitácora 048), y `trafico_edad_s` las delata.
- **Se midió sin mirar la prueba.** El recuento lee solo instantes de ingesta y
  no etiqueta ni toca `features`. Se hizo antes del commit que cierra la fase A
  (389581b) y antes de copiar los días a `data/raw/`.

## Qué se hizo / qué queda abierto

Hecho:
- La cifra quedó anotada en la nota del 11/10 al ADR-024 y la hora del 06/10 se
  corrigió en `params.yaml`, en el commit 389581b.
- El 06-12/10 está en `data/raw/`, idéntico byte a byte a la copia de la Pi.
  El 13/10 sigue capturándose y no se ha copiado. No se ha ejecutado
  `dvc repro`.
- `analysis/medir_completitud.py` sustituye al script de la tarea 9 del plan
  de la fase 2.
- `pull_data.sh --verificar` del 13/10 da los 35 ficheros del 06-12/10 con el
  mismo contenido que la Pi; solo cambian los permisos.
- Sitio en la SD: 20 GB libres de 29 GB el 13/10 (`df -h` en la Pi). A unos
  36 MB al día, llega de sobra al 21/10.

Abierto:
- **El 13-19/10**, cuando se traiga el 21/10: el mismo comando con
  `--desde 2026-10-13 --hasta 2026-10-19` antes de `dvc repro` (paso 3 de la
  tarea 11). Esta entrada se cierra con esa cifra.
- Los 8 sondeos de más del crudo de la EMT frente a los contadores del colector.

## Para la memoria

> Antes de incorporar los días de la prueba se verificó la completitud de su
> captura. Tras el fallo del equipo de captura del 5 de octubre, el servicio
> había figurado como activo durante más de un día sin registrar ninguna
> consulta, así que el estado del proceso no garantiza la captura y la
> verificación se hizo contando los registros guardados. Entre el 7 y el 12 de
> octubre se conservaron 17.119 de las 17.280 consultas de posiciones de la flota
> que corresponden a una cadencia de 30 s (99,1 %). Ningún intervalo entre
> consultas consecutivas superó los 2 minutos, frente al umbral de una hora
> fijado de antemano para descartar un día de servicio. La capa de estado del
> tráfico conservó 1.724 de 1.728 consultas (99,8 %), con una única interrupción
> de 15 minutos. El recuento coincide con los contadores del propio programa de
> captura, con una discrepancia del 0,04 %. Ningún día de la prueba se descartó
> por falta de datos.
