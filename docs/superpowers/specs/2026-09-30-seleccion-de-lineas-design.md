# Selección de líneas, estrato de sensores y soporte mínimo por línea

_Diseño aprobado en conversación el 30/09/2026. Cierra el pendiente «selección de
corredores» de `docs/07_decisiones.md`._

## Problema

En agosto se propuso acotar el trabajo a 4-6 corredores (`docs/05`, sección 4)
por dos motivos: se temía que etiquetar las 47 líneas no diera tiempo, y solo
algunas líneas tienen sensores de tráfico cerca. El primero ya no existe: el
pipeline etiqueta todas las líneas. Los cinco corredores propuestos (93, C3, 98,
99, 81) son el 24,5 % de las 1.506.078 filas de la tabla; acotar tiraría tres
cuartas partes del dato.

«Corredor» mezclaba tres decisiones distintas, que aquí se separan: qué líneas
entran en la muestra, qué papel tiene la cobertura de sensores y qué líneas
pueden informarse con cifra propia.

## Decisiones

1. **Muestra.** Se entrena y se evalúa con todas las líneas etiquetadas menos las
   que no pasan el criterio de calidad de la etiqueta.
2. **Criterio de exclusión.** Queda fuera la línea con menos del **40 %** de sus
   posiciones en viajes asignados, contando solo los días no excluidos. El
   criterio es sobre la etiqueta. Nunca se excluye una línea por el error del
   modelo ni por su cobertura de sensores.
3. **Sensores.** La cobertura de sensores de tráfico define un **estrato de
   evaluación**, no recorta la muestra. Lo que aporte la capa 192 se informa
   dentro del estrato con sensor.
4. **Soporte.** Una línea tiene cifra propia en los resultados si reúne al menos
   **100 viajes en 3 días de servicio distintos** en la prueba y al menos 100
   viajes en entrenamiento. Las demás no se tiran: cuentan en la métrica global
   y se informan agrupadas.

Todas son revisables; las condiciones están al final.

## El criterio, medido

Indicador por línea, sobre `data/interim/viajes`: posiciones de los tramos con
`motivo == "asignado"` entre las posiciones de todos los tramos con
`motivo != "excluido"`.

| línea | posiciones válidas | en viajes asignados | |
|---|---|---|---|
| 96, 98E, 100, 8 | 78.387 | 0 % | sin trazado u horario en el GTFS |
| 73 | 15.396 | **14,3 %** | fuera |
| 25 | 206.710 | **17,7 %** | fuera |
| 63 | 35.823 | **29,0 %** | fuera |
| 24 | 140.297 | 46,4 % | dentro, señalada como dudosa |
| 14 | 839 | 57,1 % | dentro |
| las otras 38 | | 70,0 - 92,4 % | dentro |

El umbral del 40 % cae en el hueco entre la 63 y la 24.

**Aplicado de forma uniforme, el criterio excluye tres líneas: 25, 63 y 73.** En
la conversación solo se habló de la 25; la 63 y la 73 no tienen filas de
entrenamiento y habrían caído en el grupo «sin entrenamiento», pero dejarlas
dentro con un indicador peor que el de la línea excluida no sería defendible.
Filas que salen de la tabla: 7.932 de la 25, 1.524 de la 63 y 567 de la 73, el
0,67 % del total.

Las cuatro líneas sin etiqueta ya están fuera por construcción: 117.715 de
10.457.901 posiciones, el 1,1 %.

**Lo que hay que declarar en la defensa.** La 25 es también la línea peor
cubierta por sensores (27 %, `docs/10`). Excluirla por la calidad de su etiqueta
favorece de rebote a la hipótesis de la fusión con tráfico. Se declara, y se
acompaña del error del modelo base con y sin ella.

## Cambios en el código

### `params.yaml → features`

```yaml
  # Líneas fuera de la tabla por calidad de la etiqueta: menos del 40 % de sus
  # posiciones en viajes asignados (ADR-018, bitácora 036). Lista explícita, no
  # regla automática: que una línea entre o salga es una decisión, no un efecto
  # de reejecutar. Comprobar con `medir_rutas lineas`.
  excluir_lineas: ["25", "63", "73"]
  linea_min_viajes: 100     # soporte para informar una línea con cifra propia
  linea_min_dias: 3
```

### `features.construir`

Parámetro nuevo `excluir_lineas: tuple[str, ...] = ()`. Las filas de esas líneas
se quitan **al final**, junto al filtro de filas sin objetivo, cuando las
variables ya están calculadas.

Supuesto: los viajes etiquetados de una línea excluida siguen contando como
sensor para las demás (`tramo_ganado_*`, `bus_anterior_*` solo mira la propia
línea y no le afecta). Sus etiquetas son correctas; lo que falla es que son
pocas y no son una muestra al azar de la línea.

### `features.soporte_por_linea`

```python
def soporte_por_linea(train, test, min_viajes=100, min_dias=3) -> pd.DataFrame
```

Una fila por línea presente en `test`, con `viajes` y `dias` de la prueba,
`viajes_train` y `grupo`:

- `sin_entrenamiento`: ningún viaje en `train`;
- `propia`: `viajes >= min_viajes`, `dias >= min_dias` y `viajes_train >= min_viajes`;
- `poco_soporte`: el resto.

Un viaje es un par (`fecha_servicio`, `viaje_id`) distinto. Se cuenta en viajes y
no en filas porque las paradas de un mismo viaje están correlacionadas.

Vive junto a `baselines()` porque la usa el stage `features` hoy y la usará
`evaluate.py` cuando exista.

### `features.baselines` y `metrics/features.json`

`baselines_test.por_linea[<línea>]` gana `viajes`, `dias` y `grupo`. Aparece
`baselines_test.por_grupo`, con horario y persistencia de los tres grupos.

### `analysis/medir_rutas.py lineas`

Columna nueva `pos_asignadas`: el indicador de arriba. Es el comando que
reproduce el criterio.

### `analysis/medir_soporte.py` (nuevo)

Por línea de la prueba: viajes, días y el semiancho del intervalo del 95 % del
MAE de la persistencia, remuestreando viajes enteros con semilla fija. Es la
tabla que justifica el umbral de 100.

## Pruebas

En `tests/test_features.py`, con pasos sintéticos como los existentes:

1. La línea excluida no tiene ninguna fila en la tabla.
2. La línea excluida sigue contando como sensor: el `tramo_ganado` de otra línea
   que comparte el tramo no cambia al excluirla.
3. `soporte_por_linea`: 100 viajes en 3 días es `propia`; 99 viajes, o 100 en 2
   días, es `poco_soporte`; sin viajes en `train` es `sin_entrenamiento`.

Un mutante por cada uno en `auditoria/catalogo.toml` (ADR-011): quitar el filtro,
aplicarlo a la entrada en vez de al final, y relajar el umbral.

## Qué invalida

Solo el stage `features`: `train.parquet`, `test.parquet` y
`metrics/features.json`. `curar` y `prepare` no se tocan. Se reejecuta con
`uv run dvc repro features`.

## Qué queda escrito

- **ADR-018** en `docs/07_decisiones.md`, revisable, con las cuatro decisiones.
- **Bitácora 036**: el indicador por línea y la tabla de soporte.
- **`CLAUDE.md`**, sección Pipeline ML: una línea que apunte a ADR-018, para que
  toda sesión la tenga en contexto.
- **«Pendientes de decidir»**: sale «selección de corredores» y entra «cobertura
  de sensores por tramo».

## Fuera de este trabajo

- El estrato de sensores en sí: necesita medir la cobertura por tramo entre
  paradas (hoy solo está por posición: 69,4 % a menos de 50 m) y llega con la
  capa 192 en `features.py`.
- Los intervalos de confianza dentro del pipeline: llegan con `evaluate.py`.
- Las líneas de caso para las figuras de la memoria y el demostrador.
- La 24: no lleva marca en código. Tiene cifra propia, y la nota de «dudosa» va
  en el ADR y en la memoria.

## Qué reabriría cada decisión

- **Exclusión:** que el indicador de una línea excluida supere el 40 %, o que el
  de una incluida baje de ahí, al reprocesar con más captura o con un tracker
  mejor.
- **Estrato:** que, medido, solo aporte ruido.
- **Soporte:** que con la captura completa casi ninguna línea quede por debajo;
  entonces el umbral sobra o puede subirse.
