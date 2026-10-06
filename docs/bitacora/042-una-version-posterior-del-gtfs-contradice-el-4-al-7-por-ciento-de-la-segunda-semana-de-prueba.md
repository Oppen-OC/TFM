---
id: 042
titulo: La versión del GTFS publicada el 05/10 contradice entre el 3,6 % y el 7,0 % de los pasos etiquetados del 28/09-04/10. Quita la línea 13, que siguió circulando, y prolonga el horario excepcional de la 35. Se archiva y la prueba sigue con la 19-09
fecha: 2026-10-06
tipo: anomalia
capa: fuentes
capitulo: limitaciones
impacto: medio
estado: aceptado
evidencia: uv run python -m project.analysis.comparar_gtfs data/raw/gtfs_archivo/google_transit2026-10-04.zip; uv run python -m project.ingest.transitland --desde 2026-09-21 --hasta 2026-10-04
trampa: —
---

## Qué se observó

Toda la prueba (21/09-04/10) se etiqueta con la versión `19-09-2026` del GTFS,
la última descargada (18/09). Transitland registra **14 versiones** posteriores,
casi una al día, con el calendario corriendo: empieza unos 8 días antes de cada
publicación y acaba unas 4 semanas después. Solo es descargable gratis la
vigente en VLCi. El 06/10 era la `05-10-2026` (sha1 `21a5e04c727f`, vigente
28/09-04/11), que cubre la segunda semana de la prueba.

Pasos etiquetados cuyo (línea, parada, hora programada) no existe en la
`05-10-2026`:

| día | pasos | fuera | líneas que lo concentran |
|---|---|---|---|
| 28/09 lun | 71.249 | 3,9 % | 13 (100 %), 32 (100 %), 35 (94 %) |
| 29/09 mar | 69.523 | 4,2 % | 13 (100 %), 35 (92 %), 9 (48 %) |
| 30/09 mié | 67.761 | 4,8 % | 13, 35, 9 (56 %), 10 (42 %) |
| 01/10 jue | 64.172 | 4,5 % | 13, 35, 9 (42 %) |
| 02/10 vie | 63.663 | 3,6 % | 13, 35 |
| 03/10 sáb | 42.236 | 6,5 % | 13, 35 |
| 04/10 dom | 36.846 | 7,0 % | 13, 35 |

Lo concentran dos líneas con soporte propio:

- **La 13 desaparece de la versión nueva**: ningún viaje y ningún trazado.
  Pero los buses siguieron publicándose como línea 13, y se etiquetaron todos
  los días con la `19-09-2026`: del 28/09 al 04/10, entre 58 y 93 viajes al día y un retraso
  mediano diario de 3 a 81 s, cifras plausibles.
- **La 35 cambia de servicio.** La `19-09-2026` aplica un horario excepcional
  (`35_935_601_EXC`) hasta el 27/09 y vuelve al normal (`35_935_606`) el
  28/09. La `05-10-2026` mantiene el excepcional (`35_935_601`) desde el
  28/09. Los mismos trazados y paradas, con salidas desplazadas 3-7 min desde
  las 08:00. Se ajustó cada viaje observado de la 35 al mejor viaje de cada
  horario: en el 28/09-04/10 el error mediano es de 101-118 s con uno y de
  91-125 s con el otro, y cada uno gana unos días. **No decide cuál circuló.**

La asignación por día no se mueve en esa semana: entre el 56 % y el 63 % de los
tramos se asignan, igual que en la anterior. Como en la bitácora 024, una
etiqueta con el horario dudoso no da la cara.

## Cómo se midió

```bash
uv run python -m project.ingest.transitland --desde 2026-09-21 --hasta 2026-10-04
uv run python -m project.analysis.comparar_gtfs data/raw/gtfs_archivo/google_transit2026-10-04.zip
```

El zip se bajó de la API de VLCi (`package_show?id=google-transit-lines-stops-bus-schedules`)
y su sha1 coincide con la versión que Transitland capturó el 06/10.
`comparar_gtfs` busca cada paso etiquetado en el horario de la otra versión por
(línea, parada, hora programada), sin `trip_id`, que cambia entre versiones.
El ajuste de los viajes de la 35 a los dos horarios se hizo con un script de
exploración no versionado: es lo único de esta entrada que no reproduce un
comando del repo.

## Por qué importa

- **El GTFS no es un dato fijo.** Se republica casi a diario y puede reescribir
  días ya pasados. La primera semana de la prueba (21-27/09) no se puede
  contrastar: las versiones que la cubren solo están en Transitland de pago.
- **La versión más reciente no es la más fiable.** Si se aplicara la regla del
  ADR-014 sin más, la 13 se quedaría sin etiquetar en media prueba aunque
  circuló, y la 35 cambiaría de horario sin que lo observado lo respalde.
- **El alcance es acotado.** Las dos líneas son el 6,5 % de los viajes de la
  prueba (1.027 y 1.573 de 40.032) y la mitad de sus días. En la 35, un
  desfase constante dentro del viaje se cancela en lo que gana o pierde entre
  paradas, que es lo que predice el modelo, pero no en la etiqueta binaria.

## Qué se hizo / qué queda abierto

Hecho:
- La `05-10-2026` se guarda en `data/raw/gtfs_archivo/` con DVC, fuera de
  `gtfs_dir`, para que la etiqueta no la use.
- La prueba sigue etiquetada con la `19-09-2026`. Es una excepción declarada
  en el ADR-014.

Abierto:
- **Capturar el GTFS a diario desde el colector**, como el resto de fuentes,
  para no depender de descargas a mano.
- Volver a contrastar la 35 cuando se pueda decidir qué horario circuló.

## Para la memoria

> El horario teórico se toma del GTFS que publica la EMT en el portal de datos
> abiertos del Ayuntamiento. La operadora republica el fichero casi a diario y
> cada versión sustituye a la anterior sin conservar histórico, de modo que una
> publicación posterior puede reescribir días ya etiquetados. La versión
> publicada el 5 de octubre discrepa del horario empleado en entre el 3,6 % y el
> 7,0 % de los pasos de la segunda semana de prueba. La discrepancia se
> concentra en dos líneas: la versión posterior suprime la línea 13, que siguió
> circulando y cuyos pasos se etiquetan con retrasos plausibles, y mantiene en
> la línea 35 un horario excepcional que la versión empleada daba por concluido.
> Contrastar los viajes observados con ambos horarios no permite decidir cuál
> se aplicó. Por ello la prueba conserva el horario vigente al inicio del
> periodo, que lo cubre por completo, y la discrepancia se declara como
> limitación.
