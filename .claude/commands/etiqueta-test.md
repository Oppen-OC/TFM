---
description: Genera un test con datos sintéticos de verdad-terreno conocida antes de tocar el etiquetado
argument-hint: <caso a cubrir, p.ej. "bus parado en semáforo" o "cambio de hora">
---

Escribe el test de verdad-terreno para: **$ARGUMENTS**

El etiquetado de retraso y el tracking son la capa donde un bug es silencioso: no
lanza excepción, contamina todas las etiquetas y las métricas siguen pareciendo
razonables. Por eso el test va **antes** que el código.

## Pasos

1. Fabrica el escenario sintético a mano. Tú decides las posiciones, los
   timestamps y el horario teórico, así que sabes exactamente qué retraso debe
   salir. Nada de muestrear datos reales: si no conoces la respuesta de
   antemano, no es un test de verdad-terreno.

2. Cubre el caso normal **y** el borde. Para los bordes que ya han mordido, lee
   las fichas de `.claude/trampas/` con `capa: tracking` o `capa: etiquetado` —
   el índice ya lo tienes en contexto. Prioriza cubrir las que están en estado
   `vigente` o `mitigada`: son, por definición, las que no tienen guardia.

   Bordes propios del pipeline, además de esas:
   - Trayectorias por debajo de `prepare.min_posiciones_viaje` se descartan.
   - Saltos por encima de `prepare.salto_max_m` o `prepare.vel_max_kmh` son
     errores de emparejamiento, no movimiento real.
   - Un test que cruce el cambio de hora de octubre vale su peso en oro.

3. Coloca el test donde corresponda: `tests/test_features.py` si toca la
   transformación, un test junto a `prepare.py` si toca tracking o etiquetado.
   Sigue el estilo de `demo/selftest.py`: sin red, determinista, verdad-terreno
   explícita en el propio test.

4. **Confirma que el test falla** antes de tocar el código. Un test que pasa
   desde el primer momento no está probando lo que crees.

5. Arregla. Vuelve a correr:

   ```
   uv run pytest
   python demo/selftest.py
   ```

6. Si el test cierra la guardia de una ficha en estado `vigente` o `mitigada`,
   actualiza su frontmatter: `estado: cerrada` y `test:` apuntando al check
   nuevo. Es el único camino para que una ficha se cierre.

## Salida

El test, la razón por la que fallaba, el arreglo, si el cambio invalida etiquetas
ya generadas en `data/interim/`, y qué ficha de `.claude/trampas/` cambia de
estado.
