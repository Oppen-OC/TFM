#!/usr/bin/env bash
# Instala el colector del TFM como servicio systemd en una Raspberry Pi.
#
#   curl/scp este repo a la Pi, luego:
#     sudo bash deploy_pi/instalar.sh
#
# Idempotente: se puede volver a ejecutar para actualizar el código.
set -euo pipefail

DESTINO=/opt/tfm
DATOS=${DATOS:-/srv/tfm-data}
USUARIO=${SUDO_USER:-$(id -un)}
ORIGEN=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

echo "==> usuario   : $USUARIO"
echo "==> código    : $DESTINO"
echo "==> datos     : $DATOS"

# --- comprobaciones previas -------------------------------------------------
ARCO=$(dpkg --print-architecture 2>/dev/null || uname -m)
if [[ "$ARCO" == "armhf" || "$ARCO" == "armv7l" ]]; then
  echo "!! Sistema de 32 bits ($ARCO). pandas y pyarrow dan bastante guerra aquí."
  echo "   Recomendado: Raspberry Pi OS de 64 bits (arm64)."
  read -rp "   ¿Seguir de todos modos? [s/N] " r; [[ "$r" == [sS] ]] || exit 1
fi

PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')
echo "==> python    : $PYV"
python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)' || {
  echo "!! Hace falta Python >= 3.10"; exit 1; }

# --- dependencias del sistema ----------------------------------------------
echo "==> instalando dependencias del sistema"
apt-get update -qq
apt-get install -y -qq python3-venv python3-dev build-essential \
                       libopenblas-dev tzdata rsync

# --- código ------------------------------------------------------------------
echo "==> copiando código a $DESTINO"
mkdir -p "$DESTINO"
rsync -a --delete \
      --exclude '.git' --exclude 'data' --exclude '.venv' --exclude '__pycache__' \
      "$ORIGEN"/ "$DESTINO"/
chown -R "$USUARIO":"$USUARIO" "$DESTINO"

# --- entorno virtual ---------------------------------------------------------
if [[ ! -x "$DESTINO/.venv/bin/python" ]]; then
  echo "==> creando entorno virtual"
  sudo -u "$USUARIO" python3 -m venv "$DESTINO/.venv"
fi
echo "==> instalando dependencias de Python (en arm64 tarda unos minutos)"
sudo -u "$USUARIO" "$DESTINO/.venv/bin/pip" install -q --upgrade pip
sudo -u "$USUARIO" "$DESTINO/.venv/bin/pip" install -q \
     --extra-index-url https://www.piwheels.org/simple \
     httpx pandas pyarrow

# --- almacén de datos --------------------------------------------------------
mkdir -p "$DATOS"
chown -R "$USUARIO":"$USUARIO" "$DATOS"
echo "==> datos en :"
df -h --output=source,fstype,size,avail,target "$DATOS" | sed 's/^/    /'
if ! mountpoint -q "$DATOS"; then
  echo
  echo "  !! $DATOS NO es un punto de montaje: estás escribiendo en el disco del"
  echo "     sistema. Monta antes la memoria externa:"
  echo "       sudo bash deploy_pi/preparar_disco.sh"
  echo
  read -rp "  ¿Seguir de todos modos? [s/N] " r; [[ "$r" == [sS] ]] || exit 1
fi
if df "$DATOS" | tail -1 | grep -q 'mmcblk'; then
  cat <<'AVISO'

  !! ATENCIÓN: los datos van a la tarjeta SD.
     Una captura continua de meses escribe sin parar y las SD se degradan.
     Además esta Pi sirve el DNS de la casa: si la tarjeta muere, te quedas
     sin Pi-hole y sin TFM a la vez.
     Recomendado: un USB o SSD montado en /srv/tfm-data.
       lsblk                                  # localiza el disco
       sudo mkfs.ext4 /dev/sdX1
       sudo mount /dev/sdX1 /srv/tfm-data     # y añádelo a /etc/fstab

AVISO
fi

# --- comprobación en seco ----------------------------------------------------
echo "==> comprobando el código"
sudo -u "$USUARIO" "$DESTINO/.venv/bin/python" "$DESTINO/demo/selftest.py" | tail -3

# --- servicio ----------------------------------------------------------------
echo "==> instalando el servicio systemd"
sed "s|^User=%i|User=$USUARIO|; s|--out /srv/tfm-data|--out $DATOS|; s|ReadWritePaths=/srv/tfm-data|ReadWritePaths=$DATOS|" \
    "$DESTINO/deploy_pi/tfm-colector.service" > /etc/systemd/system/tfm-colector.service
systemctl daemon-reload
systemctl enable --now tfm-colector.service

sleep 6
echo
systemctl --no-pager --lines=8 status tfm-colector.service || true
cat <<FIN

  Listo. Arranca solo en cada reinicio.

    Estado  : systemctl status tfm-colector
    Registro: journalctl -u tfm-colector -f
    Latido  : $DESTINO/.venv/bin/python $DESTINO/demo/collect.py --status --out $DATOS
    Parar   : sudo systemctl stop tfm-colector
    Datos   : $DATOS

  Copia de seguridad semanal (desde tu PC, no desde la Pi):
    rsync -av pi@raspberrypi.local:$DATOS/raw/ ./copia-tfm/raw/

FIN
