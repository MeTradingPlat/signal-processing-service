from datetime import datetime, time, timezone

from app.models.enums import EnumEstadoEscaner, EnumTipoEjecucion
from app.models.escaner import Escaner, EstadoEscaner, TipoEjecucion
from app.orchestrator.process_registry import ProcessRegistry
from app.scanner.calendar import is_within_window
from app.scanner.runner import _run_once


def test_overnight_window_active_after_midnight():
    now = datetime(2026, 7, 17, 2, 0, 0)
    assert is_within_window(now, time(22, 0, 0), time(6, 0, 0))


def test_overnight_window_active_before_midnight():
    now = datetime(2026, 7, 17, 23, 0, 0)
    assert is_within_window(now, time(22, 0, 0), time(6, 0, 0))


def test_overnight_window_inactive_midday():
    now = datetime(2026, 7, 17, 14, 0, 0)
    assert not is_within_window(now, time(22, 0, 0), time(6, 0, 0))


def test_overnight_window_friday_night_active():
    now = datetime(2026, 7, 17, 23, 0, 0)
    assert is_within_window(now, time(22, 0, 0), time(6, 0, 0))


def test_overnight_window_saturday_morning_inactive():
    now = datetime(2026, 7, 18, 2, 0, 0)
    assert not is_within_window(now, time(22, 0, 0), time(6, 0, 0))


def test_una_vez_completes_across_midnight():
    now = datetime(2026, 7, 17, 23, 30, 0, tzinfo=timezone.utc)
    escaner = Escaner(
        idEscaner=1,
        nombre="overnight",
        horaInicio=time(22, 0, 0),
        horaFin=time(6, 0, 0),
        objEstado=EstadoEscaner(enumEstadoEscaner=EnumEstadoEscaner.INICIADO),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.UNA_VEZ),
    )

    _run_once(escaner, _now=now)


def test_registry_duplicate_add():
    registry = ProcessRegistry()
    from multiprocessing import Process

    escaner = Escaner(
        idEscaner=5,
        nombre="dup-test",
        horaInicio=time(0, 0, 0),
        horaFin=time(0, 0, 1),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.UNA_VEZ),
    )

    p1 = Process(target=_run_once, args=(escaner, datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone.utc)))
    registry.add(5, p1)

    old = registry.pop(5)
    assert old is p1

    p2 = Process(target=_run_once, args=(escaner, datetime(2026, 7, 17, 15, 0, 0, tzinfo=timezone.utc)))
    registry.add(5, p2)
    assert 5 in registry._processes
