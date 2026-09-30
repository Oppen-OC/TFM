---
id: 035
titulo: El corpus entero solo está en el PC — la copia de la Pi empieza el 18/08 a las 23:02 UTC, y copiarla encima del crudo deja ese día de la EMT en 115 sondeos en vez de 1.109 sin dar ningún error
fecha: 2026-09-30
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: medio
estado: mitigado
evidencia: uv run python -m project.analysis.auditar_persistencia --copia C:/Users/oppen/tfm-data/raw
trampa: 016
---

## Qué se observó

`data/raw/` contra la copia traída de la Pi (`C:/Users/oppen/tfm-data/raw`,
del 18/08 al 18/09), fichero a fichero: de los 163 del repo, **143 coinciden
byte a byte** con la copia y **20 no tienen igual**.

- **15 no están en la copia**: los cinco de cada día del 15 al 17/08, que capturó
  el portátil antes de que existiera la Pi. 16.371 sondeos, 6.087 de la EMT.
- **5 difieren**: los del 18/08, el día del relevo entre los dos colectores.

| fuente, 18/08 | repo | copia | comunes | solo repo | solo copia | claves nuevas |
|---|---|---|---|---|---|---|
| emt_buses | 1.109 | 115 | 7 | 1.102 | 108 | 0 |
| renfe_cercanias | 1.105 | 115 | 8 | 1.097 | 107 | 0 |
| trafico_estado | 188 | 13 | 1 | 187 | 12 | 12 |
| trafico_intensidad | 50 | 5 | 0 | 50 | 5 | 5 |
| valenbisi | 112 | 12 | 1 | 111 | 11 | 8 |
| **total** | 2.564 | 260 | 17 | 2.547 | 243 | 25 |

El fichero del repo es una costura: los sondeos del portátil hasta las 23:56:19
UTC y, detrás, los 7 de la Pi desde las 23:56:34. El primer sondeo de la Pi es
de las 23:02:07, así que los dos colectores sondearon a la vez 54 minutos. Los
108 sondeos de la EMT que la copia tiene y el repo no son de ese solape, y
**ninguno trae un `snapshot_id` que el repo no tenga** (114 claves en los 115
sondeos de la copia, las 114 en el repo): no aportan una sola posición.

En total, **18.918 sondeos** (7.189 de la EMT) están en el repo y no en la copia.

Esto sustituye a lo que motivó la entrada. La sospecha era que el fichero de la
Pi del 18/08 (148 KB frente a 3,8 MB) fuese un día truncado o a medio copiar,
en la línea de `_TRUNCADOS.txt`. No lo es: está íntegro, y la truncación ya
quedó descartada en la [011](011-el-crudo-esta-integro-y-ningun-test-lo-guarda.md).
Es corto porque la Pi empezó a capturar a las 23:02.

## Cómo se midió

```bash
uv run python -m project.analysis.auditar_persistencia --copia C:/Users/oppen/tfm-data/raw
```

`comparar()` descarta los ficheros iguales byte a byte y, en el resto, cruza los
`ts_ingest_utc` que devuelve `gzip.open` a cada lado. `claves_nuevas` parsea los
dos ficheros y cuenta las claves de sondeo (`clave_sondeo`, la que usa
`reprocesar` para deduplicar) que están en la copia y no en el repo.

Contraste con otro instrumento, que no pasa por Python:

```bash
ORIGEN=/mnt/c/Users/oppen/tfm-data/raw bash deploy_pi/pull_data.sh --verificar   # desde WSL
```

`rsync --checksum` señala los mismos 5 ficheros del 18/08 y ninguno más.

Dos cosas que la cifra **no** dice:

- La copia es la del PC, no la Pi. Cuando se trajo (su último día es el 18/09),
  la Pi tenía eso en el 18/08: el `mtime` del fichero copiado es su última
  escritura, 23:59 UTC del 18/08. Si guarda además el 15-17/08 no se ha
  comprobado: no hay acceso por clave y la copia se trajo filtrando por día.
- `claves_nuevas` en tráfico es siempre igual a `solo_copia`. Esas capas no
  publican marca de tiempo y su clave es el instante de captura
  ([004](004-el-solape-con-trafico-es-un-suelo-no-el-desfase-real.md)): dos
  colectores nunca coinciden. En Renfe sale 0 porque los 115 sondeos de la
  copia quedan vacíos tras filtrar el núcleo: a esa hora no circula ningún tren.

## Por qué importa

El corpus no es recapturable, y la instrucción que había para traerlo
(`rsync -av pi:/srv/tfm-data/raw/ …`) es correcta hacia un directorio aparte y
destructiva hacia `data/raw/`: rsync sustituye el fichero del 18/08 por el de la
Pi porque difieren en tamaño y fecha. Se perderían 1.102 de los 1.109 sondeos de
la EMT de ese día (99,4 %) y 2.547 de los 2.564 de las cinco fuentes. Nada
falla después: `reprocesar` lee lo que haya, `dvc repro` se rehace con un día
de una hora y las métricas salen igual de plausibles.

No se acumula, pero tampoco se deshace: `data/` está fuera de git, `raw/` no
tiene puntero de DVC y no hay remoto configurado. De los cuatro primeros días
(15-18/08) la única copia comprobada es la de este disco.

## Qué se hizo / qué queda abierto

Hecho:

- `deploy_pi/pull_data.sh` trae el crudo a `data/raw/` con `--ignore-existing`:
  solo añade ficheros y no puede tocar uno que ya esté. Deja fuera el día en
  curso (UTC), `curated/` y `reference/`. Probado contra un árbol sintético
  (fichero existente intacto, día en curso y `gtfs/` fuera, segunda pasada sin
  transferencias) y, en seco, contra la copia real: no traería nada.
- `--verificar` en el mismo script y `--copia` en `auditar_persistencia`.

Abierto:

- Comprobar en la Pi qué días tiene (`ls /srv/tfm-data/raw/source=emt_buses`) y
  pasar `--verificar` contra ella, no contra la copia.
- **Segunda copia del 15-18/08.** Hoy depende de un solo disco.
- Los 25 sondeos del solape con clave propia (17 de tráfico, 8 de Valenbisi) no
  están en el repo. Siguen en `tfm-data/`; son de la 01:00 a las 02:00 hora
  local y el repo ya muestrea esa hora con el otro colector.
- El script no tiene guardia en `pytest`: necesita `rsync`, que en este entorno
  solo existe dentro de WSL.

## Para la memoria

> La captura se inició en un ordenador portátil el 15 de agosto de 2026 y se
> trasladó a un equipo dedicado de bajo consumo el 18 de agosto, con un periodo
> de 54 minutos en el que ambos colectores sondearon las fuentes a la vez. La
> comparación de las dos copias del corpus, fichero a fichero, mostró que 143 de
> los 163 ficheros diarios eran idénticos y que los 20 restantes correspondían a
> los cuatro primeros días: 18.918 sondeos, 7.189 de ellos de posiciones de
> autobuses, existían únicamente en la copia del portátil. Durante el solape, los
> 108 sondeos de posiciones registrados solo por el segundo colector no contenían
> ninguna instantánea que el primero no hubiese capturado: en ese intervalo, un
> segundo colector independiente no vio nada que el primero hubiera perdido. La
> consecuencia operativa es que la copia del equipo de captura no contiene el
> corpus completo, y que una sincronización convencional de ese equipo sobre el
> corpus de trabajo habría sustituido el día del relevo por su última hora sin
> emitir error alguno. La transferencia se restringió por ello a añadir jornadas
> cerradas, sin sobrescribir nunca un fichero existente.
