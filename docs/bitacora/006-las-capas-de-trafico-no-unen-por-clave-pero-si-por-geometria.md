---
id: 006
titulo: Las dos capas de tráfico tienen intersección cero de idtramo pero instrumentan la misma red; la mitad de los tramos de la 188 tiene vecino de la 192 a menos de 50 m
fecha: 2026-09-01
tipo: medicion
capa: fuentes
capitulo: metodologia
impacto: medio
estado: abierto
evidencia: uv run python -m project.analysis.medir_fuentes --union-trafico
trampa: —
---

## Qué se observó

Las dos capas de tráfico del Ajuntament son complementarias sobre el papel: la
192 da un estado categórico y la 188 (`OPENDATA/Trafico/188`) una **medida
continua** de intensidad. Unirlas es lo que permitiría cuantificar la congestión
en vez de clasificarla, que es justo lo que la entrada
[005](005-la-capa-192-tiene-410-tramos-y-63-con-congestion.md) demuestra que hace
falta.

**Por clave no se unen.** No es un problema de tipos, es que son espacios de
nombres distintos:

| capa | tramos | tipo de `idtramo` | ejemplos |
|---|---|---|---|
| 188 intensidad | 389 | `VARCHAR` | `A302`, `A347`, `B14`, `B92` |
| 192 estado | 410 | `DOUBLE` | `158`, `185`, `271`, `151` |

Intersección tras castear ambos a texto: **0**.

**Por geometría sí.** Distancia de cada tramo de la 188 al tramo más cercano de
la 192, calculada con haversine sobre los puntos iniciales que guarda
`data/reference/`:

| umbral | tramos de la 188 | % |
|---|---|---|
| ≤ 50 m | 193 de 389 | 49,6 |
| ≤ 100 m | 221 de 389 | 56,8 |
| ≤ 250 m | 302 de 389 | 77,6 |
| ≤ 500 m | **384 de 389** | **98,7** |

Mediana 51,6 m, media 135,6 m, máximo 871,9 m. Las dos capas están instrumentando
la misma red viaria con dos numeraciones distintas.

**Pero la correspondencia no es uno a uno.** Los 389 tramos de la 188 apuntan a
solo **175** tramos distintos de la 192. Un `merge` por vecino más cercano
duplicaría filas: `EUGENIA VIÑES` de la 192 recoge dos tramos de la 188 y `SANT
PIUS V - TRINITAT - GUADALAVIAR` recoge tres.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_fuentes --union-trafico
```

Conjuntos de `idtramo` distintos de cada capa en `data/curated/`, casteados
ambos a texto antes de intersecar. Para la distancia, haversine de todos contra
todos (389 × 410 = 159.490 pares, trivial en memoria) sobre las tablas
`data/reference/trafico_estado_geometria.parquet` y
`trafico_intensidad_geometria.parquet`.

**Ojo con el instrumento**, y por eso la entrada nace `abierto`: `lat` y `lon` de
`reference/` son el **punto inicial** de la `LINESTRING` de cada tramo, no su
centroide ni su trazado. Dos tramos que recorren la misma calle en sentidos
opuestos empiezan en extremos contrarios y la medida los separa cientos de
metros. **La cifra acota por arriba: la correspondencia real es al menos tan
buena como esta, nunca peor.** Una unión definitiva exige comparar las
`LINESTRING` completas y considerar el sentido de circulación.

Deriva del notebook
[03_trafico_intensidad.ipynb](../../notebooks/EDA/03_trafico_intensidad.ipynb),
sección 5.

## Por qué importa

Es lo que decide si la capa 188 entra en el modelo o se queda fuera, y esa
decisión cambió de signo al medirla.

Antes del EDA, la 188 era "una capa complementaria más". Después de la entrada
[005](005-la-capa-192-tiene-410-tramos-y-63-con-congestion.md) —la 192 da 63
tramos con congestión y 111 episodios en dieciséis días— la 188 pasa a ser
**candidata a variable explicativa principal**: una lectura continua tiene señal
donde una categórica con el 98,2 % de sus filas en una sola clase no la tiene.

El riesgo que hay que evitar es concreto y silencioso: **un `merge` por `idtramo`
entre las dos capas devuelve cero filas**. No lanza excepción. En un pipeline con
`how="left"` el resultado son columnas de intensidad enteramente nulas, que
parecen un problema de cobertura de la fuente y no un error de unión. La forma de
no caer es saber de antemano que la intersección es cero por construcción, no por
datos que falten.

El segundo riesgo es el inverso: unir por vecino más cercano sin agregar
duplicaría las filas de los tramos de la 192 que recogen varios de la 188, y
sobrerrepresentaría exactamente los corredores mejor instrumentados —los grandes
ejes—, que son los que más autobuses llevan.

## Qué se hizo / qué queda abierto

Hecho:

- La medición queda reejecutable en `src/project/analysis/medir_fuentes.py`.
- El notebook 03 documenta la intersección vacía con los tipos y los ejemplos, y
  dibuja el histograma de distancias con los umbrales marcados.

Abierto:

- **La unión no está implementada.** Requiere comparar `LINESTRING` completas y
  decidir el criterio de sentido de marcha. Es trabajo de `prepare.py`.
- **La agregación no está decidida.** Cuando varios tramos de la 188 caen sobre
  el mismo de la 192, hay que elegir —máximo, media, suma de intensidades— y
  justificarlo. Hoy no hay elección, solo la constatación de que hace falta una.
- **La cifra se remide cuando exista la unión real.** Los 49,6 % a 50 m salen de
  puntos iniciales; con trazados completos el número será distinto y presumible-
  mente mejor. La guardia natural, cuando `prepare.py` exista, es un test que
  falle si la unión devuelve cero filas o si multiplica el número de filas de
  entrada.

## Para la memoria

> El Ajuntament de València publica dos capas de tráfico complementarias: una de
> estado categórico y otra de intensidad, esta última con una medida continua de
> vehículos que resulta de mayor interés como regresor. Se evaluó la posibilidad
> de combinarlas. Ambas capas emplean identificadores de tramo mutuamente
> incompatibles —alfanuméricos con prefijo de letra en la capa de intensidad,
> numéricos en la de estado—, con intersección vacía entre los 389 y los 410
> tramos respectivos, por lo que no admiten unión por clave.
>
> Se recurrió entonces a una correspondencia geográfica, calculando para cada
> tramo de la capa de intensidad la distancia al tramo más próximo de la capa de
> estado a partir de las geometrías de referencia. La distancia mediana resultó
> de 51,6 metros, con un 49,6 % de los tramos por debajo de los 50 metros y un
> 98,7 % por debajo de los 500, lo que evidencia que ambas capas instrumentan la
> misma red viaria bajo numeraciones distintas. La correspondencia, no obstante,
> no es biunívoca: los 389 tramos de la capa de intensidad se proyectan sobre
> únicamente 175 tramos de la capa de estado, de modo que la unión requiere
> definir explícitamente un criterio de agregación para evitar la duplicación de
> registros en los corredores mejor instrumentados. Debe señalarse además que la
> distancia se calculó entre los puntos iniciales de cada tramo y constituye por
> tanto una cota superior: la correspondencia efectiva, evaluada sobre los
> trazados completos y atendiendo al sentido de circulación, no puede ser peor
> que la aquí estimada.
