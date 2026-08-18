# 05 · Hallazgos de la primera captura real

**Ventana:** 15/08/2026 22:15 → 16/08/2026 08:55 hora local (12,5 h).
**Volumen:** 1.284 sondeos de EMT, 65.053 posiciones, 76,7 MB en disco.

Todo lo que sigue está medido sobre datos propios. Es material directo para el
capítulo de calidad del dato de la memoria.

---

## 1. El servicio de la EMT alterna entre dos convenciones horarias

El hallazgo más importante, y el que habría arruinado el etiquetado sin dar la
cara.

El campo `fecha` de la capa de buses viene en epoch-ms, pero **no siempre en la
misma zona horaria**. Analizando la latencia (instante de ingesta menos
instante declarado) sobre 1.224 snapshots:

| Convención | Snapshots | Filas |
|---|---|---|
| Hora local de Madrid sellada como si fuera UTC | 979 (79 %) | 51.854 |
| UTC real | 267 (21 %) | 13.199 |

No es un cambio puntual: hay **338 alternancias en 12,5 horas**, con rachas de
mediana 2 snapshots. Es decir, cambia prácticamente de un sondeo al siguiente.
La explicación más probable es un balanceador con varios nodos detrás
configurados con zonas horarias distintas: según a cuál caiga la petición, el
sello es uno u otro.

**Consecuencia.** Fijar la conversión a una sola convención (que es lo que hacía
la primera versión del parser) deja el 20 % de las posiciones desplazadas
exactamente dos horas. Sobre una etiqueta de retraso construida por
interpolación del paso por parada, eso no produce ruido: produce **etiquetas
sistemáticamente falsas en una quinta parte del conjunto**, sin ningún síntoma
visible.

**Solución.** No asumir. Por cada snapshot se prueban las dos interpretaciones y
se elige la que produce una latencia plausible (`resolver_convencion` en
`demo/sources.py`). Efecto medido sobre los mismos payloads crudos:

| | p50 | p90 | p99 | máx | filas desplazadas > 1 h |
|---|---|---|---|---|---|
| Antes | 26 s | 7.222 s | 7.241 s | 7.348 s | 12.335 (20,3 %) |
| Después | 23 s | 39 s | 76 s | 477 s | **0** |

El método se autocalibra además en el cambio de hora de octubre, porque no
codifica el desfase: lo deduce.

> Esto se arregló **sin recapturar nada**, reprocesando los payloads crudos
> guardados en `data/raw/`. Es el argumento operativo de por qué la ingesta se
> separa del procesado, y el mismo que justifica Kafka en la memoria: capturar
> es irreversible, procesar es reintentable.

---

## 2. Latencia real de las fuentes

Una vez corregida la zona horaria:

| Fuente | p50 | p90 | máx |
|---|---|---|---|
| EMT buses | 23 s | 39 s | 477 s |
| Renfe Cercanías | 12 s | 18 s | 21 s |

Renfe es notablemente más consistente. Las capas de tráfico no publican
timestamp propio, así que su latencia real **sigue siendo desconocida** y hay
que declararlo como limitación: el sello temporal lo pone la ingesta.

---

## 3. Un 8 % de la capa de tráfico son filas hueco

De las 446 filas que devuelve la capa 192 en cada sondeo, unas 35 llegan **sin
`idtramo`, sin geometría y sin `estado`**. No son tramos con estado
desconocido: no son tramos. Contarlas como nulos inflaba artificialmente el
porcentaje de dato ausente. El parser ahora las descarta.

Tramos reales utilizables: **410**.

---

## 4. Cobertura espacial: 57,7 %

Primera respuesta medida a la pregunta 1 del diagnóstico, sobre las 65.053
posiciones reales:

| Umbral | Posiciones con tramo de tráfico cerca |
|---|---|
| ≤ 25 m | 54,2 % |
| ≤ 50 m | **57,7 %** |
| ≤ 100 m | 64,1 % |
| ≤ 200 m | 74,4 % |

La curva se aplana rápido: pasar de 25 a 200 metros solo gana 20 puntos. Eso
significa que **no es un problema de precisión del emparejamiento sino de
cobertura de la red**: hay calles por las que circulan buses donde
sencillamente no hay sensor de tráfico.

Por línea, **21 de 34 superan el 50 % de cobertura**:

- Mejor cubiertas: 93 (91 %), C3 (84 %), 98E (79 %), 99 (78 %), 81 (77 %)
- Peor cubiertas: 96 (11 %), 23 (20 %), 13 (25 %), 31 (25 %), 24 (28 %)

**Consecuencia para el alcance.** Refuerza la decisión de acotar a 4-6
corredores en lugar de modelar las 47 líneas. Los corredores candidatos salen
solos de esta tabla: 93, C3, 98E, 99 y 81 son los que tienen dato de tráfico
donde circulan. La cobertura deja de ser una limitación y pasa a ser un
**criterio objetivo y defendible de selección de la muestra**.

395 de los 410 tramos son alcanzados por algún bus, así que el problema es
asimétrico: sobra red de tráfico sin bus, no al revés.

---

## 5. Otros apuntes de calidad

- **Perfil diario** (buses simultáneos, hora local): 102 el sábado a las 22 h,
  mínimo de 27 a las 05 h, 68 a las 07 h y 121 a las 08 h del domingo. Coherente
  con el servicio nocturno reducido.
- **52 posiciones con `trayecto` nulo** (0,08 %), repartidas por muchas líneas.
- **Las posiciones fuera del área urbana no son error de GPS.** Las 1.364
  posiciones por debajo de 39,36° de latitud pertenecen a las líneas 25 y 24,
  que efectivamente bajan por la costa hacia El Perellonet. No filtrar por caja
  geográfica sin comprobar antes a qué línea pertenecen.
- **Deduplicación:** solo 28 snapshots repetidos de 1.265 (2,2 %) sondeando a
  30 s una fuente que refresca cada 29,3 s. Confirma que la cadencia está bien
  calibrada.
- **Renfe:** de 941 observaciones del núcleo 40, 379 (40 %) con retraso > 0;
  mediana 0 min, p90 3 min, máximo 7 min. Líneas C1, C2, C3, C5 y C6.
- **El deduplicador de Valenbisi no funciona**, porque `update_jcd` varía por
  estación y el máximo cambia siempre. No causa pérdida de datos, solo
  redundancia. Sin prioridad.

---

## 6. Crecimiento en disco

76,7 MB en 12,5 h → **~147 MB/día → ~13 GB en 90 días**.

El 74 % lo genera `raw/trafico_estado`, porque el payload crudo repite la
geometría completa de los 446 tramos en cada sondeo. Como esa geometría es
estática y ya está guardada en `reference/`, añadir `&returnGeometry=false` a
la consulta a partir del segundo sondeo reduciría esa fuente en torno a un 90 %,
dejando el total en ~2-3 GB. Pendiente de decidir: el crudo verbatim tiene valor
probatorio para la memoria.

---

## 7. Rendimiento a vigilar

`rastrear()` recorre los snapshots en Python y asigna celda a celda. Con 12,5 h
va sobrado; con 3 meses (unas 260.000 posiciones por semana) habrá que
vectorizarlo o pasarlo a DuckDB. No es urgente, pero está identificado.

---

## Qué falta para el go/no-go

Las preguntas 2, 3 y 4 del diagnóstico **siguen sin responder**: esta ventana es
casi toda noche de sábado a domingo, sin hora punta de laborable. La cobertura
(pregunta 1) ya está medida y no depende del día.

Repetir con una captura que incluya un lunes o martes de 07:00 a 10:00, y
entonces lanzar `python demo/diagnose.py`.
