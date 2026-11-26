# Día 3 · Calidad del dato y el giro del proyecto (el día más importante)

## Objetivo del día

Entender qué se midió sobre datos reales, qué se descubrió (las capas de tráfico no
parecían medir tráfico), cómo eso estuvo a punto de invertir la pregunta y por qué
**finalmente no se invirtió**. Es lo que más va a preguntar el tribunal.

> **Aviso.** Los números de este día son los de los documentos de esta rama
> (`develop`, commit `3a73904`), que es la versión de referencia: la reformulación de
> `docs/06`, ADR-024 y bitácora 057 se contrastaron el 26/11 y coinciden. Fecha de la reformulación (13/11/2026; `docs/00` se actualizó el 24/11).

## Lecturas

En este orden:

1. `docs/05_hallazgos_primera_captura.md`, entero (176 líneas). §1 (l. 17), la
   alternancia horaria; §3 (l. 79) filas hueco; §4 (l. 94) cobertura espacial.
2. `docs/06_veredicto_capas_trafico.md`, entero (160 líneas). Lee primero el aviso de
   l. 9-14 (reformulado el 13/11): el veredicto de agosto **se sostiene para la capa
   188 y no para la 192**. Después, «Veredicto» (l. 18), «El control…» (l. 62) y «Qué
   quedó del veredicto» (l. 87).
3. `docs/07_decisiones.md`, ADR-001 a ADR-010 (l. 17-256) y «Pendientes de decidir»
   (l. 1141). Del 011 en adelante solo el título de cada uno (están en l. 257-1068).
4. Abre en el navegador `docs/fig_trafico_vs_buses.html`: tres paneles, mismo día, mismo
   eje; uno se mueve y los otros dos son líneas rectas.
5. Opcional, de reojo: `docs/bitacora/README.md` (qué es la bitácora) y las fichas 031 y
   057 (la capa 192 en periodo lectivo y la prueba del tráfico).

## Comandos a ejecutar

```powershell
Start-Process docs/fig_trafico_vs_buses.html          # el gráfico interactivo
uv run python -m project.analysis.diagnose --help     # las cuatro preguntas del GO/NO-GO
Get-ChildItem docs/bitacora | Select-Object -Last 8   # las últimas entradas
```

`diagnose` sin `--help` necesita `data/curated` y `data/reference` capturados y puede
tardar; no es necesario hoy.

## Qué tienes que saber explicar

**P1. ¿Qué descubrió la primera captura sobre la calidad del dato?**
(1) La hora de la EMT alterna entre dos convenciones: 79 % hora local sellada como UTC
y 21 % UTC real (`docs/05:17-62`). (2) La latencia real: p50 23 s en la EMT, 12 s en
Renfe; las capas de tráfico no traen timestamp propio, así que su latencia es
desconocida (`docs/05:64-77`). (3) 34 de 446 filas de la capa 192 son huecos; 410
tramos reales (`docs/05:79-92`). (4) Cobertura espacial del 57,7 % a 50 m, y 21 de 34
líneas por encima del 50 % (`docs/05:94-125`). (5) Las posiciones al sur no son error:
son las líneas 24 y 25 (`docs/05:127-146`).

**P2. ¿Qué concluía `docs/06` en agosto y por qué?**
Que las dos capas de tráfico eran estáticas: en la 192, 8 de 409 tramos cambian de
estado en todo el lunes 17 (1,703 % no fluidos a las 04:00, 08:00 y 19:00); en la 188,
1 de 294 snapshots cambia el total. Y que no es que agosto estuviera vacío: la flota
iba un 52 % más lenta a las 17:00 que a las 22:00 (`docs/06:18-85`). De ahí proponía
invertir la pregunta: usar los autobuses como red de sensores.

**P3. ¿Qué cambió después?**
Con el corpus entero, la 188 sigue congelada (los mismos 243 valores distintos en 354
puntos, `docs/06:120-125`), pero la 192 se anima en periodo lectivo: la mediana de
tramos con congestión pasa de 8,5 a 34 por día laborable (`docs/06:104-119`). La
hipótesis sí se pudo contrastar.

**P4. ¿Cuál fue el resultado de contrastarla?**
Con la comparación primaria fijada de antemano (ADR-024, `docs/07_decisiones.md:872`):
la capa 192 **no aporta** en la primaria (mejora 0,13 s sobre 56 s de error; IC por días
[−0,30, +0,01], contiene el cero; las filas sin sensor mejoran lo mismo). Donde veía
congestión, el error baja un 5 % (−4,85 s sobre 98 s), pero es el 3,2 % de las filas
(`docs/06:126-143`). La v2 sin tráfico bate al listón: −3,37 s.

**P5. ¿Se invirtió entonces la pregunta de investigación?**
No. El TFM sigue siendo de predicción de retrasos. La flota como sensor entró como
**variables del modelo**, no como tema (bitácora 032), y la auditoría de las capas
abiertas queda como hallazgo de calidad del dato (`docs/06:144-154`).

**P6. ¿Por qué cobertura del 57,7 % no es «un problema de precisión»?**
Porque la curva se aplana (de 25 m a 200 m solo gana 20 puntos): faltan sensores donde
circulan buses, no es el emparejamiento (`docs/05:94-125`). Por eso la cobertura es un
**estrato de evaluación**, no un recorte de la muestra (ADR-018,
`docs/07_decisiones.md:511`; `CLAUDE.md`, *Pipeline ML*).

**P7. ¿Por qué el split es temporal y no aleatorio?**
Con series de posiciones, un split aleatorio mete futuro en el entrenamiento y da
métricas infladas; es el primer error que busca un tribunal (ADR-007,
`docs/07_decisiones.md:154-181`; `features.partir`, `src/project/features.py:460`). Su
coste: el test hereda lo que pasó esos días (obras, festivos, meteorología) y hay que
declararlo como limitación.

**P8. ¿Por qué el crudo no es un cuello de botella de disco?**
Porque la geometría de las capas de tráfico se guarda una vez (ADR-017,
`docs/07_decisiones.md:487`); era el 74 % del disco (`docs/05:148-159`). Medido, el
corpus son ~32 M de filas en 57 días, ~56 M a tres meses, 433 MB en Parquet
(`docs/bitacora/056*.md`; `docs/00:34-38`).

## Ejercicio

Escribe **una frase** que reconcilie la pregunta original («¿cuánto del retraso se
explica por la congestión aguas abajo y con qué antelación?») con lo que dice
`docs/06`. Una frase, que contenga: lo que medía la capa 192, lo que se encontró, y por
qué la pregunta se mantiene. Después, una segunda versión de 20 segundos para voz.

Pista de estructura, no de contenido: *«Hipótesis → medida → resultado negativo
acotado → qué se hizo con él.»*

## Mis respuestas / dudas

