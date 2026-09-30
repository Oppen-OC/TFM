# Selección de líneas, estrato de sensores, soporte por línea y criterio de mejora

_Diseño aprobado en conversación el 30/09/2026 y revisado el mismo día tras
interrogar el plan (`/grill-me`). Cierra el pendiente «selección de corredores»
de `docs/07_decisiones.md`._

## Problema

En agosto se propuso acotar el trabajo a 4-6 corredores (`docs/05`, sección 4)
por dos motivos: se temía que etiquetar las 47 líneas no diera tiempo, y solo
algunas líneas tienen sensores de tráfico cerca. El primero ya no existe: el
pipeline etiqueta todas las líneas. Los cinco corredores propuestos (93, C3, 98E,
99, 81) son el 22,8 % de las 1.506.078 filas de la tabla, y la 98E no aporta
ninguna; acotar tiraría tres cuartas partes del dato.

«Corredor» mezclaba tres decisiones distintas, que aquí se separan: qué líneas
entran en la muestra, qué papel tiene la cobertura de sensores y qué líneas
pueden informarse con cifra propia. Al interrogar el plan apareció una cuarta que
faltaba en todo el proyecto: qué cuenta como mejora.

## Decisiones

1. **Muestra.** Se entrena y se evalúa con todas las líneas etiquetadas. No se
   excluye ninguna.
2. **Sensores.** La cobertura de sensores de tráfico define un **estrato de
   evaluación**, no recorta la muestra.
3. **Soporte.** Una línea tiene cifra propia en los resultados si reúne al menos
   **100 viajes en 3 días de servicio distintos** en la prueba y al menos 100
   viajes en entrenamiento. Las demás no se tiran: cuentan en la métrica global
   y se informan agrupadas.
4. **Criterio de mejora.** Toda comparación —modelo contra persistencia, modelo
   con tráfico contra modelo sin él— se informa como **diferencia sobre los
   mismos viajes, con su intervalo del 95 %** remuestreando viajes. Hay mejora si
   el intervalo no contiene el cero; si lo contiene, el resultado es «no se
   distingue». No se fija un mínimo de magnitud: se informa el tamaño del efecto.
5. **Dónde se juzga el tráfico.** En el conjunto y en el estrato con sensor, no
   línea a línea. Las cifras por línea se enseñan con su intervalo, como
   descripción.

Nunca se excluye una línea por el error del modelo ni por su cobertura de
sensores.

## La exclusión que se consideró y se descartó

La primera versión de este diseño sacaba de la tabla las líneas con menos del
40 % de sus posiciones en viajes asignados: la 25 (17,7 %), la 63 (29,0 %) y la
73 (14,3 %). Se descartó por cuatro medidas:

- **La regla de soporte ya las aparta de las cifras por línea.** La 25 tiene 42
  viajes en la prueba y cae en «poco soporte»; la 63 y la 73 no tienen ninguno en
  entrenamiento y caen en «sin entrenamiento».
- **Excluirlas solo movía el resultado global 0,08 s** (la persistencia, de 37,62
  a 37,54 s de MAE).
- **Lo que sí se etiqueta de ellas no es peor.** El margen del viaje asignado
  sobre el segundo candidato, en su percentil 10, es de 449 s en la 25 y 534 s en
  la 63, frente a 372 s de mediana en las demás líneas.
- **El umbral no caía en el hueco natural.** El hueco mayor está entre la 24
  (46,4 %) y la siguiente línea con volumen (70 %): un criterio de hueco sacaba
  también la 24.

A cambio, la exclusión obligaba a defender un umbral elegido después de ver los
datos y un sesgo a favor de la hipótesis, porque la 25 es la línea peor cubierta
por sensores (27 %, `docs/10`).

El indicador se publica igualmente, por línea, como limitación declarada:

| línea | posiciones válidas | en viajes asignados |
|---|---|---|
| 96, 98E, 100, 8 | 78.387 | 0 % (sin trazado u horario en el GTFS; no tienen filas) |
| 73 | 15.396 | 14,3 % |
| 25 | 206.710 | 17,7 % |
| 63 | 35.823 | 29,0 % |
| 24 | 140.297 | 46,4 % |
| 14 | 839 | 57,1 % |
| las otras 38 | | 70,0 - 92,4 % |

## Lo que mide el umbral de soporte

Semiancho del intervalo del 95 %, mediana entre las líneas de cada banda,
remuestreando viajes en la prueba actual (5 días):

| viajes en la prueba | del MAE de la persistencia | de la diferencia con un modelo parecido | con un modelo muy distinto |
|---|---|---|---|
| menos de 100 | 3,2 s | 2,7 s | 16,6 s |
| de 100 a 299 | 1,6 s | 0,9 s | 6,3 s |
| 300 o más | 1,0 s | 0,6 s | 3,8 s |

El «parecido» es la persistencia encogida un 10 %; el «muy distinto», la
persistencia encogida a la mitad. Son
sustitutos: todavía no hay modelo.

Por línea, con 100 a 299 viajes, no se distingue una mejora de menos de 1-2 s si
el modelo se parece a la persistencia, ni de menos de unos 6 s si se aleja. El
efecto del tráfico será menor (bitácora 032): de ahí la decisión 5.

## Cambios en el código

### `params.yaml → features`

```yaml
  # Soporte para informar una línea con cifra propia: viajes y días de servicio
  # en la prueba, y los mismos viajes en entrenamiento. Por debajo se informa
  # agrupada, no se tira (ADR-018).
  linea_min_viajes: 100
  linea_min_dias: 3
```

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

Vive junto a la función de los baselines porque la usa el stage `features` hoy y
la usará la evaluación del modelo cuando exista.

### Baselines y `metrics/features.json`

`baselines_test.por_linea[<línea>]` gana `viajes`, `dias` y `grupo`. Aparece
`baselines_test.por_grupo`, con horario y persistencia de los tres grupos.

### Medidor `medir_rutas lineas`

Columna nueva `pos_asignadas`: posiciones de los tramos con
`motivo == "asignado"` entre las de los tramos con `motivo != "excluido"`.

### Medidor nuevo: `medir_soporte`, en `src/project/analysis/`

Por línea de la prueba: viajes, días, grupo, el MAE de la persistencia y los
semianchos de la tabla de arriba, remuestreando viajes enteros con semilla fija.

## Pruebas

En `tests/test_features.py`, con datos sintéticos:

1. El soporte se cuenta en viajes y días: 100 viajes en 3 días es `propia`; 99
   viajes, 100 en 2 días o menos de 100 en entrenamiento, `poco_soporte`; sin
   entrenamiento, `sin_entrenamiento`. El mismo `viaje_id` en días distintos son
   viajes distintos. Una línea solo de entrenamiento no aparece. Una prueba vacía
   devuelve una tabla vacía.
2. Los baselines traen el soporte por línea y los tres grupos, y son
   serializables.

Un mutante por cada guardia en `auditoria/catalogo.toml` (ADR-011): no exigir
días distintos, y contar filas en vez de viajes.

## Qué invalida

Solo el stage `features`, y solo `metrics/features.json`: la tabla no cambia ni
en una fila. Es la comprobación de que el cambio no toca la muestra.

## Qué queda escrito

- **ADR-018** en `docs/07_decisiones.md`, revisable, con las cinco decisiones y
  la exclusión descartada.
- **Bitácora 036**: el indicador por línea, la tabla de soporte y los grupos.
- **`CLAUDE.md`**, sección Pipeline ML: una línea que apunte a ADR-018.
- **«Pendientes de decidir»**: sale «selección de corredores» y entra «cobertura
  de sensores por tramo».

## Fuera de este trabajo

- El estrato de sensores en sí: necesita medir la cobertura por tramo entre
  paradas y llega con la capa 192 en `features.py`.
- El intervalo de la diferencia dentro del pipeline: llega con la evaluación del
  modelo. Aquí solo se mide con sustitutos, en el medidor.
- Cómo se codifica `linea` para que el modelo pueda predecir líneas que no ha
  visto: se decide al escribir el entrenamiento.
- Rehacer el corte entre entrenamiento y prueba con la captura posterior al
  18/09. Las cifras de este trabajo son las de las 32 jornadas actuales.

## Qué reabriría cada decisión

- **Muestra:** que el modelo, medido con y sin las líneas de indicador bajo, dé
  resultados distintos más allá de su intervalo.
- **Estrato:** que, medido, solo aporte ruido.
- **Soporte:** que con la captura completa casi ninguna línea quede por debajo.
- **Criterio de mejora:** que el tutor pida un mínimo de magnitud.
