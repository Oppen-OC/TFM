# Plan de 7 días

Unas 4-5 h por día. Regla: **si no sabes contestar las preguntas de control del día,
no pasas al siguiente.** Repites la lectura de lo que falle, no avanzas.

| Día | Tiempo | Bloques (orden) | Sale con… |
|---|---|---|---|
| 1 · El porqué | 4 h | lectura de `docs/00`, `docs/04` (1 h 30) · `docs/02`, solo el porqué del descarte (45 min) · `README.md` «El problema» y «Fuentes» (30 min) · preguntas (45 min) · pitch de 2 min, cronometrado (30 min) | un pitch de 2 min: problema, pregunta, aportación, plan B |
| 2 · Las fuentes | 4 h | `docs/01` (1 h 30) · `docs/03` (45 min) · `ingest/sources.py` (1 h) · `ingest.explore` con red (15 min) · preguntas (30 min) | saber qué da cada fuente, con qué cadencia y qué rareza trae |
| 3 · Calidad y giro | 5 h | `docs/05` (1 h 15) · `docs/06` (1 h 15) · `docs/07` ADR-001…010 y pendientes (1 h 15) · `fig_trafico_vs_buses.html` (15 min) · preguntas y ejercicio (1 h) | una frase que reconcilie pregunta original y reformulación |
| 4 · Las trampas | 5 h | índice de trampas y fichas 002 → 001 → 003 → 004 → 005 → 006 (2 h 30) · cada guardia en su test (1 h) · pytest de las guardias (15 min) · hojear 007-022 (45 min) · preguntas (30 min) | las 6 trampas con su guardia, y por qué vuelven a caer |
| 5 · El ETL | 5 h | `tracking.py` (1 h 30) · `collect.py` y `reprocesar.py` (1 h) · `diagnose.py` y `test_diagnose.py` (1 h) · cómo se fabrica la etiqueta: `etiquetado.py`, `prepare.py` (1 h) · preguntas (30 min) | explicar húngaro frente a vecino más cercano y de dónde sale `retraso_s` |
| 6 · Pipeline y arquitectura | 4 h 30 | `dvc.yaml`, `params.yaml` (1 h) · `CLAUDE.md` Arquitectura y Pipeline ML (45 min) · `api/`, `services/`, `ui/` y `tests/test_api.py` (1 h 15) · dibujar de memoria el grafo de dependencias (30 min) · lista de lo que falta (30 min) · preguntas (30 min) | el grafo dibujado, y qué está hecho y qué no |
| 7 · Simulacro | 5 h | `/sincronizar` (30 min) · agente `tribunal` (1 h) · `/grill-me` (1 h) · lista escrita de límites (45 min) · exposición de 15-20 min cronometrada, dos veces (1 h 30) | la lista de límites y una exposición que cabe en el tiempo |

## Cómo se ordenan las ideas

1. **Por qué** (día 1): sin eso no se sabe qué defender.
2. **Qué datos** (días 2-3): qué hay, qué calidad tiene y por qué cambió el proyecto.
3. **Qué puede salir mal** (día 4): las trampas son lo que el tribunal pregunta cuando
   quiere saber si has entendido el dato.
4. **Cómo se construye** (días 5-6): código y arquitectura, ya con el porqué claro.
5. **Defensa** (día 7): preguntas hostiles y tiempo.

## Adaptaciones respecto al plan original

- Todo `demo/…` pasa a su ruta en `src/` (tabla en [README.md](README.md)).
- Día 4: el plan hablaba de «las 6 fichas»; el repo tiene 22. Se estudian a fondo las
  6 primeras y se hojean las otras 16.
- Día 6: «saber qué falta por implementar» ya no es «casi todo»: es una lista corta y
  concreta (`docs/00_tema_y_alcance.md:74-112`).
- Día 3: la reformulación de `docs/06` (buses como sensores) está **superada** por su
  propia sección «Qué quedó del veredicto» (`docs/06:87`). Contrastado el 26/11 con
  `origin/develop` (versión de referencia): las cifras coinciden; ver `decisiones_pendientes.md` (a).
- Los comandos que necesitan red (`ingest.explore`) los ejecutas tú.
