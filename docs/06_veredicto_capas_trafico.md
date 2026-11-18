# 06 · Veredicto sobre las capas de tráfico

**Ventana analizada:** 15/08/2026 22:14 → 18/08/2026 02:05 hora local (~42 h),
incluyendo **el lunes 17 completo**, día laborable con sus dos horas punta.

**Volumen:** 632.329 posiciones de autobús · 1.017.228 lecturas de estado de
tráfico (2.033 sondeos) · 193.256 de intensidad (294 sondeos) · 417,9 MB.

> **Reformulado el 13/11/2026.** El veredicto de abajo salía de 42 horas de
> agosto. Con el corpus entero se sostiene para la capa 188 y **no** para la 192,
> que en periodo lectivo declara congestión con perfil de hora punta (bitácora
> 031). Las mediciones de agosto se conservan tal cual; lo que cambió está en
> *Qué quedó del veredicto*, al final, y sustituye a la reformulación del TFM que
> este documento proponía.

---

## Veredicto: las dos capas de tráfico son estáticas

No es una cuestión de poca varianza. Es que **no varían**.

### Capa 192 · estado de congestión

| Métrica | Valor |
|---|---|
| Snapshots analizados (lunes) | 1.408 |
| Tramos | 410 |
| **Tramos que cambian de estado en todo el lunes** | **8 de 409** |
| Distribución: estado 0 | 98,05 % |
| estado 3 | 1,70 % (7 tramos fijos, corredor Pérez Galdós) |
| estado 1 | **39 filas de 580.096** (0,007 %) |
| estado 2 | **3 filas** |

El porcentaje de tramos no fluidos es **1,703 % a las 04:00 y 1,703 % a las
08:00 y 1,703 % a las 19:00**. Idéntico las 24 horas, salvo dos episodios:

- 15:21–15:41 · un tramo (Paso Inferior Menéndez Pidal) en estado 1
- 21:39–21:41 · tres tramos junto al Puente del Assut de l'Or

**24 minutos de congestión declarada en un día laborable entero, sobre 409
tramos.** Los 7 tramos permanentes en estado 3 son todos del mismo corredor en
obras. La capa se comporta como un **registro de incidencias y obras**, no como
una medición de tráfico.

### Capa 188 · intensidad medida (veh/h)

| Métrica | Valor |
|---|---|
| Snapshots en toda la captura (42 h) | 294 |
| Puntos de medida | 354 con lectura válida |
| **Puntos cuya lectura cambia alguna vez** | **3 de 355** |
| Puntos con un único valor en 42 h | 352 |
| **Snapshots en los que cambia el total agregado** | **1 de 294** |

La intensidad media es **1.079 veh/h a las 03:00 y 1.079 veh/h a las 08:00**.
El único cambio en toda la captura ocurrió el 17/08 a las 00:16 UTC.

Era el plan B. También está muerto.

---

## El control que convierte esto en un hallazgo

La objeción evidente es que agosto en València está vacío y sencillamente no
hubo congestión. **Los propios autobuses la refutan.**

Reconstruyendo la velocidad de la flota a partir de las posiciones GPS, el mismo
lunes:

| Hora local | Velocidad mediana |
|---|---|
| 22:00 | **12,2 km/h** (máximo) |
| 08:00 | 7,3 km/h |
| 14:00 | 6,7 km/h |
| **17:00** | **5,8 km/h** (mínimo en servicio) |
| 19:00 | 7,8 km/h |

**Los autobuses circulan un 52 % más lento a las 17:00 que a las 22:00.** Hay
congestión, es grande, sigue un perfil diario coherente y es perfectamente
medible. Lo que falla no es la ciudad: es la capa que dice medirla.

Ver `fig_trafico_vs_buses.html`: tres paneles, mismo día, mismo eje temporal.
Uno se mueve; los otros dos son líneas rectas.

---

## Qué quedó del veredicto

_Sección reescrita el 13/11/2026. Sustituye a «Consecuencia para el TFM»,
«Reformulación propuesta» y «Antes de cerrar el veredicto», que concluían sobre
tres días de agosto._

### Lo que este documento concluía en agosto

Que la hipótesis de fusión no se podía contrastar, porque la variable
explicativa no contenía información, y que el TFM debía invertir la pregunta:
usar los autobuses como red de sensores para medir el tráfico y contrastarlo con
el registro oficial. Dejaba dos comprobaciones pendientes antes de cerrarlo:
seguir capturando hasta el periodo lectivo y preguntar al Ajuntament por la
frecuencia de actualización de las capas.

La primera comprobación se hizo, y cambió la conclusión.

### Capa 192: se anima en periodo lectivo

Con la captura hasta el 18/09 (bitácora 031), por día laborable y contando solo
los estados 1 y 2:

| | Tramos que llegan a congestión | Horas-tramo de congestión |
|---|---|---|
| Antes del 08/09, mediana | 8,5 | 3,7 |
| Desde el 08/09 (lectivo), mediana | **34** | **42,3** |

Además tiene la forma del tráfico: en laborables lectivos hay 17,4 tramos
congestionados de media a las 8 h y 6,9 a las 18 h, frente a casi ninguno de
noche. El veredicto de «registro de incidencias y obras» describe bien el estado
3, que son sobre todo vías cortadas de forma permanente (bitácora 005), pero no
los estados 1 y 2.

### Capa 188: sigue congelada

Los 32 días medidos tienen exactamente los mismos 243 valores distintos en 354
puntos, con la misma media de 1.079 veh/h que en agosto (bitácora 031). Para
esta capa el veredicto se mantiene.

### La hipótesis sí se pudo contrastar

Con la 192 viva, la aportación del tráfico se decidió en una prueba con la
comparación primaria fijada de antemano (ADR-024), sobre los días de servicio
del 07 al 19/10. Resultado (bitácora 057):

- **En la primaria no aporta.** Con cinco paradas de horizonte y sensor en el
  recorrido, el modelo con la 192 mejora 0,13 s sobre 56 s de error, con un
  intervalo por días de [−0,30, +0,01] que contiene el cero. Las filas sin
  ningún sensor en el recorrido mejoran lo mismo, así que esa diferencia no se
  puede atribuir al tráfico.
- **Donde la capa veía congestión al predecir, el error baja un 5 %** (−4,85 s
  sobre 98 s). Son el 3,2 % de las filas.

La respuesta a la pregunta de investigación es, por tanto, un resultado medido y
no una imposibilidad: el estado del tráfico publicado aporta poco al conjunto y
algo donde declara congestión, que es raro.

### Qué se decidió

- **La pregunta de investigación no se invirtió.** El TFM sigue siendo de
  predicción de retrasos; el modelo sin tráfico bate al listón (−3,37 s con
  cinco paradas de horizonte, bitácora 057).
- **La flota como sensor entró como variables del modelo**, no como tema: mide
  sobre todo el sesgo del horario (bitácora 032).
- **La auditoría de datos abiertos queda como hallazgo de calidad del dato**:
  una capa de intensidad congelada y una de estado que solo informa en hora
  punta lectiva.

### Lo que sigue pendiente

- **El correo al Ajuntament** sobre la frecuencia de actualización de las capas
  188 y 192. La respuesta, o su ausencia, va al anexo.
- **La cadencia de la 192** sigue en 5 min, fijada cuando la capa parecía
  estática; nadie ha vuelto a medir si basta (pendiente en `07_decisiones.md`).
