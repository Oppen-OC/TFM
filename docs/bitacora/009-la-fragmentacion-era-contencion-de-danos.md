---
id: 009
titulo: La fragmentación de trayectorias estaba conteniendo el daño de los intercambios de identidad; eliminarla dobla la cola contaminada sin añadir un solo salto
fecha: 2026-09-16
tipo: medicion
capa: tracking
capitulo: metodologia
impacto: alto
estado: abierto
evidencia: PYTHONPATH=$SB uv run python $SB/giro_real.py
trampa: 007
---

## Qué se observó

Al evaluar el arreglo que agrupa por `linea` en vez de por `(linea, trayecto)`,
sobre flota simulada con verdad-terreno y con los dos sentidos **solapados a 200
m** —que es como circulan en la calle, uno a cada lado de la calzada, y no a los
2 km que separa el simulador por defecto:

| dispersión 200 m | fragmentación | saltos | contaminadas | **cola** |
|---|---|---|---|---|
| actual | 2,00 | **23** | 15,8 % | **15,42 %** |
| agrupar por línea | 1,00 | **23** | 31,7 % | **30,08 %** |

**Exactamente los mismos 23 saltos de identidad. El doble de daño.**

El arreglo no introduce ni un intercambio nuevo: `saltos` y `err_ident` (1,58 %)
son idénticos en las dos configuraciones. Lo que cambia es la **cola** —las
posiciones posteriores al primer salto de su trayectoria, que son las que heredan
la identidad equivocada—, que pasa de 15,42 % a 30,08 % de las posiciones.

La causa es que el giro en cabecera estaba **truncando la cola contaminada**.
Cuando el tracker confunde dos autobuses, hoy la trayectoria se parte poco
después —al cambiar el `trayecto`, la clave de agrupación cambia y la cadena se
rompe— y la propagación se corta ahí. Sin esa rotura, el error se arrastra hasta
el final de la trayectoria.

El efecto depende de la densidad y **no es monótono**:

| dispersión | saltos | cola actual | cola agrupando por línea |
|---|---|---|---|
| 2 km (la del simulador por defecto) | 0 | 0,00 % | 0,00 % |
| 200 m | 23 | 15,42 % | **30,08 %** |
| 30 m (sentidos totalmente solapados) | 4 | 0,50 % | 0,50 % |

A 2 km no hay competencia entre candidatos y no hay saltos. A 30 m el
solapamiento es tal que la siembra por centroide vuelve a desempatar bien. El
caso adverso está en medio, a distancias del orden del paso de refresco.

## Cómo se midió

```bash
SB=<scratchpad>/sandbox_tracking
PYTHONPATH=$SB uv run python $SB/giro_real.py
```

El generador del banco reproduce `project.analysis.simulacion.simular_flota` con
dos diferencias: la dispersión espacial inicial es ajustable, y en cabecera el
autobús **invierte la marcha** (`rumbo += pi`) además de cambiar la etiqueta de
`trayecto`. El escenario de `simular_flota(flip_en=...)` deja el movimiento
continuo a propósito, para aislar el defecto de agrupación del de predicción;
este añade la dificultad que falta.

Las cuatro métricas son las de `project.analysis.medir_tracking.medir()`, más
`fragmentacion`, añadida en esta misma tanda:
trayectorias reconstruidas por bus real.

## Por qué importa

Es un resultado contraintuitivo con consecuencias directas sobre el orden de
trabajo: **la fragmentación no es solo un defecto, también es un mecanismo de
contención**. Reducirla es necesario —una trayectoria de 10,5 min no cubre un
servicio de 40 y sin trayectoria completa no hay retraso frente al horario
teórico que medir— pero hacerlo **antes** de bajar la tasa de intercambios
duplica las posiciones que heredan la etiqueta de otro autobús.

Dicho de otro modo: las dos métricas no se pueden optimizar en cualquier orden.
Primero la identidad, después la continuidad. Esto refuerza la prioridad de la
trampa [007](../../.claude/trampas/007-arranque-en-frio-del-tracker.md) —el empate
exacto del arranque en frío— que hasta ahora se trataba como un caso raro: con la
fragmentación reducida, cada una de esas situaciones ambiguas contamina una
trayectoria el doble de larga.

También explica por qué la fragmentación no puede evaluarse sola, y por qué el
banco reporta siempre `fragmentacion` junto a `saltos` y `cola`: las cuatro
métricas históricas (`err_ident`, `saltos`, `contaminadas`, `cola`) solo ven
**fusión**, y `fragmentacion` solo ve **partición**. Un arreglo puede mejorar una
y empeorar la otra sin que ninguna de las dos, por separado, lo delate.

## Qué se hizo / qué queda abierto

Hecho:

- `fragmentacion` añadida a `project.analysis.medir_tracking.medir()` y al CLI.
- `tests/test_tracking_fragmentacion.py::test_la_fragmentacion_y_la_fusion_son_ejes_independientes`
  fija la doble ceguera con las dos mitades medidas: un sondeo al 20 % deja las
  cuatro métricas de fusión en cero con fragmentación 1,80; el tracker ingenuo a
  80 sondeos saca fragmentación 1,00 con 4 saltos y 5 % de contaminadas.
- `simular_flota()` acepta ahora `flip_en` y `parciales`, que generan los dos
  fenómenos que dominan la fragmentación real conservando la verdad-terreno.

Abierto:

- **La tasa de intercambios sobre densidad real no está medida.** El 200 m del
  simulador es una elección razonada, no una medición: falta calibrar la
  distribución real de distancias entre autobuses del mismo par (línea, sentido)
  contra la captura, como se hizo en la bitácora
  [002](002-el-empate-de-grupo-es-raro-no-normal.md) para la misma (línea,
  trayecto).
- La `cola` no se puede medir sobre dato real por falta de verdad-terreno. La
  cifra de este hallazgo es exclusivamente simulada.
- El simulador mueve los autobuses en línea casi recta con rumbo perturbado, no
  sobre las rutas del GTFS. Dos sentidos reales de una línea no son dos rectas
  paralelas.

## Para la memoria

> Al evaluar las correcciones de la fragmentación de trayectorias se obtuvo un
> resultado contraintuitivo que condiciona el orden en que deben abordarse. Sobre
> flota simulada con verdad-terreno, y con ambos sentidos de cada línea separados
> 200 metros —distancia representativa de dos carriles opuestos, frente a los 2
> kilómetros que separa la configuración por defecto del simulador—, la
> agrupación por línea mantiene exactamente el mismo número de intercambios de
> identidad que la configuración de referencia (23 saltos, error por posición del
> 1,58 % en ambos casos) pero duplica la proporción de posiciones contaminadas,
> del 15,4 % al 30,1 %.
>
> La corrección no introduce errores nuevos: elimina una discontinuidad que los
> estaba conteniendo. El cambio de sentido en cabecera interrumpe la clave de
> agrupación y, con ella, la cadena de identidad, de modo que un intercambio
> erróneo deja de propagarse poco después de producirse. Al suprimir esa
> interrupción, el error se arrastra hasta el final de una trayectoria que además
> es más larga. El efecto no es monótono con la densidad: desaparece tanto a 2
> kilómetros de separación, donde no hay competencia entre candidatos, como a 30
> metros, donde el solapamiento permite que la estimación por centroide resuelva
> la ambigüedad; el caso adverso se sitúa a distancias del orden del paso de
> refresco.
>
> De ello se deriva un criterio de prioridad: la continuidad de las trayectorias
> y la corrección de la identidad no son objetivos independientes, y reducir la
> fragmentación antes de haber acotado la tasa de intercambios amplifica el daño
> en lugar de reducirlo. En consecuencia, la evaluación de cualquier corrección
> sobre esta capa reporta conjuntamente una métrica de partición y una de fusión,
> dado que cada una es ciega al modo de fallo que mide la otra.
