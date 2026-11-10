from contextlib import asynccontextmanager

from fastapi import FastAPI

from project.api.routers import prediccion, vivo
from project.services.model_service import Servicio
from project.services.vivo import Vivo


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Carga única al arrancar, no por petición (CLAUDE.md).
    app.state.servicio = Servicio.desde_disco()
    # Nunca lanza: si la demo no puede arrancar, lo dice al pedir una parada.
    app.state.vivo = Vivo.desde_disco(app.state.servicio)
    yield


app = FastAPI(title="TFM API", lifespan=lifespan)
app.include_router(prediccion.router)
app.include_router(vivo.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
