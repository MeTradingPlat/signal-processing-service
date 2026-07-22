from multiprocessing import Pipe

from fastapi.testclient import TestClient

from app.api.server import create_app
from app.ipc.sender import PipeSender


def make_client():
    parent_conn, child_conn = Pipe()
    app = create_app(parent_conn)
    app.state.pipe_sender = PipeSender(parent_conn)
    return TestClient(app), child_conn


def test_scanner_started_returns_202():
    client, _ = make_client()

    response = client.post(
        "/signal-processing/escaner",
        json={
            "idEscaner": 1,
            "nombre": "Test",
            "horaInicio": "09:30:00",
            "horaFin": "16:00:00",
            "objEstado": {"enumEstadoEscaner": "INICIADO"},
            "objTipoEjecucion": {"enumTipoEjecucion": "UNA_VEZ"},
            "filtros": [],
            "mercados": [],
        },
    )

    assert response.status_code == 202
    assert response.json()["ok"] is True
    assert response.json()["idEscaner"] == 1


def test_scanner_stopped_returns_202():
    client, _ = make_client()

    response = client.post("/signal-processing/escaner/42/detener")

    assert response.status_code == 202
    assert response.json()["ok"] is True
    assert response.json()["idEscaner"] == 42


def test_health_returns_up():
    client, _ = make_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "UP"
