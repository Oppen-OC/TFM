---
id: 062
titulo: Renfe omite la clave sin valor en vez de mandarla a null, y los 254 errores de parseo de `curar.json` eran respuestas con uno a tres trenes en toda España y ninguno de València, la mitad de día en cinco episodios de fuente degradada
fecha: 2026-10-28
tipo: anomalia
capa: fuentes
capitulo: calidad-dato
impacto: bajo
estado: resuelto
evidencia: uv run python -m project.analysis.medir_claves_renfe --raw C:/Users/oppen/Code/TFM/data/raw (crudo del 15/08 al 20/10)
trampa: 019
---

## Qué se observó

Sobre los 176.642 payloads de Renfe del crudo, con 34.721.435 trenes, de los
cuales 2.237.180 son del núcleo 40:

- **Renfe nunca manda una clave a null: la omite.** No hay ningún null
  explícito en las 14 claves que lee el parser. Faltan tres:

  | clave | trenes sin ella | de València | % de los de València |
  |---|---|---|---|
  | `porAvanc` | 639.074 | 239.474 | 10,70 % |
  | `codEstDest` | 27.510 | 259 | 0,01 % |
  | `codEstOrig` | 5.825 | 0 | 0 % |

  Las otras once no faltan nunca.
- **Los 254 errores de `curar.json` son los payloads en que una clave falta en
  toda la flota**, de modo que la columna no existe. Hay exactamente uno por
  payload: `codEstDest` 154, `porAvanc` 97 y `codEstOrig` 3. Caen en 27
  particiones del crudo, 26 días en hora local, del 17/08 al 18/10.
- **La flota era mínima.** 239 de esos payloads traen 1 tren de toda España,
  14 traen 2 y uno trae 3. Ninguno es del núcleo 40.
- **Hay dos tipos de episodio** (hora local):
  - **De madrugada (126).** Están todos los de `porAvanc` y `codEstOrig`,
    más 26 de `codEstDest`. Desde el 05/09 se repite el mismo patrón: 13
    noches, todas de sábado, domingo o festivo (el 12/10), de 03:41 a 03:56,
    con un único tren en toda la flota y sin `porAvanc`.
  - **De día (128, todos de `codEstDest`).** Caen en cinco episodios en que
    `flota.json` sirvió uno o dos trenes para toda España:

    | día | de | a | payloads | trenes |
    |---|---|---|---|---|
    | 19/08 | 04:51 | 09:39 | 39 | 1 |
    | 26/09 | 10:56 | 14:55 | 33 | 1 |
    | 28/09 | 09:00 | 10:27 | 14 | 1 |
    | 30/09 | 08:33 | 10:40 | 19 | 2 |
    | 03/10 | 09:17 | 14:28 | 42 | 1 |

    `medir_completitud` ya los daba como huecos de Renfe, en UTC: el 28/09,
    dentro del hueco de 27/09 21:49 a 28/09 08:35; el 30/09, de 06:33 a 08:48;
    y el 03/10, de 07:16 a 12:36. El del 26/09 es el que recoge la 061.

## Cómo se midió

```bash
$env:PYTHONUTF8 = "1"
uv run python -m project.analysis.medir_claves_renfe --raw C:/Users/oppen/Code/TFM/data/raw
```

`medir_claves_renfe` cuenta sobre el JSON crudo, sin pasar por el parser:
- trenes sin cada clave y trenes con la clave a null;
- los payloads en que una clave falta en toda la flota;
- esos payloads agrupados en episodios, si los separan menos de 30 min.

**El instrumento se contrastó con otro independiente.** Se volvió a parsear
cada payload con el parser anterior al arreglo (`git archive 4d71dac src`,
`parse` dentro de un `try`), anotando la excepción y el instante. Salieron los
mismos 254 payloads, instante a instante, y todos eran `KeyError` de la clave
ausente.

**Efecto del arreglo** (1094871, 2dcb177):
- Con el crudo de los 27 días, el código viejo y el nuevo dan los mismos 127
  Parquet, idénticos byte a byte en las cinco fuentes.
- `dvc repro curar` deja `data/curated` en el mismo md5, `c3c687f6…dir`, y los
  errores de Renfe pasan de 254 a 0 (f7a2bda).

## Por qué importa

- **Esta vez no se perdió nada.** Ningún payload con error traía trenes de
  València, y el curated no cambia. Pero el mecanismo era silencioso:
  - `reprocesar` y el colector capturaban la excepción.
  - Los 254 se acumularon desde agosto en un contador agregado que el
    pipeline no lee.
  - Con un tren de València en un payload así, el sondeo entero se habría
    descartado igual de callado.
  - Salió a la luz porque `medir_completitud`, que no captura la excepción, se
    cayó (issue #4).
- **La columna solo desaparece cuando la flota es mínima.** Con cientos de
  trenes siempre hay alguno que trae la clave. Por eso no se ve en ninguna
  muestra diurna ni en el fixture.
- **Cuatro episodios caen entre las 8 y las 15 h**, y el del 19/08 llega
  hasta las 09:39. Son huecos en Renfe que no son de madrugada ni del colector:
  la fuente se degrada y sirve uno o dos trenes para todo el país. Para Renfe
  como fuente de etiquetas (plan B), son entre una hora y media y cinco horas
  sin dato.
- **A uno de cada diez trenes de València le falta `porAvanc`.** Cualquier uso
  de ese campo tiene que tratar la ausencia como un valor, no como un error.
- **Cada error del parser activaba el retroceso del colector** (issue #5), que
  espaciaba el crudo siguiente (bitácora 061).

## Qué se hizo / qué queda abierto

**Hecho:**
- `parse_renfe` completa a nulo las 13 claves que lee, tras filtrar el núcleo.
  `nucleo` sigue siendo obligatoria. Commits 1094871 y 2dcb177.
- Guardias: los tests de `tests/test_ingest.py` y los mutantes 195-197. Ficha
  de trampa 019.
- `docs/01` decía que `porAvanc` toma `null`; corregido.
- `curar` re-firmado en f7a2bda.

**Abierto:**
- El retroceso ante errores del parser (#5).
- El tipo de una columna que falta un día entero no se fija: saldría `null` o
  `double`. Está marcado con `ponytail:` en `sources.py`.
- Nada avisa de los episodios de flota degradada. Se ven como huecos en
  `medir_completitud`, y de día `collect --status` los daría por caída pasados
  30 min (061).

## Para la memoria

> La fuente de Cercanías no publica como nulo un campo sin valor: lo omite del
> registro del tren. En los 34,7 millones de registros capturados entre el 15
> de agosto y el 20 de octubre no apareció ningún nulo explícito, mientras que
> al 10,7 % de los 2,24 millones de registros de trenes de València les
> faltaba el indicador de avance. Cuando ningún tren del país trae un campo,
> este desaparece de la respuesta, y el procesamiento, que esperaba un
> conjunto fijo de campos, la rechazaba entera. Ocurrió en 254 de las 176.642
> respuestas (0,14 %), siempre con uno a tres trenes en toda la red y ninguno
> de València, de modo que no se perdió ningún dato del núcleo estudiado. 126
> de ellas se produjeron de madrugada; las otras 128, en cinco episodios
> diurnos de hora y media a cinco horas en que la fuente sirvió uno o dos
> trenes para todo el país. Los rechazos se contaban sin que nada los
> señalara, y con trenes de València habrían eliminado observaciones válidas
> sin aviso. Tras adaptar el procesamiento para tratar el campo ausente como
> vacío, la reconstrucción completa de los datos depurados resultó idéntica,
> byte a byte, a la anterior.
