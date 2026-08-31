---
description: Audita el registro de trampas y guía la creación de una ficha nueva
argument-hint: [síntoma de la trampa nueva, o vacío para solo auditar]
---

Registro: `.claude/trampas/`. Su índice ya está en tu contexto vía el import de
`CLAUDE.md`; no hace falta releerlo para la parte de auditoría.

## Si `$ARGUMENTS` está vacío: auditar

**Primero lo mecánico**, que ya está automatizado y corre en CI:

```
uv run pytest .claude/tests/test_trampas.py -q
```

Cubre frontmatter, ids correlativos, `cerrada` sin guardia, `test:` que referencia
checks inexistentes, índice desincronizado y tamaño del índice. Si falla, arregla
eso antes de seguir: el resto de la auditoría no vale nada sobre un registro que
miente.

**Después lo que exige juicio**, que ningún test puede comprobar:

1. **Fichas sin guardia.** Toda ficha `vigente` o `mitigada` es deuda: un fallo
   conocido que nada impide reintroducir. Lístalas con lo que falta para cerrar,
   que está en su sección "Guardia", y estima cuánto cuesta ese test.

2. **Duplicación fuera del directorio.** Es la causa raíz de que el registro
   exista — una copia divergió y acabó enseñando una corrección falsa:

   ```
   grep -rn --exclude=trampas.md "autoincrement\|local naive\|El Perellonet\|sort_values\|idtramo" CLAUDE.md .claude/agents/ .claude/commands/
   ```

   Debe salir vacío. Punteros sí; contenido copiado no.
   (`--exclude` porque este mismo fichero contiene el patrón.)

3. **Trampas huérfanas en `docs/`.** Hallazgos descritos en la documentación que
   nadie ha fichado. `docs/05_hallazgos_primera_captura.md` es la mina: revisa su
   sección 5 ("Otros apuntes de calidad") contra el índice.

4. **Fichas estancadas.** `vigente` sin movimiento en más de un mes: o se cierra,
   o se acepta como riesgo conocido y se dice por qué en la ficha.

5. **Fichas que el código ya contradice.** Si una ficha describe un comportamiento
   de la fuente que el parser actual ya no ve, gana el código: marca la ficha como
   sospechosa de estar obsoleta en vez de asumir que sigue vigente.

Salida: una línea por hallazgo. Si el registro está sano, dilo en una línea.

## Si `$ARGUMENTS` describe una trampa: fichar

1. **Filtra por el criterio de admisión.** Entra solo si *un ingeniero
   competente, leyendo el código y la documentación de la fuente, lo volvería a
   hacer*. Typo, off-by-one, import olvidado, cualquier cosa que salga en el
   stack trace: **no entra**. Dilo y redirige a `gh issue create`.

   La prueba práctica: intenta escribir la sección "Por qué se vuelve a caer
   aquí". Si no sale, no era una trampa.

2. **Comprueba que no está ya fichada.** Puede ser una cara nueva de una trampa
   existente; entonces se amplía la ficha, no se crea otra.

3. Coge el siguiente `id` libre y crea
   `.claude/trampas/NNN-<slug-kebab>.md` con el frontmatter completo (`id`,
   `titulo`, `estado`, `capa`, `detectada`, `test`) y las cuatro secciones fijas:
   Síntoma, Causa, Por qué se vuelve a caer aquí, Guardia.

   `capa`: `fuentes` · `tracking` · `etiquetado` · `pipeline` · `serving`.
   `estado`: `cerrada` solo si ya hay test. Si no, `mitigada` (hay workaround) o
   `vigente` (no hay nada), y la sección Guardia dice qué falta.

4. Añade la fila al índice del README, en orden de `id`.

5. Si la trampa nace de algo ya medido, **cita la fuente** (`docs/…` con sección,
   commit, o `fichero:línea`). Nada de números inventados: cada cifra de una
   ficha debe poder rastrearse.
