---
id: 014
tema: puerta · clave del Marcador de la demo en vivo
fecha: 2026-11-17
fuentes: src/project/services/vivo.py (Marcador, _resultado), src/project/etiquetado.py (_asignar_tramo, conflictos 519-528), .claude/trampas/014
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · el trip_id se reasigna en cada ciclo
<!-- concepto: trip-id-se-reasigna-cada-ciclo -->

Se cambia la clave del marcador de `(fecha_servicio, viaje_id)` a
`(fecha_servicio, trip_id)`, el viaje programado del GTFS, y cada ciclo sigue
reetiquetando el día desde el principio. ¿En qué casos una predicción congelada
se quedaría sin verificar, o se verificaría con el paso de otro bus? Nombra el
mecanismo de `etiquetado.py` responsable.

**Respuesta:**

> cruces es la funcion encargada de verificar las predicciones congeladas o el
> apso de otro bus. Esto no se cuando podria suceder.

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: `cruces` calcula el instante de paso por cada parada
a partir de las posiciones; las predicciones congeladas las verifica
`Marcador.verificar`. Pista: el `trip_id` no viene en el dato, lo pone
`etiquetar` al casar el viaje observado con el horario, cada ciclo sobre el
prefijo visto; mirar `etiquetado.py:519-528`.

**Respuesta (ronda 2):**

> en caso de que no haya venido en el payload

**Veredicto (ronda 2):** fallada

_Respuesta completa._

- **Asignación por coste sobre el prefijo.** `_asignar_tramo` elige el viaje
  programado de menor `coste_s` con los pasos vistos hasta el ciclo. Con más
  pasos, el mejor ajuste puede pasar a otra salida cercana (refuerzo, misma
  franja, regulación en cabecera): la clave congelada queda huérfana, o la
  reclama otro bus y se verifica con su paso.
- **Conflictos** (`etiquetado.py:519-528`): dos viajes observados con el mismo
  `trip_id`, gana el de menor `coste_s` y el otro sale de los pasos. El ganador
  puede cambiar entre ciclos: misma clave, otro bus físico; o el bus congelado
  pasa a perdedor y desaparece.
- **Con `viaje_id`, además**, la identidad de `rastrear` cambia a posteriori:
  `_suavizar_intercambios` mira un sondeo adelante y `_coser_alternancias` une
  fragmentos (trampa 014).
- Ninguno da error: un marcador con cifras plausibles y casos mal puntuados.
