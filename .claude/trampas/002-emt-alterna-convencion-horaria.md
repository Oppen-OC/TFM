---
id: 002
titulo: La EMT alterna entre UTC y hora local naive de un sondeo al siguiente
estado: cerrada
capa: fuentes
detectada: 2026-08-16
test: demo/selftest.py::"serie con convenciones alternas: ninguna fila desplazada >1 h"
---

## Síntoma

El campo `fecha` de la capa de buses viene en epoch-ms. Al convertirlo, la
mayoría de las posiciones dan una latencia razonable (decenas de segundos) y una
minoría da exactamente **dos horas**. No hay error, no hay nulos: solo una parte
de la serie desplazada.

## Causa

El servicio **no usa una única convención**. Medido el 16/08/2026 sobre 12,5 h de
captura real, 1.224 snapshots:

| Convención | Snapshots | Filas |
|---|---|---|
| Hora local de Madrid sellada como si fuera UTC | 979 (79 %) | 51.854 |
| UTC real | 267 (21 %) | 13.199 |

Y no es un cambio puntual: **338 alternancias en 12,5 horas**, con rachas de
mediana 2 snapshots. Cambia prácticamente de un sondeo al siguiente. La
explicación más probable es un balanceador con varios nodos detrás configurados
con zonas horarias distintas: según a cuál caiga la petición, el sello es uno u
otro.

## Por qué se vuelve a caer aquí

Porque el diagnóstico correcto ("va adelantada +2 h en verano, +1 h en invierno")
lleva a la solución incorrecta. Inspeccionar una muestra pequeña confirma el
desfase fijo, y aplicar `zoneinfo` por fecha lo arregla en el 79 % de los casos.
El 21 % restante queda desplazado dos horas.

Sobre una etiqueta de retraso construida por interpolación del paso por parada,
eso no produce ruido: produce **etiquetas sistemáticamente falsas en una quinta
parte del conjunto, sin ningún síntoma visible**. El modelo entrena, converge y
reporta métricas creíbles.

Mismo riesgo con `fechaActualizacion` de Renfe, que llega como ISO naive.

## Guardia

`resolver_convencion()` en `demo/sources.py:68`. No asume: por cada snapshot
prueba las dos interpretaciones y se queda con la que produce una latencia
plausible. Se autocalibra en el cambio de hora de octubre, porque no codifica el
desfase — lo deduce.

Efecto medido sobre los mismos payloads crudos:

| | p50 | p90 | p99 | máx | filas desplazadas > 1 h |
|---|---|---|---|---|---|
| Antes | 26 s | 7.222 s | 7.241 s | 7.348 s | 12.335 (20,3 %) |
| Después | 23 s | 39 s | 76 s | 477 s | **0** |

Test: `demo/selftest.py`, check *"serie con convenciones alternas: ninguna fila
desplazada >1 h"*. Ver también *"dato rancio -> se marca DUDOSA en vez de
adivinar"*: cuando ninguna de las dos interpretaciones da latencia plausible, no
se elige a ciegas.

Se arregló **sin recapturar nada**, reprocesando los payloads crudos de
`data/raw/`. Es el argumento operativo de por qué la ingesta se separa del
procesado: capturar es irreversible, procesar es reintentable.
