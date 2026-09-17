"""Escenarios deterministas de identidad, con verdad-terreno construida a mano.

`test_tracking.py` mide el tracker sobre una flota aleatoria: buena guardia
estadística, pero el azar casi nunca coloca dos buses de la misma línea en la
configuración que rompe el emparejamiento. Aquí se colocan a propósito.

El caso que destapó los dos defectos de `tracking.py` es el convoy en fila
india: cuando la separación entre buses de una misma (línea, trayecto) es
comparable al paso por refresco, la asignación por vecino más cercano no es
"difícil", es un EMPATE EXACTO, y Hungarian desempata por orden de fila. Sobre
la captura real del 16/08/2026 está en esa situación el 1,9 % de las posiciones
en horario de servicio, y el 58 % está en grupos de tres o más vehículos, donde
puede darse (`docs/bitacora/002-el-empate-de-grupo-es-raro-no-normal.md`).

Las posiciones se construyen en metros sobre un eje recto y se convierten a
grados al final: así el escenario se lee y se razona en las mismas unidades en
las que están escritos VEL_MAX_KMH y SALTO_MAX_M.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from project import tracking
from project.analysis.simulacion import simular_flota
from project.tracking import SALTO_MAX_M, VEL_MAX_KMH, rastrear

LAT0, LON0 = 39.46, -0.37
M_POR_GRADO_LAT = 111_320.0
DT = 30.0  # refresco medido de la capa de la EMT: ~29 s


def _construir(
    trayectorias: dict[str, list[tuple[float, float]]],
    linea: str | dict[str, str] = "L1",
    trayecto: str = "Ida",
    seed: int = 3,
) -> pd.DataFrame:
    """Monta un df con la forma que consume `rastrear`, más la columna `verdad`.

    `trayectorias` mapea bus -> [(metros_a_lo_largo, metros_lateral), ...], una
    entrada por snapshot. Un `nan` significa que ese bus todavía no está (o ya
    no está) en servicio, y esa fila no se emite.
    """
    t0 = pd.Timestamp("2026-08-15T19:00:00Z")
    filas: list[dict] = []
    gid = 1000
    n_snaps = len(next(iter(trayectorias.values())))
    for s in range(n_snaps):
        for bus, puntos in trayectorias.items():
            along, lateral = puntos[s]
            if np.isnan(along):
                continue
            gid += 1
            filas.append(
                {
                    "snapshot_id": 1000 + s,
                    "gid": gid,
                    "linea": linea if isinstance(linea, str) else linea[bus],
                    "trayecto": trayecto,
                    "lat": LAT0 + lateral / M_POR_GRADO_LAT,
                    "lon": LON0 + along / (M_POR_GRADO_LAT * np.cos(np.radians(LAT0))),
                    "ts_utc": t0 + pd.Timedelta(seconds=s * DT),
                    "verdad": bus,
                }
            )
    # Barajar dentro del snapshot es deliberado: es lo que destapa un
    # reenganche por posición de fila en vez de por identidad (trampa 004).
    return (
        pd.DataFrame(filas)
        .sample(frac=1, random_state=seed)
        .sort_values("snapshot_id", kind="stable")
        .reset_index(drop=True)
    )


def _rastrear_con_verdad(sim: pd.DataFrame, predictivo: bool = True) -> pd.DataFrame:
    out = rastrear(sim.drop(columns=["verdad"]), predictivo=predictivo)
    out["verdad"] = sim["verdad"]
    return out


def _precision(out: pd.DataFrame) -> float:
    """Fracción de posiciones que caen en la trayectoria de su bus mayoritario."""
    aciertos = (
        out.groupby("vehicle_id")["verdad"]
        .agg(lambda s: s.value_counts().iloc[0])
        .sum()
    )
    return aciertos / len(out)


# --------------------------------------------------------------------------- #
# Constructores de escenario
# --------------------------------------------------------------------------- #
def _convoy(n_buses=4, v_kmh=15.0, sep_m=60.0, n_snaps=10):
    """Fila india: mismo sentido, misma velocidad, separación constante."""
    paso = v_kmh / 3.6 * DT
    return {
        f"bus{i}": [(-i * sep_m + s * paso, 0.0) for s in range(n_snaps)]
        for i in range(n_buses)
    }


def _cruce_frontal(v_kmh=20.0, n_snaps=12):
    """Dos buses de la misma (línea, trayecto) en sentidos opuestos."""
    paso = v_kmh / 3.6 * DT
    return {
        "sube": [(s * paso, 0.0) for s in range(n_snaps)],
        "baja": [((n_snaps - 1) * paso - s * paso, 0.0) for s in range(n_snaps)],
    }


def _alcance(v_lento=10.0, v_rapido=12.0, n_snaps=12, desfase=0.5):
    """El rápido viene por detrás y adelanta al lento por el mismo carril.

    `desfase` sitúa el instante del adelantamiento respecto a la rejilla de
    muestreo. Con 0.5 el cruce cae ENTRE dos sondeos, que es el caso físico: la
    probabilidad de que un sondeo aterrice justo cuando dos buses comparten
    coordenada es nula. Con 0.0 caen exactamente encima, y eso ya no es un
    adelantamiento difícil sino una configuración sin información: ver
    `test_coincidencia_exacta_de_dos_buses_es_irresoluble`.
    """
    p_l, p_r = v_lento / 3.6 * DT, v_rapido / 3.6 * DT
    cruce = n_snaps // 2 + desfase
    return {
        "lento": [(s * p_l, 0.0) for s in range(n_snaps)],
        "rapido": [(cruce * (p_l - p_r) + s * p_r, 0.0) for s in range(n_snaps)],
    }


def _anillo(n_buses=8, radio_m=300.0, v_kmh=20.0, n_snaps=10):
    """Ruta circular con los buses equiespaciados: configuración simétrica."""
    w = (v_kmh / 3.6 * DT) / radio_m
    fases = np.linspace(0, 2 * np.pi, n_buses, endpoint=False)
    return {
        f"bus{i}": [
            (radio_m * np.cos(fases[i] + s * w), radio_m * np.sin(fases[i] + s * w))
            for s in range(n_snaps)
        ]
        for i in range(n_buses)
    }


# --------------------------------------------------------------------------- #
# Configuraciones que rompen el emparejamiento ingenuo
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n_buses,sep_m", [(2, 60), (3, 120), (4, 60), (6, 120)])
def test_convoy_en_fila_india_no_intercambia_identidad(n_buses, sep_m):
    """El caso que destapó el arranque en frío. Antes del arreglo: 35 % con 4x60.

    Con separación comparable al paso por refresco (125 m a 15 km/h), el coste
    de la asignación correcta y el de la intercambiada son EXACTAMENTE iguales.
    """
    out = _rastrear_con_verdad(_construir(_convoy(n_buses=n_buses, sep_m=sep_m)))
    assert _precision(out) == 1.0, f"{_precision(out):.1%}"


def test_cruce_frontal_no_intercambia_identidad():
    """Dos buses de la misma línea cruzándose: el fallo que ataca la predicción."""
    out = _rastrear_con_verdad(_construir(_cruce_frontal()))
    assert _precision(out) == 1.0, f"{_precision(out):.1%}"


@pytest.mark.parametrize("v_lento,v_rapido", [(10, 11), (10, 15), (15, 18), (20, 25)])
def test_alcance_no_intercambia_identidad(v_lento, v_rapido):
    """Adelantamiento por el mismo carril, incluso con 1 km/h de diferencia.

    En el sondeo más próximo al adelantamiento los dos buses quedan a 4 m. Con
    eso basta: la extrapolación los separa y no hace falta más margen.
    """
    out = _rastrear_con_verdad(_construir(_alcance(v_lento, v_rapido)))
    assert _precision(out) == 1.0, f"{_precision(out):.1%}"


def test_el_convoy_discrimina_entre_predictivo_e_ingenuo():
    """Si el escenario no hundiera al modo ingenuo, no estaría ejerciendo nada."""
    sim = _construir(_convoy(n_buses=4, sep_m=60))
    pred = _precision(_rastrear_con_verdad(sim, predictivo=True))
    ing = _precision(_rastrear_con_verdad(sim, predictivo=False))
    assert pred == 1.0
    assert ing < pred, f"el ingenuo tambien acierta ({ing:.1%}): escenario flojo"


def test_lineas_distintas_no_se_mezclan():
    """Dos buses casi superpuestos pero de líneas distintas: nunca se emparejan."""
    paso = 15 / 3.6 * DT
    tray = {
        "a": [(s * paso, 0.0) for s in range(8)],
        "b": [(s * paso + 5.0, 3.0) for s in range(8)],  # a ~6 m del otro
    }
    out = _rastrear_con_verdad(_construir(tray, linea={"a": "L1", "b": "L2"}))
    assert _precision(out) == 1.0
    assert out["vehicle_id"].nunique() == 2


# --------------------------------------------------------------------------- #
# Invariantes estructurales
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "escenario", [_convoy(), _cruce_frontal(), _alcance(), _anillo()]
)
def test_un_vehicle_id_no_se_repite_dentro_de_un_snapshot(escenario):
    """Un id dos veces en el mismo instante sería un bus en dos sitios a la vez."""
    out = _rastrear_con_verdad(_construir(escenario))
    repetidos = out.groupby("snapshot_id")["vehicle_id"].apply(
        lambda s: s.duplicated().any()
    )
    assert not repetidos.any(), (
        f"snapshots con id repetido: {list(repetidos[repetidos].index)}"
    )


def test_un_vehicle_id_no_se_repite_en_la_flota_simulada(flota_simulada):
    out = _rastrear_con_verdad(flota_simulada)
    repetidos = out.groupby("snapshot_id")["vehicle_id"].apply(
        lambda s: s.duplicated().any()
    )
    assert not repetidos.any()


@pytest.mark.parametrize(
    "escenario", [_convoy(), _cruce_frontal(), _alcance(), _anillo()]
)
def test_ningun_desplazamiento_supera_la_puerta_fisica(escenario):
    """La puerta se evaluaba sobre la posición PREDICHA, no sobre la real.

    Con `predictivo=True` las dos divergen, así que colaban desplazamientos que
    el tope prohíbe: 10 en 150 snapshots reales, el mayor de 957 m a 100 km/h
    con `VEL_MAX_KMH` en 70.
    """
    out = _rastrear_con_verdad(_construir(escenario))
    tr = out.dropna(subset=["dist_m"])
    assert tr["dist_m"].max() <= SALTO_MAX_M, f"salto de {tr['dist_m'].max():.0f} m"
    assert tr["vel_kmh"].max() <= VEL_MAX_KMH + 1e-6, f"{tr['vel_kmh'].max():.0f} km/h"


def test_la_puerta_fisica_se_respeta_en_la_flota_simulada(flota_simulada):
    tr = _rastrear_con_verdad(flota_simulada).dropna(subset=["dist_m"])
    assert tr["dist_m"].max() <= SALTO_MAX_M
    assert tr["vel_kmh"].max() <= VEL_MAX_KMH + 1e-6


def test_la_puerta_fisica_se_respeta_tras_sondeos_perdidos():
    """TRAMPA 008, la guardia que de verdad la guarda.

    Los escenarios de arriba van a velocidad constante con pasos de 30 s: la
    posición predicha y la real nunca se separan lo bastante como para que
    importe sobre cuál se evalúa la puerta, y volver a evaluarla solo sobre la
    predicha los deja en verde (`docs/11_auditoria_tests.md`). Con dos sondeos
    perdidos a cadencia de 60 s el paso dura 180 s, la extrapolación se aleja, y
    ese código acepta 34 desplazamientos por encima de `SALTO_MAX_M`, hasta
    1.442 m.
    """
    tr = _rastrear_con_verdad(simular_flota(dt=60.0, huecos=(6, 7)))
    tr = tr.dropna(subset=["dist_m"])
    tope = np.minimum(SALTO_MAX_M, VEL_MAX_KMH / 3.6 * np.maximum(tr["dt_s"], 1.0))
    fuera = tr[tr["dist_m"] > tope + 1e-6]
    assert fuera.empty, (
        f"{len(fuera)} desplazamientos por encima de la puerta, "
        f"el mayor de {fuera['dist_m'].max():.0f} m"
    )


def test_rastrear_no_reordena_filas_dentro_del_sondeo():
    """TRAMPA 004, sin depender de cómo ordene numpy.

    La guardia anterior solo podía caer si quicksort permutaba una entrada YA
    ordenada, y eso depende de la versión: numpy 2.2.6 lo hace, 2.4.6 no. Aquí la
    entrada llega desordenada ENTRE sondeos, así que hay que ordenar, y solo un
    orden estable conserva dentro de cada sondeo el orden de llegada, que es lo
    que asume todo lo que reengancha por posición de fila.
    """
    sim = simular_flota().sample(frac=1, random_state=11).reset_index(drop=True)
    out = rastrear(sim.drop(columns=["verdad"]))
    for snap, g in out.groupby("snapshot_id", sort=False):
        llegada = sim.loc[sim["snapshot_id"] == snap, "gid"].tolist()
        assert g["gid"].tolist() == llegada, f"sondeo {snap} reordenado"


def test_resultado_invariante_al_orden_de_las_filas():
    """TRAMPA 004: barajar dentro del snapshot no puede cambiar la partición.

    Más afilado que un umbral de precisión: compara la partición completa, no
    un agregado que puede compensar errores.
    """
    particiones = []
    for seed in (1, 2, 3, 5, 8):
        out = _rastrear_con_verdad(_construir(_convoy(n_buses=5, sep_m=90), seed=seed))
        particiones.append(
            frozenset(
                frozenset(zip(g["verdad"], g["snapshot_id"]))
                for _, g in out.groupby("vehicle_id")
            )
        )
    assert len(set(particiones)) == 1, "la partición depende del orden de llegada"


# --------------------------------------------------------------------------- #
# Entradas, salidas y roturas de cadena
# --------------------------------------------------------------------------- #
def test_bus_que_entra_en_servicio_recibe_id_nuevo():
    tray = _convoy(n_buses=3, sep_m=120)
    paso = 15 / 3.6 * DT
    tray["nuevo"] = [
        (np.nan, np.nan) if s < 4 else (-500.0 + s * paso, 0.0) for s in range(10)
    ]
    out = _rastrear_con_verdad(_construir(tray))

    ids_previos = set(out[out["verdad"] != "nuevo"]["vehicle_id"])
    ids_nuevo = set(out[out["verdad"] == "nuevo"]["vehicle_id"])
    assert len(ids_nuevo) == 1, f"el bus entrante se partió en {len(ids_nuevo)}"
    assert not (ids_nuevo & ids_previos), "reutilizó el id de un bus ya en servicio"
    assert _precision(out) == 1.0


def test_bus_que_sale_de_servicio_no_cede_su_id():
    tray = _convoy(n_buses=3, sep_m=120)
    tray["bus1"] = [
        p if s < 5 else (np.nan, np.nan) for s, p in enumerate(tray["bus1"])
    ]
    out = _rastrear_con_verdad(_construir(tray))

    id_saliente = out[out["verdad"] == "bus1"]["vehicle_id"].unique()
    assert len(id_saliente) == 1
    tras_salir = out[
        (out["snapshot_id"] >= 1005) & (out["vehicle_id"] == id_saliente[0])
    ]
    assert tras_salir.empty, "otro bus heredó el id del que salió de servicio"


@pytest.mark.parametrize("salto_m", [550.0, 2000.0], ids=["550m", "2km"])
def test_salto_imposible_rompe_la_cadena(salto_m):
    """Un desplazamiento por encima de la puerta debe abrir trayectoria nueva.

    Emparejarlo sería inventar un viaje imposible en 30 s; romper la cadena
    cuesta longitud de trayectoria pero no contamina la etiqueta de retraso.

    Los 2 km superan cualquier puerta y no discriminan nada. Los 550 m sí: el
    desplazamiento real es de 675 m, por encima de los 583 m que permiten
    70 km/h en 30 s y por debajo de `SALTO_MAX_M`; la distancia a la posición
    predicha es de 550 m, por debajo. Solo la puerta completa lo rechaza: la
    evaluada sobre la predicha (trampa 008) o con una velocidad máxima más
    laxa lo aceptan.
    """
    paso = 15 / 3.6 * DT
    tray = {
        "salton": [(s * paso if s < 5 else s * paso + salto_m, 0.0) for s in range(10)]
    }
    out = _rastrear_con_verdad(_construir(tray))
    antes = set(out[out["snapshot_id"] < 1005]["vehicle_id"])
    despues = set(out[out["snapshot_id"] >= 1005]["vehicle_id"])
    assert not (antes & despues), "emparejó por encima de la puerta física"


def test_sondeos_con_el_mismo_instante_no_rompen_la_cadena():
    """Dos sondeos con el mismo `ts_utc` dan `dt = 0`: se trata como un paso de 30 s.

    Si se tratase como 1 s, la puerta se cerraría a 19 m y un bus a 15 km/h
    saldría partido en dos trayectorias (mutante 025 de la auditoría).
    """
    paso = 15 / 3.6 * DT
    df = _construir({"bus": [(s * paso, 0.0) for s in range(6)]})
    t2 = df.loc[df["snapshot_id"] == 1002, "ts_utc"].iloc[0]
    df.loc[df["snapshot_id"] == 1003, "ts_utc"] = t2
    df.loc[df["snapshot_id"] > 1003, "ts_utc"] -= pd.Timedelta(seconds=DT)
    out = _rastrear_con_verdad(df)
    assert out["vehicle_id"].nunique() == 1, "el paso con dt = 0 partió la cadena"


# --------------------------------------------------------------------------- #
# Paradas y giros en un encuentro
# --------------------------------------------------------------------------- #
# Coordenadas en metros de dos buses de la flota simulada con paradas y giros al
# ritmo real (`simular_flota(semilla=42, p_parada=0.17)`, sondeos 1000-1006, y
# `simular_flota(semilla=7, p_giro=0.10)`, sondeos 1005-1012), congeladas aquí
# para que el escenario no dependa del generador. Sin `_suavizar_intercambios`
# el tracker los intercambia en las cinco ordenaciones de fila: 85,7 % y 87,5 %.
PARADA_JUNTO_A_OTRO = {
    "para": [
        (-838.7, -775.7), (-866.0, -855.2), (-889.3, -936.0), (-889.3, -936.0),
        (-889.3, -936.0), (-888.3, -1020.0), (-888.3, -1020.0),
    ],
    "pasa": [
        (-910.2, -1422.4), (-910.2, -1422.4), (-889.6, -1221.9), (-939.1, -1026.5),
        (-1000.5, -834.5), (-1088.2, -653.0), (-1169.1, -468.3),
    ],
}  # fmt: skip
GIRO_EN_UN_CRUCE = {
    "gira": [
        (-615.9, -724.7), (-812.6, -783.9), (-861.0, -584.2), (-1061.2, -630.4),
        (-1255.0, -698.6), (-1458.7, -725.0), (-1660.1, -765.8), (-1862.4, -801.2),
    ],
    "sigue": [
        (-980.2, -1417.4), (-1070.4, -1278.0), (-1156.3, -1136.1), (-1247.0, -997.0),
        (-1338.8, -858.8), (-1458.5, -743.7), (-1577.8, -628.4), (-1674.8, -493.6),
    ],
}  # fmt: skip


@pytest.mark.parametrize("seed", [1, 2, 3, 5, 8])
@pytest.mark.parametrize(
    "escenario", [PARADA_JUNTO_A_OTRO, GIRO_EN_UN_CRUCE], ids=["parada", "giro"]
)
def test_parar_o_girar_en_un_encuentro_no_intercambia_identidad(escenario, seed):
    """El predictor extrapola al bus que para o gira y le asigna la posición del otro.

    El error se delata en el sondeo siguiente —el bus "parado" habría ido hasta
    el otro y vuelto—, y `_suavizar_intercambios` usa ese sondeo para deshacerlo
    (`docs/bitacora/015-el-sondeo-siguiente-delata-el-intercambio.md`).
    """
    out = _rastrear_con_verdad(_construir(escenario, seed=seed))
    assert _precision(out) == 1.0, f"precisión {_precision(out):.1%}"


@pytest.mark.parametrize(
    "escenario", [PARADA_JUNTO_A_OTRO, GIRO_EN_UN_CRUCE], ids=["parada", "giro"]
)
def test_sin_suavizado_el_encuentro_si_intercambia(escenario, monkeypatch):
    """Discriminación: los escenarios de arriba ejercitan el suavizado de verdad."""
    monkeypatch.setattr(tracking, "_suavizar_intercambios", lambda df: df)
    out = _rastrear_con_verdad(_construir(escenario))
    assert _precision(out) < 1.0, "el escenario ya no necesita el suavizado"


def test_el_suavizado_mide_el_tiempo_con_el_reloj_de_sondeo():
    """`dt_s` tras suavizar es el del emparejamiento: máximo `ts_utc` por sondeo.

    Las filas de un sondeo no siempre traen el mismo `ts_utc`. Medido por fila, el
    suavizado reescribía `dt_s` de 8 s o negativos donde el tracker tenía 30, y la
    puerta física calculada con ese `dt_s` aparecía violada 14 veces en un día
    real. Aquí se desordena el reloj dentro de cada sondeo a propósito.
    """
    sim = simular_flota(semilla=42, p_parada=0.17)
    rng = np.random.default_rng(0)
    sim["ts_utc"] -= pd.to_timedelta(rng.uniform(0, 12, len(sim)), unit="s")
    out = rastrear(sim.drop(columns=["verdad"]))

    reloj = out.groupby("snapshot_id")["ts_utc"].max()
    reloj_s = (reloj - reloj.min()).dt.total_seconds()
    o = out.sort_values(["vehicle_id", "snapshot_id"], kind="stable")
    anterior = o.groupby("vehicle_id")["snapshot_id"].shift()
    tiene = anterior.notna()
    esperado = (
        reloj_s.loc[o.loc[tiene, "snapshot_id"]].to_numpy()
        - reloj_s.loc[anterior[tiene].astype(int)].to_numpy()
    )
    esperado = np.where(esperado == 0, 30.0, esperado)
    obtenido = o.loc[tiene, "dt_s"].to_numpy(dtype=float)
    assert np.allclose(obtenido, esperado), "dt_s no sigue el reloj de sondeo"


# --------------------------------------------------------------------------- #
# Límite conocido
# --------------------------------------------------------------------------- #
@pytest.mark.xfail(
    strict=True,
    reason="Mismo límite que el anillo, en versión instantánea: si un sondeo "
    "captura a dos buses en la MISMA coordenada, la matriz de coste es toda "
    "ceros y no hay nada que decidir. Se corrige solo en el sondeo siguiente y "
    "no altera dist_m ni vel_kmh (ambos están en el mismo punto), así que no "
    "contamina la etiqueta; queda anotado para que nadie lo persiga como bug.",
)
def test_coincidencia_exacta_de_dos_buses_es_irresoluble():
    out = _rastrear_con_verdad(_construir(_alcance(10, 11, desfase=0.0)))
    assert _precision(out) == 1.0


@pytest.mark.xfail(
    strict=True,
    reason="Límite de identificabilidad, no un bug: con los vehículos "
    "equiespaciados sobre un anillo, permutar sus identidades es una simetría "
    "de lo observado. Ningún método que sólo mire posiciones lo distingue; "
    "haría falta rumbo o velocidad, y la capa de la EMT no los publica. "
    "Si algún día esto pasa a verde, el método ha cambiado: documentar por qué.",
)
def test_ruta_circular_equiespaciada_es_irresoluble():
    out = _rastrear_con_verdad(_construir(_anillo(n_buses=8, radio_m=300.0)))
    assert _precision(out) == 1.0
