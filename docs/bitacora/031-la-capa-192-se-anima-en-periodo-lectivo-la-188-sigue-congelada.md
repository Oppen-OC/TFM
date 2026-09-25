---
id: 031
titulo: En periodo lectivo la capa 192 declara congestión con perfil de hora punta (34 tramos por laborable y 42 horas-tramo, ×11 frente a agosto); la 188 sigue congelada, con los mismos 243 valores los 32 días
fecha: 2026-09-25
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: alto
estado: abierto
evidencia: uv run python -m project.analysis.medir_fuentes --lectivo
trampa: —
---

## Qué se observó

El veredicto de `docs/06_veredicto_capas_trafico.md` («las dos capas de tráfico
son estáticas») salía de 42 horas de agosto. El tutor condicionó la formulación
del TFM a una comprobación en periodo lectivo (`docs/10_respuestas_tutor.md`,
§2). Con la captura hasta el 18/09:

**Capa 192 (estado), por día laborable, estados 1-2:**

| | tramos que llegan a congestión | pico de tramos a la vez | horas-tramo de congestión |
|---|---|---|---|
| antes del 08/09, mediana | 8,5 | 4 | 3,7 |
| desde el 08/09 (lectivo), mediana | **34** | **15,5** | **42,3** |

La subida empieza con la vuelta al trabajo: 13 tramos el 31/08, 23 el 01/09,
44 el 04/09 y 52 el 17/09 (40 a la vez).

**Tiene la forma del tráfico.** Tramos congestionados de media por hora, en
laborables:

| hora | 7 | 8 | 9 | 10 | 15 | 18 | 22-6 |
|---|---|---|---|---|---|---|---|
| antes del 08/09 | 0,5 | 1,3 | 0,7 | 0,2 | 2,1 | 2,3 | ~0 |
| lectivo | 4,2 | **17,4** | 6,4 | 1,4 | 5,1 | **6,9** | ~0 |

**El estado 4 es un fallo del servicio, no tráfico:** aparece en toda la capa a
la vez, en 402 tramos el 05/09 entre las 9 y las 10 h (12 sondeos) y en 395 el
17/09 a las 16 h (1 sondeo). La medida lo excluye.

**Capa 188 (intensidad): congelada.** Los 32 días tienen exactamente los mismos
243 valores distintos en 354 puntos, con una media de 1.079 veh/h.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_fuentes --lectivo
```

Por día local, desde `data/curated/source=trafico_estado`:

- tramos distintos en estado 1 o 2;
- máximo de tramos en 1-2 dentro de un mismo sondeo;
- suma de tramos en 1-2 por sondeo, dividida entre los sondeos por hora del día.

Esto último evita inflar los días parciales (el 10, el 14 y el 18/09).
«Lectivo» se toma desde el 08/09. El perfil horario promedia, sobre todos los
laborables de cada periodo, la fracción de filas en 1-2, multiplicada por 410.

**El instrumento se corrigió antes de la cifra.** Un primer recuento de «tramos
que cambian de estado en el día» daba unos 400 tramos el 05/09 y el 17/09, y
mezclaba los fallos de estado 4 con el tráfico. Sin mirar el perfil horario,
llevó a declarar la capa «casi plana», y era falso.

## Por qué importa

- **El veredicto del documento 06 vale para la 188 y para agosto, no para la
  192 en periodo lectivo.** Es el caso que el tutor dejó previsto: «si las capas
  se animan, el enfoque 1 recupera valor».
- **Desplazamiento de covariables en el split de la bitácora 030.** El
  entrenamiento es sobre todo de agosto (16 de 19 días), cuando la capa apenas
  declara congestión; la prueba (14-18/09) es lectiva. Una variable de la 192
  llegaría al modelo casi constante en entrenamiento y viva en prueba. Lo mismo,
  en menor grado, para cualquier variable de congestión medida por la flota.
- La 192 sigue sin timestamp propio (bitácora 004) y solo publica estados
  discretos.

## Qué se hizo / qué queda abierto

Hecho: la medida `medir_fuentes --lectivo`.

Abierto:

- Confirmar con la captura de octubre, como pedía el documento 10.
- Cuánto de la congestión declarada cae sobre el viario de las líneas: la
  cobertura espacial de la bitácora 004 se midió en agosto.
- Revisar el corte de la bitácora 030: para que una variable de congestión
  pueda aprenderse, el entrenamiento tiene que incluir días lectivos.
- Actualizar `docs/06_veredicto_capas_trafico.md` con esta medida: gana el
  dato.

## Para la memoria

> El registro municipal del estado del tráfico, que durante agosto se comportaba
> como un inventario de obras e incidencias, comienza a declarar congestión con la
> vuelta a la actividad en septiembre. En los días laborables de periodo lectivo,
> una mediana de 34 tramos alcanza estados de tráfico denso o congestionado, con
> hasta 40 simultáneos y un perfil horario con máximos a las 8 y a las 18 horas,
> frente a 8,5 tramos en los laborables anteriores al 8 de septiembre. La capa de
> intensidad, en cambio, publica exactamente los mismos valores durante los 32
> días observados. La primera capa es, por tanto, utilizable como variable
> explicativa en periodo lectivo, y la segunda no lo es en ningún periodo.
