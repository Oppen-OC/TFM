---
description: Convierte una petición cruda en un encargo completo, con supuestos marcados y preguntas bloqueantes
argument-hint: <la petición tal cual la escribirías, por pobre que sea>
---

Petición cruda: **$ARGUMENTS**

Tu trabajo es devolverla completa, no ejecutarla. **No implementes nada** hasta que
el usuario apruebe el encargo reescrito.

**Frontera con `/grill-me`:** aquí se completa una *petición*; allí se interroga un
*plan ya formado*. Encadenan en ese orden. Si `$ARGUMENTS` ya trae método y pasos,
no es materia de este comando: dilo y pasa a `/grill-me`. Ninguno de los dos
examina lo que ya sabes del repo escrito: eso es `/examen`.

## Método

1. **Investiga antes de preguntar.** `docs/00_tema_y_alcance.md` para el alcance
   vigente, `docs/07_decisiones.md` para lo ya cerrado, el índice de
   `.claude/trampas/`, `docs/bitacora/` y el código que la petición toque. Lo que
   responda el repo no se pregunta: se cita.

2. **Recorre las ocho dimensiones de *Encargos incompletos* (`CLAUDE.md`).** No
   las copies aquí; están siempre en contexto. Clasifica cada una en una de tres:

   - **resuelta** — el repo la contesta. Cita fichero o línea.
   - **supuesto** — la contestas tú con el valor por defecto razonable. Escribe el
     valor y **qué se rompe si es falso**.
   - **bloqueante** — supuesta al revés, el trabajo sale distinto. Solo estas se
     preguntan.

   Una dimensión que no muerde en este encargo se omite. No rellenes las ocho por
   simetría: ruido que no discrimina es peor que silencio.

3. **Pregunta como mucho tres**, ordenadas por palanca. Cada una con: por qué
   importa, tu recomendación, y qué desbloquea. Una pregunta cuya respuesta no
   cambia el trabajo no es bloqueante — degrádala a supuesto.

4. **Reescribe el encargo** con las respuestas y los supuestos dentro.

## Dónde suele estar el hueco

Sitios de este repo donde la petición corta ha salido cara antes:

- **La cifra sin instrumento.** Se pide medir algo sin decir contra qué se compara
  ni qué valor sería un fracaso. El instrumento también miente (trampa 004).
- **El dato que nadie captura.** Se planifica una feature sobre un campo que no
  está en `data/raw/`, y no hay histórico que recuperar.
- **El cambio que reetiqueta.** Tocar `tracking.py` o el etiquetado invalida todo
  lo generado antes, en silencio y sin excepción.
- **El script suelto.** Entrenar o transformar fuera de un stage de `dvc.yaml`,
  con hiperparámetros fuera de `params.yaml`.
- **El test que no falsaría nada.** Un test que pasaría igual con el código roto.
  Los de `tests/conftest.py` valen porque conocen la verdad-terreno.
- **La frontera cruzada por comodidad.** Un import de `services/` desde `ui/`
  ahorra diez minutos hoy y rompe el despliegue después.

## Salida

1. **Encargo reescrito** — objetivo, entradas, salidas, criterio de aceptación,
   no-objetivos. En prosa corta, no en formulario.
2. **Supuestos** — tabla `supuesto · valor asumido · qué se rompe si es falso`.
3. **Preguntas bloqueantes** — máximo tres, o "ninguna" si de verdad no las hay.
4. **Siguiente acción concreta** — normalmente `/grill-me` sobre el encargo ya
   completo, o directamente el plan si el encargo es pequeño.

Si al completar el encargo aparece un hallazgo de los que ficha la bitácora,
ofrécelo antes de cerrar.
