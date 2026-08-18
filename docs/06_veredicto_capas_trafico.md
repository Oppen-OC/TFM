# 06 · Veredicto sobre las capas de tráfico

**Ventana analizada:** 15/08/2026 22:14 → 18/08/2026 02:05 hora local (~42 h),
incluyendo **el lunes 17 completo**, día laborable con sus dos horas punta.

**Volumen:** 632.329 posiciones de autobús · 1.017.228 lecturas de estado de
tráfico (2.033 sondeos) · 193.256 de intensidad (294 sondeos) · 417,9 MB.

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

## Consecuencia para el TFM

**La hipótesis de fusión, tal como estaba formulada, no se puede contrastar.**
No porque el tráfico no explique el retraso, sino porque la variable explicativa
que el Ayuntamiento publica no contiene información.

Lo que **no** se pierde:

- El corpus de posiciones de la EMT es real, denso y de calidad (latencia
  mediana 23 s, refresco 29,3 s, 632.329 posiciones en 42 h).
- Todo el ETL de reconstrucción de identidad, trayectorias y etiquetado sigue en
  pie, y era la aportación metodológica principal.
- Renfe Cercanías sigue vivo y con retraso oficial etiquetado.

---

## Reformulación propuesta

> **Los autobuses como red de sensores móviles: estimación del estado del tráfico
> urbano a partir de la flota de la EMT de València y contraste con el registro
> oficial del Ayuntamiento.**

Se invierte la dirección de la pregunta original. En vez de usar el tráfico para
predecir el autobús, se usa el autobús para **medir** el tráfico. Es una técnica
reconocida (*vehicles as probes*), y aquí tiene un gancho que no es habitual: se
puede contrastar contra un registro oficial y demostrar, con 42 horas de
evidencia, que ese registro no capta lo que dice captar.

Aportaciones que quedan, y son tres:

1. **Recurso.** El corpus de trayectorias de la EMT etiquetado, que no existe y
   no se puede reconstruir hacia atrás.
2. **Método.** Reconstrucción de identidad de vehículo y etiquetado de retraso
   desde una fuente sin `trip_id`, validable contra Renfe.
3. **Auditoría de datos abiertos.** Cuantificación de la brecha entre lo
   publicado y lo mantenido en una plataforma municipal FIWARE. Con la
   alternancia de zona horaria del apartado anterior, son dos fallos
   documentados y medidos en el mismo servicio.

La tercera es la más citable. "Publicado" y "mantenido" no son lo mismo, y
demostrarlo con datos propios es un resultado, no una excusa.

---

## Antes de cerrar el veredicto

Con 42 horas en agosto no se puede afirmar que las capas estén *siempre*
congeladas. Dos comprobaciones baratas, por rigor:

1. **Seguir capturando hasta septiembre**, con el curso escolar empezado. Si en
   octubre siguen planas, el hallazgo es firme.
2. **Escribir al Ajuntament** preguntando por la frecuencia de actualización de
   las capas 188 y 192. La respuesta, o su ausencia, va al anexo.

Y una tercera, no negociable: **el colector lleva 14 horas parado** (último
latido 18/08 03:35). Reinícialo antes que nada.
