---
id: 063
titulo: La capa 157 de clima publica a dos ritmos (10 min y casi 1 h con 51-91 min de retraso), la clave de sondeo por el máximo tira 3 de 64 lecturas y retrasa 12, y la captura puente deja 51 h 54 min sin cubrir antes de que la Pi tome el relevo
fecha: 2026-11-09
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: medio
estado: aceptado
evidencia: bloque de «Cómo se midió», sobre data/raw/source=meteo_estaciones/date=2026-11-06 (120 sondeos); commits 9f9e066 (clave por estación) y 155c617 (curar re-firmado)
trampa: —
---

## Qué se observó

La capa 157 del geoportal (`OPENDATA/MedioAmbiente/MapServer/157`, *Estaciones
Atmosféricas*) es la única fuente en vivo con lluvia, viento y temperatura dentro
de València. Sirve el último valor de cada estación y lo pisa: no guarda
histórico. Sobre los **120 sondeos** del 06/11 (16:59-20:57 UTC, uno cada 2 min,
cinco filas cada uno, ningún payload sin filas):

- **Cinco estaciones**: W01 Av. Francia, W02 Nazaret, W03, W04 y W06 (no hay
  W05). W03 es AEMET 8414A (Valencia Aeropuerto, SYNOP 08284) y W04 es AEMET
  8416Y (València Viveros, SYNOP 08285).
- **Dos cadencias.** En 4 h salen **64 lecturas distintas** (estación, marca):

  | estaciones | lecturas | intervalo entre marcas | latencia de la primera vista |
  |---|---|---|---|
  | W01, W02 (municipales) | 25 y 24 | 10 min (W02, un salto de 20) | 5,5-9,3 min, mediana 7,4 |
  | W03, W04, W06 (AEMET) | 5 cada una | 40-90 min | 51-91 min, mediana 51-62 |

  Las de AEMET aparecen hacia el minuto :41 (y una vez al :59); los valores
  intermedios no se publican nunca.
- **La convención se decide solo con W01 y W02.** Las de AEMET llegan 51-91 min
  tarde y, con la capa servida en hora local, su lectura como UTC cae dentro de
  la horquilla de latencia plausible: desplazaría el sondeo entero +1 h sin
  aviso. Sin ninguna municipal en el sondeo la convención sale `DUDOSA`
  (`ESTACIONES_MUNICIPALES`, commit c4bbcd0, mutante 207).
- **La convención horaria es UTC ese día.** La presión de W04 coincide con el
  SYNOP 08285 leyendo `fecha_carg` como UTC y se aparta leyéndola como hora
  local (tabla en *Cómo se midió*). El grupo comparado es el **3PPPP, presión
  de estación**, no el 4PPPP, que es la presión reducida al nivel del mar y
  queda ~1,5 hPa por encima. Un solo día **no fija** la convención: la EMT
  alterna de un sondeo al siguiente (trampa 002), y por eso el parser decide en
  cada respuesta.
- **La latencia por sondeo depende de a qué fila se mida.** La fila más fresca
  llega con **332-933 s** (mediana 683); la mediana de las cinco, con
  **3.081-6.575 s**. Decidir la convención por la mediana, como hace
  `resolver_convencion` por omisión, daría `DUDOSA` siempre; la capa 157 decide
  con la fila más fresca (`agg="min"`).
- **La clave de sondeo por el máximo pierde lecturas.** Con la clave que
  `clave_sondeo` usa en una fuente con `ts_utc` (la mayor marca), los 120
  sondeos son **25 distintos**; con el conjunto (estación, marca), **32**.
  - Con el máximo se **pierden 3 lecturas, todas de W02** (20:00, 20:20 y 20:40
    UTC): 61 de 64 lecturas.
  - Con el máximo **12 lecturas entran tarde**, de 240 a 360 s (4-6 min), todas
    de las tres estaciones AEMET.
  - El mecanismo: una estación que publica con una marca anterior al máximo
    vigente no cambia el máximo, y su respuesta cuenta como duplicada.
- **Descartada la alternativa de la GVA**: el CSV horario «últimos 2000» se
  actualiza una vez al día (`Last-Modified` 11:02 UTC). A las 17:00 del 06/11 su
  último dato era del 05/11 a las 23:00, y cubre unas 4 h de todas las
  estaciones. No sirve ni para rellenar el pasado reciente ni para el presente.
- **`precipitac` vale 0,0 en todas las estaciones**: no ha llovido, y no se sabe
  si acumula 10 min, 1 h o el día. Las unidades del viento tampoco están
  interpretadas.
- **La captura puente tiene tres huecos irrecuperables.** Hasta que la Pi tomó el
  relevo (servicio arrancado el 09/11 a las 10:30:22 UTC; su primer `--status`
  dio `meteo_estaciones` con 1 sondeo, 5 filas, 0 errores y VIVO), la capa la
  capturó el portátil con un sondeo lanzado a mano desde una sesión de trabajo:

  | día | de (UTC) | a (UTC) | sondeos |
  |---|---|---|---|
  | 06/11 | 16:59 | 20:57 | 120 |
  | 07/11 | 14:22 | 22:29 | 244 |
  | 08/11 | 13:30 | 14:57 | 45 |
  | 09/11 | 10:25 | 10:37 | 7 |

  | hueco | duración |
  |---|---|
  | 06/11 20:57 → 07/11 14:22 | 17 h 25 min |
  | 07/11 22:29 → 08/11 13:30 | 15 h 01 min |
  | 08/11 14:57 → 09/11 10:25 | 19 h 28 min |
  | **total** | **51 h 54 min** |

  Son 416 sondeos del portátil, sin ningún payload con error. Antes del 06/11
  16:59 no hay nada: esa fue la primera vez que se miró la capa. Causa de cada
  hueco, solo donde está verificada:
  - **Primero (06/11 → 07/11)**: la captura del 06/11 fue una tanda exploratoria
    acotada (120 sondeos cada 2 min, unas 4 h) y el sondeo puente no se lanzó
    hasta el 07/11 a las 14:22 UTC.
  - **Segundo (07/11 → 08/11)**: el sondeo paró a las 22:29 UTC. Causa **no
    verificada**: pudo ser el fin de su tiempo de ejecución configurado o el fin
    de la sesión.
  - **Tercero (08/11 → 09/11)**: verificado. El sondeo, relanzado para 48 h,
    murió al terminar la sesión que lo había lanzado.

  La lección es que una captura que depende de la sesión de un portátil no es una
  captura.

## Cómo se midió

El instrumento reutiliza `read_raw`, `parse_meteo` y `clave_sondeo`, que son lo
que corre en el colector. `clave_sondeo` del repo es hoy la clave por pares; la
del máximo se escribe aquí a mano. No hay medidor en `analysis/`: el bloque es la
evidencia.

```bash
$env:PYTHONUTF8 = "1"
uv run python -c "
from pathlib import Path
import pandas as pd
from project.ingest.sources import clave_sondeo, parse_meteo, read_raw

dia = Path('data/raw/source=meteo_estaciones/date=2026-11-06')
S = [(ts, parse_meteo(p, ts)) for f in sorted(dia.glob('*.gz')) for ts, p in read_raw(f)]
S = [(ts, df) for ts, df in S if not df.empty]
print('sondeos con filas', len(S))

def primeras(clave):                      # la primera captura de cada clave
    v = {}
    for ts, df in S:
        v.setdefault(clave(df, ts), (ts, df))
    return v
def vistas(v):                            # primera vez que entra cada (estacion, marca)
    o = {}
    for ts, df in v.values():
        for r in df.itertuples():
            k = (r.fiwareid, r.ts_utc)
            o[k] = min(o.get(k, ts), ts)
    return o

km = primeras(lambda df, ts: str(df['ts_utc'].max()))
kp = primeras(clave_sondeo)
print('claves distintas: maximo', len(km), '| pares', len(kp))
vm, vp = vistas(km), vistas(kp)
print('lecturas: pares', len(vp), '| maximo', len(vm))
print('perdidas con el maximo', sorted((e, str(t)[11:16]) for e, t in set(vp) - set(vm)))
tarde = pd.Series({k: (vm[k] - vp[k]).total_seconds() for k in vm if vm[k] > vp[k]})
print('tarde con el maximo', len(tarde), '| s min/max', round(tarde.min()), round(tarde.max()))
fresca = pd.Series([df['latencia_s'].min() for _, df in S])
mediana = pd.Series([df['latencia_s'].median() for _, df in S])
print('latencia fila mas fresca s', round(fresca.min()), round(fresca.median()), round(fresca.max()))
print('latencia mediana de las cinco s', round(mediana.min()), round(mediana.max()))
print('convenciones', pd.Series([df['tz_convencion'].iloc[0] for _, df in S]).value_counts().to_dict())
lat = pd.DataFrame([(e[:3], (t0 - m).total_seconds() / 60) for (e, m), t0 in vp.items()],
                   columns=['estacion', 'min'])
print(lat.groupby('estacion')['min'].agg(['count', 'min', 'median', 'max']).round(1))
"
```

Salida del 09/11:

```
sondeos con filas 120
claves distintas: maximo 25 | pares 32
lecturas: pares 64 | maximo 61
perdidas con el maximo [('W02_NAZARET_10m', '20:00'), ('W02_NAZARET_10m', '20:20'), ('W02_NAZARET_10m', '20:40')]
tarde con el maximo 12 | s min/max 240 360
latencia fila mas fresca s 332 683 933
latencia mediana de las cinco s 3081 6575
convenciones {'YA_EN_UTC': 120}
          count   min  median   max
estacion                           
W01          25   5.5     7.4   9.3
W02          24   5.6     7.4   9.3
W03           5  51.5    61.6  91.3
W04           5  51.3    61.5  71.4
W06           5  51.3    51.5  69.3
```

La tabla por estación son las últimas líneas: lecturas distintas y minutos entre
la marca y la primera vez que se ve.

Los huecos de la captura puente salen de la primera y la última hora de
`ts_ingest_utc` de cada `date=` de `source=meteo_estaciones` (`read_raw`):
17:25:04, 15:01:08 y 19:28:18 entre un día y el siguiente.

La convención contra el SYNOP sale de Ogimet, público y sin clave, que sirve los
mensajes SYNOP en bruto. El grupo `3PPPP` es la presión de estación en décimas
de hPa, con el 1 de los millares omitido (`30209` = 1020,9 hPa):

```bash
curl -s "https://www.ogimet.com/cgi-bin/getsynop?block=08285&begin=202611061400&end=202611062100"
# 20 UTC: AAXX 06201 08285 ... 30209 40224 ...  -> 3PPPP = 1020,9 ; 4PPPP = 1022,4 (nivel del mar)
```

W04 leído como UTC, comparado con el SYNOP 08285 interpolado linealmente a ese
instante (la lectura es de 10 min y el SYNOP, horario). «Local» es leer la misma
marca como hora de Madrid, UTC+1 el 6/11:

| marca de W04 | W04 (hPa) | SYNOP interpolado | diferencia, UTC | diferencia, local |
|---|---|---|---|---|
| 15:50 | 1019,0 | 1019,09 | −0,09 | −0,04 |
| 16:50 | 1019,3 | 1019,35 | −0,05 | +0,21 |
| 17:30 | 1019,8 | 1019,80 | 0,00 | +0,55 |
| 18:40 | 1020,5 | 1020,47 | +0,03 | +0,57 |
| 19:50 | 1020,9 | 1020,85 | +0,05 | +0,37 |

La de las 19:50 vale **1020,9 hPa, el valor exacto del SYNOP de las 20 UTC**. La
diferencia media absoluta es de 0,04 hPa con lectura UTC y de 0,35 con lectura
local (0,75 con UTC+2, sobre las cuatro lecturas que caen dentro del SYNOP
descargado). Con W03 contra el SYNOP 08284: 0,11 frente a 0,37
(0,82). El diseño anotó 0,5-0,8 hPa de diferencia local; sobre las cinco
lecturas sale 0,04-0,57 (media 0,35) con UTC+1, y 0,26-1,20 (media 0,75) con
UTC+2. La conclusión no cambia, pero el contraste es
modesto: la presión sube despacio y una hora de desplazamiento mueve solo unas
décimas, así que no sustituye a observar la fuente más días.

## Por qué importa

- **La variable de clima tendrá histórico solo desde el 06/11.** Es un límite del
  alcance, no un fallo del colector: la capa no guarda pasado y el CSV de la GVA
  tampoco sirve. Los 51 h 54 min de huecos son, a las cadencias medidas, del
  orden de **310 lecturas de cada estación municipal y 52 de cada una de AEMET**
  que no estarán (estimación a 6 y a ~1 lecturas por hora, no contadas). Quien
  una el clima a los pasos por parada de esos días debe tratar el hueco como
  dato ausente, no como dato igual al anterior.
- **Dos cadencias, dos «ahora».** Una lectura de AEMET llega con 51-91 min de
  retraso. Con la regla de la trampa 017, la variable de clima en una fila es la
  última lectura **ya visible** (`ts_ingest_utc`), no la de su marca; unir por la
  marca filtraría el futuro en las tres estaciones AEMET.
- **La clave por el máximo habría dado un corpus incompleto sin error.** Tira 3
  lecturas (el 4,7 % de las 64) y retrasa 12 (el 19 %), y como la capa no tiene
  histórico, lo tirado no se recupera. El parser usa ya la clave por estación
  (commit 9f9e066, mutantes 203-206); `curar` se re-firmó con la capa 157 fuera
  y `data/curated` es idéntico (155c617).
- **El silencio de la fuente no se puede medir aún.** Con `silencio_max_s` de 30
  min (supuesto S4 del diseño), una sola estación muerta no da CAÍDA: hace falta
  `analysis/medir_silencios` tras unas dos semanas de captura.

## Qué se hizo / qué queda abierto

- **Captura**: capa 157 como fuente `meteo_estaciones` en el colector de develop
  (commits c219f24, c1c0b8b, 52cfcc7, 9f9e066, 2b34619, 155c617) y en el porte a
  mano de la rama `raspberry` (be1dd5e). Sondeo cada 5 min (`period_s=300`); los
  2 min eran del sondeo puente del portátil. Los huecos de arriba
  quedan **aceptados**: no se pueden rehacer.
- **Día del solape, D = 2026-11-09.** Ese día hay una captura del portátil
  (10:25-10:37 UTC, 7 sondeos) y otra de la Pi (desde las 10:30:22 UTC). El
  fichero del portátil se ha renombrado a
  `source=meteo_estaciones/date=2026-11-09/payloads-portatil.ndjson.gz`. Así
  `deploy_pi/pull_data.sh` (`rsync --ignore-existing`) no lo ve como existente y
  trae el `payloads.ndjson.gz` de la Pi **al lado**, y `reprocesar`
  (`sorted(dir_raw.rglob("*.ndjson.gz"))`) lee los dos, el del portátil primero
  (`-` < `.`). Los sondeos de los minutos en que coinciden entran dos veces y los
  absorbe la clave por estación. Límite: los `analysis/medir_*` que abren
  `payloads.ndjson.gz` por nombre exacto no ven los ~5 min del portátil
  (10:25-10:30Z, antes de que arrancara la Pi).
- **Abierto**: la unidad y la ventana de `precipitac` (S1: comparar con el SYNOP
  08285 la primera vez que llueva) y las unidades del viento (S7).
- **Abierto**: el segundo plan necesita histórico para la variable y la capa no
  lo da. Ogimet sirve los SYNOP horarios de 08284 y 08285 (aeropuerto y
  Viveros, las dos estaciones AEMET de la capa); es la fuente histórica
  candidata, a validar contra la capa 157 en los días que ambas cubran. No se ha
  comprobado cuánto pasado ofrece.
- **Sin guardia**: que el día del solape se junte bien no lo guarda ningún test;
  un `test_pull_data_une_el_dia_del_solape` cabría en el segundo plan.

## Para la memoria

> La capa de estaciones atmosféricas del geoportal municipal es la única fuente
> abierta en tiempo real con lluvia, viento y temperatura dentro de València, y
> no conserva histórico: sirve el último valor de cada estación y lo sustituye.
> Un sondeo cada dos minutos durante cuatro horas del 6 de noviembre de 2026
> (120 sondeos, 64 lecturas distintas) mostró que sus cinco estaciones publican
> a dos ritmos: las dos municipales, una lectura cada diez minutos visible unos
> siete minutos después de su marca; las tres de AEMET, una lectura cada 40-90
> minutos que aparece entre 51 y 91 minutos tarde. La convención horaria de la
> marca se contrastó con el mensaje SYNOP de la estación de Viveros: leída como
> UTC, la presión coincide con el SYNOP de las 20:00 (1020,9 hPa) y la diferencia
> media es de 0,04 hPa, frente a 0,35 hPa con lectura local. Deduplicar los
> sondeos por su marca máxima, como se hace con otras fuentes, habría tirado 3 de
> las 64 lecturas (el 4,7 %) y retrasado 12 entre cuatro y seis minutos; por eso
> la clave del sondeo es el conjunto de pares (estación, marca). La alternativa
> de la Generalitat, un CSV horario con los últimos 2.000 datos, se descartó
> porque se actualiza una vez al día. Como la fuente no guarda pasado, la captura
> empieza de hecho el 6 de noviembre y presenta tres huecos irrecuperables, de
> 17 h 25 min, 15 h 1 min y 19 h 28 min (51 h 54 min en total), anteriores a que
> la Raspberry Pi tomara el relevo el 9 de noviembre; el análisis posterior debe
> tratarlos como dato ausente y no interpolarlos.
