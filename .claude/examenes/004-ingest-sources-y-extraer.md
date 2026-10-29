---
id: 004
tema: src/project/ingest/sources.py, src/project/analysis/dashboard_ingesta/extraer.py
fecha: 2026-10-28
fuentes: src/project/ingest/sources.py, src/project/ingest/collect.py, src/project/ingest/reprocesar.py, src/project/gtfs.py, trampas/002, trampas/011, bitacora/004, bitacora/019, bitacora/042, docs/07_decisiones.md (ADR-014, ADR-017)
estado: corregido
ronda: 2
nota: 0/6 (ronda 1)
---

## P1 · el sondeo se nombra por su gid mínimo
<!-- concepto: snapshot-id-minimo-del-bloque -->

El sondeo de la EMT se identifica por el `gid` mínimo de su bloque. El máximo
también cambia en cada refresco y también serviría de nombre. ¿Por qué el
mínimo? ¿Qué pasaría al reconstruir el curated si se usara el máximo, y por qué
no daría ningún error?

**Respuesta:**

> El minimo identifica la primera instancia de entrada
> No pasaria nada porque noa hya una forma de diferenciar un maximo de un minimo, el unico problema seria uqe este movería la ventana N posiciones

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: la respuesta dice que no pasaría nada, y sí pasa.
Piensa qué contiene una captura tomada mientras la tabla se está reinsertando:
¿cuál de los dos extremos del bloque comparte con el bloque completo y cuál no?
Después sigue esa captura por `reprocesar`. Mira la trampa 011 y la bitácora 020.

**Respuesta (ronda 2):**

## P2 · una sola regla de sondeo repetido
<!-- concepto: clave-sondeo-compartida-colector-reprocesar -->

El colector en vivo y la reconstrucción del curated deciden con la misma función
si un sondeo ya se ha visto. Si cada uno tuviera su propia regla, las dos
razonables, ¿qué se rompería y dónde se notaría? ¿Por qué unos pocos sondeos
repetidos no se quedan en unas pocas filas de más?

**Respuesta:**

> Se tendría uqe decidir cual de los dos sondeos es el correcto con algun tip de metrica. no se donde se comperia ni donde se notaria
> No lo se

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: no se trata de elegir el sondeo correcto, sino de
qué pasa cuando dos reglas razonables no coinciden. Esto ya ocurrió una vez:
busca en la bitácora 019 qué diferencia hubo entre el curated del colector y el
reconstruido. Para la segunda pregunta, sigue un sondeo duplicado hasta
`rastrear` y mira la cifra de la tabla de esa entrada.

**Respuesta (ronda 2):**

## P3 · el tráfico no dice cuándo midió
<!-- concepto: ts-trafico-es-captura-desfase-suelo -->

Las capas de tráfico usan como instante del dato el de su captura. Con eso, la
antigüedad del último tráfico frente a cada sondeo de bus sale con una mediana
de unos dos minutos. ¿Por qué esa cifra es un suelo y no el desfase real? ¿Qué
podría hacerla crecer sin que el colector lo viera?

**Respuesta:**

> Porque representa unicamente la media de estos datos, el desfase real se calcula de otra forma
> Datos anomalos

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: no es una media ni intervienen datos anómalos. Mira
qué instante guardan las capas de tráfico como `ts_utc` (`parse_trafico_estado`)
y qué tramo del recorrido del dato, desde que la fuente mide hasta que el
colector lee, queda fuera de ese instante. Para la segunda parte, mira cómo
decide `clave_sondeo` si un sondeo de tráfico está repetido, y pregúntate con
qué señal contaría el colector para notar que la fuente se ha retrasado. Está en
la bitácora 004.

**Respuesta (ronda 2):**

## P4 · la versión nueva del GTFS no entra sola
<!-- concepto: gtfs-nuevo-no-entra-solo -->

El colector guarda cada versión nueva del GTFS en el crudo, no en el directorio
del que el etiquetado elige horario. ¿Por qué no dejar que entre sola? ¿Qué les
pasaría a los días ya etiquetados, y por qué no daría la cara?

**Respuesta:**

**Veredicto:** fallada

_Rondas._ Ronda 1, en blanco. Empieza por la regla con la que el etiquetado
elige horario cuando varias versiones cubren el mismo día (ADR-014,
`gtfs.elegir_horario`), y por lo que haría DVC con `prepare` si cambiara el
contenido de ese directorio. Para el «no daría la cara», la bitácora 042 midió
cuánto contradice una versión posterior a lo ya etiquetado y si la tasa de
asignación se movía.

**Respuesta (ronda 2):**

## P5 · dónde nace la alternancia horaria
<!-- concepto: convencion-la-pone-quien-sirve -->

En la foto del dashboard, la alternancia horaria de la EMT se cuenta por sondeo
y no por captura, porque a veces el mismo sondeo llega dos veces con
convenciones distintas. ¿Qué revela ese hecho sobre el origen de la
alternancia? ¿Por qué es la razón de que la convención se resuelva respuesta a
respuesta, y no con un desfase fijo por fecha?

**Respuesta:**

> Que se usaron modelos distintos
> Porque depende de la version del programa, de esta forma es mas facildesglosarlo

**Veredicto:** a-medias

_Rondas._ Ronda 1, a-medias: apuntas al software, pero no dices dónde nace la
alternancia ni por qué eso descarta el desfase por fecha; «es más fácil
desglosarlo» no es un porqué. Un mismo sondeo es un mismo refresco de la tabla.
Si llega con dos convenciones, ¿la convención va en el dato guardado o se pone
en otro momento? Y según dónde se ponga, ¿qué granularidad necesita la
corrección? Mira la Causa de la trampa 002 y la tabla de su Guardia.

**Respuesta (ronda 2):**

## P6 · la geometría del tráfico se baja una vez
<!-- concepto: geometria-estatica-referencia-unica -->

La geometría de los tramos de tráfico se descarga una vez y después se piden
las capas sin ella. ¿Qué compromiso se aceptó y contra qué alternativa? ¿Qué
fallo deja pasar sin error, y qué señal en los datos obligaría a reabrirlo?

**Respuesta:**

> Que no se está respetando la geometria real y se está aceptando un nivel de error con la geometria de las paradas
> No lo se

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: aquí no intervienen las paradas, solo los tramos de
tráfico, y el compromiso no es de precisión, es de coste. Mira qué ahorra pedir
sin geometría (`geometria_estatica` en `sources.py`) y qué se pierde a cambio.
Para el fallo, mira qué hace `collect.asegurar_geometria` cuando la referencia ya
existe, y en qué supuesto sobre la fuente descansa eso. Las tres partes las
cierra el ADR-017.

**Respuesta (ronda 2):**
