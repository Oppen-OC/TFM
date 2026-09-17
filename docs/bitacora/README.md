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
