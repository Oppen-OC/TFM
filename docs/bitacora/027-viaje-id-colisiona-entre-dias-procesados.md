---
id: 027
titulo: viaje_id no es único entre los días que procesa prepare: 932 se repiten entre particiones, 890 de ellos con líneas distintas, y 74 viajes programados se etiquetan dos veces
fecha: 2026-09-23
tipo: anomalia
capa: etiquetado
capitulo: metodologia
impacto: medio
estado: resuelto
evidencia: uv run python -m project.analysis.medir_rutas colisiones
trampa: —
---

## Qué se observó

Sobre la salida de `prepare` (32 particiones diarias, 221.073 tramos,
2.103.594 pasos):

| | |
|---|---|
| `viaje_id` repetidos | **932** (1.864 filas), todos en particiones distintas |
| de ellos, con líneas distintas | **890** |
| `trip_id` asignados dos veces el mismo día de servicio | **74** |
| pares (`viaje_id`, `stop_sequence`) repetidos en `pasos` | **657** |

Hora local de inicio de las filas repetidas: 1.291 entre la 01 y las 05 h, y
573 a las 14, 16, 18 y 22 h. Estas últimas son las primeras trayectorias de las
particiones incompletas, que arrancan a media tarde (15, 18 y 21/08 y 14/09,
entrada 022), y chocan con las de madrugada de la partición siguiente. Motivo
de las filas repetidas: 1.223 `corto`, 509 `asignado` y el resto rechazos.

Mecanismo, en tres piezas que por separado son correctas:

1. `rastrear` numera los vehículos desde `v00000` en cada llamada
   (`src/project/tracking.py:447`).
2. `prepare` llama una vez por día UTC (`cargar_dia`), que en verano corta a las
   02:00 locales.
3. `viaje_id = f"{vid}_{dia:%Y%m%d}_{k}"` usa el **día de servicio**, y una
   trayectoria que empieza antes de `HORA_CORTE` (04:00) pertenece al anterior
   (`src/project/etiquetado.py:58` y `:427`).

Así, el `v00003` de la partición del 16/08 que sale a las 02:00 lleva el día de
servicio 15/08, igual que el `v00003` de la partición del 15/08: el mismo
`viaje_id` para dos buses distintos. Además, el viaje físico que cruza las 02:00
se parte en dos llamadas, y las dos mitades pueden reclamar el mismo `trip_id`.
El desempate de conflictos (`etiquetado.py:488-495`) solo ve una llamada: el
viaje de la 19 que sale a las 01:38 del 16/08 (día de servicio 15/08) queda
asignado a `v00518` en una partición y a `v00003` en la siguiente.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_rutas colisiones
```

Lee `data/interim/{viajes,pasos}` con el nombre del fichero de cada fila, para
distinguir las particiones.

## Por qué importa

- Hoy no rompe nada: dentro de una llamada `viaje_id` es único, y nada une
  todavía entre particiones.
- **Lo romperá `features.py`**: el retraso de la parada anterior de un mismo
  viaje (el baseline de persistencia, y cualquier desfase temporal) se construye
  agrupando por `viaje_id`. Con la clave repetida, 932 viajes mezclan las
  paradas de dos buses de líneas distintas, sin error y con valores plausibles.
- Los 74 `trip_id` dobles son el mismo servicio contado dos veces, cada mitad
  con su propia asignación. Afecta a la madrugada: poco volumen, pero justo la
  franja nocturna que el etiquetado ya trata como caso especial.

## Qué se hizo / qué queda abierto

Hecho:

- **`prepare` procesa por día de servicio**, de las `HORA_CORTE` (04:00) a las
  04:00 locales del día siguiente, filtrando por `ts_utc`
  (`prepare.ventana_servicio`). A las 03:30-04:00 hay en servicio 0,2-0,8 buses
  por sondeo, y ningún viaje asignado cruzaba las 04:00, frente a 105 que
  cruzaban las 02:00. Toda trayectoria que empieza en la ventana es de ese día
  de servicio, así que la numeración por llamada vuelve a ser segura y el
  desempate de conflictos ve el viaje entero. Las particiones de
  `data/interim/` pasan a ser días de servicio.
- `procesar_dia` lanza un error si alguna posición sale con otro día de
  servicio: si la ventana y `HORA_CORTE` se desalinean, ya no pasa en silencio.
- Guardias: `test_cada_dia_de_servicio_se_procesa_entero_y_sus_claves_no_chocan`
  (un nocturno que cruza las 02:00, etiquetado por días y unido) y
  `test_la_ventana_de_servicio_va_de_corte_a_corte_en_hora_local` (23, 24 y 25 h
  en los cambios de hora; el de 25 h es el sábado 24/10, porque el cambio cae
  antes del corte). El mutante 074, que devuelve el corte por día UTC, pone los
  dos en rojo con el `viaje_id` repetido del caso real.

Tras `dvc repro prepare`: **0** `viaje_id` repetidos, **0** `trip_id` dobles y
**0** pasos duplicados. Las 10.457.901 posiciones se reparten sin perder
ninguna. La misma ejecución incorporó la exclusión del 31/08-07/09 (`eca39b9`,
que no se había reproducido), así que el total de pasos no es comparable. Fuera
de esos días, pasos 1.549.095 → 1.550.607 (+0,1 %) y asignados 70.593 → 70.600.
No se ha desglosado: los días vecinos a la exclusión también cambian de borde.

La clave de una posición es (`fecha_servicio`, `vehicle_id`): `vehicle_id` sigue
reiniciándose cada día.

## Para la memoria

> El etiquetado se ejecutaba por jornadas de captura en tiempo universal, que en
> horario de verano terminan a las dos de la madrugada locales, mientras que
> cada viaje se adscribe a su día de servicio, que se extiende hasta las cuatro.
> Como los identificadores de vehículo reconstruidos se reinician en cada
> ejecución, los viajes de madrugada comparten identificador con viajes del día
> anterior: se detectaron 932 identificadores repetidos entre ejecuciones, 890
> de ellos entre líneas distintas. Además, 74 servicios programados que cruzan
> el corte quedaron etiquetados dos veces, una por cada fragmento. Para
> evitarlo, el etiquetado se ejecuta por día de servicio, de cuatro a cuatro de
> la madrugada en hora local, franja en la que no circula en servicio ni un
> autobús por sondeo. Con ese corte no queda ningún identificador repetido ni
> ningún servicio etiquetado dos veces, y ninguna posición se pierde en el
> reparto entre días.
