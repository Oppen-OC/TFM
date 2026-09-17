---
id: 004
titulo: Sort inestable reordena filas dentro del snapshot y falsea la métrica de tracking
estado: cerrada
capa: tracking
detectada: 2026-08-19
test: tests/test_tracking_identidad.py::test_rastrear_no_reordena_filas_dentro_del_sondeo
---

## Síntoma

El selftest reportaba **~11 % de precisión de tracking** cuando la real era
~99 %. El tracker parecía roto de raíz.

## Causa

`sort_values(["snapshot_id"])` usa quicksort por defecto, que **no es estable**:
filas que comparten `snapshot_id` se reordenan silenciosamente aunque la entrada
ya viniera bien ordenada.

El emparejamiento húngaro en sí es por índice y no se ve afectado. El daño estaba
en el arnés: reengancha las etiquetas de verdad-terreno **por
posición de fila** después de llamar a `rastrear()`. Con el orden barajado, cada
verdad se pegaba a la fila equivocada.

Arreglado en el commit `d92a9af`, una línea.

## Por qué se vuelve a caer aquí

Es una trampa de segundo orden y la más peligrosa del repo: **el bug estaba en la
medición, no en lo medido**. La reacción natural ante un 11 % es ir a depurar el
tracker — que estaba bien — y "arreglarlo" hasta que la métrica suba. Eso habría
roto código correcto persiguiendo un número falso.

La estabilidad del sort no es algo que se mire al leer un `sort_values`, y pandas
no avisa. Cualquier reordenación posterior por columna con valores repetidos
reintroduce el mismo fallo si algo aguas abajo depende de la posición de fila.

Regla que sale de aquí: **no reenganchar datos por posición de fila.** Si hay que
hacerlo, `kind="stable"` explícito y una clave de desempate en el sort.

## Guardia

`tests/test_tracking_identidad.py::test_rastrear_no_reordena_filas_dentro_del_sondeo`:
entrada desordenada entre sondeos, y el orden de llegada dentro de cada sondeo
tiene que sobrevivir a `rastrear()`.

Hasta 09/2026 la guardia era `test_tracker_predictivo_identidad_correcta`, y
**había dejado de guardar sin que nada cambiase en el código ni en el test**.
Solo caía si quicksort permutaba una entrada ya ordenada: numpy 2.2.6 lo hace,
numpy 2.4.6 en la CPU de desarrollo no. Al actualizar `uv.lock`, quitar
`kind="stable"` dejó de alterar un solo byte de salida
(`docs/bitacora/012-tres-guardias-de-trampas-cerradas-no-guardan.md`). La
guardia nueva ordena una entrada desordenada, donde cualquier orden no estable
permuta.
