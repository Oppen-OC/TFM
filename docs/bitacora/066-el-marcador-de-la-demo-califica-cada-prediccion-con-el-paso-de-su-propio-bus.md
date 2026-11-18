---
id: 066
titulo: El marcador de la demo en vivo califica cada predicción con el paso de su propio bus, 0 de 109 mal calificadas en tres ventanas del 01/10 aunque cada ciclo reetiqueta el día; las que van a la última parada de su viaje no se verifican nunca
fecha: 2026-11-17
tipo: medicion
capa: serving
capitulo: metodologia
impacto: bajo
estado: aceptado
evidencia: uv run python -m project.analysis.medir_marcador_vivo --dia 2026-10-01 --stop 773 --desde 17:00 --hasta 20:00 (y --stop 773 --desde 07:00 --hasta 10:30; y --stop 2277 --desde 07:00 --hasta 10:30)
trampa: 014
---

## Qué se observó

El `Marcador` de `services/vivo.py` congela la primera predicción de cada viaje
con la clave `(fecha_servicio, viaje_id)` y la verifica con el paso de esa clave
por la parada. Cada ciclo reetiqueta el día desde el principio, y `rastrear` puede
cambiar el `viaje_id` (suavizado de intercambios, cosido de la alternancia,
trampa 014). La asignación del viaje programado también puede cambiar. Si la
clave derivase, la predicción se quedaría sin verificar o se calificaría con el
paso de otro bus, sin ningún error. Era el aviso Importante 1 del pre-merge de
`feat/demo-en-vivo` (puerta 015).

Reproduciendo la demo ciclo a ciclo cada 2 min sobre el 01/10:

| parada, ventana local | ciclos | congeladas | evaluables | bien calificadas | cambia `viaje_id` / `trip_id` |
|---|---|---|---|---|---|
| 2277, 07:00-10:30 | 106 | 37 | 18 | 18 | 0 / 0 |
| 773, 07:00-10:30 | 106 | 53 | 48 | 48 | 0 / 0 |
| 773, 17:00-20:00 | 91 | 44 | 43 | 43 | 0 / 0 |
| **total** | 303 | 134 | **109** | **109** | **0 / 0** |

- **Ninguna huérfana, ninguna cruzada y ninguna con otro retraso.** Con 0 de 109,
  la cota superior del 95 % para la tasa de mal calificadas es del **2,7 %**
  (regla del tres).
- Las 25 no evaluables:
  - 19 no llegan a la parada en el día completo: 16 de la 72 en la 2277, más una
    de la 16, una de la 26 y una de la 94 en la 773.
  - 6 tienen su verdad después del final de la ventana.
- **Las 3 de la 773 se miraron a mano**, porque un viaje partido después del
  ancla, con la continuación bajo otro `viaje_id`, saldría como «no llega» y
  escondería una huérfana. No lo es ninguna:
  - La 26 y la 16 terminan antes de la parada (secuencia 22 de 29 y 18 de 21) y
    su `vehicle_id` no vuelve a aparecer. El paso siguiente de la línea por la 773
    es de otro bus, que en ese momento iba varias paradas por detrás o por delante.
  - La 94 pasa por la parada (secuencia 11), pero su viaje no tiene pasos en la
    11 ni en la 12: es un hueco del etiquetado, no del marcador.
  - En la demo, las tres quedan en «⏳», como las de la 72.
- **La 72 no se verifica nunca en la 2277.** La 2277 es la última parada de 66 de
  sus 131 viajes del día. En todo el día, con el día completo, el etiquetado
  marca solo **2** pasos por la última parada de un viaje de la 72. Las
  predicciones hacia la parada final se congelan y en la demo quedan en «⏳»
  indefinidamente.
- **La 2281 no congela ninguna** en 07:00-10:30. Es la parada 2-7 de casi todas
  sus rutas: el retraso de un paso se sabe unos 81 s después (bitácora 046), y
  ningún bus que va hacia ella tiene aún un paso sabido entre 1 y 10 paradas por
  delante. Se descartó como muestra; por eso se eligió la 773, que queda a mitad
  de ruta en sus 9 líneas.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_marcador_vivo --dia 2026-10-01 --stop 2277 --desde 07:00 --hasta 10:30
uv run python -m project.analysis.medir_marcador_vivo --dia 2026-10-01 --stop 773 --desde 07:00 --hasta 10:30
uv run python -m project.analysis.medir_marcador_vivo --dia 2026-10-01 --stop 773 --desde 17:00 --hasta 20:00
```

- Es un `Vivo` de verdad, con su `Marcador`, llamado con un «ahora» histórico
  cada `--cada-min`. Se envuelve `_etiquetar` para quedarse con los pasos de cada
  ciclo.
- Va **sin historial**. Cambian las variables del modelo, pero no la identidad,
  que no lo lee, y el ciclo cuesta un tercio.
- **La identidad física no es la clave.** Es el último paso sabido al congelar
  (línea, `stop_sequence`, `t_obs_utc`). Un paso sabido no cambia
  (`provisionales`), así que el día completo lo vuelve a tener con el mismo
  `t_obs`, se llame como se llame su viaje.
- La verdad es el primer paso de ese viaje por la parada en el día completo. Se
  compara con el paso que usó el marcador en el ciclo en que verificó: otro
  `t_obs` es una cruzada, y otro retraso con el mismo `t_obs` es otro viaje
  programado.
- Solo cuentan las predicciones cuya verdad se sabía dos ciclos antes del último
  corte.

**El instrumento se probó antes que lo medido.**
`tests/test_medir_marcador.py` construye un caso para cada clase: correcta,
huérfana, cruzada, otro retraso, ancla perdida, fuera de ventana y no llega.
También construye un bus renombrado al final del día con otro `trip_id`. Un
medidor que diera «correcta» a todo no pasaría. El medidor repite la casación de
`Marcador.verificar` para saber con qué paso calificó. Un test comprueba que
coinciden en la ruta circular y en el paso sin etiquetar, con el mutante 240, para
que un cambio en el marcador no deje al medidor midiendo otra cosa.

La cifra de la 72 sale de etiquetar el día completo de la 2277 con las líneas
de la parada y cruzar cada `trip_id` con la última parada de su patrón en el
horario `19-09-2026`. Script de una vez, no versionado.

## Por qué importa

- La demo califica el acierto de cada predicción en pantalla. Una clave que
  derivase la calificaría con el paso de otro bus, y la tasa de acierto mostrada
  sería falsa sin ningún error. En la muestra no deriva. El aviso Importante 1
  del pre-merge baja a Menor y no se cambia la clave.
- La muestra es de un solo día, dos paradas y 109 casos. No descarta un suceso
  de menos del 2,7 %, que en la demo sería una predicción mal calificada cada
  bastantes horas en una parada concurrida.
- Las predicciones hacia la última parada no son un fallo silencioso: se ven
  como pendientes para siempre. Pero ensucian el resumen del marcador, que las
  cuenta como no verificadas.

## Qué se hizo / qué queda abierto

- Hecho: el medidor (`src/project/analysis/medir_marcador_vivo.py`) y su test.
- No se toca la clave del marcador. El arreglo pensado, verificar contra el
  ancla física, queda para el día en que una medición lo pida.
- Abierto: no congelar, o no contar, las predicciones cuyo objetivo es la última
  parada del viaje. Es visible en la pantalla y no falsea nada: va a GitHub
  Issues, no a una trampa.
- Abierto: repetir en otro día, sobre todo uno con la 25 o la 99, las de más
  alternancia del trayecto (bitácoras 026 y 029). Esas líneas no paran en la 773
  ni en la 2277, así que el cosido de la trampa 014 apenas se ha ejercitado en
  esta muestra.

## Para la memoria

> La demostración en vivo congela la primera predicción de cada viaje y la
> califica cuando se conoce el retraso real en la parada. Como el seguimiento de
> vehículos se recalcula en cada ciclo sobre todo el día, el identificador de un
> viaje podría cambiar entre el ciclo en que se predijo y aquel en que se
> verifica, y la predicción se calificaría entonces con el paso de otro autobús.
> Para comprobarlo se reprodujo la demostración ciclo a ciclo sobre un día
> capturado, en dos paradas de mitad de recorrido y en horas punta de mañana y de
> tarde, identificando cada viaje por su último paso conocido y no por su
> identificador. Las 109 predicciones evaluables se calificaron con el paso de su
> propio autobús, y ninguna cambió de identificador ni de viaje programado; la
> cota superior del 95 % para la tasa de error es del 2,7 %. Las predicciones
> cuyo destino es la última parada del viaje no llegan a verificarse, porque el
> etiquetado casi nunca registra el paso por la parada final: en la línea 72,
> solo dos de 131 viajes en un día.
