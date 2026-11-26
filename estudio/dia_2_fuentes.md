# Día 2 · Las fuentes

## Objetivo del día

Saber qué da cada fuente, con qué cadencia, qué rarezas trae y por qué unas sirven y
otras se descartaron. Al acabar, debes poder dibujar una tabla de las fuentes de
memoria.

## Lecturas

En este orden:

1. `docs/01_viabilidad_fuentes_valencia.md`. Lee primero el aviso de vigencia (l. 8-20):
   cuatro cosas de ese informe de agosto quedaron superadas. Después, el veredicto
   (l. 24), §1 EMT (l. 42), §2 tráfico (l. 124), §3 Renfe (l. 155), §4 Valenbisi, §5
   Metrovalencia, §5 bis clima (l. 223) y §7 qué extraer de cada fuente (l. 288). Los
   §8-9 y el anexo son históricos.
2. `docs/03_fuentes_valencia_primer_barrido.md`: primer barrido, anterior al 01. Léelo
   rápido; sirve para ver qué se creía antes de medir (aviso de vigencia en l. 5-13).
3. `src/project/ingest/sources.py` (652 líneas; el equivalente actual de
   `demo/sources.py`). Solo: la tabla `SOURCES` (l. 436-510), los parsers
   (`parse_emt` l. 226, `parse_trafico_estado` l. 253, `parse_renfe` l. 391),
   `clave_sondeo` (l. 515) y `append_raw` (l. 559).
4. `src/project/ingest/explore.py` (91 líneas): es lo que ejecutas hoy.

## Comandos a ejecutar

Con red, en PowerShell, desde la raíz del repo (si no existe `.venv`, primero
`uv sync`):

```powershell
uv run python -m project.ingest.explore              # todas las fuentes
uv run python -m project.ingest.explore emt_buses    # una concreta
```

Equivale a `python demo/explore.py` del plan original. No escribe nada. Anota qué
fuentes responden, cuántas filas da cada una y la latencia que imprime.

Sin red, para ver cadencias configuradas:

```powershell
Select-String -Path src/project/ingest/sources.py -Pattern "period_s|silencio_max_s"
```

## Qué tienes que saber explicar

**P1. ¿Qué fuentes usa el proyecto y para qué?**
EMT `Seguimiento_EMT/384` (posición de la flota, fuente principal, sondeo cada 30 s),
tráfico capa 192 (estado de congestión, 5 min) y 188 (intensidad, 15 min), Valenbisi
228 (5 min), Renfe Cercanías núcleo 40 (30 s, con retraso ya calculado, plan B), clima
capa 157 (5 min, en captura desde el 09/11) y el GTFS estático de la EMT
(`sources.py:436-510`; `docs/01:24-36`). Metrovalencia queda fuera: solo hay GTFS
estático (ADR-008, `docs/07_decisiones.md:183`).

**P2. ¿Por qué `gid` no sirve como identificador de vehículo?**
Porque identifica al refresco, no al vehículo: la tabla se trunca y reinserta entera
en cada sondeo, y entre dos sondeos consecutivos la intersección de `gid` es cero. Solo
vale como `snapshot_id` (el `gid` mínimo del bloque), y la identidad se infiere
(`sources.py:235`; ficha 001; `tracking.py:1-10`).

**P3. ¿Qué rareza tiene la hora de la EMT?**
Que la fuente alterna entre UTC y hora local sellada como UTC de un sondeo al
siguiente (342 alternancias en 1.236 sondeos). Se decide por sondeo, con la latencia
plausible (`sources.py:78-123`; ficha 002; `docs/05_hallazgos_primera_captura.md:17`).

**P4. ¿Qué rareza tiene Renfe?**
Que la raíz es un objeto `{fechaActualizacion, trenes:[…]}`, no un array, que trae la
flota nacional (hay que filtrar `nucleo == "40"`, `sources.py:399-400`), y que omite las
claves sin valor en lugar de mandarlas a nulo (trampa 019).

**P5. ¿Por qué se guarda el crudo antes de parsear?**
Porque el pasado no se puede recapturar: si el parser estaba mal o la fuente cambia de
esquema, se reprocesa del crudo. Así se arregló la trampa 002 sin recapturar nada
(`collect.py:9-11`; `docs/07_decisiones.md:45-62`, ADR-002).

**P6. ¿Cómo se sabe si una fuente sigue viva?**
Con `collect --status`: juzga cada fuente por la edad de su último sondeo bueno frente
a su `silencio_max_s`, y no dice VIVO si una fuente lleva callada demasiado, aunque el
latido del colector siga (`collect.py:17-27`; `sources.py:149-168`).

**P7. ¿Por qué Kafka no entra en la captura?**
Porque el volumen (0,07 payloads/s) no lo pide, el crudo ya desacopla captura y
procesado, un broker es un punto de fallo más sobre datos irrecuperables y la Pi no
tiene RAM de sobra. Queda como opción para un servido en tiempo real incremental
(ADR-016, `docs/07_decisiones.md:429-486`).

## Ejercicio

Rellena de memoria esta tabla y compárala con `sources.py:436-510` y `docs/01:24-36`:

| Fuente | Qué da | Cadencia de sondeo | Rareza principal | Papel |
|---|---|---|---|---|
| | | | | |

Después, elige **una** fuente y escribe, en tres líneas, cómo la sabotearías sin que el
pipeline diera error (pista: todas las trampas 001-006 van de eso).

## Mis respuestas / dudas

