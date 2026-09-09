import threading
import time
from multiprocessing import Pipe

from app.ipc.sender import PipeSender
from app.models.events import EventType, TunnelMessage
from app.orchestrator.runtime import run_orchestrator

_SCANNER_PAYLOAD = {
    "idEscaner": 555,
    "nombre": "test-runtime",
    "horaInicio": "00:00:00",
    "horaFin": "23:59:00",
    "objTipoEjecucion": {"enumTipoEjecucion": "DIARIA"},
}


def test_run_orchestrator_exits_cleanly_when_pipe_closes():
    parent_conn, child_conn = Pipe()
    thread = threading.Thread(target=run_orchestrator, args=(child_conn,), daemon=True)
    thread.start()

    parent_conn.close()

    thread.join(timeout=5)
    assert not thread.is_alive()


def test_run_orchestrator_starts_and_stops_a_scanner_via_pipe():
    parent_conn, child_conn = Pipe()
    thread = threading.Thread(target=run_orchestrator, args=(child_conn,), daemon=True)
    thread.start()

    sender = PipeSender(parent_conn)
    sender.send(TunnelMessage(type=EventType.SCANNER_STARTED, payload=dict(_SCANNER_PAYLOAD)))
    time.sleep(1.5)

    sender.send(TunnelMessage(type=EventType.SCANNER_STOPPED, payload={"idEscaner": 555}))
    time.sleep(1.0)

    parent_conn.close()
    thread.join(timeout=5)
    assert not thread.is_alive()


def test_run_orchestrator_survives_a_bad_event():
    parent_conn, child_conn = Pipe()
    thread = threading.Thread(target=run_orchestrator, args=(child_conn,), daemon=True)
    thread.start()

    sender = PipeSender(parent_conn)
    sender.send(TunnelMessage(type="SOMETHING_UNKNOWN", payload={"garbage": True}))
    time.sleep(1.0)

    sender.send(TunnelMessage(type=EventType.SCANNER_STARTED, payload=dict(_SCANNER_PAYLOAD)))
    time.sleep(1.5)

    parent_conn.close()
    thread.join(timeout=5)
    assert not thread.is_alive()
