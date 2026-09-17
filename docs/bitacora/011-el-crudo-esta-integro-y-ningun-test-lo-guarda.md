---
id: 011
titulo: El crudo está íntegro —95.343 payloads, cero miembros gzip rotos— y la supuesta truncación era zcat parando en relleno de ceros; pero ningún test guarda la persistencia
fecha: 2026-09-17
tipo: medicion
capa: fuentes
capitulo: calidad-dato
impacto: alto
estado: mitigado
evidencia: uv run python -m project.analysis.auditar_persistencia
trampa: —
---

## Qué se observó

Sobre los 17 días capturados (15/08-31/08/2026) y las 5 fuentes:

| fuente | miembros íntegros | rotos | huecos de ceros | curados | perdidos al reprocesar | en partición ajena |
|---|---|---|---|---|---|---|
| emt_buses | 42.080 | 0 | 1 | 40.943 | 0 | 458 |
| renfe_cercanias | 40.464 | 0 | 3 | 30.649 | 0 | 0 |
| trafico_estado | 6.736 | 0 | 1 | 6.685 | 0 | 56 |
| trafico_intensidad | 1.833 | 0 | 1 | 1.819 | 0 | 10 |
| valenbisi | 4.230 | 0 | 1 | 4.206 | 0 | 27 |

Tres cosas:

1. **No hay pérdida.** Todo sondeo curado tiene su payload crudo, y `read_raw`
   devuelve el 100 % de los miembros íntegros.
2. **La nota `data/raw/_TRUNCADOS.txt` estaba mal medida.** Afirma que el fichero
   de la EMT del 24/08 solo tiene 2.400 payloads legibles y que Python se para
   igual que `zcat`. Con `zcat` son 2.400; con `gzip.open`, 2.819. Tras el
   miembro 2.400 no hay un miembro a medias sino **2.028 bytes a cero**. Los
   siete ficheros de la nota tienen exactamente ese patrón.
3. **551 sondeos están en la partición `date=` del día anterior**, todos
   capturados entre las 00:00 y las 00:29 UTC. Ninguno duplicado entre
   particiones.

Y la cifra que obligó a abrir la entrada: en la auditoría por mutación
([docs/11](../11_auditoria_tests.md)), **los 9 mutantes de la capa de
persistencia pasan la suite en verde**: parsear antes de guardar el crudo,
sobrescribir en vez de añadir, deduplicar mal, `reprocesar` leyendo un solo día.

## Cómo se midió

```bash
uv run python -m project.analysis.auditar_persistencia --csv auditoria/resultados/persistencia_fc5d15c.csv
uv run python -m project.analysis.auditar_persistencia --control "data/raw/source=emt_buses/date=2026-08-24/payloads.ndjson.gz"
uv run python auditoria/mutar.py --solo 027 028 029 030 031 032 033 034 035
```

`miembros()` recorre cada fichero miembro a miembro con `zlib` y CRC, y
resincroniza buscando la siguiente cabecera válida: cuenta lo que **hay** en
disco, independientemente de quién sepa leerlo. `legibles()` cuenta lo que ve
`gzip.open`. El instante se extrae del prefijo de cada línea para no parsear
850 MB de JSON; el `--control` comprueba que esa lectura rápida coincide con
`read_raw` sobre el fichero del 24/08 (2.819 frente a 2.819).

Contraste independiente de la cifra de la nota: `zcat ... | wc -l` da 2.400 y
`gzip -t` avisa de *trailing garbage ignored*. La cifra de la nota se reproduce;
lo que era falso es atribuírsela a Python.

## Por qué importa

El corpus no es recapturable. `reprocesar` es la única vía para corregir un
parser, y hasta hoy la documentación decía que ejecutarlo mutilaría siete días.
No lo hace, y eso desbloquea reprocesar si hace falta.

La partición ajena muerde aguas abajo: `medir_reales.cargar()` y cualquier
`prepare.py` que lea `date=X` como "el día X" se lleva media hora del siguiente
y pierde la suya. Afecta al 2 % de los sondeos de un día, en la franja de menos
servicio, pero es contaminación silenciosa en el sitio donde se construirán las
etiquetas.

Que ningún test guarde la persistencia es la parte grave: esta capa es la única
cuyo fallo no se puede reparar después.

## Qué se hizo / qué queda abierto

Hecho: medición y el instrumento `src/project/analysis/auditar_persistencia.py`.
Guardias en `tests/test_persistencia.py` (commit `c6e02cc`): los nueve mutantes
de persistencia caen. Corrección anexada a `data/raw/_TRUNCADOS.txt`.

Abierto:

- Decidir si la partición por primera fila de `flush` se corrige o se documenta
  como trampa; hoy basta con filtrar por `ts_ingest_utc`.
- Explicar la diferencia entre el 2,7 % de deduplicación medido en la EMT y el
  ~15 % del docstring del colector.

## Para la memoria

> La integridad del corpus crudo se verificó recorriendo los 95.343 payloads
> capturados entre el 15 y el 31 de agosto de 2026 miembro a miembro, validando
> la suma de comprobación de cada uno. No se encontró ningún miembro corrupto, y
> todos los registros del almacenamiento curado conservan su payload de origen,
> lo que garantiza que el corpus puede regenerarse íntegramente si se corrige un
> parser. Una inspección previa había estimado pérdidas en siete ficheros; la
> verificación mostró que la herramienta empleada interrumpía la lectura ante
> bloques de relleno nulo dejados por cortes de alimentación, mientras que el
> lector utilizado por el pipeline los omite correctamente. El episodio ilustra
> que la estimación de pérdidas depende del instrumento de lectura y debe
> contrastarse con el que usa el sistema real.
