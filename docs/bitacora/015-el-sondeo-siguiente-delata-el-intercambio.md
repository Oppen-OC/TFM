---
id: 015
titulo: Ajustar el coste de un paso no deshace los intercambios en paradas y giros, porque la información está en el sondeo siguiente; suavizar con un sondeo de retardo los reduce entre un 58 % y un 100 % sin fragmentar, pero no los elimina
fecha: 2026-09-17
tipo: tecnica
capa: tracking
capitulo: metodologia
impacto: alto
estado: mitigado
evidencia: uv run python auditoria/banco_tracker.py --reservadas --etiqueta suavizado_reservadas
trampa: 007
---

## Qué se observó

La entrada 013 mostró que, con paradas y giros al ritmo real, el tracker
intercambia identidades en encuentros entre buses del mismo grupo. Se buscó un
arreglo con un banco de medida fijo (`auditoria/banco_tracker.py`): 7
escenarios de `simular_flota` × 2 longitudes × semillas de AJUSTE (7, 11, 23,
42, 101), y 20 semillas RESERVADAS (9001-9020) que solo se miraron al final.

**Cambiar el coste de un paso no basta.** Saltos con las semillas de ajuste:

| candidato | paradas | giros | todos | estrés | hueco + paradas | sin fenómenos |
|---|---|---|---|---|---|---|
| base (`b1db54e`) | 20 | 20 | 10 | 52 | 20 | 0 |
| A · min(d_pred, d_real + 40) | 8 | 18 | 8 | 32 | 12 | 0 |
| E · A + hipótesis de giro | 8 | 8 | **16** | 42 | 4 | 0 |
| B · d_pred / (25 + 0,5·paso) | 26 | 22 | 20 | 72 | 18 | 0 |
| C · predicción ×0,75 | 14 | 22 | 0 | 46 | 6 | 0 |
| C · predicción ×0,5 | 18 | 22 | 8 | 44 | 14 | **14** |
| **D · suavizado con retardo** | **6** | **2** | **0** | **32** | **2** | **0** |

Clasificados, dos de cada tres intercambios de la base **se deshacen solos en
el sondeo siguiente**: el bus que para "va" hasta el que pasa y vuelve. La
información que falta en la matriz de coste de un paso está en el paso de
después.

**D** construye las trayectorias como siempre y luego, para cada par de
posiciones del mismo (sondeo, línea, trayecto) a menos de 400 m, prueba
intercambiar esas dos posiciones o las colas desde ahí, y acepta el cambio si
reduce en más de 10 m la suma de cambios de velocidad en ±2 sondeos, sin salir
de la puerta física. Ampliar la ventana a ±3 o ±4 no cambia ni un salto.

**Semillas reservadas, medidas una vez** (40 ejecuciones por escenario):

| escenario | base | D | |
|---|---|---|---|
| sin fenómenos | 16 | **0** | −100 % |
| paradas | 66 | 10 | −85 % |
| giros | 52 | 2 | −96 % |
| todos (calibrado) | 154 | **46** | −70 % |
| estrés | 176 | 74 | −58 % |
| hueco | 16 | 0 | −100 % |
| hueco + paradas | 78 | 14 | −82 % |

**Sobre datos reales, sin coste:**

| jornada | trayectorias | mediana (min) | fuera de la puerta | `ida_vuelta` |
|---|---|---|---|---|
| 17/08 · base → D | 7.654 → 7.654 | 26,98 → 26,90 | 0 → 0 | 291 → 269 |
| 23/08 · base → D | 6.001 → 6.001 | 23,22 → 23,13 | 0 → 0 | 201 → 185 |
| 27/08 · base → D | 7.658 → 7.658 | 20,82 → 20,84 | 0 → 0 | 254 → 232 |

El criterio de aceptación era 0 saltos en los escenarios calibrados. **No se
cumple.** De los 46 saltos que quedan en "todos" con semillas reservadas, 36
tienen velocidad previa y no están en el borde de la serie; 8 caen en los dos
primeros sondeos y 2 en el último. Los buses intercambiados están a 99 m de
mediana (p90 189 m).

Dos hallazgos más del banco:

- **La flota por defecto no era perfecta.** Con la base, sin paradas ni giros,
  hay saltos en 6 de las 40 ejecuciones reservadas (16 saltos). El "0 saltos"
  de los tests dependía de la semilla 7. Con D, 0 en las 40.
- **El indicador real `ida_vuelta` apenas ve intercambios.** Validado en
  simulación: 0 falsos positivos en 40 ejecuciones sin saltos, pero solo detecta
  5 de las 30 ejecuciones con saltos y ningún intercambio por giro. Se usa como
  cota inferior, no como criterio.

## Cómo se midió

```bash
uv run python auditoria/candidatos_coste.py                      # A, B, C, E
uv run python auditoria/banco_tracker.py --etiqueta suavizado    # D, ajuste
uv run python auditoria/banco_tracker.py --reservadas --etiqueta suavizado_reservadas
uv run python auditoria/banco_tracker.py --sin-sim --real 2026-08-17 2026-08-23 2026-08-27 --etiqueta suavizado_real
uv run python auditoria/banco_tracker.py --validar-indicador --etiqueta x
```

La base se midió cargando `src/project/tracking.py` de `b1db54e` con
`--tracker`. Resultados en `auditoria/resultados/banco_*.json`.

Comprobaciones del instrumento:

- La implementación de D en `tracking.py` da salida idéntica —`vehicle_id`,
  `dist_m`, `dt_s`, `vel_kmh`— al candidato medido, en 61 conjuntos incluidas
  44.472 posiciones reales.
- `generar` de la auditoría y `simular_flota` con fenómenos coinciden fila a
  fila (entrada 013).
- La jornada real se carga por `ts_ingest_utc` y no por partición: 7.658
  trayectorias el 27/08 frente a las 7.632 de la entrada 008, que leía la
  partición y arrastraba el desfase de media hora de la entrada 011.

## Por qué importa

Cada intercambio pone la etiqueta de un autobús en la posición de otro y
fabrica dos `vel_kmh` imposibles, justo en paradas, que es donde se acumula el
retraso. Reducirlos un 70 % sin partir una sola trayectoria más es la
diferencia entre una variable de velocidad utilizable y una contaminada.

La lección de método es la de la ficha 007 un nivel más arriba: un empate no se
rompe afinando el coste, se rompe con información que la matriz no tiene. En la
007 esa información era el movimiento del grupo; aquí es el futuro inmediato.
Los cuatro candidatos de coste movían los errores de sitio —E arregla giros y
empeora el escenario combinado; C con α = 0,5 rompe la flota limpia— en lugar
de quitarlos.

## Qué se hizo / qué queda abierto

Hecho:

- `_suavizar_intercambios` en `src/project/tracking.py`, solo en modo
  predictivo: el ingenuo sigue siendo la referencia sin ayudas.
- Guardias: `test_parar_o_girar_en_un_encuentro_no_intercambia_identidad` con
  dos encuentros de la simulación congelados como coordenadas, su test de
  discriminación con el suavizado desactivado, y
  `test_el_suavizado_mide_el_tiempo_con_el_reloj_de_sondeo`. Esta última guarda
  un error cometido durante el desarrollo: medir el tiempo por fila y no por
  sondeo reescribía `dt_s` a 8 s o negativo y dejaba 14 desplazamientos del
  27/08 aparentemente fuera de la puerta.
- `tests/test_tracking_realismo.py`: las semillas que el suavizado resuelve dejan
  de ser `xfail`; dos quedan como límite (arranque desde reposo en el último
  sondeo, y encuentro en parada con rumbos no relacionados).
- De paso deja de mezclar identidades en el giro en cabecera: el `xfail` de
  `test_flip_de_trayecto_en_cabecera_no_mezcla_identidades` se retira. La
  fragmentación del giro sigue abierta.

Abierto:

- **El residuo de "todos"** (46 saltos en 40 ejecuciones reservadas). La
  hipótesis inicial —el suavizado corrige al final, pero el predictor ya usó la
  velocidad del bus equivocado y un intercambio provoca el siguiente— **queda
  refutada**: evaluados los dos movimientos sobre el par verdadero de cada salto
  residual con velocidad previa, en 34 de 36 **ningún movimiento reduce el
  cambio de velocidad**; la asignación equivocada es cinemáticamente más suave
  que la verdadera, y en los otros 2 la mejora no llega a los 10 m. Meter el
  suavizado en el bucle no lo arreglaría: falla el criterio, no el momento.
  Explicación probable: en `simular_flota` cada bus lleva rumbo propio, y dos
  buses de la misma línea no comparten calle. Un simulador con rutas compartidas
  improvisado para comprobarlo no sirvió de árbitro: con giros casi en cada paso
  y rutas que se pisan a sí mismas, falla más que la realidad. La información
  que falta es la geometría de la ruta (GTFS `shapes.txt`).
- Las semillas 9001-9020 ya están vistas: cualquier iteración nueva necesita
  otras reservadas.
- La guardia de la trampa 009 quedó enmascarada por el suavizado y se corrigió
  para medir el predictor sin él (mutante 017, commit `7397b57`).
- Las cifras de las entradas 001, 009 y 010 se midieron sin suavizado. La 001
  usa el modo ingenuo, que no cambia; las otras dos habría que volver a medirlas.

## Para la memoria

> El reconstructor de trayectorias empareja las posiciones de cada sondeo con
> las del anterior mediante una asignación óptima sobre la distancia a la
> posición extrapolada. Al evaluarlo sobre una flota sintética con paradas y
> giros calibrados sobre la captura real, se observaron intercambios de
> identidad entre vehículos de la misma línea que coincidían en el instante en
> que uno de ellos se detenía o giraba. Cuatro reformulaciones del coste de
> asignación —hipótesis de parada, de giro, normalización por incertidumbre y
> amortiguación de la extrapolación— no los eliminaron y en dos casos
> empeoraron escenarios que la versión original resolvía. El análisis mostró
> que dos de cada tres intercambios se revertían en el sondeo siguiente, es
> decir, que la información necesaria para corregirlos no estaba disponible en
> el momento de la decisión sino un paso después. Se incorporó por ello una
> etapa de suavizado con un sondeo de retardo, que revisa localmente las
> asignaciones minimizando la variación de velocidad sin romper trayectorias.
> Sobre veinte semillas reservadas para la validación, los intercambios se
> redujeron entre un 58 % y un 100 % según el escenario, sin alterar el número
> de trayectorias ni su duración mediana en tres jornadas reales, aunque en el
> escenario más completo persiste aproximadamente un 30 % de los intercambios
> originales.
