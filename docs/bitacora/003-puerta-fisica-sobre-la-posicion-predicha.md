---
id: 003
titulo: La puerta de velocidad se evaluaba sobre la posición predicha y no sobre el desplazamiento real; colaban hasta 46 emparejamientos imposibles por ventana de 150 sondeos
fecha: 2026-09-01
tipo: anomalia
capa: tracking
capitulo: metodologia
impacto: alto
estado: resuelto
evidencia: uv run python -m project.analysis.medir_reales --hora 17 --rev 800b9e1
trampa: 008
---

## Qué se observó

El emparejador restringe las asignaciones con una puerta física:
`tope = min(SALTO_MAX_M, VEL_MAX_KMH / 3,6 · dt)`, es decir 800 m o lo que un
autobús puede recorrer a 70 km/h en el refresco, lo que sea menor —para
`dt = 30 s`, 583 m.

Esa puerta se aplicaba sobre la matriz de distancias a la posición **predicha**.
Con `predictivo=True` la predicción y la posición real no son la misma cosa, así
que un candidato lejano podía quedar dentro de la puerta por estar cerca de una
extrapolación, y aceptarse un desplazamiento real que el tope prohíbe.

Medido sobre la captura del 16/08/2026, comparando el tracker de la revisión
`800b9e1` con el actual sobre las mismas ventanas:

| ventana (150 sondeos) | emparejamientos | > puerta de velocidad | vel. máx. | dist. máx. |
|---|---|---|---|---|
| 00 UTC · antes | 7.060 | 24 | 99,6 km/h | 807 m |
| 00 UTC · después | 7.039 | **0** | 68,8 km/h | 577 m |
| 08 UTC · antes | 15.747 | 36 | 99,7 km/h | 859 m |
| 08 UTC · después | 15.710 | **0** | 69,6 km/h | 599 m |
| 17 UTC · antes | 18.543 | 46 | 110,2 km/h | 949 m |
| 17 UTC · después | 18.497 | **0** | 70,0 km/h | 607 m |

Dos matices sobre la cifra que circulaba en el docstring de `tracking.py`
("10 en 150 snapshots, el mayor de 957 m, con `vel_kmh` de hasta 100"):

- **Se quedaba corta por contar la magnitud equivocada.** Contaba
  desplazamientos por encima de `SALTO_MAX_M` (800 m), pero con `dt ≈ 30 s` la
  puerta efectiva no es esa: son los 583 m que impone `VEL_MAX_KMH`. Contando
  violaciones de la puerta real, no son ~10 sino **24 a 46 por ventana**, según
  la hora.
- **Depende de la franja.** A las 17 UTC hay 46; a medianoche, 24 sobre menos de
  la mitad de emparejamientos. El máximo observado es de 110,2 km/h, por encima
  del 100 citado.

Coste del arreglo: **21 a 46 emparejamientos menos por ventana** (−0,3 %). Son
cadenas que ahora se rompen en vez de cerrarse con un salto imposible.

## Cómo se midió

```bash
uv run python -m project.analysis.medir_reales --hora 17 --rev 800b9e1   # antes
uv run python -m project.analysis.medir_reales --hora 17                 # después
```

`--rev` carga `src/project/tracking.py` tal y como estaba en esa revisión de git
y mide con él, así que la cifra de "antes" es reejecutable indefinidamente sin
revertir nada ni copiar el código viejo dentro del medidor. `puerta()` de
`src/project/analysis/medir_reales.py` cuenta emparejamientos por encima de
`SALTO_MAX_M` y por encima de `VEL_MAX_KMH`, y reporta los máximos.

Comprobación del instrumento: las dos ejecuciones leen exactamente los mismos
parquets y difieren solo en el módulo cargado. El número de emparejamientos baja
al arreglar, que es la dirección correcta —una puerta más estricta no puede
producir más asignaciones—; si hubiera subido, el medidor estaría mintiendo.

## Por qué importa

Un emparejamiento por encima de la puerta no lanza ninguna excepción: produce una
fila con `dist_m` y `vel_kmh` perfectamente formados. El síntoma es un autobús
urbano a 110 km/h, que solo se ve si alguien mira el máximo de una columna que
nadie mira.

El daño va por dos vías:

1. **La velocidad instantánea es una variable candidata del modelo.** Si el
   tracker inventa saltos, inyecta valores extremos en la distribución de la
   variable que mejor correlaciona con la congestión, que es justo la hipótesis
   del trabajo.
2. **Un salto imposible es un intercambio de identidad disfrazado.** El vehículo
   real de destino queda además libre para heredar otro id. Por la entrada
   [001](001-error-identidad-se-mide-en-trayectorias.md), eso contamina la
   trayectoria a partir de ese punto de forma permanente.

Y hay una lección de método propia: **la restricción y el criterio de coste no
tienen por qué evaluarse sobre la misma magnitud**. Aquí el coste debe medirse
contra la predicción —es lo que hace bueno al tracker predictivo, entrada 001—
pero la puerta es una afirmación física sobre lo que un autobús puede hacer en
30 segundos, y eso solo se puede comprobar sobre el desplazamiento real. Usar
una única matriz para las dos cosas es la simplificación natural, y es la que
falla.

## Qué se hizo / qué queda abierto

Hecho:

- `_emparejar_grupo` calcula ahora dos matrices: la de coste contra la posición
  predicha y la de desplazamiento real, y la puerta exige que **ambas** estén
  por debajo del tope.
- Guardias en `tests/test_tracking_identidad.py`:
  `test_ningun_desplazamiento_supera_la_puerta_fisica` sobre los cuatro
  escenarios deterministas y `test_la_puerta_fisica_se_respeta_en_la_flota_simulada`
  sobre la flota sintética. Las dos comprueban `dist_m` y `vel_kmh` contra las
  constantes del módulo, no contra números copiados.
- Ficha [008](../../.claude/trampas/008-puerta-fisica-sobre-posicion-predicha.md)
  del registro de trampas, `cerrada` con esas dos guardias: el fallo no da la
  cara y reutilizar la matriz de coste como puerta es lo que haría cualquiera.

Abierto:

- **Ninguna guardia corre sobre datos reales**, que es donde apareció. Los tests
  usan escenarios y simulación porque `data/` no está en el repo. La
  comprobación sobre la captura hay que lanzarla a mano con el comando de
  arriba.
- **Las cadenas rotas no se miden.** El arreglo elimina 21–46 emparejamientos por
  ventana; se sabe cuántos desaparecen, no en cuántas trayectorias más se
  fragmenta la flota ni si eso deja viajes demasiado cortos para etiquetar.

## Para la memoria

> El emparejamiento entre sondeos consecutivos se restringe mediante una puerta
> física que descarta toda asignación cuyo desplazamiento implique una velocidad
> superior a 70 km/h o un salto mayor de 800 metros. En la primera
> implementación, esa restricción se evaluaba sobre la matriz de distancias
> empleada como coste, que se calcula contra la posición extrapolada del
> vehículo y no contra su posición observada. Al no coincidir ambas magnitudes,
> la puerta admitía asignaciones cuyo desplazamiento real excedía el límite.
>
> El efecto se cuantificó sobre la captura del 16 de agosto de 2026 comparando
> ambas versiones del emparejador sobre idénticas ventanas de 150 sondeos: la
> versión inicial aceptaba entre 24 y 46 asignaciones por ventana con velocidades
> implícitas superiores al límite, alcanzando los 110,2 km/h y desplazamientos de
> hasta 949 metros, valores incompatibles con un autobús urbano. La corrección
> —exigir que tanto la distancia a la posición predicha como el desplazamiento
> real respeten el tope— elimina la totalidad de esos casos, a costa de un 0,3 %
> menos de asignaciones, correspondientes a cadenas que se interrumpen en lugar
> de cerrarse con un salto imposible.
>
> La observación relevante desde el punto de vista metodológico es que el
> criterio de coste y la restricción de admisibilidad responden a preguntas
> distintas: el primero mide plausibilidad relativa frente a un modelo de
> movimiento, mientras que la segunda expresa una imposibilidad física. Evaluar
> ambas sobre la misma magnitud resulta natural en la implementación y es
> precisamente lo que introduce el error, que además no se manifiesta como fallo
> sino como valores atípicos en una variable derivada.
