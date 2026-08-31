---
description: Añade un stage al pipeline de DVC con sus params y su script, en el sitio correcto
argument-hint: <nombre-del-stage>
---

Añade el stage `$1` al pipeline. Un script de entrenamiento o de transformación
sin stage en `dvc.yaml` es un error: DVC gobierna el pipeline, no los scripts
sueltos.

## Antes de escribir nada

Comprueba que `$1` **es** un stage legítimo. La ingesta no lo es y no puede
serlo: capturar un stream en vivo no es idempotente ni reejecutable, que es justo
lo que DVC asume de cada stage. Si `$1` captura datos en vivo, para aquí y dilo.

## Pasos

1. Decide dónde encaja `$1` en la cadena `prepare → features → train → evaluate`
   y qué stages pasan a depender de él.

2. Añade el stage a `dvc.yaml` con los cuatro campos declarados:
   - `cmd:` — `uv run python -m project.$1`
   - `deps:` — datos de entrada **y** los ficheros `.py` de los que depende
   - `params:` — la clave `$1`
   - `outs:` — salidas en Parquet (o `metrics:` con `cache: false` si son
     métricas)

3. Añade la clave `$1` a `params.yaml`, con el mismo nombre y con comentarios que
   expliquen cada hiperparámetro. Los stages viven en `dvc.yaml` y los
   hiperparámetros en `params.yaml`; hasta 08/2026 estaban al revés y `dvc repro`
   no ejecutaba nada. No volver a moverlos.

4. Crea el esqueleto `src/project/$1.py`: lee params desde `params.yaml`,
   escribe Parquet (nunca CSV), y registra en MLflow si entrena algo.

5. Verifica que el stage realmente dispara:

   ```
   uv run dvc dag
   uv run dvc repro $1
   ```

   Un stage que no se ejecuta está mal declarado. Ese es el fallo a cazar aquí.

## No hagas

- Editar `dvc.lock` a mano.
- Commitear `data/` ni `models/*.pkl`: los versiona DVC.
- Introducir un split aleatorio. El split es temporal, siempre.

## Salida

El diff de `dvc.yaml` y `params.yaml`, el esqueleto creado, y qué stages quedan
invalidados por el nuevo nodo del grafo.
