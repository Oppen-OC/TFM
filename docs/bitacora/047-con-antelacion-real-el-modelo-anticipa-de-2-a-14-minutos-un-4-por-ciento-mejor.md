---
id: 047
titulo: Con antelación real, de 2 a 14 minutos, el modelo mejora un 3-4 % a la persistencia más el sesgo del tramo, de 1,1 a 3,9 s; a una parada no anticipa nada, y la ganancia relativa no crece con el horizonte
fecha: 2026-10-08
tipo: medicion
capa: pipeline
capitulo: resultados
impacto: alto
estado: aceptado
evidencia: uv run dvc repro (metrics/eval.json y metrics/horizontes/h{2,3,5,10}/); uv run python -m project.analysis.antelacion (auditoria/resultados/antelacion.json); el diagnóstico por antelación real, con el comando de «Cómo se midió»
trampa: 017
---

## Qué se observó

Barrido de horizontes del ADR-023: un modelo por horizonte (1, 2, 3, 5 y 10
paradas), con la configuración del ADR-021, sobre la prueba del 21/09-04/10.
La población es la de las predicciones que aún sirven: horizonte previsto > 0
y último paso conocido del viaje (ADR-022). La comparación se hace contra la
persistencia más el sesgo del tramo del par (*i*, *i* + *h*).

**Sobre la cohorte común**, los mismos 236.930 orígenes (día, viaje, parada) en
todos los horizontes:

| *h* | horizonte previsto (p50) | listón | modelo | diferencia (IC por días) | relativa |
|---|---|---|---|---|---|
| 1 | 27 s | 26,02 s | 25,00 s | −1,03 [−1,12, −0,94] | −4,0 % |
| 2 | 2,0 min | 36,04 s | 34,98 s | −1,06 [−1,21, −0,93] | −2,9 % |
| 3 | 3,6 min | 45,02 s | 43,41 s | −1,61 [−1,91, −1,36] | −3,6 % |
| 5 | 6,7 min | 60,82 s | 58,78 s | −2,04 [−2,71, −1,52] | −3,4 % |
| 10 | 14,5 min | 93,05 s | 89,14 s | −3,91 [−5,16, −2,88] | −4,2 % |

**Cada horizonte con su población:** de −1,06 s (*h* = 1, 451.671 filas) a
−3,80 s (*h* = 10, 396.176 filas). En proporción, entre el −3,2 y el −4,2 %.
Contexto de esa misma tabla:
- El horario solo se queda entre 149 y 171 s de MAE.
- La persistencia sube de 36,6 a 110,9 s.
- La parte *nowcast* es del 46 % con *h* = 1 y de entre el 12 y el 17 % con
  *h* ≥ 2.

**A una parada, la mejora no es antelación.** Partiendo la población por la
antelación real, `t_obs(i+h) − t_disp(i)`: es diagnóstico, porque condiciona
por el resultado, y no sirve como población.

| *h* | filas | parte | diferencia (IC por días) | relativa |
|---|---|---|---|---|
| 1 | paso objetivo ya ocurrido | 30,8 % | −2,66 [−2,93, −2,38] | −11,2 % |
| 1 | más de 30 s de antelación real | 41,0 % | **+0,28 [0,11, 0,45]** | +0,8 % |
| 2 | más de 30 s de antelación real | 87,8 % | −1,24 [−1,39, −1,09] | −3,6 % |
| 10 | todas llegan a tiempo | 100 % | −3,80 [−4,86, −2,94] | −4,2 % |

## Cómo se midió

```bash
uv run dvc repro                                   # los cinco horizontes
uv run python -m project.analysis.antelacion       # por horizonte, cohorte común y estratos
```

El diagnóstico por antelación real:

```python
import pandas as pd
from project import evaluate, features, predict
r = features.salidas(None)  # 2, 10, ... para el resto
art = predict.cargar(r["modelo"])
t = pd.read_parquet(r["tabla"] / "test.parquet"); t = t[features.poblacion(t)]
y = t["retraso_siguiente_parada_s"]
e_m = predict.predecir(art, t) - y
e_b = features.predicciones_baseline(t)["persistencia_tramo"] - y
m = t["horizonte_util_s"] > 30
evaluate.diferencia(e_m[m], e_b[m], t["fecha_servicio"][m])
```

Estas cifras salen después de tres revisiones del tribunal. Por el camino se
corrigieron cinco cosas:
1. el instante en que se sabe un paso (k1+1);
2. la espera a la asignación del viaje;
3. el objetivo, que saltaba paradas no observadas;
4. el objetivo a varias paradas, que exigía haber visto las intermedias;
5. la población, que admitía pasos ya superados por otro conocido.

Las cuatro primeras inflaban la mejora; la quinta mezclaba poblaciones entre
horizontes.

## Por qué importa

- **Responde a «con cuánta antelación».** Con datos que llegan con 81 s de
  retraso, el modelo anticipa el retraso de 2 a 14 minutos por delante con un
  error un 3-4 % menor que la persistencia corregida con el sesgo del horario.
  En segundos, de 1,1 a 3,9.
- **A una parada no hay antelación útil:** cuando llega el dato, el bus suele
  estar ya en la parada siguiente, y donde no lo está, el modelo no mejora al
  listón.
- **La ganancia relativa no crece con el horizonte.** Lo que crece es el error
  de todos: el del listón pasa de 26 a 93 s. El modelo recorta una fracción
  constante.
- **Nada de esto mide la congestión.** Ningún horizonte usa la capa 192, y la
  flota como sensor aporta poco (bitácora 045). Lo que aquí se mide es el
  horario corregido más el estado del propio viaje y de la línea.

## Qué se hizo / qué queda abierto

Hecho:
- ADR-023 (barrido y cohorte común), las precisiones de los ADR-006 y ADR-022,
  `analysis/antelacion.py` y los mutantes 120-131.

Abierto:
- **La capa 192** de tráfico. Es el pilar 2 de la pregunta: cuánto del retraso
  se explica por la congestión aguas abajo.
- **El listón a horizontes largos** es débil, porque la persistencia se acerca
  al horario. Se ha decidido no endurecerlo por ahora, y se declara.
- **La configuración del ADR-021** se eligió con *h* = 1: no se ha buscado la
  mejor por horizonte.
- Las diferencias entre horizontes no tienen un intervalo pareado: solo cada
  horizonte frente a su listón.

## Para la memoria

> Para medir con cuánta antelación puede anticiparse el retraso, se entrenó y
> evaluó un modelo para cada horizonte de predicción, de una a diez paradas por
> delante, sobre las predicciones que todavía pueden ser útiles. La
> comparación se hizo sobre un mismo conjunto de 236.930 puntos de partida para
> todos los horizontes. Con un horizonte de una parada no se obtiene antelación
> útil: en la mayoría de los casos el retraso se conoce cuando el autobús ya se
> encuentra en la parada siguiente, y cuando no es así el modelo no mejora la
> referencia. Entre dos y catorce minutos de antelación, en cambio, el modelo
> reduce el error absoluto medio entre 1,1 y 3,9 s respecto a la persistencia
> corregida con el sesgo del horario por tramo (IC 95 % remuestreando días sin
> el cero en todos los horizontes). Es una mejora relativa estable, del 3-4 %:
> el error crece con el horizonte para todos los métodos, y el modelo recorta
> de él una fracción aproximadamente constante.
