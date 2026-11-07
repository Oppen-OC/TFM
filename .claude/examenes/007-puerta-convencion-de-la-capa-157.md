---
id: 007
tema: puerta · captura de la capa 157 (issue #8)
fecha: 2026-11-06
fuentes: .claude/trampas/002-emt-alterna-convencion-horaria.md, src/project/ingest/sources.py (resolver_convencion, append_raw), src/project/ingest/collect.py
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · unas horas en UTC no fijan la convención
<!-- concepto: convencion-la-pone-quien-sirve -->

La capa 157 sale del mismo servidor ArcGIS del geoportal que la 384 de la EMT.
Supón que sondeo `fecha_carg` durante unas horas y en todas las capturas cuadra
con UTC. ¿Basta eso para convertirla con un desfase fijo en el parser? ¿Por qué
sí o por qué no, y qué tiene que dejar guardado la captura para que, si la
convención falla algún día, se vea y se pueda corregir después?

**Respuesta:**

> No, el desfase es una cosa que tiene que verificarse siempre ya que a veces le
> da por añadirle 2 horas. Se debe dejar guardado el desfase

**Veredicto:** a-medias

_Rondas._ Ronda 1, a-medias: aciertas el qué (no basta, se comprueba siempre),
pero «a veces le da por» describe el síntoma, no el porqué. ¿En qué momento se
pone la convención: cuando la estación mide el dato o cuando el servidor arma
la respuesta? Según cuál sea, unas horas limpias prueban algo o no prueban nada.
Las «2 horas» tampoco son una constante: piensa en qué mes estamos. Y sobre qué
guardar: si guardas solo el desfase que eligió el parser y el parser se
equivocó, ¿con qué lo corriges? Mira la Causa de la trampa 002 y el punto 1 del
docstring de `collect.py`.

**Respuesta (ronda 2):**

> 1. No lo sé.
> 2. Sé que no son constantes; ahora mismo tenemos UTC + 0.
> 3. Con lo guardado antes.

**Veredicto (ronda 2):** fallada

_Respuesta completa._ La convención no la pone la estación al medir: la pone
quien sirve la respuesta. La causa más probable de la trampa 002 es un
balanceador con varios nodos detrás, unos que sellan en hora de Madrid y otros
en UTC. Por eso un mismo sondeo puede llegar dos veces con convenciones
distintas, y por eso cambia de una respuesta a la siguiente, no de un día a
otro. Unas horas limpias en UTC solo dicen qué nodos te tocaron esas horas: la
respuesta siguiente puede venir del otro. La capa 157 la sirve el mismo
geoportal, así que se decide respuesta a respuesta, contra el instante de
captura, y nunca con un desfase fijo.

El desfase tampoco es una constante. València está en Europe/Madrid: UTC+2 en
verano (CEST) y UTC+1 desde el 25/10 (CET). UTC+0 es Canarias o Londres. Con
una constante de 2 h, desde el cambio de hora cada fila sale una hora
desplazada. Por eso se convierte con la zona (`TZ_LOCAL`), no con un número.

Lo que se guarda es el payload crudo tal como llegó, con el epoch sin tocar, y
el `ts_ingest_utc` de la captura: `append_raw`, antes de parsear. Si el parser
eligió mal, el desfase que eligió no sirve para corregirlo, porque es justo lo
que estaba mal. Con el crudo y el instante de captura, `reprocesar` vuelve a
decidir. La decisión de cada sondeo se deja además a la vista (`tz_convencion`,
la latencia y `DUDOSA` cuando ninguna cuadra), para que el error se vea en vez
de esconderse en una hora plausible.
