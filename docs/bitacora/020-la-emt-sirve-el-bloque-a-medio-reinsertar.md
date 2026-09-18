---
id: 020
titulo: La EMT sirve a veces el bloque a medio reinsertar, y eso explica el 92 % de los sondeos parciales
fecha: 2026-09-18
tipo: anomalia
capa: fuentes
capitulo: calidad-dato
impacto: alto
estado: resuelto
evidencia: uv run python -m project.analysis.medir_sondeos_repetidos --sources emt_buses
trampa: 011
---

## Qué se observó

Del 15/08 al 18/09, **2.078 de las 80.030 capturas no vacías** de la EMT repiten
el `snapshot_id` de la captura inmediatamente anterior. Todas son consecutivas.
De ellas, 1.340 traen contenido distinto de la primera. Comparadas `gid` a
`gid` con esa primera captura:

| repetición | capturas |
|---|---|
| mismos `gid` y posición; sólo cambia `fecha` en ±2 h (trampa 002) | 126 |
| los `gid` de la primera son el **prefijo** de los de la repetición: los más bajos, sin huecos, misma posición | **1.214** |
| subconjunto estricto que no es prefijo | 0 |
| mismo contenido reordenado | 0 |
| cualquier otra cosa | 0 |

Las 1.214 son **1.200 sondeos** (el 1,54 % de 77.952) y **109.063 filas**. La
primera captura trae la mediana del 48 % del bloque (p25 24 %, p75 71 %).

La tabla de la capa se trunca y se reinserta entera en cada refresco (trampa
001), con `gid` contiguos. Que las 1.214 parciales sean exactamente el prefijo
del bloque indica una inserción en orden creciente: una consulta que coincide
con la reinserción ve los `gid` ya escritos, que son los más bajos. Entre ellos
está el mínimo, que es el `snapshot_id`. La captura siguiente ve el bloque
entero con el mismo `snapshot_id`.

Efecto sobre los sondeos parciales, los que traen menos filas que el umbral por
la mediana de sus 20 vecinos:

| umbral | con la primera captura | con la más completa | desaparecen |
|---|---|---|---|
| 50 % | 635 | 16 | 97 % |
| 80 % | 1.081 | 82 | 92 % |
| 90 % | 1.292 | 186 | 86 % |

## Cómo se midió

```
uv run python -m project.analysis.medir_sondeos_repetidos --sources emt_buses
uv run python -m project.analysis.medir_sondeos_repetidos --sources emt_buses --umbral 0.5
uv run python -m project.analysis.medir_sondeos_repetidos --sources emt_buses --umbral 0.9
```

Recorre el crudo y agrupa las capturas por `clave_sondeo`, la misma función que
usan el colector y `reprocesar`. Después clasifica cada repetición con contenido
distinto contra la primera captura de su sondeo.

Controles del instrumento:

- `primera_subconjunto`, `reordenado` y `otros` salen a 0: cada repetición cae
  en una de las dos explicaciones.
- Los 2.078 repetidos y los 1.200 completados coinciden con lo que cuenta
  `reprocesar --dry-run`, que es otro camino de código.
- La consecutividad se comprobó por separado: la captura anterior a cada
  repetición es del mismo sondeo en las 2.078. La primera versión del contador
  de "sondeos nuevos entre medias" tenía un error de uno y daba 1 en vez de 0.

## Por qué importa

- **Era la causa desconocida de un problema conocido.** En una hora del 27/08,
  tres sondeos parciales provocaban 452 de las 883 roturas de trayectoria
  (`tests/test_tracking_fragmentacion.py`). `tolerar_hueco=2` se introdujo para
  absorberlos, junto con los vehículos que faltan sueltos (entrada 008). La
  causa se atribuía a un gzip truncado (`_TRUNCADOS.txt`), y la entrada 011 lo
  desmintió sin encontrar otra.
- **El daño al tracker ya estaba contenido; el dato no.** Con los bloques
  completos, el 27/08 pasa de 7.658 a 7.627 trayectorias (entrada 019):
  `tolerar_hueco` ya absorbía casi todo. Lo que se recupera son 109.063
  posiciones que sólo conservaba el crudo.
- **El colector de la Raspberry sigue quedándose la primera captura.** Su
  curated pierde alrededor del 1,5 % de los sondeos completos. El curated
  canónico es el reprocesado.

## Qué se hizo / qué queda abierto

- `reprocesar` se queda la captura con más filas de cada sondeo, y a igualdad la
  primera (76a1921). La guardia es
  `test_reprocesar_completa_el_sondeo_que_llego_a_medias` y el mutante 055. Se
  ficha como trampa 011.
- El colector no se toca (decisión del 18/09): el crudo está íntegro y
  `reprocesar` lo recupera.
- Abierto: quedan 82 sondeos parciales con el umbral del 80 %. No tienen segunda
  captura; que sea la misma causa es una hipótesis sin medir, y para ellos sigue
  haciendo falta `tolerar_hueco`.
- Abierto: `tracking.py` (parámetro `tolerar_hueco`), `simulacion.py`
  (parámetro `parciales`) y `test_snapshot_parcial_no_parte_la_trayectoria`
  siguen citando `_TRUNCADOS.txt` como causa.

## Para la memoria

> La capa de posiciones de la EMT se regenera truncando y reinsertando la tabla
> completa en cada refresco. Una consulta que coincide con la reinserción recibe
> sólo la parte ya escrita del bloque, con el mismo identificador de refresco
> que el bloque completo. Entre el 15 de agosto y el 18 de septiembre, 1.200 de
> los 77.952 refrescos capturados (el 1,54 %) llegaron primero incompletos, con
> una mediana del 48 % de sus filas, y completos en la captura siguiente.
> Conservar la primera captura de cada refresco, que es el criterio natural para
> descartar duplicados, habría perdido 109.063 posiciones. Conservar la más
> completa reduce los refrescos anómalamente cortos de 1.081 a 82 (menos del
> 80 % de la mediana de sus vecinos; entre el 86 % y el 97 % de reducción con
> umbrales del 90 % y del 50 %). Esto identifica la lectura concurrente con la
> reinserción como la causa principal de los refrescos parciales que obligaban
> al rastreador a tolerar ausencias.
