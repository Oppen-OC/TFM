# Captura de la capa 157 (Estaciones Atmosféricas) — diseño

Issue #8 (clima), primer plan. 07/11/2026.

## Por qué

El issue #8 quiere el clima como variable candidata del modelo. La única fuente
en vivo con lluvia, viento y temperatura dentro de València es la capa 157 del
geoportal (`OPENDATA/MedioAmbiente/MapServer/157`, *Estaciones Atmosféricas*).
**No guarda histórico**: sirve el último valor de cada estación y lo pisa. Cada
hora que la Pi no la captura se pierde para siempre (CLAUDE.md, *No hay
histórico recuperable*). Por eso este plan es solo de captura: dejar la Pi
guardando el crudo cuanto antes, con las mismas garantías que las demás fuentes.
Qué forma toma la variable se decide en el segundo plan, con histórico y con
datos.

## Lo medido el 06/11 (base del diseño)

Hay 120 sondeos reales, uno cada 2 min, de 16:59 a 20:57 UTC, en el scratchpad
de la sesión. Desde el 07/11 sigue capturando el mismo sondeo exploratorio (ver
*Captura puente*).

- **Cinco estaciones**: W01 Av. Francia, W02 Nazaret, W03, W04 y W06. No hay
  W05.
  - W03 = AEMET 8414A (Valencia Aeropuerto, SYNOP 08284).
  - W04 = AEMET 8416Y (València Viveros, SYNOP 08285).
  - Lo confirman la presión, que sigue al SYNOP con 0,1-0,2 hPa de diferencia, y
    las coordenadas redondeadas a 2 decimales, como las publica AEMET.
- **Cadencia.**
  - W01 y W02 (municipales): un valor cada 10 min, visible unos 7 min después
    de su marca.
  - W03, W04 y W06: un valor por hora, que aparece hacia el minuto :41 con 51-91
    min de latencia. La marca cae en minutos múltiplos de 10 irregulares. Los
    valores intermedios no se publican nunca.
- **Convención horaria.** El 06/11 `fecha_carg` llegó en UTC. La presión de W04
  con lectura UTC coincide con el SYNOP 08285 (19:50 → 1020,9 hPa, el mismo
  valor que el SYNOP de las 20 UTC). Con lectura local la diferencia era de
  0,5-0,8 hPa. Unas horas en UTC **no fijan** la convención (trampa 002, puerta
  007).
- **Latencia por sondeo**, con lectura UTC:
  - fila más fresca: 332-933 s, mediana 683 s;
  - mediana de las cinco filas: 3.081-6.575 s.
  - Consecuencia: decidir la convención por la mediana, como hace
    `resolver_convencion`, da `DUDOSA` siempre.
- **La clave por el máximo pierde datos.** Así deduplica hoy `clave_sondeo` en
  una fuente con `ts_utc`. Sobre los 120 sondeos:
  - con la clave por el máximo: 25 sondeos distintos; 3 lecturas de W02 se
    pierden enteras y 12 lecturas entran 4-6 min tarde;
  - con la clave por (estación, marca): 32 sondeos distintos y ninguna lectura
    perdida.
  - Mecanismo: una estación que publica con una marca anterior al máximo vigente
    no cambia el máximo, y su respuesta cuenta como duplicada.
- **`precipitac`** vale 0,0 en todas las estaciones: no ha llovido. No se sabe
  si acumula 10 min, 1 h o el día.
- **Descartado**: el CSV horario de la GVA «últimos 2000». Se actualiza una vez
  al día (Last-Modified 11:02 UTC). A las 17:00 del 06/11 su último dato era del
  05/11 a las 23:00, y solo cubre unas 4 h de todas las estaciones.

## Objetivos

1. La fuente `meteo_estaciones` entra en `src/project/ingest/sources.py`, en
   develop.
   - Guarda el crudo antes de parsear (ya lo hace `append_raw` para toda
     fuente).
   - Tiene un fixture con la forma real en `tests/fixtures.json`.
   - Tiene tests sin red.
   - `collect --status` la juzga.
2. Se porta **a mano**, sin cherry-pick, a `demo/sources.py` y
   `demo/collect.py` de la rama `raspberry` (worktree `../TFM-raspberry`).
3. La Pi la captura: `payloads.ndjson.gz` bajo
   `/srv/tfm-sd/raw/source=meteo_estaciones/`. **El despliegue lo hace el
   usuario** con los comandos de este documento: Claude no tiene SSH.

## No-objetivos

- Ninguna fuente histórica: Open-Meteo, SYNOP de Ogimet, AEMET OpenData. Van en
  el segundo plan.
- No se tocan `features.py`, ni la variable de clima, ni la prueba del 07-19/10
  (ADR-024).
- El clima no entra en `curar` ni en DVC.
- No se interpreta `precipitac` ni las unidades de viento.
- Fuera: la GVA, las predicciones meteorológicas y el estado por estación en
  `--status`.
- No se retira `demo/`.
- No se corrige el `ORIGEN` por defecto de `pull_data.sh` (sigue apuntando a
  `/srv/tfm-data`).
- No se vuelven a generar las fotos del dashboard de la defensa.
  `analysis/dashboard_ingesta/foto.py` cuenta `len(SOURCES)`: si se regenerara, diría 6
  fuentes capturadas. La foto definitiva ya está en develop y no se rehace.

## Anti-objetivos (fracaso aunque los tests pasen)

- **Convertir con un desfase fijo.** El día que el geoportal sirva hora local, o
  tras un cambio de hora, las filas salen desplazadas 1-2 h con aspecto
  plausible (trampa 002).
- **Que el despliegue no cambie nada.** `instalar.sh` hace `systemctl enable
  --now`, que no reinicia un servicio que ya está en marcha. El proceso viejo
  seguiría corriendo sin la fuente nueva, y `--status` no la listaría.
- **Que `curar` cambie.** Basta con que `reprocesar` meta el clima en
  `data/curated` para que el stage cambie de hash y todo lo de aguas abajo se
  re-ejecute (40-50 min), con el riesgo de mover cifras ya entregadas.
- **Contar un `{"error"}` como sondeo** (trampa 018).

## Restricciones

- **Frontera.** `ingest/` no importa nada de aguas abajo. `demo/` es
  independiente:
  - imports planos (`from sources import ...`);
  - sin el paquete `project` ni `config.py`;
  - el parser se busca por nombre en `PARSERS`.
- **`clave_sondeo` es una sola función** que comparten el colector y
  `reprocesar` (bitácora 019). La clave nueva va dentro de ella, no en una copia.
- **Equivalencia de DVC.** Cambiar `sources.py` deja `curar` desactualizado
  (`sources.py` es dependencia suya). Se aplica el cambio, se prueba que el
  curated sale idéntico byte a byte y después `dvc commit -f curar` (memoria
  `refactor-dvc-equivalencia`).
- **Guardia nueva ⇒ mutante nuevo** en `auditoria/catalogo.toml`. El siguiente
  id libre es el **203** (comprobado el 07/11: el último es el 202).
- **En la Pi**, los datos van en `DATOS=/srv/tfm-sd`: el disco de
  `/srv/tfm-data` está roto (bitácoras 044 y 051).

## Decidido

Cada punto lleva quién lo decidió: **usuario** (encargo de la sesión) o **mi
decisión** (revísala).

### develop

1. **Fuente `meteo_estaciones`** en `SOURCES`.
   - URL: `f"{ARCGIS}/OPENDATA/MedioAmbiente/MapServer/157/query?{QUERY_ARGS}"`.
   - Nombre: mi decisión (S6).
   - `period_s=300`: mi decisión (S3). W01 y W02 refrescan cada 10 min, así que
     con 5 min se ve cada lectura municipal y cada lectura horaria de AEMET.
   - `silencio_max_s=30 * 60`, provisional: mi decisión (S4).

2. **`parse_meteo(payload, ts_ingest)`** sobre `_arcgis_rows`. Devuelve una fila
   por estación:
   - de la fuente: `fiwareid`, `nombre`, `lat`, `lon`, `fecha_carg`,
     `temperatur`, `humedad_re`, `presion_ba`, `viento_vel`, `viento_dir` y
     `precipitac`;
   - añadidas: `ts_utc`, `ts_ingest_utc`, `latencia_s` y `tz_convencion`.

   Los nombres de la fuente no se cambian, ni sus valores: es crudo sin
   interpretar (mi decisión). Las columnas añadidas son las mismas que en
   `parse_emt`. `fecha_carg` se queda con el epoch tal como llegó, al lado de
   `ts_utc`, para auditar la convención en el curated y para la clave del punto
   4 (mi decisión).

3. **Convención por respuesta, decidida con la fila más fresca.**
   - Lo pidió el usuario: «el desfase tiene que verificarse siempre».
   - Cómo, mi decisión:
     - `resolver_convencion` recibe un parámetro de agregación. Por defecto es
       la mediana, así que las demás fuentes no cambian.
     - `parse_meteo` lo llama con el mínimo de la latencia, que es la latencia
       de la fila más fresca, y con `lat_max=2400`.
   - Por qué 2.400 s:
     - La fila fresca llega hasta 933 s, por encima del 900 por defecto.
     - En invierno, 2.400 discrimina bien. Si se sirve local, la lectura UTC da
       la latencia real menos 3.600 s, por debajo de −180. Si se sirve UTC, la
       lectura local da más de 3.600 s.
     - En verano el margen es mayor.
   - Si W01 y W02 dejan de publicar, la fila más fresca es de AEMET (más de
     3.000 s). El sondeo sale `DUDOSA` y queda a la vista: no se descarta, y
     `reprocesar` puede volver a decidirlo desde el crudo.

4. **Clave por estación en `clave_sondeo`.**
   - Rama nueva, después de la de `snapshot_id`: si `df` trae `fecha_carg`, la
     clave es la lista ordenada de pares (`fiwareid`, `ts_utc`), como cadena.
   - El usuario aprobó la clave por estación. Usar `ts_utc` ya resuelto, y no el
     epoch crudo, es mi decisión: así la misma respuesta servida en dos
     convenciones cuenta como un solo sondeo.
   - **La condición es `fecha_carg`, no `fiwareid`** (mi decisión). Las capas de
     tráfico 192 y 188 también traen `fiwareid`, en unas 410 filas por sondeo.
     Una rama sobre `fiwareid` les cambiaría la clave de `str(ts_ingest)` a una
     cadena de unos 20-25 KB. Con `MAX_VISTOS = 20_000` claves por fuente,
     serían cientos de MB en la Pi, y otro tanto en `reprocesar` sobre todo el
     corpus. El curated saldría idéntico, así que la prueba de equivalencia no
     lo detectaría. `fecha_carg` solo lo trae la capa 157. La firma de
     `clave_sondeo` no cambia, y sigue el estilo de las ramas que ya tiene por
     fuente.
   - Las demás fuentes no tienen `fecha_carg`: su clave no cambia, y lo guarda
     un test (punto 7).
   - Consecuencia: cada sondeo guarda las cinco filas aunque solo una sea nueva.
     Repetir las filas iguales se deduplica aguas abajo (S5).

5. **`reprocesar` sin `--sources` excluye `meteo_estaciones`.** Lo pidió el
   usuario.
   - Cómo, mi decisión: el valor por defecto de `--sources` pasa a ser
     `[k for k in SOURCES if k != "meteo_estaciones"]`, con un comentario
     `ponytail:` que dice que el clima entra en `curar` en el segundo plan, si
     se decide.
   - `dvc.yaml` no cambia.
   - Prueba: el curated sale idéntico a la versión actual en una muestra de días
     de cada fuente, `dvc commit -f curar` y `dvc status` limpio.
   - No lleva test propio, mi decisión: si se rompe, `dvc status` lo delata y el
     coste es tiempo de cómputo, no una contaminación silenciosa.

6. **Fixture** `meteo_estaciones` en `tests/fixtures.json`: un payload real del
   06/11 entero, con `fields`, `spatialReference` y las cinco features, tal como
   llegó. El test usa el `ts_ingest_utc` de esa captura como constante.

7. **Tests sin red:**
   - Añadir `meteo_estaciones` a `FUENTES` de `tests/test_ingest.py`, para que
     corran los tests parametrizados de parsers.
   - Fixture real: 5 filas, `ts_utc` igual a `fecha_carg` leído como UTC y
     `tz_convencion == "YA_EN_UTC"`. Este test cae si se decide por la mediana.
   - Mismo payload con cada `fecha_carg` desplazada +1 h (hora local de
     invierno) y el mismo `ts_ingest`: `LOCAL_NAIVE` y los mismos `ts_utc`. Este
     test cae con un desfase fijo.
   - **Estación que llega tarde**: dos respuestas en las que la segunda solo
     cambia la marca de una estación por otra anterior al máximo.
     - Con `_capturar_y_reprocesar` de `tests/test_persistencia.py`, el colector
       las guarda como dos sondeos y `reprocesar` también (0 duplicados).
     - Lo ideal es un par real consecutivo de la captura del 06/11, si se
       encuentra; si no, se fabrica desde el fixture.
   - **La clave del tráfico no cambia**: `clave_sondeo` sobre el fixture de
     `trafico_estado` parseado sigue dando `str(ts_ingest)`.
   - `--status`:
     - una fila de `meteo_estaciones` en el test parametrizado del silencio
       legítimo, por debajo de 30 min: no es CAÍDA;
     - un silencio por encima del umbral: es CAÍDA.
   - Un `{"error": ...}` de la capa 157 no cuenta como sondeo: parametrizar la
     guardia existente de la trampa 018, si admite fuente.

8. **Mutantes**, desde el 203:
   - quitar la rama `fiwareid` de `clave_sondeo`;
   - `parse_meteo` con desfase fijo (`pd.to_datetime(..., utc=True)` sin
     resolver);
   - `parse_meteo` decidiendo por la mediana;
   - la condición de la rama sobre `fiwareid` en vez de `fecha_carg`.

   Cada uno tiene que poner rojo al menos un test de la lista anterior. Es la
   regla de CLAUDE.md.

9. **Documentación:**
   - veredicto de la capa 157 y de la GVA en
     `docs/01_viabilidad_fuentes_valencia.md`;
   - la capa 157 en la línea *Fuentes* de CLAUDE.md;
   - comentario en el issue #8 con las cifras de arriba.

   Comprobar después `uv run pytest .claude/tests`, porque `test_memoria.py`
   compara la documentación con el código.

10. **Crudo del portátil a `data/raw/source=meteo_estaciones/`.**
    - Lo pidió el usuario para el 06/11.
    - Ampliarlo a lo que capture el sondeo puente es mi decisión.
    - **Es el primer paso del plan**, antes del fixture: el scratchpad es de
      sesión y el plan puede ejecutarse en otra. Ver *Captura puente*.

### raspberry (porte a mano)

11. **`demo/sources.py`**: `parse_meteo`, entrada en `PARSERS`, `Source` con
    `parser="parse_meteo"` y el mismo parámetro de agregación en su copia de
    `resolver_convencion`.
12. **`demo/collect.py`**:
    - la rama de `fecha_carg` en la deduplicación, que aquí está en línea y no
      en `clave_sondeo`, con la misma condición que en develop;
    - `meteo_estaciones` en la lista de `--sources` por defecto. El servicio de
      systemd no pasa `--sources`, así que sin esto la Pi no la captura.
13. **`demo/fixtures.json`** con el mismo payload, y en **`demo/selftest.py`**:
    - `meteo_estaciones` en el bucle de parsers;
    - un check de `LOCAL_NAIVE` con el payload desplazado;
    - un check de la clave por estación.
14. **`deploy_pi/instalar.sh`** (mi decisión): cambiar `systemctl enable --now`
    por `systemctl enable` más `systemctl restart`.
    - Así se cumple lo que ya dice `PASOS.md` («reinicia el servicio»), que
      ahora no es verdad: gana el código y se corrige.
    - Los comandos de abajo reinician igualmente a mano, por si acaso.

### Orden (mi decisión)

Para capturar antes:

1. En develop: los días cerrados del crudo a `data/raw` (punto 10), y después
   el parser, el fixture, los tests y los mutantes, todo en verde.
2. Porte a raspberry y push de raspberry.
3. El usuario despliega.
4. En develop: la equivalencia de DVC, la documentación, el resto del crudo,
   la bitácora y el push.

El código de la fuente se escribe primero en develop, como pidió el usuario. Lo
único que se adelanta es el push de raspberry. **Antes de cada push se pide
confirmación.**

### Comandos para la Pi (los ejecuta el usuario)

```bash
cd ~/TFM && git pull
sudo env DATOS=/srv/tfm-sd bash deploy_pi/instalar.sh
#   si /srv/tfm-sd no es punto de montaje, pregunta «¿Seguir?»: s
#   el aviso de tarjeta SD es esperado (bitácoras 044 y 051)
sudo systemctl restart tfm-colector      # por si el instalador no reinició
# a los 10 min:
/opt/tfm/.venv/bin/python /opt/tfm/demo/collect.py --status --out /srv/tfm-sd
ls /srv/tfm-sd/raw/source=meteo_estaciones/
```

Es correcto si `meteo_estaciones` aparece en `--status` con al menos 1 sondeo
y sin CAÍDA, y si hay un `date=<día del despliegue>/payloads.ndjson.gz`.

## Captura puente y día del solape

Desde el 07/11 corre en el portátil el sondeo exploratorio. Es un script del
scratchpad: no está en el repo y no es código del producto. Pide la capa cada
2 min con el formato de `append_raw`. Cubre el hueco hasta que la Pi capture,
mientras el portátil y la sesión sigan vivos.

Dónde está la captura:

- Raíz:
  `C:\Users\oppen\AppData\Local\Temp\claude\0632113743a01ff8\c125341f-bb4c-4605-a7b4-a1aa3cef5ddd\scratchpad\captura\raw\source=meteo_estaciones\`.
- Contenido: `date=2026-11-06` (120 sondeos, cerrado) y `date=2026-11-07` en
  adelante (abierto mientras el sondeo siga vivo).
- Es el payload tal como llegó, con `fecha_carg` en epoch ms sin tocar.

**Primer paso del plan:**

1. Copiar a `data/raw/source=meteo_estaciones/` solo los días cerrados.
2. Sacar de ahí el fixture.

El día abierto no se copia mientras el sondeo escriba en él: se copia al
pararlo. Si el scratchpad ya no existe cuando se ejecute el plan, lo que
quede en `data/raw` basta para el fixture.

El día D del despliegue habrá un fichero de ese día en el portátil y otro en la
Pi. `pull_data.sh` usa `--ignore-existing`, así que no traería el de la Pi.

Para ese día, mi decisión: al traer el crudo de la Pi en el segundo plan, se
unen a mano concatenando los gzip, primero el del portátil (gzip admite
miembros concatenados). El portátil se para cuando `--status` de la Pi muestre
la fuente viva. Va escrito en la bitácora para que no se olvide.

## Supuestos

| | Supuesto | Cómo se comprueba o se recalibra |
|---|---|---|
| S1 | `precipitac` se copia cruda; su ventana es desconocida | La primera vez que llueva, comparar con el SYNOP 08285: si se reinicia a diario, es acumulado diario; si coincide con el horario, es 1 h; si son fracciones pequeñas que suman, son 10 min |
| S2 | La convención se decide en cada respuesta con la fila más fresca, nunca fija; `DUDOSA` queda a la vista | `tz_convencion` en el curated; contar `DUDOSA` tras dos semanas |
| S3 | `period_s = 300` | Cadencia medida de W01 y W02: 10 min |
| S4 | `silencio_max_s = 30 min`, provisional, sin medir la noche | `analysis/medir_silencios` tras unas dos semanas. Límite conocido: una sola estación muerta no da CAÍDA |
| S5 | Clave = conjunto de (estación, marca); las filas repetidas se deduplican aguas abajo | El segundo plan deduplica por (`fiwareid`, `ts_utc`) y se queda con el primer `ts_ingest_utc` |
| S6 | Nombre `meteo_estaciones` | — |
| S7 | Unidades sin interpretar (viento en m/s o km/h, desconocido) | Segundo plan, contra el SYNOP |

## Para el builder

- Si el par real de «estación que llega tarde» sale de la captura o se fabrica.
- El nombre exacto del parámetro de agregación y de los tests.
- Qué días entran en la muestra de equivalencia de `curar` (al menos uno por
  fuente).
- Si la guardia de la trampa 018 se parametriza o se añade un caso.

## Criterio de aceptación

- `uv run pytest` y `uv run pytest .claude/tests` en verde; ruff limpio.
- `auditoria/mutar.py` sobre los mutantes 203-206: los cuatro en rojo.
- `curar` idéntico byte a byte en la muestra, `dvc commit -f curar` y
  `dvc status` limpio.
- `demo/selftest.py` en verde en el worktree de raspberry.
- Tras el despliegue (usuario): `meteo_estaciones` en `--status` sin CAÍDA y
  payloads en `/srv/tfm-sd/raw/source=meteo_estaciones/date=<D>/`.

## Entrega

- **Bitácora 063**:
  - la cadencia de cada estación;
  - la convención contrastada con el SYNOP;
  - la clave por el máximo frente a la clave por estación (3 perdidas y 12
    tarde en 4 h);
  - la GVA descartada y Ogimet como fuente histórica;
  - el día del solape.
- **Ficha de trampa** «deduplicar por el máximo pierde la estación que llega
  tarde»: se ofrece cuando esté guardada (pasa el criterio de admisión: un
  ingeniero competente reutilizaría `clave_sondeo` tal cual).
- No hace falta ADR.
- Al cerrar: `/examen` sobre `src/project/ingest/sources.py`.
