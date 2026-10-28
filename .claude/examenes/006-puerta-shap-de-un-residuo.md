---
id: 006
tema: puerta · plan de SHAP (docs/superpowers/plans/2026-10-15-shap.md)
fecha: 2026-10-28
fuentes: docs/07_decisiones.md (ADR-021), src/project/predict.py, docs/superpowers/specs/2026-10-15-shap-design.md
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · SHAP de un modelo de residuo
<!-- concepto: shap-de-un-modelo-de-residuo -->

La regresión v2 es de residuo (ADR-021). Supón que el beeswarm de la memoria
muestra que `retraso_s` tiene una contribución media |SHAP| pequeña. ¿Por qué
no puedes concluir de ahí que el retraso actual importa poco para predecir el
de la parada objetivo? ¿Y qué explican entonces, de verdad, esas
contribuciones?

**Respuesta:**

> porque falta el sesgo

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: el sesgo no distingue a un modelo de residuo de uno
que no lo es, porque lo tienen los dos; con él o sin él, la conclusión del
beeswarm seguiría siendo igual de falsa. Lo que falla es qué aprenden los
árboles en la v2 y por dónde entra `retraso_s` en la predicción final. Mira el
ADR-021 y cómo construye la predicción `predict.predecir`.

**Respuesta (ronda 2):**

> Porque esa es unicamente una metrica de las muchas que hay para verificar que
> tanto peso tiene una variable, el beeswarn no es una muestra global de todos
> los datos que existen y los que van a haber

**Veredicto (ronda 2):** fallada

_Respuesta completa._ Las dos razones que da valen para cualquier modelo, y por
eso no tocan lo propio de la v2. La muestra de 20.000 filas limita la precisión
de las medias, pero no provoca esta mala lectura. Los árboles de la v2 no
predicen el retraso, sino el residuo, ŷ − `retraso_s`. `predict.predecir` le
suma después `retraso_s` entero, con coeficiente 1, fuera de los árboles: es la
base. TreeSHAP (`pred_contribs`) reparte la salida de los árboles. Explica, por
tanto, cuánto se aparta la predicción de la persistencia y por qué, no el
retraso predicho. Un |SHAP| pequeño de `retraso_s` solo dice que la corrección
apenas depende del nivel de retraso actual: por ejemplo, poca regresión a la
media en los retrasos grandes. No dice que el retraso actual importe poco, porque
es el término más grande de la predicción y entra por construcción. La cuenta
cierra así: base (`retraso_s`) + sesgo + Σ contribuciones = ŷ. Por eso la API
devuelve `base` aparte, y por eso el sesgo solo, que tiene cualquier modelo, no
basta para cerrarla. Leer el beeswarm como importancia del retraso entero es el
error que el tribunal puede buscar en la figura.
