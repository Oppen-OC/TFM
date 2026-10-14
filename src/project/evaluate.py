"""Stage `evaluate`: el modelo contra los tres baselines, en la prueba (ADR-018).

    uv run python -m project.evaluate            # lo que ejecuta `dvc repro evaluate`

Una mejora es una diferencia de error sobre los MISMOS viajes, con su intervalo
del 95 % remuestreando VIAJES: las paradas de un viaje están correlacionadas, y
remuestrear filas da un intervalo estrecho que declara mejoras que no lo son.
Hay mejora si el intervalo no contiene el cero. Se compara con la persistencia
y, sobre todo, con la persistencia más el sesgo del tramo: el listón del
tráfico (ADR-019).

Se informa en conjunto, por grupo de soporte de la línea, por banda de
intervalo programado, por horizonte útil (lo que queda desde que se SABE el
paso hasta la parada siguiente, trampa 017) y por línea con soporte propio.
La banda separa dos calidades de etiqueta: con 8 min o menos, la asignación pliega al viaje
siguiente el 11 % de los viajes y se lleva la mitad de los retrasos de más de
5 min; con más de 15, menos del 2 % (bitácora 038). Las bandas largas son la
referencia limpia.

El intervalo por viajes da por buenos los días de la prueba: es un suelo de la
incertidumbre, no su medida (ADR-018, límite conocido). Por eso, en el conjunto,
los grupos y las bandas se da también remuestreando días de servicio.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

import mlflow
import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score

from project import features, gtfs, predict
from project.config import RAIZ, settings

REPLICAS = 1000
SEMILLA = 0
BANDAS = [-np.inf, 8 * 60, 15 * 60, 30 * 60, np.inf]
NOMBRES = ["<= 8 min", "8-15 min", "15-30 min", "> 30 min"]
# Horizonte previsto: con lo que se sabe al predecir, cuánto le queda al bus
# para la parada objetivo (ADR-022). La población es lo que tiene más de 0.
# Valen para todos los horizontes del barrido (ADR-023): con una parada casi todo
# cae por debajo de 2 min; con diez, por encima.
HORIZONTES = [0, 30, 60, 120, 300, 600, np.inf]
NOMBRES_HORIZONTE = ["0-30 s", "30-60 s", "1-2 min", "2-5 min", "5-10 min", "> 10 min"]
SIN_INTERVALO = "sin_intervalo"
# Fracción del recorrido i -> i + h bajo la 192 (ADR-024, enmienda del 10/10).
# Es geométrica y se sabe antes de predecir. La primaria mide el último estrato.
COBERTURA = [-np.inf, 0, 0.25, 0.5, 0.75, np.inf]
NOMBRES_COBERTURA = ["0", "0-25 %", "25-50 %", "50-75 %", "> 75 %"]
SIN_SENSOR, CON_SENSOR = NOMBRES_COBERTURA[0], NOMBRES_COBERTURA[-1]
CONGESTION = "con congestión"
# Más de 5 min tarde (ADR-025). El titular son las bandas largas: con 15 min o
# menos, la asignación pliega la mitad de esos retrasos (bitácora 038).
BANDAS_LARGAS = ["15-30 min", "> 30 min"]
YA_TARDE, AUN_NO = "ya tarde", "aún no"
LISTONES_BINARIOS = ("persistencia", "persistencia_tramo", "regresion")


def intervalos(h: gtfs.Horario, dia: date) -> pd.DataFrame:
    """trip_id → intervalo con el anterior y el siguiente de su línea en su 1.ª parada.

    Es el intervalo con el que un bus compite por su viaje programado: con más de
    medio intervalo de retraso, la asignación lo pliega al siguiente (bitácora
    038). Se mide entre los viajes de la misma línea que pasan por esa parada ese
    día; el GTFS de la EMT no trae `direction_id`. Vive aquí y no en `gtfs.py`
    porque aquel es dependencia de `prepare`.
    """
    vj = h.viajes[h.viajes["service_id"].isin(h.servicios(dia))][["trip_id", "linea"]]
    pv = h.paradas_de_viaje.merge(vj, on="trip_id").drop_duplicates(
        ["trip_id", "stop_id"]
    )
    primera = pv.loc[pv.groupby("trip_id")["stop_sequence"].idxmin()]
    # Toda cabecera es también el final de los viajes del otro sentido: contadas
    # sus llegadas, el intervalo sale por la mitad (en el 92 % de los viajes,
    # ≤ 8 min). Compiten los que salen o pasan, no los que terminan.
    ultima = pv.groupby("trip_id")["stop_sequence"].transform("max")
    pv = pv[pv["stop_sequence"] < ultima]
    pv = pv.sort_values(["linea", "stop_id", "t_prog_s"], kind="stable")
    g = pv.groupby(["linea", "stop_id"])["t_prog_s"]
    pv["h_ant_s"] = pv["t_prog_s"] - g.shift(1)
    pv["h_sig_s"] = g.shift(-1) - pv["t_prog_s"]
    return primera[["trip_id", "stop_id", "t_prog_s"]].merge(
        pv[["trip_id", "stop_id", "h_ant_s", "h_sig_s"]], on=["trip_id", "stop_id"]
    )


def banda_intervalo(tabla: pd.DataFrame, horarios: list[gtfs.Horario]) -> pd.Series:
    """Banda del intervalo de cada fila: el menor con el viaje anterior y el
    siguiente, en el horario que manda ese día (`gtfs.elegir_horario`).

    Se une por (día de servicio, `trip_id`), nunca por posición (trampa 012). Sin
    intervalo —viaje único en su parada, o que no está en el horario— la fila va
    a `sin_intervalo`: se informa aparte, no se tira.
    """
    partes = []
    for dia in pd.to_datetime(tabla["fecha_servicio"].unique()):
        h, _ = gtfs.elegir_horario(horarios, dia.date())
        if h is not None:
            partes.append(intervalos(h, dia.date()).assign(fecha_servicio=dia))
    iv = pd.concat(partes).set_index(["fecha_servicio", "trip_id"])
    h = iv[["h_ant_s", "h_sig_s"]].min(axis=1)
    h = h.reindex(pd.MultiIndex.from_frame(tabla[["fecha_servicio", "trip_id"]]))
    banda = pd.cut(h.to_numpy(), BANDAS, labels=NOMBRES).astype(object)
    return pd.Series(banda, index=tabla.index).fillna(SIN_INTERVALO)


def diferencia(
    e_a: pd.Series, e_b: pd.Series, viaje: pd.Series, replicas: int = REPLICAS
) -> dict:
    """MAE y RMSE de `e_a` menos los de `e_b` (negativo: `a` acierta más), con
    el intervalo del 95 % remuestreando VIAJES, no filas (ADR-018).

    Los tres van alineados por índice. Se remuestrean las sumas por viaje, así
    que un viaje largo pesa por sus filas, como en la cifra puntual.
    """
    sumas = (
        pd.DataFrame(
            {
                "abs_a": e_a.abs(),
                "abs_b": e_b.abs(),
                "cuad_a": e_a**2,
                "cuad_b": e_b**2,
                "n": 1.0,
            }
        )
        .groupby(viaje)
        .sum()
        .to_numpy()
    )

    def medidas(s: np.ndarray) -> np.ndarray:
        abs_a, abs_b, cuad_a, cuad_b, n = s.T
        return np.array(
            [(abs_a - abs_b) / n, np.sqrt(cuad_a / n) - np.sqrt(cuad_b / n)]
        )

    rng = np.random.default_rng(SEMILLA)
    k = len(sumas)
    rep = np.array(
        [medidas(sumas[rng.integers(0, k, k)].sum(0)) for _ in range(replicas)]
    )
    lo, hi = np.percentile(rep, [2.5, 97.5], axis=0)
    punto = medidas(sumas.sum(0))
    r = lambda v: round(float(v), 2)  # noqa: E731
    return {
        "mae_s": r(punto[0]),
        "mae_ic95": [r(lo[0]), r(hi[0])],
        "rmse_s": r(punto[1]),
        "rmse_ic95": [r(lo[1]), r(hi[1])],
    }


def resumen(t: pd.DataFrame, objetivo: str, dias: bool = False) -> dict:
    """Errores del modelo y de los baselines, y lo que el modelo gana a las dos
    persistencias. `t` trae `_prediccion` y `_viaje`.

    Con `dias`, también el intervalo remuestreando días de servicio: el de
    viajes da por buenos los días de la prueba y es un suelo (ADR-018). No se
    pide por línea, que puede tener solo tres días.
    """
    real = t[objetivo]
    base = features.predicciones_baseline(t)
    e_modelo = t["_prediccion"] - real

    def frente_a(grupo: pd.Series) -> dict:
        return {
            k: diferencia(e_modelo, base[k] - real, grupo)
            for k in ("persistencia", "persistencia_tramo")
        }

    r = {
        "filas": int(len(t)),
        "viajes": int(t["_viaje"].nunique()),
        "modelo": features.errores(t["_prediccion"], real),
        **{k: features.errores(v, real) for k, v in base.items()},
        "modelo_menos": frente_a(t["_viaje"]),
    }
    if dias:
        r["modelo_menos_remuestreando_dias"] = frente_a(t["fecha_servicio"])
    return r


def estratos_trafico(t: pd.DataFrame) -> pd.DataFrame:
    """`t` con `_cobertura`, la fracción del recorrido con sensor, y `_estado`, lo
    que decía la capa al predecir. Las dos se saben antes de predecir:
    estratificar por ellas no es condicionar por el resultado (ADR-024)."""
    cobertura = (t["trafico_cubierto_m"] / t["dist_objetivo_m"]).clip(upper=1)
    frac = t["trafico_congestion_frac"]
    estado = np.select(
        [frac.isna(), frac == 0], ["sin dato", "fluido"], default=CONGESTION
    )
    return t.assign(
        _cobertura=pd.cut(cobertura, COBERTURA, labels=NOMBRES_COBERTURA),
        _estado=estado,
    )


def con_menos_sin(e_con: pd.Series, e_sin: pd.Series, t: pd.DataFrame) -> dict:
    """MAE con tráfico menos MAE sin él sobre las filas de `t`, con los intervalos
    por viajes y por días (ADR-018), y el efecto relativo al MAE sin tráfico."""
    viaje = t.groupby(features.CLAVE_VIAJE, sort=False).ngroup()
    v = diferencia(e_con, e_sin, viaje)
    d = diferencia(e_con, e_sin, t["fecha_servicio"])
    mae_sin, mae_con = float(e_sin.abs().mean()), float(e_con.abs().mean())
    return {
        "filas": int(len(t)),
        "mae_sin_s": round(mae_sin, 2),
        "mae_con_s": round(mae_con, 2),
        "con_menos_sin_s": v["mae_s"],
        "relativa": round((mae_con - mae_sin) / mae_sin, 4),
        "ic_viajes": v["mae_ic95"],
        "ic_dias": d["mae_ic95"],
    }


def comprobar_pareja(con: dict, sin: dict) -> None:
    """El mismo modelo salvo las variables de la 192 (ADR-024, punto 3).

    Cruzarlos, o compararlos tras entrenar uno con otros datos, invierte o
    falsea la primaria sin ningún error.
    """
    trafico = set(features.TRAFICO)
    if not (
        set(con["columnas"]) == set(sin["columnas"]) | trafico
        and not trafico & set(sin["columnas"])
        and con["categorias"] == sin["categorias"]
        and con["residuo"] == sin["residuo"]
        and con["validacion"]["dias"] == sin["validacion"]["dias"]
    ):
        raise ValueError(
            "los modelos con y sin tráfico no son la misma pareja (ADR-024)"
        )


def comparacion_trafico(
    t: pd.DataFrame, pred_con: pd.Series, pred_sin: pd.Series, objetivo: str
) -> dict:
    """El modelo con la capa 192 contra el mismo modelo sin ella, sobre las mismas
    filas de la población (ADR-022 y ADR-024).

    `con_sensor` es la primaria con h = 5. El resto es descriptivo: el conjunto,
    las filas en las que la capa veía congestión al predecir (el secundario) y las
    que no tienen ningún sensor en el recorrido (el control: lo que la primaria no
    supere a este no se atribuye a la congestión).
    """
    e_con, e_sin = pred_con - t[objetivo], pred_sin - t[objetivo]
    t = estratos_trafico(t[features.poblacion(t)])

    def en(g: pd.DataFrame) -> dict:
        if g.empty:
            return {"filas": 0}
        return con_menos_sin(e_con[g.index], e_sin[g.index], g)

    def por(col: str) -> dict:
        return {str(k): en(g) for k, g in t.groupby(col, observed=True)}

    return {
        "dias": int(t["fecha_servicio"].nunique()),
        "con_sensor": en(t[t["_cobertura"] == CON_SENSOR]),
        "conjunto": en(t),
        "con_congestion_observada": en(t[t["_estado"] == CONGESTION]),
        "sin_sensor": en(t[t["_cobertura"] == SIN_SENSOR]),
        "por_cobertura": por("_cobertura"),
        "por_estado_observado": por("_estado"),
    }


def _r4(v: float) -> float | None:
    """Redondeo del JSON: nulo, nunca NaN, donde no hay cifra (ADR-025)."""
    v = float(v)
    return None if np.isnan(v) else round(v, 4)


def _f1(vp, fp, fn):
    """F1 = 2 VP / (2 VP + FP + FN). NaN sin positivos reales ni predichos."""
    d = np.asarray(2 * vp + fp + fn, dtype=float)  # con floats de Python, 0/0 lanza
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(d > 0, 2 * vp / d, np.nan)


def _aciertos(decision: pd.Series, real: pd.Series) -> pd.DataFrame:
    """VP, FP y FN fila a fila, como números para poder sumarlos."""
    d, r = decision.astype(bool), real.astype(bool)
    return pd.DataFrame({"vp": d & r, "fp": d & ~r, "fn": ~d & r}).astype(float)


def metricas_binarias(
    decision: pd.Series, real: pd.Series, puntuacion: pd.Series | None = None
) -> dict:
    """Precisión, sensibilidad y F1 en el punto de operación y, con una
    puntuación continua, su PR-AUC (ADR-025). Nulas donde no hay cifra."""
    vp, fp, fn = _aciertos(decision, real).sum()
    m = {
        "precision": _r4(vp / (vp + fp)) if vp + fp else None,
        "sensibilidad": _r4(vp / (vp + fn)) if vp + fn else None,
        "f1": _r4(_f1(vp, fp, fn)),
    }
    if puntuacion is not None:
        r = real.astype(bool)
        m["pr_auc"] = _r4(average_precision_score(r, puntuacion)) if r.any() else None
    return m


def diferencia_f1(
    dec_a: pd.Series,
    dec_b: pd.Series,
    real: pd.Series,
    grupo: pd.Series,
    replicas: int = REPLICAS,
) -> dict:
    """F1 de `dec_a` menos el de `dec_b` (positivo: `a` acierta más), con el
    intervalo del 95 % remuestreando `grupo` —viajes o días—, no filas (ADR-018).

    Como en `diferencia`, se remuestrean sumas por grupo: VP, FP y FN de cada
    uno. Una réplica sin positivos reales ni predichos no tiene F1: no cuenta.
    """
    sumas = (
        pd.concat(
            [
                _aciertos(dec_a, real).add_suffix("_a"),
                _aciertos(dec_b, real).add_suffix("_b"),
            ],
            axis=1,
        )
        .groupby(grupo)
        .sum()
        .to_numpy()
    )

    def medida(s: np.ndarray) -> float:
        return float(_f1(*s[:3]) - _f1(*s[3:]))

    rng = np.random.default_rng(SEMILLA)
    k = len(sumas)
    rep = np.array(
        [medida(sumas[rng.integers(0, k, k)].sum(0)) for _ in range(replicas)]
    )
    rep = rep[~np.isnan(rep)]
    lo, hi = np.percentile(rep, [2.5, 97.5]) if len(rep) else (np.nan, np.nan)
    return {"f1": _r4(medida(sumas.sum(0))), "f1_ic95": [_r4(lo), _r4(hi)]}


def comprobar_pareja_clasificador(clf: dict, reg: dict) -> None:
    """El clasificador y la regresión del mismo horizonte salen del mismo
    entrenamiento, con las mismas variables (ADR-025). Si no, el listón de la
    regresión es de otro modelo y la comparación no dice nada."""
    if not (
        clf["columnas"] == reg["columnas"]
        and clf["categorias"] == reg["categorias"]
        and clf["validacion"]["dias"] == reg["validacion"]["dias"]
    ):
        raise ValueError(
            "el clasificador y la regresión no son la misma pareja (ADR-025)"
        )


def comparacion_clasificador(
    t: pd.DataFrame,
    prob: pd.Series,
    pred_regresion: pd.Series,
    objetivo: str,
    umbral_s: float,
    umbral_decision: float,
) -> dict:
    """Más de `umbral_s` tarde: el clasificador contra los listones sobre las
    mismas filas de la población (ADR-022 y ADR-025). `t` trae `_banda`.

    Todo es descriptivo. El titular son las bandas largas, donde la etiqueta no
    pierde positivos por el pliegue (bitácora 038). El estado actual se sabe al
    predecir: separa los buses que ya van tarde de los que cruzarían el umbral
    por el camino, que es donde la persistencia no llega.
    """
    real = t[f"{objetivo}_bin"].astype(bool)
    base = features.predicciones_baseline(t)
    puntos = {
        "clasificador": prob,
        "persistencia": base["persistencia"],
        "persistencia_tramo": base["persistencia_tramo"],
        "regresion": pred_regresion,
    }
    decision = {
        "clasificador": prob >= umbral_decision,
        **{k: puntos[k] > umbral_s for k in LISTONES_BINARIOS},
        "horario": pd.Series(False, index=t.index),
    }
    p = t[features.poblacion(t)]
    p = p.assign(_estado=np.where(p["retraso_s"] > umbral_s, YA_TARDE, AUN_NO))

    def en(g: pd.DataFrame) -> dict:
        if g.empty:
            return {"filas": 0}
        i = g.index
        viaje = g.groupby(features.CLAVE_VIAJE, sort=False).ngroup()
        return {
            "filas": int(len(g)),
            "viajes": int(viaje.nunique()),
            "dias": int(g["fecha_servicio"].nunique()),
            "tasa_base": _r4(real[i].mean()),
            "brier_clasificador": _r4(((prob[i] - real[i].astype(float)) ** 2).mean()),
            "metricas": {
                k: metricas_binarias(
                    decision[k][i], real[i], puntos[k][i] if k in puntos else None
                )
                for k in decision
            },
            "clasificador_menos": {
                k: {
                    "viajes": diferencia_f1(
                        decision["clasificador"][i], decision[k][i], real[i], viaje
                    ),
                    "dias": diferencia_f1(
                        decision["clasificador"][i],
                        decision[k][i],
                        real[i],
                        g["fecha_servicio"],
                    ),
                }
                for k in LISTONES_BINARIOS
            },
        }

    def por(col: str) -> dict:
        return {str(k): en(g) for k, g in p.groupby(col, observed=True)}

    return {
        "dias": int(p["fecha_servicio"].nunique()),
        "umbral_decision": _r4(umbral_decision),
        "titular": en(p[p["_banda"].isin(BANDAS_LARGAS)]),
        "conjunto": en(p),
        "por_banda": por("_banda"),
        "por_estado_actual": por("_estado"),
    }


def main(horizonte: int | None = None) -> None:
    """Sin horizonte, el de `params.yaml`; con él, el del barrido (ADR-023)."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    obj = cfg["objetivo"]
    rutas = features.salidas(horizonte)
    test = pd.read_parquet(rutas["tabla"] / "test.parquet")
    train = pd.read_parquet(
        rutas["tabla"] / "train.parquet",
        columns=["linea", *features.CLAVE_VIAJE],
    )
    soporte = features.soporte_por_linea(
        train, test, cfg["linea_min_viajes"], cfg["linea_min_dias"]
    )
    art = predict.cargar(rutas["modelo"])
    horarios = [gtfs.cargar_horario(r) for r in gtfs.versiones(settings.gtfs_dir)]
    t = test.assign(
        _prediccion=predict.predecir(art, test),
        _viaje=test.groupby(features.CLAVE_VIAJE, sort=False).ngroup(),
        _grupo=test["linea"].map(soporte["grupo"]),
        _horizonte=pd.cut(
            test["horizonte_previsto_s"], HORIZONTES, labels=NOMBRES_HORIZONTE
        ),
        _banda=pd.Categorical(
            banda_intervalo(test, horarios), categories=[*NOMBRES, SIN_INTERVALO]
        ),
    )

    def por(t: pd.DataFrame, col: str, dias: bool) -> dict:
        return {str(k): resumen(g, obj, dias) for k, g in t.groupby(col, observed=True)}

    # La primaria, sobre las predicciones que aún pueden servir; el resto es
    # nowcast y se informa aparte (ADR-022).
    pob = features.poblacion(t)
    metricas = {
        "modelo": {k: art[k] for k in ("n_arboles", "mlflow_run_id")},
        "horizonte_paradas": horizonte or cfg["horizonte_paradas"],
        "remuestreo": {
            "unidad": "viaje y día",
            "replicas": REPLICAS,
            "semilla": SEMILLA,
        },
        "poblacion": {
            "criterio": "horizonte_previsto_s > 0 (ADR-022)",
            "filas": int(pob.sum()),
            "filas_nowcast": int((~pob).sum()),
        },
        "global": resumen(t[pob], obj, dias=True),
        "nowcast": resumen(t[~pob], obj, dias=True),
        "por_grupo": por(t[pob], "_grupo", dias=True),
        "por_banda": por(t[pob], "_banda", dias=True),
        "por_horizonte": por(t[pob], "_horizonte", dias=True),
        "por_linea": por(t[pob & (t["_grupo"] == "propia")], "linea", dias=False),
    }
    rutas["metricas"].mkdir(parents=True, exist_ok=True)
    salida = rutas["metricas"] / "eval.json"
    salida.write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    plano = pd.json_normalize(metricas["global"], sep=".").iloc[0]
    with mlflow.start_run(run_id=art["mlflow_run_id"]):
        mlflow.log_metrics(
            {
                f"test.{k}": float(v)
                for k, v in plano.items()
                if isinstance(v, (int, float))
            }
        )
        mlflow.log_dict(metricas, "eval.json")
    print(json.dumps(metricas["global"], indent=2))
    print({k: v["modelo_menos"] for k, v in metricas["por_banda"].items()})


def main_trafico(horizonte: int | None = None) -> None:
    """Stage `evaluate_trafico`: el modelo con tráfico menos el de sin tráfico en
    la prueba (ADR-024). Sin horizonte, el de `params.yaml`; con él, el del
    barrido."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    rutas = features.salidas(horizonte)
    con = predict.cargar(rutas["modelo_trafico"])
    sin = predict.cargar(rutas["modelo"])
    comprobar_pareja(con, sin)
    test = pd.read_parquet(rutas["tabla"] / "test.parquet")
    metricas = {
        "horizonte_paradas": horizonte or cfg["horizonte_paradas"],
        "prueba": [cfg["test_desde"], cfg["test_hasta"]],
        "modelos": {
            nombre: {
                "n_arboles": a["n_arboles"],
                "mlflow_run_id": a["mlflow_run_id"],
                "validacion": a["validacion"]["dias"],
            }
            for nombre, a in (("con", con), ("sin", sin))
        },
        "remuestreo": {
            "unidad": "viaje y día",
            "replicas": REPLICAS,
            "semilla": SEMILLA,
        },
        **comparacion_trafico(
            test,
            predict.predecir(con, test),
            predict.predecir(sin, test),
            cfg["objetivo"],
        ),
    }
    rutas["metricas"].mkdir(parents=True, exist_ok=True)
    (rutas["metricas"] / "trafico.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    plano = pd.json_normalize(
        {k: metricas[k] for k in ("con_sensor", "conjunto")}, sep="."
    ).iloc[0]
    with mlflow.start_run(run_id=con["mlflow_run_id"]):
        mlflow.log_metrics(
            {
                f"trafico.{k}": float(v)
                for k, v in plano.items()
                if isinstance(v, (int, float))
            }
        )
        mlflow.log_dict(metricas, "trafico.json")
    print(
        json.dumps(
            {k: metricas[k] for k in ("dias", "con_sensor", "conjunto")},
            indent=2,
            ensure_ascii=False,
        )
    )


def main_clasificador(horizonte: int | None = None) -> None:
    """Stage `evaluate_clasificador`: más de 5 min tarde contra los listones, en
    la prueba (ADR-025). Sin horizonte, el de `params.yaml`; con él, el del
    barrido."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))["features"]
    rutas = features.salidas(horizonte)
    clf = predict.cargar(rutas["clasificador"])
    reg = predict.cargar(rutas["modelo"])
    comprobar_pareja_clasificador(clf, reg)
    test = pd.read_parquet(rutas["tabla"] / "test.parquet")
    horarios = [gtfs.cargar_horario(r) for r in gtfs.versiones(settings.gtfs_dir)]
    metricas = {
        "horizonte_paradas": horizonte or cfg["horizonte_paradas"],
        "prueba": [cfg["test_desde"], cfg["test_hasta"]],
        "umbral_retraso_s": cfg["umbral_retraso_s"],
        "modelos": {
            nombre: {
                "n_arboles": a["n_arboles"],
                "mlflow_run_id": a["mlflow_run_id"],
                "validacion": a["validacion"]["dias"],
            }
            for nombre, a in (("clasificador", clf), ("regresion", reg))
        },
        "remuestreo": {
            "unidad": "viaje y día",
            "replicas": REPLICAS,
            "semilla": SEMILLA,
        },
        **comparacion_clasificador(
            test.assign(_banda=banda_intervalo(test, horarios)),
            predict.probabilidad(clf, test),
            predict.predecir(reg, test),
            cfg["objetivo"],
            cfg["umbral_retraso_s"],
            clf["umbral"],
        ),
    }
    rutas["metricas"].mkdir(parents=True, exist_ok=True)
    (rutas["metricas"] / "clasificador.json").write_text(
        json.dumps(metricas, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    plano = pd.json_normalize(
        {k: metricas[k] for k in ("titular", "conjunto")}, sep="."
    ).iloc[0]
    with mlflow.start_run(run_id=clf["mlflow_run_id"]):
        mlflow.log_metrics(
            {
                f"test.{k}": float(v)
                for k, v in plano.items()
                if isinstance(v, (int, float)) and np.isfinite(v)
            }
        )
        mlflow.log_dict(metricas, "clasificador.json")
    print(json.dumps(metricas["titular"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("--horizonte", type=int, default=None, help="paradas (ADR-023)")
    modo = a.add_mutually_exclusive_group()
    modo.add_argument(
        "--trafico", action="store_true", help="con menos sin tráfico (ADR-024)"
    )
    modo.add_argument(
        "--clasificador",
        action="store_true",
        help="más de 5 min tarde contra los listones (ADR-025)",
    )
    args = a.parse_args()
    if args.trafico:
        main_trafico(args.horizonte)
    elif args.clasificador:
        main_clasificador(args.horizonte)
    else:
        main(args.horizonte)
