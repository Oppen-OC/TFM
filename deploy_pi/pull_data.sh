#!/usr/bin/env bash
# Trae a data/raw/ el crudo que ha capturado la Pi. Se ejecuta en el PC, desde
# WSL (Git Bash no trae rsync):
#
#     bash deploy_pi/pull_data.sh               # trae los días que faltan
#     bash deploy_pi/pull_data.sh --dry-run     # enseña qué traería, sin escribir
#     bash deploy_pi/pull_data.sh --verificar   # qué difiere de la Pi, sin escribir
#
# Solo AÑADE. `--ignore-existing` no toca ningún fichero que ya esté en el repo,
# y no es prudencia de más: el 15-18/08 lo capturó el portátil y la Pi solo
# tiene la última hora del 18, así que un rsync normal dejaría ese día con 115
# sondeos de la EMT en vez de 1.109, sin ningún error (bitácora 035).
#
# Se quedan fuera a propósito:
#   - El día en curso, en UTC, que es como particiona `append_raw`. Su fichero
#     sigue creciendo y `--ignore-existing` lo congelaría a medias para siempre.
#   - `curated/` y `reference/`: los regenera el stage `curar` desde el crudo.
#     Los `part-*` del colector junto al reprocesado duplicarían los sondeos.
#
# Sin `--partial` ni `--inplace`: rsync escribe en un temporal y renombra al
# terminar, así que un corte a media transferencia no deja un fichero truncado
# que la siguiente ejecución daría por bueno.
#
# Los días nuevos cambian las deps de `curar`: el siguiente `dvc repro` rehace
# el pipeline entero, y todo lo posterior a `features.test_desde` cae en test.
set -euo pipefail

ORIGEN=${ORIGEN:-oppen@192.168.1.219:/srv/tfm-data/raw}
DESTINO=${DESTINO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/data/raw}
# ponytail: el reloj es el del PC. Lanzado en el minuto de las 00:00 UTC con los
# relojes desajustados, el día recién cerrado podría llegar a medias;
# `--verificar` lo delata.
HOY=$(date -u +%F)

[[ -d "$DESTINO" ]] || { echo "!! No existe $DESTINO"; exit 1; }

MODO=(--ignore-existing)
if [[ "${1:-}" == "--verificar" ]]; then
  shift
  # Compara por contenido y no escribe. En la salida, `>f+++++++++` es un día
  # que falta en el repo y `>fc...` uno que está en los dos y no coincide. El
  # 18/08 sale siempre: es el que el repo tiene más completo que la Pi.
  MODO=(--dry-run --checksum --no-times --itemize-changes)
fi

echo "==> $ORIGEN -> $DESTINO (sin date=$HOY)"
rsync -av "${MODO[@]}" \
      --include='source=*/' --exclude="date=$HOY/" \
      --include='source=*/date=*/***' --exclude='*' \
      "$@" "$ORIGEN/" "$DESTINO/"
