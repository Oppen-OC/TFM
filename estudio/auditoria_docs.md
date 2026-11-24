# Auditoría de la documentación frente al código

Verificada el 24/11/2026 y **reactualizada el 26/11/2026** tras integrar `3a73904`
(«docs: sincroniza docs/ con el código», en `origin/develop`) sobre la rama
`estudio/defensa`. **Cada hallazgo de la auditoría previa se ha vuelto a comprobar** contra
esta rama, y varios ya están resueltos aquí: la auditoría previa se hizo sobre un estado
anterior (`main`). **No se ha modificado ningún documento**: los cambios van como
«Diffs propuestos, no aplicados» al final.

**Efecto de `3a73904`:** cierra la cadencia del tráfico en `docs/01:277-280` (parte de
N4; **sigue viva en `docs/04:100`**), reescribe la fila del GTFS de `docs/00:128`, añade 08,
10 y `12_flujo_memoria.mmd` a los relacionados de `docs/00` (el hallazgo 11 sigue vivo:
falta `fig_trafico_vs_buses.html`), anota la UI NiceGUI en `docs/00:97` (no toca N2) y
la ficha 005 recoge el 364 y el 366 duplicados (414 filas, mismos 410 tramos). Desplaza
+2 las líneas de `docs/00` posteriores a la 94; las citas de `estudio/` ya están
corregidas.

Regla (`CLAUDE.md`): si el código contradice a la documentación, gana el código. Los
datos medidos (bitácora) ganan a las proyecciones.

## Resumen

| Estado | Hallazgos |
|---|---|
| ✅ Resuelto en esta rama | 2, 3, 6, 7, 14 |
| 🟡 Resuelto con aviso de vigencia, pero el cuerpo conserva la versión vieja | 1, 4, 5 |
| 🔴 Vigente | 8, 9, 10, 11, 12, 13 |
| 🆕 Hallados al reverificar | N1-N5 |

## Hallazgos de la auditoría previa

| # | Dónde | Dice | El código/datos dicen | Gana | Propuesta | Estado |
|---|---|---|---|---|---|---|
| 1 | `docs/01_viabilidad_fuentes_valencia.md:103-112` (hallazgo ②) | La `fecha` va 2 h adelantada, «en invierno será de 1 h»: un desfase fijo | `docs/05_hallazgos_primera_captura.md:17-62`, ficha 002 y `src/project/ingest/sources.py:78-123`: la fuente **alterna** UTC y hora local por sondeo (342 cambios en 1.236 sondeos); un desfase fijo deja 20,3 % de filas 2 h mal | Código y `docs/05` | Añadir nota en el propio ②, no solo en el aviso de `docs/01:10-14` (que ya lo advierte) | 🟡 |
| 2 | `docs/00_tema_y_alcance.md` «Estado actual» y «Lo urgente» | Captura de 24 h sin marcar; `httpx scipy pyarrow duckdb` sin marcar; última actualización 15/08 | `docs/00:3` dice «Última actualización: 24/11/2026»; `docs/00:79-98` marca hecho casi todo; `pyproject.toml:7,9,13,19,20,22` incluye duckdb, httpx, pyarrow, scipy, shap y xgboost | `docs/00` actual | Ninguna | ✅ |
| 3 | `docs/00`, `docs/04`, `README.md`, `CLAUDE.md` plantean fusión; `docs/06` concluía que no era contrastable | 8 de 409 tramos cambian en un lunes (192); 1 de 294 snapshots (188) | `docs/06:9-14` (aviso) y `docs/06:87-165` reescriben el veredicto: la 188 sigue congelada, la 192 se anima en periodo lectivo, y la hipótesis **se contrastó** (ADR-024; 192 no aporta en la primaria) | `docs/06` actual y ADR-024 | Ninguna en la rama. **Verificar con la versión del otro equipo** (decisiones_pendientes.md, a) | ✅ |
| 4 | `docs/01:374,399`; `docs/04:153` (y el anexo de `docs/01`) | «24 comprobaciones/tests» | El selftest no existe: ADR-009 (`docs/07_decisiones.md:194-231`) lo portó a `tests/test_ingest.py` y `tests/test_tracking*.py`. `README.md` y `demo/README.md` no contienen esa cifra (`demo/` no existe) | Código | Los avisos `docs/01:19-20` y `docs/04:5-12` ya lo dicen; el cuerpo mantiene «24» | 🟡 |
| 5 | `docs/05:150` y `docs/07_decisiones.md:69` | ~147 MB/día, ~13 GB a 90 d (medido de noche, 76,7 MB en 12,5 h) | `docs/06:7`: 417,9 MB en ~42 h → ~239 MB/día → ~21 GB a 90 d (cálculo propio: 417,9 / 42 × 24 × 90). Y lo medido sobre el corpus entero es otra cosa: 433 MB en Parquet y 2,57 GB de crudo comprimido (`docs/bitacora/056*.md`); la geometría sin repetir recortó el crudo (ADR-017) | Bitácora 056 (medido) | Marcar 147 MB/día y 13 GB como proyección superada y citar 056. La nota del 15/10 de ADR-003 (`docs/07_decisiones.md:72-78`) ya lo hace para el Parquet | 🟡 |
| 6 | `docs/01`, `docs/03`, `docs/04`: «Parquet particionado por fuente y día» frente a «no fijado» en `docs/07` Pendientes | — | `docs/07_decisiones.md:80-90`: **cerrado el 30/09/2026**, por fecha en todas las capas; `docs/07_decisiones.md:1141-1152` ya no lo lista | `docs/07` | Ninguna | ✅ |
| 7 | `docs/03`, `docs/04`, `docs/05`: Kafka/Redpanda | Ausente del código y de `docker-compose.yml` (solo comentarios: `src/project/ingest/collect.py:39,42`) | ADR-016 (`docs/07_decisiones.md:429-486`): Kafka descartado de la captura, opcional para el servido; avisos en `docs/03:9`, `docs/02:10-12`, `docs/05:59`; `docker-compose.yml` no contiene la palabra Kafka | ADR-016 | `docs/04:112` (arquitectura) conserva Kafka; está cubierto por su aviso de vigencia | ✅ |
| 8 | `docs/05_hallazgos_primera_captura.md:169-176` «Qué falta para el go/no-go» | Las preguntas 2-4 del diagnóstico «siguen sin responder» | Respondidas en `docs/06` (capas 192 y 188, el lunes 17, y luego el corpus entero) | `docs/06` | Reemplazar la sección por un puntero (diff 8) | 🔴 |
| 9 | `docs/05:154` | `&returnGeometry=false` «pendiente de decidir» | ADR-017 (`docs/07_decisiones.md:487`) **cerrada**; implementado en `src/project/ingest/sources.py:171-174` (`url_sin_geometria`) y usado en `src/project/ingest/collect.py:271` | Código | Cambiar «Pendiente de decidir» por «Decidido: ADR-017» | 🔴 |
| 10 | Capa 188: `docs/01:30,131` (394 filas); `docs/01:140` (358 de 394 con lectura); `docs/04:34,100` (394); `docs/06:50-51,122` (354 con lectura válida) y `docs/06:51` («3 de 355») | 394 / 358 / 354 / 355 | Coherente entre `docs/01` y `docs/06` en `develop`; **no re-medible aquí** (no hay `data/curated` ni `data/reference`). Las cifras cuentan cosas distintas (filas, filas con lectura ≠ −1, puntos distintos) y `docs/06` mezcla 354 y 355 en la misma tabla | Datos | Medir en el equipo con captura y fijar una cifra por concepto; hasta entonces no citar ninguna sin su definición | 🔴 |
| 11 | `README.md:81-86` (estructura) y `docs/00:~157-180` (documentos relacionados) | `README.md` lista solo `docs/00`-`02`; `docs/00` no lista `fig_trafico_vs_buses.html` | Existen `docs/03`-`07`, `09`, `11`, `12_flujo_de_datos.html`, `fig_trafico_vs_buses.html` (`Glob docs/*`). `docs/00` lista 01-12 (desde `3a73904` también 08, 10 y `12_flujo_memoria.mmd`) y bitácora; sigue faltando el HTML de `fig_trafico` | Árbol de ficheros | Ver diff 11 | 🔴 |
| 12 | `docs/01:371,374,375` | `python explore.py`, `python selftest.py`, `python collect.py` sin `demo/` | Ni `demo/` ni `selftest.py` existen: son `uv run python -m project.ingest.explore`, `…collect` y `pytest` (README `## Quickstart`; ADR-009) | Código | Ver diff 12 (o dejar solo el aviso de `docs/01:19-20`) | 🔴 |
| 13 | `docs/01:67` | Latencia EMT p50 36 s, p90 44 s, máx 80 s «una vez corregida la zona horaria» | `docs/05:51,70`: p50 23 s, p90 39 s, máx 477 s, medidos tras `resolver_convencion` sobre 10 h 40 min. La de `docs/01` es de una ventana de 15 min con la corrección de desfase fijo (la que la trampa 002 invalida) | `docs/05` | Añadir «(superada: 23 s, `docs/05` §2)» en `docs/01:67`; no está en el aviso de vigencia | 🔴 |
| 14 | `docs/02:17` | Pipeline de 3 stages con CSV (el encargo decía «hoy son 4 stages») | `dvc.yaml`: **20 stages**, Parquet (`dvc.yaml:24-400`). `docs/02:7-12` ya lo avisa («veinte stages»). La cifra del encargo («4 stages») también estaba obsoleta | `dvc.yaml` | Ninguna | ✅ |

Notas de la auditoría previa:

- `docs/05` repite contenido de las fichas 002 (§1), 005 (§3) y 006 (§5). Las fichas son el
  registro canónico (`.claude/trampas/README.md`); `docs/05` es la medición. Conviene que
  `docs/05` remita a la ficha y no duplique la explicación.
- `docs/06:58` llama «plan B» a la capa 188 («Era el plan B. También está muerto.»), pero el
  plan B del proyecto es **Renfe** (`docs/00:132-139`). Es una acepción distinta del término
  dentro de un documento que ya aclara el resto; propuesta: «era la alternativa» (diff 13).

## Hallados al reverificar (no estaban en la auditoría previa)

| # | Dónde | Dice | El código dice | Gana | Propuesta |
|---|---|---|---|---|---|
| N1 | `.claude/trampas/002-emt-alterna-convencion-horaria.md` (sección *Guardia*) y `.claude/trampas/003-raiz-renfe-es-objeto.md` (sección *Guardia*) | `resolver_convencion()` en `sources.py:69`; `parse_renfe()` en `sources.py:335` | `resolver_convencion` está en `src/project/ingest/sources.py:78`; `parse_renfe`, en `:391`. Las líneas de las fichas están desplazadas | Código | Citar por nombre, no por línea, o corregir las líneas. `.claude/tests/test_memoria.py` guarda deriva de documentación; no cubre estas |
| N2 | `docs/02:17`, `docs/03:159`, `docs/04:114` | UI Streamlit | La UI es NiceGUI (`src/project/ui/app.py:4`); `pyproject.toml` y `README.md` no mencionan Streamlit | Código | Los avisos de vigencia de `docs/02`, `03` y `04` no citan el cambio de UI; añadirlo |
| N3 | `docs/00:18-21` frente a `docs/04:21-25` | Dos formulaciones de la pregunta de investigación: «cuánto del retraso se explica por la congestión…» frente a «cuánta información anticipatoria… y hasta qué horizonte» | `CLAUDE.md` adopta la de `docs/00`. Son compatibles, pero la propuesta al tutor y la oficial difieren; el tribunal puede preguntarlo | `docs/00` y `CLAUDE.md` (vigente) | Tener claro cuál se defiende y por qué cambió (decisiones_pendientes.md) |
| N4 | `docs/04:100` | Sondeo del tráfico «60 s / 5 min» | `src/project/ingest/sources.py` fija `period_s=300` (192) y `period_s=900` (188); `README.md` dice 5 min y 15 min, y la nota del 15/10 de ADR-003 (`docs/07_decisiones.md:72-76`) ya dice que «el colector lo hace cada 5 min» | Código | Añadirlo al aviso de vigencia de `docs/04` |
| N5 | `.claude/trampas/004-sort-inestable-en-snapshot.md:12` | «El selftest reportaba ~11 % de precisión» | El selftest ya no existe (ADR-009); la medición vive en `tests/test_tracking_identidad.py` | Código | Aclarar «el selftest del demostrador (hoy `tests/`)» |

## Diffs propuestos, no aplicados

Cambios mecánicos para los hallazgos 1, 4, 8, 11 y 12 (más 9, 13 y N1, que son igual de
mecánicos). El 2 y el 14 ya están resueltos en esta rama y no necesitan diff. **Ninguno
se ha aplicado**; están en forma de antes/después, no de parche, para no dar por bueno un
número de línea.

### Diff 1 · `docs/01_viabilidad_fuentes_valencia.md`, hallazgo ② (l. 103)

```diff
-**② El campo `fecha` va dos horas adelantado.**
+**② El campo `fecha` no tiene un desfase fijo: alterna dos convenciones.**
+
+> Primera lectura (15/08, 15 min de muestra): parecía +2 h en verano y +1 h en invierno.
+> Con el corpus entero, la fuente **alterna** UTC y hora local sellada como UTC de un
+> sondeo al siguiente (`05_hallazgos_primera_captura.md` §1; ficha 002). Un desfase fijo
+> deja el 20 % de las filas 2 h desplazadas.
```

### Diff 4 · «24 comprobaciones»

```diff
 # docs/01_viabilidad_fuentes_valencia.md:374
-2. Ejecuta `python selftest.py`. Deben salir las 24 comprobaciones en verde.
+2. Ejecuta `uv run pytest tests/test_ingest.py tests/test_tracking.py -q`: las
+   comprobaciones del demostrador viven hoy ahí (ADR-009).
 # docs/01_viabilidad_fuentes_valencia.md:399
-- 24 tests que corren sin red.
+- Tests que corren sin red (`tests/test_ingest.py`, `tests/test_tracking.py`).
 # docs/04_propuesta_para_tutor.md:153
-(24 comprobaciones automáticas), pipeline DVC definido y esqueleto de servicio en
+(comprobaciones automáticas, hoy en `tests/`), pipeline DVC definido y esqueleto de servicio en
```

(`docs/04` es «la propuesta tal como se envió»: su aviso de vigencia ya cubre esto. Si se
prefiere no tocarla, aplicar solo en `docs/01`.)

### Diff 8 · `docs/05_hallazgos_primera_captura.md:169-176`

```diff
-## Qué falta para el go/no-go
-
-Las preguntas 2, 3 y 4 del diagnóstico **siguen sin responder**: esta ventana es
-casi toda noche de sábado a domingo, sin hora punta de laborable. [...]
+## Qué faltaba para el go/no-go
+
+Resuelto: las preguntas 2-4 se respondieron en
+[`06_veredicto_capas_trafico.md`](06_veredicto_capas_trafico.md) (ventana con el lunes 17
+completo) y se revisaron con el corpus entero (ADR-024, bitácora 057).
```

### Diff 9 · `docs/05_hallazgos_primera_captura.md:154`

```diff
-... añadir `&returnGeometry=false` a la consulta a partir del segundo sondeo [...]
-dejando el total en ~2-3 GB. Pendiente de decidir: el crudo verbatim tiene valor
-probatorio para la memoria.
+... añadir `&returnGeometry=false` [...]
+Decidido: ADR-017 (`07_decisiones.md`). Los cuatro primeros días (15-18/08) conservan
+la geometría en el crudo y mantienen su valor probatorio.
```

### Diff 11 · `README.md` (estructura) y `docs/00` (relacionados)

```diff
 # README.md, árbol ./docs/ (l. ~82-84)
 │   ├── 00_tema_y_alcance.md # decisiones tomadas y estado del trabajo
 │   ├── 01_viabilidad_fuentes_valencia.md
-│   └── 02_exploracion_de_temas.md
+│   ├── 02_exploracion_de_temas.md
+│   ├── 03_… 07_decisiones.md, 09_gtfs_emt.md, 11_auditoria_tests.md
+│   ├── fig_trafico_vs_buses.html · 12_flujo_de_datos.html
+│   └── bitacora/            # lo medido, lo descartado, lo aceptado
 # docs/00_tema_y_alcance.md, lista «Documentos relacionados»
+- [`fig_trafico_vs_buses.html`](fig_trafico_vs_buses.html) — tres paneles, mismo día: la
+  flota se mueve, las dos capas de tráfico no (agosto, `06_veredicto…`).
```

### Diff 12 · `docs/01_viabilidad_fuentes_valencia.md:371-375`

```diff
-1. Descomprime el demostrador y ejecuta `python explore.py`. [...]
+1. Ejecuta `uv run python -m project.ingest.explore`. [...]
-3. Lanza `python collect.py --minutes 1440` y **déjalo 24 horas**. [...]
+3. Lanza `uv run python -m project.ingest.collect --minutes 1440` y **déjalo 24 horas**. [...]
```

### Diff 13 · `docs/01:67` y `docs/06:58`

```diff
 # docs/01_viabilidad_fuentes_valencia.md:67
-- **Latencia del dato: p50 36 s, p90 44 s, máximo 80 s** una vez corregida la
+- **Latencia del dato: p50 36 s, p90 44 s, máximo 80 s** (superada: p50 23 s con la convención por sondeo, `05_hallazgos_primera_captura.md` §2) una vez corregida la
 # docs/06_veredicto_capas_trafico.md:58
-Era el plan B. También está muerto.
+Era la alternativa a la 192. También está congelada.
```

### Diff N1 · fichas 002 y 003

```diff
-`resolver_convencion()` en `src/project/ingest/sources.py:69`.
+`resolver_convencion()` en `src/project/ingest/sources.py`.
-`parse_renfe()` en `src/project/ingest/sources.py:335`
+`parse_renfe()` en `src/project/ingest/sources.py`
```
