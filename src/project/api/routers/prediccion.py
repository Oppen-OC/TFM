"""Predicción: valida el JSON, delega en `services/` y traduce sus errores a
HTTP. Sin lógica de negocio (CLAUDE.md)."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from project.api.schemas import MasDe5Min, Modelo, Retraso, Vector
from project.services.model_service import (
    HorizonteInvalido,
    ModeloNoDisponible,
    Servicio,
    VariablesInvalidas,
)

router = APIRouter(tags=["predicción"])


def servicio(request: Request) -> Servicio:
    """El servicio que `main.py` cargó al arrancar. Los tests lo sustituyen."""
    return request.app.state.servicio


def _llamar(f: Callable[..., dict], *args) -> dict:
    try:
        return f(*args)
    except (VariablesInvalidas, HorizonteInvalido) as e:
        raise HTTPException(status_code=422, detail=e.args[0]) from e
    except ModeloNoDisponible as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/modelos", response_model=list[Modelo])
def modelos(s: Servicio = Depends(servicio)) -> list[dict]:
    """Modelos cargados por horizonte, con las variables que espera cada uno."""
    return s.modelos()


@router.post("/prediccion/retraso", response_model=Retraso)
def retraso(
    cuerpo: Vector, horizonte: int | None = None, s: Servicio = Depends(servicio)
) -> dict:
    """Segundos de retraso en la parada `stop_sequence + horizonte` (ADR-006).
    Sin horizonte, el de `params.yaml`."""
    return _llamar(s.retraso, cuerpo.variables, horizonte)


@router.post("/prediccion/mas-de-5min", response_model=MasDe5Min)
def mas_de_5min(
    cuerpo: Vector, horizonte: int | None = None, s: Servicio = Depends(servicio)
) -> dict:
    """Probabilidad de llegar con más de 5 min de retraso y decisión con el τ
    del modelo (ADR-025). Sin horizonte, el de `params.yaml`."""
    return _llamar(s.mas_de_5min, cuerpo.variables, horizonte)
