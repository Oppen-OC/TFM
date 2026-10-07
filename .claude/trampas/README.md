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
| [006](006-posiciones-fuera-de-caja-no-son-error.md) | cerrada | etiquetado | Posiciones al sur de 39,36° **no son error de GPS**: son las líneas 24 y 25 bajando a El Perellonet. Filtrar por caja geográfica sesga la muestra hacia corredores bien cubiertos | `test_lejos_del_centro_pero_sobre_la_ruta…` |
| [007](007-arranque-en-frio-del-tracker.md) | cerrada | tracking | La 1ª transición de cada trayectoria empareja **sin predicción**: con buses de la misma línea a menos de un paso (1,9 % de las posiciones reales), el coste correcto y el intercambiado **empatan exacto** y Hungarian desempata por orden de fila. Propaga: 35 % de acierto en convoy. Romper la cadena ante la duda es PEOR | `test_convoy_en_fila_india_…` |
| [008](008-puerta-fisica-sobre-posicion-predicha.md) | cerrada | tracking | La puerta `min(SALTO_MAX_M, VEL_MAX_KMH·dt)` se evaluaba sobre la posición **predicha**, no sobre el desplazamiento real: colaban buses a 110 km/h sin error alguno. Coste y restricción no pueden compartir matriz | `test_la_puerta_fisica_se_respeta_tras_sondeos_perdidos` |
| [009](009-plat-no-arrastra-la-duracion-de-su-paso.md) | cerrada | tracking | `_plat` guarda la posición anterior pero **no cuánto duró el paso que la produjo**. Tras un hueco, el predictor lee un desplazamiento de dos sondeos como si fuera de uno y extrapola el doble. El fallo sale 1-2 sondeos después y se le carga al cambio que lo destapó | `test_un_sondeo_que_falta_…` |
| [010](010-shape-dist-traveled-es-el-horario.md) | cerrada | etiquetado | `shape_dist_traveled` del GTFS de la EMT **no es distancia: es el horario reescalado** ($R^2=1$ contra el tiempo programado). Usado como eje, el retraso sale estructuralmente cero y parece un servicio puntual. La abscisa se proyecta sobre la geometría | `test_la_abscisa_es_geometria_y_no_shape_dist_traveled` |
| [011](011-primera-captura-puede-ser-bloque-a-medias.md) | cerrada | fuentes | La primera captura de un `snapshot_id` puede ser el bloque **a medio reinsertar**: el prefijo de `gid`, con el mismo `snapshot_id` y la mediana del 48 % de las filas. Quedarse la primera, que es lo natural y lo que hace el colector, tira 1.200 sondeos y 109.063 posiciones | `test_reprocesar_completa_el_sondeo_…` |
| [012](012-columna-pegada-por-posicion-tras-rastrear.md) | cerrada | tracking | `rastrear` reordena por sondeo y **reinicia el índice**: una columna calculada sobre su salida y pegada por posición a la entrada se cruza entre filas sin error. Un solo par desordenado dio al 99,7 % la abscisa de otra fila y una mejora falsa del 1,8 % (017) | `test_el_orden_de_las_filas_de_entrada_…` |
| [013](013-puerta-fisica-corta-las-lineas-de-carretera.md) | cerrada | tracking | La puerta de 70 km/h medía el tiempo solo con el reloj del sondeo: una posición atrasada y la siguiente al día parecían ir a 88 km/h y partían la **24** en carretera (5 % de tramos asignados, fuera del denominador del éxito). Subir el umbral no es el arreglo: acepta saltos imposibles | `test_un_bus_cuyas_posiciones_llegan_con_retraso_…` |
| [014](014-la-emt-alterna-el-trayecto-a-mitad-de-ruta.md) | cerrada | fuentes | La EMT publica a veces el `trayecto` **contrario** para un bus que sigue su marcha, 1-4 sondeos a mitad de ruta (7-9 % de los pasos de la 25). La clave (línea, trayecto) lo parte en tres sin error. Cruzar el trayecto al emparejar lo arregla y engancha buses opuestos: se cose después | `test_la_alternancia_del_trayecto_no_parte_…` |
| [015](015-el-origen-del-horario-no-es-la-medianoche.md) | cerrada | etiquetado | Las horas del GTFS se miden desde **«mediodía menos 12 h»**, no desde la medianoche: coinciden salvo los dos días de cambio de hora. Con la medianoche, el 25/10 cada bus casa con el viaje programado **una hora después**, con retraso creíble y `trip_id` equivocado; en marzo se rechaza por desfase | `test_el_dia_del_cambio_de_hora_…` |
| [016](016-la-pi-no-tiene-el-corpus-entero.md) | mitigada | fuentes | La Pi **no tiene el corpus entero**: el 15-18/08 lo capturó el portátil. Un `rsync -av` de la Pi sobre `data/raw/` deja el 18/08 de la EMT en 115 sondeos en vez de 1.109, sin error. Traer solo con `deploy_pi/pull_data.sh` | — (`pull_data.sh --verificar`) |
| [017](017-las-variables-en-t-obs-ven-pasos-que-aun-no-han-llegado.md) | vigente | pipeline | Las variables calculadas en `t_obs` ven pasos que **aún no han llegado**: un paso se conoce ~37 s después (p50; p90 60 s) y en el 11-13 % de las filas el bus ya pasó la parada siguiente. El orden de eventos es correcto y los tests de fuga no lo ven | — |

## Cómo se usa

**Criterio de admisión.** Entra solo si *un ingeniero competente, leyendo el
código y la documentación de la fuente, lo volvería a hacer*. Typo, off-by-one,
import olvidado, cualquier cosa visible en el stack trace: **no entra** — eso va a
GitHub Issues (`gh issue create`).

**Nada se mueve de sitio.** Fichero numerado, inmutable: al resolverse cambia `estado`, no la ruta. **Estados:** `vigente` muerde hoy · `mitigada` hay workaround, sin test · `cerrada` hay test que la guarda. **Sin guardia no se cierra.**

**Ficha nueva:** copia el frontmatter de cualquiera (`id`, `titulo`, `estado`,
`capa`, `detectada`, `test`) y las cuatro secciones fijas — Síntoma, Causa, **Por
qué se vuelve a caer aquí**, Guardia. Si no sabes escribir la tercera, no era una
trampa. Capas: `fuentes` · `tracking` · `etiquetado` · `pipeline` · `serving`.
**`test:`** referencia un node id de pytest: `tests/<fichero>.py::<test_x>`.

Al pasar a `cerrada`, la ficha **encoge** a síntoma + por qué + puntero al test;
el detalle vive en el commit. Si la tabla pasa de ~40 líneas, compacta las `cerrada`.
