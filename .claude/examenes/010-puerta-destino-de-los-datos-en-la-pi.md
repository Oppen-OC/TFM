---
id: 010
tema: puerta · ayuda del despliegue en la Pi con host y ruta de datos caducados
fecha: 2026-11-09
fuentes: raspberry:deploy_pi/instalar.sh (DATOS), raspberry:deploy_pi/README.md, raspberry:demo/collect.py (mostrar_estado), docs/bitacora/044, .claude/trampas/016-la-pi-no-tiene-el-corpus-entero.md
estado: contestado
ronda: 2
nota: —
---

## P1 · un despliegue sin `DATOS`
<!-- concepto: destino-del-colector-parte-el-corpus -->

En la Pi, el colector escribe hoy en `/srv/tfm-sd`. Supón que alguien despliega
siguiendo `deploy_pi/README.md` al pie de la letra, con
`sudo bash deploy_pi/instalar.sh` sin `DATOS`. ¿Dónde empieza a escribir el
colector, qué le pasa al corpus y por qué no lo vería un `--status` lanzado con
el comando que trae ese mismo README?

**Respuesta:**

> Empezaría a escribir en data/raw, el corpus se reproduciría de 0.

**Veredicto:** a-medias

_Rondas._ Ronda 1, a-medias. `data/raw/` es la disposición del repo en el PC.
En la Pi, el colector escribe donde le dice el servicio, y el servicio lo monta
`instalar.sh`: mira qué hace cuando no le pasan `DATOS`, y qué es ese directorio
en esta Pi según la bitácora 044. «Se reproduciría de 0» tampoco encaja, porque
no se borra nada. Piensa dónde acaba viviendo cada parte de la captura y qué
trae el siguiente `pull_data.sh` desde `/srv/tfm-sd` (trampa 016). La tercera
parte está en blanco: ¿qué latido lee el `--status` del README y cuál escribe el
colector?
