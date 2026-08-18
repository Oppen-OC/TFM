#!/usr/bin/env bash
# Prepara una memoria externa para los datos del TFM y la deja montada de forma
# permanente en /srv/tfm-data.
#
#   sudo bash deploy_pi/preparar_disco.sh            # ver discos y elegir
#   sudo bash deploy_pi/preparar_disco.sh /dev/sda   # formatear ese disco (BORRA)
#   sudo bash deploy_pi/preparar_disco.sh /dev/sda1 --solo-montar   # sin formatear
#
# Guardas: se niega a tocar el disco donde está montado el sistema, exige que
# escribas FORMATEAR a mano, y monta por UUID (no por /dev/sdX, que cambia de
# nombre entre reinicios).
set -euo pipefail

PUNTO=${PUNTO:-/srv/tfm-data}
USUARIO=${SUDO_USER:-$(id -un)}
OBJETIVO=${1:-}
MODO=${2:-}

[[ $EUID -eq 0 ]] || { echo "Ejecútalo con sudo."; exit 1; }

# --- disco del sistema, que es intocable -------------------------------------
RAIZ_PART=$(findmnt -no SOURCE /)
RAIZ_DISCO="/dev/$(lsblk -no PKNAME "$RAIZ_PART" 2>/dev/null || true)"
[[ "$RAIZ_DISCO" == "/dev/" ]] && RAIZ_DISCO="$RAIZ_PART"

if [[ -z "$OBJETIVO" ]]; then
  echo
  echo "Discos conectados (el sistema vive en $RAIZ_DISCO, ése NO se toca):"
  echo
  lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT,TRAN,MODEL | sed 's/^/  /'
  cat <<AYUDA

  Identifica tu memoria externa por tamaño y modelo. Luego:

    Formatearla (BORRA TODO lo que tenga):
      sudo bash deploy_pi/preparar_disco.sh /dev/sda

    Si ya está en ext4 y quieres conservar su contenido:
      sudo bash deploy_pi/preparar_disco.sh /dev/sda1 --solo-montar

AYUDA
  exit 0
fi

[[ -b "$OBJETIVO" ]] || { echo "!! $OBJETIVO no es un dispositivo de bloques."; exit 1; }

# --- comprobar que no es el disco del sistema --------------------------------
BASE="/dev/$(lsblk -no PKNAME "$OBJETIVO" 2>/dev/null || true)"
[[ "$BASE" == "/dev/" ]] && BASE="$OBJETIVO"
if [[ "$BASE" == "$RAIZ_DISCO" || "$OBJETIVO" == "$RAIZ_DISCO" || "$OBJETIVO" == "$RAIZ_PART" ]]; then
  echo "!! $OBJETIVO pertenece al disco del sistema ($RAIZ_DISCO). Abortado."
  exit 1
fi
if lsblk -no MOUNTPOINT "$BASE" | grep -qE '^/$|^/boot'; then
  echo "!! $BASE tiene montado / o /boot. Abortado."
  exit 1
fi

echo
echo "Objetivo: $OBJETIVO"
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT "$BASE" | sed 's/^/  /'
echo

# --- desmontar lo que el escritorio haya automontado -------------------------
for m in $(lsblk -no MOUNTPOINT "$BASE" | grep -v '^$' || true); do
  echo "==> desmontando $m"; umount "$m" || true
done

if [[ "$MODO" == "--solo-montar" ]]; then
  PART="$OBJETIVO"
  FS=$(lsblk -no FSTYPE "$PART")
  echo "==> se conserva el contenido. Sistema de ficheros: ${FS:-desconocido}"
  case "$FS" in
    ext4|ext3|xfs|btrfs) ;;
    *) echo "!! $FS no maneja permisos POSIX. Para escritura continua de meses"
       echo "   conviene ext4. Formatea sin --solo-montar si puedes."; ;;
  esac
else
  TAM=$(lsblk -dno SIZE "$BASE")
  MODELO=$(lsblk -dno MODEL "$BASE" | xargs || true)
  echo "  Se va a BORRAR POR COMPLETO $BASE ($TAM, ${MODELO:-sin modelo})"
  echo
  read -rp "  Escribe FORMATEAR para confirmar: " C
  [[ "$C" == "FORMATEAR" ]] || { echo "Cancelado."; exit 1; }

  echo "==> creando tabla de particiones y una partición ext4"
  wipefs -a "$BASE" >/dev/null
  parted -s "$BASE" mklabel gpt
  parted -s "$BASE" mkpart primary ext4 1MiB 100%
  sleep 2; partprobe "$BASE" || true; sleep 2
  PART=$(lsblk -lno NAME,TYPE "$BASE" | awk '$2=="part"{print "/dev/"$1; exit}')
  [[ -n "$PART" ]] || { echo "!! no encuentro la partición creada"; exit 1; }
  # -m1: sólo 1 % reservado para root en vez del 5 % por defecto.
  mkfs.ext4 -q -F -L TFMDATA -m1 "$PART"
fi

UUID=$(blkid -s UUID -o value "$PART")
[[ -n "$UUID" ]] || { echo "!! no obtengo el UUID de $PART"; exit 1; }
echo "==> partición $PART  UUID=$UUID"

# --- montaje permanente por UUID ---------------------------------------------
mkdir -p "$PUNTO"
sed -i "\|[[:space:]]${PUNTO}[[:space:]]|d" /etc/fstab
# nofail: si algún día arrancas la Pi sin el disco, no se queda colgada.
echo "UUID=$UUID  $PUNTO  ext4  defaults,noatime,nofail,x-systemd.device-timeout=10  0  2" >> /etc/fstab
systemctl daemon-reload
mount "$PUNTO"
chown -R "$USUARIO":"$USUARIO" "$PUNTO"

echo
echo "==> montado:"
df -h "$PUNTO" | sed 's/^/  /'
findmnt -no SOURCE,TARGET,FSTYPE,OPTIONS "$PUNTO" | sed 's/^/  /'
cat <<FIN

  Listo. Los datos irán a $PUNTO y el montaje sobrevive a los reinicios.

  Siguiente paso:
    sudo env DATOS=$PUNTO bash deploy_pi/instalar.sh

FIN
