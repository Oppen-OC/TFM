---
id: 054
titulo: Al corpus le faltan 37,95 h por el fallo del disco de la Pi, no las 27 que dijo la 044. Las cinco fuentes saltan del 04/10 a las 23:59 al 06/10 a las 13:56 UTC. Las 27 h son lo que el colector estuvo parado; las otras 10,5 h se capturaron la mañana del 05/10 y se quedaron en el disco que falló, porque la copia al PC no trae el día en curso
fecha: 2026-10-14
tipo: medicion
capa: fuentes
capitulo: limitaciones
impacto: medio
estado: abierto
evidencia: uv run python -m project.analysis.medir_completitud --desde 2026-10-03 --hasta 2026-10-07
trampa: 016
---

## Qué se observó

El dashboard de la defensa sombrea en la parada P9 los cortes de captura de la
EMT de más de una hora. El del 04-06/10 mide **37,95 h**, y la bitácora 044, que
lo explica, dice «unas 27 h». No es un error de medida: son dos cosas
distintas.

| fuente | último sondeo antes | primero después | hueco |
|---|---|---|---|
| `emt_buses` | 04/10 23:59:42 UTC | 06/10 13:56:30 UTC | 37,95 h (2.277 min) |
| `trafico_estado` | 04/10 23:56:51 | 06/10 13:56:29 | 37,99 h |
| `valenbisi` | 04/10 23:56:52 | 06/10 13:56:30 | 37,99 h |
| `renfe_cercanias` | 04/10 23:59:42 | 06/10 13:56:30 | 37,95 h |

- **No hay partición `date=2026-10-05`** en el crudo del PC, en ninguna fuente.
- **Las 27 h de la 044 son el tiempo que el colector estuvo parado.** Por los
  contadores del journal se paró hacia las 10:30 UTC del 05/10, y volvió a las
  13:56 UTC del 06/10 (bitácora 050): unas 27,4 h.
- **Las otras ~10,5 h**, del 05/10 de 00:00 a ~10:30 UTC, se capturaron, pero
  se escribieron en el disco que dejó de leerse. Nunca llegaron al PC porque
  `deploy_pi/pull_data.sh` excluye a propósito la partición del día en curso
  (`--exclude="date=$HOY/"`, línea 48) para no copiar un fichero a medio
  escribir.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_completitud --desde 2026-10-03 --hasta 2026-10-07
```

Da los huecos de más de una hora por fuente sobre `data/raw` (crudo hasta el
12/10). Las cuatro fuentes de la tabla dan el mismo corte, a menos de 3 min. La
hora en que se paró el colector no sale del crudo: es la estimación de la 044
por los contadores. El instante de vuelta es el de la 050.

## Por qué importa

- **La memoria habría citado 27 h perdidas.** Al corpus le faltan 38, un 40 %
  más. El párrafo de la 044 («se perdieron unas 27 horas de datos») mezcla lo
  que duró la parada con lo que falta en el corpus.
- **La copia no trae el día en curso, y eso amplía cualquier fallo del equipo
  de captura.** Un fallo del disco pierde lo que no se capturó y además todo lo
  capturado desde la medianoche UTC anterior. El peor caso es casi un día
  entero de más. Es el mismo modo de fallo que la trampa 016: el corpus
  completo depende de en qué máquina está cada día.
- **No toca el modelo.** El entrenamiento y la prueba de la v2 terminan el
  04/10, y la prueba del ADR-024 empieza el 07/10.

## Qué se hizo / qué queda abierto

- El dashboard enseña la cifra del corpus (38 h en la sombra de P9). La 044 no
  se edita: esta entrada la corrige.
- **Abierto (heredado de la 044):** el diagnóstico del disco. Si `ddrescue`
  recupera la partición del 05/10, el hueco baja a unas 27 h, y esta entrada
  pasa a `resuelto` con la cifra nueva.
- **Abierto:** que el equipo de captura copie el día en curso a un segundo
  soporte (la SD o el PC) con más frecuencia que una vez al día, sin cambiar la
  regla de `pull_data.sh`, que tiene su motivo.

## Para la memoria

> El fallo del disco del equipo de captura dejó un hueco de 37,95 horas en el
> corpus, del 4 de octubre a las 23:59 al 6 de octubre a las 13:56 (UTC), igual
> en todas las fuentes. El colector solo estuvo detenido unas 27 de esas horas.
> Las otras diez y media, la madrugada y la mañana del 5 de octubre, se
> capturaron, pero quedaron en el disco averiado: la copia al equipo de análisis
> excluye el día en curso para no trasladar ficheros a medio escribir, y ese día
> no llegó a copiarse. Ese hueco no afecta a los periodos de entrenamiento y
> prueba del modelo, que terminan el 4 de octubre.
