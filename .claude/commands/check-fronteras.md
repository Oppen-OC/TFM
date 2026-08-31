---
description: Audita las violaciones de la arquitectura del repo (dirección de dependencias, config, aislamiento de demo/)
---

Audita el repositorio contra las reglas duras de arquitectura. Cada una tiene una
comprobación mecánica: córrelas todas y reporta lo que salte.

## Las siete comprobaciones

1. **`ui/` no importa `services/` ni carga el modelo.** Habla con la API por
   HTTP. Si Streamlit necesita algo nuevo, se añade un endpoint, no un import.

   ```
   grep -rnE "^\s*(from|import)\s+(project\.)?(services|predict|train|features)" src/project/ui/
   ```

2. **`api/` no contiene lógica de negocio.** Sin sklearn, pandas, numpy ni
   xgboost. Los routers validan con Pydantic y delegan en `services/`.

   ```
   grep -rnE "^\s*(from|import)\s+(sklearn|pandas|numpy|xgboost|joblib)" src/project/api/
   ```

3. **`services/` es la única capa que carga el modelo**, y lo mantiene en memoria
   (carga única al arranque, no por request).

   ```
   grep -rnE "joblib\.load|pickle\.load|\.load_model" src/project/ --include=*.py
   ```

   Solo debe aparecer en `services/model_service.py`.

4. **Nada de `os.getenv` fuera de `config.py`.** Todo ajuste sale de Pydantic
   Settings.

   ```
   grep -rn "os\.getenv\|os\.environ" src/project/ --include=*.py
   ```

5. **`src/project/` no importa de `demo/`, ni al revés.** La separación es
   deliberada; si se rompe, el prototipo deja de ser prototipo.

   ```
   grep -rn "import demo\|from demo" src/
   grep -rn "import project\|from project" demo/
   ```

6. **Sin rutas hardcodeadas.** `MODEL_PATH` y las rutas de datos vienen de
   settings.

   ```
   grep -rnE "[\"'](data|models)/" src/project/ --include=*.py
   ```

7. **`config.py` y `.env.example` están sincronizados.** `.env.example` es la
   fuente de verdad de qué variables existen. Compara los campos de `Settings`
   contra las claves del ejemplo, en ambas direcciones.

## Extras si hay diff pendiente

- Que no se esté commiteando `data/`, `models/*.pkl`, `.env`, `dvc.lock` editado
  a mano ni `uv.lock` editado a mano.
- Que no haya CSV en `data/interim/` ni `data/processed/`: Parquet, siempre.

## Salida

Una línea por violación, con `fichero:línea` y la regla que rompe. Sin proponer
refactors de estilo y sin tocar nada. Si todo está limpio, dilo en una línea.
