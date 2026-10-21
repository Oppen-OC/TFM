from contextlib import asynccontextmanager

from fastapi import FastAPI

from project.api.routers import prediccion
from project.services.model_service import Servicio


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Carga única al arrancar, no por petición (CLAUDE.md).
    app.state.servicio = Servicio.desde_disco()
    yield


app = FastAPI(title="TFM API", lifespan=lifespan)
app.include_router(prediccion.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
