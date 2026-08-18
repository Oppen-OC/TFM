# Idea 3 en València · Fuentes de datos en tiempo real verificadas

_Verificación realizada el 15/08/2026. Todo endpoint marcado como "no documentado" puede cambiar sin aviso: confírmalo tú mismo antes de comprometer el tema._

---

## Resumen ejecutivo

| Operador | ¿Tiempo real público? | Formato | Clave | Veredicto |
|---|---|---|---|---|
| **EMT València** (bus urbano) | **Sí** · posición GPS de vehículos | ArcGIS REST JSON | No | ✅ **Viable, es tu fuente principal** |
| **Metrovalencia / FGV** | **No** | — | — | ❌ Solo GTFS estático. No hay API de posición |
| **Cercanías Renfe** (núcleo València) | **Sí** · posición **+ retraso en minutos** | JSON | No | ✅ Viable, pero endpoint no documentado |
| **Valenbisi** | Sí · disponibilidad por estación | ArcGIS REST JSON | No | ⚠️ Refresca cada 10 min, no vale para 30 s |
| **Estado del tráfico municipal** | Sí · congestión por tramo viario | ArcGIS REST JSON | No | ✅ **Tu variable explicativa estrella** |

**Aviso de contexto:** el portal `valencia.opendatasoft.com` que aparece en casi todos los tutoriales y proyectos de GitHub **ya no existe**. El portal vigente del Ajuntament es `https://opendata.vlci.valencia.es/` (CKAN). Si sigues una guía antigua, fallarás.

---

## 1. EMT València · posición de vehículos en tiempo real ✅

**Endpoint** (sin autenticación):

```
https://geoportal.valencia.es/server/rest/services/EMT/Seguimiento_EMT/MapServer/384/query
    ?where=1=1&outFields=*&f=json
```

El servicio se autodescribe como *"Servicio para el seguimiento en tiempo real de los coches de la EMT"*.

- **Formato:** ArcGIS REST Feature Service. Devuelve JSON, GeoJSON o PBF (protobuf de ArcGIS, **no** GTFS-Realtime).
- **Campos:** geometría `x`/`y` en **EPSG:25830** (UTM 30N, hay que reproyectar a WGS84), `linea`, `trayecto` (sentido), `fecha` (epoch en ms de la última actualización).
- **Lo que NO trae:** identificador estable de vehículo, `trip_id`, ocupación ni ETA a parada.
- **Límite:** `maxRecordCount = 2000` por consulta. Con ~250 buses en circulación no lo tocas; si lo tocas, pagina con `resultOffset`.
- **Licencia / términos:** no hay términos de uso publicados para este servicio. Es un ArcGIS Server municipal, no una API diseñada para tráfico intensivo. Sé conservador: 30 s está bien, 1 s te puede ganar un bloqueo por IP.

**Consecuencia de diseño importante:** al no haber `trip_id` ni retraso, **la etiqueta te la tienes que fabricar tú**. Ese es exactamente el trabajo que convierte esto en un TFM y no en un ejercicio:

1. GTFS estático de EMT → geometrías de ruta (`shapes.txt`) y horarios teóricos (`stop_times.txt`).
2. Map-matching de cada posición sobre la traza de su línea/trayecto → distancia recorrida acumulada.
3. Reconstrucción de "viajes" agrupando posiciones consecutivas y asignándolas al `trip` teórico más plausible.
4. Interpolar el instante de paso por cada parada → **retraso = paso observado − paso teórico**.

Es más difícil que usar un feed GTFS-RT que ya te regala el `delay`, y es justo el motivo por el que este tema es defendible: nadie ha publicado ese dataset para València.

**GTFS estático de EMT** (necesario para lo anterior):
`https://opendata.vlci.valencia.es/dataset/google-transit-lines-stops-bus-schedules`
El ZIP se republica con nombre fechado (el visto el 13/08/2026 cubría del 24/07 al 30/08/2026: **~47 rutas, 1.160 paradas, 33.843 viajes**). Descárgalo **cada semana** y versiónalo con DVC: los horarios cambian y usar el GTFS equivocado te corrompe todas las etiquetas.

---

## 2. Metrovalencia / FGV · no hay tiempo real ❌

Malas noticias, y conviene que las sepas antes de escribir la propuesta:

- **Transitland** lista el operador `o-metro~valencia` con **una sola fuente, GTFS estático**. Sin GTFS-RT.
- El ArcGIS del Ajuntament solo tiene capas **estáticas** de FGV (estaciones id 221, bocas id 220). No existe un equivalente a `Seguimiento_EMT`.
- El portal de dades obertes de la GVA (`dadesobertes.gva.es`) solo publica geometría de red, sin horarios ni tiempo real.
- La app oficial muestra ocupación de trenes en tiempo real, pero es una función cerrada: no hay API pública que la exponga.
- Los repos de terceros están muertos o son frágiles: `seravifer/metrovalencia-api` está **archivado desde 2021**; el resto scrapean la web oficial sin contrato estable.

**GTFS estático de Metrovalencia** (lo único disponible): `http://www.metrovalencia.es/google_transit_feed/google_transit.zip` (feed `mdb-1054` en MobilityDatabase).

Si quieres metro en el trabajo, el único encaje honesto es usarlo como **red teórica de referencia** (accesibilidad multimodal, transbordos programados), dejando explícito en la memoria que no hay dato observado. No lo vendas como tiempo real.

---

## 3. Cercanías Renfe · posición **con retraso ya etiquetado** ✅

```
https://tiempo-real.renfe.com/renfe-visor/flota.json
```

Es el backend del visor oficial `tiempo-real.renfe.com`. Devuelve la flota **nacional**; filtra por `nucleo == "40"` para València.

- **Campos de oro:** `retrasoMin` (¡la etiqueta ya hecha!), `codLinea` (C1, C2, C5...), `codEstAct` / `codEstSig`, `horaLlegadaSigEst` (ETA a la próxima estación), `latitud`, `longitud`, `tripId`, `via`.
- **Frecuencia:** el propio front-end lo pide cada ~3 s. Un polling de 30 s es más conservador que el cliente oficial.
- **Sin clave ni registro.**
- ⚠️ **Riesgo:** es un endpoint **no documentado**. Está en dominio oficial de Renfe, pero no figura en `data.renfe.com` ni tiene contrato de API. Puede cambiar de esquema o desaparecer. Documéntalo como riesgo en la memoria y guarda el JSON crudo tal cual llega, para poder reprocesar si cambia el formato.

**GTFS estático de Cercanías:** `https://data.renfe.com/` (dataset "Horarios cercanías", portal CKAN oficial con API documentada).

---

## 4. Estado del tráfico en tiempo real · tu ventaja competitiva ✅

```
https://geoportal.valencia.es/server/rest/services/OPENDATA/Trafico/MapServer/192/query
    ?where=1=1&outFields=*&f=json
```

Polilíneas de tramos viarios con estado codificado (fluido / denso / congestionado / cortado). Tiene un campo `fiwareid`, señal de que se alimenta de la plataforma FIWARE de ciudad inteligente del Ajuntament.

**Esto es lo que le da originalidad a tu TFM.** Con el feed de 511.org que te propuse originalmente harías lo mismo que veinte trabajos publicados. Fusionando **posición GPS del bus + estado de congestión del tramo por el que circula en ese instante** respondes a una pregunta que no está resuelta: ¿cuánto del retraso de la EMT se explica por congestión medida, y con cuánta antelación se puede anticipar? Ahí tienes tu aportación.

Otras capas del mismo ArcGIS, todas sin clave:

| Capa | id | Contenido |
|---|---|---|
| Paradas EMT | 226 | estático |
| Estado tráfico tiempo real | 192 | **tiempo real** |
| Cámaras de tráfico | 190 | ubicaciones |
| Estaciones FGV | 221 | estático |
| Paradas MetroBus | 248 | estático |
| Valenbisi disponibilidad | 228 | cada 10 min |

Directorio completo de servicios: `https://geoportal.valencia.es/server/rest/services`

---

## 5. Valenbisi · útil, pero ojo con la cadencia ⚠️

```
https://geoportal.valencia.es/server/rest/services/OPENDATA/Trafico/MapServer/228/query
    ?where=1=1&outFields=*&f=json
```

Campos: `Direccion`, `Numero`, `Activo`, `Bicis_disponibles`, `Espacios_libres`, `Espacios_totales`, `fecha_actualizacion`. ~275 estaciones.

**La ficha oficial dice literalmente que se actualiza cada 10 minutos.** Pollear cada 30 s no te da más información, solo duplicados. Si lo incluyes, hazlo a 5 min y como fuente de demanda de movilidad complementaria, no como serie de alta frecuencia. Sin GBFS estándar publicado.

Ficha CKAN: `https://opendata.vlci.valencia.es/dataset/valenbisi-disponibilitat-valenbisi-dsiponibilidad`

---

## Propuesta de TFM revisada para València

> **Título:** *Fusión de posiciones GPS de flota y estado de tráfico urbano en tiempo real para la predicción de retrasos del transporte público: el caso de la EMT de València.*

**Volumen que vas a generar** (la carta que juegas ante el tribunal de Big Data):

- EMT: ~250 vehículos × 2.880 muestras/día ≈ **720.000 filas/día**
- Tráfico: ~1.500 tramos × 2.880 ≈ **4,3 M filas/día**
- Renfe núcleo 40: ~40 trenes × 2.880 ≈ 115.000 filas/día

En 3 meses: **~450 millones de filas crudas**. En CSV es inmanejable en un portátil; en **Parquet particionado por día + DuckDB/Polars** se procesa sin cluster. Esa demostración es, por sí sola, la competencia de Big Data que el repo actual no acredita.

**Arquitectura sobre tu esqueleto:**

```
colectores (asyncio, 30 s)  ──>  Redpanda/Kafka  ──>  consumidor
                                                          │
                                             data/raw/  (Parquet, part. por fecha)
                                                          │
                                   ETL: reproyección · map-matching · viajes ·
                                        etiquetado de retraso · join espacial con tráfico
                                                          │
                                            DVC: features → train → evaluate
                                                          │
                                           XGBoost  ──>  FastAPI  ──>  Streamlit
```

- El join espacial bus ↔ tramo de tráfico se hace con GeoPandas / DuckDB Spatial.
- Guarda **siempre el JSON crudo** además del Parquet limpio. Si te equivocas en el parseo tres semanas después, no puedes recapturar el pasado.
- **Objetivo XGBoost:** regresión sobre segundos de retraso en la siguiente parada, y clasificación binaria (`retraso > 5 min`) que encaja tal cual con tu `schemas.py` actual.
- Baselines obligatorios: horario teórico puro (retraso = 0) y persistencia (el retraso actual del vehículo). Si no bates a la persistencia, no tienes trabajo.

---

## Checklist antes de cerrar el tema (esta semana)

1. [ ] Abrir en el navegador el endpoint de `Seguimiento_EMT` y confirmar que devuelve buses con `fecha` del minuto actual.
2. [ ] Idem con `flota.json` de Renfe: verificar que existen registros con `nucleo == "40"`.
3. [ ] Descargar el GTFS de EMT y comprobar que trae `shapes.txt` (sin geometrías de ruta, el map-matching se complica mucho).
4. [ ] Dejar corriendo un colector mínimo **24 h** y medir: filas/día reales, tamaño en disco, huecos de servicio nocturno, y si el servidor responde estable a 30 s.
5. [ ] Escribir al Ajuntament / EMT preguntando por condiciones de uso y si existe un GTFS-RT no publicitado. Aunque no contesten, el email documentado en el anexo de la memoria te cubre la parte ética y legal, y eso el tribunal lo valora.
6. [ ] Solo entonces, cerrar el tema con tu tutor.

**El punto 4 es innegociable.** Todo el TFM depende de que la captura aguante meses. Descubrirlo en octubre es recuperable; descubrirlo en enero, no.

---

## Fuentes

- [Portal de datos abiertos del Ajuntament de València (CKAN)](https://opendata.vlci.valencia.es/)
- [GTFS EMT · Google Transit, líneas, paradas y horarios](https://opendata.vlci.valencia.es/dataset/google-transit-lines-stops-bus-schedules)
- [Valenbisi disponibilidad](https://opendata.vlci.valencia.es/dataset/valenbisi-disponibilitat-valenbisi-dsiponibilidad)
- [Directorio de servicios ArcGIS del geoportal municipal](https://geoportal.valencia.es/server/rest/services)
- [Transitland · operador EMT Valencia](https://www.transit.land/operators/o-ezp8-emtvalencia)
- [Transitland · operador Metro Valencia](https://www.transit.land/operators/o-metro~valencia)
- [MobilityDatabase · MetroValencia GTFS (mdb-1054)](https://mobilitydatabase.org/feeds/gtfs/mdb-1054)
- [NAP · ficha GTFS EMT València](https://nap.transportes.gob.es/Files/Detail/965)
- [NAP · ficha GTFS Metro de València](https://nap.transportes.gob.es/Files/Detail/967)
- [Renfe Data · portal de datos abiertos](https://data.renfe.com/)
- [Visor de tiempo real de Renfe](https://tiempo-real.renfe.com/)
- [Dades Obertes de la Generalitat Valenciana](https://dadesobertes.gva.es/)
