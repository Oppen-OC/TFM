---
name: diagnosticar
description: Método para diagnosticar fallos difíciles y regresiones de rendimiento con un bucle de retroalimentación reproducible. Úsalo cuando un fallo sea intermitente, esté mal entendido, se haya diagnosticado mal más de una vez, o cuando la métrica que lo delata pueda estar mintiendo. No lo uses para errores de una línea con causa ya probada.
---

# Diagnosticar

Adaptado de `diagnosing-bugs` (MiquelGomezCorral/my-opencode-config).

Este proyecto tiene una clase de fallo que no lanza excepción: contamina las
etiquetas y deja que el modelo entrene, converja y reporte métricas creíbles. Aquí
el instinto de "arreglar lo que parece roto" es el enemigo.

## Regla primera

**No arregles antes de reproducir.** La única excepción es que la evidencia
estática pruebe el defecto directamente.

El corolario duele más: **antes de arreglar lo medido, comprueba la medición.** La
trampa [004](../../trampas/004-sort-inestable-en-snapshot.md) reportó 11 % de
precisión de tracking cuando la real era 99 %. El tracker estaba bien; el arnés
reenganchaba la verdad-terreno por posición de fila. Ir a "arreglar" el tracker
habría roto código correcto persiguiendo un número falso.

Ante una métrica sorprendentemente mala, la primera hipótesis es que el
instrumento miente.

## Bucle

1. **Construye la señal más estrecha que reproduzca el síntoma.** Un test
   enfocado, una invocación de `demo/`, un snapshot concreto de `data/raw/`
   reprocesado. Cuanto más rápido el ciclo, más hipótesis caben.

2. **Reproduce el fallo real y minimiza la entrada** manteniéndolo en rojo. Si
   minimizar lo apaga, acabas de aprender dónde está.

3. **Ordena hipótesis falsables** y prueba primero la predicción discriminante más
   barata. **Una variable cada vez.** No repitas una hipótesis sin evidencia
   nueva.

4. **Instrumenta solo las fronteras que distinguen hipótesis.** Marca los
   diagnósticos temporales para poder quitarlos todos después.

5. **Convierte la reproducción mínima en test de regresión**, en la costura
   correcta: `demo/selftest.py` si es parseo de fuentes o tracking (sin red,
   determinista), `tests/` si es features, API o el registro de trampas. Solo
   entonces aplica el arreglo mínimo de causa raíz.

6. **Verifica en tres niveles:** la reproducción original, el test nuevo, y lo que
   rodea. Quita los diagnósticos temporales.

## Guardarraíles del proyecto

- **Un fallo cercano no es el fallo reportado.** Si aparece otro bug por el
  camino, anótalo y sigue con el tuyo.
- **Regresiones de rendimiento: mide el baseline antes de tocar nada**, y compara
  la misma carga después. `rastrear()` está identificado como cuello de botella
  para 3 meses de datos (`docs/05`, sección 7); optimizarlo sin medir antes es
  adivinar.
- **Datos sintéticos de verdad-terreno, no muestras reales,** para todo lo que
  toque tracking o etiquetado. Si no conoces la respuesta de antemano, no es un
  test, es una foto.
- **Reprocesa el crudo antes de recapturar.** `data/raw/` guarda el payload
  verbatim justamente para esto: la trampa 002 se arregló sobre datos ya
  capturados. Y no hay histórico recuperable, así que recapturar no siempre es una
  opción.
- **Si el arreglo cambia el etiquetado, di qué etiquetas ya generadas quedan
  invalidadas.** Nunca se omite.
- **Si el código contradice a la documentación o a una ficha, gana el código.**

## Cuándo parar y preguntar

Si no consigues una reproducción determinista, sube la tasa de fallo o captura un
artefacto concreto (el snapshot exacto, el payload crudo, el run de MLflow).
Cuando sigas bloqueado, di qué intentaste y pide **un** artefacto o acceso
concreto. No sigas iterando a ciegas.

## Informe

Comando de reproducción · causa raíz · arreglo · test que lo cubre · verificación
fresca. Separa lo probado de lo que sigue siendo incertidumbre.

Si la causa raíz era algo que la fuente no documenta o documenta mal, abre ficha
en `.claude/trampas/`. Si era visible en el stack trace, no: a GitHub Issues.
