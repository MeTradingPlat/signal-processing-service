from datetime import time
from multiprocessing import Process

from app.models.enums import EnumTipoEjecucion
from app.models.escaner import Escaner, TipoEjecucion
from app.orchestrator.process_registry import ProcessRegistry
from app.scanner.runner import run_scanner


def test_add_and_remove_process():
    registry = ProcessRegistry()

    escaner = Escaner(
        idEscaner=99,
        horaInicio=time(0, 0, 0),
        horaFin=time(23, 59, 0),
        objTipoEjecucion=TipoEjecucion(enumTipoEjecucion=EnumTipoEjecucion.DIARIA),
    )
    process = Process(target=run_scanner, args=(escaner,), daemon=True)
    process.start()
    registry.add(99, process)

    assert 99 in registry._processes

    registry.remove(99)

    assert 99 not in registry._processes
    assert not process.is_alive()


def test_remove_nonexistent_does_not_raise():
    registry = ProcessRegistry()
    registry.remove(999)
