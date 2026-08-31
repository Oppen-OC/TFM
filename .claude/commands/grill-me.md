---
description: Interroga un plan o una decisión en árbol de dependencias antes de ejecutar nada
argument-hint: <el plan, enfoque o decisión a presionar>
---

Presiona esto antes de que se convierta en código: **$ARGUMENTS**

Adaptado de `grill-me` (`grp06/useful-codex-skills`, MIT).

Tu trabajo es resolver las decisiones importantes, las dependencias, los supuestos
y los modos de fallo — o registrarlos explícitamente como riesgo aceptado. **No
implementes nada** hasta que el usuario cambie de modo. Preguntar sale barato
ahora y carísimo dentro de tres semanas de captura.

## Método

1. **Lee la evidencia disponible antes de preguntar.** `docs/00_tema_y_alcance.md`
   para el alcance vigente, `docs/07_decisiones.md` para lo ya cerrado, el índice
   de `.claude/trampas/`, y el código que toque. No preguntes lo que el repo ya
   responde.

2. **Resume tu comprensión en 3-6 viñetas.** Si has entendido mal el plan, se ve
   aquí y no después de veinte preguntas.

3. **Construye el árbol de decisión ordenado por dependencias.** Ramas, en este
   orden, porque cada una condiciona la siguiente:

   - **Objetivo** — qué pregunta responde esto, y para quién.
   - **Criterio de éxito** — número concreto contra un baseline concreto. "Mejor"
     no es criterio. ¿Batir a persistencia en MAE? ¿Por cuánto?
   - **No-objetivos** — qué queda explícitamente fuera. Sin esto, el alcance se
     desborda solo.
   - **Datos** — ¿existe el dato que esto necesita? ¿Está capturado ya, o supone
     capturar durante N semanas más? Nada de esto es recuperable a posteriori.
   - **Método** — por qué este y no la alternativa obvia.
   - **Validación** — cómo sabrás que funciona, y cómo sabrías que no. Un plan sin
     condición de falsación no es un plan.
   - **Riesgo y plan B** — qué lo mata, con cuánta antelación lo verías venir, y a
     qué pivotas.
   - **Coste** — horas de trabajo y de cómputo. Un cambio que invalida `prepare`
     sobre 145 M de filas no es gratis.

4. **Investiga antes de preguntar.** Lo que puedan responder los ficheros, los
   tests, `docs/`, el historial de git o los runs de MLflow, resuélvelo tú. Pide
   solo el juicio que sigue siendo del usuario.

5. **Una pregunta cada vez**, la de mayor palanca: explica por qué importa,
   recomienda una respuesta y di qué desbloquea. Agrupa hasta tres solo si
   comparten rama.

6. **Tras cada respuesta**, reformula la decisión con tus palabras y pasa a la
   rama que dependía de ella.

## Cómo presionar

Sé concreto y ve a por lo que suele estar flojo:

- **Éxito difuso.** "Predecir bien" no es medible. ¿Contra qué baseline, con qué
  métrica, sobre qué conjunto?
- **Métricas falsas.** Cualquier cosa evaluada con split aleatorio sobre series
  temporales está inflada. Es el primer sitio donde mirará el tribunal.
- **Baselines ausentes.** Si el plan no compara contra horario teórico y
  persistencia, no hay resultado, hay un número.
- **Dato que no existe.** Se planifican features que nadie está capturando. Y no
  hay histórico recuperable.
- **Acoplamiento oculto.** Un cambio en el etiquetado invalida todas las etiquetas
  ya generadas. ¿Se ha contado eso?
- **Complejidad empujada al futuro.** "Ya lo optimizaremos" sobre 145 M de filas
  significa que no se hará.

**No aceptes una respuesta vaga como cerrada.** Repregunta o anótala como supuesto
sin resolver. Un supuesto explícito es defendible; uno tácito no.

## Salida

Libro de decisiones, en cuatro listas:

- **Cerradas** — decisión y su porqué en una línea.
- **Abiertas** — qué falta para cerrarlas.
- **Supuestos** — lo que se da por bueno sin evidencia, y qué pasa si es falso.
- **Riesgos aceptados** — conocidos, no mitigados, y por qué se acepta.

Cierra con la siguiente acción concreta.

Si alguna decisión cerrada aquí es estructural del TFM, dilo: merece entrada en
`docs/07_decisiones.md`.
