---
id: 010
titulo: El predictor del tracker extrapola en pasos de snapshot y no en segundos; el fallo aparece uno o dos sondeos después del hueco y se atribuye al cambio equivocado
fecha: 2026-09-16
tipo: anomalia
capa: tracking
capitulo: metodologia
impacto: medio
estado: resuelto
evidencia: uv run pytest tests/test_tracking.py -k "hueco"
trampa: 009
---

## Qué se observó

Evaluando el arreglo que descarta los sondeos con carga útil truncada, el
escenario sintético del sondeo parcial devolvía **4 saltos de identidad y 3,3 %
de trayectorias contaminadas** donde la configuración de referencia daba cero.
La lectura inmediata —«descartar sondeos rompe la identidad»— resultó ser falsa.

Localizados los saltos por snapshot:

| configuración | saltos en | sondeo descartado | transición que lo salva |
|---|---|---|---|
| descartar parciales | **1009, 1009, 1010, 1010** | 1007 | 1006 → 1008 |
| tolerar hueco | ninguno | — | — |

**Ningún salto cae en la transición que salta el hueco.** Todos caen uno y dos
sondeos después, que es donde el defecto real se manifiesta.

La causa es que `_plat` / `_plon` guardan la posición del paso anterior pero no
su duración. Tras la transición 1006 → 1008, `_plat` contiene la posición de 1006
—dos sondeos atrás— mientras la predicción de 1008 → 1009 sigue aplicando
`lat_pred = 2 · lat − _plat`, que asume un paso. El desplazamiento leído es el
doble del real y la extrapolación se pasa de largo.

Añadida al banco la duración del paso que generó `_plat`, y extrapolando por la
razón entre duraciones, el escenario vuelve a **0 saltos y 0,0 % de
contaminadas**, y el coste en posiciones descartadas (1,0 %) queda como única
diferencia frente a tolerar huecos.

Frecuencia del disparador sobre dato real, jornada del 27/08/2026, 2.749
transiciones:

| razón entre la duración de un paso y la del anterior | transiciones | % |
|---|---|---|
| > 1,5 | 10 | 0,36 % |
| > 2 | **5** | 0,18 % |
| > 5 | 2 | 0,07 % |

Cadencia: mediana **31,0 s**, p99 34,0 s, máximo **445,0 s**. Una transición con
duración cero (dos sondeos con el mismo sello temporal) queda cubierta por el
`or 30.0` de `rastrear()`.

## Cómo se midió

Ya en el repositorio, sobre `simular_flota(huecos=(7,))`:

```bash
uv run pytest tests/test_tracking.py -k "hueco"
```

La primera detección fue en el banco del scratchpad, comparando el escenario del
sondeo parcial con y sin el arreglo:

```bash
PYTHONPATH=$SB uv run python $SB/experimento.py
```

La localización de los saltos por snapshot se obtiene recorriendo cada trayectoria
reconstruida y anotando el sondeo en que cambia la columna `verdad`, sobre
`simular_flota(parciales={7: 0.2})`.

La frecuencia del disparador sale de `data/curated/source=emt_buses/date=2026-08-27`,
comparando la duración de cada transición con la de la anterior.

## Por qué importa

El interés de este hallazgo no es el tamaño del defecto —hoy muerde en 5 de 2.749
transiciones— sino **la distancia entre el síntoma y su causa**, que es lo que lo
convierte en una trampa y no en un bug.

El fallo aparece uno o dos sondeos *después* del hueco, de modo que el cambio que
lo destapa no es el que lo provoca. Sin haber localizado los saltos por snapshot,
la conclusión del banco habría sido «descartar sondeos parciales daña la
identidad», y se habría descartado un arreglo por un motivo falso mientras el
defecto real seguía en el código.

Además está **latente**: el predictor es correcto mientras la cadencia sea
uniforme, y el colector la mantiene uniforme el 99,8 % del tiempo. Se activa con
cualquier mecanismo que altere esa cadencia —tolerar huecos, descartar sondeos,
submuestrear la serie—, que son precisamente los cambios propuestos para reducir
la fragmentación (bitácora [008](008-la-ventana-de-medicion-censuraba-la-metrica.md)).
Es, por tanto, prerrequisito de cualquiera de ellos.

Es la cuarta vez que el instrumento induce a error en esta capa, y conviene
tenerlas juntas: la trampa 004 **exageraba** el fallo, la bitácora
[001](001-error-identidad-se-mide-en-trayectorias.md) lo **diluía**, la
[008](008-la-ventana-de-medicion-censuraba-la-metrica.md) lo **censuraba por
arriba**, y esta lo **desplaza en el tiempo** y se lo carga a otro.

## Qué se hizo / qué queda abierto

Hecho:

- **Arreglo portado a `src/project/tracking.py`**: el predictor extrapola por la
  razón entre la duración del paso que viene y la del que produjo `_plat`. Con
  cadencia regular el factor vale 1 y reproduce el `2*lat - _plat` anterior.
  Verificado que no cambia nada: mismo `vehicle_id` y `dist_m` que la versión
  previa sobre seis conjuntos, incluidas 22.208 posiciones reales.
- `simular_flota()` acepta `huecos=(...)`, que elimina sondeos **enteros** y es el
  único escenario con cadencia no uniforme del repositorio.
- Ficha [trampa 009](../../.claude/trampas/009-plat-no-arrastra-la-duracion-de-su-paso.md)
  cerrada con guardia: `tests/test_tracking.py::test_un_sondeo_que_falta_no_rompe_la_identidad`.
  Verificado que la guardia discrimina — revertido el arreglo, falla con
  `assert 4 == 0`.

Abierto:

- El efecto sobre el dato real no está cuantificado más allá de la frecuencia del
  disparador: se sabe que 5 transiciones al día lo activan, no cuántas identidades
  se pierden en ellas.

## Para la memoria

> La extrapolación de posición empleada en la asociación de identidades utiliza un
> modelo de velocidad constante expresado en diferencias finitas sobre la rejilla
> de sondeos. Dicha formulación presupone que el intervalo que separa la posición
> anterior de la actual coincide con el intervalo que se pretende predecir,
> hipótesis que se cumple mientras la cadencia de captura sea regular —lo es en el
> 99,8 % de las 2.749 transiciones de la jornada analizada, con mediana de 31,0
> segundos— pero que deja de cumplirse ante cualquier discontinuidad de la serie,
> ya proceda de una interrupción del colector (máximo observado: 445 segundos) o
> de un tratamiento deliberado de los sondeos incompletos.
>
> El efecto de esta discrepancia resulta particularmente difícil de atribuir: el
> emparejamiento erróneo no se produce en la transición que atraviesa la
> discontinuidad, sino en las una o dos siguientes, cuando la posición de
> referencia almacenada corresponde ya a dos sondeos atrás y la extrapolación
> duplica el desplazamiento real. En la evaluación de correcciones descrita
> anteriormente, este comportamiento se manifestó inicialmente como un deterioro
> atribuible a la corrección evaluada; la localización de los intercambios por
> sondeo permitió descartar esa atribución e identificar la causa en el propio
> modelo de extrapolación. Corregido éste para operar sobre intervalos temporales
> en lugar de sobre pasos de rejilla, el deterioro desaparece por completo, y la
> reproducción exacta de los resultados previos en condiciones de cadencia
> regular confirma que la corrección no altera ninguna medición publicada.
