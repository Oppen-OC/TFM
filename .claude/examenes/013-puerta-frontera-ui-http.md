---
id: 013
tema: puerta · migrar la UI de Streamlit a NiceGUI
fecha: 2026-11-16
fuentes: CLAUDE.md (Arquitectura), src/project/ui/app.py, src/project/services/vivo.py, src/project/services/model_service.py, README.md (guion de la demo)
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · la frontera ui/ ──HTTP──> api/
<!-- concepto: frontera-ui-solo-http -->

NiceGUI no funciona como Streamlit: la página corre dentro de un servidor ASGI de
Python, de la misma familia que FastAPI. Eso tienta a montarla en el mismo
proceso que `api/` y llamar directamente a `services/vivo.py`, sin pasar por
HTTP. ¿Qué protege la frontera «`ui/` solo habla con la API por HTTP»? Y si se
cruza, ¿qué se rompe? ¿Daría la cara o pasaría en silencio?

**Respuesta:**

> los tests que ya existen

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada: la respuesta nombra algo que se rompería, pero no
dice qué protege la frontera ni por qué. Además, los tests seguirían en verde
aunque la UI importara `services/`. Pista: piensa en qué estado vive en memoria
dentro de `services/` y qué pasa si dos procesos lo tienen a la vez. Puntero:
`CLAUDE.md`, «`services/` es la única capa que carga el modelo», y en
`services/vivo.py` el ciclo de `CICLO_S` y el `Marcador`.

**Respuesta (ronda 2):**

> Si están en un puerto disttinso no sucederia nada

**Veredicto (ronda 2):** fallada

_Respuesta completa._

- **Qué protege.** Un solo dueño del estado. `api/main.py` construye en el
  `lifespan` un único `Servicio` (modelos cargados una vez) y un único `Vivo`:
  su caché de `CICLO_S`, su cerrojo y su `Marcador`, que congela la primera
  predicción de cada bus. Lo que enseña la UI es lo que responde `/vivo/...`, el
  mismo contrato Pydantic que ve cualquier cliente y que guarda `test_api`.
- **Puerto distinto es justo el caso malo.** Otro puerto es otro proceso. Si ese
  proceso importa `services/`, monta su propio `Vivo.desde_disco`: un segundo
  juego de modelos en memoria, un segundo ciclo releyendo el crudo cada 40 s y
  un **segundo `Marcador`**. Este congela cada predicción en otro instante, así
  que puntúa otras predicciones. La UI enseñaría un «modelo 7/9 · regla 6/9»
  distinto del de la API y del medido en la bitácora 064, **sin error**: dos
  cifras plausibles que no cuadran.
- **En el mismo proceso, en cambio, da la cara.** El ciclo tarda 30-40 s con el
  cerrojo cogido. Llamado de forma síncrona desde el bucle de eventos de NiceGUI,
  congela la página de todos los navegadores. Se ve, pero tumba la demo.
- **Aparte**, la UI arrastraría pandas, sklearn y XGBoost. La frontera también
  existe para que `ui/` no lo necesite.
