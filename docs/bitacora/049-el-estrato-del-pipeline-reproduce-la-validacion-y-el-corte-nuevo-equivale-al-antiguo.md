---
id: 049
titulo: Mover los estratos de la 192 al pipeline no cambia nada, porque la validación de la 048 sale idéntica en sus 324 valores, y el corte de tres fechas reproduce byte a byte las seis tablas y los cinco modelos sin tráfico; el estrato que decidirá la primaria es el prerregistrado
fecha: 2026-10-11
tipo: medicion
capa: pipeline
capitulo: metodologia
impacto: medio
estado: aceptado
evidencia: uv run python -m project.analysis.trafico_validacion (auditoria/resultados/trafico_validacion.json, commit f9becb8, comparado con 058d8d9); ensayo `dvc repro` con train_hasta 2026-09-20, test_desde 2026-09-21 y test_hasta 2026-10-04 (tarea 7 de docs/superpowers/plans/2026-10-11-fase2-trafico.md)
trampa: —
---

## Qué se observó

Para la fase 2 del ADR-024 se hicieron dos cambios. Los estratos de la capa 192
y la comparación con − sin pasaron de `analysis/trafico_validacion.py` al
pipeline (`evaluate.estratos_trafico` y `evaluate.con_menos_sin`), y el split
pasó de un corte a tres (`features.partir`). Dos comprobaciones dicen que
ninguno de los dos cambió el instrumento:

- **La validación de la 048 sale idéntica.** Se volvió a ejecutar
  `trafico_validacion` con los estratos importados de `evaluate.py`. El JSON
  coincide con el de 058d8d9 en los **324 valores** de los cuatro horizontes
  (2, 3, 5 y 10). Solo cambia una cosa: aparece la clave nueva `relativa`. La
  primaria en la validación (h = 5, más del 75 % del recorrido con sensor) sigue
  siendo la misma:

  | *h* | filas | MAE sin tráfico | con − sin | relativa | IC por viajes | IC por días |
  |---|---|---|---|---|---|---|
  | 5 | 225.235 | 55,96 s | −0,07 s | −0,13 % | [−0,12, −0,03] | [−0,14, 0,00] |
  | 10 | 159.201 | 87,46 s | −0,33 s | −0,38 % | [−0,43, −0,24] | [−0,68, −0,05] |

  Con *h* = 5, en conjunto, el efecto relativo es de −0,12 %. Donde la capa
  veía congestión al predecir, de −1,27 %.

- **El corte nuevo equivale al antiguo.** Se ejecutó `dvc repro` de punta a
  punta con las tres fechas fijadas en el corte de entonces: entrenamiento hasta
  el 20/09 y prueba del 21/09 al 04/10.
  - Las salidas de `disponibilidad`, `features` y `features_h@{2,3,5,10}` tienen
    en `dvc.lock` el **mismo md5** que en HEAD: seis tablas idénticas byte a
    byte.
  - Los cinco modelos sin tráfico se reentrenaron porque cambió su código, y sus
    cinco `eval.json` son idénticos salvo `mlflow_run_id`. El entrenamiento es
    determinista con la configuración del ADR-021.
  - Los cinco stages nuevos (`train_trafico*` y `evaluate_trafico*`)
    terminaron sin errores. Cada `trafico.json` tiene todas sus claves y una
    pareja de modelos con la misma validación (14-20/09). Ningún estrato quedó
    vacío.

## Cómo se midió

```bash
uv run python -m project.analysis.trafico_validacion   # ~2 h, 8 ajustes
```

```python
import json, subprocess
nuevo = json.load(open("auditoria/resultados/trafico_validacion.json", encoding="utf-8"))
viejo = json.loads(subprocess.run(
    ["git", "show", "058d8d9:auditoria/resultados/trafico_validacion.json"],
    capture_output=True, text=True, encoding="utf-8", check=True).stdout)
def sin_relativa(x):
    return {k: sin_relativa(v) for k, v in x.items() if k != "relativa"} if isinstance(x, dict) else x
assert sin_relativa(nuevo) == viejo                    # 324 valores
```

El ensayo es la tarea 7 del plan de la fase 2:
1. Se ponen en `params.yaml` las fechas del corte de entonces.
2. Se ejecuta `uv run dvc repro`.
3. Se comparan los `md5` de las salidas de cada stage en `dvc.lock` con los de
   `git show HEAD:dvc.lock`, y los `eval.json` con `git diff`.
4. Se restaura con `git checkout params.yaml dvc.lock metrics/` y
   `dvc checkout`.

Sus cifras sobre la prueba antigua no se commitearon: esa prueba ya estaba
contaminada.

## Por qué importa

- La primaria del ADR-024 se mide con el estrato que se fijó en la validación.
  Si al moverlo al pipeline hubiera cambiado algo, como un borde de banda, la
  regla del estado observado o la unidad de remuestreo, la prueba se habría
  medido con un estrato distinto del prerregistrado, y sin ningún error.
- El corte de tres fechas solo tenía que excluir días. Que reproduzca las tablas
  byte a byte con el corte antiguo demuestra que no mueve ni pierde filas.
- El determinismo del entrenamiento hace que con − sin dependa solo de las
  variables: la diferencia no es ruido de semilla ni de hilos.
- Deja también el **tamaño relativo** que el ADR-024 pide informar: en la
  validación, la primaria es un −0,13 % del error del modelo sin tráfico.

## Qué se hizo / qué queda abierto

Hecho:
- El JSON regenerado está commiteado (f9becb8).
- Mutantes 137-143 del corte y de la comparación, todos detectados.
- Antes de traer la prueba, la revisión final de la fase A añadió una guardia
  para el caso en que los dos modelos lleven la capa 192.

Abierto:
- La prueba del 07 al 19/10 se trae desde el 21/10 y se evalúa una sola vez
  (tareas 11-15 del plan).

## Para la memoria

> Antes de evaluar la aportación del tráfico sobre la prueba se comprobó que el
> instrumento de medida no había cambiado al integrarlo en el flujo
> reproducible. La estratificación por cobertura de sensores y la comparación
> entre el modelo con tráfico y el modelo sin él se trasladaron desde el
> análisis exploratorio con el que se fijaron. Al repetir aquel análisis con el
> código trasladado se obtuvieron los mismos 324 valores en los cuatro
> horizontes. En la validación, con un horizonte de cinco paradas y en las filas
> con más de tres cuartas partes del recorrido cubiertas por sensores, el tráfico
> reduce el error absoluto medio en 0,07 s, un 0,13 % del error del modelo sin
> tráfico. La partición temporal, redefinida con tres fechas para excluir los
> días incompletos posteriores al fallo del equipo de captura, se ejecutó con
> las fechas de la partición anterior. Reprodujo bit a bit las tablas de
> entrenamiento y prueba, y los modelos reentrenados dieron métricas idénticas,
> lo que confirma que el entrenamiento es determinista. La diferencia entre los
> dos modelos que se informe sobre la prueba responde, por tanto, solo a las
> variables de tráfico, medida con el estrato fijado antes de ver los datos.
