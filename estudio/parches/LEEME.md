# Parche de sincronización de `docs/` (no aplicado)

`docs_sincroniza.patch` recoge los cambios **mecánicos** de
[`../auditoria_docs.md`](../auditoria_docs.md). Se generó el 27/11/2026 sobre
`origin/develop` (`d276d57`) en un `git worktree` temporal, ya eliminado. **Nada de
`docs/`, `README.md` ni `.claude/` se ha modificado en este repo**: el parche solo
existe como fichero.

## Cómo aplicarlo (en tu ordenador principal)

```powershell
git switch develop ; git pull
git apply --check estudio/parches/docs_sincroniza.patch   # no escribe nada
git apply estudio/parches/docs_sincroniza.patch           # aplica
git diff --stat                                           # revisa antes de commitear
```

Si `develop` ha cambiado esos ficheros desde el 27/11, `--check` fallará: usa
`git apply --3way estudio/parches/docs_sincroniza.patch` y resuelve a mano.
Para aplicar solo parte: `git apply --include='docs/05*' estudio/parches/docs_sincroniza.patch`.

## Qué hace cada fichero

| Fichero del parche | Cambio | Hallazgo (`auditoria_docs.md`) |
|---|---|---|
| `docs/01_viabilidad_fuentes_valencia.md` | El hallazgo ② ya no dice «desfase fijo»: remite a `docs/05` §1 y a la ficha 002 | 1 |
| `docs/01_viabilidad_fuentes_valencia.md` | Latencia p50 36 s marcada como superada por la de 23 s de `docs/05` §2 | 13 |
| `docs/01_viabilidad_fuentes_valencia.md` | Sección 9: `python explore.py`/`selftest.py`/`collect.py` pasan a `uv run python -m project.ingest.…` y `pytest tests/test_ingest.py tests/test_tracking.py`; el anexo deja de citar «24 tests» | 4, 12 |
| `docs/05_hallazgos_primera_captura.md` | «Qué falta para el go/no-go» pasa a «Qué faltaba» y remite a `docs/06` | 8 |
| `docs/05_hallazgos_primera_captura.md` | `returnGeometry=false`: de «pendiente de decidir» a «decidido, ADR-017» | 9 |
| `docs/05_hallazgos_primera_captura.md` | ~147 MB/día y ~13 GB a 90 d marcados como proyección superada por la bitácora 056 | 5 |
| `docs/06_veredicto_capas_trafico.md` | «Era el plan B» → «Era la alternativa a la 192» (el plan B del proyecto es Renfe) | nota de la auditoría |
| `README.md` | El árbol de `docs/` lista `03`…`07`, `09`, `11`, los HTML y `bitacora/` | 11 |
| `docs/00_tema_y_alcance.md` | «Documentos relacionados» añade `fig_trafico_vs_buses.html` | 11 |
| `.claude/trampas/002`, `003` | Quitan el número de línea de `sources.py` (se había desplazado); citan por nombre | N1 |
| `.claude/trampas/004` | Aclara que el selftest del demostrador vive hoy en `tests/test_tracking_identidad.py` | N5 |
| `docs/02`, `docs/03`, `docs/04` | Solo en el **aviso de vigencia** (no se reescribe el cuerpo): la UI es NiceGUI, no Streamlit | N2 |
| `docs/04_propuesta_para_tutor.md` | Aviso de vigencia: el tráfico se sondea cada 5 min (192) y 15 min (188), no «60 s / 5 min» | N4 |

## Qué NO incluye, a propósito

- **Hallazgo 10** (cifras de la capa 188: 394/358/354/355). Hay que remedir sobre la
  captura, que no está en este equipo.
- **N3** (dos formulaciones de la pregunta de investigación): decisión tuya.
- **Kafka para el servido** (ADR-016 revisable): decisión tuya.
- El cuerpo de `docs/04` («24 comprobaciones», «Streamlit», «60 s»): es la propuesta
  tal como se envió; su aviso de vigencia ya lo cubre y solo se amplía.
- `docs/07` (ADR-003, 147 MB/día): su nota del 15/10 ya lo recoge.

## Verificado

Con el parche aplicado en el worktree temporal:

- `uv run pytest .claude/tests -q` → **756 passed, 2 skipped**.
- `uv run pytest tests -q` → **424 passed, 5 xfailed** (200 s).
- `git apply --check` sobre `develop` → correcto.
