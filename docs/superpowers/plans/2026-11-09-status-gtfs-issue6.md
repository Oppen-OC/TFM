# Vida de la captura del GTFS en `--status` (issue #6). Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** que `collect --status` dé por caída la captura del GTFS cuando lleva
más de 12 h sin terminar una comprobación de VLCi, y que la columna «último ok»
no presente el arranque como si fuera un ok.

**Architecture:**
- `capturar_gtfs` fecha `ultima_comprobacion` en toda vuelta que termina bien,
  traiga versión nueva o no. Un error no la fecha.
- `mostrar_estado` juzga el GTFS por esa fecha contra `GTFS_TOLERANCIA_S`, que
  vale dos `GTFS_PERIODO_S`. Las demás fuentes no cambian.
- Porte a mano a `demo/collect.py` en la rama `raspberry`. El usuario lo
  despliega en la Pi.

**Tech Stack:** Python 3.11, pandas, httpx (`MockTransport`), pytest, uv, ruff.

**Spec:** sin documento de diseño. El encargo se aprobó en la sesión del
09/11 y se resume en *Encargo aprobado*. Lee también el issue:
`gh issue view 6`.

## Encargo aprobado

- **Un `dup` del GTFS es señal de vida.** Una comprobación que acaba en `dup`
  ha bajado el zip entero y ha comparado su sha1 con los que hay en disco
  (`sources.guardar_gtfs`). Si hubiera habido versión nueva, se habría
  guardado en esa vuelta. `ultimo_ok` sigue siendo la última versión nueva y
  no se juzga: la EMT ha pasado 32 días sin publicar.
- **N = 2, es decir, 12 h.**
  - N = 1 da falsa alarma con un solo error: el reintento llega a la media
    hora, así que la comprobación siguiente cae a las 6 h 30 min.
  - N = 2 aguanta unas 6 h de VLCi caído, con reintentos cada 30 min.
  - N = 4 dejaría perder antes del aviso una versión que dure un día
    (bitácora 042).
- **La columna dice «ninguno»** cuando una fuente no ha dado ningún ok, sea
  cual sea la fuente. El juicio sigue contando desde el arranque. En el GTFS se
  añade «comprobado hace X» o, si no hay comprobación, «sin comprobar».
  Evidencia del 09/11 en la Pi, con 0,17 h en marcha: `gtfs_emt` tenía 0
  snapshots y 1 dup, y la columna decía «hace 11 min (no se juzga)».
- **`ultimo_error` sigue sin fecha.** El log ya pone hora a cada aviso, y la
  alarma salta igual con la tarea colgada que con la tarea fallando en cada
  intento.
- **Fuera de alcance:**
  - Las versiones perdidas desde el 06/10 (bitácora 051).
  - Un catálogo de VLCi atascado con el zip viejo.
  - Una versión que viva menos de 6 h.
  - Un colector sin la tarea `capturar_gtfs`.
  - `sources.py`, `features.py`, `dvc.lock` y la prueba del 07-19/10.

## Global Constraints

- **No se toca `src/project/ingest/sources.py`.** Es dependencia de `curar`.
  `collect.py` no lo es, así que no hace falta la prueba de equivalencia de DVC.
- **Los `buscar` de los mutantes 187, 190, 191 y 192 tienen que seguir
  apareciendo exactamente una vez en `src/project/ingest/collect.py`.**
  `auditoria/mutar.py` aborta si `texto.count(buscar) != 1`. En concreto, deben
  seguir intactos:
  - `    elif caidas:`
  - el bloque `if edad >= 180: … elif caidas: …`
  - `    STATS[key]\n    fallos = 0`
  - `v["ultimo_ok"] or e["arrancado_utc"]`
- **Siguen en verde, sin cambiar lo que comprueban:** los tests de `--status`
  del issue #1, el test parametrizado
  `test_el_silencio_legitimo_mas_largo_medido_no_es_una_caida` y todo
  `uv run pytest`.
- **Se commitea por ruta.** El árbol de trabajo trae cambios del usuario sin
  commitear: `.claude/examenes/004-ingest-sources-y-extraer.md`,
  `docs/00_tema_y_alcance.md` y `docs/bitacora/019-*.md`. Nunca `git add -A`
  ni `git add .`.
- **Comentarios y docstrings en español**, en el estilo del módulo: el porqué
  y la cifra, no el qué.
- **Antes de cada commit:** `uv run ruff format <ficheros> && uv run ruff check --fix <ficheros>`.
- **Mensajes de commit** con prefijo convencional y en español. Terminan con:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- **Sin push** a ningún remoto. El usuario lo autoriza aparte.

## Review Focus

1. **Un latido de un colector anterior al cambio, sin la clave
   `ultima_comprobacion`, leído por el `--status` nuevo.** No debe romper:
   cuenta como «nunca comprobado» y el juicio cuenta desde el arranque. Lo
   cubre el caso `nunca-desde-el-arranque` de la tarea 2, porque el helper no
   escribe la clave.
2. **Colector parado con el GTFS viejo.** Debe salir PARADO (2), no FUENTE
   CAÍDA (3). Ya lo cubre `test_el_colector_parado_no_se_tapa_con_una_fuente_callada`,
   y el orden del bloque del mutante 190 no se toca.
3. **Una clave del latido que no está en `SOURCES` ni es el GTFS** (por
   ejemplo, una fuente retirada). Se conserva la marca `(no se juzga)` y no
   puede lanzar `KeyError`. Se queda la rama existente.
4. **Cambio de hora.** Todo se compara en UTC y la tolerancia va en segundos,
   así que no se depende de la hora local. No hace falta test.
5. **Que el latido serialice la fecha nueva.** Un `Timestamp` sin convertir
   haría fallar `json.dumps`, `latir` solo dejaría un aviso en el log y
   `--status` diría PARADO. Lo cubre la última aserción del test del `dup` en
   la tarea 1.

---

### Task 1: `capturar_gtfs` fecha toda comprobación que termina bien

**Files:**
- Modify: `src/project/ingest/collect.py` (`escribir_latido`, ~l.153-174; `capturar_gtfs`, ~l.289-317)
- Test: `tests/test_persistencia.py` (sección del GTFS, tras `test_el_colector_guarda_el_gtfs_que_anuncia_vlci`, ~l.438)

**Interfaces:**
- Produces: la clave `STATS[GTFS_FUENTE]["ultima_comprobacion"]`, que vale
  `pd.Timestamp | None`, existe desde que arranca `capturar_gtfs` y sale en el
  latido como ISO 8601 o `null`.

- [ ] **Step 1: Escribe los dos tests que fallan**

Saca a una constante de módulo `PAQUETE_VLCI` el dict `paquete` del test
existente y úsalo en los tres tests. Añade un helper
`_una_vuelta_gtfs(colector, root, responder) -> None`, que es el
`asyncio.run` de `capturar_gtfs` con `httpx.MockTransport(responder)`.

```python
def test_una_comprobacion_sin_version_nueva_fecha_la_vida_del_gtfs(
    tmp_path, colector, monkeypatch
):
    """La EMT ha pasado 32 días sin publicar (issue #6). Un `dup` ha bajado el
    zip entero y lo ha comparado por sha1: si hubiera versión nueva, estaría
    guardada. Es la prueba de que la captura sigue viva."""
    gtfs_zip = _zip(**{"stop_times.txt": "trip_id\nA\n"})
    sources.guardar_gtfs(tmp_path, gtfs_zip, URL_GTFS, T0)
    ahora = T0 + pd.Timedelta(hours=6)
    monkeypatch.setattr(colector, "now_utc", lambda: ahora)
    # responder: package_show -> PAQUETE_VLCI; el zip -> PARAR.set() y gtfs_zip
    ...
    st = colector.STATS[sources.GTFS_FUENTE]
    assert (st["ok"], st["dup"], st["ultimo_ok"]) == (0, 1, None)
    assert st["ultima_comprobacion"] == ahora
    colector.escribir_latido(tmp_path)
    latido = json.loads((tmp_path / "_status.json").read_text(encoding="utf-8"))
    assert latido["fuentes"][sources.GTFS_FUENTE]["ultima_comprobacion"] == ahora.isoformat()


def test_una_comprobacion_que_falla_no_fecha_la_vida_del_gtfs(tmp_path, colector):
    """Una tarea que falla en cada intento sube `err` y nada más: si el intento
    fallido fechara la comprobación, `--status` la daría por viva."""
    # responder: PARAR.set() y httpx.Response(503) a cualquier petición
    ...
    st = colector.STATS[sources.GTFS_FUENTE]
    assert st["err"] == 1
    assert st["ultima_comprobacion"] is None
```

- [ ] **Step 2: Comprueba que fallan**

Run: `uv run pytest tests/test_persistencia.py -k "fecha_la_vida_del_gtfs" -v`
Expected: los dos FAIL con `KeyError: 'ultima_comprobacion'`.

- [ ] **Step 3: Implementa en `capturar_gtfs` y `escribir_latido`**

En `capturar_gtfs` van estas líneas exactas, porque los mutantes 209 y 210
las buscan tal cual:

```python
    st = STATS[GTFS_FUENTE]
    st.setdefault("ultima_comprobacion", None)
```
```python
            ruta = guardar_gtfs(root, z.content, url, ts, modificado)
            st["ultima_comprobacion"] = ts
            if ruta is None:
```

Añade una frase al docstring: `ultima_comprobacion` fecha la última vuelta
que terminó bien, con versión nueva o sin ella, y es lo que juzga
`--status` (issue #6).

En `escribir_latido`, cada fuente se serializa convirtiendo a ISO **todo**
valor `pd.Timestamp` (hoy solo se convierte `ultimo_ok`):

```python
            k: {c: x.isoformat() if isinstance(x, pd.Timestamp) else x for c, x in v.items()}
```

- [ ] **Step 4: Comprueba que pasan, y que no se rompe nada**

Run: `uv run pytest tests/test_persistencia.py -v`
Expected: todo PASS, también `test_el_colector_guarda_el_gtfs_que_anuncia_vlci`
y los tests de `--status`.

- [ ] **Step 5: Commit**

```bash
uv run ruff format src/project/ingest/collect.py tests/test_persistencia.py
uv run ruff check --fix src/project/ingest/collect.py tests/test_persistencia.py
git add src/project/ingest/collect.py tests/test_persistencia.py
git commit -m "feat(ingest): el latido fecha la última comprobación del GTFS (issue #6)"
```

---

### Task 2: `--status` juzga el GTFS por su última comprobación y la columna no finge un ok

**Files:**
- Modify: `src/project/ingest/collect.py` (constantes ~l.80; docstring del módulo, punto 4, ~l.23-33; `mostrar_estado`, ~l.177-214)
- Test: `tests/test_persistencia.py` (helper `_status` ~l.448 y sección «Latido»)

**Interfaces:**
- Consumes: `STATS[GTFS_FUENTE]["ultima_comprobacion"]` de la tarea 1. En el
  latido llega como ISO, `null` o ausente.
- Produces: `GTFS_TOLERANCIA_S: int`, en `collect.py`, y
  `_hace(s: float) -> str`, en `collect.py`, que devuelve `"hace N min"` si
  `s < 5400` y `"hace N.N h"` si no, con el formato que ya tiene la columna.

- [ ] **Step 1: Amplía el helper `_status` y escribe los tests que fallan**

El helper recibe un parámetro nuevo,
`gtfs_comprobado_hace: pd.Timedelta | None = pd.Timedelta(seconds=10)`, que
va antes de `**ultimo_ok`. Si no es `None`, escribe
`STATS[GTFS_FUENTE]["ultima_comprobacion"] = ahora - gtfs_comprobado_hace`. Si
es `None`, **no escribe la clave**: así reproduce también un latido viejo.
Actualiza su docstring: el GTFS no ha sacado versión nueva desde el arranque,
que es lo normal, pero se comprobó hace 10 s.

```python
@pytest.mark.parametrize(
    ("comprobado_hace", "esperado"),
    [
        (pd.Timedelta(minutes=10), 0),
        (pd.Timedelta(hours=7), 0),
        (pd.Timedelta(hours=13), 3),
        (None, 3),
    ],
    ids=[
        "comprobado-hace-10-min",
        "un-fallo-y-su-reintento",
        "dos-periodos-sin-comprobar",
        "nunca-desde-el-arranque",
    ],
)
def test_gtfs_se_juzga_por_su_ultima_comprobacion(
    tmp_path, colector, monkeypatch, capsys, comprobado_hace, esperado
):
    """Sin versión nueva en 32 días (01/08 → 02/09) la captura puede estar
    sana. Lo que no puede es pasar dos periodos sin terminar una comprobación:
    un fallo y su reintento a la media hora ya pasan de uno."""
    codigo = _status(
        colector, monkeypatch, tmp_path, DIA,
        gtfs_comprobado_hace=comprobado_hace,
        **{sources.GTFS_FUENTE: DIA - pd.Timedelta(days=32)},
    )
    assert codigo == esperado
    if esperado:
        assert sources.GTFS_FUENTE in capsys.readouterr().out.split("\n")[1]


def test_la_columna_del_ultimo_ok_no_hace_pasar_el_arranque_por_un_ok(
    tmp_path, colector, monkeypatch, capsys
):
    """09/11 en la Pi: `gtfs_emt` con 0 versiones y 1 comprobación, y la
    columna «último ok» decía «hace 11 min», que era la edad del arranque."""
    codigo = _status(
        colector, monkeypatch, tmp_path, DIA,
        gtfs_comprobado_hace=pd.Timedelta(minutes=11),
        **{sources.GTFS_FUENTE: None},
    )
    (linea,) = [
        x for x in capsys.readouterr().out.splitlines()
        if x.strip().startswith(sources.GTFS_FUENTE)
    ]
    assert codigo == 0
    assert "ninguno · comprobado hace 11 min" in linea
```

- [ ] **Step 2: Comprueba que fallan**

Run: `uv run pytest tests/test_persistencia.py -k "ultima_comprobacion or columna_del_ultimo_ok" -v`
Expected: FAIL `dos-periodos-sin-comprobar` y `nunca-desde-el-arranque`
(sale 0, no 3), y FAIL el test de la columna (no encuentra «ninguno»).

- [ ] **Step 3: Implementa la constante, `_hace` y el juicio en `mostrar_estado`**

Junto a `FLUSH_SEG` y `LATIDO_SEG`, con el porqué de N = 2 en un comentario
de tres líneas (ver *Encargo aprobado*). La línea es exacta porque la busca el
mutante 211:

```python
GTFS_TOLERANCIA_S = 2 * GTFS_PERIODO_S
```

El cuerpo del bucle de `mostrar_estado` queda así. Lo fijan los mutantes 208
y 212 y los `buscar` intactos de 187 y 192:

```python
    for k, v in e["fuentes"].items():
        # Sin ningún sondeo bueno, la fuente lleva callada desde el arranque.
        s = (ahora - pd.Timestamp(v["ultimo_ok"] or e["arrancado_utc"])).total_seconds()
        ok = _hace(s) if v["ultimo_ok"] else "ninguno"
        if k == GTFS_FUENTE:
            # Su último ok es la última versión nueva, y la EMT ha pasado 32 días
            # sin publicar: se juzga la última comprobación terminada (issue #6).
            c = v.get("ultima_comprobacion")
            s = (ahora - pd.Timestamp(c or e["arrancado_utc"])).total_seconds()
            ok += f" · comprobado {_hace(s)}" if c else " · sin comprobar"
            tolerado = GTFS_TOLERANCIA_S
        else:
            tolerado = SOURCES[k].silencio_tolerado(ahora) if k in SOURCES else None
        if tolerado is None:
            marca = "  (no se juzga)"
        elif s > tolerado:
            marca = "  CAÍDA"
            caidas.append(k)
        else:
            marca = ""
        filas.append(
            f"  {k:22} {v['ok']:>10,} {v['filas']:>12,} {v['dup']:>7} {v['err']:>6}"
            f"  {ok}{marca}"
        )
```

En el punto 4 del docstring del módulo, cambia «El GTFS no se juzga: …» por
esto: el GTFS se juzga por su última comprobación terminada, con versión nueva
o sin ella, contra `GTFS_TOLERANCIA_S`; su último ok es la última versión
nueva, y la EMT ha pasado hasta 32 días sin publicar (issue #6).

- [ ] **Step 4: Comprueba que pasan los nuevos y los del issue #1**

Run: `uv run pytest tests/test_persistencia.py -v`
Expected: todo PASS. En particular, los siete casos de
`test_el_silencio_legitimo_mas_largo_medido_no_es_una_caida`, los cuatro de
`test_renfe_callada_de_madrugada_no_es_una_caida` y
`test_la_fuente_que_arranca_devolviendo_errores_sale_caida`.

- [ ] **Step 5: Suite entera y los `buscar` intactos**

Run: `uv run pytest`
Expected: todo `passed` o `xfailed`.

Run: `uv run python -c "t=open('src/project/ingest/collect.py',encoding='utf-8').read(); print([t.count(s) for s in ['    elif caidas:', '    STATS[key]\n    fallos = 0', 'v[\"ultimo_ok\"] or e[\"arrancado_utc\"]']])"`
Expected: `[1, 1, 1]`

- [ ] **Step 6: Commit**

```bash
uv run ruff format src/project/ingest/collect.py tests/test_persistencia.py
uv run ruff check --fix src/project/ingest/collect.py tests/test_persistencia.py
git add src/project/ingest/collect.py tests/test_persistencia.py
git commit -m "fix(ingest): --status juzga la captura del GTFS por su última comprobación (issue #6)"
```

---

### Task 3: mutantes 208-212 y cierre en la documentación

**Files:**
- Modify: `auditoria/catalogo.toml` (al final)
- Create: `auditoria/resultados/mutantes_<hash>.json` (lo escribe `mutar.py`)
- Modify: `CLAUDE.md` (sección *Tests*, viñeta de `tests/test_persistencia.py`)
- Modify: `docs/bitacora/061-el-silencio-legitimo-de-cada-fuente-va-de-10-minutos-a-6-horas-y-el-gtfs-32-dias.md` (tabla, fila `gtfs_emt`; *Qué se hizo / qué queda abierto*)

**Interfaces:**
- Consumes: las líneas exactas fijadas en las tareas 1 y 2.

- [ ] **Step 1: Añade los cinco mutantes**

Todos con `capa = "persistencia"`, `fichero = "src/project/ingest/collect.py"`,
`sondas = []` y un comentario de una línea con el porqué, en el estilo de
187-193.

| id | nombre | buscar | reemplazar | detector |
|----|--------|--------|------------|----------|
| 208 | el GTFS se juzga por su última versión nueva | `            s = (ahora - pd.Timestamp(c or e["arrancado_utc"])).total_seconds()` | igual, con `v["ultimo_ok"]` en lugar de `c` | `test_gtfs_se_juzga_por_su_ultima_comprobacion` |
| 209 | solo una versión nueva fecha la comprobación | `st["ultima_comprobacion"] = ts` + `if ruta is None: … else:` (las cuatro líneas) | la fecha pasa dentro del `else:` | `test_una_comprobacion_sin_version_nueva_fecha_la_vida_del_gtfs` |
| 210 | un intento fallido cuenta como comprobación | `            r = await client.get(GTFS_PAQUETE)` | `            st["ultima_comprobacion"] = ts` y, en la línea siguiente, la línea buscada | `test_una_comprobacion_que_falla_no_fecha_la_vida_del_gtfs` |
| 211 | la tolerancia del GTFS es un solo periodo | `GTFS_TOLERANCIA_S = 2 * GTFS_PERIODO_S` | `GTFS_TOLERANCIA_S = GTFS_PERIODO_S` | `test_gtfs_se_juzga_por_su_ultima_comprobacion` |
| 212 | la columna enseña el arranque como un ok | `        ok = _hace(s) if v["ultimo_ok"] else "ninguno"` | `        ok = _hace(s)` | `test_la_columna_del_ultimo_ok_no_hace_pasar_el_arranque_por_un_ok` |

Los detectores llevan el prefijo `tests/test_persistencia.py::`.

- [ ] **Step 2: Commit del catálogo, para que `mutar.py` vea `src/` y `tests/` limpios contra HEAD**

```bash
git add auditoria/catalogo.toml
git commit -m "test(auditoria): mutantes 208-212 de la vida del GTFS (issue #6)"
```

- [ ] **Step 3: Ejecuta los cinco**

Run: `uv run python auditoria/mutar.py --solo 208 209 210 211 212`
Expected: controles en verde y los cinco «detectado» por su detector. Si
alguno sale «no detectado», para y repórtalo: no ajustes el test para que
caiga.

- [ ] **Step 4: Documentación**

- `CLAUDE.md`, viñeta de `tests/test_persistencia.py`: después de «… con una
  fuente callada de más (issue #1)», añade «, ni con la captura del GTFS sin
  comprobar en 12 h (issue #6)».
- Bitácora 061:
  - En la fila `gtfs_emt` de la tabla, cambia «no se juzga» por «última
    comprobación, 12 h (#6)».
  - En «Abierto», quita «Señal de vida del GTFS (#6)».
  - En «Hecho», añade una línea: `--status` juzga el GTFS por la última
    comprobación terminada, con tolerancia de dos periodos (12 h); mutantes
    208-212 (issue #6).

- [ ] **Step 5: Andamiaje y commit**

Run: `uv run pytest .claude/tests`
Expected: todo PASS.

```bash
git add auditoria/resultados/mutantes_*.json CLAUDE.md docs/bitacora/061-el-silencio-legitimo-de-cada-fuente-va-de-10-minutos-a-6-horas-y-el-gtfs-32-dias.md
git commit -m "docs(ingest): vida del GTFS en --status; mutantes 208-212 detectados"
```

Añade solo el JSON nuevo de resultados, no otros que haya sin seguimiento.

---

### Task 4: porte a la rama `raspberry`

**Files:**
- Modify: `C:\Users\oppen\Code\TFM-raspberry\demo\collect.py` (`STATS` l.70-72; docstring l.30-31; `escribir_latido` l.125-141; `mostrar_estado` l.144-179; `capturar_gtfs` l.253-283)
- Create (fuera del repo): `<scratchpad>\verificar_demo.py`

**Interfaces:**
- Consumes: la semántica de las tareas 1 y 2.

- [ ] **Step 1: Porta a mano, sin cherry-pick**

`demo/` importa en plano (`from sources import ...`), tiene su propio estilo
de líneas largas y no tiene `project`. Lleva al worktree
`C:\Users\oppen\Code\TFM-raspberry` lo mismo que las tareas 1 y 2:

- `st.setdefault(...)` y `st["ultima_comprobacion"] = ts` en `capturar_gtfs`;
- la serialización genérica de los `Timestamp` en `escribir_latido`;
- `GTFS_TOLERANCIA_S = 2 * GTFS_PERIODO_S`, con su comentario;
- `_hace` y el bucle nuevo en `mostrar_estado`;
- el docstring.

No toques `demo/sources.py`.

- [ ] **Step 2: Verifica sin red con un script desechable**

`verificar_demo.py` hace esto:

- inserta `C:\Users\oppen\Code\TFM-raspberry\demo` en `sys.path` e importa
  `collect`;
- reproduce, con `httpx.MockTransport` y un directorio temporal, los dos casos
  de la tarea 1 (un `dup` fecha la comprobación, un 503 no);
- reproduce los cinco escenarios de `--status` de la tarea 2, monkeypatcheando
  `collect.now_utc`, `collect.INICIO` y `collect.STATS` a mano. Comprueba los
  códigos 0, 0, 3, 3, 0 y el texto «ninguno · comprobado hace 11 min»;
- termina con `print("OK")`.

Run: `uv run --project C:/Users/oppen/Code/TFM python <scratchpad>/verificar_demo.py`
Expected: `OK`

Run (desde `C:\Users\oppen\Code\TFM-raspberry\demo`): `uv run --project C:/Users/oppen/Code/TFM python selftest.py`
Expected: sin fallos, igual que antes del porte.

- [ ] **Step 3: Commit en `raspberry`, sin push**

```bash
git -C C:/Users/oppen/Code/TFM-raspberry add demo/collect.py
git -C C:/Users/oppen/Code/TFM-raspberry commit -m "fix(demo): --status juzga la captura del GTFS por su última comprobación (issue #6)"
```

---

## Después de las tareas (sesión principal, no subagente)

1. Revisión final de la rama completa, en Opus, y skill `pre-merge`.
2. Parar y preguntar antes de cualquier push (`develop`/rama y `raspberry`) y
   antes de comentar en el issue #6.
3. Comandos para la Pi, que despliega el usuario. Solo después del push de
   `raspberry`:
   ```bash
   cd ~/TFM && git pull
   sudo env DATOS=/srv/tfm-sd bash deploy_pi/instalar.sh   # reinicia el servicio
   /opt/tfm/.venv/bin/python /opt/tfm/demo/collect.py --status --out /srv/tfm-sd
   ```
   Lo esperado: código 0, y en la línea de `gtfs_emt`, «ninguno · comprobado
   hace N min».
