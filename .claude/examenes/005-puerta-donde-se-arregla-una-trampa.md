---
id: 005
tema: puerta · mapa del flujo con sus guardias
fecha: 2026-10-28
fuentes: trampas/014, trampas/001, src/project/tracking.py, src/project/ingest/sources.py
estado: corregido
ronda: 2
nota: 0/1
---

## P1 · dónde se arregla una trampa
<!-- concepto: donde-se-arregla-el-parser -->

La trampa 014 nace en la fuente —la EMT publica a ratos el sentido contrario
para un bus que sigue su marcha—, pero no se corrige al leer el payload, sino
después de reconstruir las trayectorias. ¿Por qué no puede arreglarse en el
parser, que parece lo natural, y qué tiene que existir antes para que la
mentira se pueda ver?

**Respuesta:**

> Por la agrupacion de linea trayecto del tracker. una vez agrupados no se
> puede corregir. Antes debe existir un historial de esa linea

**Veredicto:** a-medias

_Rondas._ Ronda 1, a-medias: acierta el qué —hace falta historia antes de poder
ver la mentira— y falla de quién es esa historia y en qué orden se corrige. No
basta la historia de la línea, y la corrección llega precisamente después de
agrupar, no antes. Mira la trampa 001 (qué no publica la fuente) y la sección
*Guardia* de la 014: cuándo se cose y qué tiene que saber quien cose. Contestó
con la ficha 014 abierta en el editor.

**Respuesta (ronda 2):**

> la historia es de un bus concreto de una linea concreta, esta es corregida
> por el tracker.

**Veredicto (ronda 2):** a-medias

_Respuesta completa._ Acierta de quién es la historia y quién corrige; falta el
porqué el parser no puede. El parser ve un payload, la foto de un sondeo, y la
EMT no publica qué bus es cuál: el `gid` identifica el refresco, no el vehículo
(001). Sin identidad no hay antes ni después del mismo bus, y un trayecto
invertido no se distingue de un bus que de verdad va en el otro sentido por la
misma calle. La identidad la infiere `rastrear`; solo con ella aparece el patrón
A + F + C —un sentido, 1-4 sondeos invertidos, vuelta al original sin dejar de
avanzar— que delata la mentira. Y no se corrige al agrupar: permitir el cambio
de trayecto al emparejar engancha buses de sentidos opuestos, hasta un 25 % menos
de trayectorias sin error visible. Se cose después, sobre trayectorias ya
formadas (`_coser_alternancias`). Además, `ingest/` no sabe de aguas abajo y
guarda el crudo tal cual. Una trampa se arregla donde vive la información para
verla, no donde nace el síntoma.
