---
id: 044
titulo: El disco USB de la Pi falló por subtensión y la captura se quedó parada unas 27 h, del 05/10 a media mañana al 06/10, con el servicio «active (running)»; el 05/10 queda fuera del corpus
fecha: 2026-10-06
tipo: limitacion
capa: fuentes
capitulo: limitaciones
impacto: alto
estado: abierto
evidencia: en la Pi, `journalctl -u tfm-colector` (líneas ESTADO), `sudo dmesg -T` y `vcgencmd get_throttled` del 06/10; salidas pegadas en la sesión del 06/10. El journal rota: copiarlo antes de que se pierda
trampa: —
---

## Qué se observó

El 06/10, al desplegar la copia diaria del GTFS (ADR-020), `instalar.sh` falló
en `chown` sobre `/srv/tfm-data` con `Input/output error`. El diagnóstico en la
Pi dio esto:

- **El disco no puede leer el directorio raíz de su sistema de ficheros.** Es
  un WD20SDRW de 2 TB alimentado por USB. Cada lectura del sector 77904 caduca
  a los 180 s con `Sense Key 0x4`, y ese sector es el bloque del directorio raíz
  (`EXT4-fs warning … inode #2: lblock 0`). Todo lo que hay en `/srv/tfm-data`
  devuelve EIO.
- **La causa probable es la alimentación.** Hay `Undervoltage detected` cada
  ~2 min y `throttled=0x50000` (ha habido subtensión y estrangulamiento).
- **El colector estaba bloqueado, no caído.** systemd lo daba por
  `active (running)` desde el 04/10 a las 08:17 UTC. Sus contadores eran
  idénticos a las 12:50, 13:05 y 13:15 UTC del 06/10:

  | fuente | sondeos guardados desde el arranque | ritmo normal (bitácora 033) | horas que representan |
  |---|---|---|---|
  | `emt_buses` | 3.086 | 2.851 al día | ~26 h |
  | `trafico_estado` | 318 | 288 al día | ~26,5 h |
  | `valenbisi` | 318 | 288 al día | ~26,5 h |

  Las tres coinciden: **la captura se paró hacia las 10:30 UTC del 05/10**. La
  causa es que el colector escribe en disco desde un solo hilo `asyncio`: una
  lectura colgada 180 s bloquea todas las fuentes, también las que solo leen de
  la red.

**Ventana perdida:** desde el 05/10 hacia las 10:30 UTC (estimación por los
contadores) hasta que el colector volvió a escribir en la SD el 06/10, después
de las 13:22 UTC. Son **unas 27 h**. La cota segura es de al menos **15 h**:
del 05/10 a las 22:00 UTC (hay errores desde que empieza el filtro del journal)
al 06/10 a las 13:22 UTC.

**El instrumento mintió una vez.** El primer diagnóstico dio como «primer error
de E/S» el del 05/10 a las 22:10 UTC. Era el primero que mostraba
`journalctl --since today`, y en hora local «hoy» empieza a las 22:00 UTC del
día anterior. Los contadores sitúan el bloqueo 12 h antes.

## Cómo se midió

En la Pi:

```bash
journalctl -u tfm-colector --no-pager | grep ESTADO | tail -5   # contadores congelados
journalctl -u tfm-colector --no-pager | grep -m1 "Errno 5"      # primer EIO, SIN --since
sudo dmesg -T | grep -iE "sda|ext4|i/o error|voltage" | tail -40
vcgencmd get_throttled
```

La hora del bloqueo sale de dividir los sondeos guardados entre el ritmo
mediano de la bitácora 033, contando desde el arranque. El primer `Errno 5` sin
filtro de fecha la confirmará o corregirá, si el journal no ha rotado.

## Por qué importa

- **Se pierde aproximadamente un día de captura, para siempre.** Ninguna fuente
  guarda histórico. El PC tiene todo hasta el 04/10. La mañana del 05/10 que
  llegó a escribirse está en un disco que no se puede leer.
- **No avisó nada, por segunda vez.** Como en la bitácora 021, el servicio
  parecía vivo. `--status` habría delatado el latido viejo, pero solo si
  alguien lo mira. Sin alerta, el tiempo hasta detectarlo es el que tarda alguien
  en asomarse.
- **Un fallo de disco paró también las fuentes de red.** Con la escritura en el
  mismo hilo que los sondeos, el modo de fallo del disco se convierte en el de
  todo el colector.

## Qué se hizo / qué queda abierto

Hecho (en la Pi el 06/10, por la sesión de Claude que corre allí; no lo he
verificado desde el PC: confirmar con `--status --out /srv/tfm-sd`):
- El colector escribe de forma provisional en `/srv/tfm-sd`, la SD, mediante
  un drop-in de systemd que también abre `ReadWritePaths` a esa ruta.
- El disco se desmontó.
- **Se trabaja sin el 05/10.** El corpus sigue terminando el 04/10. Lo nuevo
  se trae desde `/srv/tfm-sd`:
  `ORIGEN=oppen@192.168.1.219:/srv/tfm-sd/raw bash deploy_pi/pull_data.sh --verificar`.

Abierto:
- **Alimentación:** un hub USB con alimentación propia, o una fuente oficial.
- **El disco:** diagnóstico en lectura (`smartctl`, leer el sector 77904,
  `fsck.ext4 -n`) y, si el sector no se lee, una imagen con `ddrescue` antes de
  reparar. Decidirá si se recupera algo de la mañana del 05/10.
- **Una alerta que no dependa de mirar:** el latido viejo tiene que avisar
  solo, al PC o al móvil.
- **El colector no debe bloquearse por el disco:** escribir fuera del bucle de
  sondeo (`asyncio.to_thread`), con un respaldo en la SD si el disco no
  responde.
- **El postmortem del incidente.**

## Para la memoria

> El 5 de octubre el disco externo del equipo de captura dejó de responder,
> probablemente por una alimentación insuficiente para el equipo y un disco
> alimentado por USB. Como el colector escribía en disco desde el mismo hilo
> en el que consultaba las fuentes, el bloqueo detuvo la captura de todas
> ellas, mientras el servicio seguía apareciendo como activo. Se perdieron unas
> 27 horas de datos, desde la mañana del 5 de octubre hasta el día siguiente.
> Como ninguna fuente conserva histórico, no son recuperables: ese día queda
> fuera del corpus. El periodo de entrenamiento y prueba termina el 4 de
> octubre y no se ve afectado. El incidente motivó tres medidas: alimentar el
> disco de forma independiente, avisar automáticamente cuando el colector deja
> de dar señales de vida y desacoplar la escritura en disco de la consulta de
> las fuentes.
