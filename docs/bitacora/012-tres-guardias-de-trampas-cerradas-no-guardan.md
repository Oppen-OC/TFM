---
id: 012
titulo: Tres de las siete trampas cerradas tienen una guardia que no cae al deshacer su arreglo; la de la 004 quedó inerte al actualizar numpy
fecha: 2026-09-17
tipo: anomalia
capa: tracking
capitulo: metodologia
impacto: alto
estado: abierto
evidencia: uv run python auditoria/mutar.py
trampa: 008
---

## Qué se observó

Se deshizo el arreglo de cada trampa `cerrada` sobre un worktree desechable y se
comprobó si la guardia que cita su ficha se pone roja:

| trampa | guardia de la ficha | ¿cae? | por qué no |
|---|---|---|---|
| 001 | `test_gids_de_sondeos_consecutivos_son_disjuntos` | no | comprueba el fixture, no código |
| 002 | `test_serie_con_convenciones_alternas_ninguna_fila_desplazada` | sí | — |
| 003 | `test_renfe_filtra_solo_nucleo_40` | sí | — |
| 004 | `test_tracker_predictivo_identidad_correcta` | **no** | el bug ya no se manifiesta |
| 007 | `test_convoy_en_fila_india_no_intercambia_identidad` | sí | — |
| 008 | `test_ningun_desplazamiento_supera_la_puerta_fisica` | **no** | los escenarios no lo ejercitan |
| 009 | `test_un_sondeo_que_falta_no_rompe_la_identidad` | sí | — |

**Trampa 008.** Evaluar la puerta física solo sobre la posición predicha no altera
ningún test de la suite. Con dos sondeos perdidos a cadencia de 60 s, ese código
acepta 34 desplazamientos por encima de `SALTO_MAX_M`, hasta 1.442 m; el actual,
ninguno.

**Trampa 004.** Con numpy 2.2.6 —la versión del 19/08, cuando se detectó—
`argsort(kind="quicksort")` permuta un `int64` ya ordenado con claves repetidas.
Con numpy 2.4.6 en un AMD Zen 3 devuelve la identidad. Como `simular_flota()`
entrega la flota ya ordenada, quitar `kind="stable"` hoy no cambia ni un byte de
salida en ninguna sonda.

## Cómo se midió

```bash
uv run python auditoria/mutar.py --solo 001 016
uv run --no-project --with numpy==2.2.6 python -c "import numpy as np; a=np.repeat(np.arange(20),60); print((np.argsort(a,kind='quicksort')!=np.arange(1200)).any())"
uv run --no-project --with numpy==2.4.6 python -c "import numpy as np; a=np.repeat(np.arange(20),60); print((np.argsort(a,kind='quicksort')!=np.arange(1200)).any())"
```

El runner lee el campo `test:` de cada ficha y lo compara con los tests que caen.
Controles previos: suite de referencia verde, `import project` resolviendo al
worktree, mutante nulo equivalente y un mutante determinista detectado. El caso
de la 004 se detectó precisamente porque era el control positivo previsto y
salió equivalente: se investigó antes de aceptar que el runner funcionaba.

Los 34 saltos de la 008 se obtienen cargando el `tracking.py` mutado como módulo
aparte y comparando `dist_m` contra la puerta sobre los escenarios de
`auditoria/sondas.py`.

## Por qué importa

Una ficha `cerrada` afirma que hay un test que impide volver a caer. En tres de
siete, esa afirmación era falsa y nada lo delataba: la suite estaba en verde.

La 008 es la más seria porque el defecto está documentado sobre datos reales
—24 a 46 saltos imposibles por ventana, bitácora 003— y una regresión pasaría la
CI. La 004 enseña algo distinto: **una guardia puede caducar sin tocar ni el
código ni el test**, solo con actualizar una dependencia. El arreglo sigue siendo
correcto; lo que dejó de funcionar es la demostración.

## Qué se hizo / qué queda abierto

Hecho: el diagnóstico, el catálogo `auditoria/catalogo.toml` y el runner, que
ahora vuelve a medirlo en 40 minutos.

Abierto, pendiente de aprobación:

- Fichas 004 y 008 de `cerrada` a `mitigada` hasta que tengan guardia efectiva.
- Ficha 001: citar `test_emt_snapshot_id_es_el_gid_minimo_del_bloque`, que sí cae.
- Guardia de la 008 con un escenario de paso largo o sondeo perdido.
- Guardia de la 004 que no dependa del algoritmo de ordenación de numpy: por
  ejemplo, entrada desordenada entre sondeos con verdad unida por clave.

## Para la memoria

> La batería de pruebas se sometió a una auditoría por mutación dirigida: para
> cada defecto documentado y ya corregido se reintrodujo deliberadamente el
> error y se verificó si la prueba asociada lo detectaba. En tres de los siete
> defectos cerrados la prueba seguía superándose con el error presente. En un
> caso los escenarios de la prueba no llegaban a ejercitar la condición que
> desencadena el fallo; en otro, el defecto original, dependiente del algoritmo
> de ordenación de la biblioteca numérica, había dejado de manifestarse tras una
> actualización de versión, de modo que la prueba ya no podía fallar aunque se
> reintrodujera el código erróneo. Estos resultados muestran que una prueba en
> verde no constituye por sí misma evidencia de protección frente a regresiones,
> y que dicha protección debe verificarse de forma explícita y periódica.
