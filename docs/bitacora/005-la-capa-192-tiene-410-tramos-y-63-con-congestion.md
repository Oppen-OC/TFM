---
id: 005
titulo: La capa 192 declara 410 tramos pero solo 63 llegan a congestionarse, y el 98 % de su estado "cortado" son siete vías cerradas de forma permanente
fecha: 2026-09-01
tipo: medicion
capa: fuentes
capitulo: limitaciones
impacto: alto
estado: aceptado
evidencia: uv run python -m project.analysis.medir_fuentes --senal-192
trampa: —
---

## Qué se observó

La capa `OPENDATA/Trafico/192` es la variable explicativa central del TFM. Su
censo dice 410 tramos. Medido sobre los 2.754.220 registros del corpus
(15/08–31/08 de 2026, 6.685 sondeos), lo que informa es mucho menos:

| tramos | cifra |
|---|---|
| con estado no nulo | 409 |
| que cambian de estado **alguna vez** | 77 |
| que llegan a estar `denso` o `congestionado` | **63** |
| que llegan a estar `cortado` | 22 |

Reparto de la variable `estado`:

| estado | filas | % |
|---|---|---|
| 0 fluido | 2.705.250 | 98,222 |
| **3 cortado** | **41.444** | **1,505** |
| nulo | 6.685 | 0,243 |
| 1 denso | 779 | 0,028 |
| 2 congestionado | 62 | 0,002 |

`cortado` aparece **cincuenta veces más** que `denso` y `congestionado` juntos. En
una red urbana real el orden es el inverso, y una escala ordinal invertida indica
que una de sus categorías no mide lo que dice su nombre.

**El estado 3 no es congestión.** Tres evidencias independientes:

1. **Concentración.** Cinco tramos están en `3` el **100 %** del corpus —un único
   valor de `estado` en dieciséis días— y aportan 33.425 filas, el **80,7 %** de
   todo el estado 3. Otros dos (`296` y `20`) están al 53,4 % y aportan 7.146. En
   conjunto, **siete tramos son el 97,9 %** de las 41.444 filas.
2. **Ausencia de dinámica.** En 5,5 millones de observaciones hay **33 entradas**
   al estado 3. Dos al día en toda la ciudad. Y la matriz de transición da
   99,932 % de permanencia con **cero** transiciones de `3` a `1` o `2`: un corte
   de tráfico que se despeja pasa por congestionado y denso antes de fluir; este
   salta directo a `0` o no sale.
3. **Sin patrón horario.** El mapa de calor de `3` por día de la semana × hora
   local es plano: la misma proporción a las 4:00 del domingo que a las 8:00 del
   martes. La congestión real (`1` y `2`), en el mismo corpus, sí se enciende en
   las puntas de los laborables.

Los nombres cierran el caso. Los cinco permanentes son `PÉREZ GALDÓS DE LITERATO
GABRIEL MIRÓ A PECHINA` y cuatro `VÍA DE SERVICIO DE PÉREZ GALDÓS…` contiguas. Y
los dos del 53,4 % —`GIORGETA` y `PUENTE DE CAMPANAR HACIA PÉREZ GALDÓS`, mismo
corredor— pasan de `3` a `0` **en el mismo sondeo**, el 20/08/2026 a las 08:19
UTC. Es una obra terminando por fases, no tráfico.

Descontado el 3, la señal real de la capa son **841 filas** en estado `1` o `2`
sobre 2,75 millones, agrupadas en **111 episodios** en dieciséis días: siete
episodios de congestión al día en toda València.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_fuentes --senal-192
```

Reparto de `estado`, cobertura por tramo (`count(DISTINCT estado)` y presencia de
cada clase), tramos que alcanzan el 3 ordenados por permanencia, y conteo de
entradas a cada estado con la función de ventana `lag` de SQL particionada por
`idtramo`.

La ausencia de patrón horario y la matriz de transición se ven en
[02_trafico_estado.ipynb](../../notebooks/EDA/02_trafico_estado.ipynb), secciones
6 y 8, que dibujan `pct_congestion` y `pct_cortado` en mapas separados
precisamente para que la comparación sea visible.

Comprobación del instrumento: el denominador es 409 tramos con estado no nulo, no
410 ni 446. Las filas hueco de la trampa
[005](../../.claude/trampas/005-filas-hueco-capa-trafico.md) ya las descarta el
colector en ingesta (`df = df[df["idtramo"].notna()]`), así que no llegan a
`curated/` y no inflan el denominador aquí.

## Por qué importa

Dos consecuencias, de distinto orden.

**La inmediata es un bug esperando a ocurrir.** La lectura natural de la
documentación —`0` fluido, `1` denso, `2` congestionado, `3` cortado— lleva a
construir la feature `pct_no_fluido = estado >= 1`. Si se hace, el 97,9 % de la
masa de esa feature son siete tramos con valor constante durante todo el corpus.
El modelo no vería congestión: vería un indicador fijo de "este tramo es uno de
los siete de la obra de Pérez Galdós". Y si alguna línea de bus pasa por ese
corredor, la feature correlacionará con su retraso y **parecerá que la congestión
explica el retraso**, cuando lo que lo explica es una obra concreta de agosto de
2026. Sin excepción, sin número raro y con una conclusión falsa en la memoria.

**La de fondo es un límite del alcance.** La variable explicativa del TFM cubre
63 tramos, no 410, y produce siete episodios diarios en toda la ciudad. Eso
cambia cómo hay que usarla: el estado instantáneo de un tramo no sirve como
regresor —es constante para cuatro de cada cinco tramos—, y lo que puede servir
son agregados sobre ventanas temporales y sobre el subconjunto de tramos que
realmente varían.

Es también lo que reabre la capa 188 como candidata seria: su medida continua de
intensidad aporta justo lo que a la 192 le falta. Ver la entrada
[006](006-las-capas-de-trafico-no-unen-por-clave-pero-si-por-geometria.md).

## Qué se hizo / qué queda abierto

Hecho:

- La medición queda reejecutable en `src/project/analysis/medir_fuentes.py`.
- El notebook 02 dibuja `pct_congestion` y `pct_cortado` por separado, en el mapa
  horario y en el mapa espacial, para que nadie los vuelva a sumar por descuido.

Abierto:

- **No hay guardia.** El bug de sumar el `3` a una feature de congestión no lo
  impide nada todavía, porque `features.py` está vacío. Le corresponde una ficha
  en `.claude/trampas/`, y esta entrada se actualizará con su id en el campo
  `trampa:` cuando exista.
- **Los 16 días son de agosto.** Los 111 episodios de congestión pueden ser un
  suelo estacional: en periodo lectivo cabe esperar más. La cifra hay que
  remedirla si se amplía la captura, y hasta entonces se cita con su ventana.
- **No está comprobado si las líneas de bus pasan por los 63 tramos que varían.**
  Es la comprobación de viabilidad que corresponde a `analysis/diagnose.py`, y sin
  ella el número de 63 no dice todavía cuánta señal es utilizable.

## Para la memoria

> La capa de estado del tráfico del Ajuntament de València publica 410 tramos
> viarios con un estado categórico ordinal (fluido, denso, congestionado,
> cortado) refrescado cada cinco minutos. El análisis exploratorio del corpus
> capturado entre el 15 y el 31 de agosto de 2026 —2.754.220 registros en 6.685
> sondeos— revela que ese censo sobreestima considerablemente la información
> disponible: 77 tramos modifican su estado alguna vez durante el periodo y
> únicamente 63 llegan a registrar congestión, entendida como los estados denso o
> congestionado. Estos representan el 0,03 % de los registros, distribuidos en
> 111 episodios, aproximadamente siete diarios para el conjunto de la ciudad.
>
> El examen del estado "cortado", que con un 1,5 % de los registros resulta
> cincuenta veces más frecuente que la congestión propiamente dicha, muestra que
> no describe un fenómeno de tráfico. El 97,9 % de sus apariciones corresponde a
> siete tramos, cinco de los cuales permanecen en dicho estado durante la
> totalidad del periodo observado sin registrar ningún otro valor; los dos
> restantes transitan a estado fluido simultáneamente, en el mismo sondeo del 20
> de agosto. Todos ellos pertenecen al mismo corredor viario y cuatro son vías de
> servicio. La cadena de transiciones lo confirma: se contabilizan 33 entradas al
> estado cortado en todo el periodo, ninguna transición desde él hacia estados de
> congestión intermedia, y una distribución horaria y semanal plana, incompatible
> con un fenómeno de tráfico y consistente con obras de larga duración.
>
> De ello se derivan dos consecuencias metodológicas. La primera es que cualquier
> indicador agregado de congestión debe excluir el estado cortado, pues su
> inclusión introduciría una variable prácticamente constante asociada a siete
> emplazamientos concretos, susceptible de generar correlaciones espurias con el
> retraso de las líneas que los atraviesan. La segunda es que la cobertura
> efectiva de la variable explicativa es de 63 tramos y no de 410, lo que acota el
> alcance espacial del estudio y motiva la incorporación de la capa de intensidad
> de tráfico como fuente complementaria de medida continua.
