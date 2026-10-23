---
id: 002
tema: puerta · issue #1, salud por fuente en collect --status
fecha: 2026-10-23
fuentes: bitacora/021, trampas/018, src/project/ingest/collect.py
estado: cerrado
ronda: 1
nota: 1/1
---

## P1 · la señal de salud
<!-- concepto: alarma-mide-dato-bueno-no-errores -->

El latido ya publica, por fuente, el contador `err` y el `ultimo_error`. Otra
forma de arreglar el issue sería diagnosticar con ellos («fuente con errores
recientes ⇒ caída») en vez de con la edad de `ultimo_ok`. ¿Habría avisado esa
alternativa el 10-14/09 (bitácora 021) y el 13/10 (trampa 018)? ¿Por qué sí o
por qué no en cada caso, y qué dice eso de qué tiene que medir una alarma de
captura?

**Respuesta:**

> 13/10: la conclusión es correcta, no habría avisado. Falta el porqué: el
> error llegaba como una respuesta HTTP válida, {"error": …}, así que no salta
> ninguna excepción y err no se mueve.
> 10-14/09: aquí hay una contradicción. Si el portal hubiera dado errores (sin
> conexión, tiempos de espera agotados), cada intento lanzaría una excepción,
> err subiría y la alternativa sí habría avisado. Además, no está demostrado
> que fuera el portal: la bitácora 021 deja la causa abierta y apunta a que las
> tareas dejaron de pedir, porque las cuatro capas volvieron en el mismo
> segundo del reinicio. Solo en ese caso la alternativa no avisa. La respuesta
> correcta es «depende de la causa», y explicar qué pasa en cada rama.
> Falta la tercera parte: qué tiene que medir una alarma de captura. Tiene que
> medir que llega dato bueno (la edad de ultimo_ok), no que hay errores. Un
> contador de errores calla igual cuando todo va bien que cuando nadie pregunta
> o cuando la fuente contesta con un error disfrazado de respuesta válida.

**Veredicto:** correcta

_Matiz de la corrección, sin restar._ En la rama «fallaba la red», `err` sube,
pero despacio: el retroceso de `collect.sondear` espacia los intentos hasta 16
periodos. Y el latido no fecha `ultimo_error`, así que «errores recientes» no se
puede calcular desde un solo `_status.json`.
