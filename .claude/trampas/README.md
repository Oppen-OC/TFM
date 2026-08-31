# Trampas conocidas

Bugs que **no dan la cara**: no lanzan excepción, producen resultados plausibles y
contaminan en silencio. Esta tabla está siempre en contexto. **Abre la ficha
completa antes de tocar la capa correspondiente.**

| id | estado | capa | trampa | guardia |
|----|--------|------|--------|---------|
| [001](001-gid-no-identifica-vehiculo.md) | cerrada | fuentes | `gid` identifica al refresco, no al vehículo: la tabla se trunca y reinserta entera, intersección cero entre sondeos. Solo vale de `snapshot_id`; la identidad se infiere | selftest "gids … disjuntos" |
| [002](002-emt-alterna-convencion-horaria.md) | cerrada | fuentes | La EMT **alterna** UTC y hora local naive de un sondeo al siguiente (338 alternancias / 1.224 snapshots). Corregir con desfase fijo deja el 20 % de las filas 2 h desplazadas | selftest "convenciones alternas" |
| [003](003-raiz-renfe-es-objeto.md) | cerrada | fuentes | Raíz de Renfe es objeto, no array: `{fechaActualizacion, trenes:[...]}`. Sin filtrar `nucleo == "40"` te llevas la flota nacional sin error | selftest "renfe: núcleo 40" |
| [004](004-sort-inestable-en-snapshot.md) | cerrada | tracking | `sort_values` usa quicksort, no estable. Reordena filas del mismo snapshot y rompe todo lo que reenganche **por posición de fila**. Reportó 11 % de precisión siendo 99 % | selftest "identidad correcta >= 99 %" |
| [005](005-filas-hueco-capa-trafico.md) | mitigada | fuentes | ~35 de las 446 filas de la capa 192 llegan sin `idtramo`, sin geometría y sin `estado`. No son tramos desconocidos: no son tramos. Denominador real **410** | ⚠ ninguna |
| [006](006-posiciones-fuera-de-caja-no-son-error.md) | vigente | etiquetado | Posiciones al sur de 39,36° **no son error de GPS**: son las líneas 24 y 25 bajando a El Perellonet. Filtrar por caja geográfica sesga la muestra hacia corredores bien cubiertos | ⚠ ninguna |

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

**`test:`** referencia `demo/selftest.py::"<nombre del check>"` (no es pytest,
usa `check()`) o un node id de `tests/`.

Al pasar a `cerrada`, la ficha **encoge** a síntoma + por qué + puntero al test.
El detalle de la investigación vive en el commit. Si esta tabla pasa de ~40
líneas, compacta las `cerrada`.
