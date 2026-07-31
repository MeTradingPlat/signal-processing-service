from datetime import datetime, time, timezone
from multiprocessing import Process

from app.models.enums import EnumEstadoEscaner, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.orchestrator.process_registry import ProcessRegistry
from app.scanner.runner import _run_once


def test_una_vez_scanner_completes_when_hora_fin_passed():
    now = datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone.utc)
    escaner = Escaner(
        idEscaner=1,
        nombre="test-una-vez",
        horaInicio=time(9, 30, 0),
        horaFin=time(10, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.UNA_VEZ),
    )

    _run_once(escaner, _now=now)


def test_una_vez_registry_detects_completion():
    registry = ProcessRegistry()

    now = datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone.utc)
    escaner = Escaner(
        idEscaner=2,
        nombre="test-completion",
        horaInicio=time(9, 30, 0),
        horaFin=time(10, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.UNA_VEZ),
    )

    process = Process(target=_run_once, args=(escaner, now), daemon=False)
    process.start()
    registry.add(2, process)

    # cargar_todos() ahora reintenta con backoff antes de rendirse (hasta
    # ~9s sin red, ver test_symbols_retry.py) -- el timeout de join tiene
    # que cubrir eso, no solo el tiempo de un fetch que falla al instante.
    process.join(timeout=15)

    completed = registry.collect_completed()
    assert 2 in completed
