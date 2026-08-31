---
description: Detecta deriva entre la documentación y el código, y propone la corrección sin aplicarla
argument-hint: [fichero o capa a revisar, o vacío para todo]
---

Busca dónde la memoria del proyecto ya no describe el código real: `CLAUDE.md`,
`docs/`, las fichas de `.claude/trampas/` y los prompts de `.claude/agents/`.

Alcance: **$ARGUMENTS** (vacío = todo).

## Regla que gobierna este comando

**La dirección es asimétrica.** El código puede *invalidar* una afirmación de la
memoria; no puede *escribirla*. `docs/07_decisiones.md` explica por qué DVC y no
Airflow: eso no tiene contrapartida en el código, y borrarlo por no encontrarlo
sería destruir precisamente lo que se defiende ante el tribunal.

Por eso: **detectas, reportas, propones. No escribes.** Espera aprobación
explícita antes de tocar un solo fichero, aunque la corrección sea obvia.

## Primero lo mecánico

```
uv run pytest .claude/tests -q
```

Cubre rutas y funciones citadas que no existen, stages de `dvc.yaml` contra lo
documentado, `params:` sin clave en `params.yaml`, dependencias declaradas como
pendientes que ya están, y afirmaciones sobre ficheros vacíos. Si falla, eso ya es
deriva confirmada: no hace falta que la vuelvas a buscar a mano.

## Después lo que exige juicio

Esto es lo que ningún test puede comprobar. Para cada punto, cita
`fichero:línea` de la afirmación **y** `fichero:línea` de la evidencia en código.

1. **Comportamiento descrito que el código contradice.** El caso de referencia: la
   trampa 002 vivió descrita como un desfase horario fijo en tres sitios mientras
   `resolver_convencion()` resolvía por snapshot. Busca afirmaciones sobre cómo se
   comporta una fuente, cómo se corrige algo o qué hace una función, y contrástalas
   con la implementación actual.

2. **Decisiones de `docs/07_decisiones.md` que el código ya no respeta.** Si una
   ADR dice Parquet y hay un `to_csv` en el pipeline, o dice split temporal y hay
   un `train_test_split` sin fecha, es lo más grave que puedes encontrar: o el
   código está mal, o la decisión cambió sin registrarse.

3. **Estado mal descrito.** Módulos descritos como si funcionaran y vacíos;
   trabajo listado como pendiente y ya hecho. `CLAUDE.md` tiene una sección
   `## Estado` que envejece sola.

4. **Cifras rancias.** El proyecto arrastra números con significado: comprobaciones
   del selftest, tramos reales de tráfico (410 de 446), porcentaje de cobertura
   espacial, volumen proyectado. Contrasta cada cifra con su fuente en `docs/` o
   con el código que la produce.

5. **Punteros rotos por reorganización.** Documentos que citan secciones de otros
   documentos que se movieron o renombraron.

6. **Contenido duplicado entre memoria y fichas.** Toda copia diverge. Si una
   trampa aparece descrita fuera de `.claude/trampas/`, esa copia sobra.

## Cómo se decide qué gana

- **El código gana** en afirmaciones sobre comportamiento, estructura o cifras
  medidas.
- **La memoria gana** en el porqué, en las decisiones cerradas y en el alcance:
  esos no están en el código, y que el código no los refleje puede significar que
  el código está mal.
- **Duda:** no la resuelvas tú. Repórtala como conflicto y deja que el usuario
  decida. Una decisión de diseño revertida en silencio por un agente es peor que
  una doc desactualizada.

## Salida

Una tabla, ordenada por gravedad:

| Dónde | Dice | El código dice | Gana | Propuesta |
|---|---|---|---|---|

Debajo, el diff exacto que aplicarías, sin aplicarlo. Si no hay deriva, dilo en
una línea.

Si algo de lo encontrado es una trampa — algo que la fuente no documenta o
documenta mal, y que se volvería a hacer — proponlo también como ficha nueva en
`.claude/trampas/`.
