# 11 · Auditoría de validez de los tests

**Commit auditado:** `fc5d15c` (`src/` y `tests/` limpios) · **Fecha:** 2026-09-17
· **Método:** [ADR-011](07_decisiones.md) · **Alcance:** fase 1, diagnóstico sin
tocar `src/project/` (secciones 1-5); fase 2, guardias para los huecos sobre
`c6e02cc`, sin tocar el código de producción (sección 6)

La pregunta no es si los tests pasan —pasan: 69 `passed`, 4 `xfailed`— sino si
**detectarían** un fallo real en los tres ejes que sostienen el TFM: validez del
dato, reconstrucción de la identidad de los autobuses y persistencia del corpus.
Un test verde que no discrimina es peor que su ausencia, porque da una garantía
que no existe.

## Resumen

Estado en `fc5d15c`, antes de la fase 2. Tras ella: **33 detectados, 0 huecos,
3 equivalentes**, y las guardias de las trampas 001, 004 y 008 verificadas
(sección 6).

| Eje | Resultado | Gravedad |
|---|---|---|
| Persistencia del corpus | **Ningún dato perdido**: 95.343 payloads íntegros, 0 miembros gzip rotos, todo sondeo curado tiene su crudo. `_TRUNCADOS.txt` sobrestimaba la pérdida. Pero **ningún test** guarda esta capa: 9 de 9 mutantes pasan inadvertidos | alta (sin guardia) |
| Guardias de trampas cerradas | De 7 trampas `cerrada`, **4 guardias funcionan** (002, 003, 007, 009). La de la **008 no detecta** que se deshaga su arreglo; la de la **004 quedó inerte** al actualizar numpy; la de la **001** comprueba el fixture, no el código | alta |
| Tracking contra realidad | La flota simulada **nunca para y apenas gira**; los buses reales están parados en el **29 %** de los pasos y giran con p90 de **57°**. Con paradas y giros realistas, el tracker produce **2-4 saltos de identidad** que ningún test ve | alta |
| Parsers | 9 de 13 mutantes de fuentes detectados o equivalentes. Huecos: filas sin `idtramo` en las dos capas de tráfico (trampa 005), `ts_utc` de Renfe y la horquilla de latencia ampliada a 2 h | media |
| Global | 36 mutantes: **16 detectados, 16 huecos, 4 equivalentes** | — |

## Controles de la propia auditoría

Una auditoría que no se controla a sí misma es otra fuente de alucinaciones.

- **Suite de referencia** sobre el worktree sin mutar: 73 tests, todos `passed` o
  `xfailed`.
- **`import project` resuelve al worktree**, no al paquete editable del árbol
  principal. Sin esto, los mutantes se probarían contra el código original y todo
  saldría "no detectado".
- **Sondas deterministas:** dos ejecuciones sin mutar dan hashes idénticos.
- **Mutante nulo:** equivalente, como debe.
- **Control positivo:** el previsto era el bug histórico `d92a9af`, y **falló**:
  salió equivalente. No era un fallo del runner sino de la premisa (ver 2.2).
  Se sustituyó por el mutante 002, determinista; se detecta.
- **Generador de escenarios:** con todos los fenómenos apagados reproduce
  `simular_flota()` fila a fila.
- **Lectura rápida del crudo** contra `read_raw()` sobre el fichero del 24/08:
  2.819 payloads en ambos.

## 1. Persistencia: `raw/` frente a `curated/`

```bash
uv run python -m project.analysis.auditar_persistencia --csv auditoria/resultados/persistencia_fc5d15c.csv
```

17 días × 5 fuentes. Resultados en `auditoria/resultados/persistencia_fc5d15c.txt`.

| fuente | miembros íntegros | rotos | huecos de ceros | curados | pérdida al reprocesar | curados sin crudo | en partición ajena |
|---|---|---|---|---|---|---|---|
| emt_buses | 42.080 | 0 | 1 | 40.943 | 0 | 0 | 458 |
| renfe_cercanias | 40.464 | 0 | 3 | 30.649 | 0 | 0 | 0 |
| trafico_estado | 6.736 | 0 | 1 | 6.685 | 0 | 0 | 56 |
| trafico_intensidad | 1.833 | 0 | 1 | 1.819 | 0 | 0 | 10 |
| valenbisi | 4.230 | 0 | 1 | 4.206 | 0 | 0 | 27 |

**1.1 · `_TRUNCADOS.txt` confundía `zcat` con Python.** El fichero de la EMT del
24/08 da 2.400 líneas con `zcat` y 2.819 con `gzip.open`. Tras el miembro 2.400
hay **2.028 bytes a cero**, no un miembro truncado: el relleno que deja un corte
de corriente sobre un bloque asignado y no escrito. GNU `gzip` lo toma por basura
final y para; el lector de Python salta el relleno de ceros entre miembros y
sigue. Los 7 ficheros de la lista tienen exactamente ese patrón y ningún miembro
roto. **`reprocesar` no pierde nada.** La afirmación de la nota ("`gzip.open()`
de Python hace lo mismo") es falsa en Python 3.11.

Lo que sí se pierde es lo que no llegó a escribirse: como mucho un sondeo por
hueco, 7 en total.

**1.2 · La partición `date=` no es fiable en la primera media hora UTC.** 551
sondeos curados —458 de la EMT— viven en la partición **del día anterior**, todos
capturados entre las 00:00 y las 00:29 UTC. `flush` fecha el volcado entero por
su primera fila. Ningún sondeo está duplicado entre particiones. Quien lea una
partición como "el día" se lleva media hora del siguiente y pierde la suya.
`reprocesar` sí particiona bien, así que reprocesar **cambia** el contenido de las
particiones sin perder filas.

**1.3 · Deduplicación.** Los curados de la EMT son un 2,7 % menos que los
payloads (42.080 → 40.943), no el ~15 % que anuncia el docstring de
`src/project/ingest/collect.py`. Cifra no investigada más allá: el curado también
descarta payloads vacíos.

## 2. Mutación dirigida

```bash
uv run python auditoria/mutar.py
```

Catálogo en `auditoria/catalogo.toml`, sondas en `auditoria/sondas.py`,
resultados en `auditoria/resultados/mutantes_fc5d15c.json`. 38 minutos.

### 2.1 Veredicto por mutante

| id | capa | trampa | rompe | veredicto |
|---|---|---|---|---|
| 000 | control | — | nada | equivalente ✔ |
| 001 | tracking | 004 | `sort_values` sin `kind="stable"` | **equivalente** (2.2) |
| 002 | fuentes | 001 | `snapshot_id` = gid máximo | detectado (control +) |
| 003 | fuentes | 002 | convención siempre local naive | detectado |
| 004 | fuentes | 002 | horquilla de latencia a 7.300 s | **hueco** |
| 005 | fuentes | 002 | desempate UTC/local invertido | equivalente |
| 006 | fuentes | — | epoch local sin reinterpretar | detectado |
| 007 | fuentes | 003 | Renfe sin filtro de núcleo | detectado |
| 008 | fuentes | — | `ts_utc` de Renfe = captura | **hueco** |
| 009 | fuentes | 005 | estado de tráfico conserva filas hueco | **hueco** |
| 010 | fuentes | 005 | intensidad conserva filas hueco | **hueco** |
| 011 | fuentes | — | centinela `-1` como lectura | detectado |
| 012 | fuentes | — | Valenbisi con horquilla de 900 s | equivalente |
| 013 | fuentes | — | signo de `latencia_s` | detectado |
| 014 | fuentes | — | haversine con lat/lon cruzadas | detectado |
| 015 | tracking | 007 | sin siembra por centroide | detectado |
| 016 | tracking | 008 | puerta solo sobre la predicha | **hueco** |
| 017 | tracking | 009 | extrapolación en pasos, no segundos | detectado |
| 018 | tracking | — | predicción desactivada | detectado |
| 019 | tracking | — | candidatos de los dos sentidos | detectado (solo por los xfail) |
| 020 | tracking | — | `HUECO_MAX_S` infinito | detectado |
| 021 | tracking | — | `tolerar_hueco` ignorado | detectado |
| 022 | tracking | — | `VEL_MAX_KMH` = 200 | **hueco** |
| 023 | tracking | — | candidato emparejado sigue vivo | detectado |
| 024 | tracking | — | `dist_m` desde la predicha | detectado |
| 025 | tracking | — | `dt = 0` tratado como 1 s | **hueco** |
| 026 | tracking | — | entrada en servicio hereda id | detectado |
| 027 | persistencia | — | parsear antes de guardar el crudo | **hueco** |
| 028 | persistencia | — | `append_raw` sobrescribe | **hueco** |
| 029 | persistencia | — | partición del crudo por reloj de pared | **hueco** |
| 030 | persistencia | — | deduplicador desactivado | **hueco** |
| 031 | persistencia | — | deduplicador sin olvido | **hueco** |
| 032 | persistencia | — | referencia con tramos repetidos | **hueco** |
| 033 | persistencia | — | `reprocesar` lee un solo día | **hueco** |
| 034 | persistencia | — | `reprocesar` no cuenta errores | **hueco** |
| 035 | persistencia | — | `read_raw` descarta el último | **hueco** |

Los tres equivalentes que no son control están justificados. 005 y 012 tocan
ramas a las que no llega ningún dato plausible: el desempate solo se evalúa si
UTC y local dan latencias válidas a la vez, imposible con un desfase de 1-2 h, y
Valenbisi descarta la etiqueta y el recurso de `DUDOSA` elige la misma serie.
001 se explica abajo.

### 2.2 Guardias de las trampas cerradas

| trampa | guardia citada en la ficha | ¿cae al deshacer el arreglo? |
|---|---|---|
| 001 | `test_gids_de_sondeos_consecutivos_son_disjuntos` | **no puede**: comprueba el fixture, no el código |
| 002 | `test_serie_con_convenciones_alternas_ninguna_fila_desplazada` | sí |
| 003 | `test_renfe_filtra_solo_nucleo_40` | sí |
| 004 | `test_tracker_predictivo_identidad_correcta` | **no**: el bug ya no se manifiesta |
| 007 | `test_convoy_en_fila_india_no_intercambia_identidad` | sí |
| 008 | `test_ningun_desplazamiento_supera_la_puerta_fisica` | **no** |
| 009 | `test_un_sondeo_que_falta_no_rompe_la_identidad` | sí |

**Trampa 004.** Con numpy 2.2.6, `argsort(kind="quicksort")` sobre un `int64`
ya ordenado con claves repetidas **permuta** filas; con numpy 2.4.6 en esta CPU
(AMD Zen 3) devuelve la identidad. `simular_flota()` entrega la flota ya ordenada
por `snapshot_id`, así que quitar `kind="stable"` hoy no cambia nada y la guardia
no puede caer. El arreglo sigue siendo correcto —la estabilidad no es una
garantía de quicksort— pero **la guardia dejó de guardar al actualizar
`uv.lock`**, sin que nada avisase. Comprobación:

```bash
uv run --no-project --with numpy==2.2.6 python -c "import numpy as np; a=np.repeat(np.arange(20),60); print((np.argsort(a,kind='quicksort')!=np.arange(1200)).any())"
```

**Trampa 008.** Evaluar la puerta solo sobre la posición predicha no altera
ningún test. Los cuatro escenarios de la guardia van a velocidad constante con
pasos de 30 s: predicción y posición real nunca divergen lo bastante. Con dos
sondeos perdidos a cadencia de 60 s (paso de 180 s), el mutante acepta **34
desplazamientos por encima de `SALTO_MAX_M`, hasta 1.442 m**; el original,
ninguno. Sobre datos reales esta trampa colaba 24-46 saltos imposibles por
ventana ([bitácora 003](bitacora/003-puerta-fisica-sobre-la-posicion-predicha.md)):
una regresión real pasaría la CI en verde.

### 2.3 Tests que no discriminan

Cero detecciones no significa decorativo si ningún mutante atacaba su invariante.
Se separan:

**No cayeron ante el mutante dirigido a lo que dicen vigilar:**

- `test_predictivo_mejora_al_ingenuo` — compara con `>=`: con la predicción
  desactivada (018) ambos empatan y pasa.
- `test_ningun_desplazamiento_supera_la_puerta_fisica` y
  `test_la_puerta_fisica_se_respeta_en_la_flota_simulada` — ver trampa 008.
- `test_un_vehicle_id_no_se_repite_dentro_de_un_snapshot` y
  `test_un_vehicle_id_no_se_repite_en_la_flota_simulada` — un candidato que
  sigue vivo tras emparejar (023) no llega a duplicar id en sus escenarios; lo
  detectan otros dos tests.
- `test_velocidades_dentro_del_rango_simulado` — con haversine roto (014) caen
  nueve tests y este no: la horquilla de 2 a 32 km/h admite casi cualquier cosa.
- Mezclar los dos sentidos (019) solo lo detectan los dos `xfail(strict=True)`
  del giro en cabecera, porque el mutante los "arregla". Si esos xfail se
  retiran al corregir el giro, nada vigilará la separación por trayecto.

**Sin mutante que los ataque en este catálogo** (fuera de alcance o por diseño):
`test_health_ok`, `test_diagnose_discrimina`, `test_iso_naive_de_renfe_a_utc`,
`test_parser_devuelve_filas`, `test_parser_tiene_ts_utc_y_ts_ingest_utc`,
`test_renfe_retraso_min_es_numerico`, `test_reconstruye_una_trayectoria_por_bus`,
`test_tasa_de_emparejamiento_por_encima_del_95`, `test_la_flota_limpia_no_se_fragmenta`,
`test_tolerar_hueco_es_lo_que_arregla_el_parcial` (fija `tolerar_hueco=0` a
propósito), `test_los_bloques_de_gid_son_contiguos` (fixture) y los dos `xfail`
de límites de identificabilidad.

## 3. La simulación frente a la captura real

```bash
uv run python -m project.analysis.auditar_supuestos --json auditoria/resultados/supuestos_fc5d15c.json
uv run python auditoria/escenarios.py --json auditoria/resultados/escenarios_fc5d15c.json
```

**3.1 · Magnitudes.** 13 días completos, cuatro ventanas de una hora (08, 11, 14
y 18 h local): 52 ventanas y 1.005.141 pasos. Mismo instrumento en ambos lados.

| magnitud | simulación | laborable | fin de semana |
|---|---|---|---|
| velocidad p10 / p50 / p90 (km/h) | 4,2 / 18,5 / 26,7 | 0,2 / 7,5 / 26,3 | 0,2 / 8,3 / 28,1 |
| **pasos parado** (< 1,2 km/h) | **0 %** | **29,2 %** | **28,4 %** |
| desplazamiento parado p50 / p90 | — | 2,0 / 6,7 m | 2,0 / 6,4 m |
| **giro p50 / p90** | 5,6° / **13,9°** | 8,7° / **56,9°** | 8,9° / **57,6°** |
| vecino de su (línea, trayecto) p10 / p50 | 496 / 1.389 m | 611 / 1.719 m | 796 / 2.129 m |
| vecino más cerca que el propio paso | 0,88 % | 0,53 % | 0,43 % |
| vehículos por grupo p50 / p90 | 7,5 / 8 | 3 / 6 | 2 / 5 |
| duración del paso p50 / p99 | 30 / 30 s | 31 / 33 s | 31 / 33 s |

La simulación es **más exigente** en densidad (grupos mayores, más encuentros) y
**mucho más fácil** en movimiento: línea recta a velocidad constante, que es
exactamente lo que el predictor supone.

**3.2 · Criterio 2c: inyectar cada fenómeno.** Generador calibrado contra la
columna laborable; 5 semillas × 2 longitudes (20 y 80 sondeos).

| escenario | calibración obtenida | saltos | contaminadas (máx.) | fragmentación | veredicto |
|---|---|---|---|---|---|
| ninguno | — | 0 | 0 % | 1,00 | inocuo |
| **paradas** | parado 28,6 % | **20** | **3,3 %** | 1,00 | **hallazgo** |
| ruido GPS (σ 2 m) | — | 0 | 0 % | 1,00 | inocuo |
| **giros** | giro p90 24° (real 57°) | **20** | **3,3 %** | 1,00 | **hallazgo** |
| cadencia irregular | paso p99 32 s | 0 | 0 % | 1,00 | inocuo |
| todos | parado 29,5 % · ruido 3,3 m | 10 | 3,3 % | 1,00 | hallazgo |
| estrés (×2) | — | 52 | 13,3 % | 1,00 | hallazgo |

Mecanismo, comprobado caso a caso: dos buses del mismo grupo coinciden a menos
de un paso (19-103 m, con pasos de 145-205 m) justo cuando uno **se detiene o
gira**. El predictor extrapola el movimiento anterior y asigna al parado la
posición del que pasa. Casi siempre se deshace en el sondeo siguiente —dos
saltos, una posición mal etiquetada y dos `vel_kmh` falsas—; en convoy no se
deshace. Es la zona de la trampa 007, alcanzada por otra vía.

Dos matices que acotan la cifra. Los giros están **subcalibrados** (24° frente a
57°) porque el p90 salta de 21° a 81° entre `p_giro` 0,08 y 0,12: el efecto real
puede ser mayor. Y la simulación tiene más encuentros que la realidad (0,88 %
frente a 0,53 %): no se extrapola una tasa de saltos por día real a partir de
estos números.

## 4. Anomalías del dato encontradas de paso

- **Capa 192: 412 filas con `idtramo`, 410 tramos.** Los tramos 211 y 216 llegan
  duplicados en cada sondeo (1.715 de 1.715 revisados), sin contradecir nunca su
  `estado`. El parser los conserva; todo agregado por filas cuenta esos dos
  tramos dos veces. Filas hueco: 34 en los 5.961 payloads medidos, constante.

## 5. Hallazgos y encaminamiento propuesto

Según `docs/bitacora/README.md`. Encaminamiento propuesto en la fase 1; lo
resuelto en la fase 2 está en la sección 6.

| # | hallazgo | destino |
|---|---|---|
| H1 | Persistencia sin ninguna guardia (9/9 huecos) | fase 2 · bitácora [011](bitacora/011-el-crudo-esta-integro-y-ningun-test-lo-guarda.md) |
| H2 | `_TRUNCADOS.txt` medido con `zcat`, no con Python | bitácora 011 · corregir la nota (está en `data/`, fuera de git) |
| H3 | Partición `date=` ajena en la primera media hora UTC | bitácora 011 · candidata a trampa (`prepare.py` la heredará) |
| H4 | Guardia de 008 no guarda | bitácora [012](bitacora/012-tres-guardias-de-trampas-cerradas-no-guardan.md) · ficha 008 a `mitigada` |
| H5 | Guardia de 004 inerte desde numpy 2.4.6 | bitácora 012 · ficha 004 a `mitigada` |
| H6 | Guardia de 001 comprueba el fixture | bitácora 012 · ficha 001: citar también `test_emt_snapshot_id_es_el_gid_minimo_del_bloque` |
| H7 | Tracker sin probar con paradas y giros; 2-4 saltos con ellos | bitácora [013](bitacora/013-la-flota-simulada-no-para-ni-gira.md) · escenario nuevo en fase 2 |
| H8 | Filas hueco de la 005 sin guardia (confirmado por mutación) | fase 2 |
| H9 | 410 tramos, 412 filas: 211 y 216 duplicados | bitácora [014](bitacora/014-la-capa-192-duplica-los-tramos-211-y-216.md) |
| H10 | `test_predictivo_mejora_al_ingenuo` con `>=`; horquilla 2-32 km/h | fase 2 |

## 6. Fase 2: guardias para los huecos

```bash
uv run python auditoria/mutar.py    # sobre c6e02cc
```

Cada test se escribió después de comprobar que pasa con el código de producción
intacto y falla con su mutante; después se volvió a ejecutar el catálogo entero.
`src/project/` no se tocó salvo `analysis/simulacion.py`, que gana fenómenos
apagados por defecto (flota por defecto idéntica a la de `fc5d15c`, verificado
fila a fila).

| | `fc5d15c` | `c6e02cc` |
|---|---|---|
| detectados | 16 | **33** |
| huecos | 16 | **0** |
| equivalentes | 4 | 3 |
| tests (passed / xfailed) | 69 / 4 | 91 / 9 |

El mutante 001 pasa de equivalente a detectado: la guardia nueva de la trampa 004
no depende del algoritmo de ordenación de numpy. Siguen equivalentes el control
nulo, 005 y 012 (justificados en 2.1).

| hueco | test que lo detecta ahora |
|---|---|
| 001 · sort inestable (004) | `test_rastrear_no_reordena_filas_dentro_del_sondeo` |
| 004 · horquilla de 2 h | `test_dato_rancio_se_marca_dudosa_en_vez_de_adivinar[1h]` |
| 008 · `ts_utc` de Renfe | `test_renfe_ts_utc_es_la_fecha_de_actualizacion_y_no_la_captura` |
| 009, 010 · filas hueco (005) | `test_filas_hueco_de_trafico_se_descartan` |
| 016 · puerta sobre la predicha (008) | `test_la_puerta_fisica_se_respeta_tras_sondeos_perdidos`, `test_salto_imposible_rompe_la_cadena[550m]` |
| 022 · `VEL_MAX_KMH` = 200 | `test_salto_imposible_rompe_la_cadena[550m]` |
| 025 · `dt = 0` | `test_sondeos_con_el_mismo_instante_no_rompen_la_cadena` |
| 027-035 · persistencia | `tests/test_persistencia.py` (8 tests) |

Además:

- `test_predictivo_mejora_al_ingenuo` compara con `>`.
- `test_read_raw_salta_el_relleno_de_ceros_entre_miembros` fija el hallazgo 1.1,
  sin mutante: protege un comportamiento de la biblioteca estándar del que
  depende el corpus.
- `tests/test_tracking_realismo.py` fija H7 como `xfail(strict=True)` en las
  semillas medidas, con test de discriminación (sin fenómenos no fallan) y de
  calibración (29 % parado). El tracker no se corrige: es trabajo aparte.
- Fichas 001, 004 y 008 apuntan a las guardias verificadas; la 005 pasa a
  `cerrada`. `_TRUNCADOS.txt` lleva la corrección anexada.

Siguen abiertos H3 (partición por primera fila en `flush`), H7 (el defecto del
tracker, ahora visible), H9 (duplicados 211 y 216) y la diferencia entre el
2,7 % de deduplicación medido y el ~15 % del docstring del colector.

## Limitaciones de esta auditoría

- **El catálogo lo escribió una persona.** Mide los fallos que se previeron. Un
  bug que nadie imaginó no está representado.
- **Mutantes de un solo punto.** No se prueban combinaciones.
- **Plataforma única** (Windows, Python 3.11.9, numpy 2.4.6, AMD Zen 3). El caso
  de la trampa 004 muestra que el resultado de un mutante puede depender de ella.
  En la CI (Ubuntu) no se ha ejecutado.
- **Las magnitudes reales salen de `rastrear()`**, así que heredan sus errores de
  identidad. Son medianas y percentiles sobre un millón de pasos: el 0,5 % de
  encuentros no las mueve de forma apreciable, pero no es cero.
- **Agosto.** Menos flota y menos tráfico que el servicio de invierno.
- `analysis/` y la API quedan fuera del catálogo.
