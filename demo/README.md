# Demostrador mínimo · Fuentes en tiempo real de València

Prototipo para validar la viabilidad del TFM antes de comprometer el tema.
Cuatro scripts, sin dependencias pesadas, ejecutables en un portátil.

## Instalación

```powershell
uv add httpx pandas pyarrow scipy duckdb
```

Sobre tu repo del TFM, esto acaba viviendo en `src/project/ingest/`.

## Uso

```powershell
python demo\explore.py                 # ¿siguen vivas las 5 fuentes desde mi red?
python demo\selftest.py                # valida parsers y tracker sin tocar la red
python demo\test_diagnose.py           # valida que el diagnóstico discrimina
python demo\collect.py --minutes 1440  # captura de 24 h (incluye hora punta)
python demo\diagnose.py                # GO / NO-GO de la hipótesis del TFM
python demo\track.py data\curated\source=emt_buses
```

Los scripts se lanzan **desde la raíz del repo**, para que `data/` caiga donde
lo versiona DVC.

## El paso que decide el trabajo

`diagnose.py` responde a cuatro preguntas sobre los datos capturados, en orden
creciente de importancia:

1. **Cobertura** — ¿qué fracción de posiciones de bus cae cerca de un tramo con
   dato de tráfico? Si es baja, la fusión solo aplica a parte de la red.
2. **Varianza** — ¿el `estado` varía por hora del día o está casi siempre en la
   misma clase? Una variable sin varianza no predice nada.
3. **Dinámica** — ¿hay tramos congelados que finjan ser dato?
4. **Señal** — ¿los buses van más lentos en los tramos declarados congestionados?
   Es el test directo de la hipótesis central, y **no necesita GTFS, ni
   map-matching, ni etiquetas de retraso**.

Si el punto 4 sale plano con las dos capas de tráfico (categórica y de
intensidad), la fusión no tiene señal y hay que replantear. Cuesta 48 horas
saberlo en septiembre en lugar de en febrero.

## Qué hace cada pieza

| Archivo | Función |
|---|---|
| `sources.py` | Definición de los 5 endpoints y sus parsers. Contiene la corrección de zona horaria (ver abajo) y la geodesia mínima. |
| `explore.py` | Sondeo one-shot: esquema, muestra, latencia medida, nulos y volumen proyectado por fuente. |
| `collect.py` | Colector asíncrono. Guarda payload crudo (NDJSON gzip) **y** Parquet particionado. Deduplica por snapshot. |
| `track.py` | Reconstrucción de identidad de vehículo por asignación húngara con predicción de movimiento. La pieza no trivial. |
| `diagnose.py` | **Go/no-go de la hipótesis del TFM.** Cobertura, varianza, dinámica y el test decisivo: ¿van más lentos los buses donde el tráfico está peor? |
| `selftest.py` | 24 comprobaciones sin red, sobre fixtures con la forma real de los payloads. |
| `test_diagnose.py` | Valida que `diagnose.py` discrimina: detecta señal cuando la hay y no la inventa cuando no la hay. |
| `fixtures.json` | Payloads reales capturados el 15/08/2026 a las ~21:10 CEST. |

## Las tres trampas que este código ya resuelve

**1. El campo `fecha` de la EMT miente dos horas.** Viene en epoch-ms, pero
construido desde la hora local de Madrid tratada como si fuera UTC. En agosto
va +2 h; en invierno irá +1 h. Si no lo corriges con la zona horaria real de
cada fecha, tu serie se parte en el cambio de hora de octubre y no te enteras.
`sources.local_naive_epoch_to_utc()` lo arregla. Mismo problema con
`fechaActualizacion` de Renfe.

**2. `gid` no identifica al vehículo.** Es un autoincrement de una tabla que se
trunca y reinserta entera en cada refresco. Dos sondeos consecutivos tienen
intersección de gids exactamente cero. Sí identifica el *refresco*, y por eso
se usa como `snapshot_id` para deduplicar.

**3. La raíz del JSON de Renfe es un objeto, no un array.** Es
`{fechaActualizacion, trenes: [...]}`. Cualquier código que haga
`json.loads(r.text)[0]` revienta.

## Resultado del autotest

```
24 comprobaciones OK, 0 fallos

tracker ingenuo    : identidad correcta  97.8 %
tracker predictivo : identidad correcta 100.0 %
```

El salto del 97.8 % al 100 % es exactamente el capítulo de metodología que
justifica el trabajo: el emparejamiento por vecino más cercano falla cuando dos
buses de la misma línea y sentido se cruzan, y extrapolar con velocidad
constante antes de asignar lo resuelve.
