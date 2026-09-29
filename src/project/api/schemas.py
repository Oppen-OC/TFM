"""Contratos de entrada/salida de la API.

Los modelos Pydantic viven aquí, no en los routers: los routers validan y
delegan, y `services/` no debe importar nada de `api/`.

Placeholder hasta que exista el endpoint de predicción. Lo que ya está fijado:
la salida es el retraso en segundos en la siguiente parada y su variante
binaria, `retraso > 300 s` (ADR-006), y las variables del modelo las da
`features.variables()`, que este módulo no copia. Los modelos de abajo son los
de la plantilla inicial y todavía no reflejan nada de eso.
"""

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Una observación a predecir. Sus campos se definen con el endpoint."""

    ...


class PredictResponse(BaseModel):
    prediction: int = Field(..., description="Clase predicha")
    probability: float = Field(
        ..., ge=0.0, le=1.0, description="Probabilidad de la clase positiva"
    )


class HealthResponse(BaseModel):
    status: str
