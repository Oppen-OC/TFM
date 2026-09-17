"""Reconstrucción de identidad de vehículo: el problema central de esta fuente.

La capa de la EMT NO publica identificador de vehículo. El campo `gid` es un
autoincrement de una tabla que se trunca y reinserta entera en cada refresco:
entre dos sondeos consecutivos, la intersección de gids es exactamente cero
(verificado empíricamente el 15/08/2026: bloques [...987635-987800] y
[...987801-987967], contiguos y disjuntos).

Tampoco sirve la posición dentro del bloque: emparejando por rango sólo
coincide la línea y el trayecto en un 32-73 % de los casos, con
desplazamientos de hasta 5 km entre sondeos. Descartado.

Lo que sí funciona: asignación global (Hungarian) entre los vehículos de dos
snapshots consecutivos, restringida a la misma (línea, trayecto) y con una
puerta de velocidad máxima. Sobre datos reales de un sábado a las 21:15 da
0 huérfanos y un desplazamiento mediano de ~50 m por refresco de 30 s.

La asignación necesita una predicción de dónde estará cada vehículo, y la
predicción necesita una velocidad que en la PRIMERA transición de cada
trayectoria todavía no existe. Ese arranque en frío es el punto débil del
método, no el cruce de dos buses: ver `_sembrar_por_centroide`. Sobre la
captura del 16/08/2026, en horario de servicio, el 1,9 % de las posiciones
tiene un compañero de su misma (línea, trayecto) a menos de un paso de
refresco (125 m a 15 km/h) y el 58 % está en grupos de tres o más vehículos:
raro por posición, pero unas 7.000 situaciones ambiguas al día, y cada una mal
resuelta contamina la trayectoria entera. El 55 % que decía esta nota era con
vecino de CUALQUIER línea a 250 m, que el emparejador no puede confundir
porque agrupa por (línea, trayecto):
`docs/bitacora/002-el-empate-de-grupo-es-raro-no-normal.md`.

Límite conocido, no resoluble con posiciones: si los vehículos de un grupo
están equiespaciados sobre una ruta en anillo, permutar sus identidades es una
simetría de lo observado. Ningún método que sólo mire posiciones lo distingue.

Esto es ETL de verdad, no un `pd.read_csv`. Es el capítulo de la memoria que
convierte el trabajo en un TFM.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from project.ingest.sources import haversine_m

VEL_MAX_KMH = 70.0  # un bus urbano por encima de esto es un error de asignación
SALTO_MAX_M = 800.0  # techo duro de desplazamiento entre snapshots
# Tope EN SEGUNDOS de lo que `tolerar_hueco` puede puentear. La tolerancia se
# expresa en sondeos, pero un sondeo no siempre dura 30 s: durante la parada de
# 445 s del colector del 27/08/2026, «dos sondeos» eran 7,5 min, y la puerta
# física satura en SALTO_MAX_M a partir de 41 s, así que a partir de ahí deja de
# restringir nada. 120 s es lo que dura el hueco que se quiere puentear a
# cadencia nominal.
HUECO_MAX_S = 120.0
# Suavizado de intercambios (`_suavizar_intercambios`). Solo se revisan pares de
# posiciones del mismo sondeo y grupo a menos de este radio: más lejos que dos
# pasos largos de refresco no hay intercambio que deshacer.
RADIO_SUAVIZADO_M = 400.0
# Mejora mínima, en metros de cambio de velocidad por paso de 30 s, para aceptar
# un intercambio. Por debajo, la diferencia es del orden del ruido de posición
# (p90 de 6,7 m entre pasos de un bus parado, bitácora 013) y no hay evidencia.
MEJORA_MIN_M = 10.0
# Coste extra de suponer que un bus se ha detenido, en metros de recorrido. Lo
# paga la hipótesis «parado» frente a «sigue a su ritmo» para que, en igualdad,
# gane la predicción: con 0 el ruido decidiría. Sin esta hipótesis, un bus parado
# al que otro adelanta se resuelve mal aunque la abscisa esté.
PENALIZACION_PARADA_M = 15.0
# Lo que tiene que ahorrar un adelantamiento para aceptarse. Sobre el recorrido,
# intercambiar dos identidades es ponerlas en el orden contrario: un
# adelantamiento. Existen —un bus parado al que otro pasa—, pero son raros, y sin
# este coste ganan por márgenes de metros: un bus que arranca tras una parada
# «avanza» 187 m de golpe y el intercambio sale 2 m más barato que la verdad.
#
# El techo no lo pone el ajuste sino un fenómeno real: en el escenario de
# adelantamiento de `tests/test_tracking_abscisa.py` la asignación correcta gana
# por 135 m, así que por encima de eso el tracker dejaría de reconocer
# adelantamientos. Barrido sobre la flota de trazados reales, semillas de ajuste:
# 0 m -> 86 saltos, 50 -> 74, 100 -> 64, 120 -> 64 pero ya rompe el
# adelantamiento. 100 deja margen.
PENALIZACION_CRUCE_M = 100.0
_DT_REF_S = 30.0


def _emparejar_grupo(
    a: pd.DataFrame, b: pd.DataFrame, tope: np.ndarray
) -> list[tuple[int, int, float]]:
    """Asignación óptima entre los vehículos de a y los de b (misma línea/trayecto).

    `tope` es el desplazamiento máximo admisible de CADA fila de `a`, no un
    escalar: con `tolerar_hueco` cada candidato arrastra un hueco distinto y por
    tanto una puerta distinta.

    Si las dos partes traen abscisa sobre el trazado —`abs_pred` en `a`,
    `abscisa_m` en `b`—, el coste se mide SOBRE EL RECORRIDO y no en el plano.
    Dos buses de la misma línea y sentido van por la misma calle en el mismo
    orden: en una horquilla o una curva cerrada, el que va 100 m por delante
    queda a 30 m en línea recta y la extrapolación plana apunta al vecino. Donde
    falte la abscisa —fuera de ruta o ambigua— se usa el plano, fila a fila.
    """
    if a.empty or b.empty:
        return []

    blat = b["lat"].to_numpy()[None, :]
    blon = b["lon"].to_numpy()[None, :]

    # Se empareja contra la posición PREDICHA de a (si el llamante la aportó)
    d = haversine_m(
        a.get("lat_pred", a["lat"]).to_numpy()[:, None],
        a.get("lon_pred", a["lon"]).to_numpy()[:, None],
        blat,
        blon,
    )
    # ...pero la puerta física se mide sobre el desplazamiento REAL. Aplicarla
    # sobre `d` deja pasar saltos que el tope prohíbe en cuanto la predicción
    # está lejos: sobre 150 snapshots reales colaban 10 por encima de
    # SALTO_MAX_M, el mayor de 957 m, con `vel_kmh` de hasta 100.
    d_real = haversine_m(
        a["lat"].to_numpy()[:, None], a["lon"].to_numpy()[:, None], blat, blon
    )

    plano = d
    if "abs_pred" in a.columns and "abscisa_m" in b.columns:
        s_pred = a["abs_pred"].to_numpy()[:, None]
        s_ahora = a["abscisa_m"].to_numpy()[:, None]
        s_b = b["abscisa_m"].to_numpy()[None, :]
        sobre_ruta = ~np.isnan(s_pred) & ~np.isnan(s_ahora) & ~np.isnan(s_b)
        # Dos hipótesis sobre el recorrido: el bus sigue a su ritmo, o se ha
        # detenido. Sin la segunda, un bus que para en el instante en que otro lo
        # alcanza produce un EMPATE EXACTO igual que el del arranque en frío
        # (trampa 007): correcto 150 + 0, intercambiado 60 + 90. En el plano esta
        # misma idea no bastaba —la probé y movía los errores de sitio, bitácora
        # 015—; sobre una recta sí, porque «parado» es una hipótesis limpia.
        sigue = np.abs(s_b - s_pred)
        parado = np.abs(s_b - s_ahora) + PENALIZACION_PARADA_M
        plano = np.where(sobre_ruta, np.minimum(sigue, parado), d)

    # La puerta sigue midiéndose en el plano y sobre el desplazamiento real: es
    # una afirmación física sobre lo que un autobús puede recorrer (trampa 008).
    t = tope[:, None]
    coste = np.where((d <= t) & (d_real <= t), plano, 1e9)

    fi, ci = linear_sum_assignment(coste)
    if "abs_pred" in a.columns and "abscisa_m" in b.columns:
        fi, ci = _deshacer_cruces(fi, ci, coste, s_ahora.ravel(), s_b.ravel())
    return [
        (int(a.index[i]), int(b.index[j]), float(d[i, j]))
        for i, j in zip(fi, ci)
        if coste[i, j] < 1e9
    ]


def _deshacer_cruces(
    fi: np.ndarray, ci: np.ndarray, coste: np.ndarray, s_a: np.ndarray, s_b: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Deshace los adelantamientos que no se pagan (`PENALIZACION_CRUCE_M`).

    Dos vehículos del mismo grupo van por la misma calle en un orden. Si la
    asignación invierte ese orden está afirmando que uno adelantó al otro, y eso
    hay que pagarlo: se deshace salvo que cruzarse salga más barato por encima
    del margen. Con el margen a 0 vuelve a decidir la diferencia de metros, que
    es lo que falla cuando un bus arranca tras una parada.
    """
    fi, ci = list(fi), list(ci)
    for _ in range(len(fi)):
        mejora = False
        for u in range(len(fi)):
            for v in range(u + 1, len(fi)):
                i, j, k, ell = fi[u], ci[u], fi[v], ci[v]
                if np.isnan(s_a[i]) or np.isnan(s_a[k]):
                    continue
                if np.isnan(s_b[j]) or np.isnan(s_b[ell]):
                    continue
                cruzan = (s_a[i] - s_a[k]) * (s_b[j] - s_b[ell]) < 0
                if not cruzan:
                    continue
                actual = coste[i, j] + coste[k, ell]
                recto = coste[i, ell] + coste[k, j]
                if recto <= actual + PENALIZACION_CRUCE_M:
                    ci[u], ci[v] = ell, j
                    mejora = True
        if not mejora:
            break
    return np.array(fi, dtype=int), np.array(ci, dtype=int)


def _sembrar_por_centroide(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Predice las filas de `a` que todavía no tienen velocidad propia.

    En su primera transición un vehículo no tiene paso anterior, así que la
    predicción cae a su posición actual y el emparejamiento vuelve a ser vecino
    más cercano puro. Con buses colineales a velocidad parecida eso no es un
    caso difícil: es un EMPATE EXACTO. Convoy a 15 km/h separado 120 m, paso de
    125 m -> correcto 125+125 = 250, intercambio 5+245 = 250. Hungarian
    desempata por orden de fila, y el error no se queda ahí: escribe un `_plat`
    equivocado que envenena la predicción del paso siguiente.

    El desplazamiento del centroide estima el movimiento de conjunto del grupo
    SIN conocer la correspondencia, que es justo lo que rompe el empate. Solo se
    aplica cuando el grupo no cambia de tamaño: si entran o salen vehículos, el
    centroide se mueve por el censo y no por el tráfico.
    """
    if a.empty or len(a) != len(b):
        return a
    sin_velocidad = a["_plat"].isna()
    if not sin_velocidad.any():
        return a
    a = a.copy()
    a.loc[sin_velocidad, "lat_pred"] = a.loc[sin_velocidad, "lat"] + (
        b["lat"].mean() - a["lat"].mean()
    )
    a.loc[sin_velocidad, "lon_pred"] = a.loc[sin_velocidad, "lon"] + (
        b["lon"].mean() - a["lon"].mean()
    )
    if "abs_pred" in a.columns:
        a.loc[sin_velocidad, "abs_pred"] = a.loc[sin_velocidad, "abscisa_m"] + (
            b["abscisa_m"].mean() - a["abscisa_m"].mean()
        )
    return a


def _cambio_de_velocidad(xs, ys, ts, filas: list[int]) -> float:
    """Suma de los cambios de velocidad a lo largo de `filas`, en metros por paso de 30 s.

    Es la segunda diferencia de la posición escrita en segundos, no en pasos de
    sondeo: con cadencia irregular la de pasos lee un hueco como una aceleración
    (trampa 009).
    """
    if len(filas) < 3:
        return 0.0
    dt = np.diff(ts[filas])
    dt = np.where(dt > 0, dt, _DT_REF_S)
    vx, vy = np.diff(xs[filas]) / dt, np.diff(ys[filas]) / dt
    return float(np.hypot(np.diff(vx), np.diff(vy)).sum() * _DT_REF_S)


def _dentro_de_la_puerta(lat, lon, ts, filas: list[int]) -> bool:
    """La misma puerta que el emparejamiento: haversine y reloj de sondeo (trampa 008)."""
    if len(filas) < 2:
        return True
    d = haversine_m(lat[filas][:-1], lon[filas][:-1], lat[filas][1:], lon[filas][1:])
    dt = np.diff(ts[filas])
    dt = np.where(dt == 0, _DT_REF_S, dt)
    tope = np.minimum(SALTO_MAX_M, VEL_MAX_KMH / 3.6 * np.maximum(dt, 1.0))
    return bool((d <= tope).all())


def _suavizar_intercambios(df: pd.DataFrame) -> pd.DataFrame:
    """Deshace intercambios de identidad mirando un sondeo hacia delante.

    El emparejamiento decide sondeo a sondeo con un modelo de velocidad
    constante. Cuando dos buses del mismo grupo coinciden a menos de un paso en
    el instante en que uno SE DETIENE o GIRA, la extrapolación apunta al otro y el
    intercambio sale más barato que la asignación correcta. Sobre la flota
    simulada con paradas y giros al ritmo real (29 % de pasos parados, bitácora
    013), dos de cada tres de esos intercambios se deshacen solos en el sondeo
    siguiente, y el resto se queda.

    Decidir un sondeo es no poder usar el siguiente, que es justo el que delata
    el error. Aquí se usa: con las trayectorias ya construidas, cada par de
    posiciones del mismo (sondeo, línea, trayecto) a menos de
    `RADIO_SUAVIZADO_M` prueba dos movimientos —cambiar entre sí solo esas dos
    posiciones (el intercambio que se deshizo) o cambiar las colas desde ahí (el
    que no)— y se acepta el que reduzca el cambio de velocidad en ±2 pasos
    alrededor en más de `MEJORA_MIN_M`, siempre que ningún desplazamiento
    resultante salga de la puerta física.

    No rompe cadenas ni crea trayectorias: solo reasigna posiciones entre
    trayectorias que ya existen. Romper la cadena ante la duda está medido como
    peor (trampa 007).

    Límites que quedan: un intercambio en el último sondeo no tiene sondeo
    siguiente que lo delate, y dos buses que arrancan a la vez desde parados no
    tienen velocidad previa que los distinga.
    """
    lat0 = float(df["lat"].mean())
    lat, lon = df["lat"].to_numpy(), df["lon"].to_numpy()
    xs = (lon - lon.mean()) * 111_320 * np.cos(np.radians(lat0))
    ys = (lat - lat0) * 111_320
    # Reloj POR SONDEO, el mismo con el que el emparejamiento calcula `dt_s`: las
    # filas de un sondeo no siempre traen el mismo `ts_utc`, y medir por fila
    # produce pasos de 8 s o negativos donde el tracker ve 30.
    reloj = df.groupby("snapshot_id")["ts_utc"].transform("max")
    ts = (reloj - reloj.min()).dt.total_seconds().to_numpy()
    snap = df["snapshot_id"].to_numpy()
    # Con abscisa, el cambio de velocidad se mide SOBRE EL RECORRIDO. En el plano,
    # una horquilla —subir por una calle y volver por la paralela— parece un ida y
    # vuelta y el suavizado deshace emparejamientos correctos.
    #
    # Las filas sin abscisa fiable (fuera de ruta o ambiguas, un 7 % en real) se
    # SALTAN dentro de la ventana en vez de tirar la ventana entera al plano: son
    # posiciones sueltas, no un corte de la trayectoria, y con el reloj por sondeo
    # el hueco que dejan ya está contado en segundos.
    s = df["abscisa_m"].to_numpy() if "abscisa_m" in df.columns else None
    ceros = np.zeros(len(df))

    def coste(filas: list[int]) -> float:
        if s is not None:
            sobre_ruta = [f for f in filas if not np.isnan(s[f])]
            if len(sobre_ruta) >= 3:
                return _cambio_de_velocidad(s, ceros, ts, sobre_ruta)
        return _cambio_de_velocidad(xs, ys, ts, filas)

    tray: dict = {}
    for vid, idx in df.groupby("vehicle_id", sort=False).indices.items():
        tray[vid] = list(idx[np.argsort(snap[idx], kind="stable")])
    dueno: dict[int, tuple] = {}
    for vid, filas in tray.items():
        for pos, f in enumerate(filas):
            dueno[f] = (vid, pos)

    tocadas: set = set()
    for _ in range(3):
        mejoras = 0
        for _, g in df.groupby(["snapshot_id", "linea", "trayecto"], sort=False):
            if len(g) < 2:
                continue
            filas_g = g.index.to_numpy()
            gx, gy = xs[filas_g], ys[filas_g]
            cerca = np.hypot(gx[:, None] - gx[None, :], gy[:, None] - gy[None, :])
            ii, jj = np.nonzero(np.triu(cerca < RADIO_SUAVIZADO_M, k=1))
            for a, b in zip(filas_g[ii], filas_g[jj]):
                (u, iu), (v, iv) = dueno[a], dueno[b]
                if u == v:
                    continue
                tu, tv = tray[u], tray[v]
                lo_u, hi_u = max(iu - 2, 0), min(iu + 3, len(tu))
                lo_v, hi_v = max(iv - 2, 0), min(iv + 3, len(tv))
                antes = coste(tu[lo_u:hi_u]) + coste(tv[lo_v:hi_v])

                punto_u = tu[lo_u:iu] + [b] + tu[iu + 1 : hi_u]
                punto_v = tv[lo_v:iv] + [a] + tv[iv + 1 : hi_v]
                punto = coste(punto_u) + coste(punto_v)
                cola_u = tu[lo_u:iu] + tv[iv:hi_v]
                cola_v = tv[lo_v:iv] + tu[iu:hi_u]
                cola = coste(cola_u) + coste(cola_v)

                if antes - min(punto, cola) <= MEJORA_MIN_M:
                    continue
                if (
                    punto <= cola
                    and _dentro_de_la_puerta(lat, lon, ts, punto_u)
                    and _dentro_de_la_puerta(lat, lon, ts, punto_v)
                ):
                    tu[iu], tv[iv] = b, a
                    dueno[a], dueno[b] = (v, iv), (u, iu)
                elif _dentro_de_la_puerta(
                    lat, lon, ts, cola_u
                ) and _dentro_de_la_puerta(lat, lon, ts, cola_v):
                    tray[u], tray[v] = tu[:iu] + tv[iv:], tv[:iv] + tu[iu:]
                    for vid in (u, v):
                        for pos, f in enumerate(tray[vid]):
                            dueno[f] = (vid, pos)
                else:
                    continue
                tocadas.update((u, v))
                mejoras += 1
        if not mejoras:
            break

    if not tocadas:
        return df
    df = df.copy()
    for vid in tocadas:
        filas = tray[vid]
        df.loc[df.index[filas], "vehicle_id"] = vid
        df.at[df.index[filas[0]], "dist_m"] = np.nan
        df.at[df.index[filas[0]], "dt_s"] = np.nan
        for p, q in zip(filas[:-1], filas[1:]):
            df.at[df.index[q], "dist_m"] = float(
                haversine_m(lat[p], lon[p], lat[q], lon[q])
            )
            df.at[df.index[q], "dt_s"] = float(ts[q] - ts[p]) or _DT_REF_S
    return df


def rastrear(
    df: pd.DataFrame, predictivo: bool = True, tolerar_hueco: int = 2
) -> pd.DataFrame:
    """Añade `vehicle_id`, `dist_m`, `dt_s` y `vel_kmh` a las posiciones de la EMT.

    df debe traer: snapshot_id, linea, trayecto, lat, lon, ts_utc.

    Si trae además `abscisa_m` —metros recorridos sobre el trazado de su línea,
    que calcula `mapmatching.emparejar`—, el emparejamiento se hace sobre el
    recorrido en vez de sobre el plano. El orden de los buses de una misma
    (línea, trayecto) a lo largo de su calle es la información que no está en
    las coordenadas sueltas. Quien llama pone `NaN` donde la abscisa no es de
    fiar: fuera de ruta o ambigua, un 7 % de las posiciones reales
    (`docs/bitacora/016-el-map-matching-casa-con-el-gtfs.md`). El tracker no
    importa el GTFS: sigue funcionando sin esa columna, y ese es el motivo de
    pedirla en vez de calcularla.

    predictivo=False  -> emparejamiento por vecino más cercano puro.
    predictivo=True   -> se extrapola la posición con la velocidad del paso
                         anterior antes de emparejar. Reduce drásticamente los
                         intercambios de identidad cuando dos buses de la misma
                         línea se cruzan, que es el fallo dominante del método
                         ingenuo (medido en el autotest: de ~5 % de posiciones
                         mal asignadas a prácticamente cero). Además, al final
                         se deshacen los intercambios que delata el sondeo
                         siguiente (`_suavizar_intercambios`).

    tolerar_hueco     sondeos que un vehículo puede faltar sin perder su
                      identidad. Con 0 se exige presencia en el sondeo anterior,
                      que es el comportamiento histórico.

                      Un vehículo ausente NO es un vehículo que se va: la fuente
                      publica sondeos truncados (`data/raw/_TRUNCADOS.txt`) y
                      pierde vehículos sueltos. Tratar cada ausencia como una
                      baja partía el autobús medio en trozos de 10,5 min frente a
                      servicios de 30-60. Sobre la jornada del 27/08/2026, pasar
                      de 0 a 2 baja de 12.709 a 7.632 trayectorias y sube la
                      mediana a 21,1 min, sin descartar ninguna posición y sin
                      desplazamientos por encima de la puerta física.
                      Medición completa en `docs/bitacora/008-...`.

                      El puente se acota también en segundos (`HUECO_MAX_S`),
                      porque dos sondeos no siempre son 60 s.
    """
    df = df.sort_values(["snapshot_id"], kind="stable").reset_index(drop=True).copy()
    df["vehicle_id"] = pd.NA
    df["dist_m"] = np.nan
    df["dt_s"] = np.nan
    # Posición del paso anterior, para poder extrapolar, y cuánto duró ese paso.
    # La duración no es decorativa: sin ella la extrapolación se mide en pasos de
    # snapshot en vez de en segundos, y basta un sondeo que falte para que el
    # predictor lea un desplazamiento de dos pasos como si fuera de uno
    # (trampa 009).
    df["_plat"] = np.nan
    df["_plon"] = np.nan
    df["_pdt"] = np.nan
    con_abscisa = "abscisa_m" in df.columns
    if con_abscisa:
        df["_pabs"] = np.nan

    snaps = sorted(df["snapshot_id"].unique())
    # Reloj POR SONDEO, no por fila: con `tolerar_hueco` el dt de un candidato es
    # el que va desde el sondeo en que se le vio por última vez, que ya no tiene
    # por qué ser el anterior.
    reloj = df.groupby("snapshot_id")["ts_utc"].max()

    primero = df["snapshot_id"] == snaps[0]
    n0 = int(primero.sum())
    df.loc[primero, "vehicle_id"] = [f"v{i:05d}" for i in range(n0)]
    siguiente_id = n0

    # Candidatos vivos: índice de fila -> índice del sondeo en que se le vio.
    vivos: dict[int, int] = dict.fromkeys(df.index[primero], 0)

    for k in range(1, len(snaps)):
        cur = df[df["snapshot_id"] == snaps[k]]
        ahora = reloj[snaps[k]]
        # El predecesor inmediato compite SIEMPRE, pase lo que pase con el reloj:
        # así `tolerar_hueco=0` reproduce exactamente el comportamiento previo.
        # El tope en segundos solo acota el puente adicional.
        candidatos = [
            i
            for i, kk in vivos.items()
            if kk == k - 1
            or (
                k - kk <= 1 + tolerar_hueco
                and (ahora - reloj[snaps[kk]]).total_seconds() <= HUECO_MAX_S
            )
        ]
        prev = df.loc[candidatos].copy()
        if prev.empty:
            for ib in cur.index:
                df.at[ib, "vehicle_id"] = f"v{siguiente_id:05d}"
                siguiente_id += 1
                vivos[ib] = k
            continue

        dt_fila = np.array(
            [
                (ahora - reloj[snaps[vivos[i]]]).total_seconds() or 30.0
                for i in prev.index
            ],
            dtype=float,
        )
        prev["_dt"] = dt_fila
        prev["_tope"] = np.minimum(
            SALTO_MAX_M, VEL_MAX_KMH / 3.6 * np.maximum(dt_fila, 1.0)
        )

        if predictivo:
            # Modelo de velocidad constante: si venía moviéndose, seguirá. El
            # factor es la razón entre el paso que viene y el que produjo _plat,
            # no un 1 implícito: con la cadencia regular vale 1 y da el clásico
            # `2*lat - _plat`, pero ante un sondeo que falta evita extrapolar el
            # doble de lo que toca (trampa 009).
            tiene = prev["_plat"].notna()
            prev["lat_pred"] = prev["lat"]
            prev["lon_pred"] = prev["lon"]
            f = prev.loc[tiene, "_dt"] / prev.loc[tiene, "_pdt"]
            prev.loc[tiene, "lat_pred"] = prev.loc[tiene, "lat"] + f * (
                prev.loc[tiene, "lat"] - prev.loc[tiene, "_plat"]
            )
            prev.loc[tiene, "lon_pred"] = prev.loc[tiene, "lon"] + f * (
                prev.loc[tiene, "lon"] - prev.loc[tiene, "_plon"]
            )
            if con_abscisa:
                # Lo mismo sobre el recorrido: avanza lo que avanzó, escalado por
                # la duración del paso.
                sobre_ruta = tiene & prev["_pabs"].notna() & prev["abscisa_m"].notna()
                prev["abs_pred"] = prev["abscisa_m"]
                fs = prev.loc[sobre_ruta, "_dt"] / prev.loc[sobre_ruta, "_pdt"]
                prev.loc[sobre_ruta, "abs_pred"] = prev.loc[
                    sobre_ruta, "abscisa_m"
                ] + fs * (
                    prev.loc[sobre_ruta, "abscisa_m"] - prev.loc[sobre_ruta, "_pabs"]
                )
        else:
            prev["lat_pred"] = prev["lat"]
            prev["lon_pred"] = prev["lon"]
            if con_abscisa:
                prev["abs_pred"] = prev["abscisa_m"]

        emparejados_b: set[int] = set()
        for clave, gb in cur.groupby(["linea", "trayecto"], sort=False):
            ga = prev[(prev["linea"] == clave[0]) & (prev["trayecto"] == clave[1])]
            if predictivo:
                ga = _sembrar_por_centroide(ga, gb)
            for ia, ib, _ in _emparejar_grupo(ga, gb, ga["_tope"].to_numpy()):
                df.at[ib, "vehicle_id"] = df.at[ia, "vehicle_id"]
                df.at[ib, "dist_m"] = float(
                    haversine_m(
                        df.at[ia, "lat"],
                        df.at[ia, "lon"],
                        df.at[ib, "lat"],
                        df.at[ib, "lon"],
                    )
                )
                df.at[ib, "dt_s"] = float(prev.at[ia, "_dt"])
                df.at[ib, "_plat"] = df.at[ia, "lat"]
                df.at[ib, "_plon"] = df.at[ia, "lon"]
                df.at[ib, "_pdt"] = float(prev.at[ia, "_dt"])
                if con_abscisa:
                    df.at[ib, "_pabs"] = df.at[ia, "abscisa_m"]
                emparejados_b.add(ib)
                vivos.pop(ia, None)
                vivos[ib] = k

        # Los no emparejados son vehículos que entran en servicio (o huérfanos)
        for ib in cur.index:
            if ib not in emparejados_b:
                df.at[ib, "vehicle_id"] = f"v{siguiente_id:05d}"
                siguiente_id += 1
                vivos[ib] = k

        # Los candidatos que agotaron su tolerancia dejan de competir.
        vivos = {i: kk for i, kk in vivos.items() if k - kk <= tolerar_hueco}

    # Solo en modo predictivo: el ingenuo es la referencia sin nada que lo ayude.
    if predictivo:
        df = _suavizar_intercambios(df)
    df["vel_kmh"] = df["dist_m"] / df["dt_s"] * 3.6
    internas = ["_plat", "_plon", "_pdt"] + (["_pabs"] if con_abscisa else [])
    return df.drop(columns=internas)


def resumen(df: pd.DataFrame) -> dict:
    tr = df.dropna(subset=["dist_m"])
    largo = df.groupby("vehicle_id").size()
    return {
        "snapshots": df["snapshot_id"].nunique(),
        "posiciones": len(df),
        "trayectorias": df["vehicle_id"].nunique(),
        "long_media_trayectoria": round(float(largo.mean()), 1),
        "long_max_trayectoria": int(largo.max()),
        "tasa_emparejamiento": round(
            len(tr) / max(len(df) - df["snapshot_id"].nunique(), 1), 3
        ),
        "dist_m_p50": round(float(tr["dist_m"].median()), 1) if len(tr) else None,
        "dist_m_p90": round(float(tr["dist_m"].quantile(0.9)), 1) if len(tr) else None,
        "vel_kmh_p50": round(float(tr["vel_kmh"].median()), 1) if len(tr) else None,
        "vel_kmh_p90": round(float(tr["vel_kmh"].quantile(0.9)), 1)
        if len(tr)
        else None,
        "vel_kmh_max": round(float(tr["vel_kmh"].max()), 1) if len(tr) else None,
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    from project.config import settings

    ruta = Path(
        sys.argv[1] if len(sys.argv) > 1 else settings.curated_dir / "source=emt_buses"
    )
    df = pd.read_parquet(ruta)
    out = rastrear(df)
    for k, v in resumen(out).items():
        print(f"  {k:26} {v}")
    # Mismo nombre que el `outs` del stage `prepare` en dvc.yaml
    destino = settings.interim_dir / "emt_tracked.parquet"
    destino.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(destino, index=False)
    print(f"\n  -> {destino}")
