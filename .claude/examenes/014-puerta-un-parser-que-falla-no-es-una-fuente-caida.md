---
id: 014
tema: puerta · issue #5, el retroceso de sondear
fecha: 2026-11-17
fuentes: src/project/ingest/collect.py (sondear), src/project/ingest/reprocesar.py, src/project/ingest/sources.py (parse), trampas/018, trampas/019, issue #5
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · dónde se trata el fallo del parser
<!-- concepto: donde-se-arregla-el-parser -->

El #5 se puede cerrar de dos formas: (a) cada parser captura su excepción y
devuelve un DataFrame vacío; (b) se toca el bucle de `sondear`. Las dos dejan el
crudo a cadencia normal. ¿Por qué (a) es peor, qué dejarías de ver y dónde se
notaría? ¿Y por qué el sitio es el bucle y no cada parser?

**Respuesta:**

> Porque devolviendo un dataframe vacio no estás comunicando correctamente el
> tipo de error que se capturó. Al hacerlo dentro del bucle el codigo es mas
> manenible y es mas facil recorrer los errores

**Veredicto:** a-medias

_Rondas._ Ronda 1, a-medias: acierta el qué —se pierde el tipo de error— y
falta la consecuencia y el porqué del sitio. Dos punteros. Uno: hoy ya hay un
payload que el parser convierte en un DataFrame vacío sin que sea un fallo
(trampa 018); mira qué contadores mueve ese caso en `sondear`, y quién más
llama a `parse` aparte del colector (`reprocesar`, `metrics/curar.json`, trampa
019). Dos: «más mantenible» describe el qué. El porqué es qué sabe `sondear`
en el momento del fallo que el parser no puede saber.

**Respuesta (ronda 2):**

> sondear tiene uan vision global del payload, parser no

**Veredicto (ronda 2):** a-medias

_Respuesta completa._ El parser también ve el payload entero; lo que no ve es
si la fuente contestó.

- **Qué se pierde con (a).** Un DataFrame vacío ya significa algo legítimo: el
  `{"error": …}` del geoportal y el sondeo sin filas (trampa 018), que en
  `sondear` no mueven ni `ok` ni `err`. Un parser roto que devuelve vacío se
  confunde con eso: `err` no sube, `ultimo_error` no dice `KeyError` y el log
  calla. Y `reprocesar` llama al mismo `parse`, así que `metrics/curar.json`
  tampoco lo cuenta: los 254 payloads de Renfe de la trampa 019 se vieron
  justo por ese contador. El fallo desaparece a la vez en el colector y en el
  pipeline; solo quedaría un `--status` que da la fuente por CAÍDA por falta de
  `ultimo_ok`, culpando a la fuente de lo que es del parser.
- **Por qué el bucle.** El retroceso existe para no martillear una fuente
  caída. Lo que decide si hay que espaciar es si la fuente contestó y el crudo
  está en disco, y eso solo lo sabe `sondear`: el parser recibe un payload que
  ya llegó. Además es el único sitio por el que pasan las seis fuentes, las de
  hoy y las que se añadan; un `try` por parser cubre solo los parsers que
  alguien se acuerde de envolver. Se arregla donde vive la información para
  decidir, no donde nace el síntoma.
