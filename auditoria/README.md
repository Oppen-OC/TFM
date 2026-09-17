# auditoria/

Validación de los tests del TFM. No es un test ni un stage de DVC: responde si la
suite **detectaría** un fallo real. Decisión y porqué en ADR-011 de
`docs/07_decisiones.md`; resultados de la primera ejecución en
`docs/11_auditoria_tests.md`.

| fichero | qué hace |
|---|---|
| `catalogo.toml` | mutantes dirigidos, cada uno atado a una trampa o invariante |
| `mutar.py` | aplica cada mutante en un worktree desechable, corre la suite y clasifica |
| `sondas.py` | hashes deterministas de salida para distinguir hueco de equivalente |
| `escenarios.py` | flota simulada con paradas, giros, ruido y cadencia reales |
| `resultados/` | salidas por commit auditado, `<qué>_<hash>` |

```bash
uv run python auditoria/mutar.py                    # ~40 min, fuera de CI
uv run python auditoria/mutar.py --solo 016 001     # algunos (los controles corren siempre)
uv run python auditoria/escenarios.py
uv run python -m project.analysis.auditar_supuestos       # lee data/curated
uv run python -m project.analysis.auditar_persistencia    # lee data/raw y data/curated
```

Cuándo ejecutarlo: antes de cerrar un capítulo, tras tocar `tracking.py` o los
parsers, y **tras actualizar dependencias**.

Añadir un mutante: que rompa algo que importe si se rompiera de verdad. Una
guardia nueva no se da por buena hasta que detecta su mutante.
