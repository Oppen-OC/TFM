---
id: 008
tema: puerta · issue #6, vida de la captura del GTFS en collect --status
fecha: 2026-11-09
fuentes: src/project/ingest/collect.py (capturar_gtfs, mostrar_estado), src/project/ingest/sources.py (guardar_gtfs), docs/bitacora/042, docs/bitacora/051, issue #6
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · un dup del GTFS no es un dup de la EMT
<!-- concepto: dup-del-gtfs-prueba-la-captura -->

En las fuentes del geoportal, un sondeo duplicado no mueve `ultimo_ok`:
`--status` lo cuenta como silencio y, pasada la tolerancia, da la fuente por
caída. Para el GTFS, el issue pide lo contrario: que una comprobación que
termina sin versión nueva (un `dup`) cuente como señal de vida. ¿Por qué tiene
sentido esa asimetría, es decir, qué garantiza una comprobación GTFS sin versión
nueva que no garantiza un sondeo duplicado de la EMT? ¿Y qué fallo de la captura
del GTFS seguiría sin verse aun con esa señal?

**Respuesta:**

> Porque con las GTFS es un comprobante de que está actualizado. El sondeo de
> la GTFS garantiza que el horario de los buses es el correcto, es un dato muy
> importante porque es con el que se compara la variable objetivo, un sondeo
> duplicado de la EMT puede simplemente solaparse con el siguiente que es cada
> 30 s, GTFS no. El fallo que seguiría sin verse no sé cuál es.

**Veredicto:** a-medias

_Rondas._ Ronda 1, a-medias: «comprobante de que está actualizado» apunta bien,
pero la razón no es la cadencia. ¿Qué ha tenido que hacer el colector, de
principio a fin, para concluir que es un `dup`? Mira cómo lo decide
`guardar_gtfs`. Del lado de la EMT: si dos sondeos seguidos de una fuente en
tiempo real traen lo mismo, ¿qué pasa con los buses en la calle y qué se
pierde? Para la segunda parte, piensa en lo que pasa entre dos comprobaciones y
en lo que hay al otro lado de VLCi: docstring de `capturar_gtfs`, bitácoras 042
y 051, «Fuera de alcance» del issue.

**Respuesta (ronda 2):**

> El GTFS revisa la fecha y la hora para verificar duplicados. Si dos sondeos
> traen lo mismo entonces se asume que es un error, existe una cierta holgura
> para procesar estos errores dentro del propio código, se pierde el dato del
> bus en un momento concreto del tiempo.

**Veredicto (ronda 2):** a-medias

_Respuesta completa._ Una comprobación del GTFS que acaba en `dup` ha recorrido
el camino entero: `package_show` contestó, se bajó el zip completo, se validó
que es un GTFS y su sha1 coincide con uno que ya está en disco. No compara
fechas ni horas: compara el contenido byte a byte. Si VLCi hubiera tenido una
versión nueva, se habría guardado en esa misma vuelta. El `dup` prueba, por
tanto, que la captura funciona **y** que no había nada que perder. El ritmo de
versiones lo marca quien publica (32 días sin ninguna), no el colector.

En la EMT el dato es la posición de cada bus en cada instante, y la flota no se
para. Dos sondeos idénticos dicen que la fuente ha dejado de entregar dato
nuevo, y esas posiciones no vuelven: no hay histórico. Por eso allí la alarma
mide dato nuevo, y en el GTFS mide comprobación completa. Es la misma regla de
la puerta 002 («la alarma mide que llega dato bueno»), aplicada a una fuente
cuyo dato bueno es «he comparado lo vigente con lo que tengo».

Lo que sigue sin verse aun con la señal:

- **Entre comprobaciones.** Cada versión sustituye a la anterior en VLCi
  (bitácora 042). Una versión que viva menos de 6 h entre dos comprobaciones se
  pierde sin rastro. La señal dice que miras, no que mires lo bastante a menudo.
- **Al otro lado de VLCi.** Si el catálogo de VLCi se queda con el zip viejo
  mientras la EMT publica, cada comprobación acaba en `dup` y todo parece sano:
  no se distingue de «la EMT no ha publicado».
- **Sin la tarea.** Un colector desplegado sin `capturar_gtfs` no escribe la
  fuente en el latido, y `--status` no puede echar en falta lo que no aparece
  (bitácora 051: la Pi, del 06/10 al 23/10).

Lo que acierta la ronda 2: la consecuencia en la EMT, el dato del bus en un
instante que se pierde. Lo que falla: el mecanismo del `dup` del GTFS, que no
es fecha ni hora sino el sha1 del zip entero, y la segunda parte, en blanco.
