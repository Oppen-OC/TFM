---
id: 067
titulo: Cuatro de los 241 mutantes del catálogo habían dejado de aplicarse sin que nadie tocara el catálogo, dos de ellos los del crudo antes del parser; la auditoría entera no se ejecuta desde el 17/09 y hoy llevaría unas 8 h, no 40 min
fecha: 2026-11-18
tipo: anomalia
capa: pipeline
capitulo: metodologia
impacto: alto
estado: resuelto
evidencia: git show 2cc17cc:auditoria/catalogo.toml > cat.toml && uv run python -c "import sys,tomllib,pathlib; sys.path.insert(0,'auditoria'); import mutar; print(mutar.invalidos(tomllib.loads(open('cat.toml',encoding='utf-8').read())['mutante'], pathlib.Path('.')))" (sobre el src/ de 2cc17cc); uv run pytest .claude/tests/test_catalogo.py
trampa: 002
---

## Qué se observó

El issue #11 señalaba dos mutantes del catálogo cuyo `buscar` no aparecía
exactamente una vez en su fichero, el 013 y el 104. Medidos todos contra el
`src/` de develop en 2cc17cc, eran **4 de 241**:

| mutante | guarda | apariciones | lo rompió |
|---|---|---|---|
| 013 | signo de `latencia_s`, convención horaria (trampa 002) | 2 | c1c0b8b, 07/11: la capa 157 repite la expresión |
| 104 | `predecir` usa las categorías guardadas con el modelo | 3 | 9444124 (14/10) y a4b05a6 (28/10): clasificador y SHAP repiten la llamada |
| 027 | el colector guarda el crudo antes de parsear | 0 | 2201d67, 17/11: un comentario del issue #5 entre las dos líneas |
| 033 | `reprocesar` lee todo el crudo | 0 | 478cc80, 10/11: `elegir_capturas` reescribe la línea |

`mutar.py` marcaba estos mutantes como `invalido`, no ejecutaba la suite contra
ellos y salía con código 0.

**El instrumento antes que lo medido.** Ningún resultado guardado en
`auditoria/resultados/` (64 ficheros) contiene un `invalido`. La razón es que
desde el 17/09 todas las ejecuciones guardadas son subconjuntos con `--solo`: la
mayor auditoría entera registrada es la de 9269074, con 41 mutantes. La última
medida del 013, el 027 y el 033 es de ese día. La del 104 es del 06/10
(8f2a68f). El fallo era latente y se habría colado en la próxima auditoría
entera.

En la ejecución del 18/11 (eb2254a), cada mutante tarda **118-128 s** (mediana
122 s) con una suite de 428 tests. Los 241 llevarían unas **8 h**, frente a los
«~40 min» que documentaban `CLAUDE.md` y `auditoria/README.md`, una cifra de
cuando el catálogo tenía 41 mutantes.

## Cómo se midió

```bash
git show 2cc17cc:auditoria/catalogo.toml > cat.toml
uv run python -c "import sys,tomllib,pathlib; sys.path.insert(0,'auditoria'); import mutar; print(mutar.invalidos(tomllib.loads(open('cat.toml',encoding='utf-8').read())['mutante'], pathlib.Path('.')))"
# [('013', 2), ('027', 0), ('033', 0), ('104', 3)]
uv run pytest .claude/tests/test_catalogo.py    # hoy: 0 inválidos
```

`mutar.invalidos` aplica la misma regla que `aplicar`: cuenta las apariciones
del `buscar` con el salto de línea del fichero. El comando de `evidencia` lo
ejecuta con el catálogo de 2cc17cc. El `src/` no cambia entre 2cc17cc y la
fusión de esta rama, así que vale contra el árbol de trabajo. Los commits
culpables salen de `git log -S "<buscar>" -- <fichero>`. Las fechas de última
medida salen de recorrer los JSON de `auditoria/resultados/` y buscar esos ids.
Los segundos por mutante, de `mutantes_eb2254a.json`.

## Por qué importa

La trampa 002 está `cerrada` porque tiene guardia, y por ADR-011 un test en
verde no demuestra que guarde nada hasta que un mutante lo pone en rojo. Con el
013 sin aplicar, la afirmación «la 002 está guardada» llevaba dos meses sin
volver a medirse. El 027 y el 033 guardan la única capa que no se puede
arreglar después: si el colector parsea antes de guardar el crudo, un parser
roto pierde el dato para siempre.

Un `invalido` no es un `hueco`. El `hueco` es una medida: el mutante se aplicó,
la suite corrió y nada cayó. El `invalido` es la ausencia de una medida
presentada como una auditoría en verde. El catálogo se ata al código **solo por
el texto** de `buscar`, y el código crece repitiendo idiomas (cada fuente
calcula su latencia, cada salida del modelo monta su matriz), así que volverá a
pasar. Uno de los cuatro lo introdujo la sesión del issue #5 el día anterior,
sin aviso.

## Qué se hizo / qué queda abierto

En la rama `fix/mutar-issues-3-11`:

- Los cuatro `buscar` llevan contexto hasta salir una sola vez. Los cuatro
  vuelven a salir `detectado`, con su detector caído, en 2cc17cc y eb2254a.
- `mutar.py` comprueba todos los `buscar` antes de crear el worktree y sale con
  código 4. También sale con 4 si un id de `--solo` no está en el catálogo.
- `.claude/tests/test_catalogo.py` lo comprueba en cada CI. No puede ir en
  `tests/`: `mutar.py` corre esa suite sobre el código mutado.
- El JSON guarda `completo` y `solo` (issue #3).
- Corregido el «~40 min» de `CLAUDE.md` y `auditoria/README.md`.

**Abierto:** la auditoría entera no se ha ejecutado contra el catálogo actual.
Unas 8 h, para una noche.

## Para la memoria

> La validación de las pruebas por mutación dirigida depende de que cada mutante
> se aplique sobre el código que pretende romper. En este trabajo el catálogo
> localiza cada mutante por el texto literal de la línea que sustituye, y en
> noviembre de 2026 una comprobación sistemática encontró que 4 de sus 241
> mutantes habían dejado de aplicarse sin que el catálogo se hubiera modificado.
> En dos casos, otro cambio había repetido la misma expresión en el mismo módulo.
> En los otros dos, la había reescrito. Entre ellos estaban los dos mutantes que
> verifican que el colector conserva la respuesta cruda antes de interpretarla, y
> el que respalda la guardia de la convención horaria. El ejecutor clasificaba
> esos casos como inválidos y terminaba sin error, de modo que una auditoría
> completa habría pasado por buena sin medir esas guardias. Se distinguió entre
> un mutante no detectado, que es una medida de la ausencia de protección, y un
> mutante no aplicado, que es la ausencia de medida. El ejecutor pasó a rechazar
> la auditoría entera ante cualquier mutante no aplicable, y la integración
> continua comprueba en cada cambio que todos se localizan de forma única. Los
> cuatro mutantes volvieron a ser detectados por las pruebas.
