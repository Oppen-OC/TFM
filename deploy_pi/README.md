# Colector en Raspberry Pi

La Pi es mejor sitio que el portátil: está encendida 24/7, no se suspende al
cerrar la tapa y systemd reinicia el proceso mucho mejor que el Programador de
tareas de Windows. Consume poco: unos 6 sondeos por minuto y ~20 MB de RAM.

## Antes de empezar

**Comprueba tres cosas.**

1. **Sistema de 64 bits.** `dpkg --print-architecture` debe decir `arm64`. En
   32 bits (`armhf`) pandas y pyarrow compilan a mano y tardan una eternidad.
2. **Dónde van los datos.** Con las cadencias actuales son ~2-3 GB en 90 días.
   Cabe en una SD, pero **no lo pongas en la SD**: una captura continua de meses
   la desgasta, y esta Pi además sirve el DNS de tu casa. Si la tarjeta muere te
   quedas sin Pi-hole y sin TFM el mismo día. Monta un USB o un SSD en
   `/srv/tfm-data`.
3. **La hora.** `timedatectl` debe mostrar el reloj sincronizado por NTP. La
   detección automática de convención horaria se apoya en comparar el sello de
   la fuente con la hora local: si la Pi va desajustada más de tres minutos,
   marcará todo como `DUDOSA`.

## Instalación

Desde tu PC, copia el repo y lanza el instalador:

```bash
rsync -av --exclude data --exclude .git --exclude .venv \
      /c/Users/oppen/Code/TFM/ pi@raspberrypi.local:/tmp/tfm/
ssh pi@raspberrypi.local
sudo bash /tmp/tfm/deploy_pi/instalar.sh
```

El script instala dependencias, crea el entorno virtual (con piwheels, que trae
ruedas ya compiladas para ARM), pasa el autotest, registra el servicio y lo
arranca. Es idempotente: vuelve a ejecutarlo para actualizar el código.

## Manejo

```bash
systemctl status tfm-colector          # ¿está vivo?
journalctl -u tfm-colector -f          # registro en directo
sudo systemctl restart tfm-colector    # reiniciar
sudo systemctl stop tfm-colector       # parar

/opt/tfm/.venv/bin/python /opt/tfm/demo/collect.py --status --out /srv/tfm-data
```

## Copia de seguridad, semanal y no negociable

Los datos no se pueden recapturar. Desde tu PC:

```bash
rsync -av pi@raspberrypi.local:/srv/tfm-data/raw/ ./copia-tfm/raw/
```

Basta con `raw/`: `curated/` se regenera con `reprocesar.py`.

## Qué hace el fichero de servicio

- `Restart=always` con `StartLimitIntervalSec=0`: vuelve siempre, sin rendirse
  tras varios fallos seguidos. En tres meses habrá cortes de red.
- `KillSignal=SIGTERM` y `TimeoutStopSec=60`: el colector atiende SIGTERM y
  vuelca lo que tenga en memoria antes de salir.
- `Nice=10`, `IOSchedulingClass=idle`, `CPUWeight=20`, `MemoryMax=512M`: el
  colector nunca compite con Pi-hole. El DNS de la casa manda.
- `ProtectSystem=strict` con `ReadWritePaths` solo al directorio de datos.

## Convivencia con Pi-hole

No hay conflicto de puertos: el colector no escucha en ninguno, solo hace
peticiones salientes. Los dos puntos de roce son el disco y la SD, y ambos se
resuelven poniendo los datos en un USB aparte.

Si quieres ir sobre seguro, mira el consumo el primer día:

```bash
systemd-cgtop -1 --order=cpu | head
df -h /srv/tfm-data
```
