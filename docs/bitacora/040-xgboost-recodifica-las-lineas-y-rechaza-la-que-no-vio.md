---
id: 040
titulo: XGBoost 3.2 guarda las categorías del entrenamiento y recodifica por valor, así que la línea con otro código no se lee como otra; lo que rompe es la línea que no vio, que tira la predicción entera con error, y la prueba trae una
fecha: 2026-10-06
tipo: tecnica
capa: pipeline
capitulo: metodologia
impacto: medio
estado: resuelto
evidencia: uv run pytest tests/test_modelo.py::test_predict_reutiliza_las_categorias_guardadas_con_el_modelo; uv run python auditoria/mutar.py --solo 104
trampa: —
---

## Qué se observó

El ADR-019 fijó las categorías de `linea` en el entrenamiento
(`features.categorias_linea`) y las aplica `features.matriz`. La razón escrita
era que pandas numera las categorías por las que ve en cada tabla, así que una
tabla con una sola línea la codificaría como 0 y el modelo leería otra línea
sin error (mutante 099). Se escribió antes de instalar XGBoost.

Con XGBoost 3.2.0 no pasa. El modelo entrenado con una `linea` categórica
guarda sus categorías y, al predecir sobre un `DataFrame`, recodifica la
entrada por valor. Un modelo con `A = 0, B = 100, C = 200` predice 200 para
una tabla que solo trae la C, aunque pandas la numere 0. El mutante 104, que
hace que `predict` recalcule las categorías con la tabla que recibe, salió
**equivalente**: el test de entonces no caía.

Lo que sí rompe es una línea que el entrenamiento no vio. Con las categorías
de la tabla, XGBoost la rechaza y la predicción entera falla con
`Found a category not in the training set`. Con las categorías fijadas, la
línea queda nula y el modelo la trata como dato faltante. La prueba tiene una
línea así, la **8**: 314 filas y 22 viajes, grupo `sin_entrenamiento` en
`metrics/features.json`. Sin las categorías fijadas, `evaluate` no habría
terminado.

## Cómo se midió

```bash
uv run pytest tests/test_modelo.py::test_predict_reutiliza_las_categorias_guardadas_con_el_modelo
uv run python auditoria/mutar.py --solo 104
```

El test entrena con las líneas A, B y C y predice sobre 50 filas de la C más 5
de una línea Z. Exige que la C dé lo mismo sola que mezclada, que pase de 150 s
y que la Z tenga predicción. Con el mutante 104 aplicado a mano cae con
`XGBoostError` en la Z.

## Por qué importa

- **El riesgo de la línea leída como otra sigue existiendo si cambia la
  frontera.** Un servicio que pase `numpy` o un `DMatrix` con los códigos ya no
  se beneficia de la recodificación. `features.matriz` no depende de que la
  librería lo haga.
- **El riesgo real es ruidoso, no silencioso, pero tira todo.** Una petición o
  una evaluación con una línea nueva falla entera, y en la prueba ya hay una.

## Qué se hizo / qué queda abierto

Hecho:
- El test añade la línea nueva y el mutante 104 lo pone rojo.
- Se corrigieron el texto de ADR-019, los docstrings de `features.matriz` y de
  `predict` y los comentarios de los mutantes 099 y 104.

Abierto: nada. Si se cambia de versión de XGBoost, se vuelve a ejecutar la
auditoría, como pide el ADR-011.

## Para la memoria

> La línea entra al modelo como variable categórica con las categorías fijadas
> en el entrenamiento, que se guardan junto al modelo. La versión de XGBoost
> empleada (3.2) ya conserva esas categorías y recodifica la entrada por su
> valor, de modo que una línea conocida se interpreta correctamente aunque la
> tabla la codifique de otra forma. Sin embargo, una línea ausente del
> entrenamiento provoca un error que impide predecir sobre el conjunto
> completo, y el periodo de prueba incluye una (la línea 8, con 22 viajes).
> Fijar las categorías hace que esa línea se trate como dato faltante y que el
> resultado no dependa del comportamiento de la librería.
