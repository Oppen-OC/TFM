---
id: 004
titulo: La fusión buses × tráfico es viable con 124 s de desfase mediano, pero esa cifra es un suelo: las capas de tráfico no publican timestamp propio
fecha: 2026-09-01
tipo: medicion
capa: fuentes
capitulo: metodologia
impacto: alto
estado: aceptado
evidencia: uv run python -m project.analysis.medir_fuentes --solape
trampa: —
---

## Qué se observó

La condición de viabilidad del TFM —que las posiciones de la flota y el estado
del tráfico coincidan en el tiempo— **se cumple**. Sobre los 40.943 sondeos de
`emt_buses` del corpus (15/08–31/08 de 2026), la antigüedad de la última medida
de tráfico disponible en el instante de cada sondeo es:

| métrica | valor |
|---|---|
| sondeos de bus | 40.943 |
| sin tráfico previo | 1 |
| mediana | **124 s** |
| p95 | 284 s |
| máximo | 54.675 s (15,2 h) |
| por debajo de 5 min | **99,6 %** |

La distribución es casi uniforme entre 0 y 300 s, que es exactamente lo que cabe
esperar de una capa refrescada cada 5 minutos leída por otra que va a 30 s.

**La cifra que importa no es la mediana, es lo que la mediana no mide.** Las dos
capas de tráfico no publican timestamp propio: el colector escribe
`ts_utc = ts_ingest_utc` (`src/project/ingest/sources.py`, `parse_trafico_estado`
y `parse_trafico_intensidad`). Se comprueba en el agregado de latencias del
notebook 00, donde `trafico_estado` y `trafico_intensidad` dan mediana, p95,
mínimo y máximo **exactamente 0**, frente a los 25 s de `emt_buses` o los 10 s de
`renfe_cercanias`.

Los 124 s son, por tanto, la antigüedad de la **captura**, no la de la **medida**.
El desfase real de alineación es 124 s más una cantidad desconocida: lo que la
capa 192 tardara en calcular y publicar el estado antes de que nosotros lo
leyéramos.

El máximo de 15,2 h tampoco es una anomalía suelta: es la parada del colector del
18/08, que aparece a la vez en las cuatro capas municipales. Durante un hueco, el
último tráfico conocido envejece tanto como dure el hueco.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_fuentes --solape
```

`ASOF LEFT JOIN` de DuckDB sobre los `ts_ingest_utc` distintos de ambas fuentes:
para cada sondeo de buses, el sondeo de tráfico más reciente que no sea
posterior. Se usa `ts_ingest_utc` —el reloj del colector— y no `ts_utc`, porque en
la EMT este último alterna de convención (trampa
[002](../../.claude/trampas/002-emt-alterna-convencion-horaria.md)) y en tráfico
es el reloj del colector de todas formas.

La ausencia de timestamp propio en las capas de tráfico se verifica en el código
(`parse_trafico_estado` asigna `df["ts_utc"] = ts_ingest`) y en el dato (latencia
idénticamente cero en el notebook 00, sección 5).

Deriva del notebook [00_panorama_general.ipynb](../../notebooks/EDA/00_panorama_general.ipynb),
secciones 5 y 6.

## Por qué importa

Es la pregunta que decidía si el TFM se podía hacer. La respuesta es que sí, y
esa es la mitad buena.

La mitad incómoda es que **el error de alineación no está acotado por arriba**, y
hay que declararlo en vez de dejarlo implícito. Un lector que vea "124 s de
mediana" entenderá que la feature de congestión describe el tráfico de hace dos
minutos. Lo cierto es que describe el tráfico de hace dos minutos *más* el tiempo
de cálculo de la fuente, que no podemos medir porque la fuente no lo dice. Nada
de lo que se construya aguas abajo puede prometer resolución temporal más fina
que eso.

Aguas abajo, en `prepare.py`, la consecuencia es concreta: hace falta una
**política explícita de caducidad**. Arrastrar el último valor conocido de
tráfico sin límite significa que, durante la parada de 15 horas del 18/08, cada
posición de bus recibiría un estado de tráfico de hasta 15 horas antes, con
aspecto de dato válido y sin ninguna marca que lo distinga de uno fresco. El
número de filas afectadas es pequeño; el problema es que son indistinguibles.

## Qué se hizo / qué queda abierto

Hecho:

- La medición queda reejecutable en `src/project/analysis/medir_fuentes.py`.
- Los notebooks separan explícitamente el desfase de captura del de medida, para
  que la cifra no se cite sin su matiz.

Abierto:

- **La latencia real de las capas de tráfico no es medible con lo que hay.**
  Solo se podría acotar comparando contra otra fuente de congestión con reloj
  propio, que hoy no tenemos.
- **`prepare.py` no existe todavía**, así que la política de caducidad está
  decidida pero no implementada. Cuando se escriba, la guardia natural es un test
  que compruebe que ninguna fila del conjunto final lleva una medida de tráfico
  más antigua que el umbral declarado.
- **El corpus son 16 días de agosto.** Agosto en València no es un mes de tráfico
  representativo, y la cadencia de la fuente podría variar en periodo lectivo.

## Para la memoria

> La fusión de ambas fuentes exige verificar previamente que sus series
> temporales se solapan con una resolución suficiente. Sobre el corpus capturado
> entre el 15 y el 31 de agosto de 2026, se determinó para cada uno de los 40.943
> sondeos de posiciones la antigüedad de la observación de tráfico más reciente
> disponible en ese instante, mediante una unión temporal asimétrica. La
> antigüedad mediana resultó de 124 segundos, con un percentil 95 de 284 y un
> 99,6 % de los sondeos por debajo de los cinco minutos, valores coherentes con
> el refresco quinquenal de la capa municipal frente al de treinta segundos de la
> capa de seguimiento de la flota. La condición de viabilidad se considera, por
> tanto, satisfecha.
>
> Conviene precisar el alcance de esa cifra. Las capas de tráfico del
> Ajuntament no publican marca temporal propia, de modo que el instante asociado
> a cada observación es el de su captura y no el de su medición. Los 124 segundos
> constituyen así una cota inferior del desfase real de alineación, al que hay
> que sumar el tiempo —desconocido— transcurrido entre el cálculo del estado por
> parte de la fuente y su publicación. En consecuencia, ninguna afirmación sobre
> la antelación con que el modelo anticipa el retraso puede sostenerse con
> resolución más fina que ese límite, y así se recoge en las limitaciones del
> trabajo.
