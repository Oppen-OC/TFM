---
id: 051
titulo: La Pi no guarda versiones del GTFS desde el 06/10, porque corre un colector anterior a la captura del ADR-020; se pierden unas doce versiones intermedias, y la que se bajó a mano el 13/10 cubre la prueba y devuelve a la línea 13 los viajes que la del 05/10 le había quitado
fecha: 2026-10-13
tipo: limitacion
capa: fuentes
capitulo: limitaciones
impacto: medio
estado: mitigado
evidencia: en la Pi el 13/10, `grep -rc capturar_gtfs /opt/tfm --include=collect.py`, `ls /srv/tfm-sd/raw/`, `systemctl cat tfm-colector` y `journalctl -u tfm-colector --since 2026-10-06 | grep -i gtfs` (salidas pegadas en la sesión del 13/10); en el PC, `git show raspberry:demo/collect.py | grep -c capturar_gtfs` y el recuento de viajes de la 13 de «Cómo se midió»
trampa: —
---

## Qué se observó

El ADR-020 dispuso que el colector guardara cada versión nueva del GTFS de la
EMT en `raw/source=gtfs_emt/`. El 13/10, al traer la prueba con
`pull_data.sh --verificar`, no apareció ninguna. En la Pi:

- `/srv/tfm-sd/raw/` tiene las cinco fuentes de siempre y **no** tiene
  `source=gtfs_emt`.
- El colector que corre (`/opt/tfm/demo/collect.py`, por el drop-in que lo
  manda a la SD desde la bitácora 044) contiene **0** apariciones de
  `capturar_gtfs`.
- El journal no tiene ninguna línea de GTFS desde el 06/10.
- La rama `raspberry` sí tiene la captura: el commit 77a3122, del 06/10. Ese
  mismo día, el despliegue falló en `instalar.sh` por el disco roto (bitácora
  044), y la Pi siguió con el código anterior.

**Lo que se pierde.** Entre el 19/09 y el 06/10 la EMT publicó 14 versiones,
unas 0,8 al día (bitácora 042). A ese ritmo, del 06 al 21/10 se habrán
publicado **unas doce** que nadie ha guardado. Es una estimación: el número
real solo lo tiene Transitland, de pago.

**Mitigación.** El 13/10 a las 08:35 UTC se bajó a mano la versión vigente con
las funciones del propio colector:
- `12-10-2026`, sha1 `489e908256966f8ee90abc3a188a94d7a9d1d5b8`, 6.797.788 bytes;
- en `data/raw/source=gtfs_emt/date=2026-10-13/`, fuera de `gtfs_dir`;
- vigente del **05/10 al 11/11**: cubre la prueba entera (07-19/10).

**Por qué importan las versiones intermedias.** La línea 13 tiene 381 viajes
en la `19-09-2026`, la que etiqueta. Tiene **0** en la `05-10-2026`, como
recogió la bitácora 042. Y vuelve a tener **287** en la `12-10-2026`. La 13 no
desapareció: una versión intermedia la quitó y la siguiente la devolvió. Sin
las versiones entre medias no se puede saber qué horario publicó la EMT cada
día de la prueba, solo contrastarla con las que se guardaron.

## Cómo se midió

En la Pi (`ssh oppen@192.168.1.219 'bash -s'`):

```bash
ls /srv/tfm-sd/raw/
grep -rc "capturar_gtfs" /opt/tfm --include=collect.py        # /opt/tfm/demo/collect.py:0
systemctl cat tfm-colector | grep -E "ExecStart|ReadWritePaths"
journalctl -u tfm-colector --since "2026-10-06" --no-pager | grep -i gtfs
```

En el PC:

```bash
git show raspberry:demo/collect.py | grep -c capturar_gtfs      # la rama sí la tiene
for z in data/raw/gtfs/versiones/google_transit2026-09-18.zip \
         data/raw/gtfs_archivo/google_transit2026-10-04.zip \
         data/raw/source=gtfs_emt/date=2026-10-13/489e90825696_google_transit2026-10-11.zip; do
  r=$(unzip -p $z routes.txt | awk -F, '$3=="13"{print $1}')
  unzip -p $z trips.txt | awk -F, -v r="$r" 'NR>1 && $1==r' | wc -l   # 381, 0, 287
done
```

La descarga usó `sources.gtfs_url` y `sources.guardar_gtfs` con las cabeceras
de `collect.py`, como haría el colector. `capturas.ndjson` guarda la URL, el
`last_modified` (12/10, 19:36) y el sha1. La estimación de doce versiones
sale del ritmo de la bitácora 042 (14 en 17 días) por los 15 días sin captura.

## Por qué importa

- **No toca las etiquetas.** La prueba se etiqueta con la `19-09-2026` (nota
  del 11/10 al ADR-024), y las versiones nuevas solo sirven para contrastarla y
  declarar el límite. La `12-10-2026` basta para ese contraste, como bastó la
  `05-10-2026` en la 042.
- **Lo que se pierde es la secuencia.** Con una sola versión posterior se mide
  cuánto de lo etiquetado contradice ese horario, pero no cuándo cambió ni si
  el cambio se deshizo después. El caso de la 13 demuestra que se deshacen.
- **Un despliegue fallido no da la cara.** El servicio siguió capturando las
  cinco fuentes, y nada avisó de que faltaba la sexta. Es el mismo patrón que
  la 021 y la 044: proceso vivo y captura incompleta.
- **El ADR-020 daba por hecho el despliegue.** Dice que la captura «está en las
  dos copias del colector: `demo/` en la rama `raspberry`, que es lo que corre
  la Pi». Está en la rama, pero no corre en la Pi.

## Qué se hizo / qué queda abierto

Hecho:
- Bajada a mano la `12-10-2026` (13/10). Anotado en la nota del ADR-024
  (8b71f8c), con la decisión de no redesplegar a mitad de prueba: un reinicio
  fallido dejaría un hueco en ella.
- Precisión añadida al ADR-020.

Abierto:
- **El 21/10:** bajar a mano la versión vigente y contrastar las dos con
  `analysis/comparar_gtfs` antes de las comparaciones (tarea 12 del plan de la
  fase 2).
- **Después de cerrar la prueba** (pasado el 20/10 a las 02:00 UTC):
  redesplegar `raspberry` en la Pi y comprobar que aparece
  `source=gtfs_emt` y una línea `gtfs:` en el journal.
- **Que el latido cuente las seis fuentes.** `--status` y `ESTADO` solo listan
  las que el colector conoce: uno que no tiene la captura no puede echarla en
  falta. Falta una comprobación de que el código desplegado coincide con la
  rama.

## Para la memoria

> El horario programado de la operadora se republica casi a diario y cada
> publicación sustituye a la anterior sin conservar histórico. Para conservar
> la secuencia de versiones se añadió al programa de captura una descarga
> periódica del horario, pero su despliegue en el equipo de captura falló el 6
> de octubre, durante la incidencia del disco, y el equipo siguió funcionando
> con la versión anterior del programa. Las demás fuentes se capturaron con
> normalidad y nada indicó la ausencia. Al ritmo de publicación observado, de
> unas 0,8 versiones diarias, se estima que entre el 6 y el 21 de octubre se
> perdieron unas doce versiones intermedias. Para el contraste de la prueba se
> descargó manualmente la versión vigente el 13 de octubre, que cubre todo el
> periodo de prueba. Las etiquetas no dependen de estas versiones, porque la
> prueba se etiqueta con el horario vigente al comienzo del periodo, pero sin
> la secuencia completa no puede determinarse qué horario publicó la operadora
> cada día. Las versiones conservadas muestran que esos cambios pueden
> revertirse: una línea retirada en la publicación del 5 de octubre reaparece,
> con 287 viajes, en la del 12 de octubre.
