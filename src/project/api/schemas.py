"""Contratos de entrada y salida de la API.

Los modelos Pydantic viven aquí, no en los routers: los routers validan y
delegan, y `services/` no importa nada de `api/`. La lista de variables no se
copia: la conoce el artefacto, y `services/` comprueba el vector contra ella.
La única copia es el ejemplo de Swagger, y un test la ata a
`features.variables()`.
"""

from pydantic import BaseModel, Field

# Una fila real de ENTRENAMIENTO (línea 92, 18/09/2026), nunca de la prueba:
# mirar predicciones de la prueba antes de su evaluación única la gastaría.
EJEMPLO = {
    "retraso_s": 228.42,
    "retraso_lag1_s": 290.85,
    "retraso_lag2_s": 296.0,
    "retraso_delta_s": -62.43,
    "t_prog_hasta_objetivo_s": 76.0,
    "dist_objetivo_m": 271.25,
    "stop_sequence": 31,
    "abscisa_parada_m": 9050.76,
    "linea_retraso_1min": -132.53,
    "linea_pasos_1min": 5,
    "linea_retraso_5min": -115.85,
    "linea_pasos_5min": 41,
    "linea_retraso_15min": -101.14,
    "linea_pasos_15min": 111,
    "bus_anterior_retraso_s": -419.46,
    "bus_anterior_edad_s": 115.25,
    "tramo_ganado_5min": 5.48,
    "tramo_soporte_5min": 2,
    "tramo_ganado_15min": 5.48,
    "tramo_soporte_15min": 2,
    "tramo_sesgo_s": -7.62,
    "hora": 12.98,
    "dia_semana": 4,
    "fin_de_semana": 0,
    "linea": "92",
}


class Vector(BaseModel):
    """Las variables del modelo, ya calculadas: exactamente las de `GET /modelos`."""

    variables: dict[str, float | str | None] = Field(
        ...,
        description="Nombre → valor. `linea` es texto; el resto, números o null.",
        examples=[EJEMPLO],
    )


class Contribucion(BaseModel):
    variable: str
    valor: float


class Contribuciones(BaseModel):
    """SHAP de esta predicción: base + sesgo + Σ principales + resto es la
    salida del modelo, en `unidad`."""

    unidad: str = Field(..., description="«s del residuo», «s» o «log-odds»")
    base: float = Field(
        ..., description="retraso_s si el modelo es de residuo (ADR-021); si no, 0"
    )
    sesgo: float
    principales: list[Contribucion]
    resto: float = Field(..., description="La suma de las demás variables")


class Retraso(BaseModel):
    horizonte_paradas: int
    retraso_s: float = Field(
        ..., description="Segundos de retraso en la parada stop_sequence + h"
    )
    contribuciones: Contribuciones | None = None


class MasDe5Min(BaseModel):
    horizonte_paradas: int
    probabilidad: float = Field(..., ge=0.0, le=1.0)
    umbral: float = Field(..., description="τ, elegido en la validación (ADR-025)")
    llega_tarde: bool = Field(..., description="probabilidad ≥ umbral")
    tasa_base_validacion: float = Field(
        ..., description="Fracción de más de 5 min en la validación (ADR-006)"
    )
    contribuciones: Contribuciones | None = None


class Modelo(BaseModel):
    modelo: str
    horizonte_paradas: int
    columnas: list[str]
    n_arboles: int
    mlflow_run_id: str | None
    dias_validacion: list[str]
    umbral: float | None = None
    tasa_base_validacion: float | None = None


class HealthResponse(BaseModel):
    status: str
