---
id: 065
titulo: A 63 días el EDA enseña tres cosas que agosto no tenía — las posiciones al sur de 39,36° caen del 2,06 % en agosto al 0,11 % en octubre, la capa 192 duplica los tramos 364 y 366 desde el 22/09 a las 17:27 UTC, y la EMT publica 633 posiciones fuera del área metropolitana, una por sondeo y 556 de la línea 92
fecha: 2026-11-17
tipo: anomalia
capa: fuentes
capitulo: calidad-dato
impacto: bajo
estado: aceptado
evidencia: uv run python -m project.analysis.medir_fuentes --eda-63 (con DATA_ROOT absoluto; curated del stage curar, 15/08-20/10/2026)
trampa: 006
---

## Qué se observó

Los notebooks de `notebooks/EDA/` se reejecutaron el 16/11 sobre el curated de
`curar` (15/08-20/10, 63 días, 18,7 M de filas de la EMT). Tres cosas no salían
con los 16 días de agosto de la primera versión.

**1. El sur de El Perellonet es estacional.** Posiciones con `lat < 39,36`
(trampa 006, líneas 24 y 25):

| mes | filas | al sur | % |
|---|---|---|---|
| 2026-08 | 5.330.500 | 109.962 | 2,06 |
| 2026-09 | 9.123.816 | 89.820 | 0,98 |
| 2026-10 | 4.268.486 | 4.828 | 0,11 |
| total | 18.722.802 | 204.610 | 1,09 |

**2. La capa 192 duplica dos tramos más.** Pares (sondeo, `idtramo`)
repetidos:

| idtramo | copias con `fiwareid` | sondeos | periodo (UTC) |
|---|---|---|---|
| 211, 216 | las dos | 11.716 | 15/08 20:14 - 22/09 11:02 |
| 211, 216 | una | 7.408 | 22/09 17:27 - 20/10 |
| **364, 366** | una | **7.408** | **22/09 17:27 - 20/10** |

Siempre dos copias con el mismo `estado`. A las 17:27 del 22/09 cambió el
formato de la capa entera: aparecen dos tramos duplicados más, y desde entonces
la copia de los cuatro llega sin `fiwareid`. Entre las 11:02 y las 17:27 de ese
día la capa solo devolvió errores del geoportal (bitácora 060).

**3. 633 posiciones fuera del área.** Fuera de la caja 39,15-39,65 N /
0,65-0,15 W, que ningún recorrido de la EMT alcanza, hay 633 filas en 633
sondeos distintos: una por sondeo, nunca la flota entera. 556 son de la línea
92 entre el 02 y el 15/10, de 38,1° N (Alicante) a 0,36° E en el mar. El resto
son sueltas de nueve líneas, del 22/09 al 18/10, con extremos en 25,6° N y en
47,7° N / 2,1° E (centro de Francia).

## Cómo se midió

```bash
DATA_ROOT="$(pwd -W)/data" uv run python -m project.analysis.medir_fuentes --eda-63
```

Bloque `eda_63()` de `medir_fuentes.py`: `ROLLUP` por mes sobre `emt_buses`,
`GROUP BY (ts_ingest_utc, idtramo) HAVING count(*) > 1` sobre `trafico_estado`,
partido por cuántas copias traen `fiwareid`, y
línea, fechas y extremos de las posiciones fuera de la caja. `DATA_ROOT` tiene
que ser absoluto si se lanza desde otro directorio (`notebooks/EDA/README.md`).

**El instrumento.** Se leyó el curated de `curar`, no el del colector en vivo:
con el del colector, `(snapshot_id, gid)` daba 973 duplicados que eran capturas
a medias (trampa 011, puerta 012). Las 633 son una por sondeo, así que no son
filas repetidas de una captura. La caja es solo un instrumento de recuento: el
pipeline no la usa.

## Por qué importa

- **El Perellonet.** La guardia de la trampa 006 sigue valiendo, pero su peso
  cambia con la estación: en octubre, el mes de la prueba del 07-19/10, el sur es
  el 0,11 % de las posiciones. Un filtro por caja habría sesgado poco la prueba
  y mucho agosto, que es entrenamiento. Por eso no se puede juzgar el filtro con
  una sola ventana.
- **Los duplicados 364/366.** No cambian ninguna cifra: `trafico.py` deduplica
  por `(ts_ingest_utc, idtramo)` antes de usar la capa (bitácora 014). Sí lo
  hace cualquier recuento de filas sobre el curated sin deduplicar. Desde el
  22/09, la capa tiene **414** filas con tramo por sondeo, no 412.
- **Las 633.** Son el 0,003 % de las filas y caen en el map-matching, que filtra
  por distancia al trazado de su línea y no por caja. No contaminan las
  etiquetas, pero sí cualquier figura que dibuje la extensión de la flota sin
  recortar.

## Qué se hizo / qué queda abierto

Hecho:

- Notebooks 01 y 02 actualizados con las tres observaciones (hallazgos 5, 8 y
  duplicados de la 02).
- La medición queda en `medir_fuentes.py --eda-63`.
- La 005 citaba los 63 tramos con congestión como cifra de la capa; ahora
  remite a la 031, la 052 y a esta.

Abierto:

- **No se sabe por qué la 92 publica coordenadas lejanas** durante dos semanas.
  No se investiga: el map-matching las descarta y no hay histórico que mirar.
- **No hay test que cuente las 633 descartadas por el map-matching.** Cabría
  uno, `test_posicion_a_cientos_de_km_no_se_asigna`, pero la guardia de la 006
  ya ejerce el filtro por distancia.

## Para la memoria

> La ampliación del corpus de 16 a 63 días modifica la lectura de varias
> anomalías de las fuentes. Las posiciones situadas al sur de la latitud 39,36°,
> que corresponden a las líneas que dan servicio a la pedanía litoral de El
> Perellonet y no a errores de geolocalización, representan el 2,06 % de los
> registros en agosto, el 0,98 % en septiembre y el 0,11 % en octubre: su peso
> es estacional, y un filtro por recuadro geográfico habría sesgado de forma
> desigual el periodo de entrenamiento y el de prueba. En la capa de estado del
> tráfico, desde el 22 de septiembre dos tramos adicionales se publican por
> duplicado con el mismo estado, lo que obliga a deduplicar por instante y tramo
> antes de cualquier recuento. Por último, la flota publica 633 posiciones fuera
> del área metropolitana, hasta a cientos de kilómetros y siempre una por
> sondeo, 556 de ellas de una única línea durante dos semanas de octubre. Su
> peso es despreciable (0,003 % de los registros) y el emparejamiento con el
> trazado las descarta por distancia, sin necesidad de recortes geográficos.
