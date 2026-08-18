# Informe de viabilidad · Fuentes en tiempo real de València

**Exploración en vivo realizada el sábado 15/08/2026 entre 21:05 y 21:20 CEST.**
Todo lo que sigue está medido, no estimado. Las cifras de flota corresponden a
un sábado por la noche: en hora punta de un día laborable serán bastante mayores.

---

## Veredicto

| Fuente | Estado | Cadencia real | Filas/sondeo | ¿Sirve? |
|---|---|---|---|---|
| EMT · posición de buses | ✅ viva | refresco **29,3 s** | 168-169 | **Sí, fuente principal** |
| Tráfico · estado por tramo | ✅ viva | sin timestamp propio | 446 | **Sí, variable explicativa** |
| Tráfico · intensidad medida | ✅ viva | sin timestamp propio | 394 | Sí, complementaria |
| Renfe Cercanías · núcleo 40 | ✅ viva | actualiza ~cada 12 s | 17 | Sí, con etiqueta gratis |
| Valenbisi | ✅ viva | ~10 min | 273 | Marginal |
| Metrovalencia / FGV | ❌ no existe | — | — | No |

**Las dos ideas son viables.** La de EMT + tráfico tiene más recorrido como TFM;
la de Renfe es el plan B de bajo riesgo. Detalle abajo.

---

## 1. EMT · posición de la flota

```
GET https://geoportal.valencia.es/server/rest/services/EMT/Seguimiento_EMT
        /MapServer/384/query?where=1=1&outFields=*&outSR=4326&f=json
```

La capa se llama literalmente **"Buses EMT"**. Sin autenticación,
`maxRecordCount = 2000`, capacidades `Query,Map,Data`. El parámetro `outSR=4326`
te devuelve WGS84 directamente y te ahorra la reproyección desde EPSG:25830.

### Esquema completo

| Campo | Tipo | Contenido |
|---|---|---|
| `gid` | OID | **No es un id de vehículo.** Ver más abajo. |
| `linea` | String(30) | `"70"`, `"C3"`, `"93"`… |
| `trayecto` | String(50) | `"Alboraia - La Fontsanta"` (línea + sentido) |
| `the_geom` | Point | posición |
| `fecha` | Date | timestamp del dato, **desplazado 2 h** |

### Medidas tomadas

- **166-169 buses simultáneos** a las 21:15 de un sábado, **31 líneas activas**.
- **Refresco cada 29,3 s de media** (intervalos observados: 22, 33, 33 s).
- **Latencia del dato: p50 36 s, p90 44 s, máximo 80 s** una vez corregida la
  zona horaria. Es decir, sondear cada 30 s está bien calibrado: más rápido solo
  te trae duplicados, más lento pierdes refrescos.
- **Velocidades reconstruidas: p50 6,2 km/h, p90 29,6 km/h.** La mediana baja
  refleja buses parados en cabecera a esa hora.
- Líneas con más vehículos en ese momento: C3 (13), 93 (12), 19 (11), 92 (11).

### Los tres hallazgos que condicionan el diseño

**① `gid` no identifica al vehículo, identifica al refresco.**

Comparé dos sondeos separados 35 s:

```
sondeo t0 : gid ∈ [1 659 987 635 … 1 659 987 800]   166 filas
sondeo t1 : gid ∈ [1 659 987 801 … 1 659 987 967]   167 filas
intersección: 0
```

Bloques contiguos y disjuntos: la tabla se trunca y se reinserta entera en cada
refresco, con un autoincrement global. Confirmado además porque
`returnCountOnly` sobre toda la tabla devuelve **168**, y una consulta por
`gid < mínimo_del_primer_sondeo` devuelve **0 filas**.

Dos consecuencias, una mala y una buena:

- **No hay histórico recuperable.** Nada de backfill. Lo que no captures, se
  pierde para siempre. El colector tiene que arrancar ya.
- **`gid` sí sirve como `snapshot_id`** (el mínimo del bloque identifica el
  refresco), lo que te permite deduplicar limpiamente.

Probé también si la posición dentro del bloque era un identificador estable.
No lo es: emparejando por rango, la línea y el trayecto solo coinciden en el
**32-73 %** de los casos y aparecen saltos de hasta 5 km entre sondeos.
Descartado.

**② El campo `fecha` va dos horas adelantado.**

```
fecha máx. observada, leída como UTC : 2026-08-15T21:08:52Z
hora de pared en ese instante        : 21:08:58 CEST
```

El timestamp es epoch-ms, pero construido a partir de la **hora local de Madrid
tratada como si fuera UTC**. En agosto el desfase es de 2 h; en invierno será de
1 h. Si no lo corriges con la zona horaria real de cada fecha, la serie se te
parte en el cambio de hora del último domingo de octubre y las etiquetas de
retraso de ese día quedan corruptas sin que salte ninguna alarma.

Esto, en la memoria, es un párrafo excelente. Es la clase de detalle que
demuestra que has tocado los datos de verdad.

**③ No hay `trip_id`, ni matrícula, ni ocupación.** Solo línea, sentido y
posición. La etiqueta de retraso hay que construirla entera.

---

## 2. Tráfico municipal · la pieza que te da la originalidad

El `MapServer` de tráfico tiene **54 capas**. Las que importan:

| id | Capa | Filas | Contenido |
|---|---|---|---|
| **192** | Estado tráfico tiempo real | 446 | `estado` (int), `idtramo`, `denominacion`, `fiwareid` |
| **188** | Intensidad tráfico tramos | 394 | `lectura` (veh/h), `des_tramo`, `tipo_vehiculo` |
| 208 | Espiras electromagnéticas | — | `ih` (intensidad horaria), `idpm`, `fecha_actualizacion` |
| 226 | Paradas EMT | — | estático |
| 4, 252, 253, 254 | **Predicción ocupación aparcamiento a 1/6/12/24 h** | — | ojo: el Ayuntamiento ya publica modelos |

**Medido en la capa 192 a las 21:15 de un sábado:** 404 tramos en estado 0
(fluido), 7 en estado 3, y **35 en nulo**. Ese 8 % de nulos es un problema real
de calidad del dato que tendrás que tratar, y conviene que lo digas.

**Medido en la capa 188:** 358 de 394 tramos con lectura válida, mediana
**555 veh/h**, máximo 6.012. Los 36 restantes traen `lectura = -1`, que es el
código de "sin dato" (no un cero: si lo tratas como cero, metes un sesgo).

Ninguna de las dos capas publica timestamp propio, así que **el sello temporal
lo pones tú en la ingesta**. Consecuencia importante para el modelo: la latencia
real de esta fuente es desconocida, y eso hay que declararlo como limitación.

Detalle que vale la pena mirar: las capas 4/252/253/254 son predicciones de
ocupación de aparcamiento publicadas por el propio Ayuntamiento. No compiten
con tu trabajo, pero son un precedente citable de que la plataforma FIWARE
municipal ya sirve modelos, lo que refuerza el argumento de aplicabilidad.

---

## 3. Renfe Cercanías · núcleo 40

```
GET https://tiempo-real.renfe.com/renfe-visor/flota.json
```

**Corrección respecto a lo que te dije ayer:** la raíz **no es un array**, es un
objeto `{fechaActualizacion, trenes: [...]}`. El código que espere una lista
falla en la primera línea.

### Medido

- `fechaActualizacion`: `2026-08-15T21:11:56` frente a hora de pared 21:12:08 →
  **12 segundos de latencia**. (También es hora local naive: mismo problema de
  zona horaria que la EMT.)
- **147 trenes en toda España**, de los cuales **17 en el núcleo 40 (València)**,
  repartidos en C1 (3), C2 (6), C3 (3), C6 (5).
- **Retrasos en ese instante: mediana 0 min, p90 7 min, máximo 9 min.**
  6 de 17 trenes con retraso > 0.

### Campos

`tripId`, `codTren`, `codLinea`, **`retrasoMin`**, `codEstAct`, `codEstSig`,
`horaLlegadaSigEst`, `codEstOrig`, `codEstDest`, `porAvanc`, `latitud`,
`longitud`, `nucleo`, `accesible`, `via`, `nextVia`.

Dos matices que no estaban documentados en ningún sitio:

- **`tripId` es estable dentro del viaje.** Aquí sí tienes identidad de vehículo
  gratis, al contrario que en la EMT.
- **`porAvanc` no es un flag binario.** Toma valores `"A"`, `"E"`, `null` y
  también numéricos como `"67.0"`, `"25.0"`, `"99.0"`: parece el porcentaje de
  avance entre estaciones. Habrá que caracterizarlo con datos de varios días.

**Ventaja decisiva:** `retrasoMin` **ya viene calculado**. No tienes que hacer
map-matching ni reconstruir horarios. Es la etiqueta servida en bandeja.

**Riesgo:** endpoint no documentado, sin contrato público. Puede cambiar o
desaparecer. Por eso el colector guarda siempre el payload crudo.

---

## 4. Valenbisi

273 estaciones, campos `available`, `free`, `total`, `open`, `updated_at` y
`update_jcd`. Confirmado que el `updated_at` es idéntico para todas las
estaciones en un mismo sondeo (`"15/08/2026 21:10:55"`), mientras que
`update_jcd` sí varía por estación: es el timestamp real del operador.

Refresca cada ~10 minutos. Sondearlo a 30 s solo genera duplicados. Inclúyelo a
5 minutos como señal de demanda de movilidad, o déjalo fuera.

---

## 5. Metrovalencia · confirmado que no hay nada

Ya lo verificamos ayer y no ha cambiado: listando todas las carpetas del ArcGIS
Server municipal solo existe la carpeta `EMT`; no hay `FGV` ni `Metro`. Las
únicas capas de FGV (estaciones, bocas) son estáticas. Transitland lista el
operador con una sola fuente, GTFS estático.

Si quieres metro en el trabajo, entra como red teórica para análisis de
transbordo, nunca como dato observado.

---

## 6. Volumen proyectado

Con las cadencias recomendadas, y contando que en día laborable la flota de la
EMT será claramente mayor que los 168 buses de un sábado noche:

| Fuente | Cadencia | Filas/día | 3 meses |
|---|---|---|---|
| EMT buses | 30 s | ~480.000 (noche) a ~900.000 (laborable) | **~65 M** |
| Tráfico estado | 60 s | ~642.000 | **~58 M** |
| Tráfico intensidad | 5 min | ~113.000 | ~10 M |
| Renfe núcleo 40 | 30 s | ~49.000 | ~4,4 M |
| Valenbisi | 5 min | ~79.000 | ~7 M |
| | | | **~145 M filas** |

En Parquet con compresión zstd son unos pocos GB, perfectamente manejables con
DuckDB en un portátil. En CSV, no. Ese contraste, medido y documentado, **es** la
competencia de Big Data que tu esqueleto actual no acredita.

---

## 7. Qué extraer de cada fuente

### De la EMT: reconstruir lo que la fuente no te da

Es el núcleo del ETL y el capítulo fuerte de la memoria.

1. **Identidad de vehículo.** No existe, hay que inferirla. Implementado en el
   demostrador con asignación húngara restringida a la misma (línea, trayecto)
   y con puerta de velocidad máxima. En el autotest sobre flota simulada con
   verdad-terreno conocida:

   ```
   vecino más cercano ingenuo  : 97,8 % de identidades correctas
   con predicción de movimiento: 100,0 %
   ```

   El fallo del método ingenuo es sistemático: se equivoca justo cuando dos
   buses de la misma línea y sentido se cruzan. Extrapolar la posición con la
   velocidad del paso anterior antes de asignar lo resuelve. Ese contraste
   medido es una sección entera de metodología.

2. **Segmentación en viajes.** Detectar cabeceras, principio y fin de servicio,
   y descartar los desplazamientos en vacío a cocheras.

3. **Progreso sobre la ruta.** Proyectar cada posición sobre `shapes.txt` del
   GTFS → distancia acumulada.

4. **Paso por parada y retraso.** Interpolar el instante de paso por cada parada
   y compararlo con `stop_times.txt`. **Aquí nace tu variable objetivo.**

5. **Regularidad de intervalo (*headway*).** En líneas de alta frecuencia, la
   métrica que importa no es el retraso sino la irregularidad y el
   encadenamiento de autobuses. Casi nadie lo modela.

### Del tráfico: la variable explicativa que nadie ha cruzado con esto

- Estado de congestión del tramo que el bus está pisando en ese instante.
- Estado de los tramos **aguas abajo** de su ruta, a 1, 3 y 5 minutos vista:
  esta es la feature con más potencial predictivo de todo el trabajo.
- Intensidad medida (veh/h) del corredor, y su desviación respecto al perfil
  típico de ese día y hora.
- Fracción de la ruta restante actualmente congestionada.

### De Renfe: etiquetas gratis y validación cruzada

- `retrasoMin` como serie por tren y línea, sin ETL de etiquetado.
- Propagación del retraso a lo largo del recorrido: cómo evoluciona entre
  estaciones consecutivas.
- Comparación bus vs tren ante el mismo evento (lluvia, festivo, corte de
  tráfico): ¿qué modo es más resiliente? Buena sección de discusión.

### Variables de contexto que debes añadir

Meteorología de AEMET (lluvia es el factor externo más obvio), calendario
laboral y festivos locales, eventos en Mestalla y en la Ciutat de les Arts,
y falla/mascletà en marzo (si capturas hasta entonces, tienes un experimento
natural regalado).

---

## 8. Comparación honesta de las dos ideas

|  | **EMT + tráfico** | **Renfe Cercanías** |
|---|---|---|
| Etiqueta | Hay que construirla (map-matching) | **Ya viene dada** |
| Dificultad del ETL | Alta, y esa es la gracia | Baja |
| Volumen | ~123 M filas/3 meses | ~4,4 M filas/3 meses |
| Identidad de vehículo | Hay que inferirla | `tripId` estable |
| Estabilidad de la fuente | Servicio municipal oficial | Endpoint no documentado |
| Originalidad | Alta: la fusión con tráfico no está hecha | Media |
| Riesgo de no terminar | Medio-alto | Bajo |

**Recomendación: haz las dos, pero con pesos distintos.** Captura ambas desde el
primer día, que cuesta lo mismo. Renfe es tu red de seguridad: si el
map-matching de la EMT se te atraganta en diciembre, tienes un dataset
etiquetado y un modelo entrenable en dos semanas. Y si la EMT sale bien, Renfe
se convierte en el capítulo de validación cruzada entre modos, que enriquece la
defensa en vez de sobrar.

---

## 9. Lo que tienes que hacer esta semana

1. Descomprime el demostrador y ejecuta `python explore.py`. Confirma que las
   cinco fuentes responden **desde tu red** (yo las he probado desde tu
   navegador, pero conviene que lo veas tú desde el script).
2. Ejecuta `python selftest.py`. Deben salir las 24 comprobaciones en verde.
3. Lanza `python collect.py --minutes 1440` y **déjalo 24 horas**. Con eso
   mides el ciclo diario completo: hora punta, valle, servicio nocturno, tamaño
   real en disco, tasa de errores y estabilidad del servidor municipal.
4. Con esos números, cierra el tema con tu tutor.
5. En paralelo, escribe al Ajuntament y a EMT preguntando por condiciones de
   uso. Aunque no contesten, el correo documentado en el anexo te cubre la parte
   ética y legal, y el tribunal lo valora.

El punto 3 es el único que no se puede saltar. Todo lo demás es reversible.

---

## Anexo · Lo que ya está resuelto en el código

- Corrección de zona horaria con `zoneinfo`, válida en el cambio de hora.
- Deduplicación por `snapshot_id`: sin ella te comes ~15 % de filas repetidas
  sondeando a 30 s una fuente que refresca a 29,3 s.
- Persistencia del payload crudo en NDJSON gzip **antes** de parsear, para poder
  reprocesar si Renfe cambia el esquema.
- `lectura = -1` convertido a nulo, no a cero.
- Parquet particionado por fuente y día, con compresión zstd.
- Tracker con asignación húngara y modelo de velocidad constante.
- 24 tests que corren sin red.
