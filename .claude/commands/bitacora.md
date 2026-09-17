---
description: Ficha un hallazgo en la bitácora del TFM, verificando la cifra antes de escribirla
argument-hint: [descripción del suceso, o vacío para solo auditar]
---

Registro: `docs/bitacora/`. Su índice y el formato completo están en
`docs/bitacora/README.md`. Léelo antes de escribir; no dupliques aquí sus campos.

## Si `$ARGUMENTS` está vacío: auditar

**Primero lo mecánico:**

```
uv run pytest .claude/tests/test_bitacora.py -q
```

Cubre frontmatter, ids correlativos, las cinco secciones, `evidencia` no vacía,
`trampa:` que apunta a ficha existente e índice sincronizado. Si falla, arregla
eso antes de seguir.

**Después lo que exige juicio:**

1. **Cifras que ya no se sostienen.** Toda entrada declara en `evidencia` un
   comando. Reejecuta los baratos y compara con lo escrito. Una cifra que ya no
   sale es peor que ninguna: la memoria la citará igual.
2. **Entradas `abierto` estancadas.** Más de un mes sin movimiento: o se cierra,
   o se convierte en limitación declarada y se dice por qué.
3. **Hallazgos sin fichar.** Barre `docs/05_hallazgos_primera_captura.md`,
   `docs/06_veredicto_capas_trafico.md` y los commits recientes buscando cifras
   medidas que nadie haya recogido.
4. **Cobertura por capítulo.** Agrupa por `capitulo:` y di cuál va vacío. Un
   capítulo de la memoria sin entradas es un capítulo que habrá que escribir de
   memoria en febrero.
5. **Solapamiento con los otros registros.** Ninguna entrada debe copiar el
   contenido de una ficha de `.claude/trampas/` ni de un ADR de
   `docs/07_decisiones.md`: punteros sí, contenido no.

Salida: una línea por hallazgo. Si el registro está sano, dilo en una línea.

## Si `$ARGUMENTS` describe un suceso: fichar

1. **Encamina.** La tabla de `docs/bitacora/README.md` manda:

   - bug silencioso que un ingeniero competente repetiría → `/trampas`
   - decisión estructural con alternativas → `docs/07_decisiones.md`
   - typo, off-by-one, visible en el stack trace → `gh issue create`
   - cifra medida, anomalía, hipótesis descartada, límite del alcance → sigue

   Si es trampa **y además** hallazgo, van los dos: la ficha explica el bug, la
   entrada explica lo que se aprendió. Cruce por el campo `trampa:`.

2. **Verifica antes de escribir.** Esta es la razón de que el comando exista;
   sin este paso escribes una anécdota con decimales.

   - Localiza el código y los datos que producen la cifra.
   - **Comprueba el instrumento antes que lo medido.** La trampa
     [004](../trampas/004-sort-inestable-en-snapshot.md) reportó un 11 % que era
     un 99 %: el bug estaba en el arnés de medida. Ante una cifra sorprendente,
     la primera hipótesis es que el medidor miente.
   - Reprodúcela con un comando reejecutable. Si el hallazgo no tiene medidor,
     escríbelo en `src/project/analysis/` — no en el directorio temporal, o la
     entrada nace sin evidencia. Si el medidor necesita datos con verdad-terreno,
     parte de `src/project/analysis/simulacion.py`; no dupliques el generador.
   - Si no consigues reproducirla, la entrada nace `estado: abierto` diciendo
     "no reproducido" de forma explícita. Nunca con la cifra a pelo.

3. **Cuantifica el efecto, no solo el síntoma.** Pregúntate en qué unidad hay que
   contarlo: la 001 existe porque el porcentaje por posición se diluye mientras
   el daño real crece. Si algo se acumula, muestra cómo escala. Si contamina
   aguas abajo, di qué fracción y de qué.

4. **Escribe la entrada.** Siguiente `id` libre,
   `docs/bitacora/NNN-<slug-kebab>.md`, frontmatter completo y las cinco
   secciones del README. La quinta —**Para la memoria**— se escribe en prosa
   académica en tercera persona, con las cifras dentro y sin jerga de repo: se
   pega tal cual en el capítulo que dice `capitulo:`. Las otras cuatro son notas
   de trabajo y pueden hablar de ficheros y funciones.

5. **Añade la fila al índice** del README, en orden de `id`.

6. **Cierra el bucle.** Si la entrada deja algo abierto que un test podría
   guardar, dilo en una línea al terminar, con el nombre del test que faltaría.
