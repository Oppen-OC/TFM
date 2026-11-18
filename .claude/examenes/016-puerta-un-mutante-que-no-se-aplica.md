---
id: 016
tema: puerta · issues #3 y #11, mutar.py
fecha: 2026-11-17
fuentes: auditoria/mutar.py (aplicar, main), auditoria/catalogo.toml (013, 104), src/project/ingest/sources.py, trampas/002, ADR-011, issue #11
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · un mutante que no se aplica
<!-- concepto: mutante-invalido-no-es-evidencia -->

El mutante 013 invierte el signo de la latencia; su detector es el test de la
convención horaria (trampa 002, `cerrada`). Hoy no se aplica: su `buscar` sale
dos veces en `sources.py`, la tabla lo marca `invalido` y `mutar.py` acaba con
código 0. (1) ¿Por qué un `invalido` es peor que un `hueco` para lo que el TFM
afirma de sus guardias? (2) ¿Por qué un `buscar` que era único deja de serlo sin
que nadie toque el catálogo, y por qué volverá a pasar?

**Respuesta:**

> 1. porque es mas facil identificar un error de un dato faltante que uno
> invalido. 2. No lo se, ayudame

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: (1) no explica qué prueba cada veredicto y (2) en
blanco. Pistas. Para (1): un `hueco` es una medida —el mutante se aplicó, la
suite corrió y nada cayó—; pregúntate qué se midió en un `invalido`, qué exige
el README de trampas para que una ficha esté `cerrada`, y qué cree quien lee
«código 0». Para (2): `git log -S` con el `buscar` del 013 sobre `sources.py`
da el commit que añadió la segunda copia; mira qué hacía ese commit y qué ata,
en el catálogo, un mutante a su sitio en el código.

**Respuesta (ronda 2):**

> 1. Porque un valor invalido es mas dificil de catalogar como erroneo que un
> valor directamente hueco. 2. no lo se

**Veredicto (ronda 2):** fallada

_Respuesta completa._ `invalido` no es un valor peor que `hueco`. Es la
ausencia de una medida, y la ejecución la presenta como si fuera una medida.

- **(1) Qué prueba cada veredicto.** En un `hueco` el mutante se aplicó, la
  suite corrió y nada cayó: está medido que falta guardia, y la tabla lo dice.
  En un `invalido` el código no llegó a mutarse y no corrió ningún test contra
  la mutación, así que no hay evidencia en ningún sentido. Pero `mutar.py` sale
  con código 0, y quien lee la ejecución entiende «auditoría en verde». La
  trampa 002 sigue `cerrada` porque tiene guardia, y por ADR-011 un test en
  verde no demuestra que guarde nada hasta que un mutante lo pone en rojo.
  Desde c1c0b8b (07/11) ese mutante no se ejecuta, y por tanto la afirmación
  «la 002 está guardada» no se apoya en nada, sin aviso. Un `hueco` grita; un
  `invalido` con código 0 calla.
- **(2) Por qué deja de ser único y por qué volverá a pasar.** El catálogo ata
  un mutante a su sitio **solo por el texto literal** de `buscar`: ni línea ni
  función. Basta un commit que repita esa línea en el mismo fichero. c1c0b8b
  añadió la capa 157 y copió la fórmula de `latencia_s` en el parser de meteo
  (`sources.py:352`). En el 104, `predict.py` tiene la misma llamada a
  `features.matriz` en tres funciones: las añadieron 9444124 (clasificador,
  14/10) y a4b05a6 (SHAP, 28/10). Volverá a pasar porque el código crece así:
  cada fuente nueva calcula su latencia y cada salida nueva del modelo monta su
  matriz con el mismo idioma. Quien toca `sources.py` no abre
  `catalogo.toml`. El remedio no es estar atento. Es que la unicidad se
  compruebe sola: que un `invalido` haga fallar la ejecución, y un test barato
  que verifique en cada `pytest`, sin mutar nada, que todo `buscar` sale
  exactamente una vez.
