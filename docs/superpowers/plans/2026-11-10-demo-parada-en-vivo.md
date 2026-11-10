# Demo en vivo por parada: plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** una página de Streamlit donde se elige una parada de la EMT y se ven, con los datos de hoy, los buses que van hacia ella con `P(> 5 min tarde)`, la regla simple al lado y la verificación cuando pasan.

**Architecture:** el colector de siempre escribe el crudo en una carpeta propia de la demo. Cada ciclo, `services/vivo.py` elige las capturas como `reprocesar`, rastrea y etiqueta con las funciones del pipeline, calcula `t_disp`, añade como filas pendientes las paradas que el viaje aún no ha pasado y llama a `features.construir` sin descartar las filas sin objetivo. El clasificador ya cargado por `Servicio` predice; un `Marcador` congela la primera predicción y la verifica. La API la expone en `/vivo/...` y la UI la pinta.

**Tech Stack:** Python 3.10+, pandas, FastAPI, Streamlit 1.59 (`st.fragment(run_every=...)`), pytest. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-11-10-demo-parada-en-vivo-design.md`

## Global Constraints

- Ninguna variable del modelo se calcula fuera de `features.construir`; la demo solo le prepara la entrada.
- Ningún cálculo usa un paso con `t_disp_utc` posterior al `ahora` del ciclo, ni sin `t_disp_utc` (ADR-022, trampa 017).
- La demo lee y escribe solo bajo su `DATA_ROOT`. Nunca `data/` del corpus ni el `metrics/` del repo.
- `ui/` no importa `services/`; `api/` no importa pandas ni sklearn; nada de `os.getenv` fuera de `config.py`.
- Las capturas de un mismo sondeo se eligen con `clave_sondeo` y la regla de `reprocesar`: la que más filas trae (trampa 011).
- Un sondeo es un payload con filas (trampa 018).
- Toda columna se une por clave (`CLAVE_VIAJE`, `CLAVE_PASO`), nunca por posición (trampa 012).
- Guardia nueva ⇒ mutante en `auditoria/catalogo.toml`. Libres desde el **214**, correlativos en el orden de las tareas.
- `reprocesar.py`, `sources.py`, `gtfs.py`, `etiquetado.py` y `features.py` son dependencias de DVC: la tarea 10 demuestra que las salidas no cambian.
- Umbral de «tarde»: `features.umbral_retraso_s` (300 s). Horizontes: `model_service.horizontes()` (1, 2, 3, 5, 10).
- Identificadores, docstrings y textos en español, como el resto del repo. Commits sin líneas de atribución.

## Review Focus

1. **El crudo del día se lee mientras el colector lo amplía**: el último miembro gzip puede estar a medias. El ciclo lee lo completo y sigue (test en la tarea 2).
2. **Antes de las 04:00 locales, o en un día de servicio que cruza la medianoche UTC**, hacen falta los ficheros de dos fechas UTC (test en la tarea 7).
3. **Una parada sin buses en camino, o de madrugada**: tabla vacía, sin error (test en la tarea 5).
4. **El día de la demo no hay versión del GTFS vigente en `GTFS_DIR`**: mensaje claro al pedir la parada; la API arranca igual (test en la tarea 7).
5. **El tutor cambia de parada y vuelve**: lo congelado de la primera parada sigue ahí (test en la tarea 6).

---

### Task 1: Medir el ciclo antes de construir

**Files:**
- Create: `src/project/analysis/medir_ciclo_vivo.py`

**Interfaces:**
- Produces: la cifra que fija `CICLO_S` en la tarea 7 (30 si cabe; si no, lo medido redondeado hacia arriba a 10 s).

- [ ] **Step 1: Escribir el medidor.** CLI `--dia 2026-10-01 --hasta 10:00 --stop <stop_id>`; sin `--stop`, la parada del horario vigente con más líneas. Sobre el corpus (`settings`, solo lectura): `prepare.cargar_dia(dia)` recortado a `ts_utc <= hasta`, filtrado a las líneas que paran en la parada; cronometra por separado `prepare.etiquetar_dia`, `features.instante_disponible` y `features.construir(horizonte=2)` sobre los pasos de esas líneas de los días anteriores con la misma `feed_version` más los del día. Escribe un JSON en stdout con los segundos de cada paso y las filas de entrada.
- [ ] **Step 2: Comprobar que recortar por líneas no cambia nada.** El mismo medidor, con `--comprobar-lineas`, etiqueta el día con todas las líneas y con las de la parada y compara los `pasos` de esas líneas por `CLAVE_PASO`: `retraso_s` y `t_obs_utc` idénticos. Si difieren, se para aquí y se informa: el recorte no vale.
- [ ] **Step 3: Ejecutar**

Run: `uv run python -m project.analysis.medir_ciclo_vivo --dia 2026-10-01 --hasta 10:00 --comprobar-lineas`
Expected: JSON con `segundos_total` y `recorte_lineas_identico: true`.

- [ ] **Step 4: Anotar la cifra** al final de este plan, en *Resultado de la tarea 1*, y ofrecer ficharla en la bitácora.
- [ ] **Step 5: Commit**

```bash
git add src/project/analysis/medir_ciclo_vivo.py docs/superpowers/plans/2026-11-10-demo-parada-en-vivo.md
git commit -m "feat(analysis): medidor del ciclo de la demo en vivo"
```

---

### Task 2: Elegir las capturas en memoria, tolerando la cola a medias

**Files:**
- Modify: `src/project/ingest/reprocesar.py` (el bucle de `reprocesar`)
- Test: `tests/test_persistencia.py`

**Interfaces:**
- Produces:

```python
@dataclass
class Capturas:
    elegidos: dict[int | str, tuple[str, pd.DataFrame]]  # clave_sondeo -> (día, df), en orden de primera aparición
    payloads: int
    errores: int
    duplicados: int
    completados: set
    geo: pd.DataFrame | None
    ultimo_ok_utc: pd.Timestamp | None           # ts_ingest del último payload con filas
    ultimo_error: tuple[pd.Timestamp, str] | None  # último payload sin filas o que no parsea, si es posterior al último ok

def elegir_capturas(ficheros: Iterable[Path], source: str, tolerar_cola: bool = False) -> Capturas
```

Mensaje del error: `str(payload["error"])[:200]` si el payload trae `error`; si `parse` lanza, el nombre de la excepción; si no, `"payload sin filas"`.

- [ ] **Step 1: Tests que fallan**

```python
def test_elegir_capturas_tolera_la_cola_a_medias(tmp_path):
    # tres payloads con filas y un cuarto miembro gzip cortado a la mitad
    c = elegir_capturas([f], "emt_buses", tolerar_cola=True)
    assert len(c.elegidos) == 3

def test_sin_tolerar_la_cola_a_medias_falla(tmp_path):
    with pytest.raises((EOFError, gzip.BadGzipFile, json.JSONDecodeError)):
        elegir_capturas([f], "emt_buses")

def test_el_error_posterior_al_ultimo_ok_se_informa(tmp_path):
    # ok a las 10:00:00, {"error": {"code": 500}} a las 10:00:30
    c = elegir_capturas([f], "emt_buses")
    assert c.ultimo_ok_utc == pd.Timestamp("2026-11-10T10:00:00Z")
    assert c.ultimo_error[0] == pd.Timestamp("2026-11-10T10:00:30Z")
    assert "500" in c.ultimo_error[1]

def test_un_ok_despues_del_error_lo_borra(tmp_path):
    assert elegir_capturas([f], "emt_buses").ultimo_error is None
```

Los payloads salen de `tests/fixtures.json`, como en el resto del fichero.

- [ ] **Step 2: Run** `uv run pytest tests/test_persistencia.py -k elegir_capturas -v` → FAIL (`elegir_capturas` no existe).
- [ ] **Step 3: Implementar** `elegir_capturas` con el bucle actual de `reprocesar`; `reprocesar` pasa a llamarla con `sorted(dir_raw.rglob("*.ndjson.gz"))` y conserva sus claves de retorno. Con `tolerar_cola`, la lectura de un fichero se corta en la primera línea o miembro gzip incompleto.
- [ ] **Step 4: Run** `uv run pytest tests/test_persistencia.py tests/test_ingest.py -v` → PASS, los de siempre incluidos (la guardia de la trampa 011 sigue ahí).
- [ ] **Step 5: Mutantes 214 y 215** en `auditoria/catalogo.toml`: 214 quita la tolerancia (detector: `test_elegir_capturas_tolera_la_cola_a_medias`); 215 no borra `ultimo_error` con un ok posterior (detector: `test_un_ok_despues_del_error_lo_borra`). Run `uv run python auditoria/mutar.py --solo 214 215` → ambos detectados.
- [ ] **Step 6: Commit** `feat(ingest): elegir_capturas en memoria, con la cola a medias y el último error`

---

### Task 3: Las paradas programadas de un viaje, y el nombre de cada parada

**Files:**
- Modify: `src/project/gtfs.py` (`cargar_horario`, el `DataFrame` `paradas`)
- Modify: `src/project/etiquetado.py`
- Test: `tests/test_etiquetado.py`

**Interfaces:**
- Produces:
  - `Horario.paradas` gana la columna `nombre` (de `stops.stop_name`, `""` si falta).
  - `etiquetado.paradas_del_viaje(h: Horario, shape_id: str, trip_id: str) -> pd.DataFrame` con columnas `stop_id, stop_sequence, abscisa_parada_m, t_prog_s`, en orden de `stop_sequence`. Sale del `_Patron` de `_Programacion(h).patrones(shape_id)` que contiene el `trip_id`: la misma abscisa y el mismo `t_prog_s` que `_asignar_tramo` escribe en los pasos. Caché de `_Programacion` por `h.version` a nivel de módulo. `KeyError` si el viaje no está en ese trazado.

- [ ] **Step 1: Tests que fallan**

```python
def test_paradas_del_viaje_coinciden_con_los_pasos_observados(...):
    # GTFS sintético y flota de este fichero; un viaje asignado
    r = etiquetar(pos, [h], P)
    v = r.pasos[r.pasos["viaje_id"] == viaje]
    prog = paradas_del_viaje(h, v["shape_id"].iloc[0], v["trip_id"].iloc[0])
    m = v.merge(prog, on="stop_sequence", suffixes=("", "_prog"), validate="one_to_one")
    assert (m["stop_id"] == m["stop_id_prog"]).all()
    assert np.array_equal(m["abscisa_parada_m"], m["abscisa_parada_m_prog"])
    assert np.array_equal(m["t_prog_s"], m["t_prog_s_prog"])
    assert len(prog) >= len(v)

def test_el_horario_trae_el_nombre_de_la_parada(...):
    assert "nombre" in cargar_horario(zip_sintetico).paradas.columns
```

- [ ] **Step 2: Run** `uv run pytest tests/test_etiquetado.py -k "paradas_del_viaje or nombre" -v` → FAIL.
- [ ] **Step 3: Implementar** los dos cambios.
- [ ] **Step 4: Run** `uv run pytest tests/test_etiquetado.py tests/test_mapmatching.py -v` → PASS.
- [ ] **Step 5: Mutante 216**: `paradas_del_viaje` devuelve `t_prog_s` de la primera fila del patrón en vez de la del viaje (detector: `test_paradas_del_viaje_coinciden_con_los_pasos_observados`). `--solo 216` → detectado.
- [ ] **Step 6: Commit** `feat(etiquetado): paradas_del_viaje y nombre de parada en el horario`

---

### Task 4: `construir` acepta filas pendientes y no las descarta

**Files:**
- Modify: `src/project/features.py` (`construir`)
- Test: `tests/test_features.py`

**Interfaces:**
- Produces:
  - `features.FUTURO = pd.Timestamp("2200-01-01", tz="UTC")`.
  - `construir(..., solo_con_objetivo: bool = True)`. Con `False` no se filtra `p[objetivo].notna()`. El docstring fija el contrato: una parada que el viaje aún no ha pasado entra como fila con sus columnas de horario (`stop_id`, `stop_sequence`, `abscisa_parada_m`, `t_prog_s` y las de viaje), `retraso_s` nulo y `t_obs_utc = t_disp_utc = FUTURO`.

- [ ] **Step 1: Tests que fallan**

```python
def test_la_fila_en_vivo_ve_lo_mismo_que_la_del_entrenamiento():
    # pasos sintéticos de dos días (el primero da el sesgo del tramo), varios
    # viajes de una línea con t_disp conocido; R = (viaje V, parada k), h = 2
    completa = construir(pasos, OBJ, horizonte=2, ventanas_flota_min=(5, 15))
    ahora = t_disp de R
    vivo = pasos con: los pasos con t_disp > ahora de viajes en curso como
           pendientes (retraso_s NaN, t_obs_utc = t_disp_utc = FUTURO);
           los de viajes que aún no han empezado, fuera
    en_vivo = construir(vivo, OBJ, horizonte=2, ventanas_flota_min=(5, 15),
                        solo_con_objetivo=False)
    a, b = fila de R en completa, fila de R en en_vivo
    cols = variables(lags_min=(1, 5, 15), ventanas_flota_min=(5, 15))
    pd.testing.assert_series_equal(a[cols], b[cols], check_names=False)

def test_sin_objetivo_la_fila_solo_se_queda_si_se_pide():
    assert R not in construir(vivo, OBJ, horizonte=2)
    assert R in construir(vivo, OBJ, horizonte=2, solo_con_objetivo=False)
```

Reusa el generador de pasos sintéticos de `tests/test_features.py`.

- [ ] **Step 2: Run** `uv run pytest tests/test_features.py -k "en_vivo or sin_objetivo" -v` → FAIL.
- [ ] **Step 3: Implementar.** Si el primer test falla con el filtro ya quitado, alguna variable ve la fila pendiente: se arregla en `construir` sin cambiar su salida con `solo_con_objetivo=True`.
- [ ] **Step 4: Run** `uv run pytest tests/test_features.py -v` → PASS, las guardias 079-082 incluidas.
- [ ] **Step 5: Mutante 217**: el filtro se aplica siempre (detector: `test_sin_objetivo_la_fila_solo_se_queda_si_se_pide`). `--solo 217` → detectado.
- [ ] **Step 6: Commit** `feat(features): construir admite paradas pendientes para la inferencia en vivo`

---

### Task 5: El núcleo del ciclo: lo sabido, lo pendiente y los buses de la parada

**Files:**
- Create: `src/project/services/vivo.py`
- Test: `tests/test_vivo.py`

**Interfaces:**
- Consumes: `features.FUTURO`, `features.construir(..., solo_con_objetivo=False)` (tarea 4); `ParadasDe = Callable[[str, str, str], pd.DataFrame]`, de `(feed_version, shape_id, trip_id)` a la salida de `etiquetado.paradas_del_viaje` (tarea 3). `Vivo` la construye como `lambda v, s, t: paradas_del_viaje(horarios[v], s, t)`; los tests pasan una tabla a mano.
- Produces:

```python
def separar(pasos: pd.DataFrame, ahora: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]
    # (sabidos, no_sabidos): sabido = t_disp_utc no nulo y <= ahora
def pendientes(sabidos: pd.DataFrame, paradas_de: ParadasDe) -> pd.DataFrame
    # por viaje con algún paso sabido: sus paradas con stop_sequence > la última sabida,
    # columnas de viaje copiadas, retraso_s NaN, t_obs_utc = t_disp_utc = FUTURO
def candidatos(sabidos: pd.DataFrame, pend: pd.DataFrame, stop_id: str, horizontes: list[int]) -> pd.DataFrame
    # una fila por viaje que tiene stop_id entre sus pendientes y 1 <= h <= max(horizontes):
    # fecha_servicio, viaje_id, linea, stop_sequence (la última sabida), h, retraso_s, t_disp_utc, con_modelo
def tabla(historial: pd.DataFrame, sabidos: pd.DataFrame, pend: pd.DataFrame, horizonte: int, cfg: dict) -> pd.DataFrame
    # construir sobre historial + sabidos + pend con los parámetros de params.yaml → features (cfg)
```

`h` = `stop_sequence` de la parada en el horario − `stop_sequence` del último paso sabido. `con_modelo` = `h in horizontes`.

- [ ] **Step 1: Tests que fallan** (pasos sintéticos a mano, sin tracker)

```python
def test_un_paso_que_aun_no_se_sabe_queda_pendiente():
    s, n = separar(pasos, ahora)  # un paso con t_disp = ahora + 10 s
    assert clave_del_paso in n and clave_del_paso not in s

def test_un_paso_sin_t_disp_no_se_sabe(): ...

def test_la_fila_del_ciclo_no_ve_el_paso_que_no_se_sabe():
    # el retraso del paso no sabido no aparece en ninguna variable de la fila
    t = tabla(hist, s, pendientes(s, paradas_de), 2, CFG)
    assert fila_del_viaje["retraso_s"] == retraso_del_ultimo_sabido

def test_el_horizonte_se_cuenta_en_el_horario():
    # último sabido seq 4, parada en seq 6, la 5 nunca observada
    assert candidatos(s, p, stop, [1, 2, 3, 5, 10]).loc[0, "h"] == 2

def test_a_una_distancia_sin_modelo_no_hay_prediccion():
    c = candidatos(...)  # h = 4 y h = 11
    assert c.set_index("viaje_id").loc["v4", "con_modelo"] is False
    assert "v11" not in set(c["viaje_id"])

def test_una_parada_sin_buses_en_camino_da_tabla_vacia():
    assert candidatos(s, p, "parada_sin_nadie", [1, 2]).empty

def test_un_viaje_sin_pasos_sabidos_no_entra(): ...
```

- [ ] **Step 2: Run** `uv run pytest tests/test_vivo.py -v` → FAIL.
- [ ] **Step 3: Implementar** las cuatro funciones; uniones por `CLAVE_VIAJE`/`CLAVE_PASO`.
- [ ] **Step 4: Run** `uv run pytest tests/test_vivo.py -v` → PASS.
- [ ] **Step 5: Mutantes 218 y 219**: 218, `separar` da por sabido todo paso con `t_disp_utc` no nulo, sin compararlo con `ahora` (detector: `test_un_paso_que_aun_no_se_sabe_queda_pendiente`); 219, `h` cuenta pasos observados en vez de posiciones del horario (detector: `test_el_horizonte_se_cuenta_en_el_horario`). `--solo 218 219` → detectados.
- [ ] **Step 6: Commit** `feat(services): núcleo del ciclo en vivo`

---

### Task 6: El marcador: congelar la primera predicción y verificarla

**Files:**
- Modify: `src/project/services/vivo.py`
- Test: `tests/test_vivo.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class Prediccion:
    probabilidad: float
    umbral: float
    llega_tarde: bool
    regla_llega_tarde: bool  # retraso_s del último paso sabido > umbral_retraso_s
    h: int
    t_utc: pd.Timestamp

class Marcador:
    def congelar(self, stop_id: str, clave: tuple, p: Prediccion) -> Prediccion  # devuelve la primera; nunca la sustituye
    def verificar(self, stop_id: str, sabidos: pd.DataFrame, umbral_s: float) -> None
        # para cada congelada sin resultado: si hay paso sabido del viaje en stop_id,
        # resultado = {retraso_real_s, llego_tarde: retraso > umbral_s,
        #              acierta_modelo, acierta_regla}
    def entradas(self, stop_id: str) -> dict[tuple, dict]  # {clave: {"congelada": Prediccion, "resultado": dict | None}}
    def resumen(self, stop_id: str) -> dict  # verificados, aciertos_modelo, aciertos_regla, discrepan (entre los verificados)
```

`clave` = `(fecha_servicio, viaje_id)`. Vive en memoria; no se persiste.

- [ ] **Step 1: Tests que fallan**

```python
def test_la_primera_prediccion_queda_congelada():
    m.congelar("S", k, p1); assert m.congelar("S", k, p2) == p1

def test_se_verifica_con_el_paso_sabido_en_la_parada():
    m.verificar("S", sabidos_con_paso_en_S_retraso_310, 300)
    r = m.entradas("S")[k]["resultado"]
    assert r["llego_tarde"] is True and r["retraso_real_s"] == 310

def test_un_paso_aun_no_sabido_no_verifica(): ...

def test_el_marcador_cuenta_las_discrepancias():
    assert m.resumen("S") == {"verificados": 2, "aciertos_modelo": 2,
                              "aciertos_regla": 1, "discrepan": 1}

def test_cambiar_de_parada_no_borra_lo_congelado():
    m.congelar("S", k, p1); m.congelar("T", k2, p3)
    assert m.entradas("S")[k]["congelada"] == p1
```

- [ ] **Step 2: Run** `uv run pytest tests/test_vivo.py -k "congelad or verifica or marcador or parada" -v` → FAIL.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Run** `uv run pytest tests/test_vivo.py -v` → PASS.
- [ ] **Step 5: Mutante 220**: `congelar` sustituye la anterior (detector: `test_la_primera_prediccion_queda_congelada`). `--solo 220` → detectado.
- [ ] **Step 6: Commit** `feat(services): marcador de la demo con la regla simple`

---

### Task 7: El ciclo completo, `Vivo`

**Files:**
- Modify: `src/project/services/vivo.py`
- Test: `tests/test_vivo.py`

**Interfaces:**
- Consumes: `elegir_capturas` (tarea 2), `paradas_del_viaje` (tarea 3), las funciones de las tareas 5 y 6, `prepare.etiquetar_dia`, `prepare.cargar_parametros`, `prepare.ventana_servicio`, `features.instante_disponible`, `features.con_disponibilidad`, `gtfs.versiones`, `gtfs.cargar_horario`, `gtfs.elegir_horario`, `Servicio.mas_de_5min`, `Servicio.modelos`.
- Produces:

```python
CICLO_S: int      # de la tarea 1
SIN_DATOS_S = 120 # sin sondeo bueno durante más, se avisa aunque no haya error

class DemoNoDisponible(Exception): ...   # la API la traduce a 503
class ParadaDesconocida(Exception): ...  # y esta a 404

def ficheros_del_dia(raw_emt: Path, ahora: pd.Timestamp) -> list[Path]
    # los payloads.ndjson.gz de las fechas UTC que cubre ventana_servicio(día de servicio de ahora)

class Vivo:
    @classmethod
    def desde_disco(cls, servicio: Servicio) -> "Vivo"  # nunca lanza: lo que falte va a self.problema
    def paradas(self) -> list[dict]  # [{"stop_id", "nombre", "lineas": [str]}] del horario vigente hoy
    def parada(self, stop_id: str, ahora: pd.Timestamp | None = None) -> dict
```

`parada` devuelve, con instantes en ISO 8601 UTC:

```python
{"stop_id": str, "nombre": str, "ahora_utc": str, "datos_hasta_utc": str | None,
 "error": None | {"mensaje": str, "desde_utc": str},
 "filas": [{"linea": str, "viaje_id": str, "paradas": int, "retraso_actual_s": float,
            "edad_s": float, "probabilidad": float | None, "umbral": float | None,
            "llega_tarde": bool | None, "regla_llega_tarde": bool,
            "congelada": dict | None, "resultado": dict | None}],
 "marcador": {"verificados": int, "aciertos_modelo": int, "aciertos_regla": int, "discrepan": int}}
```

Las filas son los candidatos de ahora más los viajes ya congelados en esa parada, para que lo verificado siga a la vista. El historial (pasos de `settings.interim_dir` de los días anteriores, con su `t_disp` por `con_disponibilidad`) se carga una vez en `desde_disco`, entero: el sesgo del tramo en el entrenamiento usa todos los días previos con la misma versión. El resultado de cada parada se guarda `CICLO_S` segundos. El vector va a `Servicio.mas_de_5min` con exactamente las columnas del artefacto (`Servicio.modelos()`).

- [ ] **Step 1: Tests que fallan**

```python
def test_sin_datos_la_demo_no_tumba_el_arranque(tmp_path, monkeypatch):
    # DATA_ROOT y GTFS_DIR vacíos
    v = Vivo.desde_disco(servicio_falso)
    assert v.problema
    with pytest.raises(DemoNoDisponible):
        v.parada("123")

def test_sin_horario_vigente_hoy_se_dice(tmp_path, monkeypatch):
    # un GTFS sintético cuya vigencia acabó
    with pytest.raises(DemoNoDisponible, match="horario"):
        Vivo.desde_disco(servicio_falso).parada("123")

def test_de_madrugada_se_leen_dos_fechas(tmp_path):
    # 02:30 locales del 11/11: el día de servicio es el 10/11
    fs = ficheros_del_dia(raw, pd.Timestamp("2026-11-11T01:30Z"))
    assert {f.parent.name for f in fs} == {"date=2026-11-10", "date=2026-11-11"}

def test_una_parada_que_no_existe_es_desconocida(...):
    with pytest.raises(ParadaDesconocida): v.parada("no_existe")
```

- [ ] **Step 2: Run** `uv run pytest tests/test_vivo.py -k "arranque or horario or madrugada or desconocida" -v` → FAIL.
- [ ] **Step 3: Implementar** `ficheros_del_dia` y `Vivo`. Error de la fuente: `Capturas.ultimo_error`; si no lo hay y `ahora − ultimo_ok_utc > SIN_DATOS_S`, `"Sin datos nuevos de la EMT desde HH:MM"` en hora local.
- [ ] **Step 4: Run** `uv run pytest tests/test_vivo.py -v` → PASS.
- [ ] **Step 5: Humo sobre un día real del corpus**, solo lectura y con `ahora` en el pasado (es una prueba, no un modo de la demo):

Run: `uv run python -c "import pandas as pd; from project.services.model_service import Servicio; from project.services.vivo import Vivo; v = Vivo.desde_disco(Servicio.desde_disco()); import json; print(json.dumps(v.parada('<stop de la tarea 1>', pd.Timestamp('2026-10-01T08:00Z')), indent=1, default=str)[:3000])"`
Expected: filas con `probabilidad` entre 0 y 1 para `h` con modelo, `error: null`, y el tiempo del ciclo del orden del de la tarea 1.

- [ ] **Step 6: Commit** `feat(services): ciclo de la demo en vivo por parada`

---

### Task 8: Endpoints `/vivo`

**Files:**
- Create: `src/project/api/routers/vivo.py`
- Modify: `src/project/api/schemas.py`, `src/project/api/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `Vivo.paradas()`, `Vivo.parada(stop_id)`, `DemoNoDisponible`, `ParadaDesconocida` (tarea 7).
- Produces: `GET /vivo/paradas` → `list[ParadaVivo]`; `GET /vivo/parada/{stop_id}` → `EstadoParada`, con los campos del dict de la tarea 7. `DemoNoDisponible` → 503 con el motivo; `ParadaDesconocida` → 404. `main.py`: el `lifespan` crea `app.state.vivo = Vivo.desde_disco(app.state.servicio)` e incluye el router. Dependencia `vivo(request)` sustituible en los tests, como `servicio`.

- [ ] **Step 1: Tests que fallan** (con un `Vivo` falso, como el `Servicio` falso del fichero)

```python
def test_paradas_en_vivo(falso_vivo): r = client.get("/vivo/paradas"); assert r.status_code == 200 and r.json()[0]["stop_id"] == "123"
def test_estado_de_la_parada_pasa_tal_cual(falso_vivo): assert r.json()["marcador"]["discrepan"] == 1
def test_parada_desconocida_es_404(falso_vivo): ...
def test_demo_sin_datos_es_503(falso_vivo): ...
def test_los_nulos_de_una_fila_sin_modelo_viajan(falso_vivo): assert fila["probabilidad"] is None
```

- [ ] **Step 2: Run** `uv run pytest tests/test_api.py -k vivo -v` → FAIL.
- [ ] **Step 3: Implementar** router, esquemas y `main.py`.
- [ ] **Step 4: Run** `uv run pytest tests/test_api.py -v` → PASS.
- [ ] **Step 5: Commit** `feat(api): endpoints de la demo en vivo`

---

### Task 9: La página de Streamlit

**Files:**
- Modify: `src/project/ui/app.py` (se sustituye la plantilla)

**Interfaces:**
- Consumes: `GET /vivo/paradas` y `GET /vivo/parada/{stop_id}` por `requests`, con `settings.api_url`.

- [ ] **Step 1: Implementar la página.**
  - Selector `st.selectbox` sobre `/vivo/paradas`, rotulado `"{nombre} ({stop_id})"`.
  - `@st.fragment(run_every=REFRESCO_S)`, constante de la UI con el valor de `CICLO_S` (la UI no importa `services/`), que pide la parada y pinta: aviso `st.warning` con `error.mensaje`; antigüedad del dato (`ahora_utc − datos_hasta_utc`); tabla con las columnas **Línea · A · Va ahora · Modelo P(>5 min) · Regla simple · Resultado**, en gris las filas sin modelo; la línea del marcador «modelo X/N · regla simple Y/N · casos en que discrepan: D» y debajo «Regla simple = persistencia: «si ya va más de 5 min tarde, llegará tarde».»
  - `st.expander("¿Cómo se calcula esto?")` con el texto del anexo del diseño, literal.
  - API caída: `st.error` con `API no disponible en {API_URL}`; 503: el motivo.
  - Nada de `services/` ni de modelos (CLAUDE.md).
- [ ] **Step 2: Comprobar a mano** con la API sobre el corpus (como el humo de la tarea 7) y la UI: `uv run uvicorn project.api.main:app --port 8000` y `uv run streamlit run src/project/ui/app.py`. Se ve la tabla, el marcador y el desplegable; con la API parada sale el error.
- [ ] **Step 3: Run** `uv run ruff format . && uv run ruff check --fix .` → sin errores.
- [ ] **Step 4: Commit** `feat(ui): página de la demo en vivo por parada`

---

### Task 10: Equivalencia, documentación y guion

**Files:**
- Modify: `README.md`, `docs/07_decisiones.md` (ADR-016), `docs/00_tema_y_alcance.md`, `CLAUDE.md` (*Estado* y *Tests*)

- [ ] **Step 1: Las salidas del pipeline no cambian.** Run `uv run dvc repro` (40-50 min). Expected: `git diff dvc.lock` solo cambia los `md5` de las dependencias de código (`reprocesar.py`, `gtfs.py`, `etiquetado.py`, `features.py`); ningún `outs` ni ninguna métrica. Si cambia alguno, se para y se investiga antes de seguir.
- [ ] **Step 2: Todos los tests.** Run `uv run pytest && uv run pytest .claude/tests` → PASS. Run `uv run python auditoria/mutar.py --solo 214 215 216 217 218 219 220` → todos detectados.
- [ ] **Step 3: README**, sección «Demo en vivo»: preparación del diseño (traer de la Pi con `DESTINO=<demo>/raw deploy_pi/pull_data.sh --verificar`; `reprocesar`, `prepare --metricas <demo>/metrics/prepare.json` y `features --disponibilidad` con `DATA_ROOT`/`GTFS_DIR` de la demo; colector una hora antes; API y UI con el mismo `DATA_ROOT`), en PowerShell (`$env:DATA_ROOT = '...'`).
- [ ] **Step 4: ADR-016**: la demo existe, sin broker. **`docs/00`**: el servido en tiempo real pasa a demo. **`CLAUDE.md`**: `services/vivo.py` y `tests/test_vivo.py` en *Estado* y *Tests*, con sus mutantes.
- [ ] **Step 5: Commit** `docs: demo en vivo por parada (README, ADR-016, alcance)`
- [ ] **Step 6: Proponer al autor** cerrar o reescribir el issue #10 y fichar en la bitácora la cifra de la tarea 1. No se hace sin su visto bueno.

---

## Resultado de la tarea 1

_(se rellena al ejecutarla)_
