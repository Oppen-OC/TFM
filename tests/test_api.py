"""La API valida, delega en `services/` y traduce sus errores. El servicio se
mockea: aquí no se carga ningún modelo (CLAUDE.md)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from project.api.main import app
from project.api.routers.prediccion import servicio
from project.api.schemas import EJEMPLO
from project.services.model_service import (
    HorizonteInvalido,
    ModeloNoDisponible,
    VariablesInvalidas,
)

# Sin `with`: no corre el `lifespan`, así que no se carga ningún modelo.
client = TestClient(app)


@pytest.fixture
def falso():
    s = MagicMock()
    app.dependency_overrides[servicio] = lambda: s
    yield s
    app.dependency_overrides.clear()


def test_health_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_retraso_delega_en_el_servicio(falso):
    falso.retraso.return_value = {"horizonte_paradas": 5, "retraso_s": 212.4}
    r = client.post("/prediccion/retraso?horizonte=5", json={"variables": EJEMPLO})
    assert r.status_code == 200
    assert r.json() == {"horizonte_paradas": 5, "retraso_s": 212.4}
    variables, h = falso.retraso.call_args.args
    assert h == 5
    assert variables == EJEMPLO


def test_sin_horizonte_decide_el_servicio(falso):
    falso.retraso.return_value = {"horizonte_paradas": 1, "retraso_s": 0.0}
    client.post("/prediccion/retraso", json={"variables": EJEMPLO})
    assert falso.retraso.call_args.args[1] is None


def test_mas_de_5min(falso):
    falso.mas_de_5min.return_value = {
        "horizonte_paradas": 1,
        "probabilidad": 0.31,
        "umbral": 0.42,
        "llega_tarde": False,
        "tasa_base_validacion": 0.061,
    }
    r = client.post("/prediccion/mas-de-5min", json={"variables": EJEMPLO})
    assert r.status_code == 200
    assert r.json()["llega_tarde"] is False


def test_variables_y_horizonte_invalidos_son_422(falso):
    falso.retraso.side_effect = VariablesInvalidas({"faltan": ["hora"], "sobran": []})
    r = client.post("/prediccion/retraso", json={"variables": EJEMPLO})
    assert r.status_code == 422
    assert r.json()["detail"] == {"faltan": ["hora"], "sobran": []}
    falso.retraso.side_effect = HorizonteInvalido({"horizonte": 4, "validos": [1, 5]})
    r = client.post("/prediccion/retraso?horizonte=4", json={"variables": EJEMPLO})
    assert r.status_code == 422


def test_un_modelo_que_falta_es_503(falso):
    falso.mas_de_5min.side_effect = ModeloNoDisponible(
        "no hay modelo de clasificador para h = 1"
    )
    r = client.post("/prediccion/mas-de-5min", json={"variables": EJEMPLO})
    assert r.status_code == 503
    assert "clasificador" in r.json()["detail"]


def test_un_cuerpo_mal_formado_no_llega_al_servicio(falso):
    assert client.post("/prediccion/retraso", json={}).status_code == 422
    r = client.post("/prediccion/retraso", json={"variables": {"hora": [1]}})
    assert r.status_code == 422
    r = client.post("/prediccion/retraso?horizonte=cinco", json={"variables": EJEMPLO})
    assert r.status_code == 422
    falso.retraso.assert_not_called()


def test_explicar_llega_al_servicio(falso):
    c = {
        "unidad": "s del residuo",
        "base": 228.42,
        "sesgo": 1.0,
        "principales": [{"variable": "tramo_sesgo_s", "valor": -3.0}],
        "resto": 0.5,
    }
    falso.retraso.return_value = {
        "horizonte_paradas": 1,
        "retraso_s": 226.92,
        "contribuciones": c,
    }
    r = client.post("/prediccion/retraso?explicar=true", json={"variables": EJEMPLO})
    assert r.status_code == 200
    assert r.json()["contribuciones"] == c
    assert falso.retraso.call_args.kwargs == {"explicar": True}


def test_explicar_llega_al_servicio_en_mas_de_5min(falso):
    c = {
        "unidad": "log-odds",
        "base": 0.0,
        "sesgo": -1.2,
        "principales": [{"variable": "retraso_s", "valor": 0.8}],
        "resto": 0.1,
    }
    falso.mas_de_5min.return_value = {
        "horizonte_paradas": 1,
        "probabilidad": 0.4,
        "umbral": 0.3,
        "llega_tarde": True,
        "tasa_base_validacion": 0.2,
        "contribuciones": c,
    }
    r = client.post(
        "/prediccion/mas-de-5min?explicar=true", json={"variables": EJEMPLO}
    )
    assert r.status_code == 200
    assert r.json()["contribuciones"] == c
    assert falso.mas_de_5min.call_args.kwargs == {"explicar": True}


def test_sin_explicar_no_hay_contribuciones(falso):
    falso.retraso.return_value = {"horizonte_paradas": 1, "retraso_s": 0.0}
    r = client.post("/prediccion/retraso", json={"variables": EJEMPLO})
    assert "contribuciones" not in r.json()
    assert falso.retraso.call_args.kwargs == {"explicar": False}


def test_modelos(falso):
    falso.modelos.return_value = [
        {
            "modelo": "clasificador",
            "horizonte_paradas": 1,
            "columnas": list(EJEMPLO),
            "n_arboles": 148,
            "mlflow_run_id": "abc",
            "dias_validacion": ["2026-09-28"],
            "umbral": 0.42,
            "tasa_base_validacion": 0.061,
        }
    ]
    r = client.get("/modelos")
    assert r.status_code == 200
    assert r.json()[0]["umbral"] == 0.42


def test_swagger_lleva_el_ejemplo():
    """«Try it out» en /docs funciona sin teclear las 25 variables."""
    esquema = client.get("/openapi.json").json()
    vector = esquema["components"]["schemas"]["Vector"]["properties"]["variables"]
    assert vector["examples"] == [EJEMPLO]
