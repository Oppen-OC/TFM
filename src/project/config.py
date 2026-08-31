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

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/project/config.py -> src/project -> src -> raíz del repo
RAIZ = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---------------------------------------------------------------
    app_name: str = "tfm"
    env: str = "development"
    log_level: str = "info"

    # --- API ---------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_key: str = ""

    # --- Modelo ------------------------------------------------------------
    model_path: Path = Path("models/model.pkl")

    # --- Datos -------------------------------------------------------------
    # Raíz del corpus. En la Pi es /srv/tfm-data; en local, data/.
    data_root: Path = Field(default=RAIZ / "data")

    # Zona horaria de las fuentes. NO es cosmética: la capa de la EMT alterna
    # entre UTC y hora local naive de un sondeo al siguiente (trampa 002), y
    # resolver esa ambigüedad exige saber cuál es "la local".
    tz_local: str = "Europe/Madrid"

    # GTFS estático de la EMT: el horario teórico del que sale la etiqueta de
    # retraso. Sin esto no hay variable objetivo.
    gtfs_zip: Path = Field(
        default=RAIZ / "data" / "raw" / "gtfs" / "emt_google_transit.zip"
    )

    # --- Rutas derivadas ---------------------------------------------------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def raw_dir(self) -> Path:
        """Payloads crudos, uno por sondeo. Nunca se reescriben."""
        return self.data_root / "raw"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def curated_dir(self) -> Path:
        """Parquet particionado por fuente y día. Reconstruible desde raw/."""
        return self.data_root / "curated"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reference_dir(self) -> Path:
        """Lo que no cambia con el tiempo: geometría de los tramos de tráfico."""
        return self.data_root / "reference"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def interim_dir(self) -> Path:
        return self.data_root / "interim"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def processed_dir(self) -> Path:
        return self.data_root / "processed"

    @property
    def zona_horaria(self) -> ZoneInfo:
        return ZoneInfo(self.tz_local)

    @property
    def api_url(self) -> str:
        """URL a la que CONECTARSE, que no es la misma con la que se hace bind.

        `api_host` es donde escucha uvicorn: `0.0.0.0` significa "todas las
        interfaces". Como destino de una petición no es válido en Windows ni en
        macOS, así que un cliente que lo use tal cual falla solo en algunas
        máquinas — el tipo de bug que no se reproduce en la del que lo escribió.
        """
        host = "127.0.0.1" if self.api_host in ("0.0.0.0", "::") else self.api_host
        return f"http://{host}:{self.api_port}"


settings = Settings()
