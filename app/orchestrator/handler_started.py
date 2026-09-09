import logging
from multiprocessing import Process

from app.models.escaner import Escaner
from app.orchestrator.process_registry import ProcessRegistry
from app.orchestrator.process_termination import terminate_and_reap
from app.scanner.runner import run_scanner

logger = logging.getLogger(__name__)


def handle_scanner_started(registry: ProcessRegistry, payload: Escaner):
    existing = registry.pop(payload.idEscaner)
    if existing is not None:
        logger.warning(
            "Handler: duplicate SCANNER_STARTED id=%d, killing old process pid=%d",
            payload.idEscaner,
            existing.pid,
        )
        if existing.is_alive():
            terminate_and_reap(existing, timeout=3)

    process = Process(target=run_scanner, args=(payload,), daemon=True)
    process.start()
    registry.add(payload.idEscaner, process)
    logger.info(
        "Handler: SCANNER_STARTED id=%d name='%s' pid=%d",
        payload.idEscaner,
        payload.nombre,
        process.pid,
    )
