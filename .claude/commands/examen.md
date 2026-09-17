---
description: Te examina sobre los temas y las decisiones de diseño del repo, corrige tus respuestas y registra lo que flojea
argument-hint: [tema, ruta, id de trampa, --corregir, o vacío para atacar debilidades]
---

Encargo: **$ARGUMENTS**

Registro: `.claude/examenes/`. El formato, la rúbrica, el ciclo de vida y —sobre
todo— la sección *Qué se pregunta y qué no* están en
`.claude/examenes/README.md`. **Léelo antes de generar o corregir; no dupliques
aquí sus reglas ni sus campos.**

**Frontera:** `/encargo` completa una petición cruda · `/grill-me` presiona un
plan ya formado · **este comando presiona lo que tú sabes del repo ya escrito.**
Aquí no se decide ni se ejecuta nada: no hay plan que aprobar, no hay código que
tocar. Si lo que traes es una duda genuina sobre qué hacer, no es materia de este
comando.

## Encaminamiento de `$ARGUMENTS`

| argumento | acción |
|---|---|
| `tracking`, `fuentes`, `pipeline`, `arquitectura`… | genera tanda del tema |
| una ruta (`src/project/tracking.py`) | genera tanda sobre las decisiones de ese módulo |
| un id de tres dígitos (`008`) | genera tanda sobre esa ficha de trampa |
| `--corregir` | corrige el examen `contestado` más reciente |
| `--corregir 003` | corrige ese |
| *(vacío)* | genera tanda sobre los conceptos `flojo` de `debilidades.md` |

## Generar

1. **Lee las fuentes ahora, no de memoria.** Abre el código, las fichas y las
   entradas de bitácora que tocan el tema **en este momento**. Lo que creas
   recordar de la conversación no vale como fuente: el repo cambia y tu recuerdo
   de esta sesión está contaminado.

2. **Descarta lo que acabas de contar.** Si un concepto salió explicado en el chat
   de esta misma sesión, no se pregunta. Aprobaría sin saber nada, que es
   exactamente el fallo que mata el instrumento.

3. **Escribe 5-7 preguntas** que pasen los dos filtros del README. Todas sobre
   temas y decisiones de diseño; ninguna sobre firmas, constantes, rutas ni
   nombres. Antes de escribir cada una, comprueba que la respuesta correcta no se
   encuentra con un `grep` y que contiene un *porque*.

4. **Ataca lo flojo primero.** Si `debilidades.md` tiene conceptos `flojo` del
   tema pedido, al menos uno entra — con una **pregunta distinta** de la que se
   falló. Reciclar el enunciado mide memoria del enunciado.

5. **Escribe el fichero** con el siguiente `id` libre, `estado: en-blanco`,
   `ronda: 1`, y `fuentes:` con lo que realmente has leído. Sin clave dentro.

6. Termina diciendo la ruta del fichero y nada más. **No adelantes pistas ni
   comentes las preguntas**: cualquier cosa que digas aquí es una respuesta
   filtrada.

## Corregir

1. **Relee las fuentes.** Se juzga contra el repo de hoy, no contra lo que
   supieras al generar. Orden de autoridad: el del README.

2. **Un veredicto por pregunta**, con la rúbrica del README. Sé duro con
   `a-medias`: la respuesta que acierta el qué y calla el porqué es la que engaña.
   Si te descubres justificando por qué una respuesta floja «vale», es que no
   vale.

3. **Ronda 1, fallo: pista y puntero.** Di qué parte del razonamiento no encaja y
   dónde mirar —fichero, ficha, entrada de bitácora—, y **para ahí**. No escribas
   la respuesta, ni una versión reconocible de ella. Sube `ronda: 2`, deja el
   fichero listo para reescribir y dilo.

4. **Ronda 2, fallo: respuesta completa** y el concepto a `debilidades.md`. No hay
   ronda 3.

5. **Actualiza `debilidades.md`.** Un acierto a la primera en sesión distinta y
   pregunta distinta suma acierto limpio; dos ⇒ `dominado`. Todo lo demás suma
   fallo.

6. **Escribe `nota:` y el `estado:`** que corresponda.

7. **Si defiendes una respuesta y tienes razón**, la clave estaba mal: no baja la
   nota. Encamina el hallazgo — `gh issue create`, ficha de trampa o entrada de
   bitácora, según la tabla de `docs/bitacora/README.md`.

## Cuándo el comando está roto

Si una tanda te aprueba todo a la primera, y se repite, el fallo no es tuyo: las
preguntas son blandas o se están generando de lo que ya se habló. Endurece la
generación antes de creerte la nota. Es la misma lección de la trampa 004 — ante
un resultado sorprendente, la primera hipótesis es que el instrumento miente.
