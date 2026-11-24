# Día 1 · El porqué: tema, pregunta y alcance

## Objetivo del día

Poder explicar en dos minutos **qué problema resuelve el TFM, qué pregunta hace, qué
aporta y qué haces si falla**, y por qué las otras nueve ideas se descartaron.

## Lecturas

En este orden:

1. `docs/00_tema_y_alcance.md`, entero (167 líneas). Fíjate en *Pregunta* (l. 18),
   *Pilares de defensa* (l. 23), *Alcance* (l. 48), *Riesgos* (l. 119) y *Plan B* (l. 130).
2. `docs/04_propuesta_para_tutor.md`, entero. Es la propuesta **de agosto**, tal como se
   envió; tiene un aviso de vigencia al principio con lo que quedó superado.
3. `docs/02_exploracion_de_temas.md`, **solo** el aviso crítico (l. 21), las diez ideas
   (l. 29-168: cada una con su «Dificultad» y «Riesgo») y la *Recomendación* (l. 169).
   No leas el anexo.
4. `README.md`, secciones «El problema» (l. 12) y «Fuentes de datos» (l. 38).

## Comandos a ejecutar

No necesitan red:

```powershell
git log --oneline -8                     # en qué punto está el repo
Get-Content docs/00_tema_y_alcance.md -TotalCount 50
Get-Content .claude/trampas/README.md | Select-Object -First 12   # índice de trampas, de reojo
```

## Qué tienes que saber explicar

Contesta por escrito en la última sección **antes** de mirar la respuesta modelo.

**P1. ¿Por qué es defendible el tema?**
Tres pilares (`docs/00:23-46`): (1) la etiqueta de retraso no existe en la fuente y hay
que construirla con un ETL (tracking, viajes, map-matching, interpolación), que es lo
que lo convierte en TFM y no en un `read_csv`; (2) la fusión de posiciones de flota con
el estado de tráfico municipal no está publicada para València; (3) el volumen pide
formato columnar, no infraestructura distribuida. Además, el tema es falsable: puede
salir que el tráfico no aporta, y eso también es un resultado (`docs/04:21-27`).

**P2. ¿Cuál es la pregunta de investigación?**
«¿Cuánto del retraso de un autobús urbano se explica por la congestión medida aguas
abajo de su ruta, y con cuánta antelación puede anticiparse?» (`docs/00:18-21`).
Ojo: la propuesta de agosto la formula distinta, en términos de «información
anticipatoria» y «horizonte» (`docs/04:21-25`); está anotado en `auditoria_docs.md`.

**P3. ¿Cuál es la aportación metodológica?**
Reconstruir una etiqueta que la fuente no publica: la EMT no da identificador de
vehículo, `trip_id` ni retraso. El trabajo infiere la identidad entre sondeos
(asignación óptima con modelo de movimiento), segmenta viajes, proyecta sobre la traza
del GTFS e interpola el paso por parada (`docs/04:53-61`; `docs/00:25-29`).

**P4. ¿Por qué no hay histórico?**
Ninguna fuente guarda pasado: la capa de la EMT trunca y reinserta su tabla en cada
refresco, y lo que no captura el colector se pierde (`CLAUDE.md`, sección *Dominio*;
`docs/04:46-52`; ficha `.claude/trampas/001-gid-no-identifica-vehiculo.md`). De ahí que
el corpus propio sea una aportación de recurso y que el colector deba correr siempre.

**P5. ¿Qué haces si el etiquetado de la EMT no sale?**
Plan B: pivotar a Renfe Cercanías núcleo 40, donde `retrasoMin` viene calculado y
`tripId` es estable (`docs/00:132-139`). La condición no se ha dado, el etiquetado de la
EMT funciona de punta a punta; Renfe se sigue capturando como respaldo porque el crudo
no se recupera después, y su validación cruzada queda como trabajo futuro
(`docs/00:70`).

**P6. ¿Por qué se eligió esta idea y no las otras nueve?**
Es la única del listado que activa a la vez tiempo real, arquitectura Big Data y ML, el
dataset es en sí una aportación, y el dominio se entiende sin explicaciones
(`docs/02:173`). Las alternativas quedaron como segunda y tercera opción (precios
negativos en electricidad: más segura; AIS marítimo: más impresionante pero con riesgo
de agotar el tiempo en ingeniería de datos; `docs/02:175-177`). El coste de la elegida
es de calendario: el colector tenía que correr desde la semana 1.

**P7. ¿Qué queda explícitamente fuera?**
Red completa, deep learning (trabajo futuro), datos privados o convenios con la EMT,
Metrovalencia como dato observado, y servido en tiempo real como resultado (la demo
en vivo no es una cifra del TFM) (`docs/00:48-73`).

## Ejercicio

**Pitch de 2 minutos, cronometrado**, en voz alta y luego por escrito en cuatro
párrafos: (1) el problema, (2) la pregunta, (3) la aportación, (4) qué haces si falla
(plan B). Grábate y comprueba que no pasas de 2 min. No cites cifras todavía: las
cifras empiezan el día 3.

## Mis respuestas / dudas

