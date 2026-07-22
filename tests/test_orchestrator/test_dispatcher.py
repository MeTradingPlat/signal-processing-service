from app.models.events import EventType, TunnelMessage
from app.orchestrator.dispatcher import Dispatcher
from app.orchestrator.process_registry import ProcessRegistry

_SCANNER_PAYLOAD = {
    "idEscaner": 1,
    "nombre": "test",
    "horaInicio": "00:00:00",
    "horaFin": "23:59:00",
    "objTipoEjecucion": {"enumTipoEjecucion": "DIARIA"},
}


def test_dispatcher_routes_scanner_started():
    registry = ProcessRegistry()
    dispatcher = Dispatcher(registry)

    message = TunnelMessage(
        type=EventType.SCANNER_STARTED,
        payload=dict(_SCANNER_PAYLOAD),
    )

    dispatcher.dispatch(message)

    assert len(registry._processes) == 1
    assert 1 in registry._processes

    registry.shutdown_all()


def test_dispatcher_routes_scanner_stopped():
    registry = ProcessRegistry()
    dispatcher = Dispatcher(registry)

    start_payload = dict(_SCANNER_PAYLOAD)
    start_payload["idEscaner"] = 2
    start_message = TunnelMessage(
        type=EventType.SCANNER_STARTED,
        payload=start_payload,
    )
    dispatcher.dispatch(start_message)
    assert 2 in registry._processes

    stop_message = TunnelMessage(
        type=EventType.SCANNER_STOPPED,
        payload={"idEscaner": 2},
    )
    dispatcher.dispatch(stop_message)
    assert 2 not in registry._processes

    registry.shutdown_all()
