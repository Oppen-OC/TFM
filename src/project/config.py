"""Configuración única del proyecto.

Todo ajuste sale de aquí. `os.getenv` fuera de este módulo es un error: cuando
la misma variable se lee en dos sitios, tarde o temprano se leen dos valores
distintos y el fallo aparece a kilómetros de donde está la causa.

Las rutas se derivan de `data_root`. Cambiar dónde vive el corpus es cambiar
una sola variable, no doce rutas repartidas por el código. El colector de la
Raspberry, por ejemplo, escribe en `/srv/tfm-data` y no en `data/`: eso es
`DATA_ROOT=/srv/tfm-data` en su `.env`, sin tocar una línea de Python.
"""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/project/config.py -> src/project -> src -> raíz del repo
RAIZ = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- API ---------------------------------------------------------------
    # A dónde se CONECTA la UI. Dónde escucha uvicorn lo dice su `--host`, no
    # esto: `0.0.0.0` no vale como destino en Windows ni en macOS.
    api_url: str = "http://127.0.0.1:8000"

    # --- Modelo ------------------------------------------------------------
    model_path: Path = Path("models/model.pkl")

    # --- Datos -------------------------------------------------------------
    # Raíz del corpus. En la Pi es /srv/tfm-data; en local, data/.
    data_root: Path = Field(default=RAIZ / "data")

    # Zona horaria de las fuentes. NO es cosmética: la capa de la EMT alterna
    # entre UTC y hora local naive de un sondeo al siguiente (trampa 002), y
    # resolver esa ambigüedad exige saber cuál es "la local".
    tz_local: str = "Europe/Madrid"

    # Feed por defecto de `gtfs.cargar_trazados()` cuando no se le pasa ruta:
    # lo usan los medidores de `analysis/`. La etiqueta NO sale de aquí, sino de
    # todas las versiones de `gtfs_dir` (ADR-014).
    gtfs_zip: Path = Field(
        default=RAIZ / "data" / "raw" / "gtfs" / "emt_google_transit.zip"
    )

    # Todas las versiones del feed, una por zip. El feed no guarda histórico y
    # sus vigencias se solapan: el etiquetado elige la que manda cada día de
    # servicio (`gtfs.elegir_horario`), no una fija.
    gtfs_dir: Path = Field(default=RAIZ / "data" / "raw" / "gtfs")

    # Clave de la API de Transitland, para consultar las versiones ARCHIVADAS del
    # GTFS (`ingest.transitland`). La gratuita lee metadatos; el zip exige plan de pago.
    transitland_api_key: str = ""

    # --- Rutas derivadas ---------------------------------------------------
    @property
    def raw_dir(self) -> Path:
        """Payloads crudos, uno por sondeo. Nunca se reescriben."""
        return self.data_root / "raw"

    @property
    def curated_dir(self) -> Path:
        """Parquet particionado por fuente y día. Reconstruible desde raw/."""
        return self.data_root / "curated"

    @property
    def reference_dir(self) -> Path:
        """Lo que no cambia con el tiempo: geometría de los tramos de tráfico."""
        return self.data_root / "reference"

    @property
    def interim_dir(self) -> Path:
        return self.data_root / "interim"

    @property
    def processed_dir(self) -> Path:
        return self.data_root / "processed"

    @property
    def zona_horaria(self) -> ZoneInfo:
        return ZoneInfo(self.tz_local)


settings = Settings()
