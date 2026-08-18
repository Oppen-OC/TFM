# Pasos exactos · colector en la Raspberry Pi (vía GitHub)

Tu repo ya está en `https://github.com/Oppen-OC/TFM` y es **público**, así que en
la Pi basta un `git clone`, sin credenciales ni claves.

Pero antes hay que resolver el problema real: **tu PC no encuentra la Pi**.
`raspberrypi.local` usa mDNS y Windows no siempre lo resuelve. Con GitHub o sin
él, para instalar necesitas entrar por SSH, así que esto va primero.

---

## 0 · Encontrar la Pi en la red

**Atajo, porque tienes Pi-hole.** Si el router ya usa la Pi como DNS, su IP es
tu servidor DNS:

```powershell
Get-DnsClientServerAddress -AddressFamily IPv4 |
  Where-Object {$_.ServerAddresses} |
  Select-Object InterfaceAlias, ServerAddresses
```

Si sale algo tipo `192.168.1.50`, ésa es la Pi. Compruébalo:

```powershell
ping 192.168.1.50
ssh pi@192.168.1.50
```

> Si lo que sale es la IP del router (normalmente `.1`), es que el router hace
> de intermediario. Usa el método de abajo.

**Si no, búscala por su MAC.** Las Raspberry Pi tienen prefijos reservados:

```powershell
$sub = ((Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway}).IPv4Address.IPAddress) -replace '\.\d+$',''
1..254 | ForEach-Object { (New-Object System.Net.NetworkInformation.Ping).SendPingAsync("$sub.$_",300) } | Out-Null
Start-Sleep 4
Get-NetNeighbor -AddressFamily IPv4 |
  Where-Object {$_.LinkLayerAddress -match '^(B8-27-EB|DC-A6-32|E4-5F-01|28-CD-C1|2C-CF-67|D8-3A-DD)'} |
  Select-Object IPAddress, LinkLayerAddress
```

**Y si tampoco, mira el router.** En la interfaz de tu DIGI, la lista de
clientes DHCP. Aprovecha para **reservarle la IP**, así no cambia nunca.

**Cuando la tengas, ponle nombre** (PowerShell como administrador):

```powershell
Add-Content C:\Windows\System32\drivers\etc\hosts "`n192.168.1.50`tpi"
```

Ya puedes usar `ssh pi@pi`. Sustituye `pi@` por tu usuario real si es otro.

---

## 1 · Preparar el repo (en Windows)

**Antes de commitear hay que arreglar `.gitignore`.** El actual sólo ignora
`data/raw/`, `data/interim/` y `data/processed/`, pero el colector escribe
además en `data/curated/`, `data/reference/` y `data/logs/`. Ahora mismo
`data/` ocupa **408 MB**: un `git add -A` intentaría subirlo, GitHub rechaza
ficheros de más de 100 MB y el historial quedaría inflado para siempre.

Sustituye `.gitignore` por el que te he dejado y comprueba:

```powershell
cd C:\Users\oppen\Code\TFM
git status --short
```

**No debe aparecer nada que empiece por `data/`.** Si aparece, para y avísame.

Luego:

```powershell
git add -A
git commit -m "Colector de datos abiertos de Valencia, diagnostico y despliegue en Pi"
git push origin develop
```

Estás en la rama `develop` y la rama por defecto de GitHub es `main`. Da igual
para esto: en la Pi clonaremos `develop` explícitamente.

---

## 2 · Clonar en la Pi

```powershell
ssh pi@pi
```

Ya dentro de la Pi:

```bash
git clone -b develop https://github.com/Oppen-OC/TFM.git ~/TFM
cd ~/TFM
```

---

## 3 · Ver qué disco es tu memoria externa

```bash
sudo bash deploy_pi/preparar_disco.sh
```

No formatea nada: lista los discos y marca cuál es el del sistema. Identifica el
tuyo por **tamaño y modelo**. Normalmente `/dev/sda`.

## 4 · Preparar el disco

**Se borra entero. Asegúrate de que no tiene nada que quieras.**

```bash
sudo bash deploy_pi/preparar_disco.sh /dev/sda
```

Te hará escribir `FORMATEAR`. Crea una partición ext4, la añade a `/etc/fstab`
**por UUID** y la monta en `/srv/tfm-data`.

> Si ya está en ext4 y quieres conservar el contenido:
> `sudo bash deploy_pi/preparar_disco.sh /dev/sda1 --solo-montar`

## 5 · Instalar

```bash
sudo env DATOS=/srv/tfm-data bash deploy_pi/instalar.sh
```

## 6 · Comprobar

```bash
systemctl status tfm-colector
/opt/tfm/.venv/bin/python /opt/tfm/demo/collect.py --status --out /srv/tfm-data
```

Debe decir **VIVO**, con filas subiendo en las cinco fuentes.

## 7 · Parar el de Windows y llevarte lo capturado

```powershell
.\demo\supervisar.ps1 -Modo Parar
scp -r C:\Users\oppen\Code\TFM\data\raw pi@pi:/srv/tfm-data/
```

Y en la Pi, reconstruir `curated/` con el parser actual:

```bash
cd /opt/tfm && sudo -u $USER .venv/bin/python demo/reprocesar.py --data /srv/tfm-data
```

---

## Actualizar el código más adelante

Aquí es donde GitHub gana de verdad. En Windows `git push`, y en la Pi:

```bash
cd ~/TFM && git pull
sudo env DATOS=/srv/tfm-data bash deploy_pi/instalar.sh
```

El instalador es idempotente: vuelve a copiar, reinstala dependencias si hacen
falta y reinicia el servicio. Nada de tar ni de scp.

---

## Copia de seguridad semanal

```powershell
scp -r pi@pi:/srv/tfm-data/raw C:\Users\oppen\copia-tfm\
```

## Si algo falla

| Síntoma | Qué mirar |
|---|---|
| `Could not resolve hostname` | vuelve al paso 0; usa la IP directamente |
| `Permission denied (publickey)` | usuario equivocado, o SSH desactivado (`sudo raspi-config` → Interface Options → SSH) |
| `Failed to start` | `journalctl -u tfm-colector -n 50 --no-pager` |
| Se cae al reiniciar la Pi | ¿está el disco enchufado? `findmnt /srv/tfm-data` |
| Todo marcado `DUDOSA` | `timedatectl` debe decir `synchronized: yes` |
| pandas/pyarrow no instalan | `dpkg --print-architecture` debe decir `arm64` |
