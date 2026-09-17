---
id: 013
titulo: La flota simulada nunca para y apenas gira; los buses reales están parados el 29 % de los pasos, y con paradas y giros realistas el tracker produce 2-4 saltos de identidad que ningún test ve
fecha: 2026-09-17
tipo: medicion
capa: tracking
capitulo: metodologia
impacto: alto
estado: abierto
evidencia: uv run python -m project.analysis.auditar_supuestos
trampa: 007
---

## Qué se observó

Mismo instrumento sobre la flota de `simular_flota()` y sobre 52 ventanas
horarias reales (13 días × 08, 11, 14 y 18 h local; 1.005.141 pasos):

| magnitud | simulación | laborable | fin de semana |
|---|---|---|---|
| velocidad p50 (km/h) | 18,5 | 7,5 | 8,3 |
| pasos parado (< 1,2 km/h) | **0 %** | **29,2 %** | **28,4 %** |
| giro entre pasos p90 | **13,9°** | **56,9°** | **57,6°** |
| vecino de su grupo más cerca que el propio paso | 0,88 % | 0,53 % | 0,43 % |
| vehículos por (línea, trayecto) p50 | 7,5 | 3 | 2 |
| duración del paso p99 | 30 s | 33 s | 33 s |

La simulación es más exigente en densidad y mucho más fácil en movimiento:
rectilíneo y uniforme, exactamente lo que supone el predictor.

Inyectando cada fenómeno en un generador que, apagado, reproduce
`simular_flota()` fila a fila (5 semillas × 20 y 80 sondeos):

| escenario | saltos | contaminadas (máx.) |
|---|---|---|
| ninguno | 0 | 0 % |
| paradas (28,6 % parado) | 20 | 3,3 % |
| giros (p90 24°) | 20 | 3,3 % |
| ruido GPS σ 2 m | 0 | 0 % |
| cadencia irregular | 0 | 0 % |
| todos | 10 | 3,3 % |
| estrés ×2 | 52 | 13,3 % |

La fragmentación queda en 1,00 en todos: es fusión pura.

## Cómo se midió

```bash
uv run python -m project.analysis.auditar_supuestos --json auditoria/resultados/supuestos_fc5d15c.json
uv run python auditoria/escenarios.py --json auditoria/resultados/escenarios_fc5d15c.json
```

Las magnitudes se leen de la salida de `rastrear()` en ambos lados. Las ventanas
se filtran por `ts_ingest_utc` sobre todas las particiones, no por `date=`
(entrada 011). `escenarios.py` arranca con un control: sin fenómenos, su
generador debe ser idéntico a `simular_flota()`, o se detiene.

Cada salto se inspeccionó: separación entre los dos buses intercambiados de 19 a
103 m, con pasos de 145 a 205 m. En los casos de parada, el predictor extrapola
al bus detenido hacia delante y le asigna la posición del que pasa; el sondeo
siguiente lo deshace. En convoy no se deshace.

## Por qué importa

Los tests de tracking y las cifras de las entradas 001, 009 y 010 se miden sobre
una flota en la que el predictor de velocidad constante es exacto por
construcción. El 0 de saltos era una propiedad de la simulación, no del tracker.

Cada intercambio deja una posición con la etiqueta de otro autobús y dos
`vel_kmh` imposibles —un bus parado que "recorre" 200 m y vuelve—. La velocidad
es candidata a variable del modelo, y los intercambios ocurren justo en paradas,
que es donde se acumula el retraso.

La tasa no se puede trasladar a la captura real: los giros están subcalibrados
(24° frente a 57°) y la simulación tiene más encuentros que la realidad. Es un
orden de existencia, no una estimación de volumen.

## Qué se hizo / qué queda abierto

Hecho: `src/project/analysis/auditar_supuestos.py` y `auditoria/escenarios.py`,
que quedan como herramienta re-ejecutable.

Abierto:

- Escenario con paradas y giros en los tests de tracking (fase 2).
- Medir los intercambios sobre captura real sin verdad-terreno: por ejemplo,
  pasos con parada seguidos de reanudación en el sondeo siguiente.
- Decidir si el predictor debe amortiguar la velocidad tras un paso corto; eso
  cambia el tracker y queda fuera de esta auditoría.

## Para la memoria

> La evaluación del reconstructor de trayectorias descansa sobre una flota
> sintética con verdad-terreno conocida. Para comprobar que esa flota
> representa las condiciones reales, se compararon con el mismo instrumento
> sus propiedades cinemáticas con las de 52 ventanas horarias de la captura, algo
> más de un millón de desplazamientos. La flota sintética resultó más densa que
> la real, pero con un movimiento rectilíneo y uniforme: ningún vehículo se
> detenía, frente al 29 % de los desplazamientos reales, y el cambio de rumbo en
> el percentil 90 era de 14 grados frente a 57. Al incorporar paradas y giros con
> frecuencias calibradas sobre los datos, el reconstructor pasó de cero a entre
> dos y cuatro intercambios de identidad por ejecución, concentrados en encuentros
> entre vehículos de la misma línea en el instante en que uno se detiene o gira.
> El resultado delimita la validez de las métricas obtenidas sobre la flota
> original y motiva su ampliación.
