# Exámenes

Interrogatorio del **conocimiento del repo ya escrito**. Existe porque buena parte
de `tracking.py`, `analysis/` y los medidores los tecleó el agente: el examen
fuerza a reconstruir en voz alta el porqué de decisiones que no tomaste tú.

No es documentación ni revisión de código. No se ejecuta nada, no se decide nada.

## Qué se pregunta y qué no

**Esta sección manda.** El comando la aplica; no la copia.

Se pregunta por **temas amplios y decisiones de diseño**:

- por qué esta decisión y no la alternativa obvia, y qué se probó antes;
- qué se rompe aguas abajo si se cambia, y si el daño da la cara o no;
- por qué una cifra medida es un suelo o un techo y no el valor real;
- qué invalidaría un resultado, y cómo lo verías venir;
- qué protege una frontera de la arquitectura, y qué pasa el día que se cruza;
- por qué una trampa vuelve a morder aunque el código parezca correcto;
- qué compromiso se aceptó, contra qué alternativa, y bajo qué condición se
  reabre.

**No se pregunta detalle de código.** Fuera, sin excepción:

- qué devuelve una función, su firma, sus parámetros, su valor por defecto;
- el valor de una constante o el nombre de una columna;
- en qué fichero o línea vive algo;
- nombres de funciones, clases o variables;
- recitar los pasos de un algoritmo sin exigir el porqué de cada uno.

Dos filtros, y la pregunta tiene que pasar los dos:

1. **Si la respuesta cabe en un `grep`, no es pregunta.** Mide navegación, no
   comprensión.
2. **Si la respuesta correcta no contiene un "porque", no es pregunta.** Una
   respuesta que solo describe *qué* pasa está incompleta por construcción.

Una pregunta puede *partir* de un detalle concreto —una puerta, un umbral, una
cifra— siempre que lo que pida sea la razón de que esté ahí y no en otro sitio.

## Formato

Un fichero por tanda: `NNN-<tema>.md`, id correlativo de tres dígitos.

```yaml
id: 001                  # correlativo, tres dígitos, coincide con el nombre
tema: tracking           # tema, ruta o id de ficha que originó la tanda
fecha: 2026-09-04        # YYYY-MM-DD de generación
fuentes: src/project/tracking.py, trampas/007, trampas/008
estado: en-blanco        # en-blanco | contestado | corregido | cerrado
ronda: 1                 # 1 o 2; no hay tercera
nota: —                  # correctas/total tras la última corrección
```

Un bloque por pregunta, en este orden exacto:

```markdown
## P1 · puerta física
<!-- concepto: puerta-fisica-vs-coste -->

La puerta `min(SALTO_MAX_M, VEL_MAX_KMH·dt)` y el coste del Hungarian no pueden
compartir matriz. ¿Por qué, y qué se colaba mientras la compartían?

**Respuesta:**

**Veredicto:** —
```

El `concepto:` es el identificador estable que cruza con el registro de
debilidades. Kebab-case, describe la idea, no la pregunta: una idea admite muchas
preguntas distintas y esa es justo la mecánica que hace falta.

**La clave no se escribe nunca en el fichero.** Ni al final, ni oculta, ni en
comentario. Si está escrita, se lee. Al corregir se releen las `fuentes:` y se
juzga en fresco — que además evita consolidar una respuesta que envejece cuando
el código cambia debajo.

## Rúbrica

| veredicto | significa |
|---|---|
| `correcta` | reconstruye el porqué, aunque el vocabulario no sea el del repo |
| `a-medias` | acierta el qué y falla el porqué, o le falta la consecuencia |
| `fallada` | razonamiento incorrecto, o en blanco |
| `—` | sin corregir todavía |

**`a-medias` cuenta como fallada** en el registro de debilidades. Sin esa dureza
el examen deja de discriminar y aprueba a quien no sabe.

## Ciclo de vida

`en-blanco` → contestas a mano → `contestado` → corrección → `corregido` o
`cerrado`.

- Ronda 1, fallo: **pista y puntero, nunca la respuesta.** Qué parte del
  razonamiento no encaja y dónde mirar. Reescribes en el mismo fichero, `ronda: 2`.
- Ronda 2, fallo: respuesta completa y el concepto entra a `debilidades.md`. No
  hay ronda 3: repetir la misma pregunta más veces mide paciencia.
- Todas `correcta` ⇒ `cerrado`.

**Discrepar con la corrección es señal, no fallo.** Si defiendes tu respuesta con
el código delante y tienes razón, eso va a `gh issue create` o a ficha de trampa.
No baja la nota: significa que la clave estaba mal.

## Registro de debilidades

`debilidades.md` es el único estado que sobrevive a la tanda. Los exámenes son
material de trabajo; el registro es lo que dirige la siguiente sesión.

| campo | qué es |
|---|---|
| `concepto` | id kebab-case, el mismo del comentario en el examen |
| `tema` | tema al que pertenece |
| `fallos` | veces `fallada` o `a-medias` acumuladas |
| `aciertos limpios` | veces `correcta` **a la primera**, en sesiones distintas |
| `último` | fecha del último movimiento |
| `estado` | `flojo` \| `dominado` |

`dominado` = 2 aciertos limpios en **sesiones distintas** y sobre **preguntas
distintas** del mismo concepto. Un acierto justo después de leer la corrección no
cuenta: mide memoria de cuarenta segundos.

## Autoridad de la clave

`src/` primero. Luego `.claude/trampas/` y `docs/bitacora/`, que es donde vive el
porqué. `docs/` en prosa al final. Si el código contradice a la documentación,
gana el código — y eso mismo es material de pregunta.

## Relación con los otros registros

Punteros sí, contenido no. Un examen **cita** una ficha de trampa o una entrada de
bitácora por su id; nunca reproduce su texto, o la copia diverge.

No hay índice de exámenes: el listado del directorio ya lo es, y `debilidades.md`
es el índice del estado, que es lo único que se consulta.
