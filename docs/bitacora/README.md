# Bitácora de hallazgos

Registro cronológico de lo que se ha **medido, descartado o aceptado** durante el
desarrollo. Cada entrada es material directo para la memoria: trae la cifra, el
comando que la reproduce y un párrafo ya redactado para el capítulo que le toca.

El TFM no se defiende con el modelo final, sino con el rastro de decisiones que
llevan hasta él. Ese rastro se pierde en tres semanas si no se escribe el día que
pasa.

## Índice

| id | fecha | tipo | capítulo | hallazgo |
|----|-------|------|----------|----------|
| [001](001-error-identidad-se-mide-en-trayectorias.md) | 2026-09-01 | medicion | metodologia | El error de identidad del tracker no se cuenta en posiciones: el 2,2 % del método ingenuo son 4 saltos que contaminan el 5 % de las trayectorias, y alargar la captura **baja** la cifra sin arreglar nada |
| [002](002-el-empate-de-grupo-es-raro-no-normal.md) | 2026-09-01 | medicion | calidad-dato | El 55 % de vehículos con compañero cerca es de **cualquier** línea; restringido a la misma (línea, trayecto), que es lo único que el tracker empareja, baja al 1,9 % |
| [003](003-puerta-fisica-sobre-la-posicion-predicha.md) | 2026-09-01 | anomalia | metodologia | La puerta de velocidad se evaluaba sobre la posición **predicha**: colaban 24-46 emparejamientos imposibles por ventana de 150 sondeos, hasta 110 km/h, sin lanzar ningún error |
| [004](004-el-solape-con-trafico-es-un-suelo-no-el-desfase-real.md) | 2026-09-01 | medicion | metodologia | La fusión buses × tráfico es viable —124 s de desfase mediano, 99,6 % por debajo de 5 min— pero esa cifra es un **suelo**: las capas de tráfico no publican timestamp propio |
| [005](005-la-capa-192-tiene-410-tramos-y-63-con-congestion.md) | 2026-09-01 | medicion | limitaciones | La capa 192 declara 410 tramos y solo **63** llegan a congestionarse; el 97,9 % de su estado `cortado` son siete vías cerradas de forma permanente, sin patrón horario |
| [006](006-las-capas-de-trafico-no-unen-por-clave-pero-si-por-geometria.md) | 2026-09-01 | medicion | metodologia | Las dos capas de tráfico tienen **intersección cero** de `idtramo` pero instrumentan la misma red: mediana de 51,6 m al vecino más cercano, y correspondencia no biunívoca (389 → 175) |
| [007](007-total-de-valenbisi-es-capacidad-instalada-no-anclajes-operativos.md) | 2026-09-01 | anomalia | calidad-dato | `available + free` no suma `total` en el 24,9 % de las filas, y el desfase es por defecto en 286.325 de 286.339: `total` es capacidad instalada, no anclajes operativos |
| [008](008-la-ventana-de-medicion-censuraba-la-metrica.md) | 2026-09-16 | descarte | metodologia | Medido en ventanas de 1 h, agrupar por línea parecía el mejor arreglo del tracker; sobre el día completo fabrica una trayectoria de **19,8 h**. Una métrica de duración no se mide en una ventana de su mismo orden. Aplicado en su lugar `tolerar_hueco=2`: 12.709 → 7.632 trayectorias, mediana 10,5 → 21,1 min |
| [009](009-la-fragmentacion-era-contencion-de-danos.md) | 2026-09-16 | medicion | metodologia | La fragmentación estaba **conteniendo** el daño: con los dos sentidos a 200 m, agrupar por línea mantiene los mismos 23 saltos y dobla la cola contaminada (15,4 % → 30,1 %) |
| [010](010-plat-sin-su-dt.md) | 2026-09-16 | anomalia | metodologia | El predictor extrapola en pasos de snapshot, no en segundos: el fallo sale 1-2 sondeos **después** del hueco y se atribuye al cambio equivocado. Disparador real: 5 de 2.749 transiciones |
| [011](011-el-crudo-esta-integro-y-ningun-test-lo-guarda.md) | 2026-09-17 | medicion | calidad-dato | El crudo está **íntegro**: 95.343 payloads, 0 miembros gzip rotos. La "truncación" era `zcat` parando en relleno de ceros; Python lo salta. Pero los 9 mutantes de persistencia pasan la suite en verde |
| [012](012-tres-guardias-de-trampas-cerradas-no-guardan.md) | 2026-09-17 | anomalia | metodologia | En **3 de 7** trampas cerradas la guardia no cae al deshacer el arreglo; la de la 004 quedó inerte al pasar de numpy 2.2.6 a 2.4.6, sin tocar código ni test |
| [013](013-la-flota-simulada-no-para-ni-gira.md) | 2026-09-17 | medicion | metodologia | La flota simulada nunca para; la real está parada el **29 %** de los pasos y gira con p90 de 57°. Con paradas y giros realistas, el tracker pasa de 0 a **2-4 saltos** de identidad |
| [014](014-la-capa-192-duplica-los-tramos-211-y-216.md) | 2026-09-17 | anomalia | calidad-dato | La capa 192 da **412** filas con `idtramo` para **410** tramos: el 211 y el 216 llegan duplicados en cada sondeo, con el mismo estado |
| [015](015-el-sondeo-siguiente-delata-el-intercambio.md) | 2026-09-17 | tecnica | metodologia | Ajustar el coste de un paso no deshace los intercambios en paradas y giros: la información está en el sondeo **siguiente**. Suavizar con un sondeo de retardo los reduce un **58-100 %** en semillas reservadas sin partir ni una trayectoria real; quedan 46 saltos en 40 ejecuciones del escenario completo |
| [016](016-el-map-matching-casa-con-el-gtfs.md) | 2026-09-17 | medicion | calidad-dato | Las posiciones casan con los trazados del GTFS a **4 m** de mediana (5,16 M de posiciones). El sentido lo decide el avance: **0,998** sobre el trazado elegido frente a **0,018** sobre el contrario. Lo que queda fuera de ruta son buses en cochera: 4,8 % en servicio frente a >50 % de madrugada |
| [017](017-la-abscisa-mejora-la-identidad-un-8-por-ciento.md) | 2026-09-18 | medicion | metodologia | Emparejar sobre el recorrido quita el **7,6 %** de los intercambios con semillas reservadas, no el 35 % que aparentaban cinco de ajuste. Hicieron falta la hipótesis de parada y penalizar los adelantamientos, con techo puesto por los adelantamientos reales |
| [018](018-las-posiciones-sin-trayecto-salen-como-trayectorias-de-un-punto.md) | 2026-09-18 | anomalia | calidad-dato | 1.834 de 5,16 M posiciones (0,036 %, 31 líneas) llegan sin `trayecto`; `groupby` las descarta y cada una sale como trayectoria de **un punto**: el 1,07 % de las trayectorias del 27/08 |
| [019](019-reprocesar-no-deduplica-sondeos.md) | 2026-09-18 | anomalia | calidad-dato | `reprocesar` no deduplica sondeos como el colector: el 27/08 pasa de 2.784 a 2.854 capturas y un **2,5 %** más de filas da un **53 %** más de trayectorias (7.658 → 11.730) |
| [020](020-la-emt-sirve-el-bloque-a-medio-reinsertar.md) | 2026-09-18 | anomalia | calidad-dato | La EMT sirve a veces el bloque **a medio reinsertar**: 1.200 sondeos (1,54 %) llegan primero como prefijo de `gid` y completos en la captura siguiente. Quedarse la más completa baja los sondeos parciales de **1.081 a 82**: era la causa de los que motivaron `tolerar_hueco` |
| [021](021-las-capas-del-geoportal-faltan-cuatro-dias-con-el-colector-vivo.md) | 2026-09-18 | limitacion | limitaciones | Las cuatro capas del geoportal faltan **103,7 h** (10/09 06:24 - 14/09 14:05 UTC) con el colector vivo y Renfe completa; volvieron con un reinicio del colector. Unos 11.900 sondeos de la EMT perdidos, y `--status` dijo `VIVO` los cuatro días |
| [022](022-el-map-matching-aguanta-en-septiembre.md) | 2026-09-18 | medicion | calidad-dato | El map-matching aguanta en septiembre: **4,21 m** de mediana y avance **0,996 frente a 0,03** en 91 grupos. La 40 era un bus en cochera, la C3 regulación en cabecera, la subida del fuera de ruta un desvío de la 24 y la 25; la 63 no tiene horario en el feed |
| [023](023-la-segunda-pasada-no-mejora-la-jornada-real.md) | 2026-09-18 | anomalia | metodologia | En jornada real la segunda pasada con abscisa no cambia las trayectorias y sube **30-55 %** `ida_vuelta`. La mejora real de la 017 era abscisa pegada por posición: el 99,7 % de las filas recibió la de otra |
| [024](024-la-etiqueta-sale-bien-salvo-donde-el-horario-no-es-el-que-se-circula.md) | 2026-09-21 | medicion | metodologia | La cascada da **2,1 M** de pasos con retraso y asigna el **94 %** de los tramos de servicio de agosto. Del 31/08 al 11/09 el feed vigente no es el horario que se circula: el éxito cae al 75 % y los conflictos se triplican; con el feed posterior, 84-88 % |
| [025](025-desde-el-9-de-septiembre-la-fuente-deja-de-publicar-lineas-enteras.md) | 2026-09-21 | anomalia | limitaciones | Desde el 09/09 la capa de la EMT deja de publicar casi toda la **71** (−93 %) y buena parte de la 28, la 25, la 4 y la 73; esos buses no reaparecen con otro número de línea |
| [026](026-la-24-y-la-25-casi-no-llegan-a-la-etiqueta.md) | 2026-09-23 | anomalia | metodologia | La 24 y la 25 son el **4,9 %** de las posiciones y el **0,37 %** de los pasos etiquetados, y el éxito de la 024 no lo ve porque excluye los cortos. A la 24 la trocea la puerta de 70 km/h en carretera (abrirla: 363 → 144 trayectorias); a la 25, una fuente que alterna el trayecto del mismo bus a mitad de ruta (**6,9-9,0 %** de los pasos, ≤ 0,4 % en las de control) |
| [027](027-viaje-id-colisiona-entre-dias-procesados.md) | 2026-09-23 | anomalia | metodologia | `viaje_id` no es único entre los días que procesa `prepare`: **932** se repiten entre particiones (890 con líneas distintas) y **74** viajes programados se etiquetan dos veces. El tracker numera desde `v00000` en cada llamada y la madrugada pertenece al día de servicio anterior |
| [028](028-la-puerta-cuenta-el-reloj-de-la-posicion.md) | 2026-09-23 | tecnica | metodologia | La puerta física cuenta el mayor de los dos relojes, el del sondeo y el de la posición: la 24 pasa de **4.272 a 13.596** pasos y la 25 de 826 a 7.413, con las líneas urbanas a ±0,4 %. Subir el umbral a 100 km/h recuperaba lo mismo pero aceptaba saltos imposibles y rompía dos guardias |
| [029](029-la-alternancia-del-trayecto-se-cose-despues-no-al-emparejar.md) | 2026-09-25 | tecnica | metodologia | La alternancia del trayecto se cose DESPUÉS de rastrear: cruzar el trayecto al emparejar recuperaba la 25 pero bajaba hasta un **34 %** las trayectorias urbanas. El cosido sube la 25 un 16 % en pasos, baja un **42 %** las trayectorias de un punto y deja `ida_vuelta` igual. La alternancia no es solo de la 25: la 99 aporta 2.089 posiciones corregidas |
| [030](030-la-tabla-de-entrenamiento-y-los-baselines.md) | 2026-09-25 | medicion | metodologia | La tabla de entrenamiento: **1,24 M** de filas en 19 días y **269.493** en 5 de prueba (14-18/09). La persistencia deja el MAE de la parada siguiente en **37,6 s** frente a 139,9 del horario: es el listón. Los diagnósticos de la asignación (`desfase_s`) miraban paradas futuras y quedan fuera |
| [031](031-la-capa-192-se-anima-en-periodo-lectivo-la-188-sigue-congelada.md) | 2026-09-25 | medicion | calidad-dato | En periodo lectivo la capa 192 **se anima**: 34 tramos congestionados por laborable y 42 horas-tramo (×11 frente a agosto), con picos a las 8 y a las 18 h. La 188 sigue congelada (243 valores idénticos los 32 días). El veredicto del documento 06 vale para la 188, no para la 192 |
| [032](032-la-flota-como-sensor-mide-sobre-todo-el-sesgo-del-horario.md) | 2026-09-25 | medicion | resultados | La flota como sensor del tramo aguas abajo correlaciona **+0,45** con lo que la persistencia no explica, pero casi todo es el **sesgo estático del horario** en cada tramo: sin él quedan +0,07, y sin el perfil diario, +0,03. El modelo necesitará el sesgo histórico del tramo como control |
| [033](033-el-volumen-de-la-captura-no-pide-un-broker.md) | 2026-09-30 | descarte | metodologia | Las cinco fuentes suman **6.336 payloads al día**, 0,07 por segundo y 297 MB sin comprimir: el volumen no pide un broker y Kafka queda fuera de la captura (ADR-016). El tráfico da 155.000 filas al día, 28 veces menos que los 4,3 M proyectados |
| [034](034-el-cambio-de-hora-desplaza-el-horario-entero.md) | 2026-09-30 | anomalia | metodologia | El GTFS cuenta las horas desde «mediodía menos 12 h», no desde la medianoche. El día del cambio de hora, la medianoche habría asignado el **77,5 %** de los viajes a otro viaje programado (el de una hora después), con 238 s de error mediano en el retraso y ningún error visible |
| [035](035-el-corpus-entero-solo-esta-en-el-pc.md) | 2026-09-30 | medicion | calidad-dato | El corpus entero solo está en el PC: **18.918 sondeos** del 15-18/08 no están en la copia de la Pi, que empieza el 18/08 a las 23:02 UTC. Copiarla encima del crudo deja ese día de la EMT en **115 sondeos en vez de 1.109**, sin error. En 54 min de solape, el segundo colector no vio ningún `snapshot_id` que el primero no tuviera |
| [036](036-todas-las-lineas-entran-y-el-soporte-decide-cuales-se-informan.md) | 2026-09-30 | medicion | metodologia | Todas las líneas etiquetadas entran en la muestra: excluir la 25, la 63 y la 73 (menos del 30 % de sus posiciones en viajes asignados) movía la persistencia **0,08 s**. Con 5 días de prueba, **24 líneas** tienen soporte para una cifra propia, y con 100-299 viajes no se distingue una mejora de menos de **1-2 s** (de 6 s si el modelo se aleja de la persistencia): el tráfico se juzga en el conjunto, no por línea |
| [037](037-el-08-10-09-era-el-11-por-ciento-del-entrenamiento-con-el-horario-de-verano.md) | 2026-10-05 | medicion | metodologia | El 08-10/09, etiquetado con el horario de verano, era el **10,9 %** del entrenamiento (135.114 de 1.236.585 filas), con ×5-6 conflictos y ×8-9 rechazos por margen. Excluirlo deja el entrenamiento en agosto: **4,88 %** de positivos frente al **5,85 %** de la prueba |
| [038](038-la-asignacion-pliega-la-mitad-de-los-retrasos-de-mas-de-5-minutos.md) | 2026-10-05 | limitacion | metodologia | La asignación pliega al viaje siguiente el **4,1 %** de los viajes (**3,0 %** sin delatar), el 11 % con intervalos ≤ 8 min, y la **mitad** de los buses que salen con más de 5 min de retraso. Acotado con Lynden-Bell y validado prediciendo los rechazos por margen: 2.342 frente a 2.379 |
| [039](039-el-sesgo-del-horario-por-tramo-explica-un-28-por-ciento-del-error-de-la-persistencia.md) | 2026-10-06 | medicion | metodologia | Lo que la persistencia no explica vive en el **tramo**, no en la línea: corregirla con el sesgo histórico del horario por (versión, línea, par de paradas) baja su MAE de **36,8 a 26,5 s** (−28 %); la línea sola, 0,07 s. Es el tercer baseline: el listón del tráfico |

## Qué va aquí y qué no

| Es… | Va a |
|-----|------|
| bug silencioso que un ingeniero competente volvería a cometer | `.claude/trampas/` |
| decisión estructural con alternativas y condición de reapertura | `docs/07_decisiones.md` |
| cifra medida, anomalía de fuente, hipótesis descartada, límite del alcance | **aquí** |
| typo, off-by-one, cualquier cosa visible en el stack trace | `gh issue create` |

Una trampa **también** genera entrada de bitácora: la ficha explica el bug, la
entrada explica lo que se aprendió y cómo se cuenta. El cruce va en el campo
`trampa:`. Los tres registros se citan entre ellos; ninguno copia contenido de
otro.

## Cómo se escribe una entrada

`uv run` no hace falta: se pide el comando `/bitacora <descripción del suceso>`,
que encamina por la tabla de arriba, **reproduce la cifra antes de escribirla** y
deja la entrada creada con su fila en este índice. `/bitacora` sin argumentos
audita el registro.

Ficheros `NNN-slug.md`, id correlativo, **inmutables**: al resolverse cambia
`estado`, no la ruta.

Frontmatter completo:

```yaml
id: 001                    # correlativo, tres dígitos
titulo: ...                # la frase dice el hallazgo, no el tema
fecha: 2026-09-01          # YYYY-MM-DD
tipo: medicion             # medicion | anomalia | limitacion | descarte | tecnica
capa: tracking             # fuentes | tracking | etiquetado | pipeline | serving
capitulo: metodologia      # calidad-dato | metodologia | resultados | limitaciones
impacto: alto              # alto | medio | bajo
estado: mitigado           # abierto | mitigado | resuelto | aceptado
evidencia: uv run python -m project.analysis.medir_tracking
trampa: 004                # ficha relacionada, o — si no hay
```

Cinco secciones fijas, en este orden:

1. **Qué se observó** — la cifra con su denominador. Un porcentaje sin
   denominador no es un hallazgo.
2. **Cómo se midió** — comando reproducible, o la razón explícita de que no lo
   haya. Sin esto la entrada es una anécdota.
3. **Por qué importa** — el efecto real aguas abajo. Si se acumula, cómo escala.
4. **Qué se hizo / qué queda abierto**.
5. **Para la memoria** — el párrafo, ya redactado, listo para pegar en el
   capítulo que dice `capitulo:`. Es lo que hace que esto valga: al escribir la
   memoria se concatenan párrafos, no se releen treinta entradas.

**Cada cifra debe poder rastrearse** hasta un comando, un `fichero:línea` o un
commit. Ninguna entrada inventa números, y ninguna cita un número que no se haya
vuelto a medir. La trampa 004 reportó un 11 % que en realidad era 99 %: ante una
cifra sorprendente, la primera hipótesis es que el instrumento miente.
