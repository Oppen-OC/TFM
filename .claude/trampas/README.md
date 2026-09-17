# Trampas conocidas

Bugs que **no dan la cara**: no lanzan excepción, producen resultados plausibles y
contaminan en silencio. Esta tabla está siempre en contexto. **Abre la ficha
completa antes de tocar la capa correspondiente.**

| id | estado | capa | trampa | guardia |
|----|--------|------|--------|---------|
| [001](001-gid-no-identifica-vehiculo.md) | cerrada | fuentes | `gid` identifica al refresco, no al vehículo: la tabla se trunca y reinserta entera, intersección cero entre sondeos. Solo vale de `snapshot_id`; la identidad se infiere | `test_emt_snapshot_id_…_minimo_del_bloque` |
| [002](002-emt-alterna-convencion-horaria.md) | cerrada | fuentes | La EMT **alterna** UTC y hora local naive de un sondeo al siguiente (338 alternancias / 1.224 snapshots). Corregir con desfase fijo deja el 20 % de las filas 2 h desplazadas | `test_serie_con_convenciones_alternas…` |
| [003](003-raiz-renfe-es-objeto.md) | cerrada | fuentes | Raíz de Renfe es objeto, no array: `{fechaActualizacion, trenes:[...]}`. Sin filtrar `nucleo == "40"` te llevas la flota nacional sin error | `test_renfe_filtra_solo_nucleo_40` |
| [004](004-sort-inestable-en-snapshot.md) | cerrada | tracking | `sort_values` usa quicksort, no estable. Reordena filas del mismo snapshot y rompe todo lo que reenganche **por posición de fila**. Reportó 11 % de precisión siendo 99 % | `test_rastrear_no_reordena_filas_dentro_del_sondeo` |
| [005](005-filas-hueco-capa-trafico.md) | cerrada | fuentes | 34 de las 446 filas de la capa 192 llegan sin `idtramo`, sin geometría y sin `estado`. No son tramos desconocidos: no son tramos. Denominador real **410** tramos (412 filas: 211 y 216 duplicados) | `test_filas_hueco_de_trafico_se_descartan` |
| [006](006-posiciones-fuera-de-caja-no-son-error.md) | vigente | etiquetado | Posiciones al sur de 39,36° **no son error de GPS**: son las líneas 24 y 25 bajando a El Perellonet. Filtrar por caja geográfica sesga la muestra hacia corredores bien cubiertos | ⚠ ninguna |
| [007](007-arranque-en-frio-del-tracker.md) | cerrada | tracking | La 1ª transición de cada trayectoria empareja **sin predicción**: con buses de la misma línea a menos de un paso (1,9 % de las posiciones reales), el coste correcto y el intercambiado **empatan exacto** y Hungarian desempata por orden de fila. Propaga: 35 % de acierto en convoy. Romper la cadena ante la duda es PEOR | `test_convoy_en_fila_india_…` |
| [008](008-puerta-fisica-sobre-posicion-predicha.md) | cerrada | tracking | La puerta `min(SALTO_MAX_M, VEL_MAX_KMH·dt)` se evaluaba sobre la posición **predicha**, no sobre el desplazamiento real: colaban buses a 110 km/h sin error alguno. Coste y restricción no pueden compartir matriz | `test_la_puerta_fisica_se_respeta_tras_sondeos_perdidos` |
| [009](009-plat-no-arrastra-la-duracion-de-su-paso.md) | cerrada | tracking | `_plat` guarda la posición anterior pero **no cuánto duró el paso que la produjo**. Tras un hueco, el predictor lee un desplazamiento de dos sondeos como si fuera de uno y extrapola el doble. El fallo sale 1-2 sondeos después y se le carga al cambio que lo destapó | `test_un_sondeo_que_falta_…` |

## Cómo se usa

**Criterio de admisión.** Entra solo si *un ingeniero competente, leyendo el
código y la documentación de la fuente, lo volvería a hacer*. Typo, off-by-one,
import olvidado, cualquier cosa visible en el stack trace: **no entra** — eso va a
GitHub Issues (`gh issue create`).

**Nada se mueve de sitio.** Fichero numerado, inmutable. Al resolverse cambia
`estado`, no la ruta.

**Estados.** `vigente` muerde hoy · `mitigada` hay workaround, sin test · `cerrada`
hay test que la guarda. **Sin guardia no se cierra.**

**Ficha nueva:** copia el frontmatter de cualquiera (`id`, `titulo`, `estado`,
`capa`, `detectada`, `test`) y las cuatro secciones fijas — Síntoma, Causa, **Por
qué se vuelve a caer aquí**, Guardia. Si no sabes escribir la tercera, no era una
trampa. Capas: `fuentes` · `tracking` · `etiquetado` · `pipeline` · `serving`.

**`test:`** referencia un node id de pytest: `tests/<fichero>.py::<test_x>`.

Al pasar a `cerrada`, la ficha **encoge** a síntoma + por qué + puntero al test.
El detalle de la investigación vive en el commit. Si esta tabla pasa de ~40
líneas, compacta las `cerrada`.
