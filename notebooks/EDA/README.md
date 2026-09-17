# EDA de las fuentes

Un notebook por tabla de `data/curated/`, más uno transversal y uno de método.
Exploración, no pipeline: **nada de `src/project/` importa de aquí**, igual que con
`analysis/`.

| notebook | fuente | profundidad |
|----------|--------|-------------|
| [00_panorama_general.ipynb](00_panorama_general.ipynb) | las cinco a la vez | condición de viabilidad de la fusión |
| [01_emt_buses.ipynb](01_emt_buses.ipynb) | capa EMT 384 | profunda |
| [02_trafico_estado.ipynb](02_trafico_estado.ipynb) | capa Tráfico 192 | profunda |
| [03_trafico_intensidad.ipynb](03_trafico_intensidad.ipynb) | capa Tráfico 188 | media |
| [04_valenbisi.ipynb](04_valenbisi.ipynb) | capa Valenbisi 228 | estándar |
| [05_renfe_cercanias.ipynb](05_renfe_cercanias.ipynb) | `flota.json`, núcleo 40 | estándar |
| [06_cascada_etiqueta_retraso.ipynb](06_cascada_etiqueta_retraso.ipynb) | GTFS estático × `emt_buses` | método, no fuente |

La profundidad es proporcional al peso en la pregunta de investigación: `emt_buses`
y `trafico_estado` son la hipótesis del TFM; las otras tres son contexto.

## Cómo se corren

```bash
uv run jupyter lab            # o abrirlos desde VS Code
```

Para reejecutar uno **desde la línea de órdenes en Windows**, hace falta el modo
UTF-8 de Python:

```bash
PYTHONUTF8=1 uv run jupyter execute --inplace notebooks/EDA/06_cascada_etiqueta_retraso.ipynb
```

Sin `PYTHONUTF8=1`, `jupyter execute --inplace` lee el `.ipynb` con la página de
códigos de la consola (cp1252) y lo reescribe en UTF-8: cada acento se convierte en
dos caracteres basura —`Ibáñez` pasa a `IbÃ¡Ã±ez`— en el fichero guardado, no solo
en pantalla. Se comprueba con `grep -c 'Ã' notebooks/EDA/*.ipynb`, que debe dar
cero. Ejecutándolos desde Jupyter Lab o VS Code no pasa.

Los notebooks se commitean **con las salidas dentro**, para que se lean sin
arrancar kernel. Corren tanto desde `notebooks/EDA/` como desde la raíz del repo.

Reejecutarlos entero cuesta menos de un minuto y medio: el trabajo pesado lo hace
DuckDB en SQL y solo el resultado agregado pasa a pandas. `emt_buses` son 5,1 M de
filas y ninguna llega entera a memoria.

## `eda_utils.py`

Censo, perfil de nulos, resumen numérico con moda, cadencia, huecos, heatmaps y
lectura de la geometría estática. Vive aquí y no en `src/project/` a propósito.

Dos detalles suyos que no son cosméticos:

- la conexión de DuckDB fija `TimeZone='UTC'`. En Madrid, dejar la zona del
  sistema desplaza dos horas en verano;
- todas las lecturas usan `union_by_name=1`. Los ficheros de una misma fuente no
  tienen las mismas columnas —las capas de tráfico solo traen geometría en los
  reprocesados— y sin esa opción DuckDB aborta el glob entero.

## Qué salió de aquí

Lo que estos notebooks midieron y que no estaba escrito en ningún sitio:

- la fusión buses × tráfico es **viable**: mediana de ~2 min de desfase, casi todo
  por debajo de 5;
- pero las capas de tráfico **no publican timestamp propio**, así que ese desfase
  es un suelo y no el error real de alineación;
- **`estado = 3` no es congestión, es cierre permanente** — casi absorbente, sin
  patrón horario, concentrado en vías de servicio. Es el hallazgo con más
  consecuencias para `features.py`;
- la capa 192 tiene 410 tramos pero **solo 63 llegan a estar congestionados** en
  dieciséis días;
- la capa 188 **no une por `idtramo`** con la 192 (intersección cero) pero **sí
  geográficamente**: la mitad de los tramos a menos de 50 m;
- en Valenbisi, `total` es capacidad instalada y no anclajes operativos: la
  ocupación se calcula con `available / (available + free)`;
- el `shape_dist_traveled` del GTFS **no es distancia, es el horario reescalado**
  ($R^2 = 1{,}00000$ contra los segundos programados): usarlo como eje habría hecho
  circular el cálculo del retraso sin lanzar un solo error;
- la geometría de `shapes.txt` **sí** es buena — las paradas caen a 3,4 m de mediana
  del trazado, y las posiciones reales a 1,8 m — así que la abscisa se recalcula
  proyectando;
- **una trayectoria no es un viaje**: el vehículo del ejemplo pasa 44 de sus 94
  minutos parado en cabecera;
- Renfe enseña **cómo se ve un retraso real**: 41 % de ceros, cola larga, y unos
  pocos valores imposibles por el cruce de medianoche — el mismo artefacto que
  producirá la etiqueta del TFM si no se cuida.

Cada notebook cierra con su lista de hallazgos numerados. Lo que de ahí merezca
quedar fichado va a `docs/bitacora/`, `docs/07_decisiones.md` o
`.claude/trampas/` según la tabla de encaminamiento de `docs/bitacora/README.md`.
