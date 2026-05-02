"""Tests for REST controller endpoints."""
import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.infrastructure.input.rest_controller import crear_router


@pytest.fixture
def app_con_gestor():
    app = FastAPI()
    router = crear_router()
    app.include_router(router)

    mock_gestor = MagicMock()
    app.state.gestor = mock_gestor
    return app, mock_gestor


class TestHealthEndpoint:
    def test_health_retorna_200(self, app_con_gestor):
        app, _ = app_con_gestor
        client = TestClient(app)
        response = client.get("/signal-processing/health")
        assert response.status_code == 200

    def test_health_retorna_status_up(self, app_con_gestor):
        app, _ = app_con_gestor
        client = TestClient(app)
        response = client.get("/signal-processing/health")
        data = response.json()
        assert data["status"] == "UP"

    def test_health_retorna_nombre_servicio(self, app_con_gestor):
        app, _ = app_con_gestor
        client = TestClient(app)
        response = client.get("/signal-processing/health")
        data = response.json()
        assert data["servicio"] == "signal-processing-service"


class TestStatusEndpoint:
    def test_status_retorna_200(self, app_con_gestor):
        app, mock_gestor = app_con_gestor
        mock_gestor.obtener_estado.return_value = {}
        client = TestClient(app)
        response = client.get("/signal-processing/status")
        assert response.status_code == 200

    def test_status_retorna_lista_escaneres_activos(self, app_con_gestor):
        app, mock_gestor = app_con_gestor
        mock_gestor.obtener_estado.return_value = {
            1: {"nombre": "Scanner A", "estado": "ejecutando"},
            2: {"nombre": "Scanner B", "estado": "ejecutando"},
        }
        client = TestClient(app)
        response = client.get("/signal-processing/status")
        data = response.json()
        assert "escaneres_activos" in data
        assert data["total"] == 2

    def test_status_total_cero_si_sin_escaneres(self, app_con_gestor):
        app, mock_gestor = app_con_gestor
        mock_gestor.obtener_estado.return_value = {}
        client = TestClient(app)
        response = client.get("/signal-processing/status")
        data = response.json()
        assert data["total"] == 0

    def test_status_llama_obtener_estado(self, app_con_gestor):
        app, mock_gestor = app_con_gestor
        mock_gestor.obtener_estado.return_value = {}
        client = TestClient(app)
        client.get("/signal-processing/status")
        assert mock_gestor.obtener_estado.call_count >= 1

    def test_status_total_coincide_con_cantidad_escaneres(self, app_con_gestor):
        app, mock_gestor = app_con_gestor
        estado = {i: {"nombre": f"Scanner {i}"} for i in range(5)}
        mock_gestor.obtener_estado.return_value = estado
        client = TestClient(app)
        response = client.get("/signal-processing/status")
        data = response.json()
        assert data["total"] == 5
