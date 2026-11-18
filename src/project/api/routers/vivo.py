"""Demo en vivo por parada: valida, delega en `services/vivo.py` y traduce sus
errores a HTTP. Sin lógica de negocio (CLAUDE.md)."""

from fastapi import APIRouter, Depends, HTTPException, Request

from project.api.schemas import EstadoParada, ParadaVivo
from project.services.vivo import DemoNoDisponible, ParadaDesconocida, Vivo

router = APIRouter(prefix="/vivo", tags=["demo en vivo"])


def vivo(request: Request) -> Vivo:
    """La demo que `main.py` creó al arrancar. Los tests la sustituyen."""
    return request.app.state.vivo


# `def` y no `async def`: `Vivo.parada` puede tardar 30-40 s en hora punta y
# FastAPI ejecuta los `def` en su pool de hilos, sin bloquear el bucle.
@router.get("/paradas", response_model=list[ParadaVivo])
def paradas(v: Vivo = Depends(vivo)) -> list[dict]:
    """Las paradas con servicio hoy."""
    try:
        return v.paradas()
    except DemoNoDisponible as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


@router.get("/parada/{stop_id}", response_model=EstadoParada)
def parada(stop_id: str, v: Vivo = Depends(vivo)) -> dict:
    """Los buses que van a la parada, qué dice el modelo de cada uno y el
    marcador contra la regla simple. Los nulos viajan: son información."""
    try:
        return v.parada(stop_id)
    except ParadaDesconocida as e:
        raise HTTPException(
            status_code=404, detail=f"Ninguna línea para en la parada {stop_id}"
        ) from e
    except DemoNoDisponible as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
