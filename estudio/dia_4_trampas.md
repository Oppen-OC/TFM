# Día 4 · Las trampas

## Objetivo del día

Saber qué es una trampa (un bug que **no da la cara**: no lanza excepción, produce
resultados plausibles y contamina en silencio), conocer a fondo las seis primeras y
su guardia, y saber hojear las otras dieciséis.

## Lecturas

En este orden:

1. `.claude/trampas/README.md`: el índice (22 filas) y *Cómo se usa* (criterio de
   admisión, estados `vigente`/`mitigada`/`cerrada`; «sin guardia no se cierra»).
2. Las seis fichas, **empezando por la 002** y siguiendo 001 → 003 → 004 → 005 → 006:
   - `.claude/trampas/002-emt-alterna-convencion-horaria.md`
   - `.claude/trampas/001-gid-no-identifica-vehiculo.md`
   - `.claude/trampas/003-raiz-renfe-es-objeto.md`
   - `.claude/trampas/004-sort-inestable-en-snapshot.md`
   - `.claude/trampas/005-filas-hueco-capa-trafico.md`
   - `.claude/trampas/006-posiciones-fuera-de-caja-no-son-error.md`
3. Cada guardia en su test (tabla de abajo). Lee el test entero: el fixture o el
   escenario sintético es la mitad de la guardia.
4. Hojear (una pasada de 2 min por ficha): 007-022. Del índice, retén las que
   encadenan con las seis (007-009, 013-014 del tracker; 010, 015 del etiquetado; 017 de
   la fuga de futuro; 018-022 de las fuentes).

## Comandos a ejecutar

En PowerShell, desde la raíz (si no hay `.venv`: `uv sync`). Equivale a
`python demo/selftest.py` del plan original, que ya no existe (ADR-009):

```powershell
uv run pytest tests/test_ingest.py tests/test_tracking_identidad.py tests/test_mapmatching.py -q
uv run pytest .claude/tests -q        # el andamiaje de agentes: fichas, memoria, catálogo
```

Para ver sólo las seis guardias:

```powershell
uv run pytest -q `
  "tests/test_ingest.py::test_emt_snapshot_id_es_el_gid_minimo_del_bloque" `
  "tests/test_ingest.py::test_serie_con_convenciones_alternas_ninguna_fila_desplazada" `
  "tests/test_ingest.py::test_renfe_filtra_solo_nucleo_40" `
  "tests/test_tracking_identidad.py::test_rastrear_no_reordena_filas_dentro_del_sondeo" `
  "tests/test_ingest.py::test_filas_hueco_de_trafico_se_descartan" `
  "tests/test_mapmatching.py::test_lejos_del_centro_pero_sobre_la_ruta_no_se_descarta"
```

**No ejecutes** `auditoria/mutar.py`: rompe a propósito cada invariante y tarda ~8 h
(`CLAUDE.md`, *Tests*). Léelo como idea, no como ejercicio.

## Las seis y su guardia

| # | Trampa en una frase | Guardia | Código |
|---|---|---|---|
| 001 | `gid` identifica al refresco, no al vehículo | `tests/test_ingest.py:251` `test_emt_snapshot_id_es_el_gid_minimo_del_bloque` | `sources.py:235` |
| 002 | la EMT alterna UTC y hora local de un sondeo al siguiente | `tests/test_ingest.py:108` `test_serie_con_convenciones_alternas_ninguna_fila_desplazada` | `sources.py:78-123` |
| 003 | la raíz de Renfe es un objeto; sin `nucleo == "40"` te llevas la flota nacional | `tests/test_ingest.py:143` `test_renfe_filtra_solo_nucleo_40` | `sources.py:391-400` |
| 004 | `sort_values` no es estable y rompe lo que se reengancha por posición | `tests/test_tracking_identidad.py:267` `test_rastrear_no_reordena_filas_dentro_del_sondeo` | `tracking.py:609` |
| 005 | 34 de 446 filas de la capa 192 no son tramos | `tests/test_ingest.py:225` `test_filas_hueco_de_trafico_se_descartan` | `sources.py:253` |
| 006 | posiciones al sur de 39,36° no son error: son las líneas 24 y 25 | `tests/test_mapmatching.py:331` `test_lejos_del_centro_pero_sobre_la_ruta_no_se_descarta` | `mapmatching.py:146` `emparejar()` (distancia al trazado) |

## Qué tienes que saber explicar

Para cada una: **síntoma**, **por qué se vuelve a caer aquí** y **guardia**.

**P1. Trampa 002: ¿por qué un desfase fijo deja filas mal sin dar la cara?**
(Es la pregunta de la puerta 017.) Porque el desfase no es fijo: el 79 % de los
sondeos llega en hora local sellada como UTC y el 21 % en UTC real; `zoneinfo` por
fecha arregla el 79 % y deja el 21 % dos horas desplazado. No hay error ni nulos: la
etiqueta de retraso sale falsa en una quinta parte y el modelo entrena y converge con
métricas creíbles. La guardia prueba las dos interpretaciones por sondeo y elige la de
latencia plausible; si ninguna lo es, `DUDOSA` (ficha 002; `sources.py:78-123`).

**P2. Trampa 001: ¿por qué la identidad de vehículo hay que inferirla?**
Porque `gid` es un autoincrement de una tabla que se trunca y reinserta entera en cada
refresco (intersección cero entre sondeos), y emparejar por rango dentro del bloque
acierta línea y trayecto solo en el 32-73 % de los casos (`tracking.py:1-10`). Sirve
únicamente como `snapshot_id`, y se toma el **mínimo** del bloque (`sources.py:235`).

**P3. Trampa 003: ¿por qué es peligrosa si el fallo parece de volumen normal?**
Olvidar el filtro de núcleo no da error: da la flota nacional, que parece un volumen
alto normal; y Renfe es la vía de escape (plan B), así que el parser mal filtrado
contamina justo ahí. Se suma la 019: completar a nulo también `nucleo` vacía el filtro
sin error (fichas 003 y 019).

**P4. Trampa 004: ¿qué tiene de especial que el bug estuviera en la medición?**
Que el selftest reportaba 11 % de precisión de tracking cuando la real era ~99 %: el
`sort_values` con quicksort reordenaba filas del mismo snapshot y el arnés reenganchaba
la verdad-terreno **por posición de fila**. La reacción natural era «arreglar» el
tracker, que estaba bien. Regla: no reenganchar por posición; `kind="stable"` y clave
de desempate (ficha 004; `tracking.py:609` ya usa `kind="stable"`). La guardia antigua
había caducado sin que nada cambiase: con numpy 2.4.6 quitar `kind="stable"` ya no
alteraba un byte; la nueva ordena una entrada desordenada, donde cualquier sort no
estable permuta (ficha 004, *Guardia*; bitácora 012). Reaparece como la 012 (columna
pegada por posición tras `rastrear`).

**P5. Trampa 005: ¿por qué el fixture no la delata?**
Porque el fixture de tráfico está recortado a tres filas reales y ninguna es hueco, así
que quitar el filtro no rompía ningún test; hubo que añadir un caso con filas hueco.
Denominador correcto: **410** tramos (412 filas con `idtramo`; el 211 y el 216 vienen
duplicados; desde el 22/09 también el 364 y el 366: 414 filas, mismos 410 tramos) (ficha 005; bitácoras 014 y 065).

**P6. Trampa 006: ¿por qué filtrar por caja geográfica sesga el resultado a favor de la
hipótesis?**
Porque las líneas 24 y 25, que bajan por la costa a El Perellonet, son de las peor
cubiertas por sensores de tráfico (20 % y 28 %): borrarlas deja una muestra de
corredores bien cubiertos e infla la utilidad aparente de la fusión, y con la etiqueta
intacta. Se filtra por distancia al trazado, nunca por caja (ficha 006;
`CLAUDE.md`, *Arquitectura*).

**P7. ¿Qué es lo común a las seis?**
Todas dan resultados plausibles sin excepción, y su efecto se carga a otra cosa: el
modelo, el tracker o «la calidad de la fuente». Por eso el criterio de admisión del
índice es *«un ingeniero competente, leyendo el código y la documentación de la
fuente, lo volvería a hacer»* (`.claude/trampas/README.md`, *Cómo se usa*), y por eso
cada una cierra con un test que la reproduce.

**P8. ¿Por qué «un test en verde no demuestra que guarde nada»?**
Porque un test que no cae cuando se rompe el invariante no guarda nada.
`auditoria/mutar.py` rompe a propósito cada invariante y comprueba que algún test caiga
(ADR-011, `docs/07_decisiones.md:257`; `CLAUDE.md`, *Tests*). La guardia de la trampa 004
caducó con numpy.

## Ejercicio

1. Elige una trampa de la 007 a la 022 que **no** se haya estudiado a fondo y rellena su
   fila de la tabla (frase, guardia, código) sin mirar la ficha; luego comprueba.
2. Inventa una trampa **nueva** plausible para este proyecto (por ejemplo, qué pasaría
   con un cambio de hora en el GTFS) y comprueba si pasa el criterio de admisión: ¿la
   volvería a hacer un ingeniero competente? Si es un off-by-one, no entra.

## Mis respuestas / dudas

