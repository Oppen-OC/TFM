---
id: 052
titulo: La mediana lectiva de la capa 192 que publicó la 031 (34 tramos congestionados por laborable) se midió con el 18/09 a medias, porque el recuento diario de tramos crece con las horas que cubre el día; con el 18/09 entero, la misma cuenta da 43, y 46 sin los dos días que partió el hueco del 10-14/09; la 188 sigue congelada en 243 valores los 57 días
fecha: 2026-10-14
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: medio
estado: abierto
evidencia: uv run python -m project.analysis.medir_fuentes --lectivo (tabla por día) y el fragmento de «Cómo se midió» para las medianas del 08-18/09 y la congestión acumulada del 18/09
trampa: —
---

## Qué se observó

El exportador del dashboard de la defensa coteja cada cifra con la ficha que la
publicó (plan `docs/superpowers/plans/2026-10-14-dashboard-ingesta.md`, parada
P7). Contra la bitácora 031 falló: la mediana de tramos de la 192 que llegan a
congestión en los laborables lectivos sale **43**, no 34.

Laborables del 08 al 18/09, sobre el curado reconstruido el 14/10:

| día | sondeos de la 192 | tramos en congestión | pico a la vez | horas-tramo |
|---|---|---|---|---|
| 08/09 | 288 | 25 | 10 | 32,8 |
| 09/09 | 285 | 43 | 15 | 57,0 |
| 10/09 | 101 | 11 | 11 | 5,4 |
| 14/09 | 95 | 18 | 15 | 27,2 |
| 15/09 | 282 | 43 | 27 | 51,7 |
| 16/09 | 277 | 50 | 32 | 66,8 |
| 17/09 | 280 | 52 | 40 | 90,9 |
| 18/09 | 286 | 49 | 27 | 109,1 |

| mediana de laborables | tramos | pico | horas-tramo |
|---|---|---|---|
| bitácora 031, «con la captura hasta el 18/09» | 34 | 15,5 | 42,3 |
| hoy, mismos días y misma cuenta | **43** | 21 | 54,4 |
| hoy, solo los 6 días completos | **46** | 27 | 61,9 |
| hoy, lectivo entero (08/09-13/10, 25 laborables) | 39 | 22 | 51,7 |
| hoy, lectivo entero, 18 laborables completos | 46 | 24 | 61,9 |
| antes del 08/09 (16 laborables) | 8,5 | 4 | 3,7 |

- **El instrumento no ha cambiado:** agosto reproduce la 031 exacta (8,5 / 4 /
  3,7). Lo que se movió es el corpus debajo de la cifra.
- **La 031 incluía el 18/09 a medias**, y lo decía («los días parciales: el 10,
  el 14 y el 18/09»). Con ocho laborables, la mediana es la media del cuarto y
  el quinto: para que diera 34, el 18/09 tenía que contar 25 tramos o menos. Ese
  día la congestión acumula **21 tramos hasta las 12:59** locales y 28 a las
  13 h: la copia de entonces acababa antes de las 13 h. Encaja con las entradas
  019-023, escritas el mismo 18/09 con la captura del día en curso.
- **La cuenta de tramos no se normaliza por las horas del día.** La 031
  normalizaba las horas-tramo para no inflar los días parciales, pero el número
  de tramos distintos que llegan a congestión sí crece con las horas cubiertas.
  El 10 y el 14/09 quedan partidos para siempre por el hueco de la 021, y bajan
  la mediana de 46 a 43.
- **La 188 sigue congelada:** 243 valores distintos en cada uno de los 57 días
  con dato, hasta el 13/10.

Con la cuenta de la 031, las horas-tramo lectivas son **×15** las de agosto
(54,4 frente a 3,7), no ×11.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_fuentes --lectivo
```

Esa salida da la tabla por día y las medianas del lectivo entero hasta hoy. Las
del 08-18/09 y la marca de días completos:

```python
from project.analysis import medir_fuentes as m
l = m.lectivo(); e = l["estado"].copy(); e["dia"] = e["dia"].astype(str)
s = m.sql("""SELECT CAST(ts_ingest_utc AT TIME ZONE 'Europe/Madrid' AS DATE) AS dia,
             count(DISTINCT ts_ingest_utc) AS sondeos FROM {f} GROUP BY 1""",
          f="trafico_estado")
s["dia"] = s["dia"].astype(str)
lab = e.merge(s, on="dia").query("dow >= 1 and dow <= 5")
cols = ["tramos_congestion", "pico_simultaneo", "horas_tramo"]
v = lab[lab["dia"].between("2026-09-08", "2026-09-18")]
print(v[cols].median(), v[v.sondeos >= 274][cols].median())   # 274 = 95 % de 288
```

La congestión acumulada del 18/09 por hora local:

```python
m.sql("""WITH c AS (SELECT idtramo, min(ts_ingest_utc AT TIME ZONE 'Europe/Madrid') p
         FROM {f} WHERE estado IN (1, 2)
           AND CAST(ts_ingest_utc AT TIME ZONE 'Europe/Madrid' AS DATE) = DATE '2026-09-18'
         GROUP BY 1)
         SELECT extract(hour FROM p) h, count(*) n FROM c GROUP BY 1 ORDER BY 1""",
      f="trafico_estado")
```

Sobre `data/curated` reconstruido con `dvc repro curar` el 14/10, crudo hasta el
12/10 UTC.

## Por qué importa

- La memoria habría citado 34 tramos y ×11. La conclusión de la 031 no cambia
  —la 192 se anima en periodo lectivo y la 188 está congelada—, se refuerza: la
  192 se anima más de lo publicado.
- Una cifra medida sobre un día en curso caduca cuando el día se completa, y no
  da error: la mediana sigue siendo plausible. Cualquier recuento diario de la
  192 tiene que decir si incluye días parciales (43 frente a 46).
- Es el cotejo funcionando: sin comparar con la ficha, el dashboard habría
  enseñado 43 y la memoria 34, y el tribunal habría visto las dos.

## Qué se hizo / qué queda abierto

- La parada P7 del dashboard coteja contra **43**, con la cuenta de la 031
  (laborables del 08 al 18/09, parciales incluidos).
- **Abierto:** el comentario de `SOURCES["trafico_estado"]` en
  `src/project/ingest/sources.py` repite «unos 34 tramos por laborable». Ese
  fichero es dependencia de `curar`: se corrige con su próximo cambio de código,
  no solo por un comentario.
- **Abierto:** decidir si los recuentos diarios de la 192 que entren en la
  memoria excluyen los días parciales.

## Para la memoria

> En periodo lectivo, desde el 8 de septiembre, la capa de estado del tráfico
> declara congestión en una mediana de 43 tramos por día laborable, frente a 8,5
> en agosto, y acumula 54,4 horas-tramo de congestión al día, unas quince veces
> las de agosto (3,7). Una primera medición, hecha con el último día todavía en
> captura, había dado 34 tramos: el número de tramos que llegan a congestionarse
> en un día crece con las horas que ese día tiene observadas, y un día incompleto
> lo infravalora. Contando solo los laborables completos, la mediana es de 46
> tramos. La capa de intensidad, en cambio, repite los mismos 243 valores
> distintos en cada uno de los 57 días con datos, por lo que se considera
> congelada y no se usa como predictor.
