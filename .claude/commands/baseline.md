---
description: Compara el modelo actual contra los baselines obligatorios (horario teórico y persistencia)
---

Compara el run vigente de XGBoost contra los dos baselines obligatorios. Ninguna
métrica se reporta ni se escribe en la memoria sin haber pasado por aquí.

## Los dos baselines

1. **Horario teórico** — predicción constante: retraso = 0. Es lo que hoy ve el
   usuario en la marquesina. Si el modelo no lo bate, el trabajo no aporta nada.
2. **Persistencia** — el retraso observado ahora se mantiene hasta la siguiente
   parada. Es el baseline duro: en series temporales suele ser sorprendentemente
   bueno, y batirlo es el resultado que defiende el TFM.

## Pasos

1. Evalúa los tres sobre **el mismo conjunto de test**, el que define
   `features.test_desde` en `params.yaml`. Split temporal, nunca aleatorio: con
   series de posiciones, un split aleatorio filtra el futuro y da métricas
   falsas.

2. Métricas de regresión sobre `retraso_siguiente_parada_s`: MAE, RMSE y P90 del
   error absoluto. La P90 importa: un retraso mal predicho en la cola es el que
   se nota.

3. Para la variante binaria (`retraso > features.umbral_retraso_s`): precisión,
   recall y F1, más la matriz de confusión. Reporta la tasa base de la clase
   positiva junto a ellas — sin eso, un F1 no se puede leer.

4. Desglosa por franja horaria (hora punta contra valle) y, si el volumen lo
   permite, por línea. El agregado esconde justo el caso que interesa: el modelo
   puede batir a persistencia solo en valle, que es cuando no hace falta.

5. Registra la comparación en MLflow, en el mismo experimento y con los baselines
   como runs propios. No la dejes solo en stdout.

## Cómo se reporta

Tabla de tres filas (horario teórico, persistencia, XGBoost) por métrica. Después
una frase clara: **¿bate el modelo a persistencia, y por cuánto?**

Si no la bate, esa es la conclusión y se escribe tal cual. Un resultado negativo
bien medido es defendible; uno maquillado no sobrevive a la primera pregunta del
tribunal.
