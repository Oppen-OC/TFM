"""Contratos de entrada/salida de la API.

Los modelos Pydantic viven aquí, no en los routers: los routers validan y
delegan, y `services/` no debe importar nada de `api/`.

Placeholder: los campos concretos dependen del dataset, aún sin definir.
"""

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """Una observación a predecir. Sustituir por los campos reales del dataset."""

    # TODO: campos reales, p. ej. age: int, tenure: int, balance: float
    ...


class PredictResponse(BaseModel):
    prediction: int = Field(..., description="Clase predicha")
    probability: float = Field(
        ..., ge=0.0, le=1.0, description="Probabilidad de la clase positiva"
    )


class HealthResponse(BaseModel):
    status: str
