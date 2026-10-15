---
id: 055
titulo: El clasificador de más de 5 min suma unos 5 min al dvc repro de la prueba. Entrenar los cinco horizontes lleva 126 s (18-31 s cada uno) y evaluarlos 176 s (33-38 s), medidos uno detrás de otro sobre las tablas del corte antiguo. Las dos primeras cifras que se dieron, 47 s y 66 s a h = 1, eran del vigilante, que sondeaba cada 20 s
fecha: 2026-10-15
tipo: medicion
capa: pipeline
capitulo: metodologia
impacto: bajo
estado: aceptado
evidencia: uv run python -m project.train [--horizonte H] --clasificador y uv run python -m project.evaluate [--horizonte H] --clasificador, cronometrados con date +%s%N, uno detrás de otro, sobre data/processed/ del corte antiguo (11/10)
trampa: —
---

## Qué se observó

El ensayo del plan del clasificador (ADR-025, tarea 6) tenía que dar cuánto
tarda un entrenamiento, para saber cuánto alarga el `dvc repro` del 21/10.
Cronometrado proceso a proceso, sin nada más corriendo, en el PC (24 hilos):

| h | entrenar | evaluar | árboles | filas de la tabla de entrenamiento |
|---|---|---|---|---|
| 1 | 20,2 s | 35,0 s | 148 | 1.516.264 |
| 2 | 31,4 s | 35,6 s | 154 | 1.437.615 |
| 3 | 29,2 s | 38,5 s | 117 | 1.361.683 |
| 5 | 27,2 s | 33,8 s | 115 | 1.214.738 |
| 10 | 18,2 s | 32,7 s | 78 | 873.387 |
| **total** | **126,0 s** | **175,5 s** | | |

- Son tiempos de reloj de cada proceso entero: arranque de `uv`, lectura del
  parquet, ajuste y reajuste, registro en MLflow y escritura del artefacto.
- Las filas son las de `train.parquet` antes de filtrar la población.
- El tiempo de entrenamiento sigue al número de árboles más que al de filas:
  h = 2 es el más lento con 154 árboles; h = 10, el más rápido con 78.
- En frío, la primera ejecución del 14/10 tardó **37 s** en entrenar h = 1 y
  **48 s** en evaluarlo, contados por la hora de escritura del artefacto y de
  los logs. La diferencia con los 20 s es el arranque en frío: imports, caché
  de disco y la creación del experimento de MLflow.

## Cómo se midió

Un bucle de bash que, para h = 1, 2, 3, 5 y 10, lanza el entrenamiento y la
evaluación del clasificador uno detrás de otro y cronometra cada proceso con
`date +%s%N`. Las tablas son las de `data/processed/` del corte antiguo: el
entrenamiento llega al 20/09, y la «prueba», del 21/09 al 04/10, ya es
entrenamiento con el corte del ADR-024. Nada toca la prueba del 07-19/10 ni
ejecuta DVC. No se leyó ninguna métrica. Después se borraron los artefactos y
los 15 runs de MLflow de las mediciones. Antes de la siguiente medida se
comprobó que no quedaba ningún proceso de entrenamiento ni de evaluación vivo.

```bash
for h in 1 2 3 5 10; do
  arg=""; [ "$h" != 1 ] && arg="--horizonte $h"
  for paso in train evaluate; do
    t0=$(date +%s%N)
    uv run python -m project.$paso $arg --clasificador > /dev/null 2> medir_${paso}_h$h.err
    echo "h=$h $paso rc=$? $(( ($(date +%s%N) - t0) / 1000000 )) ms"
  done
done
# Limpieza: borrar los runs de MLflow del experimento retraso_mas_de_5min y
# models/**/model_clasificador.pkl, metrics/**/clasificador.json.
```

El instrumento mintió dos veces antes de esta tabla:

1. **El vigilante.** El ensayo del 14/10 marcaba el fin del proceso con un
   bucle que miraba cada 20 s si seguía vivo, y dio **47 s** y **66 s**. La
   hora de escritura del `.pkl` (22:13:42) y la del log de la evaluación
   (22:14:54) los dejan en **37** y **48 s**. El vigilante sumaba hasta un
   periodo de sondeo entero.
2. **Dos mediciones a la vez.** Un primer bucle se paró a mano porque no había
   `bc` para restar los tiempos. Pero parar la tarea solo mató el `tee` de la
   tubería: el bucle siguió lanzando procesos en paralelo con el segundo. Ese
   segundo bucle dio de 21 a 39 s por entrenamiento y hasta 60 s por
   evaluación, hasta un **70 % más** que la tabla de arriba, porque los dos
   competían por la CPU. Se descartó entero y se repitió con la máquina libre.

## Por qué importa

- La fase B del plan del ADR-024 añade al mismo `dvc repro` los cinco
  clasificadores y sus cinco evaluaciones. Con estas cifras son unos **5 min**
  más, y no cambian la planificación del 21/10. Las tablas nuevas tendrán unas
  dos semanas más de entrenamiento: debería tardar algo más, no un orden de
  magnitud más.
- La evaluación tarda más que el entrenamiento: hasta 54.000 réplicas por
  horizonte (9 estratos: titular, conjunto, 5 bandas y 2 estados actuales; 3
  listones, 2 unidades de remuestreo y 1.000 réplicas cada uno). La prueba
  nueva tiene 13 días frente a los 14 de la antigua: el tiempo será parecido.

## Qué se hizo / qué queda abierto

- Aceptado. Por cinco horizontes, el clasificador cuesta minutos y no pide
  ningún cambio en el plan de la fase B.
- Corregida la cifra que se dio al cerrar el plan, 47 s, que salía del
  vigilante.
- Abierto: el 21/10, el `dvc repro` da la duración real con las tablas nuevas.
  Si se aparta mucho de esta tabla, hay que mirar por qué.

## Para la memoria

> El clasificador de retrasos de más de cinco minutos añade un coste de cómputo
> marginal al pipeline. Sobre las tablas del corte previo a la prueba, de entre
> 0,87 y 1,52 millones de filas según el horizonte, su entrenamiento con parada
> temprana y reajuste tarda entre 18 y 31 s por horizonte, y su evaluación con
> remuestreo por viajes y por días, entre 33 y 38 s. Para los cinco horizontes
> suman unos cinco minutos. El tiempo de entrenamiento sigue al número de
> árboles que fija la parada temprana (de 78 a 154) más que al tamaño de la
> tabla. La medida exigió dos correcciones del instrumento. Un vigilante que
> sondeaba cada 20 s sobrestimaba la duración en hasta un periodo de sondeo. Y
> una segunda medición que corrió en paralelo con otra inflaba los tiempos hasta
> un 70 %. Las cifras que se dan proceden de ejecuciones secuenciales con la
> máquina libre.
