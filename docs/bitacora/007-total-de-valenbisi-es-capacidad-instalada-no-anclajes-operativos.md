---
id: 007
titulo: En Valenbisi `available + free` no suma `total` en el 24,9 % de las filas y el desfase es siempre por defecto: `total` es capacidad instalada, no anclajes operativos
fecha: 2026-09-01
tipo: anomalia
capa: fuentes
capitulo: calidad-dato
impacto: medio
estado: aceptado
evidencia: uv run python -m project.analysis.medir_fuentes --valenbisi
trampa: —
---

## Qué se observó

La capa `OPENDATA/Valenbisi/228` publica tres contadores por estación:
`available` (bicis disponibles), `free` (anclajes libres) y `total`. La
comprobación obvia —que los dos primeros sumen el tercero— falla en una de cada
cuatro filas.

Sobre 1.148.238 registros de 273 estaciones (15/08–31/08 de 2026):

| métrica | valor |
|---|---|
| filas | 1.148.238 |
| cuadran | 861.899 |
| **no cuadran** | **286.339 (24,94 %)** |
| desfase por **defecto** (`available + free < total`) | 286.325 |
| desfase por exceso | **14** |
| desfase mínimo | −30 |
| desfase máximo | +3 |

**La dirección es el hallazgo.** Si el descuadre fuera ruido de medida, sobrarían
y faltarían anclajes por igual. Con 286.325 filas por defecto contra 14 por
exceso, no es ruido: es que `total` cuenta algo distinto de `available + free`.
La lectura que encaja con los datos es que **`total` es la capacidad física
instalada de la estación** y `available + free` los anclajes operativos en ese
instante. La diferencia son anclajes averiados o bicis retiradas a mantenimiento.

El descuadre además **no se concentra en unas pocas estaciones averiadas**, que
sería la hipótesis cómoda: repartido por estación da mediana 14,7 %, media
24,9 %, con recorrido completo de 0 % a 100 %. No hay dos grupos separados; hay
un continuo. Excluir estaciones no arregla nada.

Dos observaciones menores de la misma capa, del notebook 04:

- **`abierta` es constante `True`** en las 1.148.238 filas. Ninguna estación
  aparece cerrada en dieciséis días, lo que la inutiliza como feature y sugiere
  que la fuente no actualiza el campo.
- **Dos estaciones tienen el reloj congelado**: `016_COLON I` publica un `ts_utc`
  del 20/07/2026 —1.017 horas antes del último sondeo— y `018_COLON II` uno del
  19/08. Ambas siguen apareciendo en los 4.206 sondeos con contenido idéntico. Es
  el motivo de que el `ts_utc` mínimo del corpus de Valenbisi sea de julio pese a
  que la captura empezó el 15 de agosto.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_fuentes --valenbisi
```

Conteo global de coincidencias y descuadres separando el signo del desfase, más
la distribución del porcentaje de descuadre agrupado por `number`, que es lo que
distingue "unas pocas estaciones rotas" de "propiedad de la fuente".

Los relojes congelados y la constancia de `abierta` se ven en
[04_valenbisi.ipynb](../../notebooks/EDA/04_valenbisi.ipynb), secciones 4 y 5.

Comprobación del instrumento: `(ts_ingest_utc, number)` sí es clave única en esta
capa —0 duplicados sobre 1.148.238 filas—, así que el descuadre no puede venir de
filas repetidas, a diferencia de lo que ocurre en la capa 192.

## Por qué importa

La ocupación de las estaciones es la covariable que aporta esta fuente: un proxy
de actividad urbana, útil porque una zona que vacía sus anclajes a las 8:00 tiene
demanda de movilidad y puede correlacionar con congestión.

Calcularla como `available / total` —que es lo natural viendo los nombres de las
columnas— introduce un sesgo **que varía por estación y en el tiempo**: una
estación con seis anclajes averiados de treinta parecerá permanentemente un 20 %
más vacía de lo que está. Y como la proporción de anclajes averiados cambia a lo
largo de las semanas, el sesgo tampoco es una constante que se cancele al
comparar franjas horarias. El denominador correcto es `available + free`.

El caso de los relojes congelados es del mismo tipo, con el signo opuesto: una
estación cuyo contenido se repite idéntico en 4.206 sondeos es, para cualquier
estadístico de dispersión, la estación **más estable** de la red. Es exactamente
lo contrario: es una estación que no está informando. Un agregado por zona que la
incluya arrastra ese valor congelado como si fuera una observación.

Ninguno de los dos da error, y ambos producen números plausibles.

## Qué se hizo / qué queda abierto

Hecho:

- La medición queda reejecutable en `src/project/analysis/medir_fuentes.py`.
- El notebook 04 calcula la ocupación con `available / (available + free)`, no
  con `total`, y documenta por qué en el punto donde se hace.

Abierto:

- **La interpretación de `total` es inferida, no documentada.** Encaja con la
  dirección del desfase y con el sentido físico, pero la fuente no publica
  especificación. Se acepta como hipótesis de trabajo declarada, no como hecho.
- **Las dos estaciones con reloj congelado no están excluidas de nada**, porque
  todavía no hay nada que las consuma. Cuando `features.py` construya el agregado
  por zona, la guardia natural es un test que falle si entra una estación cuyo
  `ts_utc` lleve más de un umbral declarado sin avanzar.
- **`abierta` constante puede ser un artefacto del periodo.** Agosto, dieciséis
  días: quizá simplemente no cerró ninguna. Se remide si se amplía la captura.

## Para la memoria

> La capa de Valenbisi publica, para cada una de las 273 estaciones, el número de
> bicicletas disponibles, el de anclajes libres y un total. La verificación de
> coherencia interna sobre los 1.148.238 registros capturados entre el 15 y el 31
> de agosto de 2026 muestra que la suma de los dos primeros no coincide con el
> tercero en el 24,9 % de los casos. El desfase resulta sistemáticamente negativo
> —286.325 registros por defecto frente a 14 por exceso—, lo que descarta el
> error de medida aleatorio e indica que el campo total corresponde a la
> capacidad física instalada de la estación y no al número de anclajes operativos
> en cada instante, siendo la diferencia atribuible a anclajes averiados o
> bicicletas retiradas del servicio. La discrepancia no se concentra en un
> subconjunto de estaciones defectuosas, sino que se distribuye de forma continua
> entre ellas, con una mediana del 14,7 % de observaciones descuadradas por
> estación.
>
> En consecuencia, el índice de ocupación empleado como covariable de actividad
> urbana se define como el cociente entre bicicletas disponibles y anclajes
> operativos, y no sobre la capacidad instalada, que introduciría un sesgo
> variable por estación y en el tiempo. Se detectaron asimismo dos estaciones
> cuya marca temporal permanece congelada durante todo el periodo —una de ellas
> desde el 20 de julio— y que continúan publicando registros idénticos en cada
> sondeo; estas se tratan como ausencia de dato y no como observaciones estables,
> dado que cualquier estadístico de dispersión las interpretaría erróneamente
> como las estaciones de comportamiento más regular de la red.
