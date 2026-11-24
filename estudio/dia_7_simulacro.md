# Día 7 · Simulacro

## Objetivo del día

Pasar de saber a defender: dejarte interrogar con dureza, detectar lo que no sabes
contestar, escribir la lista de **límites del trabajo** y cronometrar una exposición de
15-20 minutos.

## Lecturas

1. Tus «Mis respuestas / dudas» de los días 1 a 6: lo que dejaste en duda es lo primero
   que repasas hoy.
2. `.claude/commands/sincronizar.md`, `.claude/commands/grill-me.md` y
   `.claude/agents/tribunal.md`: qué hace cada herramienta y qué reglas trae.
3. `docs/bitacora/README.md` (cómo se ficha) y las fichas 057 (capa 192 en la prueba),
   058 (límites del GTFS), 053 (la alternancia horaria recalculada) y 056 (volumen).
4. `docs/07_decisiones.md`: «Qué la reabriría» de ADR-002, 007, 016 y 018, que son las
   preguntas de «¿y si…?».
5. `estudio/auditoria_docs.md` y `estudio/decisiones_pendientes.md`: si el tribunal
   pilla una incoherencia entre documentos, debes haberla visto antes.

## Comandos a ejecutar

Dentro de Claude Code (en la rama de trabajo, **no** pidas que escriban en `docs/` ni en
`.claude/` hoy: es material de estudio):

```text
/sincronizar            # deriva entre documentación y código; propone, no aplica
/grill-me <tu plan de defensa: «defiendo que el tráfico aporta poco y por qué»>
```

Y el agente `tribunal` (revisor metodológico). Su definición dice que «escribe solo en
`docs/`»: pídele explícitamente que **responda por el chat** y no cree ficheros, o
revisa antes que no ha tocado nada con `git status`.

Y en PowerShell, para comprobar que lo estudiado sigue en verde:

```powershell
uv run pytest .claude/tests -q
uv run pytest tests/test_ingest.py tests/test_tracking_identidad.py -q
```

## Qué tienes que saber explicar

Es el simulacro: contesta **en voz alta, cronometrado, sin notas**.

**P1. Resume el TFM en 60 segundos.**
Problema (apps estiman la llegada con reglas simples que fallan en punta), pregunta
(cuánto del retraso se explica por la congestión aguas abajo y con qué antelación),
aportación (etiqueta fabricada con ETL desde una fuente sin id de vehículo ni retraso;
corpus propio irrecuperable), resultado (la v2 sin tráfico bate al listón −3,37 s; la
capa 192 no aporta en la primaria) y límites (`docs/00:18-46`; `docs/06:126-143`).

**P2. «¿Por qué no usaste un histórico público?»**
Porque no existe: ninguna fuente guarda pasado, la EMT trunca y reinserta su tabla en
cada refresco (ficha 001; `docs/04:46-52`). Lo que no captura el colector se pierde para
siempre, de ahí que se guarde el crudo antes de parsear (`collect.py:9-11`).

**P3. «Tu resultado principal es negativo. ¿Qué has demostrado?»**
Que el estado del tráfico publicado aporta poco: −0,13 s sobre 56 s con IC por días
[−0,30, +0,01]; y que el control sin sensor mejora lo mismo, así que no se atribuye al
tráfico. Es un resultado medido con la comparación primaria fijada **antes** de ver la
prueba (ADR-024, `docs/07_decisiones.md:872`; `docs/06:126-143`). Y lo accesorio: donde
veía congestión el error baja 5 %, en el 3,2 % de las filas.

**P4. «¿Cómo sé que no hay fuga de futuro?»**
Split temporal por fechas, no aleatorio (ADR-007); el «ahora» de cada fila es `t_disp`
(cuándo se supo el retraso), no `t_obs` (trampa 017, ADR-022); la prueba se evaluó una
sola vez y todo análisis posterior es exploratorio (`CLAUDE.md`, *Estado*;
`tests/test_features.py`, mutantes 079-082).

**P5. «¿Cómo sabes que tu etiqueta es correcta si no hay verdad-terreno?»**
No la hay para la EMT: es derivada. Se prueba contra un GTFS sintético con retraso
conocido (±5 s) (`tests/test_etiquetado.py`, docstring) y sobre flota simulada con verdad
(`tests/conftest.py:29`). La validación externa con Renfe, que sí publica retraso,
estaba en la propuesta y hoy queda como trabajo futuro (`docs/04:85`; `docs/00:70`).
Sesgo declarado: un bus a más de medio intervalo de su horario se asigna al viaje
contiguo (`etiquetado.py:33-36`).

**P6. «Si tu tracker se equivoca, todo se contamina. ¿Cuánto?»**
Sobre la flota simulada: 0 saltos con 60 buses, 2 con 120 a 30 s y 6 con 120 a 60 s; con paradas y giros
reales 2-4 saltos, defecto conocido y marcado `xfail(strict=True)`
(`docs/00:129`; bitácora 001). Y el 99 % frente al 11 % de la trampa 004 enseña por qué
se desconfía de la métrica antes que del tracker.

**P7. «¿Por qué XGBoost y no deep learning?»**
Tabular, tamaño y trazabilidad (ADR-005, `docs/07_decisiones.md:117`); deep learning
sobre secuencias queda fuera de alcance y se cita como trabajo futuro (`docs/00:48-73`).

**P8. «¿Por qué no Kafka? ¿Dónde está el Big Data?»**
El volumen medido (32 M de filas en 57 días, 0,07 payloads/s) no lo pide; el Big Data
aquí es captura continua irrecuperable, formato columnar (Parquet + zstd) y DuckDB sobre
un portátil sin broker. Kafka queda como opción para un servido incremental (ADR-016,
`docs/07_decisiones.md:429-486`; bitácora 033, 056).

**P9. «¿Qué haría falta para ponerlo en producción?»**
Servido incremental (las variables hoy se calculan por día completo, riesgo de skew),
meteorología como variable, cadencia de la 192, y el permiso de uso de datos
(`docs/00:99-104`; ADR-016).

## Ejercicio

1. **Lista escrita de límites del trabajo** (que sea tuya, en tus palabras). Mínimo estos
   y su razón:
   - La capa 192 no aporta en la primaria; la 188 está congelada (`docs/06`).
   - El test es un bloque temporal contiguo y hereda lo que pasó esos días (ADR-007).
   - La etiqueta es derivada, sin verdad-terreno para la EMT; sesgo de medio intervalo
     (`etiquetado.py:33-36`).
   - Las versiones del GTFS posteriores contradicen entre el 8 y el 47 % de la prueba
     (bitácora 058).
   - Huecos de captura declarados: 10-14/09 (bitácora 021), disco de la Pi (054); la Pi
     no tiene el corpus entero (trampa 016).
   - El tracker falla con paradas y giros reales (`tests/test_tracking_realismo.py`).
   - Latencia de las capas de tráfico desconocida: el sello lo pone la ingesta
     (`docs/05:64-77`).
   - Meteorología sin entrar al modelo; servido incremental sin hacer.
   - La demo en vivo no es un resultado.
2. **Exposición cronometrada de 15-20 min**, dos veces. Estructura sugerida: problema y
   pregunta (3 min) · datos y calidad (4) · ETL y trampas (4) · modelo y resultado (4) ·
   límites y trabajo futuro (3) · reserva (2). Grábate; si pasas de 20, recorta
   arquitectura, no resultados.
3. Prepara **tres preguntas hostiles propias** y su respuesta.

## Mis respuestas / dudas

