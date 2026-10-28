"""Los modelos en memoria y la predicción de un vector de variables.

Es la única capa que carga modelos (CLAUDE.md): una vez, al arrancar la API, no
por petición. La API valida el JSON y delega aquí; aquí no se importa nada de
`api/`. La transformación de la entrada es la del entrenamiento, porque pasa por
`predict.predecir` y `predict.probabilidad`, que pasan por `features.matriz`.
"""

from __future__ import annotations

import math

import pandas as pd
import yaml

from project import features, predict
from project.config import RAIZ

REGRESION, CLASIFICADOR = "regresion", "clasificador"
# La clave de `features.salidas` de cada modelo servido. Los de la capa 192 no
# se sirven: su aportación la decide el ADR-024.
SALIDA = {REGRESION: "modelo", CLASIFICADOR: "clasificador"}
# Contribuciones que se devuelven con `explicar`; las demás van sumadas en `resto`.
PRINCIPALES = 5


class VariablesInvalidas(ValueError):
    """El vector no trae exactamente las variables del modelo, o con su tipo."""


class HorizonteInvalido(ValueError):
    """Un horizonte para el que no se entrena ningún modelo."""


class ModeloNoDisponible(LookupError):
    """El horizonte es válido, pero su modelo no está cargado."""


def horizontes() -> list[int]:
    """El de `params.yaml` y los del barrido (ADR-023), en ese orden."""
    cfg = yaml.safe_load((RAIZ / "params.yaml").read_text(encoding="utf-8"))
    f = cfg["features"]
    return [f["horizonte_paradas"], *f["horizontes_barrido"]]


def fila(columnas: list[str], variables: dict) -> pd.DataFrame:
    """El vector como tabla de una fila, con los tipos del entrenamiento.

    Las claves tienen que ser exactamente `columnas`. Los nulos valen, porque
    hay variables nulas de verdad, como `bus_anterior_retraso_s`; en
    `retraso_s` (nulo o NaN) no, porque sin el retraso de ahora no hay
    predicción. Un infinito (`1e400` en JSON) no vale en ninguna numérica. Las
    numéricas van a `float64`: desde JSON, una columna con un nulo queda como
    `object` y XGBoost la rechaza.
    """
    faltan = [c for c in columnas if c not in variables]
    sobran = sorted(set(variables) - set(columnas))
    if faltan or sobran:
        raise VariablesInvalidas({"faltan": faltan, "sobran": sobran})
    if pd.isna(variables["retraso_s"]):
        raise VariablesInvalidas(
            {"nulas": ["retraso_s"], "motivo": "es el retraso de ahora"}
        )
    mal_tipo = [
        c
        for c in columnas
        if variables[c] is not None and isinstance(variables[c], str) != (c == "linea")
    ]
    if mal_tipo:
        raise VariablesInvalidas(
            {"tipo": mal_tipo, "esperado": "linea es texto; el resto, números o nulos"}
        )
    no_finitas = [
        c
        for c in columnas
        if c != "linea" and isinstance(variables[c], float) and math.isinf(variables[c])
    ]
    if no_finitas:
        raise VariablesInvalidas(
            {"no_finitas": no_finitas, "motivo": "un infinito no es una medida"}
        )
    t = pd.DataFrame([variables], columns=columnas)
    numericas = [c for c in columnas if c != "linea"]
    t[numericas] = t[numericas].astype("float64")
    return t


def explicacion(artefacto: dict, x: pd.DataFrame, base: float) -> dict:
    """Las `PRINCIPALES` contribuciones de mayor valor absoluto y las demás
    sumadas, para que la cuenta cierre: base + sesgo + principales + resto es la
    salida del modelo, el retraso o el log-odds."""
    c = predict.contribuciones(artefacto, x).iloc[0]
    sesgo = float(c.pop("sesgo"))
    orden = c.abs().sort_values(ascending=False, kind="stable").index
    return {
        "unidad": predict.unidad(artefacto),
        "base": base,
        "sesgo": sesgo,
        "principales": [
            {"variable": v, "valor": float(c[v])} for v in orden[:PRINCIPALES]
        ],
        "resto": float(c[orden[PRINCIPALES:]].sum()),
    }


class Servicio:
    """Los artefactos cargados, por (modelo, horizonte)."""

    def __init__(self, modelos: dict[tuple[str, int], dict], horizontes: list[int]):
        self.modelos_cargados = modelos
        self.horizontes = horizontes

    @classmethod
    def desde_disco(cls) -> Servicio:
        """Todo artefacto que exista en `features.salidas`. Uno que falta no
        tumba el arranque: su endpoint responde que no está disponible."""
        hs = horizontes()
        modelos = {}
        for h in hs:
            rutas = features.salidas(None if h == hs[0] else h)
            for nombre, clave in SALIDA.items():
                if rutas[clave].exists():
                    modelos[nombre, h] = predict.cargar(rutas[clave])
        return cls(modelos, hs)

    def _artefacto(self, nombre: str, horizonte: int | None) -> tuple[int, dict]:
        h = self.horizontes[0] if horizonte is None else horizonte
        if h not in self.horizontes:
            raise HorizonteInvalido({"horizonte": h, "validos": self.horizontes})
        if (nombre, h) not in self.modelos_cargados:
            raise ModeloNoDisponible(f"no hay modelo de {nombre} para h = {h}")
        return h, self.modelos_cargados[nombre, h]

    def modelos(self) -> list[dict]:
        """Lo que hay cargado, para `GET /modelos`."""
        salida = []
        for (nombre, h), a in sorted(self.modelos_cargados.items()):
            m = {
                "modelo": nombre,
                "horizonte_paradas": h,
                "columnas": a["columnas"],
                "n_arboles": int(a["n_arboles"]),
                "mlflow_run_id": a.get("mlflow_run_id"),
                "dias_validacion": a["validacion"]["dias"],
            }
            if nombre == CLASIFICADOR:
                m["umbral"] = float(a["umbral"])
                m["tasa_base_validacion"] = float(a["validacion"]["tasa_base"])
            salida.append(m)
        return salida

    def retraso(
        self, variables: dict, horizonte: int | None = None, explicar: bool = False
    ) -> dict:
        """Segundos de retraso en la parada `stop_sequence + h` (ADR-006)."""
        h, a = self._artefacto(REGRESION, horizonte)
        x = fila(a["columnas"], variables)
        r = {"horizonte_paradas": h, "retraso_s": float(predict.predecir(a, x).iloc[0])}
        if explicar:
            # Un modelo de residuo explica cuánto se aparta de la persistencia.
            base = float(x["retraso_s"].iloc[0]) if a["residuo"] else 0.0
            r["contribuciones"] = explicacion(a, x, base)
        return r

    def mas_de_5min(
        self, variables: dict, horizonte: int | None = None, explicar: bool = False
    ) -> dict:
        """P(más de 5 min tarde) y la decisión con el τ del artefacto (ADR-025):
        se avisa si P ≥ τ, la convención con la que se eligió."""
        h, a = self._artefacto(CLASIFICADOR, horizonte)
        x = fila(a["columnas"], variables)
        p = float(predict.probabilidad(a, x).iloc[0])
        r = {
            "horizonte_paradas": h,
            "probabilidad": p,
            "umbral": float(a["umbral"]),
            "llega_tarde": p >= a["umbral"],
            "tasa_base_validacion": float(a["validacion"]["tasa_base"]),
        }
        if explicar:
            r["contribuciones"] = explicacion(a, x, 0.0)
        return r
