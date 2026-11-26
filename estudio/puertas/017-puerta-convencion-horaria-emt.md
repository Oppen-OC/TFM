# Puerta 017 · convención horaria de la EMT

Archivada **dentro de `estudio/`** por decisión de Daniel (opción c): esta tarea no
escribe fuera de `estudio/`, así que **no** se ha creado `.claude/examenes/017-…` ni
se ha tocado `.claude/examenes/debilidades.md`. Si quieres que cuente para el
registro de debilidades, copia este fichero a `.claude/examenes/` y añade la fila.

```yaml
id: 017
tema: tarea «material de estudio para la defensa» · incoherencia nº 1 de la auditoría
fecha: 2026-11-24
fuentes: .claude/trampas/002-emt-alterna-convencion-horaria.md, src/project/ingest/sources.py:78-123
estado: corregido
ronda: 2
nota: 0/1 limpias (a-medias en las dos rondas)
```

## P1 · desfase fijo frente a convención por sondeo
<!-- concepto: convencion-la-pone-quien-sirve -->

Corregir la hora de la EMT con un desfase fijo (+2 h en verano, +1 h en invierno)
parece razonable y no lanza ningún error. ¿Por qué deja filas mal sin dar la cara?
¿Y qué tiene que decidir la convención de cada sondeo, en lugar del desfase?

**Respuesta (ronda 1):** La razón de por qué se produce el desfase no es 100 %
clara, pero creemos que es por cómo se manejan los balanceadores y que no controlan
las mismas horas. Para decidir el desfase de cada payload se verifica con un desfase
de 1 hora y otro de 2 horas y se toma el más plausible, siempre que se recibe uno.

**Veredicto (ronda 1):** a-medias. Daba la causa probable de la alternancia, no el
porqué del fallo silencioso; y describía mal las dos interpretaciones y el «siempre».
Pista: qué supone el desfase fijo sobre cómo se reparte entre sondeos, y qué ve el
modelo después.

**Respuesta (ronda 2):** Porque no hay una forma clara de diferenciar en qué horario
está el payload; con un desfase fijo puede que no dé error, pero no sabes cuál es el
desfase real que envía el balanceador, por eso hay que verificar siempre. Las dos son
UTC+1 y UTC+2, ¿cierto? Cuando ninguna de las dos da latencia plausible se marca como
Dudoso.

**Veredicto (ronda 2):** a-medias (cuenta como fallada). Lo que acierta: la
convención hay que decidirla en cada sondeo, y `DUDOSA` cuando ninguna es plausible.
Lo que faltaba:

- El desfase fijo supone que todos los sondeos van igual de desplazados, y no es así:
  79 % llega en hora local sellada como UTC y 21 % en UTC real. Un `zoneinfo` por
  fecha arregla el 79 % y deja el 21 % desplazado 2 h
  (`.claude/trampas/002-emt-alterna-convencion-horaria.md`, *Por qué se vuelve a caer
  aquí*; 20,3 % de filas desplazadas más de 1 h antes de la guardia, 0 después).
- No da error ni nulos: la etiqueta de retraso sale falsa en una quinta parte de las
  filas, y el modelo entrena y converge con métricas creíbles.
- Las dos interpretaciones **no** son «UTC+1» y «UTC+2» (`sources.py:102-107`):
  `YA_EN_UTC` (el epoch se lee tal cual) y `LOCAL_NAIVE` (se reinterpreta como hora de
  pared de Europe/Madrid; el +1/+2 sale solo de la fecha). Se decide por la latencia
  mediana plausible (`sources.py:116-123`); si ninguna lo es, o lo son las dos,
  `DUDOSA` en vez de adivinar.

Concepto `convencion-la-pone-quien-sirve`: ya figuraba `flojo` en
`.claude/examenes/debilidades.md` (3 fallos); esta puerta sería el cuarto.
