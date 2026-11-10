---
id: 011
tema: puerta · demo en vivo por parada, sondeo repetido en el ciclo
fecha: 2026-11-10
fuentes: docs/superpowers/specs/2026-11-10-demo-parada-en-vivo-design.md, src/project/ingest/reprocesar.py, src/project/ingest/collect.py (recordar), src/project/tracking.py (rastrear), docs/bitacora/019, .claude/trampas/011-primera-captura-puede-ser-bloque-a-medias.md
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · un sondeo repetido en el ciclo en vivo
<!-- concepto: clave-sondeo-compartida-colector-reprocesar -->

En la demo, cada ciclo lee el crudo que escribe el colector del PC. Supón que la
EMT sirve el mismo sondeo dos veces seguidas, las dos capturas llegan al crudo y
el ciclo no las reconoce como el mismo sondeo. ¿Qué le pasa en la tabla que ve
tu tutor al bus afectado (si sale, desaparece, o con qué retraso), en qué
función del pipeline se origina, y por qué nadie vería un error?

**Respuesta:**

> La tabla movería el temporizador de minutos pero la información de los buses
> seguiría representando la información anterior, la mayoría de buses estarían
> "retrasados" aunque sea por culpa de la api y no la realidad. No se vería un
> error porque no existe un guardarraíl para datos duplicados servidos en
> momentos distintos.

**Veredicto:** fallada

_Rondas._ Ronda 1, fallada. Las dos capturas son el mismo sondeo: mismas
posiciones y mismo instante de la fuente. No son datos viejos con hora nueva, así
que no hay ningún «retraso por culpa de la API». Sigue esas dos copias idénticas
hasta `tracking.rastrear`: ¿qué puede hacer el tracker con una posición que ya ha
emparejado? La tabla de la bitácora 019 da la cifra. Después piensa qué necesita
una trayectoria para tener horario (decisión 9 del diseño). La tercera parte
tampoco encaja: el guardarraíl existe. Busca qué usan `collect.recordar` y
`reprocesar` para decidir que dos capturas son el mismo sondeo, y qué pasa si el
ciclo de la demo no lo usa.

**Respuesta (ronda 2):**

> El recolector es capaz de detectar ingestas duplicadas, lo que hace es borrar
> la ingesta anterior y volver a procesar los datos.

**Veredicto (ronda 2):** fallada

_Respuesta completa._

- **Qué ve el tutor.** La segunda copia trae posiciones idénticas a la primera,
  y el tracker no puede emparejar dos veces la misma posición: arranca vehículos
  nuevos. La trayectoria del bus se parte. El 27/08, un 2,5 % más de filas dio un
  53 % más de trayectorias (bitácora 019). El trozo que empieza tras la copia no
  tiene las tres primeras paradas del viaje, así que no recibe horario: el bus
  **desaparece** de la tabla o reaparece sin su historia, y su predicción
  congelada no se verifica nunca. No sale «retrasado».
- **Dónde se origina.** En `tracking.rastrear`, la identidad. Se propaga a
  `etiquetado`, que no puede asignarle viaje.
- **Por qué no hay error.** Cada trozo es una trayectoria plausible y nada
  falla. El guardarraíl es `clave_sondeo` (`ingest.sources`), la misma función
  en el colector y en `reprocesar`. Ninguno borra nada: el crudo guarda todas las
  capturas; el colector se queda la primera (`collect.recordar`) y `reprocesar`,
  la que trae más filas (trampa 011). Un ciclo que lea el crudo sin
  `clave_sondeo` se salta ese guardarraíl.
- **Para la demo.** El ciclo en vivo elige las capturas con `clave_sondeo` y la
  regla de `reprocesar`, como pide el diseño.

