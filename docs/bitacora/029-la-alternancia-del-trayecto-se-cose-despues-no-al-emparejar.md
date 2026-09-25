---
id: 029
titulo: La alternancia del trayecto se cose después de rastrear, no al emparejar; cruzar el trayecto al emparejar recuperaba la 25 pero bajaba hasta un 34 % las trayectorias urbanas, y el cosido la sube un 16 % en pasos sin mover las urbanas ni el indicador de intercambios
fecha: 2026-09-25
tipo: tecnica
capa: tracking
capitulo: metodologia
impacto: medio
estado: mitigado
evidencia: uv run dvc repro prepare && uv run python -m project.analysis.medir_rutas lineas; banco con auditoria/banco_tracker.py --tracker --real 2026-08-20 2026-08-27
trampa: 014
---

## Qué se observó

La entrada 026 atribuyó el resto de la pérdida de la línea 25 a una fuente que
publica el trayecto contrario para el mismo bus a mitad de ruta. El tracker
agrupa por (línea, trayecto), así que cada racha con el otro texto parte al bus
en tres: A, un fragmento F con el otro texto y C. `tolerar_hueco` puentea A→C
si la racha dura como mucho dos sondeos y el bus no se aleja más de
`SALTO_MAX_M` (800 m); a velocidad de carretera, o con rachas de tres sondeos o
más, no lo consigue.

**Primer diseño, descartado: cruzar el trayecto al emparejar.** Una segunda
etapa enlazaba lo que la clave dejaba suelto, a menos de un radio de la posición
predicha. Trayectorias por línea el 20/08 y el 27/08:

| radio | 25 | 99 | C3 | 93 |
|---|---|---|---|---|
| sin cruzar | 995 · 1.274 | 281 · 296 | 444 · 466 | 266 · 230 |
| 100 m | 1.006 · 1.255 | 283 · 294 | 442 · 460 | 268 · 230 |
| 400 m | 804 · 1.139 | 261 · 237 | 400 · 411 | 256 · 230 |
| 800 m | 657 · 989 | 256 · 223 | 399 · 410 | 247 · 229 |

Con 100 m la 25 no cambia: a 40-60 km/h y con curvas la predicción falla por
unos 350 m. Con más radio, las urbanas caen hasta un 25 %. Una versión anterior,
sin cortar después los cambios que se mantienen, enlazaba a través de las
cabeceras y bajaba la 93 y la C3 un **34 %**. Hungarian empareja con cualquier
candidato dentro de la puerta antes que dejar uno suelto, y los enlaces malos
arrastran a los emparejamientos siguientes.

**Diseño adoptado: coser después (`tracking._coser_alternancias`).** El
emparejamiento no cambia. Sobre la salida se une A + F + C cuando se cumplen
todas estas condiciones:

- F dura como mucho `RACHA_ALTERNANCIA_MAX` (4) sondeos;
- A acaba justo antes de F y C empieza justo después, con el texto de A;
- cada enlace cabe en la puerta física de un sondeo;
- el candidato es el más cercano a su posición predicha y saca
  `MARGEN_COSIDO_M` (100 m) al segundo;
- pasar por F no alarga el camino de A a C más de `RODEO_MAX_M` (30 m);
- ningún otro F reclama la misma A o la misma C;
- la trayectoria resultante no tiene dos filas en un sondeo.

F recupera el texto de A. El publicado se conserva en `trayecto_publicado`.

Tres de esas condiciones salieron de errores encontrados sobre la captura real:

- **El rodeo.** Con 100 m se cosía un bus de otro sentido a 600 m, con ida y
  vuelta dentro de la puerta (línea 99, 27/08, 06:47).
- **Que A no tenga filas dentro de F.** Si `tolerar_hueco` ya había puenteado,
  A podía ser otro bus que seguía su marcha, y quedaban dos buses intercalados
  en una trayectoria (línea 31, 20/08, 06:37).
- **Que dos F no compartan A.** Dos buses del mismo sondeo publicando el otro
  sentido junto a uno que no lo hacía se cosían los dos (línea 25, 27/08, 12:04).

Banco sobre jornada entera, todas las líneas, frente al tracker de `e2c08c4`:

| | 20/08 | 27/08 |
|---|---|---|
| trayectorias | 6.643 → 6.196 | 6.596 → 6.178 |
| de un punto | 819 → **471** | 814 → **470** |
| duración mediana | 29,8 → 31,5 min | 27,6 → 29,7 min |
| `ida_vuelta` | 236 → 238 | 232 → 230 |
| sobre la puerta | 0 → 0 | 0 → 0 |

Tras `dvc repro prepare`, frente a la salida de `e2c08c4`:

- **Línea 25:** 7.413 → **8.594** pasos (+15,9 %).
- **Línea 24:** 13.596 → 13.716 (+0,9 %).
- **Resto de líneas con más de 20.000 pasos:** +0,0 a +0,8 %.
- **Totales:** 1.574.436 → 1.577.736 pasos; 71.537 → 71.658 asignados;
  60.424 → 51.376 tramos cortos.
- **Invariante:** 0 trayectorias con dos filas en un sondeo.
- **Texto corregido:** 13.739 posiciones (0,13 %). La 25 es la de mayor
  proporción (1,45 % de las suyas). La 99 aporta 2.089: **la alternancia no es
  solo de la 25**. La medida «limpia» de la 026 la infravalora en las líneas
  densas, porque descuenta todo cambio con otro bus a menos de 700 m.

## Cómo se midió

```bash
uv run python auditoria/banco_tracker.py --tracker CAND.py --real 2026-08-20 2026-08-27 --sin-sim --etiqueta X
uv run dvc repro prepare
uv run python -m project.analysis.medir_rutas lineas
```

Las trayectorias por línea del primer diseño rastrean solo seis líneas (24, 25,
31, 99, 93 y C3), siempre el mismo subconjunto. El «antes» por línea se leyó de
la caché de DVC con los `md5` de `dvc.lock` en `e2c08c4`. Cada `ida_vuelta` nuevo
se atribuyó a su trío de filas: los que subían eran exactamente los que cruzaban
una unión cosida, y esos casos dieron las tres condiciones de arriba.

En simulación (`simular_flota(p_alternancia=0,05)`, un 8,6 % de pasos con el
otro texto) se separan dos cosas:

- **Eficacia**, con 2 buses por línea: como mucho un trozo de más por dentro en
  tres semillas, y ≤ 1 % de posiciones con el sentido mal, frente al 4-10 %
  publicado.
- **Seguridad**, en la flota densa (7-8 buses por línea en ~2 km), donde el
  cosido tiene que abstenerse: los mismos saltos y trayectorias mixtas que sin
  coser, en cinco semillas.
- **Semillas reservadas del banco**, miradas una vez: idénticas a `e2c08c4` en
  los siete escenarios. Ninguno tiene alternancia, y el cosido no toca nada
  donde no la hay.

## Por qué importa

- Los fragmentos de un punto eran casi todos alternancia: bajan un 42 %.
- La 25 mejora, pero poco: 8.594 pasos con el 2,9 % de las posiciones, un 0,54 %
  del total. Con la 24, las dos costeras son el 1,41 % de los pasos, frente al
  0,33 % antes de las entradas 028 y 029. El sesgo se reduce, no desaparece.
- Descartar el primer diseño tiene su propia lección: cualquier relajación de
  la clave al emparejar se paga en todas las líneas, aunque solo haga falta en
  una.

## Qué se hizo / qué queda abierto

Hecho:

- `_coser_alternancias` y la columna `trayecto_publicado`, también en
  `emt_tracked`.
- `p_alternancia` en `simular_flota`.
- Tests de eficacia, de seguridad y de etiquetado
  (`test_la_alternancia_del_trayecto_no_corta_el_viaje`).
- Mutantes 076-078.
- Trampa 014, cerrada: la fuente alterna el trayecto a mitad de ruta.

Abierto:

- Qué más pierde la 25: rachas de 5 o más sondeos, fragmentos de dos buses que
  el emparejamiento ya encadenó dentro del grupo del otro texto, y su caída de
  publicación desde el 09/09 (entrada 025).

## Para la memoria

> La fuente publica en ocasiones el sentido contrario para un mismo vehículo a
> mitad de recorrido, durante uno a cuatro sondeos. Como el emparejamiento se
> restringe a vehículos de la misma línea y sentido, cada alternancia divide la
> trayectoria en tres fragmentos. Permitir el cambio de sentido durante el
> emparejamiento recuperaba las trayectorias afectadas, pero enlazaba vehículos
> de sentidos opuestos en las líneas urbanas y reducía su número de trayectorias
> hasta un 34 %. Se optó por corregir a posteriori: se unen tres fragmentos
> consecutivos cuando el intermedio es breve, los extremos comparten sentido, los
> enlaces son físicamente posibles e inequívocos y el recorrido por el fragmento
> intermedio no se desvía más de 30 metros. El sentido publicado se conserva
> aparte. La corrección reduce un 42 % las trayectorias de una sola posición y
> aumenta un 16 % los pasos etiquetados de la línea más afectada, sin variar más
> de un 0,8 % los de las demás líneas ni el indicador de intercambios de
> identidad.
