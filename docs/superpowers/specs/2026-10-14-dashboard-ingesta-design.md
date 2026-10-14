# Dashboard de la defensa, fase 1: el camino del proyecto por la ingesta

_Diseño aprobado en conversación el 13-14/10/2026, sección a sección. Es la
primera de cuatro fases; las otras tres tendrán su propia spec._

## Problema

La defensa necesita contar el ciclo de vida del dato de forma que el tribunal lo
siga sin haber leído la memoria, y la memoria necesita las mismas figuras. Las
cifras existen (`metrics/`, bitácoras, trampas), pero repartidas en JSON y en
prosa. Se quiere una pieza dinámica, que se pueda proyectar en directo y grabar
en vídeo, y cuyas cifras salgan siempre del dato, nunca copiadas a mano.

## Fases

1. **Ingesta** (esta spec): el camino desde la idea hasta la captura completa.
2. **Resto del recorrido**: curado → identidad → etiqueta → modelo. Después del
   21/10, cuando cierre la prueba del ADR-024.
3. **Capa artística**: buses animados sobre el mapa, transiciones finas.
4. **Vídeo**: grabación con Playwright del modo automático.

La fase 1 fija la tecnología y la línea de tiempo sobre la que se montan las
otras tres.

## Decisiones

1. **Uso.** Una página HTML para la defensa, que se navega en directo o se
   reproduce sola para grabarla, y las figuras de la memoria sacadas de la misma
   foto de datos (opción C).
2. **Datos mixtos.** Esquema donde se cuenta un mecanismo, dato real donde el
   dato es el mensaje: payloads reales en las anomalías, series diarias reales
   en la captura.
3. **Escenas por pasos con reproducción automática**, no scrollytelling ni
   dashboard de pestañas: es lo único que se ve igual en directo y en vídeo.
4. **Tecnología.** HTML estático con D3 v7 y GSAP 3 dentro del repo, y un
   exportador en Python. Descartados Plotly (transiciones rígidas), Manim (no es
   interactivo) y Streamlit (anima mal; es la app que habla con la API).
5. **Estructura compatible con el TFM de la ETSINF.** El camino es una línea
   esquemática, tipo plano de metro. Las **estaciones** son los seis capítulos
   de la guía «Estructura y Contenidos Recomendados» de la ETSINF (Introducción,
   Estado del arte, Análisis del problema, Solución propuesta, Implantación,
   Conclusiones); los **problemas** son paradas entre estaciones, en orden
   cronológico dentro de cada capítulo. El índice de la defensa es el plano de
   la línea.
6. **El marcador avanza en tiempo de desarrollo**: la fecha de cada parada es
   cuándo se descubrió el problema, no cuándo ocurrió. El desfase entre las dos
   es parte de la historia (las capas cayeron el 10/09 y se vio el 18/09).
7. **Versión simple primero**: línea recta, un punto como marcador, sin mapa ni
   buses.

## Alcance

**Entra:** el exportador, la foto de datos, la página con las 10 paradas, las
figuras de la memoria de las paradas de tipo `serie`, sus tests y mutantes.

**No entra (no-objetivos):**
- Tracking, etiquetado, modelo y tráfico como predictor: fase 2.
- Mapa, buses animados, transiciones artísticas: fase 3.
- Grabación del vídeo: fase 4. Esta fase deja listo `?auto=1` para ella.
- La capa de servido (`api/`, `services/`, `ui/`): el dashboard es estático.
- Renfe y Valenbisi más allá de la parada P1: no entran en el modelo.
- Cualquier dato de `data/processed/`, etiquetas o métricas del modelo.

## Arquitectura

```
data/raw  data/curated  metrics/curar.json  docs/bitacora/*.md  .claude/trampas/*.md
        \        |              |                  |                    /
         src/project/analysis/dashboard_ingesta/   (exportador, fuera de DVC:
                 |                                  paradas, extraer, figuras, __main__)
                 |                                   |
     dashboard/datos/ingesta.js              dashboard/figuras/*.pdf
                 |
     dashboard/index.html + escena.js + estilo.css + vendor/{d3, gsap}
```

- **El exportador** define en un solo sitio las 10 paradas y extrae su prueba.
  Reutiliza `sources.read_raw`, `medir_completitud.instantes`/`huecos`,
  `medir_fuentes.lectivo` y `medir_volumen.medir`, importados como funciones.
- **La foto lleva su origen**: commit, fecha de generación, rango del crudo y
  `"sucio": true` si el árbol de trabajo tenía cambios.
- **`ingesta.js`, no `.json`**: el exportador escribe `window.DATOS = {...}`.
  `fetch` y los módulos ES fallan sobre `file://` en Chrome, y en la defensa
  debe bastar con abrir `index.html` sin servidor ni red.
- **La página es un renderizador genérico**: sabe dibujar cuatro tipos de
  prueba y nada de paradas concretas.
- **Librerías dentro del repo** (`dashboard/vendor/`), versión fijada, cargadas
  como `<script>` clásicos. Sin npm ni bundler.
- **`dashboard/` va en git**, foto incluida (< 2 MB): la defensa no depende de
  DVC ni de `data/`.

## Paradas

Cada parada es un registro: `id`, `capitulo`, `apartado`, `fecha`, `titulo`,
`texto`, `cifras`, `prueba`, `remite`, `duracion_s` (12 por defecto) y `cotejo`.

- `texto` es una plantilla **sin dígitos**; sus huecos `{nombre}` se rellenan
  con `cifras`, que salen del dato.
- `fecha` es la más temprana de las fichas a las que remite la parada
  (`fecha:` de la bitácora, `detectada:` de la trampa). P1 y P2 no remiten a
  ninguna ficha y llevan la fecha de `docs/01`-`03`.
- `cotejo` guarda la cifra que publicó la ficha y una tolerancia relativa; si la
  recalculada se sale de ella, el exportador se detiene con un error (el
  instrumento también miente, trampa 004). La tolerancia es 0 donde el
  recálculo del 14/10 reprodujo la ficha exacta (P4, P10), una milésima en la
  duración del hueco (P5) y un 2 % donde la ficha se publicó sobre otra
  versión del crudo y hoy se desvía en torno a un 1 % (P8: 6.342 payloads y
  299 MB al día). P3 y P7 cotejan sin tolerancia contra las bitácoras 053 y 052,
  que corrigieron las cifras publicadas. La página enseña siempre
  la cifra recalculada, y el exportador imprime la desviación de cada cotejo.

| | cap. | fecha | parada | prueba | origen | cotejo |
|---|---|---|---|---|---|---|
| P1 | 1 Introducción | 14/08 | La idea y el barrido de fuentes; Metrovalencia descartado (ADR-008) | `lista`: fuentes candidatas con su veredicto, y la cadencia de las que se capturan | `SOURCES.period_s`, `docs/03` | — |
| P2 | 3 Análisis del problema | 15/08 | Ninguna fuente guarda el pasado: colector 24/7, crudo antes de parsear | `cifra`: payloads guardados en el crudo y primer sondeo | crudo | — |
| P3 | 4 Solución · Adquisición | 16/08 | La EMT alterna UTC y hora local (trampa 002) | `pares`: dos sondeos seguidos con convención distinta | crudo, `tz_convencion` de `parse_emt` | 342 alternancias en 1.236 sondeos, 15/08 22:15-16/08 08:55 local (bitácora 053; se publicó 338 en 1.224) |
| P4 | 4 | 19/08 | El `gid` identifica al refresco, no al vehículo (trampa 001) | `pares`: dos sondeos seguidos con intersección de `gid` vacía | crudo | intersección 0 |
| P5 | 4 | 18/09 | La fuente falla sin avisar: capas caídas (021) y líneas que dejan de publicarse (025) | `serie`: sondeos diarios de las capas, hueco 10-14/09 sombreado; posiciones diarias de la 71 | `medir_completitud`, curado | 4 días y 7,7 h de hueco |
| P6 | 4 | 18/09 | El bloque a medio reinsertar: por qué se guarda el crudo (020, trampa 011) | `pares`: primera captura a medias frente a la completa, mismo `snapshot_id` | crudo, metrics/curar.json | completados de la EMT ≥ 1.200 (el corpus contiene el 15/08-18/09) |
| P7 | 4 | 25/09 | En periodo lectivo la 192 despierta y la 188 sigue congelada (031) | `serie`: tramos congestionados al día (192) frente a valores distintos (188) | `medir_fuentes.lectivo()` | mediana de 43 tramos densos o congestionados por laborable (la 031 publicó 34 con el 18/09 a medias; corrección en la 052); la 188, 243 valores distintos |
| P8 | 4 | 30/09 | 0,07 payloads por segundo: Kafka no hace falta (033) | `cifra`: payloads/s y MB/día por fuente | `medir_volumen.medir()` sobre los días de la 033 | 6.336 payloads/día, 297 MB (±2 %) |
| P9 | 4 | 30/09 | La infraestructura también falla: corpus solo en el PC (035), disco de la Pi (044), GTFS sin guardar (051) | `serie`: línea temporal de la captura con los incidentes anotados | `medir_completitud`, fechas de las fichas | — |
| P10 | 5 Implantación · Resultados | 13/10 | La captura de la prueba, completa (050) | `serie`: completitud diaria de EMT y 192 en todo el corpus; cifra de la prueba | `medir_completitud` | 17.119 de 17.280 sondeos de la EMT, 07-12/10 |

Los capítulos 2 (Estado del arte) y 6 (Conclusiones) aparecen como estaciones
sin paradas.

**Tipos de prueba**, los únicos que la página sabe dibujar:
- `lista`: elementos con veredicto (✅ ⚠️ ❌).
- `pares`: dos registros reales lado a lado, el campo que importa resaltado.
- `serie`: una o dos series diarias, con tramos sombreados y anotaciones.
- `cifra`: un número grande con su contexto.

## Navegación y animación

- **Lienzo fijo 16:9 (1920×1080)** escalado a la ventana con bandas.
- **Composición**: arriba la línea con las 6 estaciones y las 10 paradas,
  tramo recorrido en color y pendiente en gris; el marcador lleva la fecha
  encima. En el centro, título, texto y prueba de la parada. Al pie, la ficha
  citada y el origen de la foto.
- **Una línea de tiempo maestra de GSAP con una etiqueta por parada.**
  → / espacio / clic: `tweenTo` a la siguiente. ←: la misma animación hacia
  atrás. A o `?auto=1`: reproducción entera con pausa de `duracion_s` en cada
  parada, determinista. F: pantalla completa.
- **Transición (~2,5 s)**: sale el contenido (0,4 s) → el marcador recorre el
  camino con la cámara siguiéndolo a un tercio de la izquierda y la fecha
  contando días (1,2 s) → pulso en la parada → entran título y texto → la prueba
  se anima según su tipo (`pares`: filas que entran y destello del campo;
  `serie`: trazo de izquierda a derecha y sombras; `cifra`: cuenta hasta el
  valor; `lista`: entrada escalonada).
- **Cambio de capítulo**: rótulo superpuesto 1 s al pasar por una estación.
- **Ronda de preguntas**: tooltips de D3 con el dato exacto sobre la prueba.
- **Estilo**: fondo claro (los proyectores lavan los temas oscuros), un color de
  acento, sin marcas ni logos de la EMT, fuentes del sistema, castellano.

## Verificación

**Tests** (tests/test_dashboard.py, datos sintéticos con verdad conocida):
- Un test por extractor con lógica propia: P3 encuentra el cambio de
  convención; P4, la intersección vacía; P5, el hueco de días quitados a
  propósito; P6, el par a medias/completo en un crudo con el bloque partido.
- Ninguna plantilla de `texto` contiene dígitos y todos sus huecos se resuelven.
- Las fechas de las paradas no retroceden a lo largo del camino.
- Cada tipo de prueba trae las claves que el renderizador espera; la foto pesa
  menos de 2 MB.
- El cotejo detiene el exportador cuando la cifra no cuadra.
- Cada guardia nueva tiene su mutante en `auditoria/catalogo.toml`.

**Página**: sin framework de tests de JS. Se verifica en Chrome: las 10 paradas
hacia delante y hacia atrás, consola sin errores, una captura por parada y una
reproducción completa con `?auto=1`.

## Errores

- El exportador falla con un mensaje claro si falta lo que necesita
  (metrics/curar.json, días del crudo, una ficha citada). Sin respaldo
  silencioso.
- La página, sin `ingesta.js`, dice qué comando ejecutar en vez de quedarse en
  blanco.

## Fronteras

- El exportador vive en `src/project/analysis/`: fuera de DVC, nada lo importa.
- Lee crudo, curado, metrics/curar.json y el frontmatter de `docs/bitacora/` y
  `.claude/trampas/`. No importa `features`, `train`, `predict` ni `evaluate`.
- **No puede mirar la prueba del ADR-024**: no lee etiquetas, `data/processed/`
  ni métricas del modelo. Del 07-19/10 solo usa conteos de captura, que la
  bitácora 050 ya publicó.

## Reproducibilidad y calendario

```bash
uv run python -m project.analysis.dashboard_ingesta     # foto + figuras
```

- metrics/curar.json sale de `dvc repro curar` (lanzado el 14/10; solo
  reconstruye el curado, determinista, sin evaluar nada).
- Se desarrolla sobre el crudo hasta el 12/10. La foto definitiva se genera tras
  traer el 19/10 y el repro posterior a la prueba (~21/10).

## Supuestos

- **Duración de la defensa sin confirmar.** Otros másteres de la UPV dan 15 min
  de exposición y 15 de preguntas. Si es así, este tramo debería durar 2-3 min:
  con 12 s de pausa y 2,5 s de transición, las 10 paradas suman unos 2,5 min
  en automático. Se ajusta con `duracion_s`.
- Las cifras de las paradas sin cotejo (P1, P2, P9) son conteos directos o
  fechas de fichas; no requieren contraste.
