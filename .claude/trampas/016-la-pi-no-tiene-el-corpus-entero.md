---
id: 016
titulo: Sincronizar la Pi sobre data/raw/ machaca los días que capturó el portátil
estado: mitigada
capa: fuentes
detectada: 2026-09-30
test: ninguno
---

## Síntoma

Tras un `rsync -av` (o un `scp -r`) de la Pi sobre `data/raw/`, el 18/08 de la
EMT pasa de 1.109 sondeos a 115 y el de las cinco fuentes de 2.564 a 260. No
falla nada: `reprocesar` lee lo que haya, `dvc repro` se rehace con un día de
una hora y las métricas salen igual de plausibles. `data/` está fuera de git y
`raw/` no tiene puntero de DVC, así que tampoco hay diff que lo enseñe.

## Causa

El 15-18/08 lo capturó el portátil; la Pi empezó el 18/08 a las 23:02 UTC. El
fichero del 18/08 del repo es una costura de los dos colectores y el de la Pi
solo tiene su última hora. rsync los ve distintos en tamaño y fecha y copia el
del origen. Cifras y método en
`docs/bitacora/035-el-corpus-entero-solo-esta-en-el-pc.md`.

## Por qué se vuelve a caer aquí

La Pi es «el colector» y el PC «la copia»: lo natural es suponer que el origen
lo tiene todo y que sincronizar no puede perder nada. `deploy_pi/README.md` y
`deploy_pi/PASOS.md` dan el comando hacia un directorio aparte, donde es
correcto; cambiarle el destino a `data/raw/` es el paso obvio para que el
pipeline vea los días nuevos. Y traer el día en curso parece inofensivo porque
«ya se completará», pero con `--ignore-existing` se queda a medias para siempre
y sin él vuelve el problema de arriba.

## Guardia

Ninguna en `pytest`. Workaround: `deploy_pi/pull_data.sh`, que solo añade
(`--ignore-existing`), deja fuera el día en curso y no usa `--partial`. Se
comprueba a mano con `bash deploy_pi/pull_data.sh --verificar` y con
`uv run python -m project.analysis.auditar_persistencia --copia <raw de la copia>`.

Para cerrarla: un test que lance el script con `ORIGEN` y `DESTINO` sintéticos y
exija el fichero existente intacto, más el mutante que quita
`--ignore-existing`. Necesita `rsync`, que en este entorno solo existe dentro de
WSL: en Windows el test se saltaría, y una guardia que no corre no guarda.
