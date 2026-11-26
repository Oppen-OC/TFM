# Material de estudio para la defensa del TFM

Siete días, de 4 a 5 h cada uno, para estudiarse el proyecto de principio a fin.
Orden: del porqué → datos → calidad del dato → trampas → código → arquitectura →
simulacro. **Cada día acaba con preguntas de control; si no sabes responderlas, no
pases al siguiente.**

Escrito el 24/11/2026 sobre la rama `estudio/defensa`, creada desde `oppen/estudio`
(HEAD `c73d030`, derivada de `develop`). Todo está en este directorio: no se ha
tocado nada fuera de `estudio/`.

## Progreso

| Día | Tema | Fichero | Hecho |
|---|---|---|---|
| 1 | El porqué: tema, pregunta y alcance | [dia_1_porque.md](dia_1_porque.md) | ☐ |
| 2 | Las fuentes | [dia_2_fuentes.md](dia_2_fuentes.md) | ☐ |
| 3 | Calidad del dato y el giro del proyecto | [dia_3_calidad_y_giro.md](dia_3_calidad_y_giro.md) | ☐ |
| 4 | Las trampas | [dia_4_trampas.md](dia_4_trampas.md) | ☐ |
| 5 | El ETL | [dia_5_etl.md](dia_5_etl.md) | ☐ |
| 6 | Pipeline y arquitectura | [dia_6_pipeline_arquitectura.md](dia_6_pipeline_arquitectura.md) | ☐ |
| 7 | Simulacro | [dia_7_simulacro.md](dia_7_simulacro.md) | ☐ |

Otros ficheros:

- [00_plan_7_dias.md](00_plan_7_dias.md): el plan con orden y tiempos.
- [auditoria_docs.md](auditoria_docs.md): incoherencias entre `docs/` y el código, y
  diffs propuestos (no aplicados).
- [decisiones_pendientes.md](decisiones_pendientes.md): lo que decides tú o llevas al
  tutor.
- [puertas/017-puerta-convencion-horaria-emt.md](puertas/017-puerta-convencion-horaria-emt.md):
  la pregunta de comprensión previa a esta tarea, con tus respuestas y su corrección.

## Cómo usarlo

1. Cada día: lee **en el orden indicado**, ejecuta los comandos, contesta las
   preguntas **por escrito en «Mis respuestas / dudas» antes de mirar la respuesta
   modelo**, y haz el ejercicio.
2. Compara con la respuesta modelo. Las respuestas llevan `fichero:línea`; si no
   cuadra con lo que ves, **gana el código** (regla de `CLAUDE.md`) y lo anotas en
   «dudas».
3. Las respuestas modelo son cortas a propósito: son el núcleo, no el guion.
4. Los números de línea son de esta rama el 24/11/2026. Si el código cambia, se
   desplazan.

## Qué cambia respecto al encargo original (léelo)

El encargo se escribió pensando en el estado de `main`. Esta rama (`develop`) tiene
mucho más. Lo que afecta al estudio:

| El encargo decía | En esta rama |
|---|---|
| `src/project/` casi vacío; lo que funciona vive en `demo/` | `src/project/` está completo y `demo/` **no existe**: ADR-009 (`docs/07_decisiones.md:194`) lo portó entero a `src/` y `tests/` |
| `demo/selftest.py`, 30 comprobaciones | Sus comprobaciones viven en `tests/` (`test_ingest.py`, `test_tracking*.py`) |
| 6 trampas | **22** fichas en `.claude/trampas/`; las 6 primeras son las del plan, las otras 16 se leen en el día 4 de pasada |
| Hay que dibujar la arquitectura de memoria porque falta el código | El código existe; faltan cosas concretas (día 6) |
| Solo existe `docs/fig_trafico_vs_buses.html` | Además: `docs/12_flujo_de_datos.html` (flujo por etapa con sus guardias), `figuras/`, `dashboard/` |

Equivalencias `demo/` → `src/` (de `docs/07_decisiones.md:194-231`):

| Antes | Ahora |
|---|---|
| `demo/sources.py` | `src/project/ingest/sources.py` |
| `demo/collect.py` | `src/project/ingest/collect.py` |
| `demo/reprocesar.py`, `demo/explore.py` | `src/project/ingest/` |
| `demo/track.py` | `src/project/tracking.py` |
| `demo/diagnose.py` | `src/project/analysis/diagnose.py` |
| `demo/selftest.py` | `tests/test_ingest.py` + `tests/test_tracking*.py` |

## Entorno

`uv` no está en el PATH de Git Bash: usa PowerShell. En este worktree no existe
`.venv` (se crea con `uv sync`). Los comandos con red (`ingest.explore`) los lanzas
tú; yo no los he ejecutado.
